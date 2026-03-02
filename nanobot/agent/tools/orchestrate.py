"""Orchestrate tool — agent triggers goal decomposition and execution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nanobot.agent.tools.base import Tool

if TYPE_CHECKING:
    from nanobot.orchestrator.decomposer import GoalDecomposer
    from nanobot.orchestrator.executor import GraphExecutor
    from nanobot.orchestrator.store import GraphStore


class OrchestrateTool(Tool):
    """Tool to decompose a goal into a task graph and execute it."""

    def __init__(
        self,
        decomposer: GoalDecomposer,
        executor: GraphExecutor,
        store: GraphStore,
    ) -> None:
        self._decomposer = decomposer
        self._executor = executor
        self._store = store
        self._origin_channel = "cli"
        self._origin_chat_id = "direct"

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set origin context for result announcements."""
        self._origin_channel = channel
        self._origin_chat_id = chat_id

    @property
    def name(self) -> str:
        return "orchestrate"

    @property
    def description(self) -> str:
        return (
            "Break down an explicitly assigned TASK into subtasks and execute them "
            "with specialized AI models in parallel.\n"
            "Use ONLY when a user assigns you concrete work that requires multiple "
            "distinct subtasks (e.g., 'research X, then code Y, then review Z').\n\n"
            "NEVER use for chat, conversation, questions, greetings, or anything "
            "you can answer directly by writing text."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "The high-level goal to decompose and execute",
                },
                "context": {
                    "type": "string",
                    "description": "Optional additional context to help with decomposition",
                },
                "preview_only": {
                    "type": "boolean",
                    "description": "If true, decompose the goal and return the task graph without executing (default: false)",
                },
            },
            "required": ["goal"],
        }

    async def execute(
        self,
        goal: str,
        context: str = "",
        preview_only: bool = False,
        **kwargs: Any,
    ) -> str:
        """Decompose goal into task graph and optionally execute it."""
        try:
            graph = await self._decomposer.decompose(
                goal=goal,
                context=context,
                origin_channel=self._origin_channel,
                origin_chat_id=self._origin_chat_id,
            )
        except Exception as e:
            return f"Failed to decompose goal: {e}"

        await self._store.add(graph)

        if preview_only:
            return self._format_preview(graph)

        # Execute in background
        await self._executor.execute(graph)

        return self._format_started(graph)

    def _format_preview(self, graph: Any) -> str:
        """Format graph as a preview summary."""
        lines = [f"Task Graph Preview (id: {graph.id})", f"Goal: {graph.goal}", ""]
        for node in graph.nodes:
            deps = graph.get_dependencies(node.id)
            dep_str = f" (after: {', '.join(deps)})" if deps else ""
            lines.append(
                f"  {node.id}: [{node.capability.value}] {node.label} "
                f"→ {node.assigned_model}{dep_str}"
            )
        lines.append(f"\n{len(graph.nodes)} tasks, {len(graph.edges)} dependencies")
        lines.append("Call orchestrate again without preview_only to execute.")
        return "\n".join(lines)

    def _format_started(self, graph: Any) -> str:
        """Format graph execution start summary."""
        lines = [
            f"Orchestrator started (id: {graph.id})",
            f"Goal: {graph.goal}",
            f"Tasks: {len(graph.nodes)}, Dependencies: {len(graph.edges)}",
            "",
        ]
        for node in graph.nodes:
            lines.append(
                f"  {node.id}: [{node.capability.value}] {node.label} → {node.assigned_model}"
            )
        lines.append("\nRunning in background. I'll notify you when it completes.")
        return "\n".join(lines)
