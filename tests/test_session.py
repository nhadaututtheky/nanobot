"""Unit tests for Session dataclass and SessionManager."""

import json
from datetime import datetime, timedelta
from pathlib import Path

from nanobot.session.manager import Session, SessionManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_manager(tmp_path: Path) -> SessionManager:
    return SessionManager(tmp_path)


def make_session(key: str = "chan:123", n: int = 0, role: str = "user") -> Session:
    session = Session(key=key)
    for i in range(n):
        session.add_message(role, f"msg{i}")
    return session


# ---------------------------------------------------------------------------
# Session.add_message
# ---------------------------------------------------------------------------


class TestSessionAddMessage:
    def test_appends_message_to_empty_list(self) -> None:
        session = Session(key="t:1")
        session.add_message("user", "hello")
        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "user"
        assert session.messages[0]["content"] == "hello"

    def test_appends_multiple_messages_in_order(self) -> None:
        session = Session(key="t:2")
        session.add_message("user", "first")
        session.add_message("assistant", "second")
        session.add_message("user", "third")
        assert len(session.messages) == 3
        assert session.messages[0]["content"] == "first"
        assert session.messages[1]["content"] == "second"
        assert session.messages[2]["content"] == "third"

    def test_message_includes_timestamp(self) -> None:
        before = datetime.now()
        session = Session(key="t:3")
        session.add_message("user", "hi")
        after = datetime.now()
        ts = datetime.fromisoformat(session.messages[0]["timestamp"])
        assert before <= ts <= after

    def test_extra_kwargs_stored_on_message(self) -> None:
        session = Session(key="t:4")
        session.add_message("tool", "result", tool_call_id="abc123", name="my_tool")
        msg = session.messages[0]
        assert msg["tool_call_id"] == "abc123"
        assert msg["name"] == "my_tool"

    def test_updated_at_advances_after_add(self) -> None:
        session = Session(key="t:5")
        before = session.updated_at
        session.add_message("user", "bump")
        assert session.updated_at >= before

    def test_add_does_not_mutate_other_sessions(self) -> None:
        s1 = Session(key="t:6a")
        s2 = Session(key="t:6b")
        s1.add_message("user", "only for s1")
        assert len(s2.messages) == 0


# ---------------------------------------------------------------------------
# Session.get_history
# ---------------------------------------------------------------------------


class TestSessionGetHistory:
    def test_returns_all_when_under_max(self) -> None:
        session = make_session(n=5)
        history = session.get_history(max_messages=100)
        assert len(history) == 5

    def test_respects_max_messages_limit(self) -> None:
        session = make_session(n=10)
        history = session.get_history(max_messages=4)
        assert len(history) == 4
        # Must be the most recent 4
        assert history[0]["content"] == "msg6"
        assert history[-1]["content"] == "msg9"

    def test_alignment_drops_leading_assistant_messages(self) -> None:
        session = Session(key="t:align")
        # Leading non-user messages should be stripped
        session.add_message("assistant", "orphaned")
        session.add_message("user", "first user")
        session.add_message("assistant", "response")
        history = session.get_history(max_messages=10)
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "first user"

    def test_alignment_drops_leading_tool_result_messages(self) -> None:
        session = Session(key="t:tool")
        session.add_message("tool", "tool result", tool_call_id="x")
        session.add_message("user", "real start")
        history = session.get_history(max_messages=10)
        assert history[0]["role"] == "user"

    def test_alignment_preserves_context_role_as_start(self) -> None:
        session = Session(key="t:ctx")
        session.add_message("assistant", "orphaned")
        session.add_message("context", "system context")
        session.add_message("user", "question")
        history = session.get_history(max_messages=10)
        assert history[0]["role"] == "context"

    def test_history_excludes_consolidated_messages(self) -> None:
        session = make_session(n=10)
        session.last_consolidated = 8  # only messages[8:] are unconsolidated
        history = session.get_history(max_messages=100)
        assert len(history) == 2
        assert history[0]["content"] == "msg8"
        assert history[1]["content"] == "msg9"

    def test_history_output_fields_filtered(self) -> None:
        session = Session(key="t:fields")
        session.add_message("user", "hello")
        history = session.get_history()
        msg = history[0]
        # timestamp must NOT leak into history output
        assert "timestamp" not in msg
        assert msg["role"] == "user"
        assert msg["content"] == "hello"

    def test_history_passes_through_tool_calls(self) -> None:
        session = Session(key="t:tc")
        calls = [{"id": "c1", "function": {"name": "f", "arguments": "{}"}}]
        # Put user turn first so the assistant entry is not stripped by alignment
        session.add_message("user", "question")
        session.add_message("assistant", "", tool_calls=calls)
        history = session.get_history()
        assistant_entry = next(m for m in history if m["role"] == "assistant")
        assert "tool_calls" in assistant_entry
        assert assistant_entry["tool_calls"] == calls

    def test_history_passes_through_tool_call_id(self) -> None:
        session = Session(key="t:tcid")
        session.add_message("user", "start")
        session.add_message("tool", "result", tool_call_id="tid42", name="calc")
        history = session.get_history()
        tool_msg = next(m for m in history if m["role"] == "tool")
        assert tool_msg["tool_call_id"] == "tid42"
        assert tool_msg["name"] == "calc"

    def test_does_not_mutate_messages_list(self) -> None:
        session = make_session(n=10)
        original = [m.copy() for m in session.messages]
        session.get_history(max_messages=3)
        assert len(session.messages) == 10
        for i, msg in enumerate(session.messages):
            assert msg["content"] == original[i]["content"]

    def test_empty_session_returns_empty_list(self) -> None:
        session = Session(key="t:empty")
        assert session.get_history() == []

    def test_default_max_messages_is_large(self) -> None:
        # 500 messages should all be returned by default
        session = make_session(n=20)
        history = session.get_history()
        assert len(history) == 20


