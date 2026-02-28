"""
Claude CLI Provider — uses Claude Code CLI subprocess for LLM calls.

For users with Claude subscription (no API key). Spawns `claude --print`
as a subprocess, collects NDJSON output, translates to NanoBot's LLMResponse.

The CLI is used as a "dumb pipe" text-generation backend.
NanoBot's agent loop handles tool execution — tool definitions are injected
into the system prompt so Claude emits parseable ```tool_call blocks.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest


# ═══ CLI Helpers ═══

def _get_cli_path() -> str | None:
    """Resolve Claude CLI binary. Windows: prefer cli.js for pipe reliability."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        candidates = [
            Path(appdata) / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "cli.js",
            Path.home() / ".bun" / "install" / "global" / "node_modules" / "@anthropic-ai" / "claude-code" / "cli.js",
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        if shutil.which("claude"):
            return "claude"
        return None
    return shutil.which("claude")


def _build_clean_env(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    """Build subprocess env: strip CLAUDE_CODE_* vars, then apply extras.

    Extras are applied first, THEN security-critical vars are stripped,
    so MCP env vars cannot re-inject CLAUDE_CODE_* vars.
    """
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    # Always strip AFTER merging extras to prevent re-injection
    to_remove = [k for k in env if k.startswith("CLAUDE_CODE_") or k.startswith("CLAUDECODE")]
    for k in to_remove:
        del env[k]
    return env


# ═══ Tool Call Parsing ═══

TOOL_CALL_PATTERN = re.compile(r"```tool_call\s*\n(.*?)\n```", re.DOTALL)

TOOL_PROTOCOL_TEMPLATE = """## Available Tools

You have access to the following tools. To call a tool, include a fenced \
code block with the language tag `tool_call` containing a JSON object with \
keys: id (unique string like call_1, call_2...), name, arguments.

Example:
```tool_call
{{"id": "call_1", "name": "read_file", "arguments": {{"path": "/tmp/x.py"}}}}
```

You may call multiple tools in one response (each in its own block). \
After tool results are provided, continue your response.

{tool_defs}"""


# ═══ Provider ═══

class ClaudeCLIProvider(LLMProvider):
    """
    LLM provider that spawns Claude Code CLI for each chat() call.

    Uses --print (one-shot mode) with --output-format stream-json.
    Parses NDJSON stream to extract assistant text and tool call blocks.
    """

    MODEL_MAP = {
        "claude-cli/opus": "opus",
        "claude-cli/sonnet": "sonnet",
        "claude-cli/haiku": "haiku",
    }

    def __init__(
        self,
        default_model: str = "claude-cli/sonnet",
        project_dir: str | None = None,
        permission_mode: str = "bypassPermissions",
        timeout: float = 120.0,
        mcp_servers: dict | None = None,
    ):
        super().__init__(api_key=None, api_base=None)
        self.default_model = default_model
        self.project_dir = project_dir or str(Path.home())
        self.permission_mode = permission_mode
        self.timeout = timeout
        self.mcp_servers = mcp_servers or {}
        self._cli_path: str | None = None

    def _ensure_cli(self) -> str:
        """Find and cache CLI path. Raises RuntimeError if not found."""
        if self._cli_path is None:
            self._cli_path = _get_cli_path()
        if self._cli_path is None:
            raise RuntimeError(
                "Claude Code CLI not found. Install: npm install -g @anthropic-ai/claude-code"
            )
        return self._cli_path

    def _resolve_cli_model(self, model: str) -> str:
        """Convert NanoBot model name to CLI model flag."""
        if model in self.MODEL_MAP:
            return self.MODEL_MAP[model]
        if model.startswith("claude-cli/"):
            return model.split("/", 1)[1]
        return model

    def get_default_model(self) -> str:
        return self.default_model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Send messages to Claude CLI and return parsed response.

        Note: max_tokens and temperature are accepted for interface compatibility
        but not forwarded to the CLI (Claude CLI does not expose these controls).
        """
        messages = self._sanitize_empty_content(messages)
        model = model or self.default_model
        cli_model = self._resolve_cli_model(model)
        cli_path = self._ensure_cli()

        system_prompt, user_prompt = self._build_prompt(messages, tools)
        args = self._build_cli_args(cli_path, cli_model)

        # Collect MCP env vars to inject into subprocess
        mcp_env: dict[str, str] = {}
        for _name, cfg in self.mcp_servers.items():
            if hasattr(cfg, "env") and cfg.env:
                mcp_env.update(cfg.env)

        env = _build_clean_env(extra_env=mcp_env)

        logger.debug("[CLAUDE-CLI] Spawning: model={}, tools={}, prompt_len={}",
                     cli_model, len(tools or []), len(user_prompt))

        try:
            return await asyncio.wait_for(
                self._run_cli(args, env, tools is not None,
                              system_prompt=system_prompt, user_prompt=user_prompt),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("[CLAUDE-CLI] Timed out after {}s", self.timeout)
            return LLMResponse(
                content=f"Claude CLI timed out after {self.timeout}s",
                finish_reason="error",
            )
        except Exception as e:
            logger.error("[CLAUDE-CLI] Error: {}", e)
            return LLMResponse(
                content=f"Claude CLI error: {e}",
                finish_reason="error",
            )

    # ═══ Prompt Building ═══

    def _build_prompt(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> tuple[str, str]:
        """Convert OpenAI-format messages + tools into (system_prompt, user_prompt)."""
        system_parts: list[str] = []
        conversation_parts: list[str] = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            # Handle content blocks (list format)
            if isinstance(content, list):
                text_parts = [
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                content = "\n".join(text_parts)

            if role == "system":
                system_parts.append(content)
            elif role == "user":
                conversation_parts.append(f"[User]\n{content}")
            elif role == "assistant":
                conversation_parts.append(f"[Assistant]\n{content}")
                # Include prior tool calls for context (use json.dumps for safety)
                for tc in msg.get("tool_calls", []) or []:
                    fn = tc.get("function", {})
                    block = json.dumps({
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "arguments": fn.get("arguments", {}),
                    })
                    conversation_parts.append(f"```tool_call\n{block}\n```")
            elif role == "tool":
                tool_id = msg.get("tool_call_id", "")
                tool_name = msg.get("name", "")
                conversation_parts.append(
                    f"[Tool Result: {tool_name} (id={tool_id})]\n{content}"
                )

        # Inject tool-calling protocol into system prompt
        if tools:
            tool_protocol = self._build_tool_protocol(tools)
            system_parts.append(tool_protocol)

        return "\n\n".join(system_parts), "\n\n".join(conversation_parts)

    @staticmethod
    def _build_tool_protocol(tools: list[dict[str, Any]]) -> str:
        """Build tool-calling instruction block for the system prompt."""
        tool_defs_parts: list[str] = []
        for tool in tools:
            fn = tool.get("function", tool)
            name = fn.get("name", "")
            desc = fn.get("description", "")
            params = json.dumps(fn.get("parameters", {}), indent=2)
            tool_defs_parts.append(f"### {name}\n{desc}\nParameters:\n```json\n{params}\n```")

        return TOOL_PROTOCOL_TEMPLATE.format(tool_defs="\n\n".join(tool_defs_parts))

    def _parse_tool_calls(self, text: str) -> tuple[str, list[ToolCallRequest]]:
        """Extract ```tool_call blocks from response text."""
        tool_calls: list[ToolCallRequest] = []
        matches = list(TOOL_CALL_PATTERN.finditer(text))

        for match in matches:
            try:
                data = json.loads(match.group(1).strip())
                tool_calls.append(ToolCallRequest(
                    id=data.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                    name=data["name"],
                    arguments=data.get("arguments", {}),
                ))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("[CLAUDE-CLI] Failed to parse tool_call block: {}", e)

        clean_text = TOOL_CALL_PATTERN.sub("", text).strip() if matches else text
        return clean_text, tool_calls

    # ═══ CLI Execution ═══

    VALID_PERMISSION_MODES = {"bypassPermissions", "default", "acceptEdits", "plan"}

    def _build_cli_args(self, cli_path: str, model: str) -> list[str]:
        """Build subprocess args for claude CLI."""
        base: list[str] = []
        if sys.platform == "win32" and cli_path.endswith(".js"):
            node = shutil.which("node") or shutil.which("node.exe")
            if not node:
                raise RuntimeError("node.js not found in PATH")
            base = [node, cli_path]
        else:
            base = [cli_path]

        if self.permission_mode not in self.VALID_PERMISSION_MODES:
            raise ValueError(f"Invalid permission_mode: {self.permission_mode!r}")

        return [
            *base,
            "--print",
            "--model", model,
            "--permission-mode", self.permission_mode,
        ]

    async def _run_cli(
        self, args: list[str], env: dict[str, str], has_tools: bool,
        system_prompt: str = "", user_prompt: str = "",
    ) -> LLMResponse:
        """Spawn CLI process, collect output, return LLMResponse.

        Pipes prompt via stdin using create_subprocess_exec (not shell)
        to prevent command injection. Kills subprocess on cancellation.
        """
        if system_prompt:
            full_prompt = f"<system>\n{system_prompt}\n</system>\n\n{user_prompt}"
        else:
            full_prompt = user_prompt

        prompt_bytes = full_prompt.encode("utf-8")

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.project_dir,
            env=env,
        )

        try:
            raw_stdout, raw_stderr = await proc.communicate(input=prompt_bytes)
        except asyncio.CancelledError:
            # Timeout or external cancellation — kill subprocess to avoid leak
            proc.kill()
            await proc.wait()
            raise

        if raw_stderr:
            stderr_text = raw_stderr.decode("utf-8", errors="replace").strip()
            if stderr_text:
                logger.debug("[CLAUDE-CLI] stderr: {}", stderr_text[:300])

        output = raw_stdout.decode("utf-8", errors="replace") if raw_stdout else ""

        if not output.strip():
            logger.warning("[CLAUDE-CLI] Empty output (exit={})", proc.returncode)
            return LLMResponse(content=None, finish_reason="error")

        if proc.returncode != 0:
            logger.warning("[CLAUDE-CLI] Non-zero exit: {}", proc.returncode)

        logger.info("[CLAUDE-CLI] Got response: {} bytes, exit={}", len(output), proc.returncode)
        return self._parse_output(output, has_tools)

    def _parse_output(self, output: str, has_tools: bool) -> LLMResponse:
        """Parse CLI output — handles both NDJSON and plain text."""
        text_parts: list[str] = []
        pre_ndjson_parts: list[str] = []
        cost_usd = 0.0
        num_turns = 0
        is_ndjson = False

        for line in output.split("\n"):
            stripped = line.strip()
            if not stripped or not stripped.startswith("{"):
                # Plain text line — might be non-NDJSON output (startup noise)
                if stripped and not is_ndjson:
                    pre_ndjson_parts.append(stripped)
                continue

            try:
                msg = json.loads(stripped)
                if not is_ndjson:
                    is_ndjson = True
                    # Discard pre-NDJSON noise (e.g. Node.js warnings)
                    if pre_ndjson_parts:
                        logger.debug("[CLAUDE-CLI] Discarded pre-NDJSON lines: {}",
                                     pre_ndjson_parts[:3])
                    pre_ndjson_parts.clear()
            except json.JSONDecodeError:
                if stripped and not is_ndjson:
                    pre_ndjson_parts.append(stripped)
                continue

            msg_type = msg.get("type", "")

            if msg_type == "assistant":
                for block in msg.get("message", {}).get("content", []):
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))

            elif msg_type == "result":
                cost_usd = msg.get("total_cost_usd", 0.0)
                num_turns = msg.get("num_turns", 0)
                if msg.get("is_error"):
                    logger.error("[CLAUDE-CLI] CLI result error: {}", msg.get("result", "")[:300])
                    return LLMResponse(
                        content=f"Claude CLI error: {msg.get('result', 'unknown')}",
                        finish_reason="error",
                        usage={"total_cost_usd": cost_usd, "num_turns": num_turns},
                    )
                if not text_parts and msg.get("result"):
                    text_parts.append(msg["result"])

        # If no NDJSON was found, use raw output as plain text
        full_text = "\n".join(text_parts).strip() if is_ndjson else output.strip()
        return self._finalize_response(full_text, cost_usd, num_turns, has_tools)

    def _finalize_response(
        self, full_text: str, cost_usd: float, num_turns: int, has_tools: bool
    ) -> LLMResponse:
        """Build final LLMResponse from parsed text."""
        logger.info(
            "[CLAUDE-CLI] Done: response_len={}, cost=${:.4f}, turns={}",
            len(full_text), cost_usd, num_turns,
        )

        tool_calls: list[ToolCallRequest] = []
        content = full_text
        if has_tools and "```tool_call" in full_text:
            content, tool_calls = self._parse_tool_calls(full_text)

        finish_reason = "tool_calls" if tool_calls else "stop"

        return LLMResponse(
            content=content or None,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage={"total_cost_usd": cost_usd, "num_turns": num_turns},
        )
