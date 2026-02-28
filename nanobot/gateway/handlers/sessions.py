"""Session handlers: list, patch, delete, usage, usage.timeseries, usage.logs."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from nanobot.gateway.context import GatewayContext
from nanobot.gateway.connection import ClientConnection
from nanobot.gateway.protocol import GatewayError

logger = logging.getLogger(__name__)


def _sessions_dir(ctx: GatewayContext) -> Path:
    return ctx.config.workspace_path / "sessions"


async def handle_sessions_list(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """List all sessions with metadata."""
    raw = ctx.session_manager.list_sessions()
    include_global = params.get("includeGlobal", False)
    include_unknown = params.get("includeUnknown", False)
    limit = params.get("limit")

    sessions = []
    for item in raw:
        key = item.get("key", "")
        if not include_global and key.startswith("system:"):
            continue
        if not include_unknown and ":" not in key:
            continue
        sessions.append(item)

    if isinstance(limit, int) and limit > 0:
        sessions = sessions[:limit]

    return {"sessions": sessions}


async def handle_sessions_patch(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Update session metadata (label, thinkingLevel, etc.)."""
    key = params.get("key")
    if not key:
        raise GatewayError("INVALID_PARAMS", "key required")

    session = ctx.session_manager.get_or_create(key)

    for field in ("label", "thinkingLevel", "verboseLevel", "reasoningLevel"):
        if field in params:
            val = params[field]
            if val is None:
                session.metadata.pop(field, None)
            else:
                session.metadata[field] = val

    ctx.session_manager.save(session)
    return {"ok": True}


async def handle_sessions_delete(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Delete a session and optionally its transcript."""
    key = params.get("key")
    if not key:
        raise GatewayError("INVALID_PARAMS", "key required")

    delete_transcript = params.get("deleteTranscript", False)

    # Remove from memory cache
    ctx.session_manager.invalidate(key)

    # Delete file if requested
    if delete_transcript:
        safe_key = key.replace(":", "_").replace("/", "_")
        base = _sessions_dir(ctx).resolve()
        path = (base / f"{safe_key}.jsonl").resolve()
        if path.is_relative_to(base) and path.exists():
            path.unlink()

    return {"ok": True}


async def handle_sessions_usage(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Get session usage data."""
    sessions_dir = _sessions_dir(ctx)
    if not sessions_dir.exists():
        return {"sessions": []}

    limit = params.get("limit", 50)
    results: list[dict[str, Any]] = []

    for f in sessions_dir.glob("*.jsonl"):
        session_data: dict[str, Any] = {"key": f.stem, "totalTokens": 0, "turns": 0}
        try:
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("_type") == "metadata":
                    session_data["createdAt"] = entry.get("created_at")
                    session_data["updatedAt"] = entry.get("updated_at")
                    continue
                usage = entry.get("usage")
                if isinstance(usage, dict):
                    tokens = usage.get("total_tokens", 0)
                    if isinstance(tokens, int):
                        session_data["totalTokens"] += tokens
                if entry.get("role") == "user":
                    session_data["turns"] += 1
        except Exception:
            continue
        results.append(session_data)

    results.sort(key=lambda x: x.get("updatedAt", ""), reverse=True)
    return {"sessions": results[:limit]}


async def handle_sessions_usage_timeseries(
    ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any],
) -> Any:
    """Get usage timeseries for a specific session."""
    key = params.get("key")
    if not key:
        raise GatewayError("INVALID_PARAMS", "key required")

    safe_key = key.replace(":", "_").replace("/", "_")
    path = _sessions_dir(ctx) / f"{safe_key}.jsonl"
    if not path.exists():
        return {"points": []}

    points: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            usage = entry.get("usage")
            ts = entry.get("timestamp")
            if isinstance(usage, dict) and ts:
                points.append({
                    "timestamp": ts,
                    "tokens": usage.get("total_tokens", 0),
                    "cost": usage.get("cost", 0),
                })
    except Exception:
        pass

    return {"points": points}


async def handle_sessions_usage_logs(
    ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any],
) -> Any:
    """Read last N usage entries from session log."""
    key = params.get("key")
    if not key:
        raise GatewayError("INVALID_PARAMS", "key required")

    limit = params.get("limit", 50)
    safe_key = key.replace(":", "_").replace("/", "_")
    path = _sessions_dir(ctx) / f"{safe_key}.jsonl"
    if not path.exists():
        return {"entries": []}

    entries: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("_type") == "metadata":
                continue
            usage = entry.get("usage")
            if isinstance(usage, dict):
                entries.append({
                    "role": entry.get("role"),
                    "model": entry.get("model"),
                    "timestamp": entry.get("timestamp"),
                    "usage": usage,
                })
    except Exception:
        pass

    return {"entries": entries[-limit:]}


ROUTES = {
    "sessions.list": handle_sessions_list,
    "sessions.patch": handle_sessions_patch,
    "sessions.delete": handle_sessions_delete,
    "sessions.usage": handle_sessions_usage,
    "sessions.usage.timeseries": handle_sessions_usage_timeseries,
    "sessions.usage.logs": handle_sessions_usage_logs,
}
