"""Session management for conversation history."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.utils.helpers import ensure_dir, safe_filename

if TYPE_CHECKING:
    from nanobot.bus.event_bus import EventBus

# Word lists for human-readable session slugs
_ADJECTIVES = (
    "brave",
    "calm",
    "cool",
    "eager",
    "fast",
    "keen",
    "neat",
    "slim",
    "wise",
    "bold",
    "deep",
    "fair",
    "gold",
    "kind",
    "pure",
    "warm",
)
_NOUNS = (
    "fox",
    "owl",
    "elk",
    "bee",
    "ray",
    "oak",
    "gem",
    "arc",
    "sky",
    "bay",
    "dew",
    "fin",
    "ivy",
    "jet",
    "kit",
    "orb",
)


def _make_slug(key: str) -> str:
    """Generate a deterministic human-readable slug from a session key."""
    h = int(hashlib.md5(key.encode()).hexdigest(), 16)  # noqa: S324
    adj = _ADJECTIVES[h % len(_ADJECTIVES)]
    noun = _NOUNS[(h >> 8) % len(_NOUNS)]
    num = (h >> 16) % 100
    prefix = key.split(":")[0][:2] if ":" in key else "s"
    return f"{prefix}-{adj}-{noun}-{num}"


@dataclass
class Session:
    """
    A conversation session.

    Stores messages in JSONL format for easy reading and persistence.

    Important: Messages are append-only for LLM cache efficiency.
    The consolidation process writes summaries to MEMORY.md/HISTORY.md
    but does NOT modify the messages list or get_history() output.
    """

    key: str  # channel:chat_id
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    last_consolidated: int = 0  # Number of messages already consolidated to files

    @property
    def slug(self) -> str:
        """Human-readable display ID (e.g. 'tg-brave-fox-42')."""
        return _make_slug(self.key)

    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """Add a message to the session."""
        msg = {"role": role, "content": content, "timestamp": datetime.now().isoformat(), **kwargs}
        self.messages.append(msg)
        self.updated_at = datetime.now()

    def get_history(self, max_messages: int = 500) -> list[dict[str, Any]]:
        """Return unconsolidated messages for LLM input, aligned to a user turn."""
        unconsolidated = self.messages[self.last_consolidated :]
        sliced = unconsolidated[-max_messages:]

        # Drop leading non-user/non-context messages to avoid orphaned tool_result blocks
        for i, m in enumerate(sliced):
            if m.get("role") in ("user", "context"):
                sliced = sliced[i:]
                break

        out: list[dict[str, Any]] = []
        for m in sliced:
            entry: dict[str, Any] = {"role": m["role"], "content": m.get("content", "")}
            for k in ("tool_calls", "tool_call_id", "name"):
                if k in m:
                    entry[k] = m[k]
            out.append(entry)
        return out

    def clear(self) -> None:
        """Clear all messages and reset session to initial state."""
        self.messages = []
        self.last_consolidated = 0
        self.updated_at = datetime.now()


class SessionManager:
    """
    Manages conversation sessions.

    Sessions are stored as JSONL files in the sessions directory.
    """

    MAX_CACHED_SESSIONS = 50
    MAX_DISK_SESSIONS = 200
    MAX_AGE_DAYS = 30

    def __init__(self, workspace: Path, event_bus: EventBus | None = None):
        self.workspace = workspace
        self.sessions_dir = ensure_dir(self.workspace / "sessions")
        self.legacy_sessions_dir = Path.home() / ".nanobot" / "sessions"
        self._cache: dict[str, Session] = {}
        self._event_bus = event_bus
        self._cleanup_disk()

    def _get_session_path(self, key: str) -> Path:
        """Get the file path for a session (path-traversal safe)."""
        safe_key = safe_filename(key.replace(":", "_"))
        path = (self.sessions_dir / f"{safe_key}.jsonl").resolve()
        if not path.is_relative_to(self.sessions_dir.resolve()):
            raise ValueError(f"Invalid session key: {key}")
        return path

    def _get_legacy_session_path(self, key: str) -> Path:
        """Legacy global session path (~/.nanobot/sessions/)."""
        safe_key = safe_filename(key.replace(":", "_"))
        return self.legacy_sessions_dir / f"{safe_key}.jsonl"

    def _emit_event(self, event: str, payload: dict[str, Any]) -> None:
        """Fire-and-forget an event on the EventBus (non-blocking)."""
        if not self._event_bus:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._event_bus.emit(event, payload))
        except RuntimeError:
            pass  # No running loop (tests, startup)

    def get_or_create(self, key: str) -> Session:
        """
        Get an existing session or create a new one.

        Args:
            key: Session key (usually channel:chat_id).

        Returns:
            The session.
        """
        if key in self._cache:
            return self._cache[key]

        loaded = self._load(key)
        if loaded is None:
            session = Session(key=key)
            self._cache[key] = session
            self._evict_if_needed()
            self._emit_event("session.created", {"key": key, "slug": session.slug})
            return session

        self._cache[key] = loaded
        self._evict_if_needed()
        return loaded

    def _evict_if_needed(self) -> None:
        """Evict oldest sessions from cache when over limit."""
        if len(self._cache) <= self.MAX_CACHED_SESSIONS:
            return
        # Sort by updated_at, evict oldest
        sorted_keys = sorted(
            self._cache,
            key=lambda k: self._cache[k].updated_at,
        )
        to_evict = len(self._cache) - self.MAX_CACHED_SESSIONS
        for k in sorted_keys[:to_evict]:
            del self._cache[k]

    def _load(self, key: str) -> Session | None:
        """Load a session from disk."""
        path = self._get_session_path(key)
        if not path.exists():
            legacy_path = self._get_legacy_session_path(key)
            if legacy_path.exists():
                try:
                    shutil.move(str(legacy_path), str(path))
                    logger.info("Migrated session {} from legacy path", key)
                except Exception:
                    logger.exception("Failed to migrate session {}", key)

        if not path.exists():
            return None

        try:
            messages = []
            metadata = {}
            created_at = None
            last_consolidated = 0

            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    data = json.loads(line)

                    if data.get("_type") == "metadata":
                        metadata = data.get("metadata", {})
                        created_at = (
                            datetime.fromisoformat(data["created_at"])
                            if data.get("created_at")
                            else None
                        )
                        last_consolidated = data.get("last_consolidated", 0)
                    else:
                        messages.append(data)

            return Session(
                key=key,
                messages=messages,
                created_at=created_at or datetime.now(),
                metadata=metadata,
                last_consolidated=last_consolidated,
            )
        except Exception as e:
            logger.warning("Failed to load session {}: {}", key, e)
            return None

    def save(self, session: Session) -> None:
        """Save a session to disk."""
        path = self._get_session_path(session.key)

        with open(path, "w", encoding="utf-8") as f:
            metadata_line = {
                "_type": "metadata",
                "key": session.key,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "metadata": session.metadata,
                "last_consolidated": session.last_consolidated,
            }
            f.write(json.dumps(metadata_line, ensure_ascii=False) + "\n")
            for msg in session.messages:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")

        self._cache[session.key] = session
        self._emit_event(
            "session.message",
            {
                "key": session.key,
                "slug": session.slug,
                "messageCount": len(session.messages),
            },
        )

    def invalidate(self, key: str) -> None:
        """Remove a session from the in-memory cache."""
        removed = self._cache.pop(key, None)
        if removed:
            self._emit_event("session.ended", {"key": key, "slug": removed.slug})

    def list_sessions(self) -> list[dict[str, Any]]:
        """
        List all sessions.

        Returns:
            List of session info dicts.
        """
        sessions = []

        for path in self.sessions_dir.glob("*.jsonl"):
            try:
                # Read just the metadata line
                with open(path, encoding="utf-8") as f:
                    first_line = f.readline().strip()
                    if first_line:
                        data = json.loads(first_line)
                        if data.get("_type") == "metadata":
                            key = data.get("key") or path.stem.replace("_", ":", 1)
                            sessions.append(
                                {
                                    "key": key,
                                    "slug": _make_slug(key),
                                    "created_at": data.get("created_at"),
                                    "updated_at": data.get("updated_at"),
                                    "path": str(path),
                                }
                            )
            except Exception:
                continue

        return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)

    def _cleanup_disk(self) -> None:
        """Remove old session files on startup: by age and by count."""
        try:
            session_files = list(self.sessions_dir.glob("*.jsonl"))
            if not session_files:
                return

            cutoff = datetime.now() - timedelta(days=self.MAX_AGE_DAYS)
            removed_age = 0

            # Collect (path, updated_at) for sorting
            file_times: list[tuple[Path, datetime]] = []
            for path in session_files:
                try:
                    with open(path, encoding="utf-8") as f:
                        first_line = f.readline().strip()
                    if not first_line:
                        continue
                    data = json.loads(first_line)
                    updated = data.get("updated_at")
                    if updated:
                        dt = datetime.fromisoformat(updated)
                        if dt < cutoff:
                            path.unlink(missing_ok=True)
                            removed_age += 1
                            continue
                        file_times.append((path, dt))
                    else:
                        file_times.append((path, datetime.fromtimestamp(path.stat().st_mtime)))
                except Exception:
                    continue

            # Remove excess by count (keep most recent MAX_DISK_SESSIONS)
            removed_count = 0
            if len(file_times) > self.MAX_DISK_SESSIONS:
                file_times.sort(key=lambda x: x[1])
                excess = len(file_times) - self.MAX_DISK_SESSIONS
                for path, _ in file_times[:excess]:
                    path.unlink(missing_ok=True)
                    removed_count += 1

            if removed_age or removed_count:
                logger.info(
                    "Session cleanup: removed {} expired + {} excess (max {})",
                    removed_age,
                    removed_count,
                    self.MAX_DISK_SESSIONS,
                )
        except Exception as e:
            logger.warning("Session disk cleanup failed: {}", e)
