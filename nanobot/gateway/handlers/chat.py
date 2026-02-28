"""Chat handlers: send (with streaming), history, abort."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import uuid4

from nanobot.gateway.context import GatewayContext
from nanobot.gateway.connection import ClientConnection
from nanobot.gateway.protocol import GatewayError

logger = logging.getLogger(__name__)


async def handle_chat_send(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Send a chat message — streams deltas via broadcast events, returns void."""
    session_key = params.get("sessionKey")
    message = params.get("message")
    if not session_key or not message:
        raise GatewayError("INVALID_PARAMS", "sessionKey and message required")

    deliver = params.get("deliver", False)

    # Limit concurrent runs per session
    active = ctx.active_runs.get(session_key, [])
    active = [t for t in active if not t.done()]
    ctx.active_runs[session_key] = active
    if len(active) >= 3:
        raise GatewayError("RATE_LIMITED", "too many concurrent runs for this session")

    run_id = uuid4().hex

    async def on_progress(text: str) -> None:
        await ctx.broadcaster.broadcast("chat", {
            "runId": run_id,
            "sessionKey": session_key,
            "state": "delta",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": text}],
            },
        })

    async def _run() -> None:
        try:
            await ctx.broadcaster.broadcast("chat", {
                "runId": run_id,
                "sessionKey": session_key,
                "state": "started",
            })

            # Determine channel/chat_id from session_key
            if ":" in session_key:
                channel, chat_id = session_key.split(":", 1)
            else:
                channel, chat_id = "web", session_key

            response = await ctx.agent.process_direct(
                message,
                session_key=session_key,
                channel=channel,
                chat_id=chat_id,
                on_progress=on_progress,
            )

            await ctx.broadcaster.broadcast("chat", {
                "runId": run_id,
                "sessionKey": session_key,
                "state": "done",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": response or ""}],
                },
            })

            # Optionally deliver to channel
            if deliver and response:
                from nanobot.bus.events import OutboundMessage
                await ctx.bus.publish_outbound(OutboundMessage(
                    channel=channel,
                    chat_id=chat_id,
                    content=response,
                ))

        except asyncio.CancelledError:
            await ctx.broadcaster.broadcast("chat", {
                "runId": run_id,
                "sessionKey": session_key,
                "state": "aborted",
            })
        except Exception as exc:
            logger.exception("chat.send error for %s", session_key)
            await ctx.broadcaster.broadcast("chat", {
                "runId": run_id,
                "sessionKey": session_key,
                "state": "error",
                "error": str(exc),
            })

    task = asyncio.create_task(_run())
    ctx.active_runs.setdefault(session_key, []).append(task)

    # Cleanup when done
    def _cleanup(t: asyncio.Task[None]) -> None:
        tasks = ctx.active_runs.get(session_key, [])
        if t in tasks:
            tasks.remove(t)

    task.add_done_callback(_cleanup)

    return {"runId": run_id}


async def handle_chat_history(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Load chat history for a session."""
    session_key = params.get("sessionKey")
    if not session_key:
        raise GatewayError("INVALID_PARAMS", "sessionKey required")

    limit = params.get("limit", 100)
    session = ctx.session_manager.get_or_create(session_key)
    messages = session.get_history(max_messages=limit)

    thinking_level = session.metadata.get("thinkingLevel")
    result: dict[str, Any] = {"messages": messages}
    if thinking_level:
        result["thinkingLevel"] = thinking_level
    return result


async def handle_chat_abort(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Abort running chat tasks for a session."""
    session_key = params.get("sessionKey")
    if not session_key:
        raise GatewayError("INVALID_PARAMS", "sessionKey required")

    tasks = ctx.active_runs.get(session_key, [])
    cancelled = 0
    for task in list(tasks):
        if not task.done():
            task.cancel()
            cancelled += 1
    ctx.active_runs.pop(session_key, None)

    return {"cancelled": cancelled}


ROUTES = {
    "chat.send": handle_chat_send,
    "chat.history": handle_chat_history,
    "chat.abort": handle_chat_abort,
}
