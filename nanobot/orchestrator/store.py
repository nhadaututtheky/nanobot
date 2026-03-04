"""Graph store — JSON persistence for task graphs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.orchestrator.models import TaskGraph


class GraphStore:
    """CRUD persistence for TaskGraph objects. Stores as JSON array.

    All write operations are serialised via ``_lock`` to prevent concurrent
    ``_load`` / ``_flush`` interleaving when multiple async tasks call
    ``save()`` in parallel.
    """

    MAX_GRAPHS = 100

    def __init__(self, workspace: Path) -> None:
        self._dir = workspace / "orchestrator"
        self._path = self._dir / "graphs.json"
        self._cache: list[TaskGraph] | None = None
        self._lock = asyncio.Lock()

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[TaskGraph]:
        if self._cache is not None:
            return self._cache

        if not self._path.exists():
            self._cache = []
            return self._cache

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._cache = [TaskGraph.from_dict(d) for d in raw]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Failed to load graphs store, starting fresh: {}", e)
            self._cache = []

        return self._cache

    async def _flush(self) -> None:
        """Write the in-memory cache to disk (non-blocking)."""
        self._ensure_dir()
        graphs = self._cache or []
        data = [g.to_dict() for g in graphs]
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        await asyncio.to_thread(
            self._path.write_text, json_str, encoding="utf-8"
        )

    # --- CRUD ---

    async def add(self, graph: TaskGraph) -> None:
        """Add a graph to the store."""
        async with self._lock:
            graphs = self._load()
            # Replace if same ID exists
            graphs = [g for g in graphs if g.id != graph.id]
            graphs.append(graph)
            # Trim to MAX_GRAPHS (keep most recent)
            if len(graphs) > self.MAX_GRAPHS:
                graphs = graphs[-self.MAX_GRAPHS :]
            self._cache = graphs
            await self._flush()

    async def save(self, graph: TaskGraph) -> None:
        """Update a graph in the store (upsert)."""
        await self.add(graph)

    def get(self, graph_id: str) -> TaskGraph | None:
        """Get a graph by ID (thread-safe via in-memory cache)."""
        # _load() is safe to call without lock — it only reads from _cache or
        # does one-time disk load. Write operations hold _lock.
        graphs = self._load()
        for g in graphs:
            if g.id == graph_id:
                return g
        return None

    async def remove(self, graph_id: str) -> bool:
        """Remove a graph by ID. Returns True if found."""
        async with self._lock:
            graphs = self._load()
            before = len(graphs)
            self._cache = [g for g in graphs if g.id != graph_id]
            if len(self._cache) < before:
                await self._flush()
                return True
            return False

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent graphs as dicts (summary view)."""
        graphs = self._load()
        recent = graphs[-limit:] if len(graphs) > limit else graphs
        return [
            {
                "id": g.id,
                "goal": g.goal[:100],
                "status": g.status.value,
                "nodeCount": len(g.nodes),
                "progress": g.progress,
                "createdAt": g.created_at,
                "completedAt": g.completed_at,
            }
            for g in reversed(recent)
        ]
