"""WebSocket server lifecycle — accept, challenge/auth handshake, dispatch."""

from __future__ import annotations

import asyncio
import hmac
import logging
import secrets
import time
from typing import Any
from uuid import uuid4

import websockets
from websockets.asyncio.server import ServerConnection

from .connection import ClientConnection
from .context import GatewayContext
from .dispatcher import Dispatcher
from .protocol import RequestFrame, parse_request

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 3


_MAX_CONNECTIONS = 50
_active_connections: set[str] = set()


async def start_gateway(ctx: GatewayContext, dispatcher: Dispatcher) -> None:
    """Start the WS server and serve forever."""
    host = ctx.config.gateway.host
    port = ctx.config.gateway.port

    async def handler(ws: ServerConnection) -> None:
        if len(_active_connections) >= _MAX_CONNECTIONS:
            await ws.close(4029, "too many connections")
            return
        conn_id = uuid4().hex[:12]
        _active_connections.add(conn_id)
        try:
            await _handle_connection(ctx, dispatcher, ws, conn_id)
        finally:
            _active_connections.discard(conn_id)

    logger.info("gateway listening on ws://%s:%s", host, port)
    async with websockets.serve(handler, host, port, ping_interval=30, ping_timeout=10, max_size=2 * 1024 * 1024):
        await asyncio.Future()  # run forever


async def _handle_connection(
    ctx: GatewayContext,
    dispatcher: Dispatcher,
    ws: ServerConnection,
    conn_id: str | None = None,
) -> None:
    """Handle a single WebSocket connection lifecycle."""
    if conn_id is None:
        conn_id = uuid4().hex[:12]
    conn = ClientConnection(ws, conn_id)

    # Step 1: Send challenge
    nonce = secrets.token_hex(16)
    await conn.send_event("connect.challenge", {"nonce": nonce})

    try:
        async for raw in ws:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")

            req = parse_request(raw)
            if req is None:
                continue

            # First message must be "connect"
            if not conn.authenticated:
                if req.method != "connect":
                    await conn.send_error(req.id, "AUTH_REQUIRED", "send connect first")
                    continue
                await _handle_connect(ctx, dispatcher, conn, req, nonce)
                continue

            # Authenticated — normal dispatch
            await dispatcher.dispatch(ctx, conn, req)

    except websockets.ConnectionClosed:
        pass
    except Exception:
        logger.exception("connection error for %s", conn_id)
    finally:
        ctx.broadcaster.remove(conn)
        logger.debug("client %s disconnected", conn_id)


async def _handle_connect(
    ctx: GatewayContext,
    dispatcher: Dispatcher,
    conn: ClientConnection,
    req: RequestFrame,
    nonce: str,
) -> None:
    """Validate connect request and promote to authenticated."""
    params = req.params

    # Protocol version check
    min_proto = params.get("minProtocol", 0)
    max_proto = params.get("maxProtocol", 0)
    if not (min_proto <= PROTOCOL_VERSION <= max_proto):
        await conn.send_error(req.id, "PROTOCOL_MISMATCH",
                              f"server protocol {PROTOCOL_VERSION} not in [{min_proto},{max_proto}]")
        await conn.close(4008, "protocol mismatch")
        return

    # Token auth (simple string match, empty config token = allow all)
    expected_token = getattr(ctx.config.gateway, "token", "")
    auth = params.get("auth") or {}
    client_token = auth.get("token", "")
    if expected_token and not hmac.compare_digest(client_token, expected_token):
        await conn.send_error(
            req.id, "AUTH_FAILED", "invalid token",
            details={"detailCode": "AUTH_TOKEN_MISMATCH"},
        )
        await conn.close(4008, "auth failed")
        return

    # Mark authenticated — server assigns role/scopes, not client
    conn.authenticated = True
    conn.role = "operator"
    conn.scopes = ["operator.admin", "operator.approvals", "operator.pairing"]
    conn.client_info = params.get("client", {})
    device = params.get("device") or {}
    conn.device_id = device.get("id", "")

    # Register with broadcaster
    ctx.broadcaster.add(conn)

    # Build hello payload
    hello: dict[str, Any] = {
        "type": "hello-ok",
        "protocol": PROTOCOL_VERSION,
        "server": {
            "version": "0.1.0",
            "connId": conn.conn_id,
        },
        "features": {
            "methods": dispatcher.method_names,
            "events": [
                "chat", "cron", "presence", "agent",
                "device.pair.requested", "device.pair.resolved",
                "exec.approval.requested", "exec.approval.resolved",
            ],
        },
        "auth": {
            "role": conn.role,
            "scopes": conn.scopes,
            "issuedAtMs": int(time.time() * 1000),
        },
        "policy": {
            "tickIntervalMs": 30_000,
        },
    }

    await conn.send_response(req.id, hello)
    logger.info("client %s authenticated (role=%s)", conn.conn_id, conn.role)
