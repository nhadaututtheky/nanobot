"""Goal decomposer — breaks a high-level goal into a TaskGraph via LLM."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from loguru import logger

from nanobot.orchestrator.models import (
    GraphStatus,
    TaskCapability,
    TaskEdge,
    TaskGraph,
    TaskNode,
)

if TYPE_CHECKING:
    from nanobot.orchestrator.router import ModelRouter
    from nanobot.providers.base import LLMProvider

DECOMPOSE_SYSTEM_PROMPT = """\
You are a task decomposition engine. Given a high-level goal, break it down \
into a minimal set of concrete subtasks that can be executed by AI agents.

Each subtask must specify:
- id: short unique string (t1, t2, ...)
- label: concise title (< 60 chars)
- description: what exactly to do
- capability: one of [reasoning, coding, research, creative, data_analysis, translation, summarization, general]
- worker_role: one of [general, researcher, coder, reviewer]
- depends_on: list of task IDs that must complete first (empty if independent)

Rules:
1. Maximize parallelism — only add dependencies when strictly necessary.
2. Keep tasks atomic — each should take 1-5 minutes for an AI agent.
3. Prefer fewer tasks (3-10) over many small ones.
4. First task(s) should have NO dependencies.
5. Use the right capability so the router picks the best model.

Respond with ONLY valid JSON (no markdown fences):
{"tasks": [{"id": "t1", "label": "...", "description": "...", "capability": "...", "worker_role": "...", "depends_on": []}]}
"""


class GoalDecomposer:
    """Decomposes a goal string into a TaskGraph using the strongest available model."""

    def __init__(self, provider: LLMProvider, router: ModelRouter) -> None:
        self._provider = provider
        self._router = router

    async def decompose(
        self,
        goal: str,
        context: str = "",
        max_tasks: int = 20,
        origin_channel: str = "cli",
        origin_chat_id: str = "direct",
    ) -> TaskGraph:
        """Send goal to LLM, parse JSON output, build and return a TaskGraph."""
        orchestrator_model = self._router.route_orchestrator()
        logger.info(
            "Decomposing goal with {} (tier={})", orchestrator_model.model, orchestrator_model.tier
        )

        user_content = f"Goal: {goal}"
        if context:
            user_content += f"\n\nAdditional context:\n{context}"
        user_content += f"\n\nConstraint: maximum {max_tasks} tasks."

        messages: list[dict[str, str]] = [
            {"role": "system", "content": DECOMPOSE_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        response = await self._provider.chat(
            messages=messages,
            model=orchestrator_model.model,
            temperature=0.3,
            max_tokens=4096,
        )

        raw = (response.content or "").strip()
        # Strip markdown fences if the model wraps output
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("Decomposer JSON parse failed: {}", exc)
            raise ValueError(f"LLM returned invalid JSON: {exc}") from exc

        tasks_raw: list[dict] = data.get("tasks", [])
        if not tasks_raw:
            raise ValueError("LLM returned zero tasks")

        # Clamp to max_tasks
        tasks_raw = tasks_raw[:max_tasks]

        graph = TaskGraph(
            goal=goal,
            status=GraphStatus.DRAFT,
            origin_channel=origin_channel,
            origin_chat_id=origin_chat_id,
        )

        # Build nodes
        valid_ids: set[str] = set()
        for t in tasks_raw:
            tid = str(t.get("id", ""))
            if not tid:
                continue
            valid_ids.add(tid)

            cap_str = t.get("capability", "general")
            try:
                cap = TaskCapability(cap_str)
            except ValueError:
                cap = TaskCapability.GENERAL

            node = TaskNode(
                id=tid,
                label=t.get("label", tid),
                description=t.get("description", ""),
                capability=cap,
                worker_role=t.get("worker_role", "general"),
            )

            # Route to best model
            best = self._router.route(node)
            node.assigned_model = best.model

            graph.nodes.append(node)

        # Build edges (only between valid node IDs)
        for t in tasks_raw:
            tid = str(t.get("id", ""))
            for dep in t.get("depends_on", []):
                dep = str(dep)
                if dep in valid_ids and tid in valid_ids and dep != tid:
                    graph.edges.append(TaskEdge(from_id=dep, to_id=tid))

        # Validate DAG — reject cycles
        if graph.has_cycle():
            logger.warning("Decomposer produced a cyclic graph — removing back-edges")
            # Fall back: strip all edges to prevent deadlock
            graph.edges = []

        logger.info(
            "Decomposed goal into {} tasks, {} edges",
            len(graph.nodes),
            len(graph.edges),
        )
        return graph
