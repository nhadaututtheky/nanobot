"""Graph executor — runs a TaskGraph DAG with parallel execution."""

from __future__ import annotations

import asyncio
import json
import re
from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from loguru import logger

from nanobot.orchestrator.models import (
    GraphStatus,
    TaskGraph,
    TaskNode,
    TaskStatus,
)

_ARTIFACTS_RE = re.compile(r"<artifacts>\s*(.*?)\s*</artifacts>", re.DOTALL)
_MAX_OUTPUT_FILES = 20

if TYPE_CHECKING:
    from nanobot.bus.queue import MessageBus
    from nanobot.config.schema import Config
    from nanobot.orchestrator.store import GraphStore
    from nanobot.orchestrator.telegram_sender import TelegramOrchestratorSender
    from nanobot.providers.base import LLMProvider


def _extract_artifacts(result: str) -> tuple[str, list[str]]:
    """Parse ``<artifacts>path1\\npath2</artifacts>`` from LLM result.

    Returns ``(clean_result, [relative_paths])``.  Paths with ``..`` components
    or absolute paths are silently dropped (security).
    """
    match = _ARTIFACTS_RE.search(result)
    if not match:
        return result, []

    raw_lines = match.group(1).strip().splitlines()
    paths: list[str] = []
    for line in raw_lines:
        p = line.strip()
        if not p or p.startswith("#"):
            continue
        # Security: reject absolute paths and traversal
        if p.startswith("/") or p.startswith("\\") or ".." in p:
            logger.warning("Artifact path rejected (traversal): {}", p)
            continue
        paths.append(p)

    clean = _ARTIFACTS_RE.sub("", result).strip()
    return clean, paths[:_MAX_OUTPUT_FILES]


