"""Telegram streaming manager — sendMessageDraft (Bot API 9.3) + edit-in-place fallback."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from telegram.ext import Application

    from nanobot.channels.telegram.retry import RetryHelper
    from nanobot.config.schema import TelegramConfig


class StreamingManager:
    """Manage streaming partial responses to a Telegram chat.

    Supports two modes:
    - ``"draft"``: Uses ``sendMessageDraft`` (Bot API 9.3 / PTB 22.6) for native
      Telegram streaming bubble. Best UX. Works in private chats.
    - ``"edit"``: Edit-in-place fallback. Sends initial message then edits it
      via ``edit_message_text`` as more content arrives. Works everywhere.
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
        # chat_id → message_id of the in-progress message (for "edit" mode)
        self._progress_messages: dict[int, int] = {}

    async def update(self, chat_id: int, text: str, *, thread_id: int | None = None) -> None:
        """Stream a partial response to the chat."""
        mode = self._config.streaming
        if mode == "draft":
            await self._send_draft(chat_id, text, thread_id=thread_id)
        elif mode == "edit":
            await self._edit_in_place(chat_id, text, thread_id=thread_id)

    async def cleanup(self, chat_id: int) -> None:
        """Clean up streaming state for a chat after final response."""
        self._progress_messages.pop(chat_id, None)

    async def _send_draft(self, chat_id: int, text: str, *, thread_id: int | None = None) -> None:
        """Use sendMessageDraft for native streaming (Bot API 9.3)."""
        try:
            kwargs: dict = {
                "chat_id": chat_id,
                "text": text,
            }
            if thread_id:
                kwargs["message_thread_id"] = thread_id
            await self._app.bot.send_message_draft(**kwargs)
        except Exception as e:
            logger.debug("sendMessageDraft failed (falling back to edit): {}", e)
            # Fallback to edit-in-place
            await self._edit_in_place(chat_id, text, thread_id=thread_id)

    async def _edit_in_place(
        self, chat_id: int, text: str, *, thread_id: int | None = None
    ) -> None:
        """Send initial message then edit it with updated content."""
        from nanobot.channels.telegram.formatting import markdown_to_telegram_html

        html = markdown_to_telegram_html(text)
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
