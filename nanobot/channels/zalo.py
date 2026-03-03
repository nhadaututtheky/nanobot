"""Zalo Official Account channel — webhook receiver + OA API sender."""

from __future__ import annotations

import asyncio
import hmac as _hmac
import time
from typing import Any

import httpx
from loguru import logger

from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel

_ZALO_API_BASE = "https://openapi.zalo.me/v3.0/oa"
_ZALO_TOKEN_URL = "https://oauth.zaloapp.com/v4/oa/access_token"
_TOKEN_REFRESH_MARGIN_S = 600  # refresh 10 min before expiry (token lives 1 hr)


class ZaloChannel(BaseChannel):
    """Zalo OA channel via webhook (inbound) and REST API (outbound)."""

    name = "zalo"

    def __init__(self, config: Any, bus: MessageBus) -> None:
        super().__init__(config, bus)
        self._access_token: str = config.access_token
        self._refresh_token: str = config.refresh_token
        self._token_expires_at: float = 0.0
        self._http: httpx.AsyncClient | None = None
        self._webhook_runner: Any | None = None  # aiohttp AppRunner
        self._refresh_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start webhook server + token refresh loop."""
        self._running = True
        self._http = httpx.AsyncClient(timeout=30.0)

        # Initial token refresh if we have a refresh_token
        if self._refresh_token and not self._access_token:
            await self._refresh_access_token()

        # If we have an access_token but don't know expiry, assume it expires in 1 hr
        if self._access_token and not self._token_expires_at:
            self._token_expires_at = time.monotonic() + 3600 - _TOKEN_REFRESH_MARGIN_S

        # Start background token refresher
        self._refresh_task = asyncio.create_task(self._token_refresh_loop())

        # Start webhook server
        await self._start_webhook_server()

    async def stop(self) -> None:
        """Shutdown webhook server + HTTP client."""
        self._running = False

        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass

        if self._webhook_runner:
            await self._webhook_runner.cleanup()
            self._webhook_runner = None

        if self._http:
            await self._http.aclose()
            self._http = None

        logger.info("Zalo channel stopped")

    # ------------------------------------------------------------------
    # outbound — send messages via Zalo OA API
    # ------------------------------------------------------------------

    async def send(self, msg: Any) -> None:
        """Send a text message to a Zalo user via OA CS API."""
        if not self._http or not self._access_token:
            logger.warning("Zalo: cannot send — no access token")
            return

        payload = {
            "recipient": {"user_id": msg.chat_id},
            "message": {"text": msg.content},
        }

        try:
            resp = await self._http.post(
                f"{_ZALO_API_BASE}/message/cs",
                json=payload,
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
            data = resp.json()
            if data.get("error") not in (0, None):
                logger.warning("Zalo send error: {} — {}", data.get("error"), data.get("message"))
        except httpx.HTTPError as e:
            logger.error("Zalo send failed: {}", e)

    # ------------------------------------------------------------------
    # inbound — webhook receiver
    # ------------------------------------------------------------------

    async def _start_webhook_server(self) -> None:
        """Start an aiohttp server to receive Zalo webhook events."""
        try:
            from aiohttp import web
        except ImportError:
            logger.error("Zalo channel requires aiohttp: pip install aiohttp>=3.9.0")
            self._running = False
            return

        app = web.Application()
        app.router.add_post("/zalo/webhook", self._handle_webhook)

        runner = web.AppRunner(app)
        await runner.setup()
        self._webhook_runner = runner

        port = getattr(self.config, "webhook_port", 8444)
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info("Zalo webhook listening on port {}", port)

    async def _handle_webhook(self, request: Any) -> Any:
        """Process incoming Zalo webhook events."""
        from aiohttp import web

        # Verify webhook secret
        if not self._verify_webhook(request):
            return web.Response(status=403, text="Forbidden")

        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text="Bad Request")

        event_name = body.get("event_name", "")
        sender = body.get("sender", {})
        sender_id = sender.get("id", "")
        message = body.get("message", {})

        if event_name == "user_send_text":
            text = message.get("text", "")
            if text and sender_id:
                await self._handle_message(
                    sender_id=sender_id,
                    chat_id=sender_id,  # Zalo OA: DM only, chat_id == user_id
                    content=text,
                    metadata={"event": event_name, "zalo_msg_id": message.get("msg_id", "")},
                )

        elif event_name in ("user_send_image", "user_send_file", "user_send_sticker"):
            # Forward as text description with attachment URL
            url = message.get("url", "") or message.get("thumb", "")
            text = message.get("text", "") or f"[{event_name}]"
            content = f"{text}\n{url}" if url else text
            if sender_id:
                await self._handle_message(
                    sender_id=sender_id,
                    chat_id=sender_id,
                    content=content,
                    metadata={"event": event_name},
                )

        elif event_name in ("follow", "unfollow"):
            logger.info("Zalo {}: user {}", event_name, sender_id)

        # Zalo requires 200 response within 2 seconds
        return web.Response(status=200, text="OK")

    def _verify_webhook(self, request: Any) -> bool:
        """Verify webhook using X-Bot-Api-Secret-Token (timing-safe)."""
        secret = getattr(self.config, "webhook_secret", "")
        if not secret:
            return True  # no secret configured — accept all

        provided = request.headers.get("X-Bot-Api-Secret-Token", "")
        return _hmac.compare_digest(provided.encode(), secret.encode())

    # ------------------------------------------------------------------
    # token management
    # ------------------------------------------------------------------

    async def _token_refresh_loop(self) -> None:
        """Periodically refresh the Zalo OA access token."""
        while self._running:
            try:
                # Sleep until margin before expiry
                now = time.monotonic()
                sleep_s = max(60.0, self._token_expires_at - now)
                await asyncio.sleep(sleep_s)

                if self._refresh_token:
                    await self._refresh_access_token()
                else:
                    logger.warning("Zalo: no refresh_token — cannot auto-refresh")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Zalo token refresh failed: {}", e)
                await asyncio.sleep(60)

    async def _refresh_access_token(self) -> None:
        """Exchange refresh_token for a new access_token (single-use refresh)."""
        if not self._http:
            return

        try:
            resp = await self._http.post(
                _ZALO_TOKEN_URL,
                data={
                    "app_id": self.config.app_id,
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "secret_key": self.config.app_secret,
                },
            )
            data = resp.json()

            if "access_token" in data:
                self._access_token = data["access_token"]
                # Zalo refresh_token is single-use — store the new one
                if "refresh_token" in data:
                    self._refresh_token = data["refresh_token"]
                # Token expires in 1 hour; refresh 10 min early
                self._token_expires_at = time.monotonic() + 3600 - _TOKEN_REFRESH_MARGIN_S
                logger.info("Zalo access token refreshed (expires in ~50min)")
            else:
                err = data.get("error", "unknown")
                msg = data.get("error_description", data.get("message", ""))
                logger.error("Zalo token refresh error {}: {}", err, msg)
        except httpx.HTTPError as e:
            logger.error("Zalo token refresh HTTP error: {}", e)
