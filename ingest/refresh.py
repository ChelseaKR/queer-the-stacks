"""Ingest orchestration (``stacks refresh``) and diagnostics (``stacks doctor``).

`refresh` walks the read-only ingest path for the configured sources (or the demo
world), unifies the result, and writes it to the persisted :class:`~ingest.store.Store`.
It skips re-ingesting when the source files' mtimes are unchanged, so the
dashboard stays cheap. `doctor` validates configuration and read-only access
without mutating anything — the human-facing preflight check.

Live kosync is only used when fully configured; tests drive the real-source path
with on-disk SQLite fixtures and no network.

Kosync progress used to be fetched one sequential HTTP GET per book, *inside*
:func:`ingest.unify.unify`, with every failure silently swallowed — an N+1 with
no visible outcome. :func:`fetch_progress` replaces that: it batches every
non-empty stat key into a single bounded-concurrency step, run once per
refresh, before ``unify`` ever runs, with a captured ok/no-progress/error
outcome per key. ``unify`` now just reads the resulting in-memory map.
"""

from __future__ import annotations

import concurrent.futures
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ingest.calibre import load_library
from ingest.config import Config
from ingest.koreader import load_daily_activity, load_stats
from ingest.kosync import FixtureKosync, ProgressSource
from ingest.models import DailyActivity, DeviceProgress, ReadingStat, ReadingState
from ingest.snapshot import columns, open_readonly
from ingest.store import Store
from ingest.unify import unify


@dataclass(frozen=True)
class ProgressOutcome:
    """The captured result of fetching kosync progress for one stat key.

    Replaces the old blanket ``except Exception: return ()`` in ``unify`` —
    every key now has a visible outcome instead of a silent fallback.
    """

    key: str
    ok: bool  # False only on a transport/parse error fetching this key
    found: bool  # True if the source returned progress for this key
    error: str = ""  # non-empty iff ``ok`` is False


@dataclass(frozen=True)
class ProgressFetchResult:
    """The output of :func:`fetch_progress` — a resolved, in-memory progress map."""

    progress: dict[str, DeviceProgress] = field(default_factory=dict)
    outcomes: tuple[ProgressOutcome, ...] = ()
    fetched: int = 0
    errors: int = 0


