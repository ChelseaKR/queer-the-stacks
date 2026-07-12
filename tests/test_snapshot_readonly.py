"""Library-safety guardrail — "writes to source DBs = 0" (merge-blocking).

The real Calibre/KOReader databases are sacred. These tests prove two things:

1. :func:`ingest.snapshot.open_readonly` yields a connection that *cannot* write
   — any mutation raises ``sqlite3.OperationalError``.
2. A full ingest (Calibre + KOReader + daily activity) leaves the source files'
   bytes **identical** — verified by SHA-256 before/after.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path

import pytest
from ingest.calibre import load_library
from ingest.koreader import load_daily_activity, load_stats
from ingest.snapshot import (
    _SIDECAR_SUFFIXES,
    SnapshotIntegrityError,
    open_readonly,
    snapshot,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wal_source_with_uncheckpointed_rows(path: Path) -> sqlite3.Connection:
    """Build a WAL-mode DB whose latest committed rows live only in the ``-wal``.

    Returns the *still-open* writer connection so the ``-wal``/``-shm`` sidecars
    remain on disk (simulating a mid-write Calibre/KOReader). The caller must
    close it. Row 1 is folded into the main file; rows 2 and 3 are committed but
    left in the WAL, so a naive copy of the main file alone would miss them.
    """
    writer = sqlite3.connect(path)
    writer.execute("PRAGMA journal_mode=WAL;")
    writer.execute("PRAGMA wal_autocheckpoint=0;")  # never auto-fold the WAL
    writer.execute("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT);")
    writer.execute("INSERT INTO books (id, title) VALUES (1, 'in-main');")
    writer.commit()
    writer.execute("PRAGMA wal_checkpoint(TRUNCATE);")  # row 1 -> main file
    writer.execute("INSERT INTO books (id, title) VALUES (2, 'in-wal-A');")
    writer.execute("INSERT INTO books (id, title) VALUES (3, 'in-wal-B');")
    writer.commit()  # committed, but only in the WAL
    return writer


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


def test_snapshot_of_wal_source_is_consistent(workdir: Path) -> None:
    """A mid-write (WAL-present) source snapshots to a consistent standalone DB.

    This is FIX-02: copying only the main file yields a *torn* copy that
    ``immutable=1`` cannot recover; the backup path folds the WAL in so the
    snapshot sees every committed row.
    """
    src = workdir / "metadata.db"
    writer = _wal_source_with_uncheckpointed_rows(src)
    try:
        # The live source really is mid-write: a WAL sidecar exists on disk.
        assert (workdir / "metadata.db-wal").exists()

        # Demonstrate the bug the fix closes: a naive main-file-only copy read
        # through immutable=1 silently drops the committed-but-unmerged WAL rows.
        naive = workdir / "naive-copy.db"
        shutil.copy2(src, naive)
        with open_readonly(naive) as conn:
            naive_titles = {r[0] for r in conn.execute("SELECT title FROM books")}
        assert "in-wal-A" not in naive_titles  # torn: WAL data is missing

        # The real snapshot is transactionally consistent and standalone.
        snap = snapshot(src, workdir / "snapshots")
        assert not any(
            (snap.parent / f"{snap.name}{suffix}").exists() for suffix in _SIDECAR_SUFFIXES
        )
        with open_readonly(snap) as conn:
            titles = {r[0] for r in conn.execute("SELECT title FROM books")}
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        assert titles == {"in-main", "in-wal-A", "in-wal-B"}
        assert integrity == "ok"
    finally:
        writer.close()


def test_snapshot_of_wal_source_leaves_source_unmutated(workdir: Path) -> None:
    """Snapshotting a mid-write source never writes to its main file (guardrail)."""
    src = workdir / "metadata.db"
    writer = _wal_source_with_uncheckpointed_rows(src)
    try:
        before = _sha(src)
        snapshot(src, workdir / "snapshots")
        assert _sha(src) == before, "snapshot must not mutate the source main file"
    finally:
        writer.close()


def test_snapshot_missing_source(workdir: Path) -> None:
    with pytest.raises(FileNotFoundError):
        snapshot(workdir / "absent.db", workdir / "snapshots")


def test_snapshot_fails_loudly_on_unrecoverable_source(workdir: Path) -> None:
    """An unreadable/corrupt source aborts with a visible error, never a bad read.

    FIX-02 "excellent" bar: ingest either succeeds on retry or fails loudly —
    it must never hand a reader a silently inconsistent snapshot.
    """
    corrupt = workdir / "corrupt.db"
    corrupt.write_bytes(b"this is not a sqlite database " * 64)
    with pytest.raises(SnapshotIntegrityError):
        snapshot(corrupt, workdir / "snapshots")
