"""Read per-book reading statistics from Kobo's native ``KoboReader.sqlite``.

Strictly read-only (see :mod:`ingest.snapshot`). Kobo stores per-book state in a
single ``content`` table that mixes one row per book *and* one row per chapter
of that book. Top-level "book" rows carry ``ContentType = 6``; chapter rows can
also carry ``ContentType = 6`` on some firmware versions but point back at their
parent via ``BookID``. :func:`_top_level_rows` keeps only the volume row per
book — the one whose ``BookID`` is empty or equal to its own ``ContentID``.

There is no per-session log in ``content`` (unlike KOReader's
``page_stat_data``), so :attr:`~ingest.models.ReadingStat.sessions` is always
``0`` here — an honest "unknown", not a guess.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ingest.models import ReadingStat
from ingest.snapshot import columns, open_snapshot, table_exists

#: Kobo's ContentType for a top-level book/volume (chapters use other values,
#: though some firmware reuses 6 for chapters too — see module docstring).
BOOK_CONTENT_TYPE = 6

#: Kobo's ReadStatus: 0 = unread, 1 = reading, 2 = finished.
READ_STATUS_FINISHED = 2


def _normalize_authors(raw: str) -> tuple[str, ...]:
    """Kobo's ``Attribution`` is a single free-text, comma-separated author string."""
    parts = [p.strip() for p in raw.split(",")]
    return tuple(p for p in parts if p)


def _parse_timestamp(raw: str) -> int:
    """Parse Kobo's ISO-8601 ``DateLastRead`` into unix seconds; ``0`` if unparsable."""
    text = raw.strip()
    if not text:
        return 0
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp())


def _top_level_rows(conn: sqlite3.Connection, cols: frozenset[str]) -> list[sqlite3.Row]:
    """Select ``ContentType = 6`` rows, deduplicated to one row per book volume.

    Kobo's ``content`` table stores one row per chapter alongside the top-level
    volume row for the same book. The volume row is identified by ``BookID``
    being empty/NULL or equal to its own ``ContentID`` (a chapter row's
    ``BookID`` points at its parent volume's ``ContentID`` instead).
    """
    rows = list(
        conn.execute(
            "SELECT * FROM content WHERE ContentType = ? ORDER BY rowid",
            (BOOK_CONTENT_TYPE,),
        ).fetchall()
    )
    if "MimeType" in cols:
        rows = [r for r in rows if r["MimeType"]]
    if "ContentID" not in cols:
        return rows
    grouped: dict[str, sqlite3.Row] = {}
    for r in rows:
        content_id = str(r["ContentID"])
        book_id = r["BookID"] if "BookID" in cols else None
        is_volume = not book_id or book_id == content_id
        group_key = str(book_id) if book_id else content_id
        if group_key not in grouped or is_volume:
            grouped[group_key] = r
    return [grouped[k] for k in sorted(grouped)]


def _title_key(title: str, authors: tuple[str, ...]) -> str:
    """Fallback join key, matching :func:`ingest.unify.normalize_key` (koreader.py's idiom)."""
    from ingest.unify import normalize_key

    return normalize_key(title, authors)


def read_stats(conn: sqlite3.Connection) -> list[ReadingStat]:
    """Read per-book stats from an open read-only Kobo connection."""
    if not table_exists(conn, "content"):
        return []
    cols = columns(conn, "content")
    stats: list[ReadingStat] = []
    for r in _top_level_rows(conn, cols):
        title = str(r["Title"]) if "Title" in cols and r["Title"] else ""
        authors = (
            _normalize_authors(str(r["Attribution"]))
            if "Attribution" in cols and r["Attribution"]
            else ()
        )
        total_pages = (
            int(r["___NumPages"]) if "___NumPages" in cols and r["___NumPages"] is not None else 0
        )
        pct = (
            int(r["___PercentRead"])
            if "___PercentRead" in cols and r["___PercentRead"] is not None
            else 0
        )
        read_status = (
            int(r["ReadStatus"]) if "ReadStatus" in cols and r["ReadStatus"] is not None else 0
        )
        if read_status == READ_STATUS_FINISHED and total_pages > 0:
            pages_read = total_pages
        elif total_pages > 0:
            pages_read = round(pct / 100 * total_pages)
        else:
            pages_read = 0
        read_time = (
            int(r["TimeSpentReading"])
            if "TimeSpentReading" in cols and r["TimeSpentReading"] is not None
            else 0
        )
        last_read = (
            _parse_timestamp(str(r["DateLastRead"]))
            if "DateLastRead" in cols and r["DateLastRead"]
            else 0
        )
        stats.append(
            ReadingStat(
                key=_title_key(title, authors),
                title=title,
                authors=authors,
                pages_read=pages_read,
                total_pages=total_pages,
                read_time_seconds=read_time,
                last_read_ts=last_read,
                sessions=0,  # Kobo's `content` table has no per-session log.
                highlights=0,  # not tracked in `content`; annotations are a future source
            )
        )
    return stats


def load_stats(kobo_db: Path, snapshot_dir: Path) -> list[ReadingStat]:
    """Snapshot the Kobo DB and return all stats — the read-only entry point."""
    with open_snapshot(kobo_db, snapshot_dir) as conn:
        return read_stats(conn)
