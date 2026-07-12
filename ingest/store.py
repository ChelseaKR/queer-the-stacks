"""Persisted derived app-state — a small SQLite key/value store under ``data/``.

The dashboard reads unified reading state + per-day activity from here instead of
re-snapshotting the real libraries on every request. The store also records when
the data was refreshed and the source files' mtimes, so :mod:`ingest.refresh` can
skip work when nothing changed. It also caches per-key kosync progress with a
fetched-at timestamp, so a refresh only re-fetches keys whose underlying
``ReadingStat`` changed (see the kosync-progress-cache section below).

This is *derived* state about the user's own reading; it is sensitive and stays
local (``data/`` is git-ignored). It is the app's own writable database — wholly
separate from the read-only source libraries.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from ingest.models import DailyActivity, DeviceProgress, ReadingState
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
_PROGRESS_KEY = "kosync_progress"


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

    # --- kosync progress cache ----------------------------------------------
    #
    # Per-key cross-device progress (see ingest.refresh.fetch_progress), kept
    # with a fingerprint of the local ReadingStat that produced the key and a
    # fetched-at timestamp. This lets a refresh skip re-fetching keys whose
    # underlying stat has not changed since the last successful fetch, instead
    # of re-issuing a kosync GET for every book on every refresh.

    def cached_progress(self) -> dict[str, DeviceProgress]:
        """Cached device progress from the last fetch, keyed by stat key.

        Only keys that actually resolved to progress are included. A key that
        was checked but had no progress ("no progress yet") is tracked
        internally so :meth:`stale_progress_keys` can tell "checked, none
        found" apart from "never checked" — but it has no ``DeviceProgress``
        to return here.
        """
        raw = self._get(_PROGRESS_KEY)
        if not isinstance(raw, dict):
            return {}
        out: dict[str, DeviceProgress] = {}
        for key, entry in raw.items():
            if not isinstance(entry, dict) or not entry.get("found"):
                continue
            out[str(key)] = DeviceProgress(
                document=str(entry.get("document", "")),
                percentage=float(entry.get("percentage", 0.0)),
                device=str(entry.get("device", "unknown")),
                timestamp=int(entry.get("timestamp", 0)),
            )
        return out

    def stale_progress_keys(self, signatures: dict[str, str]) -> set[str]:
        """Keys in ``signatures`` that need a fresh kosync fetch.

        ``signatures`` maps a stat key to a cheap fingerprint of its current
        local reading state. A key is stale (needs re-fetching) if it has no
        cached entry yet, or if its stored fingerprint no longer matches —
        everything else can safely reuse :meth:`cached_progress`.
        """
        raw = self._get(_PROGRESS_KEY)
        cached = raw if isinstance(raw, dict) else {}
        stale: set[str] = set()
        for key, sig in signatures.items():
            entry = cached.get(key)
            if not isinstance(entry, dict) or entry.get("signature") != sig:
                stale.add(key)
        return stale

    def save_progress(
        self,
        progress: dict[str, DeviceProgress],
        signatures: dict[str, str],
        fetched_at: int,
    ) -> None:
        """Persist resolved kosync progress, replacing the prior cache.

        ``signatures`` should cover every stat key considered this refresh
        (whether or not it resolved to progress) so the next refresh's
        :meth:`stale_progress_keys` call has a complete picture; ``progress``
        need only carry the keys that actually resolved.
        """
        entries: dict[str, dict[str, object]] = {}
        for key, sig in signatures.items():
            dp = progress.get(key)
            entry: dict[str, object] = {
                "signature": sig,
                "fetched_at": int(fetched_at),
                "found": dp is not None,
            }
            if dp is not None:
                entry.update(
                    document=dp.document,
                    percentage=dp.percentage,
                    device=dp.device,
                    timestamp=dp.timestamp,
                )
            entries[key] = entry
        self._put(_PROGRESS_KEY, entries)
