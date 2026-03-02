"""Internal broadcast bus for multi-bot Telegram team."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass(frozen=True)
class TeamMessage:
    """A message observed by the team."""

    chat_id: str
    sender_id: str
    sender_name: str
    content: str
    message_id: int
    is_from_team_bot: bool = False  # True if sent by one of our bots
    source_role: str | None = None  # Which role's bot sent it (None = external user)
    metadata: dict[str, Any] = field(default_factory=dict)
    reply_to_message_id: int | None = None


class TeamBus:
    """Broadcasts messages to all subscribed role handlers.

    Each role subscribes and gets its own asyncio.Queue.
    When a message is broadcast, it is fanned out to ALL subscribers.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, asyncio.Queue[TeamMessage]] = {}

    def subscribe(self, role: str, maxsize: int = 100) -> asyncio.Queue[TeamMessage]:
        """Subscribe a role to the bus. Returns the queue to consume from."""
        if role in self._subscribers:
            return self._subscribers[role]
        q: asyncio.Queue[TeamMessage] = asyncio.Queue(maxsize=maxsize)
        self._subscribers[role] = q
        logger.debug("TeamBus: {} subscribed", role)
        return q

    async def broadcast(self, msg: TeamMessage) -> None:
        """Fan out a message to all subscribers."""
        for role, q in self._subscribers.items():
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                logger.warning("TeamBus: queue full for role {}, dropping message", role)

    def unsubscribe(self, role: str) -> None:
        """Remove a role subscription."""
        self._subscribers.pop(role, None)
        logger.debug("TeamBus: {} unsubscribed", role)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
