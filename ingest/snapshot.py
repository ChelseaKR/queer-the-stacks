"""The library-safety layer: snapshot-first, strictly read-only DB access.

Hard guardrail (README): the real Calibre ``metadata.db`` and KOReader
``statistics.sqlite`` are *sacred*. We never open them for writing and we never
risk corrupting them. Two complementary protections live here:

1. :func:`snapshot` copies the source file's bytes to a private snapshot before
   anything reads it. The reader works on the copy, so even a pathological SQLite
   side effect (e.g. ``-wal`` checkpoint) can never touch the original.
2. :func:`open_readonly` opens *any* SQLite file through a ``mode=ro`` +
   ``immutable=1`` URI and pins ``PRAGMA query_only=ON``. A write attempt raises
   ``sqlite3.OperationalError`` — proven by the read-only guardrail test.

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


class ReadOnlyViolation(Exception):
    """Raised if code attempts to obtain a writable handle to a source DB."""


def snapshot(src: Path, dest_dir: Path) -> Path:
    """Copy ``src`` into ``dest_dir`` and return the snapshot path.

    The copy is read with :func:`shutil.copy2` (which opens the source
    read-only) so the original is never opened for writing. The snapshot is what
    every reader consumes.
    """
    src = Path(src)
    if not src.is_file():
        raise FileNotFoundError(f"source database not found: {src}")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{src.stem}.snapshot{src.suffix or '.db'}"
    shutil.copy2(src, dest)
    return dest


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
