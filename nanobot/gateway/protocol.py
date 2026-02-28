"""Gateway JSON-RPC-over-WebSocket frame types and serialization."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Frame types
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RequestFrame:
    """Client → Server request."""
    id: str
    method: str
    params: dict[str, Any] = field(default_factory=dict)
    type: str = "req"


@dataclass(frozen=True, slots=True)
class ResponseFrame:
    """Server → Client response."""
    id: str
    ok: bool
    payload: Any = None
    error: dict[str, Any] | None = None
    type: str = "res"


@dataclass(frozen=True, slots=True)
class EventFrame:
    """Server → Client push event."""
    event: str
    payload: Any = None
    seq: int | None = None
    state_version: dict[str, int] | None = None
    type: str = "event"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class GatewayError(Exception):
    """Application-level gateway error sent back to client."""

    def __init__(self, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def serialize_frame(frame: ResponseFrame | EventFrame) -> str:
    """Serialize a frame to JSON string for the wire."""
    d: dict[str, Any] = {"type": frame.type}
    if isinstance(frame, ResponseFrame):
        d["id"] = frame.id
        d["ok"] = frame.ok
        if frame.ok:
            if frame.payload is not None:
                d["payload"] = frame.payload
        else:
            if frame.error is not None:
                d["error"] = frame.error
    elif isinstance(frame, EventFrame):
        d["event"] = frame.event
        if frame.payload is not None:
            d["payload"] = frame.payload
        if frame.seq is not None:
            d["seq"] = frame.seq
        if frame.state_version is not None:
            d["stateVersion"] = frame.state_version
    return json.dumps(d, separators=(",", ":"), default=str)


def parse_request(raw: str) -> RequestFrame | None:
    """Parse a raw JSON string into a RequestFrame, or None on bad input."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("type") != "req":
        return None
    req_id = data.get("id")
    method = data.get("method")
    if not isinstance(req_id, str) or not isinstance(method, str):
        return None
    params = data.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    return RequestFrame(id=req_id, method=method, params=params)