class GraphExecutor:
    """Execute a TaskGraph: run ready nodes in parallel, pass context downstream."""

    def __init__(
        self,
        provider: LLMProvider,
        workspace: Path,
        bus: MessageBus,
        store: GraphStore,
        config: Config,
        *,
        on_event: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        telegram_sender: TelegramOrchestratorSender | None = None,
    ) -> None:
        self._provider = provider
        self._workspace = workspace
        self._bus = bus
        self._store = store
        self._config = config
        self._on_event = on_event  # broadcast callback
        self._telegram = telegram_sender
        self._running_graphs: dict[str, asyncio.Task[None]] = {}

    async def execute(self, graph: TaskGraph) -> None:
        """Start graph execution as a background task."""
        if graph.id in self._running_graphs:
            logger.warning("Graph {} is already running", graph.id)
            return

        task = asyncio.create_task(self._run_graph(graph))
        self._running_graphs[graph.id] = task

        def _cleanup(_: asyncio.Task[None]) -> None:
            self._running_graphs.pop(graph.id, None)

        task.add_done_callback(_cleanup)

    async def cancel(self, graph_id: str) -> bool:
        """Cancel a running graph."""
        task = self._running_graphs.get(graph_id)
        if not task or task.done():
            return False
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        return True

    def is_running(self, graph_id: str) -> bool:
        t = self._running_graphs.get(graph_id)
        return t is not None and not t.done()

    # --- core execution loop ---

    async def _run_graph(self, graph: TaskGraph) -> None:
        """Main DAG execution loop."""
        graph.status = GraphStatus.RUNNING
        graph.started_at = datetime.now().isoformat()
        await self._save(graph)
        await self._emit("graph_started", graph)
        if self._telegram:
            await self._telegram.send_graph_started(graph)

        inflight: set[asyncio.Task[None]] = set()
        try:
            while True:
                ready = graph.get_ready_tasks()
                if not ready:
                    # Clean up finished tasks
                    inflight = {t for t in inflight if not t.done()}
                    if inflight:
                        # Wait for at least one running task to finish (event-driven)
                        _done, inflight = await asyncio.wait(
                            inflight,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        continue

                    pending = [n for n in graph.nodes if n.status == TaskStatus.PENDING]
                    if pending:
                        # Stuck — dependencies failed
                        for n in pending:
                            n.status = TaskStatus.SKIPPED
                            n.error = "Skipped: upstream dependency failed"
                        graph.status = GraphStatus.FAILED
                    else:
                        # All done
                        failed = [n for n in graph.nodes if n.status == TaskStatus.FAILED]
                        graph.status = GraphStatus.FAILED if failed else GraphStatus.COMPLETED
                    break

                # Launch ready nodes in parallel
                tasks = [asyncio.create_task(self._run_node(graph, node)) for node in ready]
                inflight.update(tasks)
                # Mark as queued immediately
                for node in ready:
                    node.status = TaskStatus.QUEUED
                await self._save(graph)

                # Wait for this wave to complete
                _done, inflight = await asyncio.wait(
                    inflight,
                    return_when=asyncio.ALL_COMPLETED,
                )

        except asyncio.CancelledError:
            logger.info("Graph {} cancelled", graph.id)
            for n in graph.nodes:
                if n.status in (TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING):
                    n.status = TaskStatus.CANCELLED
            graph.status = GraphStatus.CANCELLED
            raise
        finally:
            graph.completed_at = datetime.now().isoformat()
            await self._save(graph)
            await self._emit("graph_done", graph)
            await self._announce_result(graph)

    async def _run_node(self, graph: TaskGraph, node: TaskNode) -> None:
        """Execute a single task node using the subagent pattern."""
        node.status = TaskStatus.RUNNING
        node.started_at = datetime.now().isoformat()
        await self._save(graph)
        await self._emit("node_started", graph, node_id=node.id)
        if self._telegram:
            await self._telegram.send_node_started(graph, node)

        try:
            # Inject context from upstream dependencies
            self._inject_dependency_context(graph, node)

            # Build the prompt
            prompt = self._build_node_prompt(node)

            # Resolve model — use assigned_model or fall back to default.
            model = node.assigned_model or self._config.agents.defaults.model

            # Build messages
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": self._build_node_system_prompt(node)},
                {"role": "user", "content": prompt},
            ]

            # Build tools (reuse subagent patterns)
            tools = self._build_node_tools(node.worker_role)
            mcp_stack = AsyncExitStack()
            await mcp_stack.__aenter__()

            try:
                await self._connect_mcp_for_node(tools, mcp_stack, node.worker_role)

                # Agent loop
                timeout = self._config.agents.orchestrator.default_task_timeout_s
                result = await asyncio.wait_for(
                    self._agent_loop(messages, tools, model, node, graph),
                    timeout=timeout,
                )

                # Extract artifact file declarations from result
                clean_result, artifact_paths = _extract_artifacts(result or "")
                node.result = clean_result or result or ""
                node.output_summary = (clean_result or "")[:500]
                node.output_files = artifact_paths
                node.status = TaskStatus.COMPLETED
                node.progress = 1.0

            finally:
                try:
                    await mcp_stack.aclose()
                except (RuntimeError, BaseExceptionGroup):
                    pass

        except asyncio.TimeoutError:
            node.status = TaskStatus.FAILED
            node.error = (
                f"Task timed out after {self._config.agents.orchestrator.default_task_timeout_s}s"
            )
            logger.warning("Node {} timed out in graph {}", node.id, graph.id)
        except Exception as e:
            node.status = TaskStatus.FAILED
            node.error = str(e)[:500]
            logger.error("Node {} failed in graph {}: {}", node.id, graph.id, e)
        finally:
            node.completed_at = datetime.now().isoformat()
            await self._save(graph)
            await self._emit("node_done", graph, node_id=node.id)
            if self._telegram:
                await self._telegram.send_node_done(graph, node)

    async def _agent_loop(
        self,
        messages: list[dict[str, Any]],
        tools: Any,
        model: str,
        node: TaskNode,
        graph: TaskGraph,
    ) -> str:
        """Run the LLM agent loop for a node (mirrors SubagentManager pattern)."""
        from nanobot.agent.subagent import RESPONSE_LENGTH, THINKING_STYLE
        from nanobot.config.schema import SubAgentRoleConfig

        # Resolve per-role settings
        effective_roles = self._config.agents.subagent.get_effective_roles()
        role_cfg = effective_roles.get(node.worker_role, SubAgentRoleConfig())

        effective_temp = 0.7
        effective_max_tokens = 4096
        if role_cfg.thinking_style and role_cfg.thinking_style in THINKING_STYLE:
            effective_temp = THINKING_STYLE[role_cfg.thinking_style]
        elif role_cfg.temperature:
            effective_temp = role_cfg.temperature
        if role_cfg.response_length and role_cfg.response_length in RESPONSE_LENGTH:
            effective_max_tokens = RESPONSE_LENGTH[role_cfg.response_length]
        elif role_cfg.max_tokens:
            effective_max_tokens = role_cfg.max_tokens

        max_iterations = min(
            role_cfg.max_iterations or self._config.agents.subagent.default_max_iterations,
            40,
        )

        iteration = 0
        final_result: str | None = None

        while iteration < max_iterations:
            iteration += 1

            response = await self._provider.chat(
                messages=messages,
                tools=tools.get_definitions() if hasattr(tools, "get_definitions") else [],
                model=model,
                temperature=effective_temp,
                max_tokens=effective_max_tokens,
            )

            if response.has_tool_calls:
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
                messages.append(
                    {
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": tool_call_dicts,
                    }
                )

                for tool_call in response.tool_calls:
                    result = await tools.execute(tool_call.name, tool_call.arguments)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.name,
                            "content": result,
                        }
                    )

                # Update progress estimate
                node.progress = min(0.9, iteration / max_iterations)
                await self._save(graph)
                await self._emit("node_progress", graph, node_id=node.id)

                # Telegram progress (throttled inside sender)
                if self._telegram and response.tool_calls:
                    last_tc = response.tool_calls[-1]
                    last_result = messages[-1].get("content", "") if messages else ""
                    await self._telegram.send_node_progress(
                        graph,
                        node,
                        tool_name=last_tc.name,
                        tool_result_preview=last_result[:200] if last_result else "",
                        iteration=iteration,
                        max_iterations=max_iterations,
                    )
            else:
                final_result = response.content
                break

        return final_result or "Task completed but no final response was generated."

    # --- tool building (reuses SubagentManager patterns) ---

    def _build_node_tools(self, role: str) -> Any:
        """Build tool registry for a node, filtered by worker role."""
        from nanobot.agent.subagent import ROLE_TOOLS
        from nanobot.agent.tools.filesystem import (
            EditFileTool,
            ListDirTool,
            ReadFileTool,
            WriteFileTool,
        )
        from nanobot.agent.tools.registry import ToolRegistry
        from nanobot.agent.tools.shell import ExecTool
        from nanobot.agent.tools.web import WebFetchTool, WebSearchTool

        tools = ToolRegistry()
        allowed_dir = self._workspace if self._config.tools.restrict_to_workspace else None

        all_tools: list[Any] = [
            ReadFileTool(workspace=self._workspace, allowed_dir=allowed_dir),
            WriteFileTool(workspace=self._workspace, allowed_dir=allowed_dir),
            EditFileTool(workspace=self._workspace, allowed_dir=allowed_dir),
            ListDirTool(workspace=self._workspace, allowed_dir=allowed_dir),
            ExecTool(
                working_dir=str(self._workspace),
                timeout=self._config.tools.exec.timeout,
                restrict_to_workspace=self._config.tools.restrict_to_workspace,
                path_append=self._config.tools.exec.path_append,
            ),
            WebSearchTool(api_key=self._config.tools.web.search.api_key or None),
            WebFetchTool(),
        ]

        effective_roles = self._config.agents.subagent.get_effective_roles()
        eff_role = effective_roles.get(role)
        if eff_role and eff_role.tools:
            allowed = set(eff_role.tools)
        else:
            allowed = ROLE_TOOLS.get(role, set())

        for tool in all_tools:
            if not allowed or tool.name in allowed:
                tools.register(tool)

        return tools

    async def _connect_mcp_for_node(
        self,
        tools: Any,
        stack: AsyncExitStack,
        role: str,
    ) -> None:
        """Connect MCP servers for a node."""
        mcp_servers = self._config.tools.mcp_servers
        if not mcp_servers:
            return
        from nanobot.agent.tools.mcp import connect_mcp_servers

        try:
            await connect_mcp_servers(dict(mcp_servers), tools, stack)
        except BaseException as e:
            logger.warning("Node MCP connection failed (continuing without): {}", e)

    # --- prompt building ---

    def _build_node_system_prompt(self, node: TaskNode) -> str:
        """Build system prompt for a task node, including role persona."""
        import time as _time
        from datetime import datetime as dt

        now = dt.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = _time.strftime("%Z") or "UTC"

        # Resolve persona from role config
        effective_roles = self._config.agents.subagent.get_effective_roles()
        role_cfg = effective_roles.get(node.worker_role)

        role_desc = f"Your role: **{node.worker_role}**"
        if role_cfg and (role_cfg.display_name or role_cfg.description):
            display = role_cfg.display_name or node.worker_role
            desc = role_cfg.description or ""
            role_desc = f"Your role: **{display}** — {desc}"

        persona_block = ""
        if role_cfg and role_cfg.persona:
            persona_block = f"\n## Persona & Communication Style\n{role_cfg.persona}\n"

        return f"""# Orchestrator Task Node ({node.worker_role})

## Current Time
{now} ({tz})

## Role
You are an AI agent executing a subtask as part of a larger goal.
{role_desc}
Task capability: **{node.capability.value}**
{persona_block}
## Rules
1. Complete ONLY this specific task — nothing else.
2. Be thorough but concise in your output.
3. Your result will be passed to downstream tasks as context.
4. If you cannot complete the task, explain what went wrong.

## Workspace
{self._workspace}
"""

    def _build_node_prompt(self, node: TaskNode) -> str:
        """Build user prompt for a node, including injected context."""
        parts = [f"## Task: {node.label}", "", node.description]
        if node.input_context:
            parts.extend(["", "## Context from upstream tasks:", node.input_context])
        return "\n".join(parts)

    def _inject_dependency_context(self, graph: TaskGraph, node: TaskNode) -> None:
        """Inject output summaries and file paths from upstream dependencies."""
        dep_ids = graph.get_dependencies(node.id)
        if not dep_ids:
            return

        context_parts: list[str] = []
        all_files: list[str] = []
        for dep_id in dep_ids:
            dep_node = graph.get_node(dep_id)
            if not dep_node:
                continue
            if dep_node.output_summary:
                context_parts.append(
                    f"[{dep_node.label}] ({dep_node.capability.value}):\n{dep_node.output_summary}"
                )
            if dep_node.output_files:
                all_files.extend(dep_node.output_files)

        if context_parts:
            node.input_context = "\n\n---\n\n".join(context_parts)

        if all_files:
            node.input_files = all_files[:_MAX_OUTPUT_FILES]
            file_listing = "\n".join(f"  - {f}" for f in node.input_files)
            node.input_context += f"\n\n## Files from upstream tasks:\n{file_listing}"
            if len(all_files) > _MAX_OUTPUT_FILES:
                logger.warning(
                    "Node {} received {} files from upstream (capped at {})",
                    node.id,
                    len(all_files),
                    _MAX_OUTPUT_FILES,
                )

    # --- result announcement ---

    async def _announce_result(self, graph: TaskGraph) -> None:
        """Announce graph completion to the main agent via message bus."""
        from nanobot.bus.events import InboundMessage

        status_text = {
            GraphStatus.COMPLETED: "completed successfully",
            GraphStatus.FAILED: "completed with failures",
            GraphStatus.CANCELLED: "was cancelled",
        }.get(graph.status, str(graph.status.value))

        # Build summary
        node_summaries: list[str] = []
        for n in graph.nodes:
            status_icon = {
                TaskStatus.COMPLETED: "OK",
                TaskStatus.FAILED: "FAIL",
                TaskStatus.SKIPPED: "SKIP",
                TaskStatus.CANCELLED: "CANCEL",
            }.get(n.status, n.status.value)
            summary = (
                n.output_summary[:200]
                if n.output_summary
                else (n.error[:200] if n.error else "no output")
            )
            node_summaries.append(f"  [{status_icon}] {n.label}: {summary}")

        content = f"""[Orchestrator '{graph.goal[:60]}' {status_text}]

Tasks ({len(graph.nodes)}):
{chr(10).join(node_summaries)}

Summarize the orchestrated results naturally for the user. \
Highlight key findings and any failures. Keep it concise."""

        msg = InboundMessage(
            channel="system",
            sender_id="orchestrator",
            chat_id=f"{graph.origin_channel}:{graph.origin_chat_id}",
            content=content,
        )
        await self._bus.publish_inbound(msg)

        # Send Telegram summary to result channel
        if self._telegram:
            await self._telegram.send_graph_summary(graph)

    # --- helpers ---

    async def _save(self, graph: TaskGraph) -> None:
        """Persist graph state."""
        await self._store.save(graph)

    async def _emit(
        self,
        event_type: str,
        graph: TaskGraph,
        *,
        node_id: str = "",
    ) -> None:
        """Emit a broadcast event if callback is set."""
        if not self._on_event:
            return
        payload: dict[str, Any] = {
            "type": event_type,
            "graphId": graph.id,
            "status": graph.status.value,
            "progress": graph.progress,
        }
        if node_id:
            node = graph.get_node(node_id)
            if node:
                payload["node"] = node.to_dict()
        try:
            await self._on_event("orchestrator", payload)
        except Exception as e:
            logger.debug("Orchestrator event emit failed: {}", e)

    async def retry_failed(self, graph: TaskGraph) -> None:
        """Reset failed/skipped nodes to pending and re-execute."""
        for n in graph.nodes:
            if n.status in (TaskStatus.FAILED, TaskStatus.SKIPPED):
                n.status = TaskStatus.PENDING
                n.error = ""
                n.result = ""
                n.output_summary = ""
                n.progress = 0.0
                n.started_at = ""
                n.completed_at = ""
        graph.status = GraphStatus.DRAFT
        graph.completed_at = ""
        await self._save(graph)
        await self.execute(graph)
