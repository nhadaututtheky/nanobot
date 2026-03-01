"""Skills handlers: status, update, install, search, uninstall, read."""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

from nanobot.gateway.connection import ClientConnection
from nanobot.gateway.context import GatewayContext
from nanobot.gateway.protocol import GatewayError

logger = logging.getLogger(__name__)

# Patterns for input validation
_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_.-]{1,100}$")
_SAFE_SLUG = re.compile(r"^[a-zA-Z0-9_@/.:-]{1,200}$")

# ---------------------------------------------------------------------------
# Builtin skills directory (mirrors SkillsLoader)
# ---------------------------------------------------------------------------
BUILTIN_SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


def _parse_frontmatter(content: str) -> dict[str, str]:
    """Parse simple YAML frontmatter from SKILL.md content."""
    import re

    if not content.startswith("---"):
        return {}
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    metadata: dict[str, str] = {}
    for line in match.group(1).split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip().strip("\"'")
    return metadata


def _scan_skills(workspace: Path) -> list[dict[str, Any]]:
    """Scan both workspace and builtin skill directories."""
    skills: list[dict[str, Any]] = []
    seen: set[str] = set()

    workspace_skills = workspace / "skills"
    sources: list[tuple[Path, str]] = [
        (workspace_skills, "workspace"),
        (BUILTIN_SKILLS_DIR, "builtin"),
    ]

    for skills_dir, source in sources:
        if not skills_dir.exists():
            continue
        for d in sorted(skills_dir.iterdir()):
            if not d.is_dir() or d.name in seen:
                continue
            seen.add(d.name)

            skill_file = d / "SKILL.md"
            skill_info: dict[str, Any] = {
                "key": d.name,
                "name": d.name,
                "source": source,
                "installed": True,
            }

            # Parse SKILL.md frontmatter for metadata
            if skill_file.exists():
                try:
                    content = skill_file.read_text(encoding="utf-8")
                    meta = _parse_frontmatter(content)
                    if meta.get("description"):
                        skill_info["description"] = meta["description"]
                    if meta.get("emoji"):
                        skill_info["emoji"] = meta["emoji"]
                    if meta.get("always"):
                        skill_info["always"] = meta["always"].lower() in ("true", "1", "yes")
                except Exception:
                    pass

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

            # Check availability (bins/env from metadata)
            skill_info["available"] = True
            if skill_file.exists():
                try:
                    content = skill_file.read_text(encoding="utf-8")
                    meta = _parse_frontmatter(content)
                    nanobot_meta_raw = meta.get("metadata", "")
                    if nanobot_meta_raw:
                        nanobot_meta = json.loads(nanobot_meta_raw)
                        nb = nanobot_meta.get("nanobot", nanobot_meta.get("openclaw", {}))
                        requires = nb.get("requires", {})
                        import os

                        for b in requires.get("bins", []):
                            if not shutil.which(b):
                                skill_info["available"] = False
                                break
                        for env in requires.get("env", []):
                            if not os.environ.get(env):
                                skill_info["available"] = False
                                break
                except Exception:
                    pass

            skills.append(skill_info)

    return skills


