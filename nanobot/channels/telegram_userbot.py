"""Telegram userbot channel using Telethon (MTProto API).

Observes messages from other bots in group chats — the Bot API can't see
bot-to-bot messages, so a real user account bridges this gap.

This channel is **read-only**: it never sends messages. The existing
TelegramChannel (Bot API) handles all outbound communication.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import TelegramUserbotConfig


class TelegramUserbotChannel(BaseChannel):
    """Telethon-based userbot that observes bot messages in group chats.

    Architecture:
    - Human messages in groups are already handled by TelegramChannel (bot).
    - This channel only captures messages where ``sender.bot is True``.
    - Messages are saved via ``_observe_message()`` — session history only,
      no agent trigger.
    - ``send()`` is a no-op.
    - Session key matches the bot channel: ``telegram:{chat_id}``.
    """

    name = "telegram"  # Same channel name → shared session history

    def __init__(self, config: TelegramUserbotConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: TelegramUserbotConfig = config
        self._client = None
        self._observe_set: set[str] = set(config.observe_groups)

    async def start(self) -> None:
        """Connect the Telethon client and start listening."""
        from telethon import TelegramClient, events

        if not self.config.api_id or not self.config.api_hash:
            logger.error("Telegram userbot: api_id and api_hash required")
            return

        session_path = Path(self.config.session_path).expanduser()
        session_path.parent.mkdir(parents=True, exist_ok=True)

        self._client = TelegramClient(
            str(session_path),
            self.config.api_id,
            self.config.api_hash,
        )

        # Connect — if no session file exists, this will fail.
        # Users must run `python -m nanobot.channels.telegram_userbot` first.
        await self._client.connect()

        if not await self._client.is_user_authorized():
            logger.error(
                "Telegram userbot: not authorized. "
                "Run `python -m nanobot.channels.telegram_userbot` to log in."
            )
            await self._client.disconnect()
            self._client = None
            return

        me = await self._client.get_me()
        logger.info("Telegram userbot connected as {} ({})", me.first_name, me.phone)
        self._running = True

        @self._client.on(events.NewMessage)
        async def _on_new_message(event: events.NewMessage.Event) -> None:
            await self._handle_event(event)

        # Run until stopped
        while self._running:
            await asyncio.sleep(1)

    async def _handle_event(self, event) -> None:
        """Process an incoming Telethon event."""
        msg = event.message
        if not msg or not msg.sender:
            return

        sender = msg.sender
        chat_id = str(msg.chat_id or msg.peer_id)

        # Only observe group/supergroup chats
        if not (hasattr(msg, "is_group") and msg.is_group) and not (
            hasattr(msg, "is_channel") and msg.is_channel
        ):
            return

        # Filter by observe_groups if configured
        if self._observe_set and chat_id not in self._observe_set:
            return

        # Only capture messages from bots — human messages are handled by TelegramChannel
        if not getattr(sender, "bot", False):
            return

        sender_name = getattr(sender, "first_name", None) or getattr(sender, "username", None) or "Bot"
        sender_id = str(sender.id)
        text = msg.text or msg.message or ""

        if not text.strip():
            return

        content = f"[{sender_name}]: {text}"
        logger.debug("Userbot observed bot message in {}: {}...", chat_id, content[:80])

        await self._observe_message(
            sender_id=sender_id,
            chat_id=chat_id,
            content=content,
            metadata={"source": "userbot", "bot_sender": True},
        )

    async def stop(self) -> None:
        """Disconnect the Telethon client."""
        self._running = False
        if self._client:
            await self._client.disconnect()
            self._client = None
        logger.info("Telegram userbot stopped")

    async def send(self, msg: OutboundMessage) -> None:
        """No-op — the main bot channel handles sending."""
        pass


# --- Interactive auth when run directly ---

async def _interactive_login() -> None:
    """One-time interactive login flow for the userbot session."""
    from telethon import TelegramClient

    # Load config
    from nanobot.config.loader import load_config
    config = load_config()
    ub = config.channels.telegram_userbot

    if not ub.api_id or not ub.api_hash:
        logger.error("telegram_userbot.api_id and api_hash must be set in config.json")
        sys.exit(1)

    session_path = Path(ub.session_path).expanduser()
    session_path.parent.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(str(session_path), ub.api_id, ub.api_hash)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        logger.info("Already authorized as {} ({})", me.first_name, me.phone)
        await client.disconnect()
        return

    phone = ub.phone or input("Enter phone number (with country code): ")
    await client.send_code_request(phone)
    code = input("Enter the code you received: ")

    try:
        await client.sign_in(phone, code)
    except Exception:
        # 2FA might be enabled
        password = input("Enter 2FA password: ")
        await client.sign_in(password=password)

    me = await client.get_me()
    logger.info("Logged in as {} ({})", me.first_name, me.phone)
    logger.info("Session saved to {}.session", session_path)
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(_interactive_login())
