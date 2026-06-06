"""Persisted derived app-state — a small SQLite key/value store under ``data/``.

The dashboard reads unified reading state + per-day activity from here instead of
re-snapshotting the real libraries on every request. The store also records when
the data was refreshed and the source files' mtimes, so :mod:`ingest.refresh` can
skip work when nothing changed.

This is *derived* state about the user's own reading; it is sensitive and stays
local (``data/`` is git-ignored). It is the app's own writable database — wholly
separate from the read-only source libraries.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from ingest.models import DailyActivity, ReadingState
from ingest.serde import (
    activity_from_dict,
    activity_to_dict,
    state_from_dict,
    state_to_dict,
)

_STATES_KEY = "reading_states"
_ACTIVITY_KEY = "daily_activity"
_REFRESHED_KEY = "refreshed_at"
_MTIMES_KEY = "source_mtimes"


class Store:
    """A tiny JSON-document store keyed by string, backed by SQLite."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- low-level kv -------------------------------------------------------
    def _put(self, key: str, value: object) -> None:
        self._conn.execute(
            "INSERT INTO app_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
        self._conn.commit()

    def _get(self, key: str) -> object:
        row = self._conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    # --- typed accessors ----------------------------------------------------
    def save(
        self,
        states: list[ReadingState],
        daily_activity: list[DailyActivity],
        refreshed_at: int,
        source_mtimes: Optional[dict[str, int]] = None,
    ) -> None:
        """Persist a full refresh of derived state atomically."""
        self._put(_STATES_KEY, [state_to_dict(s) for s in states])
        self._put(_ACTIVITY_KEY, [activity_to_dict(a) for a in daily_activity])
        self._put(_REFRESHED_KEY, int(refreshed_at))
        self._put(_MTIMES_KEY, source_mtimes or {})

    def load_states(self) -> list[ReadingState]:
        raw = self._get(_STATES_KEY)
        if not isinstance(raw, list):
            return []
        return [state_from_dict(d) for d in raw]

    def load_daily_activity(self) -> list[DailyActivity]:
        raw = self._get(_ACTIVITY_KEY)
        if not isinstance(raw, list):
            return []
        return [activity_from_dict(d) for d in raw]

    def refreshed_at(self) -> Optional[int]:
        raw = self._get(_REFRESHED_KEY)
        return int(raw) if isinstance(raw, int) else None

    def source_mtimes(self) -> dict[str, int]:
        raw = self._get(_MTIMES_KEY)
        return {str(k): int(v) for k, v in raw.items()} if isinstance(raw, dict) else {}

    @property
    def is_populated(self) -> bool:
        return self.refreshed_at() is not None
