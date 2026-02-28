"""Skills handlers: status, update, install."""

from __future__ import annotations

import logging
from typing import Any

from nanobot.gateway.connection import ClientConnection
from nanobot.gateway.context import GatewayContext
from nanobot.gateway.protocol import GatewayError

logger = logging.getLogger(__name__)


async def handle_skills_status(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Scan skills/ directories and check their status."""
    import json

    workspace = ctx.config.workspace_path
    skills_dir = workspace / "skills"

    skills: list[dict[str, Any]] = []
    if skills_dir.exists():
        for d in sorted(skills_dir.iterdir()):
            if d.is_dir():
                skill_info: dict[str, Any] = {
                    "key": d.name,
                    "name": d.name,
                    "installed": True,
                }
                # Check for config
                config_path = d / "config.json"
                if config_path.exists():
                    try:
                        skill_info["config"] = json.loads(config_path.read_text(encoding="utf-8"))
                    except Exception:
                        pass

                # Check for requirements
                req_path = d / "requirements.txt"
                skill_info["hasRequirements"] = req_path.exists()

                skills.append(skill_info)

    return {"skills": skills}


async def handle_skills_update(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Update a skill's config/state."""
    skill_key = params.get("skillKey")
    if not skill_key:
        raise GatewayError("INVALID_PARAMS", "skillKey required")

    workspace = ctx.config.workspace_path
    skill_dir = workspace / "skills" / skill_key
    if not skill_dir.exists():
        raise GatewayError("NOT_FOUND", f"skill {skill_key} not found")

    import json
    config_path = skill_dir / "config.json"
    config: dict[str, Any] = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    if "enabled" in params:
        config["enabled"] = params["enabled"]
    if "apiKey" in params:
        config["apiKey"] = params["apiKey"]

    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return {"ok": True}


async def handle_skills_install(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Install a skill by running its install command."""
    import asyncio

    name = params.get("name")
    if not name:
        raise GatewayError("INVALID_PARAMS", "name required")

    timeout_ms = min(params.get("timeoutMs", 60000), 120_000)  # cap at 2 min
    workspace = ctx.config.workspace_path
    skill_dir = workspace / "skills" / name

    if not skill_dir.exists():
        raise GatewayError("NOT_FOUND", f"skill {name} not found")

    install_script = skill_dir / "install.sh"
    if not install_script.exists():
        # Try requirements.txt instead
        req_path = skill_dir / "requirements.txt"
        if req_path.exists():
            proc = await asyncio.create_subprocess_exec(
                "pip", "install", "-r", str(req_path),
                cwd=str(skill_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_ms / 1000)
            except asyncio.TimeoutError:
                proc.kill()
                raise GatewayError("TIMEOUT", "install timed out")

            return {
                "ok": proc.returncode == 0,
                "stdout": stdout.decode(errors="replace") if stdout else "",
                "stderr": stderr.decode(errors="replace") if stderr else "",
            }

        raise GatewayError("NOT_FOUND", "no install script or requirements.txt found")

    proc = await asyncio.create_subprocess_exec(
        "bash", str(install_script),
        cwd=str(skill_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_ms / 1000)
    except asyncio.TimeoutError:
        proc.kill()
        raise GatewayError("TIMEOUT", "install timed out")

    return {
        "ok": proc.returncode == 0,
        "stdout": stdout.decode(errors="replace") if stdout else "",
        "stderr": stderr.decode(errors="replace") if stderr else "",
    }


ROUTES = {
    "skills.status": handle_skills_status,
    "skills.update": handle_skills_update,
    "skills.install": handle_skills_install,
}
