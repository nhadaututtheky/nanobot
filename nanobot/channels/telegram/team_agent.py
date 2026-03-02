"""Per-role agent for multi-bot Telegram team."""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.agent.context import ContextBuilder
from nanobot.session.manager import SessionManager

if TYPE_CHECKING:
    from nanobot.agent.tools.registry import ToolRegistry
    from nanobot.channels.telegram.team_bus import TeamMessage
    from nanobot.config.schema import Config, SubAgentRoleConfig, TelegramTeamGroupConfig
    from nanobot.providers.base import LLMProvider

# Max tool-call rounds to prevent infinite loops
_MAX_TOOL_ROUNDS = 5

# Tools that are dangerous without user allowlisting
_SENSITIVE_TOOLS = frozenset({"exec", "write_file", "edit_file"})


class TeamRoleAgent:
    """Per-role agent that processes messages for one bot in the team.

    Each role has its own session (isolated history) but observes ALL
    messages (from users and other bots) for shared context.
    Supports tool calling with safety: user allowlist, tool permissions per role.
    """

    def __init__(
        self,
        role: str,
        role_config: SubAgentRoleConfig,
        provider: LLMProvider,
        workspace: Path,
        config: Config,
        group_config: TelegramTeamGroupConfig | None = None,
    ) -> None:
        self._role = role
        self._role_config = role_config
        self._provider = provider
        self._config = config
        self._group_config = group_config
        self._context = ContextBuilder(workspace)
        self._sessions = SessionManager(workspace)
        self._tools: ToolRegistry | None = None
        self._history_limit = 50

    def set_tool_registry(self, tools: ToolRegistry) -> None:
        """Wire shared tool registry (called after MCP connected)."""
        self._tools = tools

    def _session_key(self, chat_id: str) -> str:
        """Per-role session key for isolation."""
        return f"telegram-team:{self._role}:{chat_id}"

    def _is_user_allowed(self, sender_id: str) -> bool:
        """Check if sender is in the allowlist (empty = allow all)."""
        if not self._group_config:
            return True
        allowed = self._group_config.allowed_user_ids
        if not allowed:
            return True  # No allowlist = allow all
        return sender_id in allowed

    def _is_tool_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed for this role based on config."""
        allowed = self._role_config.allowed_tools
        denied = self._role_config.denied_tools

        # If denied list exists, check it first
        if denied:
            for pattern in denied:
                if fnmatch.fnmatch(tool_name, pattern):
                    return False

        # If allowed list exists, tool must match at least one pattern
        if allowed:
            return any(fnmatch.fnmatch(tool_name, p) for p in allowed)

        # No restrictions configured — block sensitive tools for non-allowlisted groups
        if tool_name in _SENSITIVE_TOOLS:
            # Only allow if user allowlist is configured (some trust established)
            if self._group_config and not self._group_config.allowed_user_ids:
                return False

        return True

    def _get_filtered_tool_defs(self) -> list[dict[str, Any]] | None:
        """Get tool definitions filtered by role permissions."""
        if not self._tools:
            return None

        all_defs = self._tools.get_definitions()
        filtered = [
            d for d in all_defs
            if self._is_tool_allowed(d.get("function", {}).get("name", ""))
        ]
        return filtered if filtered else None

    async def observe(self, msg: TeamMessage) -> None:
        """Save a message to this role's session as context.

        All messages (from users and other bots) are saved so each role
        sees the full conversation when building LLM context.
        """
        session = self._sessions.get_or_create(self._session_key(msg.chat_id))
        sender = msg.source_role or msg.sender_name
        session.add_message("context", f"[{sender}]: {msg.content}")
        self._sessions.save(session)

    async def respond(self, msg: TeamMessage) -> str | None:
        """Generate a response using the role's persona, with tool support.

        Safety checks:
        1. User allowlist — only allowed users can trigger tool-using responses
        2. Tool permissions — per-role allowed/denied tool lists
        3. Sensitive tools blocked by default if no user allowlist configured
        """
        user_allowed = self._is_user_allowed(msg.sender_id)

        session = self._sessions.get_or_create(self._session_key(msg.chat_id))
        history = session.get_history(max_messages=self._history_limit)

        system_prompt = self._build_system_prompt()

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": msg.content},
        ]

        model = self._role_config.model or self._provider.default_model
        temperature = self._role_config.temperature or 0.3
        max_tokens = self._role_config.max_tokens or 4096

        # Only provide tools if user is allowed
        tool_defs = self._get_filtered_tool_defs() if user_allowed else None

        try:
            # Tool-calling loop
            for _round in range(_MAX_TOOL_ROUNDS):
                llm_response = await self._provider.chat(
                    messages=messages,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    tools=tool_defs,
                )

                # If no tool calls, we have a text response
                if not llm_response.tool_calls:
                    content = llm_response.content
                    if content:
                        session.add_message("user", msg.content)
                        session.add_message("assistant", content)
                        self._sessions.save(session)
                    return content

                # Process tool calls
                messages.append({
                    "role": "assistant",
                    "content": llm_response.content or None,
                    "tool_calls": llm_response.tool_calls,
                })

                for tc in llm_response.tool_calls:
                    tool_name = tc.get("function", {}).get("name", "")
                    tool_args = tc.get("function", {}).get("arguments", {})
                    tool_id = tc.get("id", "")

                    # Parse args if string
                    if isinstance(tool_args, str):
                        try:
                            tool_args = json.loads(tool_args)
                        except json.JSONDecodeError:
                            tool_args = {}

                    # Safety: double-check tool permission
                    if not self._is_tool_allowed(tool_name):
                        result = f"Tool '{tool_name}' is not permitted for role '{self._role}'."
                        logger.warning("TeamAgent[{}] blocked tool: {}", self._role, tool_name)
                    elif self._tools and self._tools.has(tool_name):
                        logger.debug("TeamAgent[{}] calling tool: {}({})", self._role, tool_name, list(tool_args.keys()))
                        result = await self._tools.execute(tool_name, tool_args)
                    else:
                        result = f"Tool '{tool_name}' not available."

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": str(result)[:4000],
                    })

            # Exhausted rounds — final call without tools to force text
            llm_response = await self._provider.chat(
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            content = llm_response.content
            if content:
                session.add_message("user", msg.content)
                session.add_message("assistant", content)
                self._sessions.save(session)
            return content

        except Exception as e:
            logger.error("TeamRoleAgent[{}] LLM call failed: {}", self._role, e)
            return None

    def _build_system_prompt(self) -> str:
        """Build system prompt with role persona and team context."""
        base = self._context.build_system_prompt()

        # List available tools for the LLM
        tool_hint = ""
        if self._tools:
            all_names = [t.name for t in self._tools._tools.values()]
            allowed_names = [n for n in all_names if self._is_tool_allowed(n)]
            nmem_tools = [n for n in allowed_names if n.startswith("nmem_")]
            other_tools = [n for n in allowed_names if not n.startswith("nmem_")]

            parts = []
            if nmem_tools:
                parts.append(f"Memory: {', '.join(nmem_tools)}")
            if other_tools:
                parts.append(f"Other: {', '.join(other_tools)}")
            if parts:
                tool_hint = (
                    "\n\n### Available Tools\n"
                    + "\n".join(f"- {p}" for p in parts)
                    + "\nUse nmem_recall to search your memory before answering when relevant.\n"
                )

        role_section = f"""

## Your Role in the Team

You are the **{self._role_config.display_name or self._role}** {self._role_config.icon or ''}.
{self._role_config.description or ''}

### Persona
{self._role_config.persona or 'You are a helpful assistant.'}

### Your Strengths
{', '.join(self._role_config.strengths) if self._role_config.strengths else 'general'}
{tool_hint}
### Team Behavior Rules
- You are ONE member of a team of AI assistants sharing a Telegram group.
- Other team members may also respond to the same message — be concise and stay in your lane.
- Only speak when you have genuine expertise to contribute.
- Do NOT repeat what another team member already said.
- Keep responses focused and brief — this is a group chat, not a solo conversation.
- Use your role's communication style from your persona.
- Format using Markdown (**bold**, `code`, ```code blocks```). No markdown tables.
"""
        return base + role_section
