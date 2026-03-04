"""Handoff tool — allows the LLM to transfer conversation to another agent role."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nanobot.agent.tools.base import Tool

if TYPE_CHECKING:
    from nanobot.agent.handoff import HandoffManager


class HandoffTool(Tool):
    """Tool that lets the agent hand off the conversation to a different role."""

    def __init__(self, handoff_manager: HandoffManager) -> None:
        self._manager = handoff_manager

    @property
    def name(self) -> str:
        return "handoff"

    @property
    def description(self) -> str:
        return (
            "Transfer the conversation to a specialised agent role. "
            "Use this when the task requires expertise you don't have, "
            "e.g. handing off to a 'coder' for implementation or "
            "'researcher' for in-depth analysis."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target_role": {
                    "type": "string",
                    "description": (
                        "The role to hand off to (e.g. 'coder', 'researcher', 'reviewer'). "
                        "Must be a configured role name."
                    ),
                },
                "reason": {
                    "type": "string",
                    "description": "Why you are handing off — what does the target need to do?",
                },
                "context": {
                    "type": "string",
                    "description": "Additional context or instructions for the target agent.",
                },
            },
            "required": ["target_role", "reason"],
        }

    async def execute(  # type: ignore[override]
        self,
        target_role: str,
        reason: str,
        context: str = "",
        **kwargs: Any,
    ) -> str:
        """Execute the handoff."""
        full_reason = reason
        if context:
            full_reason = f"{reason}\n\nAdditional context: {context}"

        # The handoff manager needs current messages — passed via _context
        current_messages = kwargs.get("_messages", [])
        return await self._manager.handoff(
            target_role=target_role,
            reason=full_reason,
            current_messages=current_messages,
        )
