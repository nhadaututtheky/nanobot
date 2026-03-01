"""System-level handlers: status, health, models, heartbeat, presence, logs, update."""

from __future__ import annotations

import logging
import platform
import time
from typing import Any

from nanobot.gateway.connection import ClientConnection
from nanobot.gateway.context import GatewayContext
from nanobot.gateway.protocol import GatewayError

logger = logging.getLogger(__name__)


async def handle_status(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Aggregate system status from all services."""
    cron_status = ctx.cron.status()
    return {
        "agent": {"running": ctx.agent._running},
        "channels": {name: True for name in ctx.channels.enabled_channels},
        "cron": cron_status,
        "heartbeat": {"enabled": ctx.heartbeat._enabled if hasattr(ctx.heartbeat, "_enabled") else True},
        "gateway": {"clients": ctx.broadcaster.client_count},
    }


async def handle_health(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """System health snapshot."""
    return {
        "ok": True,
        "uptime": time.monotonic(),
        "platform": platform.system(),
        "python": platform.python_version(),
        "connections": ctx.broadcaster.client_count,
    }


async def handle_models_list(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """List available models from provider registry."""
    from nanobot.llm.registry import PROVIDERS

    models: list[dict[str, Any]] = []
    for provider_name, provider_cls in PROVIDERS.items():
        if hasattr(provider_cls, "MODELS"):
            for model_id in provider_cls.MODELS:
                models.append({"id": model_id, "provider": provider_name})

    # Include model_overrides from config if present
    overrides = getattr(ctx.config.agents.defaults, "model_overrides", None)
    return {
        "models": models,
        "default": ctx.config.agents.defaults.model,
        "overrides": overrides or {},
    }


async def handle_last_heartbeat(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Read the last heartbeat info."""
    hb_file = ctx.heartbeat._read_heartbeat_file() if hasattr(ctx.heartbeat, "_read_heartbeat_file") else None
    return {
        "content": hb_file,
        "enabled": ctx.heartbeat._enabled if hasattr(ctx.heartbeat, "_enabled") else True,
        "intervalS": ctx.heartbeat._interval_s if hasattr(ctx.heartbeat, "_interval_s") else 1800,
    }


async def handle_system_presence(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """List connected gateway clients."""
    clients = []
    for c in ctx.broadcaster.clients:
        clients.append({
            "connId": c.conn_id,
            "role": c.role,
            "deviceId": c.device_id,
            "client": c.client_info,
            "authenticated": c.authenticated,
        })
    return {"clients": clients}


async def handle_logs_tail(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Read last N lines from log file."""
    limit = min(params.get("limit", 100), 1000)  # Cap at 1000 lines
    cursor = params.get("cursor")
    if isinstance(cursor, int) and cursor < 0:
        cursor = 0

    log_path = ctx.config.workspace_path / "logs" / "nanobot.log"
    if not log_path.exists():
        return {"lines": [], "cursor": 0, "hasMore": False}

    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()

        start = cursor if isinstance(cursor, int) else max(0, len(lines) - limit)
        selected = lines[start:start + limit]

        return {
            "lines": selected,
            "cursor": start + len(selected),
            "hasMore": (start + len(selected)) < len(lines),
        }
    except Exception as exc:
        logger.warning("Log read failed: %s", exc)
        raise GatewayError("LOG_READ_FAILED", "failed to read log file")


async def handle_update_run(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Run system update through agent."""
    session_key = params.get("sessionKey", "system:update")
    response = await ctx.agent.process_direct(
        "Check for and apply any available system updates.",
        session_key=session_key,
        channel="system",
        chat_id="update",
    )
    return {"response": response}


async def handle_usage_cost(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Aggregate cost from session usage data."""
    sessions_dir = ctx.config.workspace_path / "sessions"
    if not sessions_dir.exists():
        return {"totalCost": 0, "byModel": {}, "bySession": {}}

    import json

    # Scan session files for usage metadata
    total_cost = 0.0
    total_tokens = 0
    by_model: dict[str, float] = {}
    by_session: dict[str, float] = {}

    for f in sessions_dir.glob("*.jsonl"):
        session_cost = 0.0
        try:
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                usage = entry.get("usage")
                if isinstance(usage, dict):
                    cost = usage.get("cost", 0)
                    if isinstance(cost, (int, float)):
                        session_cost += cost
                        model = entry.get("model", "unknown")
                        by_model[model] = by_model.get(model, 0) + cost
                    tokens = usage.get("total_tokens", 0)
                    if isinstance(tokens, int):
                        total_tokens += tokens
        except Exception:
            continue
        if session_cost > 0:
            key = f.stem
            by_session[key] = session_cost
            total_cost += session_cost

    return {
        "totalCost": total_cost,
        "totalTokens": total_tokens,
        "byModel": by_model,
        "bySession": by_session,
        "currency": "USD",
    }


ROUTES = {
    "status": handle_status,
    "health": handle_health,
    "models.list": handle_models_list,
    "last-heartbeat": handle_last_heartbeat,
    "system-presence": handle_system_presence,
    "logs.tail": handle_logs_tail,
    "update.run": handle_update_run,
    "usage.cost": handle_usage_cost,
}
