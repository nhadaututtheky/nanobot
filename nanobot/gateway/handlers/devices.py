"""Device handlers: pair list/approve/reject, token rotate/revoke."""

from __future__ import annotations

import json
import logging
import secrets
import time
from pathlib import Path
from typing import Any

from nanobot.gateway.connection import ClientConnection
from nanobot.gateway.context import GatewayContext
from nanobot.gateway.protocol import GatewayError

logger = logging.getLogger(__name__)


def _device_store_path(ctx: GatewayContext) -> Path:
    return ctx.config.workspace_path / ".gateway" / "devices.json"


def _load_device_store(ctx: GatewayContext) -> dict[str, Any]:
    path = _device_store_path(ctx)
    if not path.exists():
        return {"devices": {}, "pairRequests": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"devices": {}, "pairRequests": []}


def _save_device_store(ctx: GatewayContext, store: dict[str, Any]) -> None:
    path = _device_store_path(ctx)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2), encoding="utf-8")


async def handle_device_pair_list(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """List device pairing requests."""
    store = _load_device_store(ctx)
    return {
        "requests": store.get("pairRequests", []),
        "devices": store.get("devices", {}),
    }


async def handle_device_pair_approve(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Approve a device pairing request."""
    request_id = params.get("requestId")
    if not request_id:
        raise GatewayError("INVALID_PARAMS", "requestId required")

    store = _load_device_store(ctx)
    requests = store.get("pairRequests", [])

    found = None
    for req in requests:
        if req.get("id") == request_id:
            found = req
            break

    if not found:
        raise GatewayError("NOT_FOUND", f"pair request {request_id} not found")

    # Move from requests to devices
    device_id = found.get("deviceId", request_id)
    store["devices"][device_id] = {
        **found,
        "approved": True,
        "approvedAt": int(time.time() * 1000),
    }
    store["pairRequests"] = [r for r in requests if r.get("id") != request_id]
    _save_device_store(ctx, store)

    await ctx.broadcaster.broadcast("device.pair.resolved", {
        "requestId": request_id,
        "approved": True,
    })

    return {"ok": True}


async def handle_device_pair_reject(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Reject a device pairing request."""
    request_id = params.get("requestId")
    if not request_id:
        raise GatewayError("INVALID_PARAMS", "requestId required")

    store = _load_device_store(ctx)
    requests = store.get("pairRequests", [])
    store["pairRequests"] = [r for r in requests if r.get("id") != request_id]
    _save_device_store(ctx, store)

    await ctx.broadcaster.broadcast("device.pair.resolved", {
        "requestId": request_id,
        "approved": False,
    })

    return {"ok": True}


async def handle_device_token_rotate(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Generate a new auth token for a device."""
    device_id = params.get("deviceId")
    if not device_id:
        raise GatewayError("INVALID_PARAMS", "deviceId required")

    store = _load_device_store(ctx)
    device = store.get("devices", {}).get(device_id)
    if not device:
        raise GatewayError("NOT_FOUND", f"device {device_id} not found")

    new_token = secrets.token_urlsafe(32)
    role = params.get("role", "operator")
    scopes = params.get("scopes", ["operator.admin"])

    device["token"] = new_token
    device["role"] = role
    device["scopes"] = scopes
    device["tokenRotatedAt"] = int(time.time() * 1000)
    store["devices"][device_id] = device
    _save_device_store(ctx, store)

    return {"token": new_token, "role": role, "scopes": scopes}


async def handle_device_token_revoke(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Revoke a device's auth token."""
    device_id = params.get("deviceId")
    if not device_id:
        raise GatewayError("INVALID_PARAMS", "deviceId required")

    store = _load_device_store(ctx)
    device = store.get("devices", {}).get(device_id)
    if not device:
        raise GatewayError("NOT_FOUND", f"device {device_id} not found")

    device.pop("token", None)
    device["tokenRevokedAt"] = int(time.time() * 1000)
    store["devices"][device_id] = device
    _save_device_store(ctx, store)

    return {"ok": True}


ROUTES = {
    "device.pair.list": handle_device_pair_list,
    "device.pair.approve": handle_device_pair_approve,
    "device.pair.reject": handle_device_pair_reject,
    "device.token.rotate": handle_device_token_rotate,
    "device.token.revoke": handle_device_token_revoke,
}
