"""Ingest orchestration (``stacks refresh``) and diagnostics (``stacks doctor``).

`refresh` walks the read-only ingest path for the configured sources (or the demo
world), unifies the result, and writes it to the persisted :class:`~ingest.store.Store`.
It skips re-ingesting when the source files' mtimes are unchanged, so the
dashboard stays cheap. `doctor` validates configuration and read-only access
without mutating anything — the human-facing preflight check.

Live kosync is only used when fully configured; tests drive the real-source path
with on-disk SQLite fixtures and no network.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ingest.calibre import load_library
from ingest.config import Config
from ingest.kobo import load_stats as load_kobo_stats
from ingest.koreader import load_daily_activity, load_stats
from ingest.models import DailyActivity, ReadingState
from ingest.snapshot import columns, open_readonly
from ingest.store import Store
from ingest.unify import unify


@dataclass(frozen=True)
class RefreshResult:
    refreshed: bool
    n_states: int
    refreshed_at: int
    reason: str


def source_mtimes(config: Config) -> dict[str, int]:
    """Integer mtimes of the configured source files that currently exist."""
    out: dict[str, int] = {}
    for name, path in (
        ("calibre", config.calibre_db),
        ("koreader", config.koreader_db),
        ("kobo", config.kobo_db),
    ):
        if path is not None and path.is_file():
            out[name] = int(path.stat().st_mtime)
    return out


def _ingest_demo(config: Config) -> tuple[list[ReadingState], list[DailyActivity]]:
    from ingest.demo import build_demo_dbs, demo_kosync

    demo_dir = config.data_dir / "demo"
    metadata_db, statistics_db = build_demo_dbs(demo_dir)
    snap = config.snapshot_dir
    books = load_library(metadata_db, snap, retrieved_at="2026-06-05")
    stats = load_stats(statistics_db, snap)
    activity = load_daily_activity(statistics_db, snap)
    states = unify(books, stats, demo_kosync())
    return states, activity


def _ingest_real(config: Config) -> tuple[list[ReadingState], list[DailyActivity]]:
    snap = config.snapshot_dir
    books = load_library(config.calibre_db, snap) if config.calibre_db else []
    stats = load_stats(config.koreader_db, snap) if config.koreader_db else []
    stats = stats + (load_kobo_stats(config.kobo_db, snap) if config.kobo_db else [])
    activity = load_daily_activity(config.koreader_db, snap) if config.koreader_db else []
    progress_source = _kosync(config)
    states = unify(books, stats, progress_source)
    return states, activity


def _kosync(config: Config):  # type: ignore[no-untyped-def]
    if not config.kosync_configured:
        return None
    from ingest.kosync import KosyncClient  # pragma: no cover - constructed only in real deploys

    return KosyncClient(  # pragma: no cover
        username=config.kosync_user or "",
        userkey_md5=config.kosync_key or "",
        host=config.kosync_host or "",
    )


def ingest_states(config: Config) -> tuple[list[ReadingState], list[DailyActivity]]:
    """Run the read-only ingest path for the demo world or the real sources."""
    return _ingest_demo(config) if config.demo else _ingest_real(config)


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

    states, activity = ingest_states(config)
    store.save(states, activity, refreshed_at=now, source_mtimes=current)
    return RefreshResult(
        refreshed=True,
        n_states=len(states),
        refreshed_at=now,
        reason="demo world" if config.demo else "ingested from sources",
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
        if config.kobo_db is not None:
            checks.extend(_check_source("Kobo", config.kobo_db, "content"))
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
