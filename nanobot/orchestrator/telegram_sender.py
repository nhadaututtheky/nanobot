"""Lightweight Telegram sender for orchestrator multi-bot updates.

Uses raw HTTP (aiohttp) — no dependency on Telegram channel or python-telegram-bot.
Each sub-agent role can have its own bot token, posting to a shared group.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import aiohttp
from loguru import logger

if TYPE_CHECKING:
    from nanobot.config.schema import Config
    from nanobot.orchestrator.models import TaskGraph, TaskNode

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

_MD_ESCAPE_CHARS = str.maketrans({"_": r"\_", "*": r"\*", "[": r"\[", "]": r"\]", "`": r"\`"})


def _escape_md(text: str) -> str:
    """Escape Markdown special characters for Telegram."""
    return text.translate(_MD_ESCAPE_CHARS)


class TelegramOrchestratorSender:
    """Send orchestrator updates to Telegram via per-role bot tokens."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._orch_cfg = config.agents.orchestrator
        self._session: aiohttp.ClientSession | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._orch_cfg.telegram_group_id)

    def _get_bot_token(self, role: str) -> str | None:
        """Get bot token for a role: role-specific → main telegram bot → None."""
        effective = self._config.agents.subagent.get_effective_roles()
        role_cfg = effective.get(role)
        if role_cfg and role_cfg.telegram_bot_token:
            return role_cfg.telegram_bot_token

        # Fallback to main Telegram bot token
        tg_cfg = self._config.channels.telegram
        return tg_cfg.token if tg_cfg.token else None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _send(self, token: str, chat_id: str, text: str) -> bool:
        """Send a message via Telegram Bot API."""
        session = await self._ensure_session()
        url = TELEGRAM_API.format(token=token)
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        try:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning("Telegram send failed ({}): {}", resp.status, body[:200])
                    return False
                return True
        except Exception as e:
            logger.warning("Telegram send error: {}", e)
            return False

    async def send_node_started(self, graph: TaskGraph, node: TaskNode) -> None:
        """Post when a node starts execution."""
        if not self.enabled:
            return

        token = self._get_bot_token(node.worker_role)
        if not token:
            return

        effective = self._config.agents.subagent.get_effective_roles()
        role_cfg = effective.get(node.worker_role)
        icon = role_cfg.icon if role_cfg else "🤖"
        display = role_cfg.display_name if role_cfg and role_cfg.display_name else node.worker_role

        text = (
            f"{icon} *[{display}]* Starting task...\n"
            f"📋 _{_escape_md(node.label)}_\n"
            f"🎯 Goal: _{_escape_md(graph.goal[:80])}_"
        )
        await self._send(token, self._orch_cfg.telegram_group_id, text)

    async def send_node_done(self, graph: TaskGraph, node: TaskNode) -> None:
        """Post when a node finishes."""
        if not self.enabled:
            return

        token = self._get_bot_token(node.worker_role)
        if not token:
            return

        effective = self._config.agents.subagent.get_effective_roles()
        role_cfg = effective.get(node.worker_role)
        icon = role_cfg.icon if role_cfg else "🤖"
        display = role_cfg.display_name if role_cfg and role_cfg.display_name else node.worker_role

        status_icon = "✅" if node.status.value == "completed" else "❌"
        summary = (
            node.output_summary[:300]
            if node.output_summary
            else (node.error[:300] if node.error else "done")
        )

        text = (
            f"{icon} *[{display}]* {status_icon} Task finished\n"
            f"📋 _{_escape_md(node.label)}_\n"
            f"📝 {_escape_md(summary)}"
        )
        await self._send(token, self._orch_cfg.telegram_group_id, text)

    async def send_graph_summary(self, graph: TaskGraph) -> None:
        """Post final summary to result channel (or group if no channel set)."""
        if not self.enabled:
            return

        chat_id = self._orch_cfg.telegram_result_channel or self._orch_cfg.telegram_group_id
        token = self._get_bot_token("general")
        if not token:
            return

        status_text = {
            "completed": "✅ Completed",
            "failed": "❌ Failed",
            "cancelled": "🚫 Cancelled",
        }.get(graph.status.value, graph.status.value)

        node_lines: list[str] = []
        for n in graph.nodes:
            s_icon = {"completed": "✅", "failed": "❌", "skipped": "⏭", "cancelled": "🚫"}.get(
                n.status.value, "⏳"
            )
            summary = (
                n.output_summary[:100] if n.output_summary else (n.error[:100] if n.error else "—")
            )
            node_lines.append(f"  {s_icon} {n.label}: {summary}")

        text = (
            f"🏁 *Orchestrator Result*\n"
            f"🎯 _{graph.goal[:100]}_\n"
            f"Status: {status_text} | Progress: {round(graph.progress * 100)}%\n\n"
            f"*Tasks ({len(graph.nodes)}):*\n" + "\n".join(node_lines)
        )

        # Telegram message limit is 4096 chars
        if len(text) > 4000:
            text = text[:3997] + "..."

        await self._send(token, chat_id, text)

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
