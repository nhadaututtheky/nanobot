"""Per-connection state wrapper around a websockets server connection."""

from __future__ import annotations

import logging
from typing import Any

from websockets.asyncio.server import ServerConnection

from .protocol import EventFrame, ResponseFrame, serialize_frame

logger = logging.getLogger(__name__)


class ClientConnection:
    """Wraps a single WebSocket peer with auth state and send helpers."""

    __slots__ = ("ws", "conn_id", "authenticated", "role", "scopes", "device_id", "client_info")

    def __init__(self, ws: ServerConnection, conn_id: str) -> None:
        self.ws = ws
        self.conn_id = conn_id
        self.authenticated: bool = False
        self.role: str = ""
        self.scopes: list[str] = []
        self.device_id: str = ""
        self.client_info: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Send helpers
    # ------------------------------------------------------------------

    async def send_response(self, req_id: str, payload: Any = None) -> None:
        """Send a success response."""
        frame = ResponseFrame(id=req_id, ok=True, payload=payload)
        await self._send(serialize_frame(frame))

    async def send_error(self, req_id: str, code: str, message: str, details: Any = None) -> None:
        """Send an error response."""
        error = {"code": code, "message": message}
        if details is not None:
            error["details"] = details
        frame = ResponseFrame(id=req_id, ok=False, error=error)
        await self._send(serialize_frame(frame))

    async def send_event(self, event: str, payload: Any = None, seq: int | None = None) -> None:
        """Send a push event."""
        frame = EventFrame(event=event, payload=payload, seq=seq)
        await self._send(serialize_frame(frame))

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Gracefully close the connection."""
        try:
            await self.ws.close(code, reason)
        except Exception:
            pass

    @property
    def open(self) -> bool:
        return self.ws.state.name == "OPEN"

    async def _send(self, data: str) -> None:
        try:
            await self.ws.send(data)
        except Exception:
            logger.debug("send failed for conn %s", self.conn_id)
