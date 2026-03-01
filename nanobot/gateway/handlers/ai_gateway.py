"""AI Gateway (CLIProxyAPI) service management handlers."""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any

from nanobot.gateway.connection import ClientConnection
from nanobot.gateway.context import GatewayContext
from nanobot.gateway.protocol import GatewayError

logger = logging.getLogger(__name__)

# Module-level process reference (singleton — one AI Gateway per NanoBot instance)
_process: asyncio.subprocess.Process | None = None
_log_task: asyncio.Task[None] | None = None


def _resolve_binary(cfg_path: str) -> Path | None:
    """Find the AI Gateway binary from config or PATH."""
    if cfg_path:
        p = Path(cfg_path).expanduser()
        if p.is_file():
            return p
    # Try common locations
    for candidate in [
        Path.home() / ".nanobot" / "bin" / "cli-proxy-api.exe",
        Path.home() / ".nanobot" / "bin" / "cli-proxy-api",
    ]:
        if candidate.is_file():
            return candidate
    # Try system PATH
    found = shutil.which("cli-proxy-api")
    return Path(found) if found else None


def _resolve_config(cfg_path: str) -> Path:
    """Get config.yaml path, defaulting to ~/.cli-proxy-api/config.yaml."""
    if cfg_path:
        return Path(cfg_path).expanduser()
    return Path.home() / ".cli-proxy-api" / "config.yaml"


async def _stream_logs(proc: asyncio.subprocess.Process) -> None:
    """Read stderr from the AI Gateway process and log it."""
    if proc.stderr is None:
        return
    try:
        async for line in proc.stderr:
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                logger.info("[ai-gateway] %s", text)
    except Exception:
        pass


async def handle_ai_gateway_status(
    ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]
) -> Any:
    """Check AI Gateway service status."""
    global _process

    ai_cfg = ctx.config.gateway.ai_gateway
    binary = _resolve_binary(ai_cfg.binary_path)

    running = _process is not None and _process.returncode is None
    pid = _process.pid if running and _process else None

    return {
        "running": running,
        "pid": pid,
        "binaryFound": binary is not None,
        "binaryPath": str(binary) if binary else None,
        "managementUrl": ai_cfg.management_url,
        "proxyUrl": ai_cfg.proxy_url,
        "enabled": ai_cfg.enabled,
    }


async def handle_ai_gateway_start(
    ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]
) -> Any:
    """Start the AI Gateway (CLIProxyAPI) service."""
    global _process, _log_task

    # Already running?
    if _process is not None and _process.returncode is None:
        return {"ok": True, "pid": _process.pid, "alreadyRunning": True}

    ai_cfg = ctx.config.gateway.ai_gateway
    binary = _resolve_binary(ai_cfg.binary_path)
    if binary is None:
        raise GatewayError(
            "AI_GATEWAY_NOT_FOUND",
            "CLI Proxy API binary not found. Set gateway.aiGateway.binaryPath in config.",
        )

    config_path = _resolve_config(ai_cfg.config_path)
    cmd = [str(binary)]
    if config_path.is_file():
        cmd.extend(["-config", str(config_path)])

    logger.info("[ai-gateway] Starting: %s", " ".join(cmd))

    try:
        _process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(binary.parent),
        )
    except Exception as exc:
        raise GatewayError("AI_GATEWAY_START_FAILED", str(exc))

    # Stream logs in background
    _log_task = asyncio.create_task(_stream_logs(_process))

    # Wait briefly for process to start (or fail immediately)
    await asyncio.sleep(0.5)
    if _process.returncode is not None:
        stderr_bytes = await _process.stderr.read() if _process.stderr else b""
        stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
        _process = None
        raise GatewayError(
            "AI_GATEWAY_EXITED",
            f"Process exited immediately: {stderr_text or 'unknown error'}",
        )

    logger.info("[ai-gateway] Started with PID %d", _process.pid)
    return {"ok": True, "pid": _process.pid, "alreadyRunning": False}


async def handle_ai_gateway_stop(
    ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]
) -> Any:
    """Stop the AI Gateway service."""
    global _process, _log_task

    if _process is None or _process.returncode is not None:
        _process = None
        return {"ok": True, "wasRunning": False}

    pid = _process.pid
    logger.info("[ai-gateway] Stopping PID %d", pid)

    try:
        _process.terminate()
        try:
            await asyncio.wait_for(_process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            _process.kill()
            await _process.wait()
    except ProcessLookupError:
        pass

    if _log_task and not _log_task.done():
        _log_task.cancel()
    _log_task = None
    _process = None

    logger.info("[ai-gateway] Stopped PID %d", pid)
    return {"ok": True, "wasRunning": True, "pid": pid}


ROUTES = {
    "ai-gateway.status": handle_ai_gateway_status,
    "ai-gateway.start": handle_ai_gateway_start,
    "ai-gateway.stop": handle_ai_gateway_stop,
}
