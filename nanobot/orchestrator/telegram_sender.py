"""Telegram sender for orchestrator multi-bot updates.

Uses raw HTTP (aiohttp) — no dependency on Telegram channel or python-telegram-bot.
Each sub-agent role can have its own bot token, posting to a shared group.
Messages are threaded via reply_to_message_id for a cohesive team experience.
"""

from __future__ import annotations

import time
from collections import defaultdict
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


def _progress_bar(progress: float, length: int = 10) -> str:
    """Render a text progress bar: ████░░░░░░"""
    filled = int(progress * length)
    return "\u2588" * filled + "\u2591" * (length - filled)


# Role icon/name fallbacks by capability keyword
_CAPABILITY_ICONS: dict[str, str] = {
    "research": "\U0001f50d",
    "coding": "\U0001f4bb",
    "creative": "\U0001f3a8",
    "reasoning": "\U0001f9e0",
    "data_analysis": "\U0001f4ca",
    "translation": "\U0001f310",
    "summarization": "\U0001f4dd",
    "general": "\U0001f916",
}


class TelegramOrchestratorSender:
    """Send orchestrator updates to Telegram via per-role bot tokens."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._orch_cfg = config.agents.orchestrator
        self._session: aiohttp.ClientSession | None = None
        # Thread anchors: graph_id → message_id of plan post
        self._thread_anchors: dict[str, int] = {}
        # Progress throttle: node_id → monotonic timestamp of last progress post
        self._last_progress: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        return bool(self._orch_cfg.telegram_group_id)

    def _get_bot_token(self, role: str) -> str | None:
        """Get bot token for a role: role-specific -> main telegram bot -> None."""
        effective = self._config.agents.subagent.get_effective_roles()
        role_cfg = effective.get(role)
        if role_cfg and role_cfg.telegram_bot_token:
            return role_cfg.telegram_bot_token

        # Fallback to main Telegram bot token
        tg_cfg = self._config.channels.telegram
        return tg_cfg.token if tg_cfg.token else None

    def _get_role_display(self, role: str) -> tuple[str, str]:
        """Get (icon, display_name) for a role from effective config."""
        effective = self._config.agents.subagent.get_effective_roles()
        role_cfg = effective.get(role)
        icon = role_cfg.icon if role_cfg and role_cfg.icon else "\U0001f916"
        name = role_cfg.display_name if role_cfg and role_cfg.display_name else role
        return icon, name

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _send(
        self,
        token: str,
        chat_id: str,
        text: str,
        *,
        reply_to: int | None = None,
    ) -> int | None:
        """Send a message via Telegram Bot API. Returns message_id on success."""
        session = await self._ensure_session()
        url = TELEGRAM_API.format(token=token)
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        if reply_to is not None:
            payload["reply_to_message_id"] = reply_to
            payload["allow_sending_without_reply"] = True
        try:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning("Telegram send failed ({}): {}", resp.status, body[:200])
                    return None
                data = await resp.json()
                result = data.get("result", {})
                return result.get("message_id")
        except Exception as e:
            logger.warning("Telegram send error: {}", e)
            return None

    # --- wave computation ---

    def _compute_waves(self, graph: TaskGraph) -> list[list[str]]:
        """BFS topological ordering into execution waves (dependency depth)."""
        from collections import deque

        node_ids = {n.id for n in graph.nodes}
        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
        adj: dict[str, list[str]] = defaultdict(list)
        for edge in graph.edges:
            if edge.from_id in node_ids and edge.to_id in node_ids:
                in_degree[edge.to_id] += 1
                adj[edge.from_id].append(edge.to_id)

        # BFS by waves
        waves: list[list[str]] = []
        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
        while queue:
            wave = list(queue)
            waves.append(wave)
            next_queue: deque[str] = deque()
            for nid in wave:
                for neighbor in adj[nid]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_queue.append(neighbor)
            queue = next_queue

        return waves

    # --- graph lifecycle ---

    async def send_graph_started(self, graph: TaskGraph) -> None:
        """Boss bot announces the full plan. Creates thread anchor."""
        if not self.enabled:
            return

        token = self._get_bot_token("general")
        if not token:
            return

        waves = self._compute_waves(graph)
        node_map = {n.id: n for n in graph.nodes}

        wave_lines: list[str] = []
        for i, wave_ids in enumerate(waves, 1):
            nodes_in_wave: list[str] = []
            for nid in wave_ids:
                node = node_map.get(nid)
                if not node:
                    continue
                icon, _ = self._get_role_display(node.worker_role)
                cap_icon = _CAPABILITY_ICONS.get(node.capability.value, icon)
                model_short = node.assigned_model.split("/")[-1] if node.assigned_model else "auto"
                nodes_in_wave.append(f"{cap_icon} {_escape_md(node.label)} ({model_short})")
            wave_lines.append(f"Wave {i}: " + ", ".join(nodes_in_wave))

        text = (
            f"\U0001f3af *New Mission*\n"
            f"_{_escape_md(graph.goal[:200])}_\n"
            f"\U0001f4ca Plan: {len(graph.nodes)} tasks, {len(waves)} waves\n"
            + "\n".join(wave_lines)
        )

        # Telegram message limit
        if len(text) > 4000:
            text = text[:3997] + "..."

        msg_id = await self._send(token, self._orch_cfg.telegram_group_id, text)
        if msg_id is not None:
            self._thread_anchors[graph.id] = msg_id

    async def send_node_started(self, graph: TaskGraph, node: TaskNode) -> None:
        """Post when a node starts execution — threaded reply."""
        if not self.enabled:
            return

        token = self._get_bot_token(node.worker_role)
        if not token:
            return

        icon, display = self._get_role_display(node.worker_role)
        reply_to = self._thread_anchors.get(graph.id)

        model_short = node.assigned_model.split("/")[-1] if node.assigned_model else "auto"

        # Show resolved dependencies
        dep_ids = graph.get_dependencies(node.id)
        dep_line = ""
        if dep_ids:
            dep_labels: list[str] = []
            for did in dep_ids:
                dep_node = graph.get_node(did)
                if dep_node:
                    dep_labels.append(dep_node.label)
            if dep_labels:
                dep_line = f"\n\U0001f517 Dependencies resolved: {_escape_md(', '.join(dep_labels))}"

        text = (
            f"{icon} *[{_escape_md(display)}]* Starting...\n"
            f"\U0001f4cb _{_escape_md(node.label)}_\n"
            f"\U0001f916 Model: {_escape_md(model_short)}"
            f"{dep_line}"
        )
        await self._send(token, self._orch_cfg.telegram_group_id, text, reply_to=reply_to)

    async def send_node_progress(
        self,
        graph: TaskGraph,
        node: TaskNode,
        *,
        tool_name: str = "",
        tool_result_preview: str = "",
        iteration: int = 0,
        max_iterations: int = 1,
    ) -> None:
        """Post progress update — throttled per node."""
        if not self.enabled:
            return

        # Throttle check
        throttle_s = getattr(self._orch_cfg, "telegram_progress_throttle_s", 20.0)
        now = time.monotonic()
        last = self._last_progress.get(node.id)
        if last is not None and (now - last) < throttle_s:
            return
        self._last_progress[node.id] = now

        token = self._get_bot_token(node.worker_role)
        if not token:
            return

        icon, display = self._get_role_display(node.worker_role)
        reply_to = self._thread_anchors.get(graph.id)

        progress = min(0.95, iteration / max_iterations) if max_iterations > 0 else node.progress
        bar = _progress_bar(progress)
        pct = round(progress * 100)

        lines = [
            f"{icon} *[{_escape_md(display)}]* Working...",
            f"\U0001f4ca {bar} ({pct}%)",
        ]
        if tool_name:
            lines.append(f"\U0001f527 Using: {_escape_md(tool_name)}")
        if tool_result_preview:
            preview = tool_result_preview[:150].replace("\n", " ")
            lines.append(f"\U0001f4dd {_escape_md(preview)}")

        text = "\n".join(lines)
        await self._send(token, self._orch_cfg.telegram_group_id, text, reply_to=reply_to)

    async def send_node_done(self, graph: TaskGraph, node: TaskNode) -> None:
        """Post when a node finishes — threaded reply with duration."""
        if not self.enabled:
            return

        token = self._get_bot_token(node.worker_role)
        if not token:
            return

        icon, display = self._get_role_display(node.worker_role)
        reply_to = self._thread_anchors.get(graph.id)

        status_icon = "\u2705" if node.status.value == "completed" else "\u274c"

        # Compute duration
        duration_str = ""
        if node.started_at and node.completed_at:
            try:
                from datetime import datetime

                started = datetime.fromisoformat(node.started_at)
                completed = datetime.fromisoformat(node.completed_at)
                elapsed = (completed - started).total_seconds()
                if elapsed >= 60:
                    duration_str = f" | \u23f1 {int(elapsed // 60)}m {int(elapsed % 60)}s"
                else:
                    duration_str = f" | \u23f1 {int(elapsed)}s"
            except (ValueError, TypeError):
                pass

        summary = (
            node.output_summary[:800]
            if node.output_summary
            else (node.error[:300] if node.error else "done")
        )

        text = (
            f"{icon} *[{_escape_md(display)}]* {status_icon} Done{duration_str}\n"
            f"\U0001f4cb _{_escape_md(node.label)}_\n"
            f"\U0001f4dd {_escape_md(summary)}"
        )

        # Telegram limit
        if len(text) > 4000:
            text = text[:3997] + "..."

        await self._send(token, self._orch_cfg.telegram_group_id, text, reply_to=reply_to)

        # Clean up throttle tracker
        self._last_progress.pop(node.id, None)

    async def send_graph_summary(self, graph: TaskGraph) -> None:
        """Post final summary to result channel (or group if no channel set)."""
        if not self.enabled:
            return

        chat_id = self._orch_cfg.telegram_result_channel or self._orch_cfg.telegram_group_id
        token = self._get_bot_token("general")
        if not token:
            return

        status_text = {
            "completed": "\u2705 Mission Complete",
            "failed": "\u274c Mission Failed",
            "cancelled": "\U0001f6ab Mission Cancelled",
        }.get(graph.status.value, graph.status.value)

        # Compute total duration
        total_duration = ""
        if graph.started_at and graph.completed_at:
            try:
                from datetime import datetime

                started = datetime.fromisoformat(graph.started_at)
                completed = datetime.fromisoformat(graph.completed_at)
                elapsed = (completed - started).total_seconds()
                if elapsed >= 60:
                    total_duration = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
                else:
                    total_duration = f"{int(elapsed)}s"
            except (ValueError, TypeError):
                pass

        # Collect models used
        models_used = sorted({
            n.assigned_model.split("/")[-1]
            for n in graph.nodes
            if n.assigned_model
        })

        completed_count = sum(1 for n in graph.nodes if n.status.value == "completed")

        # Header
        header_lines = [
            f"\U0001f3c1 *{status_text}*",
            f"\U0001f3af _{_escape_md(graph.goal[:150])}_",
            f"\U0001f4ca {completed_count}/{len(graph.nodes)} tasks completed"
            + (f" | \u23f1 {total_duration}" if total_duration else ""),
        ]
        if models_used:
            header_lines.append(f"\U0001f916 Models: {', '.join(models_used)}")

        # Per-node results with role icons
        node_lines: list[str] = []
        for n in graph.nodes:
            s_icon = {
                "completed": "\u2705",
                "failed": "\u274c",
                "skipped": "\u23ed",
                "cancelled": "\U0001f6ab",
            }.get(n.status.value, "\u23f3")
            role_icon, _ = self._get_role_display(n.worker_role)
            summary = (
                n.output_summary[:150]
                if n.output_summary
                else (n.error[:100] if n.error else "\u2014")
            )
            node_lines.append(f"  {s_icon} {role_icon} {_escape_md(n.label)}: {_escape_md(summary)}")

        text = (
            "\n".join(header_lines)
            + "\n\nResults:\n"
            + "\n".join(node_lines)
        )

        # Telegram message limit is 4096 chars
        if len(text) > 4000:
            text = text[:3997] + "..."

        await self._send(token, chat_id, text)

        # Clean up thread anchor
        self._thread_anchors.pop(graph.id, None)

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
