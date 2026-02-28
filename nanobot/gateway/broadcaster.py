"""Event fan-out to all authenticated connections."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .connection import ClientConnection

logger = logging.getLogger(__name__)


class Broadcaster:
    """Manages the set of authenticated connections and broadcasts events."""

    def __init__(self) -> None:
        self._clients: set[ClientConnection] = set()
        self._seq: int = 0
        self._lock = asyncio.Lock()

    def add(self, conn: ClientConnection) -> None:
        self._clients.add(conn)

    def remove(self, conn: ClientConnection) -> None:
        self._clients.discard(conn)

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def clients(self) -> frozenset[ClientConnection]:
        return frozenset(self._clients)

    async def broadcast(self, event: str, payload: Any = None) -> None:
        """Send an event to every authenticated client with auto-incrementing seq."""
        async with self._lock:
            self._seq += 1
            seq = self._seq

            snapshot = list(self._clients)

        dead: list[ClientConnection] = []
        for conn in snapshot:
            if not conn.open:
                dead.append(conn)
                continue
            try:
                await conn.send_event(event, payload, seq=seq)
            except Exception:
                dead.append(conn)

        for conn in dead:
            self._clients.discard(conn)

    async def close_all(self, code: int = 1000, reason: str = "") -> None:
        """Close every connection (e.g. on config change / shutdown)."""
        for conn in list(self._clients):
            await conn.close(code, reason)
        self._clients.clear()
