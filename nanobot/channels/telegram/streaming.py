"""Telegram streaming manager — sendMessageDraft (Bot API 9.5) + edit-in-place fallback.

sendMessageDraft allows bots to stream partial messages while content is being
generated (like ChatGPT). Available to all bots since Bot API 9.5 (March 2026).

Two modes:
- "draft": Native streaming via sendMessageDraft. Smooth animated text. Private chats only.
- "edit": Edit-in-place fallback. Works in groups too. Sends one message then edits it.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from telegram.ext import Application

    from nanobot.channels.telegram.retry import RetryHelper
    from nanobot.config.schema import TelegramConfig

# Minimum interval between streaming updates (seconds).
# Telegram rate-limits to ~1 msg/s per chat. Being conservative avoids 429s.
_MIN_UPDATE_INTERVAL_DRAFT = 0.15  # sendMessageDraft is lightweight
_MIN_UPDATE_INTERVAL_EDIT = 0.8  # editMessageText is heavier (creates history entries)

# Minimum content change (chars) before sending an update — skip tiny deltas
_MIN_CONTENT_DELTA = 20


class StreamingManager:
    """Manage streaming partial responses to a Telegram chat.

    Usage::

        # In channel.send() for progress messages:
        await streaming.update(chat_id, partial_text, thread_id=thread_id)

        # After final response is sent:
        await streaming.finalize(chat_id)
    """

    def __init__(
        self,
        app: Application,
        config: TelegramConfig,
        retry: RetryHelper,
    ) -> None:
        self._app = app
        self._config = config
        self._retry = retry

        # Per-chat state
        # chat_id → draft_id for sendMessageDraft (monotonic, non-zero)
        self._draft_ids: dict[int, int] = {}
        # chat_id → message_id for edit-in-place mode
        self._progress_messages: dict[int, int] = {}
        # chat_id → last update timestamp (throttling)
        self._last_update: dict[int, float] = {}
        # chat_id → last sent content length (skip tiny deltas)
        self._last_length: dict[int, int] = {}

    @property
    def enabled(self) -> bool:
        return self._config.streaming in ("draft", "edit")

    def _new_draft_id(self) -> int:
        """Generate a unique non-zero draft_id based on timestamp."""
        return int(time.time() * 1000) & 0x7FFFFFFF or 1

    async def update(self, chat_id: int, text: str, *, thread_id: int | None = None) -> None:
        """Stream a partial response to the chat. Throttled to avoid rate limits."""
        if not text.strip():
            return

        now = time.monotonic()
        mode = self._config.streaming
        min_interval = _MIN_UPDATE_INTERVAL_DRAFT if mode == "draft" else _MIN_UPDATE_INTERVAL_EDIT

        # Throttle: skip if too soon since last update
        last = self._last_update.get(chat_id, 0)
        if now - last < min_interval:
            return

        # Skip tiny content deltas (avoid flickering)
        prev_len = self._last_length.get(chat_id, 0)
        if len(text) - prev_len < _MIN_CONTENT_DELTA and prev_len > 0:
            return

        self._last_update[chat_id] = now
        self._last_length[chat_id] = len(text)

        if mode == "draft":
            await self._send_draft(chat_id, text, thread_id=thread_id)
        elif mode == "edit":
            await self._edit_in_place(chat_id, text, thread_id=thread_id)

    async def finalize(self, chat_id: int) -> None:
        """Clean up streaming state after final response is sent.

        For edit mode: delete the progress message (final message is sent separately).
        For draft mode: just clear state (Telegram handles the transition).
        """
        draft_id = self._draft_ids.pop(chat_id, None)
        msg_id = self._progress_messages.pop(chat_id, None)
        self._last_update.pop(chat_id, None)
        self._last_length.pop(chat_id, None)

        # Edit mode: delete progress message so final message stands alone
        if msg_id and self._config.streaming == "edit":
            try:
                await self._app.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass  # Already deleted or too old — fine

        # Draft mode: send empty draft to clear the streaming bubble
        if draft_id and self._config.streaming == "draft":
            try:
                await self._app.bot.send_message_draft(
                    chat_id=chat_id,
                    draft_id=draft_id,
                    text="",
                )
            except Exception:
                pass

    async def _send_draft(self, chat_id: int, text: str, *, thread_id: int | None = None) -> None:
        """Use sendMessageDraft for native streaming (Bot API 9.5).

        Same draft_id per chat session → Telegram animates the text updates.
        """
        # Reuse or create draft_id for this chat
        if chat_id not in self._draft_ids:
            self._draft_ids[chat_id] = self._new_draft_id()

        try:
            kwargs: dict = {
                "chat_id": chat_id,
                "draft_id": self._draft_ids[chat_id],
                "text": text,
            }
            if thread_id:
                kwargs["message_thread_id"] = thread_id
            await self._app.bot.send_message_draft(**kwargs)
        except Exception as e:
            logger.debug("sendMessageDraft failed: {} — falling back to edit", e)
            # Fallback to edit-in-place for this chat
            self._draft_ids.pop(chat_id, None)
            await self._edit_in_place(chat_id, text, thread_id=thread_id)

    async def _edit_in_place(
        self, chat_id: int, text: str, *, thread_id: int | None = None
    ) -> None:
        """Send initial message then edit it with updated content."""
        from nanobot.channels.telegram.formatting import markdown_to_telegram_html

        html = markdown_to_telegram_html(text)
        # Append "▍" cursor to indicate streaming in progress
        if not html.endswith("▍"):
            html += " ▍"

        msg_id = self._progress_messages.get(chat_id)

        if msg_id:
            try:
                await self._retry.call(
                    self._app.bot.edit_message_text,
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=html,
                    parse_mode="HTML",
                )
                return
            except Exception:
                # Message might be deleted or too old; send new one
                self._progress_messages.pop(chat_id, None)

        # Send new progress message
        try:
            kwargs: dict = {
                "chat_id": chat_id,
                "text": html,
                "parse_mode": "HTML",
            }
            if thread_id:
                kwargs["message_thread_id"] = thread_id
            sent = await self._retry.call(self._app.bot.send_message, **kwargs)
            self._progress_messages[chat_id] = sent.message_id
        except Exception as e:
            logger.debug("Streaming edit-in-place failed: {}", e)
