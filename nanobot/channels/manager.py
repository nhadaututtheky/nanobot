"""Channel manager for coordinating chat channels."""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import Config


class ChannelManager:
    """
    Manages chat channels and coordinates message routing.

    Responsibilities:
    - Initialize enabled channels (Telegram, WhatsApp, etc.)
    - Start/stop channels
    - Route outbound messages
    """

    def __init__(self, config: Config, bus: MessageBus, provider: Any = None):
        self.config = config
        self.bus = bus
        self._provider = provider
        self.channels: dict[str, BaseChannel] = {}
        self._team_managers: list[Any] = []  # TelegramTeamManager instances
        self._dispatch_task: asyncio.Task | None = None

        self._init_channels()

    def _init_channels(self) -> None:
        """Initialize channels based on config."""

        # Telegram channel
        if self.config.channels.telegram.enabled:
            try:
                from nanobot.channels.telegram import TelegramChannel
                self.channels["telegram"] = TelegramChannel(
                    self.config.channels.telegram,
                    self.bus,
                    groq_api_key=self.config.providers.groq.api_key,
                )
                logger.info("Telegram channel enabled")
            except ImportError as e:
                logger.warning("Telegram channel not available: {}", e)

        # WhatsApp channel
        if self.config.channels.whatsapp.enabled:
            try:
                from nanobot.channels.whatsapp import WhatsAppChannel
                self.channels["whatsapp"] = WhatsAppChannel(
                    self.config.channels.whatsapp, self.bus
                )
                logger.info("WhatsApp channel enabled")
            except ImportError as e:
                logger.warning("WhatsApp channel not available: {}", e)

        # Discord channel
        if self.config.channels.discord.enabled:
            try:
                from nanobot.channels.discord import DiscordChannel
                self.channels["discord"] = DiscordChannel(
                    self.config.channels.discord, self.bus
                )
                logger.info("Discord channel enabled")
            except ImportError as e:
                logger.warning("Discord channel not available: {}", e)

        # Feishu channel
        if self.config.channels.feishu.enabled:
            try:
                from nanobot.channels.feishu import FeishuChannel
                self.channels["feishu"] = FeishuChannel(
                    self.config.channels.feishu, self.bus
                )
                logger.info("Feishu channel enabled")
            except ImportError as e:
                logger.warning("Feishu channel not available: {}", e)

        # Mochat channel
        if self.config.channels.mochat.enabled:
            try:
                from nanobot.channels.mochat import MochatChannel

                self.channels["mochat"] = MochatChannel(
                    self.config.channels.mochat, self.bus
                )
                logger.info("Mochat channel enabled")
            except ImportError as e:
                logger.warning("Mochat channel not available: {}", e)

        # DingTalk channel
        if self.config.channels.dingtalk.enabled:
            try:
                from nanobot.channels.dingtalk import DingTalkChannel
                self.channels["dingtalk"] = DingTalkChannel(
                    self.config.channels.dingtalk, self.bus
                )
                logger.info("DingTalk channel enabled")
            except ImportError as e:
                logger.warning("DingTalk channel not available: {}", e)

        # Email channel
        if self.config.channels.email.enabled:
            try:
                from nanobot.channels.email import EmailChannel
                self.channels["email"] = EmailChannel(
                    self.config.channels.email, self.bus
                )
                logger.info("Email channel enabled")
            except ImportError as e:
                logger.warning("Email channel not available: {}", e)

        # Slack channel
        if self.config.channels.slack.enabled:
            try:
                from nanobot.channels.slack import SlackChannel
                self.channels["slack"] = SlackChannel(
                    self.config.channels.slack, self.bus
                )
                logger.info("Slack channel enabled")
            except ImportError as e:
                logger.warning("Slack channel not available: {}", e)

        # QQ channel
        if self.config.channels.qq.enabled:
            try:
                from nanobot.channels.qq import QQChannel
                self.channels["qq"] = QQChannel(
                    self.config.channels.qq,
                    self.bus,
                )
                logger.info("QQ channel enabled")
            except ImportError as e:
                logger.warning("QQ channel not available: {}", e)

        # Telegram userbot (Telethon MTProto — observes bot messages in groups)
        if self.config.channels.telegram_userbot.enabled:
            try:
                from nanobot.channels.telegram_userbot import TelegramUserbotChannel
                self.channels["telegram_userbot"] = TelegramUserbotChannel(
                    self.config.channels.telegram_userbot, self.bus
                )
                logger.info("Telegram userbot channel enabled")
            except ImportError as e:
                logger.warning("Telegram userbot channel not available: {}", e)

        # Matrix channel
        if self.config.channels.matrix.enabled:
            try:
                from nanobot.channels.matrix import MatrixChannel
                self.channels["matrix"] = MatrixChannel(
                    self.config.channels.matrix,
                    self.bus,
                )
                logger.info("Matrix channel enabled")
            except ImportError as e:
                logger.warning("Matrix channel not available: {}", e)

        # Telegram multi-bot team groups
        self._init_telegram_teams()

    def _make_team_provider(self) -> Any:
        """Create a LiteLLMProvider for team bots (multi-model routing)."""
        from nanobot.providers.litellm_provider import LiteLLMProvider

        # Team bots need LiteLLMProvider to route different models per role.
        model = self.config.agents.defaults.model
        p = self.config.get_provider(model)
        return LiteLLMProvider(
            api_key=p.api_key if p else None,
            api_base=self.config.get_api_base(model) if p else None,
            default_model=model,
            extra_headers=p.extra_headers if p else None,
            config=self.config,
        )

    def _init_telegram_teams(self) -> None:
        """Initialize multi-bot team groups."""
        team_groups = self.config.channels.telegram.team_groups
        if not team_groups:
            return

        try:
            from pathlib import Path

            from nanobot.channels.telegram.team_agent import TeamRoleAgent
            from nanobot.channels.telegram.team_manager import TelegramTeamManager

            team_provider = self._make_team_provider()
            workspace = Path(self.config.agents.defaults.workspace).expanduser()

            for label, group_cfg in team_groups.items():
                if not group_cfg.enabled or not group_cfg.chat_id:
                    continue

                manager = TelegramTeamManager(
                    group_config=group_cfg,
                    config=self.config,
                    provider=team_provider,
                )

                if not manager.bots:
                    continue

                # Create per-role agents
                effective_team_roles = group_cfg.get_effective_team_roles()
                agents: dict[str, TeamRoleAgent] = {}
                for role_name in manager.bots:
                    role_cfg = effective_team_roles.get(role_name)
                    if role_cfg:
                        agents[role_name] = TeamRoleAgent(
                            role=role_name,
                            role_config=role_cfg,
                            provider=team_provider,
                            workspace=workspace,
                            config=self.config,
                            group_config=group_cfg,
                        )
                manager.set_agents(agents)

                self._team_managers.append(manager)
                logger.info(
                    "Telegram team '{}' enabled ({} bots for group {})",
                    label, len(manager.bots), group_cfg.chat_id,
                )

        except ImportError as e:
            logger.warning("Telegram team not available: {}", e)
        except Exception as e:
            logger.error("Failed to init Telegram teams: {}", e)

    async def _start_channel(self, name: str, channel: BaseChannel) -> None:
        """Start a channel and log any exceptions."""
        try:
            await channel.start()
        except Exception as e:
            logger.error("Failed to start channel {}: {}", name, e)

    async def start_all(self) -> None:
        """Start all channels, team managers, and the outbound dispatcher."""
        if not self.channels and not self._team_managers:
            logger.warning("No channels enabled")
            return

        # Start outbound dispatcher
        self._dispatch_task = asyncio.create_task(self._dispatch_outbound())

        # Start channels
        tasks = []
        for name, channel in self.channels.items():
            logger.info("Starting {} channel...", name)
            tasks.append(asyncio.create_task(self._start_channel(name, channel)))

        # Start team managers
        for tm in self._team_managers:
            tasks.append(asyncio.create_task(self._start_team(tm)))

        # Wait for all to complete (they should run forever)
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _start_team(self, tm: Any) -> None:
        """Start a team manager and log any exceptions."""
        try:
            await tm.start()
        except Exception as e:
            logger.error("Failed to start Telegram team: {}", e)

    async def stop_all(self) -> None:
        """Stop all channels, team managers, and the dispatcher."""
        logger.info("Stopping all channels...")

        # Stop dispatcher
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass

        # Stop team managers
        for tm in self._team_managers:
            try:
                await tm.stop()
            except Exception as e:
                logger.error("Error stopping Telegram team: {}", e)

        # Stop all channels
        for name, channel in self.channels.items():
            try:
                await channel.stop()
                logger.info("Stopped {} channel", name)
            except Exception as e:
                logger.error("Error stopping {}: {}", name, e)

    async def _dispatch_outbound(self) -> None:
        """Dispatch outbound messages to the appropriate channel."""
        logger.info("Outbound dispatcher started")

        while True:
            try:
                msg = await asyncio.wait_for(
                    self.bus.consume_outbound(),
                    timeout=1.0
                )

                if msg.metadata.get("_progress"):
                    if msg.metadata.get("_tool_hint") and not self.config.channels.send_tool_hints:
                        continue
                    if not msg.metadata.get("_tool_hint") and not self.config.channels.send_progress:
                        continue

                channel = self.channels.get(msg.channel)
                if channel:
                    try:
                        await channel.send(msg)
                    except Exception as e:
                        logger.error("Error sending to {}: {}", msg.channel, e)
                else:
                    logger.warning("Unknown channel: {}", msg.channel)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    def get_channel(self, name: str) -> BaseChannel | None:
        """Get a channel by name."""
        return self.channels.get(name)

    def get_status(self) -> dict[str, Any]:
        """Get status of all channels."""
        return {
            name: {
                "enabled": True,
                "running": channel.is_running
            }
            for name, channel in self.channels.items()
        }

    def set_tool_registry(self, tools: Any) -> None:
        """Share a ToolRegistry with team agents (called after MCP connected)."""
        for tm in self._team_managers:
            for agent in tm.agents.values():
                agent.set_tool_registry(tools)
        if self._team_managers:
            logger.info("Team agents: tool registry wired ({} tools)", len(tools.get_definitions()))

    @property
    def enabled_channels(self) -> list[str]:
        """Get list of enabled channel names."""
        return list(self.channels.keys())
