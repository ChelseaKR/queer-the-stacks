"""Library-safety guardrail — "writes to source DBs = 0" (merge-blocking).

The real Calibre/KOReader databases are sacred. These tests prove two things:

1. :func:`ingest.snapshot.open_readonly` yields a connection that *cannot* write
   — any mutation raises ``sqlite3.OperationalError``.
2. A full ingest (Calibre + KOReader + daily activity) leaves the source files'
   bytes **identical** — verified by SHA-256 before/after.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
from ingest.calibre import load_library
from ingest.koreader import load_daily_activity, load_stats
from ingest.snapshot import open_readonly, snapshot


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_open_readonly_rejects_writes(demo_dbs: tuple[Path, Path]) -> None:
    metadata_db, _ = demo_dbs
    with open_readonly(metadata_db) as conn:
        # Reads are fine.
        assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] > 0
        # Writes must be impossible.
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE evil (x INTEGER)")
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("UPDATE books SET title = 'corrupted'")


def test_full_ingest_does_not_mutate_sources(demo_dbs: tuple[Path, Path], workdir: Path) -> None:
    metadata_db, statistics_db = demo_dbs
    before = (_sha(metadata_db), _sha(statistics_db))

    snap = workdir / "snapshots"
    load_library(metadata_db, snap)
    load_stats(statistics_db, snap)
    load_daily_activity(statistics_db, snap)

    after = (_sha(metadata_db), _sha(statistics_db))
    assert before == after, "ingest must never alter the source databases"


def test_snapshot_is_a_separate_file(demo_dbs: tuple[Path, Path], workdir: Path) -> None:
    metadata_db, _ = demo_dbs
    snap = snapshot(metadata_db, workdir / "snapshots")
    assert snap != metadata_db
    assert snap.exists()
    assert _sha(snap) == _sha(metadata_db)  # faithful copy


def test_open_readonly_missing_file(workdir: Path) -> None:
    with pytest.raises(FileNotFoundError), open_readonly(workdir / "nope.db"):
        pass
