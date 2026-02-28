"""Cron handlers: status, list, add, update, run, remove, runs."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from nanobot.cron.types import CronPayload, CronSchedule
from nanobot.gateway.connection import ClientConnection
from nanobot.gateway.context import GatewayContext
from nanobot.gateway.protocol import GatewayError

logger = logging.getLogger(__name__)


def _job_to_dict(job: Any) -> dict[str, Any]:
    """Convert a CronJob dataclass to a JSON-safe dict."""
    d = asdict(job)
    return d


async def handle_cron_status(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    return ctx.cron.status()


async def handle_cron_list(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    include_disabled = params.get("includeDisabled", False)
    limit = params.get("limit", 100)
    offset = params.get("offset", 0)
    query = params.get("query")
    sort_by = params.get("sortBy", "created_at_ms")
    sort_dir = params.get("sortDir", "desc")

    jobs = ctx.cron.list_jobs(include_disabled=include_disabled)

    # Filter by query
    if query:
        q = query.lower()
        jobs = [j for j in jobs if q in j.name.lower() or q in j.payload.message.lower()]

    # Filter by enabled
    enabled_filter = params.get("enabled")
    if enabled_filter == "true":
        jobs = [j for j in jobs if j.enabled]
    elif enabled_filter == "false":
        jobs = [j for j in jobs if not j.enabled]

    # Sort (whitelist allowed fields)
    allowed_sort = {"created_at_ms", "updated_at_ms", "name", "enabled"}
    if sort_by not in allowed_sort:
        sort_by = "created_at_ms"
    reverse = sort_dir == "desc"
    jobs.sort(key=lambda j: getattr(j, sort_by, 0) or 0, reverse=reverse)

    total = len(jobs)
    jobs = jobs[offset:offset + limit]

    return {
        "jobs": [_job_to_dict(j) for j in jobs],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


async def handle_cron_add(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    name = params.get("name", "Untitled Job")
    sched_raw = params.get("schedule", {})
    payload_raw = params.get("payload", {})
    enabled = params.get("enabled", True)
    delete_after_run = params.get("deleteAfterRun", False)

    schedule = CronSchedule(
        kind=sched_raw.get("kind", "every"),
        at_ms=sched_raw.get("at_ms") or sched_raw.get("atMs"),
        every_ms=sched_raw.get("every_ms") or sched_raw.get("everyMs"),
        expr=sched_raw.get("expr"),
        tz=sched_raw.get("tz"),
    )

    message = payload_raw.get("message", "")
    deliver = payload_raw.get("deliver", False)
    channel = payload_raw.get("channel")
    to = payload_raw.get("to")

    job = ctx.cron.add_job(
        name=name,
        schedule=schedule,
        message=message,
        deliver=deliver,
        channel=channel,
        to=to,
        delete_after_run=delete_after_run,
    )

    await ctx.broadcaster.broadcast("cron", {"action": "added", "job": _job_to_dict(job)})
    return _job_to_dict(job)


async def handle_cron_update(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    job_id = params.get("id")
    if not job_id:
        raise GatewayError("INVALID_PARAMS", "id required")

    patch = params.get("patch", {})

    # Handle enable/disable
    if "enabled" in patch:
        result = ctx.cron.enable_job(job_id, patch["enabled"])
        if result is None:
            raise GatewayError("NOT_FOUND", f"job {job_id} not found")
        await ctx.broadcaster.broadcast("cron", {"action": "updated", "job": _job_to_dict(result)})
        return _job_to_dict(result)

    raise GatewayError("NOT_IMPLEMENTED", "only enabled patch supported currently")


async def handle_cron_run(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    job_id = params.get("id")
    if not job_id:
        raise GatewayError("INVALID_PARAMS", "id required")

    mode = params.get("mode", "force")
    success = await ctx.cron.run_job(job_id, force=(mode == "force"))
    if not success:
        raise GatewayError("RUN_FAILED", f"failed to run job {job_id}")

    return {"ok": True}


async def handle_cron_remove(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    job_id = params.get("id")
    if not job_id:
        raise GatewayError("INVALID_PARAMS", "id required")

    removed = ctx.cron.remove_job(job_id)
    if not removed:
        raise GatewayError("NOT_FOUND", f"job {job_id} not found")

    await ctx.broadcaster.broadcast("cron", {"action": "removed", "jobId": job_id})
    return {"ok": True}


async def handle_cron_runs(ctx: GatewayContext, conn: ClientConnection, params: dict[str, Any]) -> Any:
    """List cron run logs from the cron store directory."""
    from nanobot.config.loader import get_data_dir

    limit = params.get("limit", 50)
    offset = params.get("offset", 0)
    scope = params.get("scope", "all")
    filter_id = params.get("id")
    sort_dir = params.get("sortDir", "desc")
    status_filter = params.get("status")
    statuses_filter = params.get("statuses")

    runs_path = get_data_dir() / "cron" / "runs.jsonl"
    if not runs_path.exists():
        return {"runs": [], "total": 0}

    runs: list[dict[str, Any]] = []
    try:
        for line in runs_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Filter by job id
            if filter_id and entry.get("jobId") != filter_id:
                continue

            # Filter by status
            if status_filter and entry.get("status") != status_filter:
                continue
            if statuses_filter and entry.get("status") not in statuses_filter:
                continue

            runs.append(entry)
    except Exception:
        pass

    # Sort
    reverse = sort_dir == "desc"
    runs.sort(key=lambda r: r.get("startedAtMs", 0), reverse=reverse)

    total = len(runs)
    runs = runs[offset:offset + limit]

    return {"runs": runs, "total": total}


ROUTES = {
    "cron.status": handle_cron_status,
    "cron.list": handle_cron_list,
    "cron.add": handle_cron_add,
    "cron.update": handle_cron_update,
    "cron.run": handle_cron_run,
    "cron.remove": handle_cron_remove,
    "cron.runs": handle_cron_runs,
}