# ---------------------------------------------------------------------------
# Session.clear
# ---------------------------------------------------------------------------


class TestSessionClear:
    def test_clear_empties_messages(self) -> None:
        session = make_session(n=5)
        session.clear()
        assert session.messages == []

    def test_clear_resets_last_consolidated(self) -> None:
        session = make_session(n=10)
        session.last_consolidated = 7
        session.clear()
        assert session.last_consolidated == 0

    def test_clear_updates_updated_at(self) -> None:
        session = make_session(n=3)
        before = session.updated_at
        session.clear()
        assert session.updated_at >= before

    def test_add_message_after_clear_works(self) -> None:
        session = make_session(n=5)
        session.clear()
        session.add_message("user", "fresh start")
        assert len(session.messages) == 1
        assert session.messages[0]["content"] == "fresh start"


# ---------------------------------------------------------------------------
# SessionManager.get_or_create
# ---------------------------------------------------------------------------


class TestSessionManagerGetOrCreate:
    def test_creates_new_session_for_unknown_key(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        session = mgr.get_or_create("new:key")
        assert isinstance(session, Session)
        assert session.key == "new:key"
        assert session.messages == []

    def test_returns_cached_session_on_second_call(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        s1 = mgr.get_or_create("ch:1")
        s2 = mgr.get_or_create("ch:1")
        assert s1 is s2

    def test_different_keys_create_different_sessions(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        sa = mgr.get_or_create("ch:a")
        sb = mgr.get_or_create("ch:b")
        assert sa is not sb
        assert sa.key == "ch:a"
        assert sb.key == "ch:b"

    def test_loads_persisted_session_from_disk(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        session = mgr.get_or_create("persist:1")
        session.add_message("user", "saved message")
        mgr.save(session)

        # New manager — empty cache, must read from disk
        mgr2 = make_manager(tmp_path)
        loaded = mgr2.get_or_create("persist:1")
        assert len(loaded.messages) == 1
        assert loaded.messages[0]["content"] == "saved message"


# ---------------------------------------------------------------------------
# SessionManager.save / load round-trip
# ---------------------------------------------------------------------------


class TestSessionManagerSaveLoad:
    def test_save_creates_jsonl_file(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        session = make_session(key="sl:1", n=3)
        mgr.save(session)
        files = list((tmp_path / "sessions").glob("*.jsonl"))
        assert len(files) == 1

    def test_round_trip_preserves_messages(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        session = make_session(key="sl:2", n=5)
        session.metadata["foo"] = "bar"
        session.last_consolidated = 2
        mgr.save(session)

        mgr2 = make_manager(tmp_path)
        loaded = mgr2.get_or_create("sl:2")
        assert len(loaded.messages) == 5
        assert loaded.messages[0]["content"] == "msg0"
        assert loaded.messages[4]["content"] == "msg4"
        assert loaded.metadata["foo"] == "bar"
        assert loaded.last_consolidated == 2

    def test_round_trip_preserves_message_roles(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        session = Session(key="sl:3")
        session.add_message("user", "q")
        session.add_message("assistant", "a")
        session.add_message("tool", "r", tool_call_id="x", name="fn")
        mgr.save(session)

        mgr2 = make_manager(tmp_path)
        loaded = mgr2.get_or_create("sl:3")
        assert loaded.messages[0]["role"] == "user"
        assert loaded.messages[1]["role"] == "assistant"
        assert loaded.messages[2]["role"] == "tool"
        assert loaded.messages[2]["tool_call_id"] == "x"

    def test_round_trip_preserves_created_at(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        session = Session(key="sl:4")
        original_ts = session.created_at
        mgr.save(session)

        mgr2 = make_manager(tmp_path)
        loaded = mgr2.get_or_create("sl:4")
        # Allow sub-second float precision
        assert abs((loaded.created_at - original_ts).total_seconds()) < 1

    def test_save_overwrites_previous_file(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        session = make_session(key="sl:5", n=2)
        mgr.save(session)
        session.add_message("user", "extra")
        mgr.save(session)

        mgr2 = make_manager(tmp_path)
        loaded = mgr2.get_or_create("sl:5")
        assert len(loaded.messages) == 3

    def test_load_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        result = mgr._load("nonexistent:key")
        assert result is None

    def test_load_recovers_gracefully_from_corrupt_file(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        corrupt_path = sessions_dir / "corrupt_key.jsonl"
        corrupt_path.write_text("not valid json\n", encoding="utf-8")

        result = mgr._load("corrupt:key")
        assert result is None

    def test_save_updates_cache(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        session = make_session(key="sl:6", n=1)
        mgr.save(session)
        cached = mgr.get_or_create("sl:6")
        assert cached is session


# ---------------------------------------------------------------------------
# SessionManager.list_sessions
# ---------------------------------------------------------------------------


class TestSessionManagerListSessions:
    def test_returns_empty_list_when_no_sessions(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        assert mgr.list_sessions() == []

    def test_lists_all_saved_sessions(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        for key in ("chan:1", "chan:2", "chan:3"):
            mgr.save(make_session(key=key, n=1))
        sessions = mgr.list_sessions()
        assert len(sessions) == 3

    def test_each_entry_has_required_fields(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        mgr.save(make_session(key="ls:check", n=1))
        entry = mgr.list_sessions()[0]
        assert "key" in entry
        assert "created_at" in entry
        assert "updated_at" in entry
        assert "path" in entry

    def test_sorted_most_recently_updated_first(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        old_session = Session(key="ls:old")
        old_session.add_message("user", "old")
        old_session.updated_at = datetime.now() - timedelta(hours=2)
        mgr.save(old_session)

        new_session = Session(key="ls:new")
        new_session.add_message("user", "new")
        new_session.updated_at = datetime.now()
        mgr.save(new_session)

        listing = mgr.list_sessions()
        assert listing[0]["key"] == "ls:new"
        assert listing[1]["key"] == "ls:old"

    def test_skips_files_without_metadata_header(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        # File with no metadata _type header
        bad = sessions_dir / "bad_session.jsonl"
        bad.write_text(json.dumps({"role": "user", "content": "hi"}) + "\n", encoding="utf-8")

        mgr.save(make_session(key="ls:good", n=1))
        listing = mgr.list_sessions()
        # Only the good session should appear
        assert len(listing) == 1
        assert listing[0]["key"] == "ls:good"


# ---------------------------------------------------------------------------
# SessionManager._evict_if_needed
# ---------------------------------------------------------------------------


class TestSessionManagerEvict:
    def test_no_eviction_below_limit(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        for i in range(10):
            mgr.get_or_create(f"ch:{i}")
        assert len(mgr._cache) == 10

    def test_evicts_oldest_sessions_over_limit(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        max_sessions = SessionManager.MAX_CACHED_SESSIONS

        base_time = datetime.now()
        for i in range(max_sessions + 5):
            session = Session(key=f"ch:{i}")
            session.updated_at = base_time + timedelta(seconds=i)
            mgr._cache[f"ch:{i}"] = session

        mgr._evict_if_needed()

        assert len(mgr._cache) == max_sessions
        # Oldest 5 (ch:0..ch:4) must be gone
        for i in range(5):
            assert f"ch:{i}" not in mgr._cache

    def test_evicts_to_exactly_max_limit(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        max_sessions = SessionManager.MAX_CACHED_SESSIONS

        base_time = datetime.now()
        for i in range(max_sessions + 10):
            session = Session(key=f"ev:{i}")
            session.updated_at = base_time + timedelta(seconds=i)
            mgr._cache[f"ev:{i}"] = session

        mgr._evict_if_needed()
        assert len(mgr._cache) == max_sessions

    def test_newest_sessions_retained_after_eviction(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        max_sessions = SessionManager.MAX_CACHED_SESSIONS
        total = max_sessions + 3

        base_time = datetime.now()
        for i in range(total):
            session = Session(key=f"keep:{i}")
            session.updated_at = base_time + timedelta(seconds=i)
            mgr._cache[f"keep:{i}"] = session

        mgr._evict_if_needed()

        # Newest max_sessions keys should remain
        for i in range(3, total):
            assert f"keep:{i}" in mgr._cache


# ---------------------------------------------------------------------------
# SessionManager._get_session_path (path traversal protection)
# ---------------------------------------------------------------------------


class TestSessionManagerPathTraversal:
    def test_normal_key_resolves_inside_sessions_dir(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        path = mgr._get_session_path("telegram:12345")
        assert path.is_relative_to((tmp_path / "sessions").resolve())

    def test_colon_replaced_with_underscore_in_filename(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        path = mgr._get_session_path("chan:999")
        assert ":" not in path.name

    def test_path_traversal_attempt_sanitized_to_safe_path(self, tmp_path: Path) -> None:
        # safe_filename() replaces all path-unsafe chars (/, \, .) sequences with underscores,
        # so traversal strings like ../../etc/passwd are neutralized — they resolve inside
        # the sessions directory rather than escaping it.
        mgr = make_manager(tmp_path)
        path = mgr._get_session_path("../../etc/passwd")
        assert path.is_relative_to((tmp_path / "sessions").resolve())

    def test_dotdot_in_key_sanitized_to_safe_path(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        path = mgr._get_session_path("chan:..\\..\\secret")
        assert path.is_relative_to((tmp_path / "sessions").resolve())

    def test_slash_in_key_is_sanitized_or_rejected(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        # Either sanitizes (resolves inside sessions dir) or raises ValueError
        try:
            path = mgr._get_session_path("chan/subdir:1")
            assert path.is_relative_to((tmp_path / "sessions").resolve())
        except ValueError:
            pass  # Also acceptable — path traversal blocked

    def test_valid_key_with_numbers_and_dash(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        path = mgr._get_session_path("slack:C01234-XYZ")
        assert path.suffix == ".jsonl"
        assert path.is_relative_to((tmp_path / "sessions").resolve())


# ---------------------------------------------------------------------------
# SessionManager.invalidate
# ---------------------------------------------------------------------------


class TestSessionManagerInvalidate:
    def test_invalidate_removes_from_cache(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        mgr.get_or_create("inv:1")
        assert "inv:1" in mgr._cache
        mgr.invalidate("inv:1")
        assert "inv:1" not in mgr._cache

    def test_invalidate_nonexistent_key_is_noop(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        mgr.invalidate("never:existed")  # must not raise

    def test_after_invalidate_get_or_create_reloads_from_disk(self, tmp_path: Path) -> None:
        mgr = make_manager(tmp_path)
        session = make_session(key="inv:reload", n=2)
        mgr.save(session)
        mgr.invalidate("inv:reload")
        reloaded = mgr.get_or_create("inv:reload")
        assert len(reloaded.messages) == 2