async def handle_skills_status(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Scan skills/ directories and check their status."""
    workspace = ctx.config.workspace_path
    skills = _scan_skills(workspace)
    return {"skills": skills}


async def handle_skills_update(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Update a skill's config/state."""
    skill_key = params.get("skillKey")
    if not skill_key:
        raise GatewayError("INVALID_PARAMS", "skillKey required")

    if not _SAFE_NAME.match(skill_key):
        raise GatewayError("INVALID_PARAMS", "invalid skill key")

    workspace = ctx.config.workspace_path
    skill_dir = (workspace / "skills" / skill_key).resolve()
    base = (workspace / "skills").resolve()
    if not skill_dir.is_relative_to(base):
        raise GatewayError("FORBIDDEN", "path traversal not allowed")
    if not skill_dir.exists():
        raise GatewayError("NOT_FOUND", f"skill {skill_key} not found")

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
    if not _SAFE_NAME.match(name):
        raise GatewayError("INVALID_PARAMS", "invalid skill name")

    timeout_ms = min(params.get("timeoutMs", 60000), 120_000)  # cap at 2 min
    workspace = ctx.config.workspace_path
    skill_dir = (workspace / "skills" / name).resolve()
    base = (workspace / "skills").resolve()
    if not skill_dir.is_relative_to(base):
        raise GatewayError("FORBIDDEN", "path traversal not allowed")

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


async def handle_skills_search(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Search ClawHub marketplace for skills."""
    import asyncio

    query = params.get("query", "").strip()
    if not query:
        raise GatewayError("INVALID_PARAMS", "query required")
    if len(query) > 200:
        raise GatewayError("INVALID_PARAMS", "query too long")

    limit = min(params.get("limit", 20), 50)
    workspace = ctx.config.workspace_path

    proc = await asyncio.create_subprocess_exec(
        "npx", "--yes", "clawhub@latest", "search", query,
        "--limit", str(limit), "--json",
        "--workdir", str(workspace),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError:
        proc.kill()
        raise GatewayError("TIMEOUT", "search timed out")

    if proc.returncode != 0:
        err = stderr.decode(errors="replace") if stderr else "unknown error"
        logger.warning("ClawHub search failed: %s", err)
        raise GatewayError("SEARCH_FAILED", f"ClawHub search failed: {err[:200]}")

    try:
        results = json.loads(stdout.decode(errors="replace")) if stdout else []
    except json.JSONDecodeError:
        results = []

    return {"results": results}


async def handle_skills_marketplace_install(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Install a skill from ClawHub marketplace."""
    import asyncio

    slug = params.get("slug", "").strip()
    if not slug:
        raise GatewayError("INVALID_PARAMS", "slug required")
    if not _SAFE_SLUG.match(slug):
        raise GatewayError("INVALID_PARAMS", "invalid slug format")

    workspace = ctx.config.workspace_path

    proc = await asyncio.create_subprocess_exec(
        "npx", "--yes", "clawhub@latest", "install", slug,
        "--workdir", str(workspace),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    except asyncio.TimeoutError:
        proc.kill()
        raise GatewayError("TIMEOUT", "marketplace install timed out")

    if proc.returncode != 0:
        err = stderr.decode(errors="replace") if stderr else "unknown error"
        raise GatewayError("INSTALL_FAILED", f"install failed: {err[:200]}")

    # Extract skill name from slug (last segment)
    name = slug.rsplit("/", 1)[-1] if "/" in slug else slug

    return {"ok": True, "name": name}


async def handle_skills_uninstall(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Uninstall a workspace skill (delete its directory)."""
    name = params.get("name", "").strip()
    if not name:
        raise GatewayError("INVALID_PARAMS", "name required")

    workspace = ctx.config.workspace_path
    skill_dir = (workspace / "skills" / name).resolve()

    # Path traversal protection
    base = (workspace / "skills").resolve()
    if not skill_dir.is_relative_to(base):
        raise GatewayError("FORBIDDEN", "path traversal not allowed")

    if not skill_dir.exists():
        raise GatewayError("NOT_FOUND", f"skill {name} not found")

    # Only allow removing workspace skills, not builtin
    builtin_dir = BUILTIN_SKILLS_DIR / name
    if builtin_dir.exists() and not (workspace / "skills" / name).exists():
        raise GatewayError("FORBIDDEN", "cannot uninstall builtin skills")

    shutil.rmtree(skill_dir)
    return {"ok": True}


async def handle_skills_read(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """Read the full content of a skill's SKILL.md."""
    name = params.get("name", "").strip()
    if not name:
        raise GatewayError("INVALID_PARAMS", "name required")

    workspace = ctx.config.workspace_path

    # Check workspace first, then builtin
    for skills_dir in [workspace / "skills", BUILTIN_SKILLS_DIR]:
        skill_file = skills_dir / name / "SKILL.md"
        if skill_file.exists():
            # Path traversal protection
            resolved = skill_file.resolve()
            base = skills_dir.resolve()
            if not resolved.is_relative_to(base):
                raise GatewayError("FORBIDDEN", "path traversal not allowed")
            return {"content": skill_file.read_text(encoding="utf-8")}

    raise GatewayError("NOT_FOUND", f"skill {name} not found")


ROUTES = {
    "skills.status": handle_skills_status,
    "skills.update": handle_skills_update,
    "skills.install": handle_skills_install,
    "skills.search": handle_skills_search,
    "skills.marketplace-install": handle_skills_marketplace_install,
    "skills.uninstall": handle_skills_uninstall,
    "skills.read": handle_skills_read,
}
