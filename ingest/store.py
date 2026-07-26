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
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ingest.models import Book, DailyActivity, DeviceProgress, ReadingState
from ingest.serde import (
    activity_from_dict,
    activity_to_dict,
    book_from_dict,
    book_to_dict,
    state_from_dict,
    state_to_dict,
)

_STATES_KEY = "reading_states"
_ACTIVITY_KEY = "daily_activity"
_REFRESHED_KEY = "refreshed_at"
_MTIMES_KEY = "source_mtimes"
_PROGRESS_KEY = "kosync_progress"
_CATALOG_KEY = "catalog_pool"
_VIEW_REVISION_KEY = "view_revision"


@dataclass(frozen=True)
class CatalogSourceUpdate:
    """One catalog source's result from the current refresh attempt."""

    source_id: str
    books: tuple[Book, ...] = ()
    ok: bool = True
    error: str = ""


@dataclass(frozen=True)
class CatalogSourceStatus:
    """Persisted operational status for one configured public catalog source."""

    source_id: str
    status: str
    attempted_at: int
    fetched_at: Optional[int]
    candidate_count: int
    error: str = ""


@dataclass(frozen=True)
class CatalogPoolStatus:
    """Aggregate catalog freshness/egress state suitable for the dashboard."""

    outbound_mode: str = "off"
    state: str = "off"
    attempted_at: Optional[int] = None
    candidate_count: int = 0
    sources: tuple[CatalogSourceStatus, ...] = ()


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
    _UPSERT = (
        "INSERT INTO app_state (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
    )
    _BUMP_VIEW_REVISION = (
        "INSERT INTO app_state (key, value) VALUES (?, '1') "
        "ON CONFLICT(key) DO UPDATE SET "
        "value = CAST(CAST(app_state.value AS INTEGER) + 1 AS TEXT)"
    )

    def _put(self, key: str, value: object) -> None:
        """Persist one independent value and commit it immediately."""
        self._conn.execute(self._UPSERT, (key, json.dumps(value)))
        self._conn.commit()

    def _put_view_state(self, key: str, value: object) -> None:
        """Atomically persist one view input and advance its cache revision."""
        with self._conn:
            self._conn.execute(self._UPSERT, (key, json.dumps(value)))
            self._conn.execute(self._BUMP_VIEW_REVISION, (_VIEW_REVISION_KEY,))

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
        """Persist a full refresh of derived state atomically.

        All view rows are written in ONE transaction: a crash (or concurrent
        reader) can never observe new states paired with a stale
        ``refreshed_at``/``source_mtimes``/cache revision — it sees the whole
        refresh or none of it.
        """
        rows: list[tuple[str, object]] = [
            (_STATES_KEY, [state_to_dict(s) for s in states]),
            (_ACTIVITY_KEY, [activity_to_dict(a) for a in daily_activity]),
            (_REFRESHED_KEY, int(refreshed_at)),
            (_MTIMES_KEY, source_mtimes or {}),
        ]
        with self._conn:  # commits on success, rolls back on error
            self._conn.executemany(self._UPSERT, [(k, json.dumps(v)) for k, v in rows])
            self._conn.execute(self._BUMP_VIEW_REVISION, (_VIEW_REVISION_KEY,))

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

    def view_revision(self) -> int:
        """Monotonic cache key for every persisted input rendered by the app."""
        raw = self._get(_VIEW_REVISION_KEY)
        return int(raw) if isinstance(raw, int) else 0

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

    def stale_progress_keys(
        self,
        signatures: dict[str, str],
        *,
        now: Optional[int] = None,
        ttl_seconds: Optional[int] = None,
    ) -> set[str]:
        """Keys in ``signatures`` that need a fresh kosync fetch.

        ``signatures`` maps a stat key to a cheap fingerprint of its current
        local reading state. A key is stale (needs re-fetching) if it has no
        cached entry yet, if its stored fingerprint no longer matches, or if
        the bounded remote-progress TTL has expired. The TTL matters because a
        different device can advance kosync without changing any local source
        database mtime or ``ReadingStat``.
        """
        raw = self._get(_PROGRESS_KEY)
        cached = raw if isinstance(raw, dict) else {}
        stale: set[str] = set()
        for key, sig in signatures.items():
            entry = cached.get(key)
            expired = False
            if isinstance(entry, dict) and now is not None and ttl_seconds is not None:
                fetched_at = entry.get("fetched_at")
                expired = not isinstance(fetched_at, int) or now - fetched_at >= ttl_seconds
            if (
                not isinstance(entry, dict)
                or entry.get("signature") != sig
                or entry.get("error") is True
                or expired
            ):
                stale.add(key)
        return stale

    def progress_refresh_due(self, now: int, ttl_seconds: int) -> bool:
        """Whether any cached kosync key has reached its remote freshness bound."""
        raw = self._get(_PROGRESS_KEY)
        if not isinstance(raw, dict):
            return True
        if not raw:
            return False
        return any(
            not isinstance(entry, dict)
            or entry.get("error") is True
            or not isinstance(entry.get("fetched_at"), int)
            or now - int(entry["fetched_at"]) >= ttl_seconds
            for entry in raw.values()
        )

    def save_progress(
        self,
        progress: dict[str, DeviceProgress],
        signatures: dict[str, str],
        fetched_at: int,
        *,
        fetched_keys: Optional[set[str]] = None,
        failed_keys: Optional[set[str]] = None,
    ) -> None:
        """Persist resolved kosync progress, replacing the prior cache.

        ``signatures`` should cover every stat key considered this refresh
        (whether or not it resolved to progress) so the next refresh's
        :meth:`stale_progress_keys` call has a complete picture; ``progress``
        need only carry resolved or retained last-good values. ``failed_keys``
        stay explicit and immediately retryable without advancing their
        remote-freshness clock.
        """
        raw = self._get(_PROGRESS_KEY)
        previous = raw if isinstance(raw, dict) else {}
        entries: dict[str, dict[str, object]] = {}
        failures = failed_keys or set()
        for key, sig in signatures.items():
            dp = progress.get(key)
            old = previous.get(key)
            old = old if isinstance(old, dict) else {}
            fetched_this_time = fetched_keys is None or key in fetched_keys
            failed_this_time = key in failures
            entry: dict[str, object] = {
                "signature": sig,
                # Reusing a cached result must not reset its remote-freshness
                # clock; otherwise frequent local refreshes could postpone the
                # bounded TTL forever.
                "fetched_at": (
                    old.get("fetched_at")
                    if failed_this_time or not fetched_this_time
                    else int(fetched_at)
                ),
                "found": dp is not None,
                # Failed keys stay explicit and immediately retryable. Keeping
                # the marker also avoids the all-errors -> empty-cache case
                # suppressing top-level refreshes behind unchanged mtimes.
                "error": failed_this_time,
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

    # --- persisted public catalog candidate pool ----------------------------

    def load_catalog_candidates(self) -> tuple[Book, ...]:
        """Load the merged last-good candidate pool from configured sources."""
        raw = self._get(_CATALOG_KEY)
        if not isinstance(raw, dict):
            return ()
        sources = raw.get("sources")
        if not isinstance(sources, dict):
            return ()
        books: list[Book] = []
        for source_id in sorted(sources):
            entry = sources[source_id]
            if not isinstance(entry, dict) or not isinstance(entry.get("books"), list):
                continue
            for item in entry["books"]:
                if isinstance(item, dict):
                    try:
                        books.append(book_from_dict(item))
                    except KeyError, TypeError, ValueError:
                        continue
        from recommender.catalogs import merge_candidates

        return merge_candidates(tuple(books))

    def catalog_source_statuses(self) -> tuple[CatalogSourceStatus, ...]:
        raw = self._get(_CATALOG_KEY)
        sources = raw.get("sources") if isinstance(raw, dict) else None
        if not isinstance(sources, dict):
            return ()
        statuses: list[CatalogSourceStatus] = []
        for source_id in sorted(sources):
            entry = sources[source_id]
            if not isinstance(entry, dict):
                continue
            books = entry.get("books")
            statuses.append(
                CatalogSourceStatus(
                    source_id=source_id,
                    status=str(entry.get("status", "unknown")),
                    attempted_at=int(entry.get("attempted_at", 0)),
                    fetched_at=(
                        int(entry["fetched_at"])
                        if isinstance(entry.get("fetched_at"), int)
                        else None
                    ),
                    candidate_count=len(books) if isinstance(books, list) else 0,
                    error=str(entry.get("error", "")),
                )
            )
        return tuple(statuses)

    def catalog_attempted_at(self) -> Optional[int]:
        raw = self._get(_CATALOG_KEY)
        attempted = raw.get("attempted_at") if isinstance(raw, dict) else None
        return int(attempted) if isinstance(attempted, int) else None

    def catalog_pool_status(self) -> CatalogPoolStatus:
        raw = self._get(_CATALOG_KEY)
        mode = str(raw.get("outbound_mode", "off")) if isinstance(raw, dict) else "off"
        statuses = self.catalog_source_statuses()
        if mode != "public-metadata":
            state = "off"
        elif not statuses:
            state = "unconfigured"
        elif any(source.status == "error" for source in statuses):
            state = "degraded"
        else:
            state = "fresh"
        return CatalogPoolStatus(
            outbound_mode=mode,
            state=state,
            attempted_at=self.catalog_attempted_at(),
            candidate_count=len(self.load_catalog_candidates()),
            sources=statuses,
        )

    def catalog_refresh_due(self, now: int, ttl_seconds: int) -> bool:
        attempted = self.catalog_attempted_at()
        return attempted is None or now - attempted >= ttl_seconds

    def save_catalog_refresh(
        self,
        updates: tuple[CatalogSourceUpdate, ...],
        *,
        active_source_ids: set[str],
        attempted_at: int,
        outbound_mode: str,
    ) -> None:
        """Merge source results, retaining last-good books on source failure.

        Sources removed from configuration are removed from the active pool.
        A failed active source keeps its previously fetched public metadata and
        ``fetched_at`` while exposing the latest attempt/error in status.
        """
        previous = self._get(_CATALOG_KEY)
        old_sources = previous.get("sources") if isinstance(previous, dict) else {}
        old_sources = old_sources if isinstance(old_sources, dict) else {}
        by_id: Mapping[str, CatalogSourceUpdate] = {u.source_id: u for u in updates}
        sources: dict[str, object] = {}
        for source_id in sorted(active_source_ids):
            update = by_id.get(source_id)
            old = old_sources.get(source_id)
            old = old if isinstance(old, dict) else {}
            if update is None:
                sources[source_id] = old
                continue
            if update.ok:
                sources[source_id] = {
                    "status": "ok",
                    "attempted_at": attempted_at,
                    "fetched_at": attempted_at,
                    "error": "",
                    "books": [book_to_dict(book) for book in update.books],
                }
            else:
                sources[source_id] = {
                    "status": "error",
                    "attempted_at": attempted_at,
                    "fetched_at": old.get("fetched_at"),
                    "error": update.error,
                    "books": old.get("books", []),
                }
        self._put_view_state(
            _CATALOG_KEY,
            {
                "attempted_at": attempted_at,
                "outbound_mode": outbound_mode,
                "sources": sources,
            },
        )

    def save_catalog_mode(self, outbound_mode: str, active_source_ids: set[str]) -> None:
        """Record consent mode/configuration without making a fetch look attempted."""
        previous = self._get(_CATALOG_KEY)
        old = previous if isinstance(previous, dict) else {}
        old_sources = old.get("sources")
        old_sources = old_sources if isinstance(old_sources, dict) else {}
        updated = {
            "attempted_at": old.get("attempted_at"),
            "outbound_mode": outbound_mode,
            "sources": {
                source_id: old_sources[source_id]
                for source_id in sorted(active_source_ids)
                if source_id in old_sources
            },
        }
        if updated != old:
            self._put_view_state(_CATALOG_KEY, updated)
