"""Exec approval handlers: get/set gateway approvals, node approvals, resolve."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from nanobot.gateway.connection import ClientConnection
from nanobot.gateway.context import GatewayContext
from nanobot.gateway.protocol import GatewayError

logger = logging.getLogger(__name__)


def _approvals_path(ctx: GatewayContext) -> Path:
    return ctx.config.workspace_path / ".gateway" / "exec-approvals.json"


def _node_approvals_path(ctx: GatewayContext, node_id: str) -> Path:
    base = (ctx.config.workspace_path / ".gateway" / "nodes").resolve()
    path = (base / node_id / "exec-approvals.json").resolve()
    if not path.is_relative_to(base):
        raise GatewayError("FORBIDDEN", "invalid nodeId")
    return path


def _hash_content(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


async def handle_exec_approvals_get(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Read gateway exec approvals config."""
    path = _approvals_path(ctx)
    if not path.exists():
        return {"file": {}, "hash": ""}

    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}

    return {"file": data, "hash": _hash_content(raw)}


async def handle_exec_approvals_set(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Write gateway exec approvals config."""
    file_data = params.get("file")
    base_hash = params.get("baseHash")
    if file_data is None:
        raise GatewayError("INVALID_PARAMS", "file required")

    path = _approvals_path(ctx)

    # Conflict check
    if base_hash and path.exists():
        current = path.read_text(encoding="utf-8")
        if _hash_content(current) != base_hash:
            raise GatewayError("CONFLICT", "approvals modified by another client")

    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(file_data, indent=2)
    path.write_text(raw, encoding="utf-8")

    return {"hash": _hash_content(raw)}


async def handle_exec_approvals_node_get(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Read node-specific exec approvals."""
    node_id = params.get("nodeId")
    if not node_id:
        raise GatewayError("INVALID_PARAMS", "nodeId required")

    path = _node_approvals_path(ctx, node_id)
    if not path.exists():
        return {"file": {}, "hash": ""}

    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}

    return {"file": data, "hash": _hash_content(raw)}


async def handle_exec_approvals_node_set(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Write node-specific exec approvals."""
    node_id = params.get("nodeId")
    file_data = params.get("file")
    base_hash = params.get("baseHash")
    if not node_id or file_data is None:
        raise GatewayError("INVALID_PARAMS", "nodeId and file required")

    path = _node_approvals_path(ctx, node_id)

    if base_hash and path.exists():
        current = path.read_text(encoding="utf-8")
        if _hash_content(current) != base_hash:
            raise GatewayError("CONFLICT", "approvals modified by another client")

    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(file_data, indent=2)
    path.write_text(raw, encoding="utf-8")

    return {"hash": _hash_content(raw)}


async def handle_exec_approval_resolve(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Resolve a pending exec approval request."""
    approval_id = params.get("id")
    approved = params.get("approved")
    if not approval_id or approved is None:
        raise GatewayError("INVALID_PARAMS", "id and approved required")

    await ctx.broadcaster.broadcast("exec.approval.resolved", {
        "id": approval_id,
        "approved": approved,
    })

    return {"ok": True}


ROUTES = {
    "exec.approvals.get": handle_exec_approvals_get,
    "exec.approvals.set": handle_exec_approvals_set,
    "exec.approvals.node.get": handle_exec_approvals_node_get,
    "exec.approvals.node.set": handle_exec_approvals_node_set,
    "exec.approval.resolve": handle_exec_approval_resolve,
}
