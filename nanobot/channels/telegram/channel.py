"""Telegram channel implementation using python-telegram-bot."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from loguru import logger
from telegram import BotCommand, ReplyParameters, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    MessageReactionHandler,
    filters,
)
from telegram.request import HTTPXRequest

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.channels.telegram.formatting import markdown_to_telegram_html, split_message
from nanobot.channels.telegram.retry import RetryHelper
from nanobot.channels.telegram.streaming import StreamingManager
from nanobot.config.schema import TelegramConfig, TelegramGroupConfig

_MAX_MEDIA_GROUP_BUFFERS = 100
_MEDIA_GROUP_TTL_S = 30.0


class TelegramChannel(BaseChannel):
    """Telegram channel using long polling or webhook.

    Features: retry with backoff, per-group config, DM policy, ACK reactions,
    forum/topic support, streaming (draft/edit), configurable allowed_updates.
    """

    name = "telegram"

    # Commands registered with Telegram's command menu
    BOT_COMMANDS = [
        BotCommand("start", "Start the bot"),
        BotCommand("new", "Start a new conversation"),
        BotCommand("stop", "Stop the current task"),
        BotCommand("help", "Show available commands"),
    ]

    def __init__(
        self,
        config: TelegramConfig,
        bus: MessageBus,
        groq_api_key: str = "",
    ):
        super().__init__(config, bus)
        self.config: TelegramConfig = config
        self.groq_api_key = groq_api_key
        self._app: Application | None = None
        self._bot_username: str = ""
        self._bot_id: int = 0
        self._chat_ids: dict[str, int] = {}
        self._typing_tasks: dict[str, asyncio.Task[None]] = {}
        self._media_group_buffers: dict[str, dict] = {}
        self._media_group_tasks: dict[str, asyncio.Task[None]] = {}
        self._retry = RetryHelper(config.retry)
        self._streaming: StreamingManager | None = None  # Created after app init
        self._webhook_runner: object | None = None  # WebhookRunner (lazy import)

    # --- group config resolution ---

    def _get_group_config(self, chat_id: str) -> TelegramGroupConfig:
        """Resolve per-group config: specific chat_id -> wildcard '*' -> defaults."""
        return (
            self.config.groups.get(chat_id)
            or self.config.groups.get("*")
            or TelegramGroupConfig()
        )

    def _is_addressed(self, message: Update.message.__class__) -> bool:  # type: ignore[name-defined]
        """Check if a group message is addressed to this bot.

        Returns True for:
        - Private chats (always addressed)
        - Groups with require_mention=False
        - Replies to the bot's own messages
        - @mention of the bot's username
        - Bot's name mentioned (first word match, case-insensitive)
        """
        if message.chat.type == "private":
            return True

        gcfg = self._get_group_config(str(message.chat_id))

        # Group explicitly disabled
        if not gcfg.enabled:
            return False

        # Group does not require mention — respond to all
        if not gcfg.require_mention:
            return True

        # Reply to bot's message
        if message.reply_to_message and message.reply_to_message.from_user:
            if message.reply_to_message.from_user.id == self._bot_id:
                return True

        text = (message.text or message.caption or "").lower()

        # @mention
        if self._bot_username and f"@{self._bot_username}" in text:
            return True

        # Name mention — check for common bot names
        bot_names = {"thor"}
        if self._bot_username:
            clean = self._bot_username.removesuffix("bot").removesuffix("_")
            if clean:
                bot_names.add(clean)
        for bname in bot_names:
            if bname in text.split():
                return True

        return False

    # --- lifecycle ---

    async def start(self) -> None:
        """Start the Telegram bot with long polling or webhook."""
        if not self.config.token:
            logger.error("Telegram bot token not configured")
            return

        self._running = True

        # Build application with connection pool
        req = HTTPXRequest(
            connection_pool_size=16,
            pool_timeout=5.0,
            connect_timeout=30.0,
            read_timeout=30.0,
        )
        builder = (
            Application.builder()
            .token(self.config.token)
            .request(req)
            .get_updates_request(req)
        )
        if self.config.proxy:
            builder = builder.proxy(self.config.proxy).get_updates_proxy(self.config.proxy)
        self._app = builder.build()
        self._app.add_error_handler(self._on_error)

        # Init streaming manager (sendMessageDraft / edit-in-place)
        self._streaming = StreamingManager(self._app, self.config, self._retry)
        if self._streaming.enabled:
            logger.info("Telegram streaming enabled (mode={})", self.config.streaming)

        # --- handlers ---
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("new", self._forward_command))
        self._app.add_handler(CommandHandler("help", self._on_help))

        # Text, photos, voice, documents
        self._app.add_handler(
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.VOICE | filters.AUDIO | filters.Document.ALL)
                & ~filters.COMMAND,
                self._on_message,
            )
        )

        # Edited messages
        self._app.add_handler(
            MessageHandler(filters.UpdateType.EDITED_MESSAGE, self._on_edited_message)
        )

        # Callback queries (inline buttons)
        self._app.add_handler(CallbackQueryHandler(self._on_callback_query))

        # Message reactions
        self._app.add_handler(MessageReactionHandler(self._on_reaction))

        logger.info("Starting Telegram bot ({} mode)...", self.config.mode)

        await self._app.initialize()
        await self._app.start()

        # Bot info + command menu
        bot_info = await self._app.bot.get_me()
        self._bot_username = (bot_info.username or "").lower()
        self._bot_id = bot_info.id
        logger.info("Telegram bot @{} connected", bot_info.username)

        try:
            await self._app.bot.set_my_commands(self.BOT_COMMANDS)
        except Exception as e:
            logger.warning("Failed to register bot commands: {}", e)

        # Start transport
        if self.config.mode == "webhook" and self.config.webhook_url:
            from nanobot.channels.telegram.webhook import WebhookRunner

            self._webhook_runner = WebhookRunner(
                app=self._app,
                url=self.config.webhook_url,
                port=self.config.webhook_port,
                path=self.config.webhook_path,
            )
            await self._webhook_runner.start()  # type: ignore[union-attr]
        else:
            assert self._app.updater is not None
            await self._app.updater.start_polling(
                allowed_updates=self.config.allowed_updates,
                drop_pending_updates=True,
            )

        # Keep running until stopped
        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        self._running = False

        # Cancel typing indicators
        for chat_id in list(self._typing_tasks):
            self._stop_typing(chat_id)

        for task in self._media_group_tasks.values():
            task.cancel()
        self._media_group_tasks.clear()
        self._media_group_buffers.clear()

        if self._webhook_runner is not None:
            await self._webhook_runner.stop()  # type: ignore[attr-defined]
            self._webhook_runner = None

        if self._app:
            logger.info("Stopping Telegram bot...")
            if self._app.updater and self._app.updater.running:
                await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._app = None

    # --- media helpers ---

    @staticmethod
    def _get_media_type(path: str) -> str:
        """Guess media type from file extension."""
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext in ("jpg", "jpeg", "png", "gif", "webp"):
            return "photo"
        if ext == "ogg":
            return "voice"
        if ext in ("mp3", "m4a", "wav", "aac"):
            return "audio"
        return "document"

    @staticmethod
    def _get_extension(media_type: str, mime_type: str | None) -> str:
        """Get file extension based on media type."""
        if mime_type:
            ext_map = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/gif": ".gif",
                "audio/ogg": ".ogg",
                "audio/mpeg": ".mp3",
                "audio/mp4": ".m4a",
            }
            if mime_type in ext_map:
                return ext_map[mime_type]
        type_map = {"image": ".jpg", "voice": ".ogg", "audio": ".mp3", "file": ""}
        return type_map.get(media_type, "")

    # --- outbound ---

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through Telegram."""
        # Progress messages → stream via sendMessageDraft or edit-in-place
        if msg.metadata and msg.metadata.get("_progress"):
            if self._streaming and self._streaming.enabled and msg.content:
                # Skip tool hints — only stream actual content
                if not msg.metadata.get("_tool_hint"):
                    try:
                        chat_id = int(msg.chat_id)
                        thread_id = msg.metadata.get("message_thread_id")
                        await self._streaming.update(chat_id, msg.content, thread_id=thread_id)
                    except (ValueError, Exception) as e:
                        logger.debug("Streaming update failed: {}", e)
            return

        if not self._app:
            logger.warning("Telegram bot not running")
            return

        if not self.config.actions.send_message:
            logger.debug("Telegram send_message action disabled, skipping")
            return

        self._stop_typing(msg.chat_id)

        try:
            chat_id = int(msg.chat_id)
        except ValueError:
            logger.error("Invalid chat_id: {}", msg.chat_id)
            return

        # Finalize streaming (delete progress message / clear draft bubble)
        if self._streaming and self._streaming.enabled:
            await self._streaming.finalize(chat_id)

        reply_params = None
        if self.config.reply_to_message:
            reply_to_message_id = msg.metadata.get("message_id")
            if reply_to_message_id:
                reply_params = ReplyParameters(
                    message_id=reply_to_message_id,
                    allow_sending_without_reply=True,
                )

        # Forum topic: route to correct thread
        thread_id = msg.metadata.get("message_thread_id")

        # Send media files
        for media_path in msg.media or []:
            try:
                media_type = self._get_media_type(media_path)
                sender = {
                    "photo": self._app.bot.send_photo,
                    "voice": self._app.bot.send_voice,
                    "audio": self._app.bot.send_audio,
                }.get(media_type, self._app.bot.send_document)
                param = (
                    "photo"
                    if media_type == "photo"
                    else media_type if media_type in ("voice", "audio") else "document"
                )
                with open(media_path, "rb") as f:
                    send_kwargs: dict = {
                        "chat_id": chat_id,
                        param: f,
                        "reply_parameters": reply_params,
                    }
                    if thread_id:
                        send_kwargs["message_thread_id"] = thread_id
                    await self._retry.call(sender, **send_kwargs)
            except Exception as e:
                filename = media_path.rsplit("/", 1)[-1]
                logger.error("Failed to send media {}: {}", media_path, e)
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=f"[Failed to send: {filename}]",
                    reply_parameters=reply_params,
                )

        # Send text content
        if msg.content and msg.content != "[empty message]":
            chunks = split_message(msg.content, mode=self.config.chunk_mode)
            for i, chunk in enumerate(chunks):
                # Prepend response_prefix to first chunk only
                if i == 0 and self.config.response_prefix:
                    chunk = self.config.response_prefix + chunk
                try:
                    html = markdown_to_telegram_html(chunk)
                    send_kwargs = {
                        "chat_id": chat_id,
                        "text": html,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": not self.config.link_preview,
                        "reply_parameters": reply_params,
                    }
                    if thread_id:
                        send_kwargs["message_thread_id"] = thread_id
                    await self._retry.call(self._app.bot.send_message, **send_kwargs)
                except Exception:
                    # Fallback to plain text on HTML parse failure
                    try:
                        fallback_kwargs: dict = {
                            "chat_id": chat_id,
                            "text": chunk,
                            "reply_parameters": reply_params,
                        }
                        if thread_id:
                            fallback_kwargs["message_thread_id"] = thread_id
                        await self._app.bot.send_message(**fallback_kwargs)
                    except Exception as e2:
                        logger.error("Error sending Telegram message: {}", e2)

    # --- ACK reaction ---

    async def _send_ack_reaction(self, chat_id: int, message_id: int) -> None:
        """Send acknowledgment emoji reaction to a message."""
        if not self.config.ack_reaction or not self.config.actions.set_reaction:
            return
        if not self._app:
            return
        try:
            from telegram import ReactionTypeEmoji

            await self._app.bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=[ReactionTypeEmoji(emoji=self.config.ack_reaction)],
            )
        except Exception as e:
            logger.debug("Failed to set ack reaction: {}", e)

    # --- command handlers ---

    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not update.message or not update.effective_user:
            return
        user = update.effective_user
        await update.message.reply_text(
            f"\U0001f44b Hi {user.first_name}! I'm nanobot.\n\n"
            "Send me a message and I'll respond!\n"
            "Type /help to see available commands."
        )

    async def _on_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        if not update.message:
            return
        await update.message.reply_text(
            "\U0001f408 nanobot commands:\n"
            "/new \u2014 Start a new conversation\n"
            "/stop \u2014 Stop the current task\n"
            "/help \u2014 Show available commands"
        )

    @staticmethod
    def _sender_id(user: object) -> str:
        """Build sender_id with username for allowlist matching."""
        sid = str(getattr(user, "id", ""))
        username = getattr(user, "username", None)
        return f"{sid}|{username}" if username else sid

    async def _forward_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Forward slash commands to the bus for unified handling."""
        if not update.message or not update.effective_user:
            return
        await self._handle_message(
            sender_id=self._sender_id(update.effective_user),
            chat_id=str(update.message.chat_id),
            content=update.message.text or "",
        )

    # --- inbound message handling ---

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming messages (text, photos, voice, documents)."""
        if not update.message or not update.effective_user:
            return

        message = update.message
        user = update.effective_user
        chat_id = message.chat_id
        sender_id = self._sender_id(user)
        is_group = message.chat.type != "private"
        str_chat_id = str(chat_id)

        # --- DM policy check ---
        if not is_group:
            dm_mode = self.config.dm.mode
            if dm_mode == "disabled":
                return
            if dm_mode == "allowlist":
                if str(user.id) not in self.config.dm.allow_from and sender_id not in self.config.dm.allow_from:
                    return

        # --- Per-group allowlist check ---
        if is_group:
            gcfg = self._get_group_config(str_chat_id)
            if gcfg.allow_from:
                uid = str(user.id)
                if uid not in gcfg.allow_from and sender_id not in gcfg.allow_from:
                    return

        # Store chat_id for replies
        self._chat_ids[sender_id] = chat_id

        # Build content from text and/or media
        content_parts: list[str] = []
        media_paths: list[str] = []

        if message.text:
            content_parts.append(message.text)
        if message.caption:
            content_parts.append(message.caption)

        # Handle media files
        media_file: Any = None
        media_type: str | None = None

        if message.photo:
            media_file = message.photo[-1]
            media_type = "image"
        elif message.voice:
            media_file = message.voice
            media_type = "voice"
        elif message.audio:
            media_file = message.audio
            media_type = "audio"
        elif message.document:
            media_file = message.document
            media_type = "file"

        # Download media if present
        if media_file and self._app:
            try:
                file = await self._app.bot.get_file(media_file.file_id)
                ext = self._get_extension(media_type or "", getattr(media_file, "mime_type", None))

                from pathlib import Path

                media_dir = Path.home() / ".nanobot" / "media"
                media_dir.mkdir(parents=True, exist_ok=True)

                file_path = media_dir / f"{media_file.file_id[:16]}{ext}"
                await file.download_to_drive(str(file_path))
                media_paths.append(str(file_path))

                # Voice/audio transcription
                if media_type in ("voice", "audio"):
                    from nanobot.providers.transcription import GroqTranscriptionProvider

                    transcriber = GroqTranscriptionProvider(api_key=self.groq_api_key)
                    transcription = await transcriber.transcribe(file_path)
                    if transcription:
                        logger.info("Transcribed {}: {}...", media_type, transcription[:50])
                        content_parts.append(f"[transcription: {transcription}]")
                    else:
                        content_parts.append(f"[{media_type}: {file_path}]")
                else:
                    content_parts.append(f"[{media_type}: {file_path}]")

                logger.debug("Downloaded {} to {}", media_type, file_path)
            except Exception as e:
                logger.error("Failed to download media: {}", e)
                content_parts.append(f"[{media_type}: download failed]")

        # Include reply context
        if message.reply_to_message:
            reply = message.reply_to_message
            reply_sender = reply.from_user
            reply_name = (
                (reply_sender.first_name or reply_sender.username or "someone")
                if reply_sender
                else "someone"
            )
            reply_text = reply.text or reply.caption or ""
            if reply_text:
                if len(reply_text) > 200:
                    reply_text = reply_text[:200] + "..."
                content_parts.insert(0, f'[replying to {reply_name}: "{reply_text}"]')

        content = "\n".join(content_parts) if content_parts else "[empty message]"

        # Prefix sender name in group chats
        if is_group:
            sender_name = user.first_name or user.username or "Unknown"
            content = f"[{sender_name}]: {content}"

        # --- Per-group ignore filters ---
        if is_group:
            gcfg = self._get_group_config(str_chat_id)
            if gcfg.ignore_senders:
                name_lower = (user.first_name or "").lower()
                uname_lower = (user.username or "").lower()
                prefixes = [s.lower() for s in gcfg.ignore_senders]
                if any(name_lower.startswith(p) or uname_lower.startswith(p) for p in prefixes):
                    return
            if gcfg.ignore_patterns:
                ignore_re = [re.compile(p, re.IGNORECASE) for p in gcfg.ignore_patterns]
                if any(r.search(content) for r in ignore_re):
                    return

        logger.debug("Telegram message from {}: {}...", sender_id, content[:50])

        addressed = self._is_addressed(message)

        # Build metadata
        metadata: dict = {
            "message_id": message.message_id,
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "is_group": is_group,
        }
        if message.reply_to_message:
            metadata["reply_to_message_id"] = message.reply_to_message.message_id

        # Forum/topic support
        thread_id = getattr(message, "message_thread_id", None)
        if thread_id:
            metadata["message_thread_id"] = thread_id

        # Per-group overrides
        if is_group:
            gcfg = self._get_group_config(str_chat_id)
            if gcfg.system_prompt:
                metadata["system_prompt_override"] = gcfg.system_prompt
            metadata["history_limit"] = gcfg.history_limit or self.config.history_limit
            if gcfg.allowed_tools or gcfg.denied_tools:
                metadata["tool_restrictions"] = {
                    "allowed": gcfg.allowed_tools,
                    "denied": gcfg.denied_tools,
                }
        else:
            metadata["history_limit"] = self.config.dm.history_limit or self.config.history_limit

        # Session key with topic isolation (like Slack thread_ts)
        session_key = f"telegram:{chat_id}:{thread_id}" if thread_id else None

        # Media group buffering
        if media_group_id := getattr(message, "media_group_id", None):
            key = f"{str_chat_id}:{media_group_id}"
            if key not in self._media_group_buffers:
                # Evict oldest buffers if over cap
                if len(self._media_group_buffers) >= _MAX_MEDIA_GROUP_BUFFERS:
                    self._flush_stale_media_groups()
                self._media_group_buffers[key] = {
                    "sender_id": sender_id,
                    "chat_id": str_chat_id,
                    "contents": [],
                    "media": [],
                    "addressed": addressed,
                    "metadata": metadata,
                    "session_key": session_key,
                    "_created_at": asyncio.get_event_loop().time(),
                }
                if addressed:
                    self._start_typing(str_chat_id)
                    await self._send_ack_reaction(chat_id, message.message_id)
            buf = self._media_group_buffers[key]
            if addressed:
                buf["addressed"] = True
            if content and content != "[empty message]":
                buf["contents"].append(content)
            buf["media"].extend(media_paths)
            if key not in self._media_group_tasks:
                self._media_group_tasks[key] = asyncio.create_task(self._flush_media_group(key))
            return

        # Group messages not addressed to bot: observe only
        if is_group and not addressed:
            await self._observe_message(
                sender_id=sender_id,
                chat_id=str_chat_id,
                content=content,
                metadata=metadata,
            )
            return

        # Addressed message — ACK + typing + process
        await self._send_ack_reaction(chat_id, message.message_id)
        self._start_typing(str_chat_id)
        await self._handle_message(
            sender_id=sender_id,
            chat_id=str_chat_id,
            content=content,
            media=media_paths,
            metadata=metadata,
            session_key=session_key,
        )

    # --- edited message handler ---

    async def _on_edited_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle edited messages — forward with edited flag."""
        message = update.edited_message
        if not message or not update.effective_user:
            return

        user = update.effective_user
        sender_id = self._sender_id(user)
        content = message.text or message.caption or ""
        if not content:
            return

        metadata: dict = {
            "message_id": message.message_id,
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "is_group": message.chat.type != "private",
            "edited": True,
        }

        thread_id = getattr(message, "message_thread_id", None)
        if thread_id:
            metadata["message_thread_id"] = thread_id

        await self._handle_message(
            sender_id=sender_id,
            chat_id=str(message.chat_id),
            content=f"[edited] {content}",
            metadata=metadata,
        )

    # --- callback query handler ---

    async def _on_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline button callback queries."""
        query = update.callback_query
        if not query or not query.from_user:
            return

        # Acknowledge the callback
        await query.answer()

        sender_id = self._sender_id(query.from_user)
        chat_id = str(query.message.chat.id) if query.message else ""
        if not chat_id:
            return

        metadata: dict = {
            "user_id": query.from_user.id,
            "username": query.from_user.username,
            "first_name": query.from_user.first_name,
            "callback_data": query.data,
            "callback_query_id": query.id,
            "is_group": False,
        }

        await self._handle_message(
            sender_id=sender_id,
            chat_id=chat_id,
            content=f"[button: {query.data}]",
            metadata=metadata,
        )

    # --- reaction handler ---

    async def _on_reaction(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle message reactions — log for now, extensible."""
        # Reactions are informational; agent loop can decide to act on them.
        reaction = update.message_reaction
        if not reaction:
            return
        logger.debug(
            "Reaction on message {} in chat {}: {}",
            reaction.message_id,
            reaction.chat.id,
            reaction.new_reaction,
        )

    # --- media group flushing ---

    async def _flush_media_group(self, key: str) -> None:
        """Wait briefly, then forward buffered media-group as one turn."""
        try:
            await asyncio.sleep(0.6)
            if not (buf := self._media_group_buffers.pop(key, None)):
                return
            content = "\n".join(buf["contents"]) or "[empty message]"
            if not buf.get("addressed") and buf.get("metadata", {}).get("is_group"):
                await self._observe_message(
                    sender_id=buf["sender_id"],
                    chat_id=buf["chat_id"],
                    content=content,
                    metadata=buf["metadata"],
                )
                return
            await self._handle_message(
                sender_id=buf["sender_id"],
                chat_id=buf["chat_id"],
                content=content,
                media=list(dict.fromkeys(buf["media"])),
                metadata=buf["metadata"],
                session_key=buf.get("session_key"),
            )
        finally:
            self._media_group_tasks.pop(key, None)

    def _flush_stale_media_groups(self) -> None:
        """Remove media group buffers older than TTL to prevent unbounded growth."""
        now = asyncio.get_event_loop().time()
        stale = [
            k for k, v in self._media_group_buffers.items()
            if now - v.get("_created_at", 0) > _MEDIA_GROUP_TTL_S
        ]
        for k in stale:
            self._media_group_buffers.pop(k, None)
            task = self._media_group_tasks.pop(k, None)
            if task and not task.done():
                task.cancel()
        if stale:
            logger.debug("Flushed {} stale media group buffers", len(stale))

    # --- typing indicators ---

    def _start_typing(self, chat_id: str) -> None:
        """Start sending 'typing...' indicator for a chat."""
        self._stop_typing(chat_id)
        self._typing_tasks[chat_id] = asyncio.create_task(self._typing_loop(chat_id))

    def _stop_typing(self, chat_id: str) -> None:
        """Stop the typing indicator for a chat."""
        task = self._typing_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()

    async def _typing_loop(self, chat_id: str) -> None:
        """Repeatedly send 'typing' action until cancelled."""
        try:
            while self._app:
                await self._app.bot.send_chat_action(chat_id=int(chat_id), action="typing")
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("Typing indicator stopped for {}: {}", chat_id, e)

    # --- error handler ---

    async def _on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log polling / handler errors."""
        logger.error("Telegram error: {}", context.error)
