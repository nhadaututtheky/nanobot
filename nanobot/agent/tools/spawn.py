"""Spawn tool for creating background subagents."""

from typing import TYPE_CHECKING, Any

from nanobot.agent.tools.base import Tool

if TYPE_CHECKING:
    from nanobot.agent.subagent import SubagentManager


class SpawnTool(Tool):
    """Tool to spawn a subagent for background task execution."""

    def __init__(self, manager: "SubagentManager"):
        self._manager = manager
        self._origin_channel = "cli"
        self._origin_chat_id = "direct"
        self._session_key = "cli:direct"

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the origin context for subagent announcements."""
        self._origin_channel = channel
        self._origin_chat_id = chat_id
        self._session_key = f"{channel}:{chat_id}"

    @property
    def name(self) -> str:
        return "spawn"

    def _get_roles_description(self) -> str:
        """Build dynamic description listing all available roles."""
        effective = self._manager.subagent_config.get_effective_roles()
        parts: list[str] = []
        for role_id, cfg in effective.items():
            display = cfg.display_name or role_id
            icon = f"{cfg.icon} " if cfg.icon else ""
            desc = cfg.description or ""
            parts.append(f"{icon}'{role_id}' ({display}): {desc}")
        return "\n".join(parts)

    @property
    def description(self) -> str:
        roles_desc = self._get_roles_description()
        return (
            "Spawn a background subagent for an explicitly assigned TASK. "
            "Use when a user gives you a concrete job that a specialized role can handle "
            "(e.g., research, code writing, code review).\n"
            "NEVER use for chat, conversation, questions, or greetings — "
            "just reply with text for those.\n"
            f"Available roles:\n{roles_desc}"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        # Dynamic role list from config
        effective = self._manager.subagent_config.get_effective_roles()
        role_ids = list(effective.keys())

        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The task for the subagent to complete",
                },
                "label": {
                    "type": "string",
                    "description": "Optional short label for the task (for display)",
                },
                "role": {
                    "type": "string",
                    "enum": role_ids,
                    "description": f"Subagent role determining available tools. Available: {', '.join(role_ids)} (default: general)",
                },
                "context": {
                    "type": "string",
                    "description": "Optional background context from parent agent to help the subagent",
                },
                "max_iterations": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 40,
                    "description": "Max tool-call iterations before stopping (default: 15)",
                },
            },
            "required": ["task"],
        }

    async def execute(  # type: ignore[override]
        self,
        task: str,
        label: str | None = None,
        role: str = "general",
        context: str | None = None,
        max_iterations: int = 15,
        **kwargs: Any,
    ) -> str:
        """Spawn a subagent to execute the given task."""
        return await self._manager.spawn(
            task=task,
            label=label,
            origin_channel=self._origin_channel,
            origin_chat_id=self._origin_chat_id,
            session_key=self._session_key,
            role=role,
            context=context,
            max_iterations=max_iterations,
        )
