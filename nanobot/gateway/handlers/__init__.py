"""Collect all handler ROUTES dicts into a single mapping."""

from __future__ import annotations

from typing import Any


def collect_routes() -> dict[str, Any]:
    """Import every handler module and merge their ROUTES dicts."""
    from . import (
        ai_gateway,
        agents,
        channels,
        chat,
        config,
        cron,
        devices,
        exec_approvals,
        nodes,
        sessions,
        skills,
        system,
    )

    merged: dict[str, Any] = {}
    for module in (
        system,
        chat,
        sessions,
        config,
        cron,
        agents,
        channels,
        skills,
        devices,
        nodes,
        exec_approvals,
        ai_gateway,
    ):
        merged.update(module.ROUTES)
    return merged
