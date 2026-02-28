"""Config handlers: get, schema, set, apply."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from nanobot.gateway.context import GatewayContext
from nanobot.gateway.connection import ClientConnection
from nanobot.gateway.protocol import GatewayError

logger = logging.getLogger(__name__)


def _hash_content(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


async def handle_config_get(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Read current config file raw text + parsed + hash."""
    try:
        raw = ctx.config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raw = "{}"

    return {
        "raw": raw,
        "hash": _hash_content(raw),
    }


async def handle_config_schema(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Return JSON Schema for the config model."""
    from nanobot.config.schema import Config
    return {"schema": Config.model_json_schema()}


async def _validate_and_save(ctx: GatewayContext, raw: str, base_hash: str | None) -> str:
    """Validate config, save to disk, return new hash. No side effects."""
    import json
    from nanobot.config.schema import Config

    # Conflict detection
    try:
        current = ctx.config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        current = "{}"
    if base_hash and _hash_content(current) != base_hash:
        raise GatewayError("CONFLICT", "config was modified by another client")

    # Validate before saving
    try:
        parsed = json.loads(raw)
        Config.model_validate(parsed)
    except Exception as exc:
        raise GatewayError("VALIDATION_FAILED", str(exc))

    ctx.config_path.write_text(raw, encoding="utf-8")
    return _hash_content(raw)


async def handle_config_set(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Save config and trigger reconnect via 1012 close."""
    raw = params.get("raw")
    if not isinstance(raw, str):
        raise GatewayError("INVALID_PARAMS", "raw config text required")

    new_hash = await _validate_and_save(ctx, raw, params.get("baseHash"))

    # Close all clients with 1012 (service restart) — UI handles graceful reconnect
    # Note: response is sent by dispatcher before this, since we return first
    import asyncio
    asyncio.get_running_loop().call_soon(
        lambda: asyncio.ensure_future(ctx.broadcaster.close_all(code=1012, reason="config changed"))
    )

    return {"hash": new_hash}


async def handle_config_apply(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Save config + run agent message to apply changes."""
    raw = params.get("raw")
    if not isinstance(raw, str):
        raise GatewayError("INVALID_PARAMS", "raw config text required")

    new_hash = await _validate_and_save(ctx, raw, params.get("baseHash"))

    # Fire agent task in background, then schedule close_all
    import asyncio
    session_key = params.get("sessionKey", "system:config")

    async def _apply_and_close() -> None:
        try:
            await ctx.agent.process_direct(
                "Configuration has been updated. Apply any necessary changes.",
                session_key=session_key,
                channel="system",
                chat_id="config",
            )
        finally:
            await ctx.broadcaster.close_all(code=1012, reason="config changed")

    asyncio.create_task(_apply_and_close())

    return {"hash": new_hash}


ROUTES = {
    "config.get": handle_config_get,
    "config.schema": handle_config_schema,
    "config.set": handle_config_set,
    "config.apply": handle_config_apply,
}
