"""Optional webhook transport for Telegram bot (alternative to polling)."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

if TYPE_CHECKING:
    from telegram.ext import Application


class WebhookRunner:
    """Lightweight aiohttp HTTP server that receives Telegram webhook updates.

    Runs independently of the main WebSocket gateway — no refactor needed.
    Uses a secret token to verify requests come from Telegram.
    """

    def __init__(
        self,
        app: Application,
        url: str,
        port: int = 8443,
        path: str = "/telegram/webhook",
    ) -> None:
        self._app = app
        self._url = url.rstrip("/")
        self._port = port
        self._path = path
        self._runner: web.AppRunner | None = None
        self._secret_token: str = secrets.token_urlsafe(32)

    async def start(self) -> None:
        """Start the HTTP server and register webhook with Telegram."""
        aiohttp_app = web.Application()
        aiohttp_app.router.add_post(self._path, self._handle_update)

        self._runner = web.AppRunner(aiohttp_app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await site.start()

        webhook_url = f"{self._url}{self._path}"
        await self._app.bot.set_webhook(
            url=webhook_url,
            secret_token=self._secret_token,
        )
        logger.info("Telegram webhook registered: {} (port {})", webhook_url, self._port)

    async def _handle_update(self, request: web.Request) -> web.Response:
        """Receive a Telegram update via webhook and feed it to PTB."""
        # Verify the request comes from Telegram using the secret token
        token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if token != self._secret_token:
            return web.Response(status=403, text="forbidden")

        try:
            data = await request.json()
            from telegram import Update

            update = Update.de_json(data, self._app.bot)
            if update:
                await self._app.process_update(update)
            return web.Response(text="ok")
        except Exception as e:
            logger.error("Webhook handler error: {}", e)
            return web.Response(status=500, text="error")

    async def stop(self) -> None:
        """Delete webhook and stop the HTTP server."""
        try:
            await self._app.bot.delete_webhook()
        except Exception as e:
            logger.warning("Failed to delete webhook: {}", e)

        if self._runner:
            await self._runner.cleanup()
            self._runner = None
