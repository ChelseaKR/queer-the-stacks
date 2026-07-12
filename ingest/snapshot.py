"""The library-safety layer: snapshot-first, strictly read-only DB access.

Hard guardrail (README): the real Calibre ``metadata.db`` and KOReader
``statistics.sqlite`` are *sacred*. We never open them for writing and we never
risk corrupting them. Two complementary protections live here:

1. :func:`snapshot` copies the source into a private snapshot before anything
   reads it. The reader works on the copy, so even a pathological SQLite side
   effect (e.g. ``-wal`` checkpoint) can never touch the original. Crucially the
   copy is also *consistent*: if the live source has an active write-ahead log
   or rollback journal (a mid-write Calibre/KOReader), a plain byte copy of the
   main file alone would be **torn** — it would omit committed data still living
   in the ``-wal`` sidecar, and ``immutable=1`` (below) then suppresses SQLite's
   recovery so the reader silently sees stale/inconsistent state. To avoid that,
   when sidecars are present the copy is taken through SQLite's online backup
   API from a strictly read-only source handle, which reads a single
   transactionally-consistent snapshot (WAL folded in) into a standalone file.
   Every snapshot is then verified with ``PRAGMA integrity_check`` before it is
   handed to a reader; an unrecoverable source fails loudly with
   :class:`SnapshotIntegrityError` rather than yielding a silent bad read.
2. :func:`open_readonly` opens *any* SQLite file through a ``mode=ro`` +
   ``immutable=1`` URI and pins ``PRAGMA query_only=ON``. A write attempt raises
   ``sqlite3.OperationalError`` — proven by the read-only guardrail test. Because
   :func:`snapshot` produces a standalone, sidecar-free file, ``immutable=1`` is
   safe here: there is no WAL left to ignore.

The merge-blocking metric "writes to source DBs = 0" is enforced by these
mechanisms plus the test that asserts the source file's hash is unchanged after
a full ingest.
"""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

#: Sidecar suffixes SQLite writes next to a database while a transaction is in
#: flight. Their presence means the main file alone may be an inconsistent
#: (torn) view, so the snapshot must go through the consistent backup path.
_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


class ReadOnlyViolation(Exception):
    """Raised if code attempts to obtain a writable handle to a source DB."""


class SnapshotIntegrityError(Exception):
    """Raised when a snapshot cannot be made consistent (fails ``integrity_check``).

    Fail loudly: it is always preferable to abort an ingest with a visible reason
    than to hand a reader a silently torn/inconsistent copy of the library.
    """


def _has_sidecar(src: Path) -> bool:
    """True if ``src`` has a ``-wal``/``-shm``/``-journal`` sidecar on disk."""
    return any((src.parent / f"{src.name}{suffix}").exists() for suffix in _SIDECAR_SUFFIXES)


def _backup_copy(src: Path, dest: Path) -> None:
    """Copy ``src`` to ``dest`` via SQLite's online backup API.

    The source is opened strictly read-only (``mode=ro`` — *not* ``immutable``,
    so the WAL is honored) and never written to. ``Connection.backup`` reads a
    single transactionally-consistent snapshot, including data still in the WAL,
    and writes a standalone database (no sidecars) to ``dest``.
    """
    if dest.exists():
        dest.unlink()
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(dest)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _verify_integrity(path: Path) -> tuple[bool, str]:
    """Run ``PRAGMA integrity_check`` on ``path``; return ``(ok, detail)``.

    A file too corrupt to even open counts as a failure (never a silent pass).
    """
    try:
        with open_readonly(path) as conn:
            row = conn.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.DatabaseError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    result = str(row[0]) if row else "no result"
    return result == "ok", result


def snapshot(src: Path, dest_dir: Path) -> Path:
    """Copy ``src`` into ``dest_dir`` as a *consistent, verified* snapshot.

    The source is never opened for writing. With no sidecars present a plain
    :func:`shutil.copy2` is already consistent (and byte-faithful); when a
    ``-wal``/``-journal`` shows the source is mid-write, the copy goes through
    the online backup API so the snapshot captures a single consistent
    transaction rather than a torn main file. Either way the result is verified
    with ``PRAGMA integrity_check`` before being returned. If verification fails,
    the copy is retried once through the consistent backup path; a source that
    still cannot be snapshotted raises :class:`SnapshotIntegrityError`.
    """
    src = Path(src)
    if not src.is_file():
        raise FileNotFoundError(f"source database not found: {src}")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{src.stem}.snapshot{src.suffix or '.db'}"

    use_backup = _has_sidecar(src)
    last_detail = "not attempted"
    for _attempt in range(2):
        try:
            if use_backup:
                _backup_copy(src, dest)
            else:
                shutil.copy2(src, dest)
        except sqlite3.DatabaseError as exc:
            last_detail = f"copy failed: {type(exc).__name__}: {exc}"
            use_backup = True
            continue
        ok, last_detail = _verify_integrity(dest)
        if ok:
            return dest
        # A plain copy of a mid-write source can be torn; escalate to a
        # transactionally-consistent backup and try once more.
        use_backup = True
    raise SnapshotIntegrityError(
        f"could not produce a consistent snapshot of {src.name}: {last_detail}"
    )


@contextmanager
def open_readonly(path: Path) -> Iterator[sqlite3.Connection]:
    """Yield a strictly read-only connection to the SQLite file at ``path``.

    Opened via ``file:…?mode=ro&immutable=1`` and pinned with
    ``PRAGMA query_only=ON``; any attempt to mutate raises
    ``sqlite3.OperationalError``.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"database not found: {path}")
    uri = f"file:{path}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON;")
        yield conn
    finally:
        conn.close()


@contextmanager
def open_snapshot(src: Path, snapshot_dir: Path) -> Iterator[sqlite3.Connection]:
    """Snapshot ``src`` then yield a read-only connection to the snapshot.

    This is the canonical "touch the real library" entry point: callers never
    pass the live path to :func:`open_readonly` directly, they go through here so
    the snapshot-first invariant holds.
    """
    snap = snapshot(src, snapshot_dir)
    with open_readonly(snap) as conn:
        yield conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    """True iff a table named ``name`` exists (used to tolerate schema drift)."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def columns(conn: sqlite3.Connection, table: str) -> frozenset[str]:
    """Return the set of column names for ``table`` (empty if it is absent)."""
    if not table_exists(conn, table):
        return frozenset()
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return frozenset(str(r["name"]) for r in rows)
