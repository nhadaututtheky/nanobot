"""Lightweight async pub/sub event bus for internal lifecycle events."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Awaitable, Callable

from loguru import logger

EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


class EventBus:
    """Simple async event bus — subscribe to named events, emit payloads.

    Handlers are dispatched as fire-and-forget tasks so a slow handler
    never blocks other subscribers or the emitter.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventCallback]] = defaultdict(list)

    def subscribe(self, event: str, handler: EventCallback) -> None:
        """Register *handler* for *event*."""
        self._handlers[event].append(handler)

    def unsubscribe(self, event: str, handler: EventCallback) -> None:
        """Remove *handler* from *event* (no-op if not found)."""
        handlers = self._handlers.get(event)
        if handlers:
            try:
                handlers.remove(handler)
            except ValueError:
                pass

    async def emit(self, event: str, payload: dict[str, Any]) -> None:
        """Fire *event* with *payload* to all subscribers (fire-and-forget)."""
        handlers = list(self._handlers.get(event, []))
        if not handlers:
            return

        for h in handlers:
            try:
                asyncio.create_task(self._safe_call(h, event, payload))
            except RuntimeError:
                pass  # No running event loop

    async def _safe_call(
        self, handler: EventCallback, event: str, payload: dict[str, Any]
    ) -> None:
        """Run a single handler with isolated exception handling."""
        try:
            await handler(event, payload)
        except Exception as e:
            logger.warning("EventBus handler error on '{}': {}", event, e)
