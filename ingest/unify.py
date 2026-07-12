"""Unify Calibre metadata + KOReader stats + device progress into reading state.

This produces the one list the dashboard renders: every book the user owns or has
read, with its catalog facts, local reading stats, and freshest cross-device
progress, classified as currently-reading / finished / unread.

Matching is *solely* by a normalized ``title|first-author`` key
(:func:`normalize_key`); ``Book.identifiers`` is never consulted. The KOReader
md5 (``ReadingStat.key``) is **not** a join key — it is only used to look up
cross-device progress for an already-matched stat (see :func:`_progress_for`).
A work/edition identity layer that would join on identifiers is future work
(ideation FIX-03). Everything is deterministic (stable sorts, normalized keys)
so the unified state is reproducible — the merge-blocking reproducibility
metric.
"""

from __future__ import annotations

import re

from ingest.kosync import ProgressSource
from ingest.models import (
    Book,
    DeviceProgress,
    ReadingStat,
    ReadingState,
    ReadingStatus,
)

_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
#: At/above this fraction a book is considered finished even without a page match.
FINISHED_THRESHOLD = 0.99


def normalize_key(title: str, authors: tuple[str, ...] | list[str]) -> str:
    """A stable join key from a title + first author, lowercased and de-punctuated."""
    first_author = authors[0] if authors else ""
    raw = f"{title}|{first_author}".lower()
    raw = _NON_ALNUM.sub(" ", raw)
    return _WS.sub(" ", raw).strip()


def book_key(book: Book) -> str:
    return normalize_key(book.title, book.author_names)


def _status(stat: ReadingStat | None, progress: tuple[DeviceProgress, ...]) -> ReadingStatus:
    pct = 0.0
    if progress:
        pct = max(p.percentage for p in progress)
    elif stat:
        pct = stat.percent_complete
    if (stat and stat.is_finished) or pct >= FINISHED_THRESHOLD:
        return ReadingStatus.FINISHED
    if pct > 0.0 or (stat and stat.read_time_seconds > 0):
        return ReadingStatus.READING
    return ReadingStatus.UNREAD


def unify(
    books: list[Book],
    stats: list[ReadingStat],
    progress_source: ProgressSource | None = None,
) -> list[ReadingState]:
    """Merge catalog books, reading stats, and device progress into reading state.

    Books and stats are matched by :func:`normalize_key`. A stat with no matching
    book still appears (it is something the user read that is not in Calibre).

    ``progress_source`` must already be a resolved, in-memory lookup (e.g. a
    :class:`~ingest.kosync.FixtureKosync` built by
    :func:`ingest.refresh.fetch_progress`) — ``unify`` performs no network I/O
    and no longer swallows lookup errors. Batching, bounded concurrency, and
    per-key error capture all happen upstream, once per refresh, not once per
    book here.
    """
    stats_by_key: dict[str, ReadingStat] = {}
    for stat in stats:
        stats_by_key.setdefault(normalize_key(stat.title, stat.authors), stat)

    states: list[ReadingState] = []
    used_stat_keys: set[str] = set()

    for book in sorted(books, key=lambda b: (b.title.lower(), b.book_id)):
        key = book_key(book)
        matched = stats_by_key.get(key)
        if matched is not None:
            used_stat_keys.add(key)
        progress = _progress_for(matched, progress_source)
        states.append(
            ReadingState(
                title=book.title,
                authors=book.author_names,
                status=_status(matched, progress),
                book=book,
                stat=matched,
                progress=progress,
            )
        )

    # Stats with no matching Calibre book — surfaced so reading history is complete.
    for key, stat in sorted(stats_by_key.items()):
        if key in used_stat_keys:
            continue
        progress = _progress_for(stat, progress_source)
        states.append(
            ReadingState(
                title=stat.title,
                authors=stat.authors,
                status=_status(stat, progress),
                book=None,
                stat=stat,
                progress=progress,
            )
        )
    return states


def _progress_for(
    stat: ReadingStat | None, source: ProgressSource | None
) -> tuple[DeviceProgress, ...]:
    if stat is None or source is None or not stat.key:
        return ()
    # A plain in-memory lookup by now (see ingest.refresh.fetch_progress) — no
    # network call, no exception to degrade from, so nothing to swallow here.
    dp = source.progress_for(stat.key)
    return (dp,) if dp is not None else ()


def currently_reading(states: list[ReadingState]) -> list[ReadingState]:
    """Books in progress, freshest first (by last read / progress timestamp)."""
    reading = [s for s in states if s.status is ReadingStatus.READING]
    return sorted(reading, key=_recency_key, reverse=True)


def finished(states: list[ReadingState]) -> list[ReadingState]:
    done = [s for s in states if s.status is ReadingStatus.FINISHED]
    return sorted(done, key=_recency_key, reverse=True)


def _recency_key(state: ReadingState) -> tuple[int, float]:
    ts = 0
    if state.progress:
        ts = max(p.timestamp for p in state.progress)
    elif state.stat:
        ts = state.stat.last_read_ts
    return ts, state.percent_complete
