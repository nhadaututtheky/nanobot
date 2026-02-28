"""GatewayContext — shared service container passed to every handler."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus
    from nanobot.channels.manager import ChannelManager
    from nanobot.config.schema import Config
    from nanobot.cron.service import CronService
    from nanobot.heartbeat.service import HeartbeatService
    from nanobot.session.manager import SessionManager

    from .broadcaster import Broadcaster


@dataclass
class GatewayContext:
    """Everything a handler needs to interact with the system."""

    config: Config
    config_path: Path
    agent: AgentLoop
    session_manager: SessionManager
    cron: CronService
    channels: ChannelManager
    heartbeat: HeartbeatService
    bus: MessageBus
    broadcaster: Broadcaster

    # Mutable runtime state
    active_runs: dict[str, list[Any]] = field(default_factory=dict)
    """Map session_key → list of asyncio.Task for active chat runs."""
