"""Channel handlers: status, logout, web login start/wait."""

from __future__ import annotations

import logging
from typing import Any

from nanobot.gateway.connection import ClientConnection
from nanobot.gateway.context import GatewayContext
from nanobot.gateway.protocol import GatewayError

logger = logging.getLogger(__name__)


async def handle_channels_status(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Get status of all channels."""
    if hasattr(ctx.channels, "get_status"):
        return ctx.channels.get_status()

    # Fallback: build status from enabled channels
    status: dict[str, Any] = {}
    for name in ctx.channels.enabled_channels:
        channel = ctx.channels.channels.get(name)
        status[name] = {
            "enabled": True,
            "running": channel is not None,
        }
    return status


async def handle_channels_logout(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Stop a specific channel."""
    channel_name = params.get("channel") or params.get("channelId")
    if not channel_name:
        raise GatewayError("INVALID_PARAMS", "channel required")

    channel = ctx.channels.channels.get(channel_name)
    if channel is None:
        raise GatewayError("NOT_FOUND", f"channel {channel_name} not found")

    await channel.stop()
    return {"ok": True}


async def handle_web_login_start(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Start WhatsApp QR login flow (requires whatsapp bridge)."""
    channel = ctx.channels.channels.get("whatsapp")
    if channel is None:
        raise GatewayError("NOT_AVAILABLE", "whatsapp channel not configured")

    if hasattr(channel, "start_login"):
        force = params.get("force", False)
        timeout_ms = min(params.get("timeoutMs", 60000), 120_000)
        result = await channel.start_login(force=force, timeout_ms=timeout_ms)
        return result

    raise GatewayError("NOT_SUPPORTED", "whatsapp channel does not support web login")


async def handle_web_login_wait(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Wait for WhatsApp connection after QR scan."""
    channel = ctx.channels.channels.get("whatsapp")
    if channel is None:
        raise GatewayError("NOT_AVAILABLE", "whatsapp channel not configured")

    if hasattr(channel, "wait_login"):
        timeout_ms = min(params.get("timeoutMs", 60000), 120_000)
        result = await channel.wait_login(timeout_ms=timeout_ms)
        return result

    raise GatewayError("NOT_SUPPORTED", "whatsapp channel does not support web login")


ROUTES = {
    "channels.status": handle_channels_status,
    "channels.logout": handle_channels_logout,
    "web.login.start": handle_web_login_start,
    "web.login.wait": handle_web_login_wait,
}
