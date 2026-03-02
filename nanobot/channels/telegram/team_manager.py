"""Telegram team manager — multi-bot lifecycle and coordination."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from loguru import logger
from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, filters

from nanobot.channels.telegram.formatting import markdown_to_telegram_html, split_message
from nanobot.channels.telegram.relevance import RelevanceGate
from nanobot.channels.telegram.team_bus import TeamBus, TeamMessage

if TYPE_CHECKING:
    from nanobot.channels.telegram.team_agent import TeamRoleAgent
    from nanobot.config.schema import (
        Config,
        SubAgentRoleConfig,
        TelegramTeamGroupConfig,
    )
    from nanobot.providers.base import LLMProvider


class ResponseTracker:
    """Prevents duplicate and overlapping responses to the same message."""

    def __init__(self) -> None:
        self._claims: dict[int, set[str]] = {}  # message_id -> roles that claimed
        self._cooldowns: dict[str, float] = {}  # role -> monotonic time of last response
        self._lock = asyncio.Lock()

    async def try_claim(self, message_id: int, role: str, max_concurrent: int) -> bool:
        """Atomically claim a message for a role. Returns False if max reached."""
        async with self._lock:
            claimed = self._claims.setdefault(message_id, set())
            if role in claimed:
                return False
            if len(claimed) >= max_concurrent:
                return False
            claimed.add(role)
            return True

    def is_on_cooldown(self, role: str, cooldown_s: float) -> bool:
        """Check if role responded too recently."""
        last = self._cooldowns.get(role, 0.0)
        return (time.monotonic() - last) < cooldown_s

    def record_response(self, role: str) -> None:
        """Update cooldown tracker after a response."""
        self._cooldowns[role] = time.monotonic()

    def cleanup(self, max_tracked: int = 500) -> None:
        """Remove old entries to prevent memory leak."""
        if len(self._claims) > max_tracked:
            # Keep only the most recent half
            sorted_ids = sorted(self._claims.keys())
            for mid in sorted_ids[: len(sorted_ids) // 2]:
                del self._claims[mid]


class TelegramTeamBot:
    """A single bot in the team. Wraps a python-telegram-bot Application."""

    def __init__(
        self,
        role: str,
        role_config: SubAgentRoleConfig,
        token: str,
        team_bus: TeamBus,
        is_coordinator: bool = False,
    ) -> None:
        self.role = role
        self.role_config = role_config
        self.token = token
        self.team_bus = team_bus
        self.is_coordinator = is_coordinator
        self.bot_username: str = ""
        self.bot_id: int = 0
        self._app: Application | None = None

    async def start(self) -> None:
        """Build Application, register handlers, start polling."""
        self._app = (
            Application.builder()
            .token(self.token)
            .build()
        )

        # Only coordinator listens for external messages to broadcast
        if self.is_coordinator:
            self._app.add_handler(
                MessageHandler(filters.ALL & ~filters.COMMAND, self._on_message)
            )

        await self._app.initialize()
        bot_info = await self._app.bot.get_me()
        self.bot_username = (bot_info.username or "").lower()
        self.bot_id = bot_info.id
        logger.info(
            "TeamBot[{}] @{} started (coordinator={})",
            self.role, self.bot_username, self.is_coordinator,
        )

        await self._app.updater.start_polling(
            allowed_updates=["message"],
            drop_pending_updates=True,
        )
        await self._app.start()

    async def stop(self) -> None:
        """Stop polling and shutdown."""
        if self._app:
            try:
                if self._app.updater and self._app.updater.running:
                    await self._app.updater.stop()
                if self._app.running:
                    await self._app.stop()
                await self._app.shutdown()
            except Exception as e:
                logger.warning("TeamBot[{}] stop error: {}", self.role, e)
        logger.info("TeamBot[{}] stopped", self.role)

    async def _on_message(self, update: Update, context: Any) -> None:
        """Coordinator handler: broadcast external messages to TeamBus."""
        message = update.effective_message
        if not message or not message.chat:
            return

        # Skip messages from any team bot
        if message.from_user and message.from_user.is_bot:
            return

        text = message.text or message.caption or ""
        if not text.strip():
            return

        sender = message.from_user
        sender_name = (sender.first_name or sender.username or "Unknown") if sender else "Unknown"
        sender_id = str(sender.id) if sender else "0"

        team_msg = TeamMessage(
            chat_id=str(message.chat_id),
            sender_id=sender_id,
            sender_name=sender_name,
            content=f"[{sender_name}]: {text}",
            message_id=message.message_id,
            is_from_team_bot=False,
            source_role=None,
            metadata={
                "message_id": message.message_id,
                "user_id": int(sender_id) if sender_id.isdigit() else 0,
                "username": sender.username if sender else None,
                "first_name": sender.first_name if sender else None,
            },
        )
        await self.team_bus.broadcast(team_msg)

    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_to: int | None = None,
    ) -> int | None:
        """Send a message as this bot. Returns message_id."""
        if not self._app:
            return None

        try:
            html_text = markdown_to_telegram_html(text)
            chunks = split_message(html_text, mode="newline")

            last_msg_id = None
            for chunk in chunks:
                sent = await self._app.bot.send_message(
                    chat_id=int(chat_id),
                    text=chunk,
                    parse_mode="HTML",
                    reply_to_message_id=reply_to if reply_to and last_msg_id is None else None,
                )
                last_msg_id = sent.message_id

            # Broadcast our own message to TeamBus so other roles see it
            if last_msg_id:
                await self.team_bus.broadcast(TeamMessage(
                    chat_id=chat_id,
                    sender_id=str(self.bot_id),
                    sender_name=self.role_config.display_name or self.role,
                    content=f"[{self.role_config.display_name or self.role}]: {text}",
                    message_id=last_msg_id,
                    is_from_team_bot=True,
                    source_role=self.role,
                ))

            return last_msg_id
        except Exception as e:
            logger.error("TeamBot[{}] send_message failed: {}", self.role, e)
            return None

    @property
    def display_name(self) -> str:
        return self.role_config.display_name or self.role


class TelegramTeamManager:
    """Manages the full team lifecycle for one team group."""

    def __init__(
        self,
        group_config: TelegramTeamGroupConfig,
        config: Config,
        provider: LLMProvider,
    ) -> None:
        self._group_config = group_config
        self._config = config
        self._provider = provider
        self.team_bus = TeamBus()
        self.bots: dict[str, TelegramTeamBot] = {}
        self.agents: dict[str, TeamRoleAgent] = {}
        self._response_tracker = ResponseTracker()
        self._relevance_gate = RelevanceGate(provider, group_config)
        self._process_task: asyncio.Task | None = None

        self._init_bots()

    def _init_bots(self) -> None:
        """Create team bots from SubAgentRoleConfig entries with tokens."""
        effective_roles = self._config.agents.subagent.get_effective_roles()
        target_roles = self._group_config.roles or list(effective_roles.keys())
        coordinator = self._group_config.coordinator_role

        for role_name in target_roles:
            role_cfg = effective_roles.get(role_name)
            if not role_cfg:
                logger.warning("Team: role '{}' not found in config, skipping", role_name)
                continue

            token = role_cfg.telegram_bot_token
            if not token:
                logger.warning("Team: role '{}' has no telegram_bot_token, skipping", role_name)
                continue

            is_coord = role_name == coordinator
            bot = TelegramTeamBot(
                role=role_name,
                role_config=role_cfg,
                token=token,
                team_bus=self.team_bus,
                is_coordinator=is_coord,
            )
            self.bots[role_name] = bot
            self.team_bus.subscribe(role_name)

        if not self.bots:
            logger.warning("Team: no bots configured for group {}", self._group_config.chat_id)

    def set_agents(self, agents: dict[str, TeamRoleAgent]) -> None:
        """Set per-role agents after initialization (avoids circular deps)."""
        self.agents = agents

    async def start(self) -> None:
        """Start all bots + the message processing loop."""
        if not self.bots:
            return

        # Start all bot polling loops
        for role, bot in self.bots.items():
            try:
                await bot.start()
            except Exception as e:
                logger.error("Team: failed to start bot '{}': {}", role, e)

        # Start the processing loop
        self._process_task = asyncio.create_task(self._process_loop())
        logger.info(
            "TelegramTeam started: {} bots for group {}",
            len(self.bots), self._group_config.chat_id,
        )

    async def stop(self) -> None:
        """Stop all bots and processing loop."""
        if self._process_task:
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass

        for role, bot in self.bots.items():
            await bot.stop()

        logger.info("TelegramTeam stopped")

    async def _process_loop(self) -> None:
        """Main loop: consume from coordinator's TeamBus queue, run relevance + dispatch."""
        coordinator = self._group_config.coordinator_role
        coord_queue = self.team_bus.subscribe(coordinator)

        while True:
            try:
                msg = await coord_queue.get()

                # Skip messages from team bots (already observed by all)
                if msg.is_from_team_bot:
                    # Just observe for context in all role agents
                    for role, agent in self.agents.items():
                        await agent.observe(msg)
                    continue

                # Filter: only process messages for our configured chat_id
                if msg.chat_id != self._group_config.chat_id:
                    continue

                # Observe the message in all role agents for context
                for role, agent in self.agents.items():
                    await agent.observe(msg)

                # Run relevance checks + dispatch responses
                asyncio.create_task(self._dispatch_to_roles(msg))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Team process_loop error: {}", e)

    async def _dispatch_to_roles(self, msg: TeamMessage) -> None:
        """Run relevance checks for all roles and dispatch responses."""
        coordinator = self._group_config.coordinator_role
        already_claimed: set[str] = set()

        # Determine which roles are directly mentioned
        text_lower = msg.content.lower()
        directly_mentioned: set[str] = set()
        for role, bot in self.bots.items():
            # Check @username mention
            if bot.bot_username and f"@{bot.bot_username}" in text_lower:
                directly_mentioned.add(role)
            # Check role name mention
            name_lower = (bot.role_config.display_name or role).lower()
            if name_lower in text_lower.split():
                directly_mentioned.add(role)

        # If nobody specifically mentioned, coordinator is always eligible
        if not directly_mentioned:
            directly_mentioned.add(coordinator)

        # Phase 1: directly mentioned roles respond immediately (no relevance check)
        for role in directly_mentioned:
            if role not in self.agents or role not in self.bots:
                continue

            claimed = await self._response_tracker.try_claim(
                msg.message_id, role, self._group_config.max_concurrent_responses,
            )
            if not claimed:
                continue

            already_claimed.add(role)
            asyncio.create_task(self._generate_and_send(role, msg))

        # Phase 2: other roles check relevance
        other_roles = [r for r in self.bots if r not in directly_mentioned and r in self.agents]

        relevance_tasks = []
        for role in other_roles:
            # Skip if on cooldown
            if self._response_tracker.is_on_cooldown(role, self._group_config.cooldown_s):
                continue
            relevance_tasks.append((role, self._relevance_gate.check(
                role=role,
                role_config=self.bots[role].role_config,
                message=msg,
                already_claimed=already_claimed,
            )))

        for role, coro in relevance_tasks:
            try:
                result = await coro
                if result.should_respond:
                    claimed = await self._response_tracker.try_claim(
                        msg.message_id, role, self._group_config.max_concurrent_responses,
                    )
                    if claimed:
                        already_claimed.add(role)
                        logger.info(
                            "Team: {} decided to respond (confidence={:.2f}, reason={})",
                            role, result.confidence, result.reason,
                        )
                        asyncio.create_task(self._generate_and_send(role, msg))
            except Exception as e:
                logger.error("Team: relevance check failed for {}: {}", role, e)

        # Cleanup tracker periodically
        self._response_tracker.cleanup()

    async def _generate_and_send(self, role: str, msg: TeamMessage) -> None:
        """Generate a response using the role's agent and send via the role's bot."""
        agent = self.agents.get(role)
        bot = self.bots.get(role)
        if not agent or not bot:
            return

        try:
            response = await agent.respond(msg)
            if response:
                await bot.send_message(
                    chat_id=msg.chat_id,
                    text=response,
                    reply_to=msg.message_id,
                )
                self._response_tracker.record_response(role)
                logger.info("Team: {} responded to message {}", role, msg.message_id)
        except Exception as e:
            logger.error("Team: {} failed to respond: {}", role, e)
