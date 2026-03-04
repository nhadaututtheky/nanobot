"""Data models for task graph orchestration."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TaskCapability(str, Enum):
    """Capability types a task may require."""

    REASONING = "reasoning"
    CODING = "coding"
    RESEARCH = "research"
    CREATIVE = "creative"
    DATA_ANALYSIS = "data_analysis"
    TRANSLATION = "translation"
    SUMMARIZATION = "summarization"
    GENERAL = "general"


class TaskStatus(str, Enum):
    """Lifecycle status of a task node."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class GraphStatus(str, Enum):
    """Lifecycle status of an entire task graph."""

    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ModelCapability:
    """Describes a model's capabilities for routing decisions."""

    model: str  # e.g. "anthropic/claude-opus-4-5"
    provider: str  # e.g. "anthropic"
    capabilities: tuple[str, ...]  # ("reasoning", "coding", ...)
    tier: str = "mid"  # "high" | "mid" | "low"
    cost_input: float = 0.0  # per 1K tokens
    cost_output: float = 0.0
    context_window: int = 128_000


@dataclass
class TaskNode:
    """A single task in the execution graph."""

    id: str
    label: str
    description: str = ""
    capability: TaskCapability = TaskCapability.GENERAL
    worker_role: str = "general"
    status: TaskStatus = TaskStatus.PENDING
    assigned_model: str = ""
    result: str = ""
    progress: float = 0.0  # 0.0 – 1.0
    input_context: str = ""  # Injected from upstream dependencies
    output_summary: str = ""  # Extracted after completion
    output_files: list[str] = field(default_factory=list)  # Relative paths produced by this node
    input_files: list[str] = field(default_factory=list)  # Injected from upstream dependencies
    evaluate: bool = False  # Run eval loop on this node's output
    eval_score: float = 0.0  # Last eval score (0.0-1.0)
    error: str = ""
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "capability": self.capability.value,
            "workerRole": self.worker_role,
            "status": self.status.value,
            "assignedModel": self.assigned_model,
            "result": self.result,
            "progress": self.progress,
            "inputContext": self.input_context,
            "outputSummary": self.output_summary,
            "outputFiles": self.output_files,
            "inputFiles": self.input_files,
            "evaluate": self.evaluate,
            "evalScore": self.eval_score,
            "error": self.error,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> TaskNode:
        return TaskNode(
            id=d["id"],
            label=d["label"],
            description=d.get("description", ""),
            capability=TaskCapability(d.get("capability", "general")),
            worker_role=d.get("workerRole", d.get("worker_role", "general")),
            status=TaskStatus(d.get("status", "pending")),
            assigned_model=d.get("assignedModel", d.get("assigned_model", "")),
            result=d.get("result", ""),
            progress=d.get("progress", 0.0),
            input_context=d.get("inputContext", d.get("input_context", "")),
            output_summary=d.get("outputSummary", d.get("output_summary", "")),
            output_files=d.get("outputFiles", d.get("output_files", [])),
            input_files=d.get("inputFiles", d.get("input_files", [])),
            evaluate=d.get("evaluate", False),
            eval_score=d.get("evalScore", d.get("eval_score", 0.0)),
            error=d.get("error", ""),
            started_at=d.get("startedAt", d.get("started_at", "")),
            completed_at=d.get("completedAt", d.get("completed_at", "")),
        )


@dataclass(frozen=True)
class TaskEdge:
    """Dependency edge: from_id must complete before to_id can start."""

    from_id: str
    to_id: str

    def to_dict(self) -> dict[str, str]:
        return {"fromId": self.from_id, "toId": self.to_id}

    @staticmethod
    def from_dict(d: dict[str, str]) -> TaskEdge:
        return TaskEdge(
            from_id=d.get("fromId", d.get("from_id", "")),
            to_id=d.get("toId", d.get("to_id", "")),
        )


