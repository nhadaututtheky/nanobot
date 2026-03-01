"""Method routing — maps RPC method names to handler functions."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from .connection import ClientConnection
from .context import GatewayContext
from .protocol import GatewayError, RequestFrame

logger = logging.getLogger(__name__)

# Handler signature: (ctx, conn, params) -> Any
HandlerFn = Callable[[GatewayContext, ClientConnection, dict[str, Any]], Awaitable[Any]]


class Dispatcher:
    """Collects route dicts and dispatches incoming requests."""

    def __init__(self) -> None:
        self._routes: dict[str, HandlerFn] = {}

    def register(self, routes: dict[str, HandlerFn]) -> None:
        """Merge a handler module's ROUTES dict into the dispatcher."""
        for method, fn in routes.items():
            if method in self._routes:
                logger.warning("duplicate route %s — overwriting", method)
            self._routes[method] = fn

    @property
    def method_names(self) -> list[str]:
        return sorted(self._routes.keys())

    async def dispatch(
        self,
        ctx: GatewayContext,
        conn: ClientConnection,
        req: RequestFrame,
    ) -> None:
        """Route a request, call the handler, send back the response."""
        handler = self._routes.get(req.method)
        if handler is None:
            await conn.send_error(req.id, "METHOD_NOT_FOUND", f"unknown method: {req.method}")
            return

        try:
            result = await handler(ctx, conn, req.params)
            await conn.send_response(req.id, result)
        except GatewayError as exc:
            await conn.send_error(req.id, exc.code, str(exc), exc.details)
        except Exception:
            logger.exception("handler error for %s", req.method)
            await conn.send_error(req.id, "INTERNAL", "an internal error occurred")
