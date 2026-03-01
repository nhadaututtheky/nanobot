"""Subagent manager for background task execution."""

import asyncio
import json
import uuid
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.web import WebFetchTool, WebSearchTool
from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider

# Preset maps: human-friendly labels → raw values
THINKING_STYLE: dict[str, float] = {"creative": 1.0, "balanced": 0.7, "precise": 0.3}
PERSISTENCE: dict[str, int] = {"quick": 5, "normal": 15, "thorough": 30}
RESPONSE_LENGTH: dict[str, int] = {"brief": 2048, "normal": 4096, "detailed": 8192}

# Legacy role tools (used as fallback when no effective role config exists)
ROLE_TOOLS: dict[str, set[str]] = {
    "researcher": {"read_file", "list_dir", "web_search", "web_fetch"},
    "coder": {"read_file", "write_file", "edit_file", "list_dir", "exec", "web_search", "web_fetch"},
    "reviewer": {"read_file", "list_dir"},
    "general": set(),  # empty means all registered tools
}


class SubagentManager:
    """Manages background subagent execution."""

    def __init__(
        self,
        provider: LLMProvider,
        workspace: Path,
        bus: MessageBus,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        brave_api_key: str | None = None,
        exec_config: "ExecToolConfig | None" = None,  # noqa: F821
        restrict_to_workspace: bool = False,
        mcp_servers: dict | None = None,
        subagent_config: "SubAgentConfig | None" = None,  # noqa: F821
    ):
        from nanobot.config.schema import ExecToolConfig, SubAgentConfig
        self.provider = provider
        self.workspace = workspace
        self.bus = bus
        self.model = model or provider.get_default_model()
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        self.restrict_to_workspace = restrict_to_workspace
        self.mcp_servers = mcp_servers or {}
        self.subagent_config = subagent_config or SubAgentConfig()
        self._running_tasks: dict[str, asyncio.Task[None]] = {}
        self._session_tasks: dict[str, set[str]] = {}  # session_key -> {task_id, ...}
        self._completed_tasks: list[dict[str, Any]] = []  # recent completed tasks for monitoring

    async def spawn(
        self,
        task: str,
        label: str | None = None,
        origin_channel: str = "cli",
        origin_chat_id: str = "direct",
        session_key: str | None = None,
        role: str = "general",
        context: str | None = None,
        max_iterations: int = 15,
    ) -> str:
        """Spawn a subagent to execute a task in the background."""
        if not self.subagent_config.enabled:
            return "Subagents are disabled in configuration."

        task_id = str(uuid.uuid4())[:8]
        display_label = label or task[:30] + ("..." if len(task) > 30 else "")
        origin = {"channel": origin_channel, "chat_id": origin_chat_id}

        # Apply per-role config overrides (presets take priority)
        effective_roles = self.subagent_config.get_effective_roles()
        role_cfg = effective_roles.get(role)
        effective_iters = max_iterations
        if role_cfg:
            if role_cfg.persistence and role_cfg.persistence in PERSISTENCE:
                effective_iters = PERSISTENCE[role_cfg.persistence]
            elif role_cfg.max_iterations:
                effective_iters = role_cfg.max_iterations
        elif self.subagent_config.default_max_iterations:
            effective_iters = self.subagent_config.default_max_iterations
        clamped_iters = max(1, min(effective_iters, 40))

        bg_task = asyncio.create_task(
            self._run_subagent(task_id, task, display_label, origin, role, context, clamped_iters)
        )
        self._running_tasks[task_id] = bg_task
        if session_key:
            self._session_tasks.setdefault(session_key, set()).add(task_id)

        def _cleanup(_: asyncio.Task) -> None:
            self._running_tasks.pop(task_id, None)
            if session_key and (ids := self._session_tasks.get(session_key)):
                ids.discard(task_id)
                if not ids:
                    del self._session_tasks[session_key]

        bg_task.add_done_callback(_cleanup)

        logger.info("Spawned subagent [{}] (role={}): {}", task_id, role, display_label)
        return f"Subagent [{display_label}] started (id: {task_id}, role: {role}). I'll notify you when it completes."

    def _build_tools(self, role: str) -> ToolRegistry:
        """Build tool registry for a subagent, filtered by role."""
        tools = ToolRegistry()
        allowed_dir = self.workspace if self.restrict_to_workspace else None

        # Register all candidate tools
        all_tools: list = [
            ReadFileTool(workspace=self.workspace, allowed_dir=allowed_dir),
            WriteFileTool(workspace=self.workspace, allowed_dir=allowed_dir),
            EditFileTool(workspace=self.workspace, allowed_dir=allowed_dir),
            ListDirTool(workspace=self.workspace, allowed_dir=allowed_dir),
            ExecTool(
                working_dir=str(self.workspace),
                timeout=self.exec_config.timeout,
                restrict_to_workspace=self.restrict_to_workspace,
                path_append=self.exec_config.path_append,
            ),
            WebSearchTool(api_key=self.brave_api_key),
            WebFetchTool(),
        ]

        # Check effective role config for tools list first, fall back to legacy ROLE_TOOLS
        effective_roles = self.subagent_config.get_effective_roles()
        eff_role = effective_roles.get(role)
        if eff_role and eff_role.tools:
            allowed = set(eff_role.tools)
        else:
            allowed = ROLE_TOOLS.get(role, set())

        for tool in all_tools:
            if not allowed or tool.name in allowed:
                tools.register(tool)

        return tools

    async def _connect_mcp_for_subagent(
        self, tools: ToolRegistry, stack: AsyncExitStack, role: str,
    ) -> None:
        """Connect MCP servers and register tools for a subagent."""
        if not self.mcp_servers:
            return
        from nanobot.agent.tools.mcp import connect_mcp_servers

        try:
            await connect_mcp_servers(self.mcp_servers, tools, stack)

            # If role has tool restrictions, remove MCP tools not in the allowed set
            # (but MCP tools like nmem_* are always allowed for researcher/reviewer roles)
            effective_roles = self.subagent_config.get_effective_roles()
            eff_role = effective_roles.get(role)
            allowed = set(eff_role.tools) if (eff_role and eff_role.tools) else ROLE_TOOLS.get(role, set())
            if allowed:
                # MCP tools (e.g. nmem_*) are allowed for roles that include read-only access
                # We keep all MCP tools — they are specifically why we connect MCP servers
                pass
        except Exception as e:
            logger.warning("Subagent MCP connection failed (continuing without): {}", e)

    async def _run_subagent(
        self,
        task_id: str,
        task: str,
        label: str,
        origin: dict[str, str],
        role: str = "general",
        context: str | None = None,
        max_iterations: int = 15,
    ) -> None:
        """Execute the subagent task and announce the result."""
        logger.info("Subagent [{}] starting task (role={}): {}", task_id, role, label)

        mcp_stack = AsyncExitStack()
        await mcp_stack.__aenter__()

        try:
            tools = self._build_tools(role)

            # Connect MCP servers for subagent (e.g. neural memory)
            await self._connect_mcp_for_subagent(tools, mcp_stack, role)

            # Resolve per-role model/temperature/max_tokens (presets take priority)
            effective_roles = self.subagent_config.get_effective_roles()
            role_cfg = effective_roles.get(role)
            effective_model = self.model
            effective_temp = self.temperature
            effective_max_tokens = self.max_tokens
            if role_cfg:
                if role_cfg.model:
                    effective_model = role_cfg.model
                # Preset resolution: human-friendly label → raw value
                if role_cfg.thinking_style and role_cfg.thinking_style in THINKING_STYLE:
                    effective_temp = THINKING_STYLE[role_cfg.thinking_style]
                elif role_cfg.temperature:
                    effective_temp = role_cfg.temperature
                if role_cfg.response_length and role_cfg.response_length in RESPONSE_LENGTH:
                    effective_max_tokens = RESPONSE_LENGTH[role_cfg.response_length]
                elif role_cfg.max_tokens:
                    effective_max_tokens = role_cfg.max_tokens

            # Build messages with subagent-specific prompt
            system_prompt = self._build_subagent_prompt(task, role, context)
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task},
            ]

            # Run agent loop (limited iterations)
            iteration = 0
            final_result: str | None = None

            while iteration < max_iterations:
                iteration += 1

                response = await self.provider.chat(
                    messages=messages,
                    tools=tools.get_definitions(),
                    model=effective_model,
                    temperature=effective_temp,
                    max_tokens=effective_max_tokens,
                )

                if response.has_tool_calls:
                    # Add assistant message with tool calls
                    tool_call_dicts = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                            },
                        }
                        for tc in response.tool_calls
                    ]
                    messages.append({
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": tool_call_dicts,
                    })

                    # Execute tools
                    for tool_call in response.tool_calls:
                        args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                        logger.debug("Subagent [{}] executing: {} with arguments: {}", task_id, tool_call.name, args_str)
                        result = await tools.execute(tool_call.name, tool_call.arguments)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.name,
                            "content": result,
                        })
                else:
                    final_result = response.content
                    break

            if final_result is None:
                final_result = "Task completed but no final response was generated."

            logger.info("Subagent [{}] completed successfully", task_id)
            self._record_completed(task_id, label, role, "ok")
            await self._announce_result(task_id, label, task, final_result, origin, "ok")

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            logger.error("Subagent [{}] failed: {}", task_id, e)
            self._record_completed(task_id, label, role, "error")
            await self._announce_result(task_id, label, task, error_msg, origin, "error")
        finally:
            try:
                await mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass

    async def _announce_result(
        self,
        task_id: str,
        label: str,
        task: str,
        result: str,
        origin: dict[str, str],
        status: str,
    ) -> None:
        """Announce the subagent result to the main agent via the message bus."""
        status_text = "completed successfully" if status == "ok" else "failed"

        announce_content = f"""[Subagent '{label}' {status_text}]

Task: {task}

Result:
{result}

Summarize this naturally for the user. Keep it brief (1-2 sentences). Do not mention technical details like "subagent" or task IDs."""

        # Inject as system message to trigger main agent
        msg = InboundMessage(
            channel="system",
            sender_id="subagent",
            chat_id=f"{origin['channel']}:{origin['chat_id']}",
            content=announce_content,
        )

        await self.bus.publish_inbound(msg)
        logger.debug("Subagent [{}] announced result to {}:{}", task_id, origin['channel'], origin['chat_id'])

    def _build_subagent_prompt(self, task: str, role: str = "general", context: str | None = None) -> str:
        """Build a focused system prompt for the subagent."""
        import time as _time
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = _time.strftime("%Z") or "UTC"

        # Resolve effective role config for display_name, description, persona
        effective_roles = self.subagent_config.get_effective_roles()
        role_cfg = effective_roles.get(role)

        # Fallback descriptions for unknown roles
        fallback_descriptions = {
            "researcher": "You are a **researcher** subagent. Focus on gathering information, reading files, searching the web, and querying neural memory. Do NOT modify files.",
            "coder": "You are a **coder** subagent. Focus on writing, editing, and executing code to complete the task.",
            "reviewer": "You are a **reviewer** subagent. Focus on reading and analyzing code or content. Do NOT modify files.",
            "general": "You are a general-purpose subagent. Use all available tools to complete the task.",
        }

        if role_cfg and (role_cfg.display_name or role_cfg.description):
            display = role_cfg.display_name or role
            desc = role_cfg.description or ""
            role_desc = f"You are a **{display}** subagent. {desc}"
        else:
            role_desc = fallback_descriptions.get(role, fallback_descriptions["general"])

        # Persona injection
        persona_block = ""
        if role_cfg and role_cfg.persona:
            persona_block = f"\n## Persona\n{role_cfg.persona}\n"

        context_block = f"\n## Context from Parent Agent\n{context}\n" if context else ""

        return f"""# Subagent ({role})

## Current Time
{now} ({tz})

## Role
{role_desc}
{persona_block}
## Rules
1. Stay focused - complete only the assigned task, nothing else
2. Your final response will be reported back to the main agent
3. Do not initiate conversations or take on side tasks
4. Be concise but informative in your findings
{context_block}
## What You Cannot Do
- Send messages directly to users (no message tool available)
- Spawn other subagents
- Access the main agent's conversation history

## Workspace
Your workspace is at: {self.workspace}
Skills are available at: {self.workspace}/skills/ (read SKILL.md files as needed)

When you have completed the task, provide a clear summary of your findings or actions."""

    def _record_completed(self, task_id: str, label: str, role: str, status: str) -> None:
        """Record a completed task for monitoring (keep last 50)."""
        from datetime import datetime

        self._completed_tasks.append({
            "id": task_id,
            "label": label,
            "role": role,
            "status": status,
            "completedAt": datetime.now().isoformat(),
        })
        if len(self._completed_tasks) > 50:
            self._completed_tasks = self._completed_tasks[-50:]

    def get_tasks_info(self) -> dict[str, Any]:
        """Get info about running and recently completed tasks."""
        running = [
            {"id": tid, "running": not t.done()}
            for tid, t in self._running_tasks.items()
        ]
        return {
            "running": running,
            "completed": list(self._completed_tasks),
            "runningCount": self.get_running_count(),
        }

    async def cancel_by_session(self, session_key: str) -> int:
        """Cancel all subagents for the given session. Returns count cancelled."""
        tasks = [self._running_tasks[tid] for tid in self._session_tasks.get(session_key, [])
                 if tid in self._running_tasks and not self._running_tasks[tid].done()]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return len(tasks)

    def get_running_count(self) -> int:
        """Return the number of currently running subagents."""
        return len(self._running_tasks)
