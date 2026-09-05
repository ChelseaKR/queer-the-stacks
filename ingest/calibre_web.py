"""Read per-book read-state from Calibre-Web's own ``app.db``.

Strictly read-only and snapshot-first (see :mod:`ingest.snapshot`). Calibre-Web
keeps its *own* SQLite database — ``app.db``, separate from Calibre's
``metadata.db`` — for everything Calibre itself does not store: users, shelves,
and the per-user read-state this module reads.

Schema (read from upstream ``cps/ub.py``):

* ``book_read_link(id, book_id, user_id, read_status, last_modified,
  last_time_started_reading, times_started_reading)``. ``read_status`` is
  ``0`` unread / ``1`` finished / ``2`` in progress. Installs older than the
  ``read_status`` migration (Calibre-Web 0.6.4 and earlier) carry a plain
  ``is_read BOOLEAN`` instead — the era upstream's
  ``UPDATE book_read_link SET 'read_status' = 1 WHERE is_read`` migrates from.
  Both are read here.
* ``kobo_reading_state(id, user_id, book_id, last_modified, priority_timestamp)``
  with ``kobo_statistics(kobo_reading_state_id, spent_reading_minutes, …)`` and
  ``kobo_bookmark(kobo_reading_state_id, progress_percent, …)`` hanging off it.
  These three arrived with Kobo-sync support (absent in 0.6.4), so every one is
  probed before it is queried.

**``app.db`` holds no titles.** ``book_read_link.book_id`` is a foreign key into
Calibre's ``books.id``, so a read-state row can only be named by the Calibre
library it belongs to. Callers therefore pass the already-loaded
:class:`~ingest.models.Book` list, and a row whose book is not in that catalog
is dropped rather than surfaced as an untitled entry.

**What Calibre-Web measures, and what it does not.** It records *that* a book is
finished, and — only when Kobo sync has been used — minutes spent reading and a
position percentage. It never records page counts, so ``pages_read`` and
``total_pages`` stay ``0``: an honest "unknown", never a page count invented to
make a percentage come out. The finished/position signal is carried by a
:class:`~ingest.models.DeviceProgress` from the ``Calibre-Web`` device instead,
which is what lets this merge through the existing ``unify`` join with **zero
changes to** :mod:`ingest.unify` — ``unify`` already classifies a book finished
from device progress at or above its threshold.

The one thing this deliberately drops: a row that says ``read_status = 2``
(in progress) while carrying no measured position and no measured time. Nothing
in the shared vocabulary distinguishes "started, position unknown" from "0% of
the way in", and emitting a stat for it would flip
:attr:`~ingest.models.ReadingState.progress_recorded` to true and draw a 0%
meter — asserting a measurement that was never taken, which is the exact failure
that property exists to prevent. Such rows are skipped; see
``tests/test_calibre_web.py``.

Multi-user is a privacy question, not a merge question: ``app.db`` can hold
several people's read-state, and blending a housemate's into this reader's
dashboard would be silently wrong. With more than one reader present and no
``user`` configured, this raises :class:`CalibreWebUserError` rather than
guessing.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from ingest.models import Book, DeviceProgress, ReadingStat
from ingest.snapshot import columns, open_snapshot, table_exists

#: Calibre-Web's ``ReadBook`` status constants (``cps/ub.py``).
STATUS_UNREAD = 0
STATUS_FINISHED = 1
STATUS_IN_PROGRESS = 2

#: The device name stamped onto progress that came from Calibre-Web, so the
#: dashboard can say which endpoint asserted it.
DEVICE = "Calibre-Web"

#: Prefix :func:`ingest.calibre.read_books` gives every ``Book.book_id``; the
#: bridge between ``book_read_link.book_id`` and the loaded catalog.
_CALIBRE_ID_PREFIX = "calibre:"


class CalibreWebUserError(Exception):
    """Raised when *whose* read-state to import cannot be answered unambiguously.

    Either the configured reader is not a user of this Calibre-Web instance, or
    several readers have read-state and none was configured. Failing loudly is
    the point: the alternative is quietly importing somebody else's reading.
    """


@dataclass(frozen=True)
class CalibreWebState:
    """What one Calibre-Web ``app.db`` asserts about a reader's books.

    ``progress`` is keyed by :attr:`ingest.models.ReadingStat.key`, ready to be
    merged into the same in-memory progress map ``unify`` already reads.
    """

    stats: tuple[ReadingStat, ...] = ()
    progress: dict[str, DeviceProgress] = field(default_factory=dict)


@dataclass(frozen=True)
class _KoboSync:
    """The measured half of a read-state row, when Kobo sync has written one."""

    read_time_seconds: int = 0
    percent: Optional[float] = None  # 0..1; None means "no position was recorded"
    last_modified_ts: int = 0


def _parse_timestamp(raw: object) -> int:
    """Parse one of Calibre-Web's ``DateTime`` columns into unix seconds.

    SQLAlchemy stores them as ``YYYY-MM-DD HH:MM:SS[.ffffff]`` text, written by
    ``datetime.datetime.utcnow`` — naive, but UTC — so a naive value is read as
    UTC rather than as this host's local time. Anything unparsable is ``0``: the
    honest "no timestamp", not a guess.
    """
    if raw is None:
        return 0
    text = str(raw).strip()
    if not text:
        return 0
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


def _int_or_zero(value: object) -> int:
    """Coerce a nullable numeric column to ``int``; ``0`` when absent or unusable.

    SQLite is dynamically typed, so a column declared ``INTEGER`` can still hold
    text. Anything that is not a number reads as ``0`` — the honest "nothing
    usable was recorded" — rather than raising mid-ingest.
    """
    if isinstance(value, int | float):
        return int(value)
    return 0


def _join_key(title: str, authors: tuple[str, ...]) -> str:
    """The join key ``unify`` matches on (koreader.py / kobo.py's idiom)."""
    from ingest.unify import normalize_key

    return normalize_key(title, authors)


def _known_user_names(conn: sqlite3.Connection) -> list[str]:
    if not table_exists(conn, "user") or "name" not in columns(conn, "user"):
        return []
    rows = conn.execute("SELECT name FROM user WHERE name IS NOT NULL ORDER BY id").fetchall()
    return [str(r["name"]) for r in rows if str(r["name"]).strip()]


def _user_ids_with_read_state(conn: sqlite3.Connection) -> list[int]:
    if "user_id" not in columns(conn, "book_read_link"):
        return []
    rows = conn.execute(
        "SELECT DISTINCT user_id FROM book_read_link WHERE user_id IS NOT NULL ORDER BY user_id"
    ).fetchall()
    return [int(r["user_id"]) for r in rows]


def resolve_user_id(conn: sqlite3.Connection, user: Optional[str] = None) -> Optional[int]:
    """Decide whose read-state to import; ``None`` means "every row in the file".

    A configured ``user`` is matched case-insensitively against ``user.name``.
    With no name configured, a file holding exactly one reader's read-state needs
    no choice; a file holding more than one raises rather than blending them.
    """
    if not table_exists(conn, "book_read_link"):
        return None
    if user and user.strip():
        return _named_user_id(conn, user.strip())
    user_ids = _user_ids_with_read_state(conn)
    if len(user_ids) <= 1:
        return None
    raise CalibreWebUserError(
        f"{len(user_ids)} Calibre-Web users have read-state in this app.db; "
        "set [calibre_web] user (or STACKS_CALIBRE_WEB_USER) to say whose to import, "
        "rather than blending another reader's history into yours"
    )


def _named_user_id(conn: sqlite3.Connection, user: str) -> int:
    wanted = user.casefold()
    names = _known_user_names(conn)
    for name in names:
        if name.casefold() == wanted:
            row = conn.execute("SELECT id FROM user WHERE name = ? LIMIT 1", (name,)).fetchone()
            if row is not None:
                return int(row["id"])
    listed = ", ".join(names) if names else "none found"
    raise CalibreWebUserError(
        f"Calibre-Web has no user named {user!r} (users in this app.db: {listed})"
    )


def _read_status(row: sqlite3.Row, cols: frozenset[str]) -> Optional[int]:
    """The row's read status, across both recorded schema eras; ``None`` if unsaid."""
    if "read_status" in cols and row["read_status"] is not None:
        return int(row["read_status"])
    if "is_read" in cols and row["is_read"] is not None:
        return STATUS_FINISHED if int(row["is_read"]) else STATUS_UNREAD
    return None


def _kobo_minutes_by_state(conn: sqlite3.Connection) -> dict[int, int]:
    """``kobo_reading_state.id`` → minutes Calibre-Web recorded against it."""
    if not table_exists(conn, "kobo_statistics"):
        return {}
    wanted = {"kobo_reading_state_id", "spent_reading_minutes"}
    if not wanted <= columns(conn, "kobo_statistics"):
        return {}
    rows = conn.execute(
        "SELECT kobo_reading_state_id, spent_reading_minutes FROM kobo_statistics"
    ).fetchall()
    return {
        int(r["kobo_reading_state_id"]): _int_or_zero(r["spent_reading_minutes"])
        for r in rows
        if r["kobo_reading_state_id"] is not None
    }


def _kobo_percent_by_state(conn: sqlite3.Connection) -> dict[int, float]:
    """``kobo_reading_state.id`` → the synced position, as a 0..1 fraction."""
    if not table_exists(conn, "kobo_bookmark"):
        return {}
    wanted = {"kobo_reading_state_id", "progress_percent"}
    if not wanted <= columns(conn, "kobo_bookmark"):
        return {}
    rows = conn.execute(
        "SELECT kobo_reading_state_id, progress_percent FROM kobo_bookmark"
    ).fetchall()
    out: dict[int, float] = {}
    for r in rows:
        if r["kobo_reading_state_id"] is None or r["progress_percent"] is None:
            continue
        out[int(r["kobo_reading_state_id"])] = max(
            0.0, min(1.0, float(r["progress_percent"]) / 100)
        )
    return out


def _kobo_sync_by_book(conn: sqlite3.Connection, user_id: Optional[int]) -> dict[int, _KoboSync]:
    """Map ``book_id`` → the Kobo-sync measurements Calibre-Web holds for it.

    Empty for any install without Kobo-sync support (the tables are absent) or
    that has simply never synced a Kobo — in both cases the read-state rows
    still carry finished/unfinished, just nothing measured.
    """
    if not table_exists(conn, "kobo_reading_state"):
        return {}
    state_cols = columns(conn, "kobo_reading_state")
    if "book_id" not in state_cols:
        return {}
    query = "SELECT * FROM kobo_reading_state"
    params: tuple[int, ...] = ()
    if user_id is not None and "user_id" in state_cols:
        query += " WHERE user_id = ?"
        params = (user_id,)
    rows = conn.execute(query + " ORDER BY id", params).fetchall()
    if not rows:
        return {}

    minutes = _kobo_minutes_by_state(conn)
    percents = _kobo_percent_by_state(conn)
    has_modified = "last_modified" in state_cols
    out: dict[int, _KoboSync] = {}
    for r in rows:
        if r["book_id"] is None:
            continue
        state_id = int(r["id"])
        out[int(r["book_id"])] = _KoboSync(
            read_time_seconds=minutes.get(state_id, 0) * 60,
            percent=percents.get(state_id),
            last_modified_ts=_parse_timestamp(r["last_modified"] if has_modified else None),
        )
    return out


def _books_by_calibre_id(books: list[Book]) -> dict[int, Book]:
    """Index the loaded Calibre catalog by the integer id ``app.db`` refers to."""
    indexed: dict[int, Book] = {}
    for book in books:
        if not book.book_id.startswith(_CALIBRE_ID_PREFIX):
            continue
        raw = book.book_id[len(_CALIBRE_ID_PREFIX) :]
        if raw.isdigit():
            indexed.setdefault(int(raw), book)
    return indexed


def _stat_for(book: Book, row: sqlite3.Row, cols: frozenset[str], sync: _KoboSync) -> ReadingStat:
    started_ts = (
        _parse_timestamp(row["last_time_started_reading"])
        if "last_time_started_reading" in cols
        else 0
    )
    sessions = _int_or_zero(row["times_started_reading"]) if "times_started_reading" in cols else 0
    return ReadingStat(
        key=_join_key(book.title, book.author_names),
        title=book.title,
        authors=book.author_names,
        # Calibre-Web records no page counts at all — 0/0 is the honest unknown
        # here, and the device progress carries the position instead.
        pages_read=0,
        total_pages=0,
        read_time_seconds=sync.read_time_seconds,
        last_read_ts=started_ts,
        sessions=sessions,
        highlights=0,  # app.db stores bookmarks (EPUB CFIs), never highlights
    )


def read_state(
    conn: sqlite3.Connection,
    books: list[Book],
    *,
    user: Optional[str] = None,
) -> CalibreWebState:
    """Read one reader's Calibre-Web read-state from an open read-only connection.

    ``books`` is the Calibre catalog this ``app.db`` accompanies — the only place
    a title lives. Rows are emitted only where Calibre-Web actually measured
    something (see the module docstring).
    """
    if not table_exists(conn, "book_read_link"):
        return CalibreWebState()
    cols = columns(conn, "book_read_link")
    if "book_id" not in cols:
        return CalibreWebState()
    user_id = resolve_user_id(conn, user)
    by_calibre_id = _books_by_calibre_id(books)
    kobo_sync = _kobo_sync_by_book(conn, user_id)

    query = "SELECT * FROM book_read_link"
    params: tuple[int, ...] = ()
    if user_id is not None and "user_id" in cols:
        query += " WHERE user_id = ?"
        params = (user_id,)
    rows = conn.execute(query + " ORDER BY book_id", params).fetchall()

    stats: list[ReadingStat] = []
    progress: dict[str, DeviceProgress] = {}
    for row in rows:
        if row["book_id"] is None:
            continue
        book_id = int(row["book_id"])
        book = by_calibre_id.get(book_id)
        if book is None:
            # app.db stores no titles, so a row whose Calibre book is missing
            # cannot be named. Dropping it beats inventing a placeholder.
            continue
        sync = kobo_sync.get(book_id, _KoboSync())
        percent = 1.0 if _read_status(row, cols) == STATUS_FINISHED else sync.percent
        if percent is None and sync.read_time_seconds <= 0:
            # Nothing measured: an in-progress flag with no position and no time
            # would render as "0% read", which is a claim, not an absence.
            continue
        stat = _stat_for(book, row, cols, sync)
        stats.append(stat)
        if percent is None:
            continue
        row_modified = _parse_timestamp(row["last_modified"]) if "last_modified" in cols else 0
        progress[stat.key] = DeviceProgress(
            document=stat.key,
            percentage=percent,
            device=DEVICE,
            timestamp=max(sync.last_modified_ts, stat.last_read_ts, row_modified),
        )
    return CalibreWebState(stats=tuple(stats), progress=progress)


def load_state(
    app_db: Path,
    snapshot_dir: Path,
    books: list[Book],
    *,
    user: Optional[str] = None,
) -> CalibreWebState:
    """Snapshot Calibre-Web's ``app.db`` and read it — the read-only entry point."""
    with open_snapshot(app_db, snapshot_dir) as conn:
        return read_state(conn, books, user=user)
