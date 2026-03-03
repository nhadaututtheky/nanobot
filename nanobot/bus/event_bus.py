"""Lightweight async pub/sub event bus for internal lifecycle events."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Awaitable, Callable

from loguru import logger

EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


class EventBus:
    """Simple async event bus — subscribe to named events, emit payloads.

    All handlers run concurrently via ``asyncio.gather``.  Exceptions in
    individual handlers are logged but never propagate to the emitter.
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
        """Fire *event* with *payload* to all subscribers (concurrent)."""
        handlers = list(self._handlers.get(event, []))
        if not handlers:
            return

        results = await asyncio.gather(
            *(h(event, payload) for h in handlers),
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, BaseException):
                logger.warning("EventBus handler error on '{}': {}", event, r)
