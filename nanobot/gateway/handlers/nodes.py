"""Node handlers: list (single-node stub for now)."""

from __future__ import annotations

from typing import Any

from nanobot.gateway.connection import ClientConnection
from nanobot.gateway.context import GatewayContext


async def handle_node_list(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Return node list — single-node for now."""
    return {"nodes": {}}


ROUTES = {
    "node.list": handle_node_list,
}
