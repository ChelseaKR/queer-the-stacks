"""Read per-book reading statistics from KOReader's statistics.sqlite.

Strictly read-only (see :mod:`ingest.snapshot`). KOReader's modern schema stores
one row per book in ``book`` (``md5``, ``title``, ``authors``, ``pages``,
``total_read_time``, ``total_read_pages``, ``last_open``) and one row per page
view in ``page_stat_data`` (``id_book``, ``page``, ``start_time``, ``duration``).

Sessions are reconstructed by grouping a book's page views whenever the gap
between consecutive views exceeds :data:`SESSION_GAP_SECONDS` — the same notion
KOReader itself uses for "reading sessions".
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ingest.models import DailyActivity, ReadingStat
from ingest.snapshot import columns, open_snapshot, table_exists

#: Seconds in a day — used to bucket page views into calendar days for streaks.
SECONDS_PER_DAY = 86400

#: A gap longer than this between page views starts a new reading session.
SESSION_GAP_SECONDS = 3600


def _normalize_authors(raw: str) -> tuple[str, ...]:
    """KOReader stores authors newline- or comma-separated; normalize to a tuple."""
    parts = [p.strip() for chunk in raw.split("\n") for p in chunk.split(",")]
    return tuple(p for p in parts if p)


def _count_sessions(conn: sqlite3.Connection, id_book: int) -> int:
    if not table_exists(conn, "page_stat_data"):
        return 0
    rows = conn.execute(
        "SELECT start_time FROM page_stat_data WHERE id_book = ? ORDER BY start_time",
        (id_book,),
    ).fetchall()
    times = [int(r["start_time"]) for r in rows if r["start_time"] is not None]
    if not times:
        return 0
    sessions = 1
    for prev, cur in zip(times, times[1:], strict=False):
        if cur - prev > SESSION_GAP_SECONDS:
            sessions += 1
    return sessions


def read_stats(conn: sqlite3.Connection) -> list[ReadingStat]:
    """Read per-book stats from an open read-only KOReader connection."""
    if not table_exists(conn, "book"):
        return []
    cols = columns(conn, "book")
    stats: list[ReadingStat] = []
    rows = conn.execute("SELECT * FROM book ORDER BY id").fetchall()
    for r in rows:
        id_book = int(r["id"])
        md5 = str(r["md5"]) if "md5" in cols and r["md5"] else ""
        title = str(r["title"]) if "title" in cols and r["title"] else ""
        authors = (
            _normalize_authors(str(r["authors"])) if "authors" in cols and r["authors"] else ()
        )
        total_pages = int(r["pages"]) if "pages" in cols and r["pages"] is not None else 0
        read_pages = (
            int(r["total_read_pages"])
            if "total_read_pages" in cols and r["total_read_pages"] is not None
            else 0
        )
        read_time = (
            int(r["total_read_time"])
            if "total_read_time" in cols and r["total_read_time"] is not None
            else 0
        )
        last_open = int(r["last_open"]) if "last_open" in cols and r["last_open"] is not None else 0
        highlights = (
            int(r["highlights"]) if "highlights" in cols and r["highlights"] is not None else 0
        )
        stats.append(
            ReadingStat(
                key=md5 or _title_key(title, authors),
                title=title,
                authors=authors,
                pages_read=read_pages,
                total_pages=total_pages,
                read_time_seconds=read_time,
                last_read_ts=last_open,
                sessions=_count_sessions(conn, id_book),
                highlights=highlights,
            )
        )
    return stats


def read_daily_activity(conn: sqlite3.Connection) -> list[DailyActivity]:
    """Aggregate page views into per-day reading activity (for streaks + Wrapped).

    Returns one :class:`DailyActivity` per calendar day that had any reading,
    sorted ascending by day. Empty if the page-level table is absent.
    """
    if not table_exists(conn, "page_stat_data"):
        return []
    rows = conn.execute(
        "SELECT start_time, duration FROM page_stat_data WHERE start_time IS NOT NULL"
    ).fetchall()
    by_day: dict[int, list[int]] = {}
    for r in rows:
        day = int(r["start_time"]) // SECONDS_PER_DAY
        by_day.setdefault(day, [0, 0])  # [seconds, pages]
        by_day[day][0] += int(r["duration"] or 0)
        by_day[day][1] += 1
    return [
        DailyActivity(day_ordinal=day, seconds=secs_pages[0], pages=secs_pages[1])
        for day, secs_pages in sorted(by_day.items())
    ]


def load_daily_activity(statistics_db: Path, snapshot_dir: Path) -> list[DailyActivity]:
    """Snapshot the KOReader DB and return per-day activity (read-only)."""
    with open_snapshot(statistics_db, snapshot_dir) as conn:
        return read_daily_activity(conn)


def _title_key(title: str, authors: tuple[str, ...]) -> str:
    """Fallback join key when a book has no md5 (matches :func:`ingest.unify.book_key`)."""
    from ingest.unify import normalize_key

    return normalize_key(title, authors)


def load_stats(statistics_db: Path, snapshot_dir: Path) -> list[ReadingStat]:
    """Snapshot the KOReader DB and return all stats — the read-only entry point."""
    with open_snapshot(statistics_db, snapshot_dir) as conn:
        return read_stats(conn)