@dataclass
class TaskGraph:
    """A directed acyclic graph of tasks to execute."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    goal: str = ""
    nodes: list[TaskNode] = field(default_factory=list)
    edges: list[TaskEdge] = field(default_factory=list)
    status: GraphStatus = GraphStatus.DRAFT
    origin_channel: str = "cli"
    origin_chat_id: str = "direct"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: str = ""
    completed_at: str = ""

    # --- index cache (rebuilt lazily) ---

    def _build_index(self) -> None:
        """Build O(1) lookup maps from nodes/edges."""
        self._node_map: dict[str, TaskNode] = {n.id: n for n in self.nodes}
        self._dep_map: dict[str, list[str]] = {n.id: [] for n in self.nodes}
        self._fwd_map: dict[str, list[str]] = {n.id: [] for n in self.nodes}
        for e in self.edges:
            if e.to_id in self._dep_map:
                self._dep_map[e.to_id].append(e.from_id)
            if e.from_id in self._fwd_map:
                self._fwd_map[e.from_id].append(e.to_id)

    def _ensure_index(self) -> None:
        if not hasattr(self, "_node_map") or len(self._node_map) != len(self.nodes):
            self._build_index()

    def rebuild_index(self) -> None:
        """Force rebuild after structural changes (add/remove nodes/edges)."""
        self._build_index()

    # --- query helpers ---

    def get_node(self, node_id: str) -> TaskNode | None:
        self._ensure_index()
        return self._node_map.get(node_id)

    def get_dependencies(self, node_id: str) -> list[str]:
        """Return IDs of nodes that must complete before node_id."""
        self._ensure_index()
        return self._dep_map.get(node_id, [])

    def get_dependents(self, node_id: str) -> list[str]:
        """Return IDs of nodes that depend on node_id."""
        self._ensure_index()
        return self._fwd_map.get(node_id, [])

    def get_ready_tasks(self) -> list[TaskNode]:
        """Return nodes whose dependencies are all completed and that are pending."""
        self._ensure_index()
        ready: list[TaskNode] = []
        for node in self.nodes:
            if node.status != TaskStatus.PENDING:
                continue
            deps = self._dep_map.get(node.id, [])
            if all(
                (dep := self._node_map.get(d)) is not None
                and dep.status == TaskStatus.COMPLETED
                for d in deps
            ):
                ready.append(node)
        return ready

    @property
    def progress(self) -> float:
        """Overall progress (0.0 – 1.0)."""
        if not self.nodes:
            return 0.0
        done = sum(
            1
            for n in self.nodes
            if n.status
            in (
                TaskStatus.COMPLETED,
                TaskStatus.SKIPPED,
            )
        )
        return done / len(self.nodes)

    @property
    def is_terminal(self) -> bool:
        return self.status in (GraphStatus.COMPLETED, GraphStatus.FAILED, GraphStatus.CANCELLED)

    def has_cycle(self) -> bool:
        """Detect cycles using Kahn's algorithm. Returns True if the graph has a cycle."""
        node_ids = {n.id for n in self.nodes}
        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
        adj: dict[str, list[str]] = {nid: [] for nid in node_ids}

        for edge in self.edges:
            if edge.from_id in node_ids and edge.to_id in node_ids:
                in_degree[edge.to_id] = in_degree.get(edge.to_id, 0) + 1
                adj[edge.from_id].append(edge.to_id)

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        visited = 0

        while queue:
            current = queue.pop()
            visited += 1
            for neighbor in adj.get(current, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return visited != len(node_ids)

    # --- serialisation ---

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "status": self.status.value,
            "originChannel": self.origin_channel,
            "originChatId": self.origin_chat_id,
            "createdAt": self.created_at,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "progress": self.progress,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> TaskGraph:
        return TaskGraph(
            id=d["id"],
            goal=d.get("goal", ""),
            nodes=[TaskNode.from_dict(n) for n in d.get("nodes", [])],
            edges=[TaskEdge.from_dict(e) for e in d.get("edges", [])],
            status=GraphStatus(d.get("status", "draft")),
            origin_channel=d.get("originChannel", d.get("origin_channel", "cli")),
            origin_chat_id=d.get("originChatId", d.get("origin_chat_id", "direct")),
            created_at=d.get("createdAt", d.get("created_at", "")),
            started_at=d.get("startedAt", d.get("started_at", "")),
            completed_at=d.get("completedAt", d.get("completed_at", "")),
        )
