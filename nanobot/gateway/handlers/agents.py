"""Agent handlers: list, identity, files (list/get/set), tools catalog."""

from __future__ import annotations

import logging
from typing import Any

from nanobot.gateway.connection import ClientConnection
from nanobot.gateway.context import GatewayContext
from nanobot.gateway.protocol import GatewayError

logger = logging.getLogger(__name__)


async def handle_agents_list(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Scan workspace agents/ directory."""
    agents_dir = ctx.config.workspace_path / "agents"
    agents: list[dict[str, Any]] = []

    # Default agent
    agents.append({
        "id": "default",
        "name": "NanoBot",
        "workspace": str(ctx.config.workspace_path),
    })

    if agents_dir.exists():
        for d in agents_dir.iterdir():
            if d.is_dir():
                agents.append({
                    "id": d.name,
                    "name": d.name,
                    "workspace": str(d),
                })

    return {"agents": agents}


async def handle_agent_identity_get(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Read IDENTITY.md or SOUL.md from workspace."""
    workspace = ctx.config.workspace_path
    session_key = params.get("sessionKey")

    # Try IDENTITY.md first, then SOUL.md
    for name in ("IDENTITY.md", "SOUL.md"):
        path = workspace / name
        if path.exists():
            return {
                "name": "NanoBot",
                "identity": path.read_text(encoding="utf-8", errors="replace"),
                "source": name,
            }

    return {"name": "NanoBot", "identity": None, "source": None}


async def handle_agents_files_list(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """List files in agent workspace directory."""
    agent_id = params.get("agentId", "default")
    workspace = ctx.config.workspace_path

    if agent_id != "default":
        base = (ctx.config.workspace_path / "agents").resolve()
        workspace = (base / agent_id).resolve()
        if not workspace.is_relative_to(base):
            raise GatewayError("FORBIDDEN", "invalid agentId")

    if not workspace.exists():
        return {"files": []}

    files: list[dict[str, Any]] = []
    for f in sorted(workspace.iterdir()):
        if f.is_file() and not f.name.startswith("."):
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "modified": f.stat().st_mtime,
            })

    return {"files": files}


async def handle_agents_files_get(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Read a file from agent workspace."""
    agent_id = params.get("agentId", "default")
    name = params.get("name")
    if not name:
        raise GatewayError("INVALID_PARAMS", "name required")

    workspace = ctx.config.workspace_path
    if agent_id != "default":
        workspace = workspace / "agents" / agent_id

    path = (workspace / name).resolve()
    # Path traversal protection
    if not path.is_relative_to(workspace.resolve()):
        raise GatewayError("FORBIDDEN", "path traversal not allowed")

    if not path.exists():
        raise GatewayError("NOT_FOUND", f"file {name} not found")

    return {"name": name, "content": path.read_text(encoding="utf-8", errors="replace")}


async def handle_agents_files_set(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Write a file to agent workspace."""
    agent_id = params.get("agentId", "default")
    name = params.get("name")
    content = params.get("content")
    if not name or content is None:
        raise GatewayError("INVALID_PARAMS", "name and content required")

    workspace = ctx.config.workspace_path
    if agent_id != "default":
        workspace = workspace / "agents" / agent_id

    path = (workspace / name).resolve()
    if not path.is_relative_to(workspace.resolve()):
        raise GatewayError("FORBIDDEN", "path traversal not allowed")

    workspace.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    return {"ok": True}


async def handle_tools_catalog(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Get tool definitions from the agent's tool registry."""
    tools: list[dict[str, Any]] = []

    if hasattr(ctx.agent, "tools") and hasattr(ctx.agent.tools, "get_definitions"):
        definitions = ctx.agent.tools.get_definitions()
        for defn in definitions:
            if isinstance(defn, dict):
                tools.append(defn)
            elif hasattr(defn, "to_dict"):
                tools.append(defn.to_dict())
            else:
                tools.append({"name": str(defn)})

    return {"tools": tools}


async def handle_subagent_config_get(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Return subagent config with effective roles (builtin defaults merged with user overrides)."""
    cfg = ctx.config.agents.subagent
    base = cfg.model_dump(by_alias=True)

    # Replace raw roles with effective roles (merged builtin + user overrides)
    effective = cfg.get_effective_roles()
    base["roles"] = {
        role_id: role_cfg.model_dump(by_alias=True)
        for role_id, role_cfg in effective.items()
    }
    return base


async def handle_subagent_tasks_list(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """List running and recently completed subagent tasks."""
    if hasattr(ctx.agent, "subagent_manager") and ctx.agent.subagent_manager:
        return ctx.agent.subagent_manager.get_tasks_info()
    return {"running": [], "completed": [], "runningCount": 0}


ROUTES = {
    "agents.list": handle_agents_list,
    "agent.identity.get": handle_agent_identity_get,
    "agents.files.list": handle_agents_files_list,
    "agents.files.get": handle_agents_files_get,
    "agents.files.set": handle_agents_files_set,
    "tools.catalog": handle_tools_catalog,
    "subagent.config.get": handle_subagent_config_get,
    "subagent.tasks.list": handle_subagent_tasks_list,
}
