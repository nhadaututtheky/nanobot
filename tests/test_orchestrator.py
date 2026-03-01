"""Unit tests for the NanoBot orchestrator module.

Covers:
- models.py: TaskNode, TaskEdge, TaskGraph dataclasses, status transitions, graph validation
- router.py: ModelRouter model selection, fallback logic, capability matching
- store.py: GraphStore save/load/delete, max limit enforcement
- decomposer.py: GoalDecomposer JSON parsing, edge building, cycle detection
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nanobot.orchestrator.models import (
    GraphStatus,
    ModelCapability,
    TaskCapability,
    TaskEdge,
    TaskGraph,
    TaskNode,
    TaskStatus,
)
from nanobot.orchestrator.store import GraphStore

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def _make_node(
    node_id: str = "t1",
    label: str = "Test",
    capability: TaskCapability = TaskCapability.GENERAL,
    status: TaskStatus = TaskStatus.PENDING,
) -> TaskNode:
    return TaskNode(id=node_id, label=label, capability=capability, status=status)


def _make_graph(goal: str = "Test goal") -> TaskGraph:
    return TaskGraph(id="g1", goal=goal)


def _make_config(
    *,
    active_model: str = "anthropic/claude-opus-4-6",
    active_provider: str = "anthropic",
    anthropic_key: str = "sk-test",
    openai_key: str = "",
    deepseek_key: str = "",
    gemini_key: str = "",
    openrouter_key: str = "",
    orchestrator_models: list | None = None,
) -> MagicMock:
    """Build a minimal Config mock for ModelRouter tests."""
    cfg = MagicMock()

    # providers
    cfg.providers.anthropic.api_key = anthropic_key
    cfg.providers.anthropic.api_base = None
    cfg.providers.openai.api_key = openai_key
    cfg.providers.openai.api_base = None
    cfg.providers.deepseek.api_key = deepseek_key
    cfg.providers.deepseek.api_base = None
    cfg.providers.gemini.api_key = gemini_key
    cfg.providers.gemini.api_base = None
    cfg.providers.openrouter.api_key = openrouter_key
    cfg.providers.openrouter.api_base = None

    # Remaining providers — no keys
    for pname in [
        "groq", "zhipu", "dashscope", "vllm", "moonshot",
        "minimax", "aihubmix", "siliconflow", "volcengine",
        "openai_codex", "github_copilot", "custom",
    ]:
        p = MagicMock()
        p.api_key = ""
        p.api_base = None
        setattr(cfg.providers, pname, p)

    # agents
    cfg.agents.defaults.model = active_model
    cfg.agents.defaults.provider = active_provider
    cfg.agents.orchestrator.models = orchestrator_models or []

    return cfg


# ---------------------------------------------------------------------------
# models.py — TaskNode
# ---------------------------------------------------------------------------


class TestTaskNode:
    def test_defaults(self) -> None:
        node = TaskNode(id="t1", label="Do something")
        assert node.status == TaskStatus.PENDING
        assert node.capability == TaskCapability.GENERAL
        assert node.worker_role == "general"
        assert node.progress == 0.0
        assert node.assigned_model == ""
        assert node.result == ""
        assert node.error == ""

    def test_to_dict_keys(self) -> None:
        node = _make_node("t1", "Research")
        d = node.to_dict()
        assert d["id"] == "t1"
        assert d["label"] == "Research"
        assert d["status"] == "pending"
        assert d["capability"] == "general"
        assert d["workerRole"] == "general"
        assert "assignedModel" in d
        assert "progress" in d

    def test_from_dict_roundtrip(self) -> None:
        node = TaskNode(
            id="t2",
            label="Summarise",
            description="Summarise findings",
            capability=TaskCapability.SUMMARIZATION,
            worker_role="researcher",
            status=TaskStatus.RUNNING,
            assigned_model="anthropic/claude-haiku-3-5",
            progress=0.5,
        )
        restored = TaskNode.from_dict(node.to_dict())
        assert restored.id == node.id
        assert restored.label == node.label
        assert restored.capability == node.capability
        assert restored.status == node.status
        assert restored.assigned_model == node.assigned_model
        assert restored.progress == node.progress

    def test_from_dict_snake_case_fallback(self) -> None:
        """from_dict must accept snake_case keys (internal format)."""
        d = {
            "id": "t3",
            "label": "Code",
            "capability": "coding",
            "worker_role": "coder",
            "status": "completed",
            "assigned_model": "openai/gpt-4.1",
            "input_context": "ctx",
            "output_summary": "done",
            "started_at": "2026-01-01T00:00:00",
            "completed_at": "2026-01-01T01:00:00",
        }
        node = TaskNode.from_dict(d)
        assert node.worker_role == "coder"
        assert node.input_context == "ctx"
        assert node.output_summary == "done"
        assert node.started_at == "2026-01-01T00:00:00"

    def test_from_dict_invalid_capability_falls_back_to_general(self) -> None:
        d = {"id": "t4", "label": "X", "capability": "nonexistent_cap"}
        # TaskCapability("nonexistent_cap") raises ValueError, from_dict should not mask it
        with pytest.raises(ValueError):
            TaskNode.from_dict(d)

    def test_all_status_values(self) -> None:
        statuses = [
            TaskStatus.PENDING,
            TaskStatus.QUEUED,
            TaskStatus.RUNNING,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.SKIPPED,
        ]
        for status in statuses:
            node = TaskNode(id="x", label="x", status=status)
            assert node.status == status


# ---------------------------------------------------------------------------
# models.py — TaskEdge
# ---------------------------------------------------------------------------


class TestTaskEdge:
    def test_to_dict(self) -> None:
        edge = TaskEdge(from_id="t1", to_id="t2")
        d = edge.to_dict()
        assert d == {"fromId": "t1", "toId": "t2"}

    def test_from_dict_camel(self) -> None:
        edge = TaskEdge.from_dict({"fromId": "a", "toId": "b"})
        assert edge.from_id == "a"
        assert edge.to_id == "b"

    def test_from_dict_snake(self) -> None:
        edge = TaskEdge.from_dict({"from_id": "x", "to_id": "y"})
        assert edge.from_id == "x"
        assert edge.to_id == "y"

    def test_frozen(self) -> None:
        edge = TaskEdge(from_id="a", to_id="b")
        with pytest.raises((AttributeError, TypeError)):
            edge.from_id = "c"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# models.py — TaskGraph
# ---------------------------------------------------------------------------


class TestTaskGraph:
    def test_defaults(self) -> None:
        g = TaskGraph(id="g1", goal="test")
        assert g.status == GraphStatus.DRAFT
        assert g.nodes == []
        assert g.edges == []
        assert g.origin_channel == "cli"
        assert g.origin_chat_id == "direct"
        assert g.created_at  # auto-generated, non-empty

    def test_id_auto_generated(self) -> None:
        g1 = TaskGraph()
        g2 = TaskGraph()
        assert g1.id != g2.id
        assert len(g1.id) == 12  # uuid4()[:12]

    def test_get_node_found(self) -> None:
        n1 = _make_node("t1")
        n2 = _make_node("t2")
        g = TaskGraph(id="g", nodes=[n1, n2])
        assert g.get_node("t1") is n1
        assert g.get_node("t2") is n2

    def test_get_node_missing(self) -> None:
        g = TaskGraph(id="g")
        assert g.get_node("nonexistent") is None

    def test_get_dependencies(self) -> None:
        g = TaskGraph(
            id="g",
            nodes=[_make_node("t1"), _make_node("t2"), _make_node("t3")],
            edges=[TaskEdge("t1", "t3"), TaskEdge("t2", "t3")],
        )
        deps = g.get_dependencies("t3")
        assert sorted(deps) == ["t1", "t2"]
        assert g.get_dependencies("t1") == []

    def test_get_dependents(self) -> None:
        g = TaskGraph(
            id="g",
            nodes=[_make_node("t1"), _make_node("t2"), _make_node("t3")],
            edges=[TaskEdge("t1", "t2"), TaskEdge("t1", "t3")],
        )
        assert sorted(g.get_dependents("t1")) == ["t2", "t3"]
        assert g.get_dependents("t3") == []

    def test_get_ready_tasks_no_deps(self) -> None:
        n1 = _make_node("t1", status=TaskStatus.PENDING)
        n2 = _make_node("t2", status=TaskStatus.PENDING)
        g = TaskGraph(id="g", nodes=[n1, n2])
        ready = g.get_ready_tasks()
        assert len(ready) == 2

    def test_get_ready_tasks_with_incomplete_deps(self) -> None:
        n1 = _make_node("t1", status=TaskStatus.RUNNING)
        n2 = _make_node("t2", status=TaskStatus.PENDING)
        g = TaskGraph(id="g", nodes=[n1, n2], edges=[TaskEdge("t1", "t2")])
        ready = g.get_ready_tasks()
        assert ready == []

    def test_get_ready_tasks_with_completed_deps(self) -> None:
        n1 = _make_node("t1", status=TaskStatus.COMPLETED)
        n2 = _make_node("t2", status=TaskStatus.PENDING)
        g = TaskGraph(id="g", nodes=[n1, n2], edges=[TaskEdge("t1", "t2")])
        ready = g.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "t2"

    def test_progress_empty_graph(self) -> None:
        g = TaskGraph(id="g")
        assert g.progress == 0.0

    def test_progress_partial(self) -> None:
        nodes = [
            _make_node("t1", status=TaskStatus.COMPLETED),
            _make_node("t2", status=TaskStatus.SKIPPED),
            _make_node("t3", status=TaskStatus.PENDING),
            _make_node("t4", status=TaskStatus.RUNNING),
        ]
        g = TaskGraph(id="g", nodes=nodes)
        assert g.progress == pytest.approx(0.5)

    def test_progress_all_done(self) -> None:
        nodes = [
            _make_node("t1", status=TaskStatus.COMPLETED),
            _make_node("t2", status=TaskStatus.COMPLETED),
        ]
        g = TaskGraph(id="g", nodes=nodes)
        assert g.progress == 1.0

    def test_is_terminal(self) -> None:
        for terminal_status in (GraphStatus.COMPLETED, GraphStatus.FAILED, GraphStatus.CANCELLED):
            g = TaskGraph(id="g", status=terminal_status)
            assert g.is_terminal is True

        for non_terminal in (GraphStatus.DRAFT, GraphStatus.RUNNING):
            g = TaskGraph(id="g", status=non_terminal)
            assert g.is_terminal is False

    def test_has_cycle_linear_dag(self) -> None:
        """t1 → t2 → t3 is a DAG, no cycle."""
        nodes = [_make_node("t1"), _make_node("t2"), _make_node("t3")]
        edges = [TaskEdge("t1", "t2"), TaskEdge("t2", "t3")]
        g = TaskGraph(id="g", nodes=nodes, edges=edges)
        assert g.has_cycle() is False

    def test_has_cycle_detects_cycle(self) -> None:
        """t1 → t2 → t3 → t1 is a cycle."""
        nodes = [_make_node("t1"), _make_node("t2"), _make_node("t3")]
        edges = [TaskEdge("t1", "t2"), TaskEdge("t2", "t3"), TaskEdge("t3", "t1")]
        g = TaskGraph(id="g", nodes=nodes, edges=edges)
        assert g.has_cycle() is True

    def test_has_cycle_two_node_cycle(self) -> None:
        nodes = [_make_node("t1"), _make_node("t2")]
        edges = [TaskEdge("t1", "t2"), TaskEdge("t2", "t1")]
        g = TaskGraph(id="g", nodes=nodes, edges=edges)
        assert g.has_cycle() is True

    def test_has_cycle_self_loop(self) -> None:
        nodes = [_make_node("t1")]
        edges = [TaskEdge("t1", "t1")]
        g = TaskGraph(id="g", nodes=nodes, edges=edges)
        assert g.has_cycle() is True

    def test_has_cycle_fan_out(self) -> None:
        """t1 → t2, t1 → t3 (diamond without merge — DAG)."""
        nodes = [_make_node("t1"), _make_node("t2"), _make_node("t3")]
        edges = [TaskEdge("t1", "t2"), TaskEdge("t1", "t3")]
        g = TaskGraph(id="g", nodes=nodes, edges=edges)
        assert g.has_cycle() is False

    def test_has_cycle_diamond(self) -> None:
        """t1 → t2 → t4, t1 → t3 → t4 (diamond DAG)."""
        nodes = [_make_node(i) for i in ("t1", "t2", "t3", "t4")]
        edges = [
            TaskEdge("t1", "t2"),
            TaskEdge("t1", "t3"),
            TaskEdge("t2", "t4"),
            TaskEdge("t3", "t4"),
        ]
        g = TaskGraph(id="g", nodes=nodes, edges=edges)
        assert g.has_cycle() is False

    def test_has_cycle_ignores_edges_with_unknown_node_ids(self) -> None:
        """Edges referencing unknown node IDs should not affect cycle detection."""
        nodes = [_make_node("t1")]
        edges = [TaskEdge("t1", "ghost"), TaskEdge("ghost", "t1")]
        g = TaskGraph(id="g", nodes=nodes, edges=edges)
        # ghost not in node_ids, so these edges are ignored → no cycle for t1
        assert g.has_cycle() is False

    def test_to_dict_roundtrip(self) -> None:
        n1 = _make_node("t1", status=TaskStatus.COMPLETED)
        n2 = _make_node("t2")
        edge = TaskEdge("t1", "t2")
        g = TaskGraph(id="abc123", goal="do things", nodes=[n1, n2], edges=[edge])
        d = g.to_dict()
        restored = TaskGraph.from_dict(d)
        assert restored.id == "abc123"
        assert restored.goal == "do things"
        assert len(restored.nodes) == 2
        assert len(restored.edges) == 1
        assert restored.edges[0].from_id == "t1"
        assert restored.edges[0].to_id == "t2"

    def test_to_dict_includes_progress(self) -> None:
        g = TaskGraph(
            id="g",
            nodes=[
                _make_node("t1", status=TaskStatus.COMPLETED),
                _make_node("t2", status=TaskStatus.PENDING),
            ],
        )
        d = g.to_dict()
        assert "progress" in d
        assert d["progress"] == pytest.approx(0.5)

    def test_from_dict_accepts_camel_case_fields(self) -> None:
        d = {
            "id": "g99",
            "goal": "research",
            "nodes": [],
            "edges": [],
            "status": "running",
            "originChannel": "telegram",
            "originChatId": "12345",
            "createdAt": "2026-01-01T00:00:00",
            "startedAt": "2026-01-01T00:01:00",
            "completedAt": "",
        }
        g = TaskGraph.from_dict(d)
        assert g.id == "g99"
        assert g.origin_channel == "telegram"
        assert g.origin_chat_id == "12345"
        assert g.status == GraphStatus.RUNNING


# ---------------------------------------------------------------------------
# models.py — ModelCapability (frozen dataclass)
# ---------------------------------------------------------------------------


class TestModelCapability:
    def test_frozen(self) -> None:
        mc = ModelCapability(
            model="openai/gpt-4.1",
            provider="openai",
            capabilities=("reasoning",),
        )
        with pytest.raises((AttributeError, TypeError)):
            mc.model = "something-else"  # type: ignore[misc]

    def test_defaults(self) -> None:
        mc = ModelCapability(model="m", provider="p", capabilities=())
        assert mc.tier == "mid"
        assert mc.cost_input == 0.0
        assert mc.cost_output == 0.0
        assert mc.context_window == 128_000


# ---------------------------------------------------------------------------
# router.py — ModelRouter
# ---------------------------------------------------------------------------


class TestModelRouter:
    """Tests for ModelRouter using a mocked Config and provider registry."""

    def _build_router(self, **kwargs):
        """Convenience: build a router with a mocked Config."""
        from nanobot.orchestrator.router import ModelRouter

        cfg = _make_config(**kwargs)

        # Patch provider registry so _scan_* methods work without real imports
        with patch("nanobot.orchestrator.router.ModelRouter._build_registry") as mock_build:
            router = object.__new__(ModelRouter)
            router._config = cfg
            router._registry = []
            router._active_providers = set()
            router._active_gateways = []
            mock_build.return_value = None

        return router

    def _build_router_with_registry(self, models: list[ModelCapability], **kwargs):
        """Build a router with an explicit pre-set registry (bypasses provider scanning)."""
        from nanobot.orchestrator.router import ModelRouter

        cfg = _make_config(**kwargs)
        router = object.__new__(ModelRouter)
        router._config = cfg
        router._registry = list(models)
        router._active_providers = {"anthropic"}
        router._active_gateways = []
        return router

    # --- route() ---

    def test_route_picks_capability_match(self) -> None:
        models = [
            ModelCapability("anthropic/claude-opus-4-6", "anthropic", ("reasoning",), "high", 15.0, 75.0),
            ModelCapability("anthropic/claude-haiku-3-5", "anthropic", ("summarization",), "low", 0.8, 4.0),
        ]
        router = self._build_router_with_registry(models)
        task = _make_node("t1", capability=TaskCapability.REASONING)
        result = router.route(task)
        assert result.model == "anthropic/claude-opus-4-6"

    def test_route_prefers_correct_tier(self) -> None:
        """research → preferred tier = low; should pick low-tier model first."""
        models = [
            ModelCapability("high-model", "p", ("research",), "high", 10.0, 40.0),
            ModelCapability("low-model", "p", ("research",), "low", 0.1, 0.4),
        ]
        router = self._build_router_with_registry(models)
        task = _make_node("t1", capability=TaskCapability.RESEARCH)
        result = router.route(task)
        assert result.model == "low-model"

    def test_route_picks_cheapest_within_tier(self) -> None:
        """coding → preferred tier = mid; picks cheapest mid-tier."""
        models = [
            ModelCapability("expensive-mid", "p", ("coding",), "mid", 5.0, 20.0),
            ModelCapability("cheap-mid", "p", ("coding",), "mid", 0.4, 1.6),
        ]
        router = self._build_router_with_registry(models)
        task = _make_node("t1", capability=TaskCapability.CODING)
        result = router.route(task)
        assert result.model == "cheap-mid"

    def test_route_falls_back_to_general_when_no_capability_match(self) -> None:
        """No reasoning model → fall back to general."""
        models = [
            ModelCapability("general-model", "p", ("general",), "mid", 1.0, 4.0),
        ]
        router = self._build_router_with_registry(models)
        task = _make_node("t1", capability=TaskCapability.REASONING)
        result = router.route(task)
        assert result.model == "general-model"

    def test_route_falls_back_to_any_when_no_general(self) -> None:
        """No matching capability, no general → use any available model."""
        models = [
            ModelCapability("only-translation", "p", ("translation",), "low", 0.1, 0.4),
        ]
        router = self._build_router_with_registry(models)
        task = _make_node("t1", capability=TaskCapability.CODING)
        result = router.route(task)
        assert result.model == "only-translation"

    def test_route_empty_registry_returns_default_model(self) -> None:
        from nanobot.orchestrator.router import ModelRouter

        cfg = _make_config(active_model="fallback-model")
        router = object.__new__(ModelRouter)
        router._config = cfg
        router._registry = []
        router._active_providers = set()
        router._active_gateways = []

        task = _make_node("t1", capability=TaskCapability.CODING)
        result = router.route(task)
        assert result.model == "fallback-model"

    def test_route_picks_closest_tier_when_preferred_not_available(self) -> None:
        """Coding prefers mid, but only high and low exist → pick by distance."""
        models = [
            ModelCapability("high-model", "p", ("coding",), "high", 10.0, 30.0),
            ModelCapability("low-model", "p", ("coding",), "low", 0.1, 0.4),
        ]
        router = self._build_router_with_registry(models)
        task = _make_node("t1", capability=TaskCapability.CODING)
        result = router.route(task)
        # mid distance: high=1, low=1 (both equidistant) — then cheapest
        assert result.model == "low-model"

    # --- route_orchestrator() ---

    def test_route_orchestrator_prefers_high_reasoning(self) -> None:
        models = [
            ModelCapability("high-reason", "p", ("reasoning",), "high", 15.0, 75.0),
            ModelCapability("mid-general", "p", ("general",), "mid", 1.0, 4.0),
        ]
        router = self._build_router_with_registry(models)
        result = router.route_orchestrator()
        assert result.model == "high-reason"

    def test_route_orchestrator_falls_back_to_any_reasoning(self) -> None:
        models = [
            ModelCapability("mid-reason", "p", ("reasoning",), "mid", 3.0, 15.0),
            ModelCapability("low-general", "p", ("general",), "low", 0.1, 0.4),
        ]
        router = self._build_router_with_registry(models)
        result = router.route_orchestrator()
        assert result.model == "mid-reason"

    def test_route_orchestrator_no_reasoning_uses_first(self) -> None:
        models = [
            ModelCapability("only-coding", "p", ("coding",), "mid", 3.0, 15.0),
        ]
        router = self._build_router_with_registry(models)
        result = router.route_orchestrator()
        assert result.model == "only-coding"

    def test_route_orchestrator_empty_registry_returns_default(self) -> None:
        from nanobot.orchestrator.router import ModelRouter

        cfg = _make_config(active_model="default-model")
        router = object.__new__(ModelRouter)
        router._config = cfg
        router._registry = []
        router._active_providers = set()
        router._active_gateways = []

        result = router.route_orchestrator()
        assert result.model == "default-model"

    # --- get_models_info() ---

    def test_get_models_info_structure(self) -> None:
        models = [
            ModelCapability("m1", "anthropic", ("coding", "reasoning"), "mid", 3.0, 15.0, 200_000),
        ]
        router = self._build_router_with_registry(models)
        info = router.get_models_info()
        assert len(info) == 1
        row = info[0]
        assert row["model"] == "m1"
        assert row["provider"] == "anthropic"
        assert set(row["capabilities"]) == {"coding", "reasoning"}
        assert row["tier"] == "mid"
        assert row["costInput"] == 3.0
        assert row["costOutput"] == 15.0
        assert row["contextWindow"] == 200_000
        assert "directAccess" in row
        assert "viaGateways" in row

    def test_get_models_info_direct_access_flag(self) -> None:
        models = [
            ModelCapability("m1", "anthropic", ("general",), "mid"),
            ModelCapability("m2", "openai", ("general",), "mid"),
        ]
        router = self._build_router_with_registry(models)
        router._active_providers = {"anthropic"}
        info = {r["model"]: r for r in router.get_models_info()}
        assert info["m1"]["directAccess"] is True
        assert info["m2"]["directAccess"] is False


# ---------------------------------------------------------------------------
# store.py — GraphStore
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_store(tmp_path: Path) -> GraphStore:
    return GraphStore(workspace=tmp_path)


class TestGraphStore:
    @pytest.mark.asyncio
    async def test_add_and_get(self, tmp_store: GraphStore) -> None:
        g = _make_graph("goal A")
        await tmp_store.add(g)
        retrieved = tmp_store.get(g.id)
        assert retrieved is not None
        assert retrieved.id == g.id
        assert retrieved.goal == "goal A"

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, tmp_store: GraphStore) -> None:
        assert tmp_store.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_add_duplicate_replaces(self, tmp_store: GraphStore) -> None:
        g = TaskGraph(id="dup", goal="first")
        await tmp_store.add(g)
        g2 = TaskGraph(id="dup", goal="second")
        await tmp_store.add(g2)
        result = tmp_store.get("dup")
        assert result is not None
        assert result.goal == "second"
        all_ids = [x["id"] for x in tmp_store.list_recent(limit=100)]
        assert all_ids.count("dup") == 1

    @pytest.mark.asyncio
    async def test_save_is_upsert(self, tmp_store: GraphStore) -> None:
        g = TaskGraph(id="s1", goal="original")
        await tmp_store.save(g)
        g_updated = TaskGraph(id="s1", goal="updated")
        await tmp_store.save(g_updated)
        assert tmp_store.get("s1").goal == "updated"  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_remove_existing(self, tmp_store: GraphStore) -> None:
        g = _make_graph("to remove")
        await tmp_store.add(g)
        removed = await tmp_store.remove(g.id)
        assert removed is True
        assert tmp_store.get(g.id) is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent_returns_false(self, tmp_store: GraphStore) -> None:
        removed = await tmp_store.remove("ghost-id")
        assert removed is False

    @pytest.mark.asyncio
    async def test_list_recent_order(self, tmp_store: GraphStore) -> None:
        """list_recent should return most recent first (reversed)."""
        for i in range(3):
            await tmp_store.add(TaskGraph(id=f"g{i}", goal=f"goal {i}"))
        recent = tmp_store.list_recent(limit=10)
        ids = [r["id"] for r in recent]
        assert ids == ["g2", "g1", "g0"]

    @pytest.mark.asyncio
    async def test_list_recent_respects_limit(self, tmp_store: GraphStore) -> None:
        for i in range(5):
            await tmp_store.add(TaskGraph(id=f"g{i}", goal=f"g{i}"))
        recent = tmp_store.list_recent(limit=3)
        assert len(recent) == 3

    @pytest.mark.asyncio
    async def test_list_recent_summary_fields(self, tmp_store: GraphStore) -> None:
        g = TaskGraph(id="g1", goal="check fields", status=GraphStatus.RUNNING)
        await tmp_store.add(g)
        recent = tmp_store.list_recent()
        assert len(recent) == 1
        row = recent[0]
        assert row["id"] == "g1"
        assert row["goal"] == "check fields"
        assert row["status"] == "running"
        assert "nodeCount" in row
        assert "progress" in row
        assert "createdAt" in row
        assert "completedAt" in row

    @pytest.mark.asyncio
    async def test_persistence_across_instances(self, tmp_path: Path) -> None:
        """Data written by one GraphStore instance must be readable by a new one."""
        store1 = GraphStore(workspace=tmp_path)
        g = TaskGraph(id="persist-me", goal="survive reload")
        await store1.add(g)

        store2 = GraphStore(workspace=tmp_path)
        result = store2.get("persist-me")
        assert result is not None
        assert result.goal == "survive reload"

    @pytest.mark.asyncio
    async def test_max_graphs_limit(self, tmp_path: Path) -> None:
        """Store must not exceed MAX_GRAPHS (100) entries, evicting oldest."""
        store = GraphStore(workspace=tmp_path)
        limit = GraphStore.MAX_GRAPHS

        # Add limit + 10 graphs
        for i in range(limit + 10):
            await store.add(TaskGraph(id=f"g{i:04d}", goal=f"goal {i}"))

        recent = store.list_recent(limit=limit + 10)
        assert len(recent) <= limit

        # The oldest graphs (g0000 .. g0009) must have been evicted
        all_ids = {r["id"] for r in recent}
        for i in range(10):
            assert f"g{i:04d}" not in all_ids

        # The newest must survive
        assert f"g{limit + 9:04d}" in all_ids

    @pytest.mark.asyncio
    async def test_corrupted_json_resets_to_empty(self, tmp_path: Path) -> None:
        store = GraphStore(workspace=tmp_path)
        store._ensure_dir()
        store._path.write_text("INVALID JSON {{{{", encoding="utf-8")
        # Clear cache so _load reads from disk
        store._cache = None
        graphs = store._load()
        assert graphs == []

    def test_get_does_not_crash_on_empty_store(self, tmp_store: GraphStore) -> None:
        assert tmp_store.get("x") is None

    def test_list_recent_on_empty_store(self, tmp_store: GraphStore) -> None:
        assert tmp_store.list_recent() == []


# ---------------------------------------------------------------------------
# decomposer.py — GoalDecomposer
# ---------------------------------------------------------------------------


def _make_llm_response(content: str) -> MagicMock:
    """Build a mock LLM response with .content and .finish_reason."""
    resp = MagicMock()
    resp.content = content
    resp.finish_reason = "stop"
    return resp


def _make_decomposer(llm_response_content: str):
    """Return a (GoalDecomposer, mock_provider) pair."""
    from nanobot.orchestrator.decomposer import GoalDecomposer

    provider = MagicMock()
    provider.chat = AsyncMock(return_value=_make_llm_response(llm_response_content))

    router = MagicMock()
    router.route_orchestrator.return_value = ModelCapability(
        model="anthropic/claude-opus-4-6",
        provider="anthropic",
        capabilities=("reasoning",),
        tier="high",
    )
    router.route.return_value = ModelCapability(
        model="anthropic/claude-sonnet-4-6",
        provider="anthropic",
        capabilities=("general",),
        tier="mid",
    )

    decomposer = GoalDecomposer(provider=provider, router=router)
    return decomposer, provider


VALID_JSON_ONE_TASK = json.dumps({
    "tasks": [
        {
            "id": "t1",
            "label": "Research topic",
            "description": "Find information about the topic",
            "capability": "research",
            "worker_role": "researcher",
            "depends_on": [],
        }
    ]
})

VALID_JSON_THREE_TASKS = json.dumps({
    "tasks": [
        {
            "id": "t1",
            "label": "Research",
            "description": "Gather data",
            "capability": "research",
            "worker_role": "researcher",
            "depends_on": [],
        },
        {
            "id": "t2",
            "label": "Code",
            "description": "Write solution",
            "capability": "coding",
            "worker_role": "coder",
            "depends_on": ["t1"],
        },
        {
            "id": "t3",
            "label": "Review",
            "description": "Review code",
            "capability": "general",
            "worker_role": "reviewer",
            "depends_on": ["t2"],
        },
    ]
})


class TestGoalDecomposer:
    @pytest.mark.asyncio
    async def test_decompose_single_task(self) -> None:
        decomposer, _ = _make_decomposer(VALID_JSON_ONE_TASK)
        graph = await decomposer.decompose("Do some research")
        assert graph.goal == "Do some research"
        assert graph.status == GraphStatus.DRAFT
        assert len(graph.nodes) == 1
        assert graph.nodes[0].id == "t1"
        assert graph.nodes[0].label == "Research topic"
        assert graph.nodes[0].capability == TaskCapability.RESEARCH

    @pytest.mark.asyncio
    async def test_decompose_assigns_models_via_router(self) -> None:
        decomposer, _ = _make_decomposer(VALID_JSON_ONE_TASK)
        graph = await decomposer.decompose("Do some research")
        assert graph.nodes[0].assigned_model == "anthropic/claude-sonnet-4-6"

    @pytest.mark.asyncio
    async def test_decompose_three_tasks_edges(self) -> None:
        decomposer, _ = _make_decomposer(VALID_JSON_THREE_TASKS)
        graph = await decomposer.decompose("Build a thing")
        assert len(graph.nodes) == 3
        assert len(graph.edges) == 2
        edge_pairs = {(e.from_id, e.to_id) for e in graph.edges}
        assert ("t1", "t2") in edge_pairs
        assert ("t2", "t3") in edge_pairs

    @pytest.mark.asyncio
    async def test_decompose_sets_origin_fields(self) -> None:
        decomposer, _ = _make_decomposer(VALID_JSON_ONE_TASK)
        graph = await decomposer.decompose("goal", origin_channel="telegram", origin_chat_id="123")
        assert graph.origin_channel == "telegram"
        assert graph.origin_chat_id == "123"

    @pytest.mark.asyncio
    async def test_decompose_raises_on_empty_llm_response(self) -> None:
        decomposer, _ = _make_decomposer("")
        with pytest.raises(ValueError, match="empty response"):
            await decomposer.decompose("goal")

    @pytest.mark.asyncio
    async def test_decompose_raises_on_invalid_json(self) -> None:
        decomposer, _ = _make_decomposer("THIS IS NOT JSON {{{{")
        with pytest.raises(ValueError, match="invalid JSON"):
            await decomposer.decompose("goal")

    @pytest.mark.asyncio
    async def test_decompose_raises_on_zero_tasks(self) -> None:
        decomposer, _ = _make_decomposer(json.dumps({"tasks": []}))
        with pytest.raises(ValueError, match="zero tasks"):
            await decomposer.decompose("goal")

    @pytest.mark.asyncio
    async def test_decompose_strips_markdown_fences(self) -> None:
        wrapped = f"```json\n{VALID_JSON_ONE_TASK}\n```"
        decomposer, _ = _make_decomposer(wrapped)
        graph = await decomposer.decompose("goal")
        assert len(graph.nodes) == 1

    @pytest.mark.asyncio
    async def test_decompose_respects_max_tasks(self) -> None:
        many_tasks = json.dumps({
            "tasks": [
                {
                    "id": f"t{i}",
                    "label": f"Task {i}",
                    "description": "",
                    "capability": "general",
                    "worker_role": "general",
                    "depends_on": [],
                }
                for i in range(1, 16)  # 15 tasks
            ]
        })
        decomposer, _ = _make_decomposer(many_tasks)
        graph = await decomposer.decompose("goal", max_tasks=5)
        assert len(graph.nodes) <= 5

    @pytest.mark.asyncio
    async def test_decompose_skips_tasks_with_empty_id(self) -> None:
        bad_json = json.dumps({
            "tasks": [
                {"id": "", "label": "No ID", "capability": "general", "worker_role": "general", "depends_on": []},
                {"id": "t1", "label": "Has ID", "capability": "general", "worker_role": "general", "depends_on": []},
            ]
        })
        decomposer, _ = _make_decomposer(bad_json)
        graph = await decomposer.decompose("goal")
        assert len(graph.nodes) == 1
        assert graph.nodes[0].id == "t1"

    @pytest.mark.asyncio
    async def test_decompose_ignores_self_loop_edges(self) -> None:
        self_loop_json = json.dumps({
            "tasks": [
                {
                    "id": "t1",
                    "label": "Self loop",
                    "capability": "general",
                    "worker_role": "general",
                    "depends_on": ["t1"],  # self-loop
                }
            ]
        })
        decomposer, _ = _make_decomposer(self_loop_json)
        graph = await decomposer.decompose("goal")
        # Self-loop edge dep == tid, skipped
        assert graph.edges == []

    @pytest.mark.asyncio
    async def test_decompose_ignores_edges_with_unknown_dep(self) -> None:
        unknown_dep_json = json.dumps({
            "tasks": [
                {
                    "id": "t1",
                    "label": "Task",
                    "capability": "general",
                    "worker_role": "general",
                    "depends_on": ["ghost_id"],
                }
            ]
        })
        decomposer, _ = _make_decomposer(unknown_dep_json)
        graph = await decomposer.decompose("goal")
        assert graph.edges == []

    @pytest.mark.asyncio
    async def test_decompose_removes_cycle_edges(self) -> None:
        """If the LLM produces a cyclic graph, all edges must be stripped."""
        cyclic_json = json.dumps({
            "tasks": [
                {"id": "t1", "label": "A", "capability": "general", "worker_role": "general", "depends_on": ["t2"]},
                {"id": "t2", "label": "B", "capability": "general", "worker_role": "general", "depends_on": ["t1"]},
            ]
        })
        decomposer, _ = _make_decomposer(cyclic_json)
        graph = await decomposer.decompose("goal")
        # Cyclic graph detected → edges stripped to prevent deadlock
        assert graph.edges == []
        assert len(graph.nodes) == 2

    @pytest.mark.asyncio
    async def test_decompose_unknown_capability_defaults_to_general(self) -> None:
        unknown_cap_json = json.dumps({
            "tasks": [
                {
                    "id": "t1",
                    "label": "Unknown Cap",
                    "capability": "telepathy",
                    "worker_role": "general",
                    "depends_on": [],
                }
            ]
        })
        decomposer, _ = _make_decomposer(unknown_cap_json)
        graph = await decomposer.decompose("goal")
        assert graph.nodes[0].capability == TaskCapability.GENERAL

    @pytest.mark.asyncio
    async def test_decompose_raises_on_provider_error_content(self) -> None:
        error_content = "Error calling LLM: connection refused"
        decomposer, _ = _make_decomposer(error_content)
        with pytest.raises(ValueError, match="provider error"):
            await decomposer.decompose("goal")

    @pytest.mark.asyncio
    async def test_decompose_retries_on_invalid_json_once(self) -> None:
        """On first call: bad JSON. On second call: valid JSON. Should succeed."""
        from nanobot.orchestrator.decomposer import GoalDecomposer

        provider = MagicMock()
        provider.chat = AsyncMock(side_effect=[
            _make_llm_response("not json"),
            _make_llm_response(VALID_JSON_ONE_TASK),
        ])

        router = MagicMock()
        router.route_orchestrator.return_value = ModelCapability(
            model="anthropic/claude-opus-4-6",
            provider="anthropic",
            capabilities=("reasoning",),
            tier="high",
        )
        router.route.return_value = ModelCapability(
            model="anthropic/claude-sonnet-4-6",
            provider="anthropic",
            capabilities=("general",),
            tier="mid",
        )

        decomposer = GoalDecomposer(provider=provider, router=router)
        graph = await decomposer.decompose("goal with retry")
        assert len(graph.nodes) == 1
        assert provider.chat.call_count == 2
