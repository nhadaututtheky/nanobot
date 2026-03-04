"""Agent handoff — synchronous conversation transfer between agent roles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from nanobot.agent.context import ContextBuilder
    from nanobot.config.schema import Config
    from nanobot.providers.base import LLMProvider


_SUMMARY_SYSTEM = (
    "Summarise the conversation so far in 3-5 bullet points. "
    "Focus on: the user's request, key decisions made, current state, "
    "and any pending work. Be concise."
)


class HandoffManager:
    """Manages synchronous agent handoffs between roles.

    Unlike subagents (fire-and-forget, separate session), handoffs:
    - Transfer full conversation context to the target role
    - Are synchronous and blocking
    - The target takes over control of the response
    """

    def __init__(
        self,
        provider: LLMProvider,
        config: Config,
        context_builder: ContextBuilder,
    ) -> None:
        self._provider = provider
        self._config = config
        self._context = context_builder

    async def handoff(
        self,
        target_role: str,
        reason: str,
        current_messages: list[dict[str, Any]],
        max_iterations: int = 20,
    ) -> str:
        """Hand off the conversation to a different agent role.

        Args:
            target_role: Name of the target role (must exist in config).
            reason: Why the handoff is happening.
            current_messages: Current conversation messages.
            max_iterations: Max tool call iterations for the target.

        Returns:
            The target agent's response text.
        """
        roles = self._config.agents.subagent.get_effective_roles()
        role_config = roles.get(target_role)
        if not role_config:
            return f"Error: Role '{target_role}' not found. Available: {', '.join(roles.keys())}"

        # Summarise conversation for context transfer
        summary = await self._summarise(current_messages)

        # Build target agent messages
        system_prompt = role_config.persona or f"You are a {target_role} agent."
        model = role_config.model or self._config.agents.defaults.model
        temperature = role_config.temperature or 0.3
        max_tokens = role_config.max_tokens or 4096

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": (
                f"## Handoff Context\n"
                f"You are taking over this conversation from another agent.\n"
                f"**Reason**: {reason}\n\n"
                f"## Conversation Summary\n{summary}\n\n"
                f"## Last Messages\n"
            )},
        ]

        # Append last few messages for immediate context
        recent = current_messages[-6:] if len(current_messages) > 6 else current_messages
        for msg in recent:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        # Simple single-turn response (no tool loop for handoff)
        logger.info("Handoff to role '{}': {}", target_role, reason[:100])
        try:
            response = await self._provider.chat(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            result = (response.content or "").strip()
            if not result:
                result = f"Handoff to {target_role} completed but no response generated."
            return result
        except Exception as exc:
            logger.error("Handoff to '{}' failed: {}", target_role, exc)
            return f"Handoff failed: {exc}"

    async def _summarise(self, messages: list[dict[str, Any]]) -> str:
        """Generate a brief summary of the conversation."""
        # Format messages for summary
        parts: list[str] = []
        for msg in messages[-20:]:  # Last 20 messages max
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                truncated = content[:500] if len(content) > 500 else content
                parts.append(f"[{role}] {truncated}")

        if not parts:
            return "No conversation history available."

        try:
            response = await self._provider.chat(
                messages=[
                    {"role": "system", "content": _SUMMARY_SYSTEM},
                    {"role": "user", "content": "\n\n".join(parts)},
                ],
                temperature=0.0,
                max_tokens=512,
            )
            return (response.content or "").strip() or "Could not generate summary."
        except Exception:
            return "Summary unavailable."
