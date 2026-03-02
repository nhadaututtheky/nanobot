"""Tool profiles: coarse security levels for tool access control."""

from __future__ import annotations

from typing import Final

# 4 levels — from most restricted to full access.
# Each level includes all tools from the previous level.
PROFILES: Final[dict[str, frozenset[str]]] = {
    "minimal": frozenset({
        "read_file", "list_dir", "web_search", "web_fetch",
    }),
    "coding": frozenset({
        "read_file", "list_dir", "web_search", "web_fetch",
        "write_file", "edit_file", "exec",
    }),
    "messaging": frozenset({
        "read_file", "list_dir", "web_search", "web_fetch",
        "write_file", "edit_file", "exec",
        "message",
    }),
    "full": frozenset(),  # empty = all tools allowed
}

# Map legacy role names → profile for backward compat
ROLE_PROFILE: Final[dict[str, str]] = {
    "researcher": "minimal",
    "coder": "coding",
    "reviewer": "minimal",
    "general": "full",
}


def get_allowed_tools(
    profile: str | None = None,
    role: str | None = None,
    explicit_tools: list[str] | None = None,
) -> frozenset[str]:
    """Resolve the set of allowed tool names.

    Priority: explicit_tools > profile > role mapping > full access.
    Returns empty frozenset for "all tools allowed".
    """
    if explicit_tools:
        return frozenset(explicit_tools)

    if profile and profile in PROFILES:
        return PROFILES[profile]

    if role:
        mapped = ROLE_PROFILE.get(role)
        if mapped:
            return PROFILES[mapped]

    return frozenset()  # no restrictions
