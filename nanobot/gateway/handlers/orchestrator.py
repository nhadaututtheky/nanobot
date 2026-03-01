"""Orchestrator handlers: decompose, execute, graph CRUD, model info."""

from __future__ import annotations

import logging
import re
from typing import Any

from nanobot.gateway.connection import ClientConnection
from nanobot.gateway.context import GatewayContext
from nanobot.gateway.protocol import GatewayError

logger = logging.getLogger(__name__)

_GRAPH_ID_RE = re.compile(r"^[a-f0-9\-]{1,36}$")


def _get_orchestrator(ctx: GatewayContext) -> tuple:
    """Return (store, executor, decomposer) or raise if not available."""
    orch = getattr(ctx, "orchestrator", None)
    if orch is None:
        raise GatewayError("NOT_AVAILABLE", "Orchestrator not initialised")
    return orch["store"], orch["executor"], orch["decomposer"], orch["router"]


def _validate_graph_id(params: dict[str, Any]) -> str:
    """Extract and validate graphId from params."""
    graph_id = params.get("graphId", "")
    if not graph_id:
        raise GatewayError("INVALID_PARAMS", "graphId is required")
    if not _GRAPH_ID_RE.match(graph_id):
        raise GatewayError("INVALID_PARAMS", "graphId contains invalid characters")
    return graph_id


async def handle_decompose(
    ctx: GatewayContext,
    conn: ClientConnection,
    params: dict[str, Any],
) -> Any:
    """Goal -> TaskGraph preview (no execution)."""
    store, _executor, decomposer, _router = _get_orchestrator(ctx)

    goal = params.get("goal", "")
    if not goal:
        raise GatewayError("INVALID_PARAMS", "goal is required")

    context = params.get("context", "")
    max_tasks = min(
        int(params.get("maxTasks", ctx.config.agents.orchestrator.max_tasks_per_graph)),
        30,
    )

    graph = await decomposer.decompose(
        goal=goal,
        context=context,
        max_tasks=max_tasks,
    )
    await store.add(graph)
    return graph.to_dict()


async def handle_execute(
    ctx: GatewayContext,
    conn: ClientConnection,
    params: dict[str, Any],
) -> Any:
    """Start execution of an existing graph by ID."""
    store, executor, _decomposer, _router = _get_orchestrator(ctx)

    graph_id = _validate_graph_id(params)

    graph = store.get(graph_id)
    if not graph:
        raise GatewayError("NOT_FOUND", f"Graph {graph_id} not found")

    if executor.is_running(graph_id):
        raise GatewayError("CONFLICT", f"Graph {graph_id} is already running")

    # Set origin from connection if not already set
    if not graph.origin_channel or graph.origin_channel == "cli":
        graph.origin_channel = "dashboard"
        graph.origin_chat_id = "direct"
        await store.save(graph)

    await executor.execute(graph)
    return {"ok": True, "graphId": graph.id}


async def handle_run(
    ctx: GatewayContext,
    conn: ClientConnection,
    params: dict[str, Any],
) -> Any:
    """Decompose + execute in one step."""
    store, executor, decomposer, _router = _get_orchestrator(ctx)

    goal = params.get("goal", "")
    if not goal:
        raise GatewayError("INVALID_PARAMS", "goal is required")

    context = params.get("context", "")
    max_tasks = min(
        int(params.get("maxTasks", ctx.config.agents.orchestrator.max_tasks_per_graph)),
        30,
    )

    graph = await decomposer.decompose(
        goal=goal,
        context=context,
        max_tasks=max_tasks,
        origin_channel="dashboard",
        origin_chat_id="direct",
    )
    await store.add(graph)
    await executor.execute(graph)
    return graph.to_dict()


async def handle_graph_get(
    ctx: GatewayContext,
    conn: ClientConnection,
    params: dict[str, Any],
) -> Any:
    """Get a graph by ID."""
    store, _executor, _decomposer, _router = _get_orchestrator(ctx)

    graph_id = _validate_graph_id(params)

    graph = store.get(graph_id)
    if not graph:
        raise GatewayError("NOT_FOUND", f"Graph {graph_id} not found")

    return graph.to_dict()


async def handle_graph_list(
    ctx: GatewayContext,
    conn: ClientConnection,
    params: dict[str, Any],
) -> Any:
    """List recent graphs."""
    store, _executor, _decomposer, _router = _get_orchestrator(ctx)
    limit = min(int(params.get("limit", 20)), 100)
    return {"graphs": store.list_recent(limit=limit)}


async def handle_graph_cancel(
    ctx: GatewayContext,
    conn: ClientConnection,
    params: dict[str, Any],
) -> Any:
    """Cancel a running graph."""
    store, executor, _decomposer, _router = _get_orchestrator(ctx)

    graph_id = _validate_graph_id(params)

    cancelled = await executor.cancel(graph_id)
    if not cancelled:
        raise GatewayError("NOT_FOUND", f"Graph {graph_id} not running")

    return {"ok": True, "graphId": graph_id}


async def handle_graph_delete(
    ctx: GatewayContext,
    conn: ClientConnection,
    params: dict[str, Any],
) -> Any:
    """Delete a graph from the store."""
    store, executor, _decomposer, _router = _get_orchestrator(ctx)

    graph_id = _validate_graph_id(params)

    if executor.is_running(graph_id):
        raise GatewayError("CONFLICT", "Cannot delete a running graph — cancel it first")

    removed = await store.remove(graph_id)
    if not removed:
        raise GatewayError("NOT_FOUND", f"Graph {graph_id} not found")

    return {"ok": True}


async def handle_graph_retry(
    ctx: GatewayContext,
    conn: ClientConnection,
    params: dict[str, Any],
) -> Any:
    """Retry failed/skipped nodes in a graph."""
    store, executor, _decomposer, _router = _get_orchestrator(ctx)

    graph_id = _validate_graph_id(params)

    graph = store.get(graph_id)
    if not graph:
        raise GatewayError("NOT_FOUND", f"Graph {graph_id} not found")

    if executor.is_running(graph_id):
        raise GatewayError("CONFLICT", f"Graph {graph_id} is still running")

    await executor.retry_failed(graph)
    return {"ok": True, "graphId": graph.id}


async def handle_models(
    ctx: GatewayContext,
    conn: ClientConnection,
    params: dict[str, Any],
) -> Any:
    """Return available models and their capabilities."""
    _store, _executor, _decomposer, router = _get_orchestrator(ctx)
    return {"models": router.get_models_info()}


ROUTES = {
    "orchestrator.decompose": handle_decompose,
    "orchestrator.execute": handle_execute,
    "orchestrator.run": handle_run,
    "orchestrator.graph.get": handle_graph_get,
    "orchestrator.graph.list": handle_graph_list,
    "orchestrator.graph.cancel": handle_graph_cancel,
    "orchestrator.graph.delete": handle_graph_delete,
    "orchestrator.graph.retry": handle_graph_retry,
    "orchestrator.models": handle_models,
}
