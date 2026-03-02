"""Agent loop: the core processing engine."""

from __future__ import annotations

import asyncio
import json
import re
from contextlib import AsyncExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from loguru import logger

from nanobot.agent.context import ContextBuilder
from nanobot.agent.memory import MemoryStore
from nanobot.agent.subagent import SubagentManager
from nanobot.agent.tools.cron import CronTool
from nanobot.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.spawn import SpawnTool
from nanobot.agent.tools.web import WebFetchTool, WebSearchTool
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.session.manager import Session, SessionManager

if TYPE_CHECKING:
    from nanobot.config.schema import ChannelsConfig, Config, ExecToolConfig
    from nanobot.cron.service import CronService


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """

    _TOOL_RESULT_MAX_CHARS = 500

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 40,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        memory_window: int = 100,
        brave_api_key: str | None = None,
        exec_config: ExecToolConfig | None = None,
        cron_service: CronService | None = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        mcp_servers: dict | None = None,
        channels_config: ChannelsConfig | None = None,
        config: Config | None = None,
    ):
        from nanobot.config.schema import ExecToolConfig

        self.bus = bus
        self.channels_config = channels_config
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.memory_window = memory_window
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace
        self._config = config

        self.context = ContextBuilder(workspace)
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            brave_api_key=brave_api_key,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
            mcp_servers=mcp_servers,
            subagent_config=config.agents.subagent if config else None,
        )

        # Orchestrator components (None until _init_orchestrator is called)
        self.orchestrator_store = None
        self.orchestrator_executor = None
        self.orchestrator_decomposer = None
        self.orchestrator_router = None

        self._running = False
        self._mcp_servers = mcp_servers or {}
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._mcp_connecting = False
        self.on_mcp_ready: Any = None  # Callback: async fn(ToolRegistry)
        self._consolidating: set[str] = set()  # Session keys with consolidation in progress
        self._consolidation_tasks: set[asyncio.Task] = set()  # Strong refs to in-flight tasks
        self._consolidation_locks: dict[str, asyncio.Lock] = {}
        self._active_tasks: dict[str, set[asyncio.Task]] = {}  # session_key -> tasks
        self._session_locks: dict[str, asyncio.Lock] = {}  # Per-session processing locks
        self._register_default_tools()
        self._init_orchestrator()

    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        for cls in (ReadFileTool, WriteFileTool, EditFileTool, ListDirTool):
            self.tools.register(cls(workspace=self.workspace, allowed_dir=allowed_dir))
        self.tools.register(
            ExecTool(
                working_dir=str(self.workspace),
                timeout=self.exec_config.timeout,
                restrict_to_workspace=self.restrict_to_workspace,
                path_append=self.exec_config.path_append,
            )
        )
        self.tools.register(WebSearchTool(api_key=self.brave_api_key))
        self.tools.register(WebFetchTool())
        self.tools.register(MessageTool(send_callback=self.bus.publish_outbound))
        self.tools.register(SpawnTool(manager=self.subagents))
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))

    def _make_orchestrator_provider(self) -> LLMProvider:
        """Create a LiteLLM provider for orchestrator, regardless of main provider type.

        The orchestrator routes to many different models (Opus, Sonnet, Haiku,
        GPT-4.1, etc.) so it MUST use LiteLLMProvider which supports arbitrary
        model routing.
        """
        from nanobot.providers.litellm_provider import LiteLLMProvider

        # Already LiteLLM? Reuse it (inject config for per-model routing).
        if isinstance(self.provider, LiteLLMProvider):
            if not self.provider._config:
                self.provider._config = self._config
            return self.provider

        # Build a new LiteLLM provider from config
        model = self._config.agents.defaults.model
        p = self._config.get_provider(model)
        provider_name = self._config.get_provider_name(model)

        api_key = p.api_key if p else None
        extra_headers = p.extra_headers if p else None

        return LiteLLMProvider(
            api_key=api_key,
            api_base=self._config.get_api_base(model),
            default_model=model,
            extra_headers=extra_headers,
            provider_name=provider_name,
            config=self._config,
        )

    def _init_orchestrator(self) -> None:
        """Initialise orchestrator components if config is available and enabled."""
        if not self._config:
            return
        if not self._config.agents.orchestrator.enabled:
            return

        from nanobot.agent.tools.orchestrate import OrchestrateTool
        from nanobot.orchestrator.decomposer import GoalDecomposer
        from nanobot.orchestrator.executor import GraphExecutor
        from nanobot.orchestrator.router import ModelRouter
        from nanobot.orchestrator.store import GraphStore
        from nanobot.orchestrator.telegram_sender import TelegramOrchestratorSender

        try:
            orch_provider = self._make_orchestrator_provider()
            self.orchestrator_router = ModelRouter(self._config)
            self.orchestrator_store = GraphStore(self.workspace)
            self.orchestrator_decomposer = GoalDecomposer(
                provider=orch_provider,
                router=self.orchestrator_router,
            )

            # Telegram multi-bot sender (only active if telegram_group_id is set)
            tg_sender = TelegramOrchestratorSender(self._config)

            self.orchestrator_executor = GraphExecutor(
                provider=orch_provider,
                workspace=self.workspace,
                bus=self.bus,
                store=self.orchestrator_store,
                config=self._config,
                telegram_sender=tg_sender if tg_sender.enabled else None,
            )

            self.tools.register(
                OrchestrateTool(
                    decomposer=self.orchestrator_decomposer,
                    executor=self.orchestrator_executor,
                    store=self.orchestrator_store,
                )
            )
            logger.info(
                "Orchestrator initialised ({} models available)",
                len(self.orchestrator_router.get_models_info()),
            )
        except Exception as e:
            logger.warning("Orchestrator init failed (continuing without): {}", e)

    def reload_config(self, config: Config) -> None:
        """Hot-reload config into running components (called after config save)."""
        self._config = config

        # Reload sub-agent config so per-role model overrides take effect
        self.subagents.subagent_config = config.agents.subagent

        # Rebuild orchestrator router with fresh model registry
        if self.orchestrator_router is not None:
            from nanobot.orchestrator.router import ModelRouter
            try:
                self.orchestrator_router = ModelRouter(config)
                # Update decomposer's router reference
                if self.orchestrator_decomposer is not None:
                    self.orchestrator_decomposer._router = self.orchestrator_router
                # Update executor's config reference
                if self.orchestrator_executor is not None:
                    self.orchestrator_executor._config = config
                logger.info("Config hot-reloaded ({} models)", len(self.orchestrator_router.get_models_info()))
            except Exception as e:
                logger.warning("Orchestrator router reload failed: {}", e)

    def get_orchestrator_context(self) -> dict[str, Any] | None:
        """Return orchestrator components dict for GatewayContext, or None."""
        if not all(
            [
                self.orchestrator_store,
                self.orchestrator_executor,
                self.orchestrator_decomposer,
                self.orchestrator_router,
            ]
        ):
            return None
        return {
            "store": self.orchestrator_store,
            "executor": self.orchestrator_executor,
            "decomposer": self.orchestrator_decomposer,
            "router": self.orchestrator_router,
        }

    async def _connect_mcp(self) -> None:
        """Connect to configured MCP servers (one-time, lazy).

        Always connects MCP servers directly so tools are registered in NanoBot's
        tool registry — including when using Claude CLI provider (which uses --print
        one-shot mode and does not handle MCP natively).
        """
        if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
            return
        self._mcp_connecting = True
        from nanobot.agent.tools.mcp import connect_mcp_servers

        try:
            self._mcp_stack = AsyncExitStack()
            await self._mcp_stack.__aenter__()
            await connect_mcp_servers(self._mcp_servers, self.tools, self._mcp_stack)
            self._mcp_connected = True
        except BaseException as e:
            logger.error("Failed to connect MCP servers (will retry next message): {}", e)
            if self._mcp_stack:
                try:
                    await self._mcp_stack.aclose()
                except BaseException:
                    pass
                self._mcp_stack = None
        finally:
            self._mcp_connecting = False

    def _set_tool_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        """Update context for all tools that need routing info."""
        for name in ("message", "spawn", "cron", "orchestrate"):
            if tool := self.tools.get(name):
                if hasattr(tool, "set_context"):
                    tool.set_context(channel, chat_id, *([message_id] if name == "message" else []))

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        """Remove <think>…</think> blocks that some models embed in content."""
        if not text:
            return None
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip() or None

    @staticmethod
    def _tool_hint(tool_calls: list) -> str:
        """Format tool calls as concise hint, e.g. 'web_search("query")'."""

        def _fmt(tc):
            args = tc.arguments if isinstance(tc.arguments, dict) else {}
            val = next(iter(args.values()), None) if args else None
            if not isinstance(val, str):
                return tc.name
            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'

        return ", ".join(_fmt(tc) for tc in tool_calls)

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        on_progress: Callable[..., Awaitable[None]] | None = None,
    ) -> tuple[str | None, list[str], list[dict]]:
        """Run the agent iteration loop. Returns (final_content, tools_used, messages)."""
        messages = initial_messages
        iteration = 0
        final_content = None
        tools_used: list[str] = []

        while iteration < self.max_iterations:
            iteration += 1

            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            if response.has_tool_calls:
                if on_progress:
                    clean = self._strip_think(response.content)
                    if clean:
                        await on_progress(clean)
                    await on_progress(self._tool_hint(response.tool_calls), tool_hint=True)

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
                messages = self.context.add_assistant_message(
                    messages,
                    response.content,
                    tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )

                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info("Tool call: {}({})", tool_call.name, args_str[:200])
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                # Error responses (timeout, CLI crash) — log and surface to user
                if response.finish_reason == "error":
                    error_detail = (response.content or "unknown error")[:200]
                    logger.warning("LLM returned error response: {}", error_detail)
                    final_content = None  # Suppress raw error; fallback assigned downstream
                    break

                clean = self._strip_think(response.content)
                messages = self.context.add_assistant_message(
                    messages,
                    clean,
                    reasoning_content=response.reasoning_content,
                )
                final_content = clean
                break

        if final_content is None and iteration >= self.max_iterations:
            logger.warning("Max iterations ({}) reached", self.max_iterations)
            final_content = (
                f"I reached the maximum number of tool call iterations ({self.max_iterations}) "
                "without completing the task. You can try breaking the task into smaller steps."
            )

        return final_content, tools_used, messages

    async def run(self) -> None:
        """Run the agent loop, dispatching messages as tasks to stay responsive to /stop."""
        self._running = True
        try:
            await self._connect_mcp()
            if self._mcp_connected and self.on_mcp_ready:
                await self.on_mcp_ready(self.tools)
        except BaseException as e:
            logger.error("MCP connection failed at startup: {} — continuing without MCP", e)
        logger.info("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            # Observe-only messages: save to session history for context, skip agent
            if msg.metadata.get("_observe_only"):
                self._observe(msg)
                continue

            if msg.content.strip().lower() == "/stop":
                await self._handle_stop(msg)
            else:
                task = asyncio.create_task(self._dispatch(msg))
                self._active_tasks.setdefault(msg.session_key, set()).add(task)

                def _cleanup_task(t: asyncio.Task, k: str = msg.session_key) -> None:
                    tasks = self._active_tasks.get(k)
                    if tasks is not None:
                        tasks.discard(t)
                        if not tasks:
                            del self._active_tasks[k]

                task.add_done_callback(_cleanup_task)

    async def _handle_stop(self, msg: InboundMessage) -> None:
        """Cancel all active tasks and subagents for the session."""
        tasks = self._active_tasks.pop(msg.session_key, set())
        cancelled = sum(1 for t in tasks if not t.done() and t.cancel())
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        sub_cancelled = await self.subagents.cancel_by_session(msg.session_key)
        total = cancelled + sub_cancelled
        content = f"⏹ Stopped {total} task(s)." if total else "No active task to stop."
        await self.bus.publish_outbound(
            OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=content,
            )
        )

    def _get_session_lock(self, session_key: str) -> asyncio.Lock:
        """Get or create a per-session processing lock."""
        lock = self._session_locks.get(session_key)
        if lock is None:
            lock = asyncio.Lock()
            self._session_locks[session_key] = lock
        return lock

    async def _dispatch(self, msg: InboundMessage) -> None:
        """Process a message under a per-session lock (not global)."""
        lock = self._get_session_lock(msg.session_key)
        async with lock:
            try:
                response = await self._process_message(msg)
                if response is not None:
                    await self.bus.publish_outbound(response)
                elif msg.channel == "cli":
                    await self.bus.publish_outbound(
                        OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content="",
                            metadata=msg.metadata or {},
                        )
                    )
            except asyncio.CancelledError:
                logger.info("Task cancelled for session {}", msg.session_key)
                # Publish empty message so channels can stop typing indicators
                await self.bus.publish_outbound(
                    OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="Task was cancelled.",
                        metadata=msg.metadata or {},
                    )
                )
                raise
            except Exception:
                logger.exception("Error processing message for session {}", msg.session_key)
                # Always send an error response so channels can stop typing indicators
                await self.bus.publish_outbound(
                    OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="Sorry, I encountered an error processing your message."
                        if msg.channel == "cli"
                        else "Sorry, something went wrong. Please try again.",
                        metadata=msg.metadata or {},
                    )
                )

    async def close_mcp(self) -> None:
        """Close MCP connections."""
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass  # MCP SDK cancel scope cleanup is noisy but harmless
            self._mcp_stack = None

    def _observe(self, msg: InboundMessage) -> None:
        """Save an observed message to session history without agent processing.

        This gives the bot conversational context for group chats where it
        only responds when directly addressed.

        Messages are stored with role "context" (not "user") so the LLM
        treats them as background information rather than conversation turns
        it needs to respond to.
        """
        session = self.sessions.get_or_create(msg.session_key)
        session.add_message("context", msg.content)
        self.sessions.save(session)
        logger.debug("Observed message in {}: {}...", msg.session_key, msg.content[:60])

    def stop(self) -> None:
        """Stop the agent loop and clean up stale state."""
        self._running = False
        self._session_locks.clear()
        self._consolidation_locks.clear()
        logger.info("Agent loop stopping")

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> OutboundMessage | None:
        """Process a single inbound message and return the response."""
        # System messages: parse origin from chat_id ("channel:chat_id")
        if msg.channel == "system":
            channel, chat_id = (
                msg.chat_id.split(":", 1) if ":" in msg.chat_id else ("cli", msg.chat_id)
            )
            logger.info("Processing system message from {}", msg.sender_id)
            key = f"{channel}:{chat_id}"
            session = self.sessions.get_or_create(key)
            self._set_tool_context(channel, chat_id, msg.metadata.get("message_id"))
            history = session.get_history(max_messages=self.memory_window)
            messages = self.context.build_messages(
                history=history,
                current_message=msg.content,
                channel=channel,
                chat_id=chat_id,
            )
            final_content, _, all_msgs = await self._run_agent_loop(messages)
            self._save_turn(session, all_msgs, 1 + len(history))
            self.sessions.save(session)
            return OutboundMessage(
                channel=channel,
                chat_id=chat_id,
                content=final_content or "Background task completed.",
            )

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)

        key = session_key or msg.session_key
        session = self.sessions.get_or_create(key)

        # Slash commands
        cmd = msg.content.strip().lower()
        if cmd == "/new":
            lock = self._consolidation_locks.setdefault(session.key, asyncio.Lock())
            self._consolidating.add(session.key)
            try:
                async with lock:
                    snapshot = session.messages[session.last_consolidated :]
                    if snapshot:
                        temp = Session(key=session.key)
                        temp.messages = list(snapshot)
                        if not await self._consolidate_memory(temp, archive_all=True):
                            return OutboundMessage(
                                channel=msg.channel,
                                chat_id=msg.chat_id,
                                content="Memory archival failed, session not cleared. Please try again.",
                            )
            except Exception:
                logger.exception("/new archival failed for {}", session.key)
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content="Memory archival failed, session not cleared. Please try again.",
                )
            finally:
                self._consolidating.discard(session.key)
                if not lock.locked():
                    self._consolidation_locks.pop(session.key, None)

            session.clear()
            self.sessions.save(session)
            self.sessions.invalidate(session.key)
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content="New session started."
            )
        if cmd == "/help":
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content="🐈 nanobot commands:\n/new — Start a new conversation\n/stop — Stop the current task\n/help — Show available commands",
            )

        unconsolidated = len(session.messages) - session.last_consolidated
        if unconsolidated >= self.memory_window and session.key not in self._consolidating:
            self._consolidating.add(session.key)
            lock = self._consolidation_locks.setdefault(session.key, asyncio.Lock())

            async def _consolidate_and_unlock():
                try:
                    async with lock:
                        await self._consolidate_memory(session)
                finally:
                    self._consolidating.discard(session.key)
                    if not lock.locked():
                        self._consolidation_locks.pop(session.key, None)
                    _task = asyncio.current_task()
                    if _task is not None:
                        self._consolidation_tasks.discard(_task)

            _task = asyncio.create_task(_consolidate_and_unlock())
            self._consolidation_tasks.add(_task)

        self._set_tool_context(msg.channel, msg.chat_id, msg.metadata.get("message_id"))
        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool):
                message_tool.start_turn()

        # Per-channel history limit override (e.g. Telegram per-group config)
        effective_history_limit = (
            msg.metadata.get("history_limit", self.memory_window)
            if msg.metadata
            else self.memory_window
        )
        history = session.get_history(max_messages=effective_history_limit)
        initial_messages = self.context.build_messages(
            history=history,
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
        )

        # Per-channel system prompt override (e.g. Telegram per-group system_prompt)
        if msg.metadata and msg.metadata.get("system_prompt_override"):
            override = msg.metadata["system_prompt_override"]
            if initial_messages and initial_messages[0].get("role") == "system":
                initial_messages[0] = {
                    **initial_messages[0],
                    "content": initial_messages[0]["content"] + f"\n\n{override}",
                }

        async def _bus_progress(content: str, *, tool_hint: bool = False) -> None:
            meta = dict(msg.metadata or {})
            meta["_progress"] = True
            meta["_tool_hint"] = tool_hint
            await self.bus.publish_outbound(
                OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=content,
                    metadata=meta,
                )
            )

        final_content, _, all_msgs = await self._run_agent_loop(
            initial_messages,
            on_progress=on_progress or _bus_progress,
        )

        # If message tool already sent a response, don't send a duplicate or error
        message_already_sent = (
            (mt := self.tools.get("message"))
            and isinstance(mt, MessageTool)
            and mt._sent_in_turn
        )

        if final_content is None and not message_already_sent:
            # Always return a response so channels can stop typing indicators.
            # Returning None caused typing to run forever on Telegram/Discord/etc.
            final_content = (
                "LLM did not return a response. This may be a temporary issue — try again."
            )

        self._save_turn(session, all_msgs, 1 + len(history))
        self.sessions.save(session)

        if message_already_sent:
            return None

        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info("Response to {}:{}: {}", msg.channel, msg.sender_id, preview)
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            metadata=msg.metadata or {},
        )

    def _save_turn(self, session: Session, messages: list[dict], skip: int) -> None:
        """Save new-turn messages into session, truncating large tool results."""
        from datetime import datetime

        for m in messages[skip:]:
            entry = {k: v for k, v in m.items() if k != "reasoning_content"}
            role, content = entry.get("role"), entry.get("content")
            if (
                role == "tool"
                and isinstance(content, str)
                and len(content) > self._TOOL_RESULT_MAX_CHARS
            ):
                entry["content"] = content[: self._TOOL_RESULT_MAX_CHARS] + "\n... (truncated)"
            elif role == "user":
                if isinstance(content, str) and content.startswith(
                    ContextBuilder._RUNTIME_CONTEXT_TAG
                ):
                    continue
                if isinstance(content, list):
                    entry["content"] = [
                        {"type": "text", "text": "[image]"}
                        if (
                            c.get("type") == "image_url"
                            and c.get("image_url", {}).get("url", "").startswith("data:image/")
                        )
                        else c
                        for c in content
                    ]
            entry.setdefault("timestamp", datetime.now().isoformat())
            session.messages.append(entry)
        session.updated_at = datetime.now()

    async def _consolidate_memory(self, session, archive_all: bool = False) -> bool:
        """Delegate to MemoryStore.consolidate(). Returns True on success."""
        return await MemoryStore(self.workspace).consolidate(
            session,
            self.provider,
            self.model,
            archive_all=archive_all,
            memory_window=self.memory_window,
        )

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """Process a message directly (for CLI or cron usage)."""
        await self._connect_mcp()
        msg = InboundMessage(channel=channel, sender_id="user", chat_id=chat_id, content=content)
        response = await self._process_message(
            msg, session_key=session_key, on_progress=on_progress
        )
        return response.content if response else ""