def fetch_progress(
    source: Optional[ProgressSource],
    keys: Iterable[str],
    *,
    max_workers: int = 8,
) -> ProgressFetchResult:
    """Fetch kosync progress for ``keys`` with bounded concurrency.

    Each key gets its own :class:`ProgressOutcome` — ok/no-progress/error —
    instead of a blanket swallow. Dispatch and result assembly are both sorted
    by key, so the returned map and outcome order are deterministic regardless
    of which fetch happens to finish first (preserving the reproducibility
    gate even though fetches run concurrently).
    """
    sorted_keys = sorted({k for k in keys if k})
    if source is None or not sorted_keys:
        return ProgressFetchResult()

    def _fetch_one(key: str) -> tuple[str, Optional[DeviceProgress], Optional[str]]:
        try:
            dp = source.progress_for(key)
        except Exception as exc:  # noqa: BLE001 - captured as a visible outcome, not swallowed
            return key, None, f"{type(exc).__name__}: {exc}"
        return key, dp, None

    workers = max(1, min(max_workers, len(sorted_keys)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        # .map yields results in input order regardless of completion order,
        # so assembly below stays deterministic under concurrency.
        results = list(pool.map(_fetch_one, sorted_keys))

    progress: dict[str, DeviceProgress] = {}
    outcomes: list[ProgressOutcome] = []
    fetched = 0
    errors = 0
    for key, dp, error in results:
        if error is not None:
            outcomes.append(ProgressOutcome(key=key, ok=False, found=False, error=error))
            errors += 1
        elif dp is not None:
            progress[key] = dp
            outcomes.append(ProgressOutcome(key=key, ok=True, found=True))
            fetched += 1
        else:
            outcomes.append(ProgressOutcome(key=key, ok=True, found=False))

    return ProgressFetchResult(
        progress=progress, outcomes=tuple(outcomes), fetched=fetched, errors=errors
    )


def _stat_signature(stat: ReadingStat) -> str:
    """A cheap fingerprint of a stat's local reading state, for cache invalidation.

    If this hasn't changed since the last successful kosync fetch for the same
    key, the cached progress is reused instead of re-fetching.
    """
    return f"{stat.last_read_ts}:{stat.pages_read}:{stat.read_time_seconds}:{stat.sessions}"


def _resolve_progress(
    source: Optional[ProgressSource],
    stats: list[ReadingStat],
    store: Optional[Store],
    now: int,
) -> ProgressFetchResult:
    """Fetch fresh kosync progress only for keys whose stat changed; reuse the rest.

    Without a store (e.g. a bare call to :func:`ingest_states`), there is
    nothing to cache against, so every key is fetched fresh.
    """
    signatures = {stat.key: _stat_signature(stat) for stat in stats if stat.key}
    if not signatures:
        return ProgressFetchResult()
    if store is None:
        return fetch_progress(source, signatures.keys())

    stale = store.stale_progress_keys(signatures)
    fresh = fetch_progress(source, stale) if stale else ProgressFetchResult()

    reused = {
        key: dp
        for key, dp in store.cached_progress().items()
        if key in signatures and key not in stale
    }
    merged = {**reused, **fresh.progress}
    # A key whose fetch *errored* must stay stale: persisting its signature
    # would record it as "checked, no progress", silently suppressing retries
    # until the local stat changes — exactly the down-server-looks-like-no-
    # progress failure mode this module exists to kill. Dropping it from the
    # persisted signatures makes the next refresh re-fetch it.
    errored = {outcome.key for outcome in fresh.outcomes if not outcome.ok}
    persisted = {key: sig for key, sig in signatures.items() if key not in errored}
    store.save_progress(merged, persisted, fetched_at=now)

    return ProgressFetchResult(
        progress=merged, outcomes=fresh.outcomes, fetched=len(merged), errors=fresh.errors
    )


@dataclass(frozen=True)
class RefreshResult:
    refreshed: bool
    n_states: int
    refreshed_at: int
    reason: str
    progress_fetched: int = 0
    progress_errors: int = 0
    progress_outcomes: tuple[ProgressOutcome, ...] = ()


def source_mtimes(config: Config) -> dict[str, int]:
    """Integer mtimes of the configured source files that currently exist."""
    out: dict[str, int] = {}
    for name, path in (("calibre", config.calibre_db), ("koreader", config.koreader_db)):
        if path is not None and path.is_file():
            out[name] = int(path.stat().st_mtime)
    return out


def _ingest_demo(
    config: Config, store: Optional[Store] = None, now: int = 0
) -> tuple[list[ReadingState], list[DailyActivity], ProgressFetchResult]:
    from ingest.demo import build_demo_dbs, demo_kosync

    demo_dir = config.data_dir / "demo"
    metadata_db, statistics_db = build_demo_dbs(demo_dir)
    snap = config.snapshot_dir
    books = load_library(metadata_db, snap, retrieved_at="2026-06-05")
    stats = load_stats(statistics_db, snap)
    activity = load_daily_activity(statistics_db, snap)
    progress_result = _resolve_progress(demo_kosync(), stats, store, now)
    states = unify(books, stats, FixtureKosync(progress_result.progress))
    return states, activity, progress_result


def _ingest_real(
    config: Config, store: Optional[Store] = None, now: int = 0
) -> tuple[list[ReadingState], list[DailyActivity], ProgressFetchResult]:
    snap = config.snapshot_dir
    books = load_library(config.calibre_db, snap) if config.calibre_db else []
    stats = load_stats(config.koreader_db, snap) if config.koreader_db else []
    activity = load_daily_activity(config.koreader_db, snap) if config.koreader_db else []
    progress_result = _resolve_progress(_kosync(config), stats, store, now)
    states = unify(books, stats, FixtureKosync(progress_result.progress))
    return states, activity, progress_result


def _kosync(config: Config):  # type: ignore[no-untyped-def]
    if not config.kosync_configured:
        return None
    from ingest.kosync import KosyncClient  # pragma: no cover - constructed only in real deploys

    return KosyncClient(  # pragma: no cover
        username=config.kosync_user or "",
        userkey_md5=config.kosync_key or "",
        host=config.kosync_host or "",
    )


def _ingest_with_progress(
    config: Config, store: Optional[Store] = None, now: int = 0
) -> tuple[list[ReadingState], list[DailyActivity], ProgressFetchResult]:
    return _ingest_demo(config, store, now) if config.demo else _ingest_real(config, store, now)


def ingest_states(
    config: Config, store: Optional[Store] = None, now: int = 0
) -> tuple[list[ReadingState], list[DailyActivity]]:
    """Run the read-only ingest path for the demo world or the real sources."""
    states, activity, _progress = _ingest_with_progress(config, store, now)
    return states, activity


def refresh(config: Config, store: Store, now: int, *, force: bool = False) -> RefreshResult:
    """Re-ingest into the store, skipping when source mtimes are unchanged."""
    current = source_mtimes(config)
    unchanged = (
        not force
        and not config.demo
        and store.is_populated
        and bool(current)
        and current == store.source_mtimes()
    )
    if unchanged:
        states = store.load_states()
        return RefreshResult(
            refreshed=False,
            n_states=len(states),
            refreshed_at=store.refreshed_at() or 0,
            reason="sources unchanged since last refresh",
        )

    states, activity, progress_result = _ingest_with_progress(config, store, now)
    store.save(states, activity, refreshed_at=now, source_mtimes=current)
    return RefreshResult(
        refreshed=True,
        n_states=len(states),
        refreshed_at=now,
        reason="demo world" if config.demo else "ingested from sources",
        progress_fetched=progress_result.fetched,
        progress_errors=progress_result.errors,
        progress_outcomes=progress_result.outcomes,
    )


# --- doctor -----------------------------------------------------------------


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _check_source(label: str, path: Optional[Path], required_table: str) -> list[Check]:
    checks: list[Check] = []
    if path is None:
        checks.append(Check(f"{label} configured", False, "no path set (demo or unconfigured)"))
        return checks
    if not path.is_file():
        checks.append(Check(f"{label} file", False, f"not found: {path}"))
        return checks
    checks.append(Check(f"{label} file", True, str(path)))
    try:
        with open_readonly(path) as conn:
            has_table = bool(columns(conn, required_table))
        checks.append(
            Check(
                f"{label} read-only access",
                has_table,
                f"opened read-only; '{required_table}' table {'found' if has_table else 'missing'}",
            )
        )
    except Exception as exc:  # noqa: BLE001 - surface any access problem to the user
        checks.append(Check(f"{label} read-only access", False, f"{type(exc).__name__}: {exc}"))
    return checks


def doctor(config: Config, store: Optional[Store] = None) -> list[Check]:
    """Validate configuration + read-only access; never mutates anything."""
    checks: list[Check] = []
    checks.append(
        Check("mode", True, "demo (built-in offline library)" if config.demo else "real sources")
    )
    if not config.demo:
        checks.extend(_check_source("Calibre", config.calibre_db, "books"))
        checks.extend(_check_source("KOReader", config.koreader_db, "book"))
        checks.append(
            Check(
                "kosync",
                True,
                "configured (host + user + key present)"
                if config.kosync_configured
                else "not configured — progress will use KOReader stats only",
            )
        )
    checks.append(Check("data dir", True, str(config.data_dir)))
    if store is not None:
        if store.is_populated:
            checks.append(
                Check("app-state store", True, f"populated; refreshed_at={store.refreshed_at()}")
            )
        else:
            checks.append(Check("app-state store", True, "empty — run `stacks refresh`"))
    return checks
