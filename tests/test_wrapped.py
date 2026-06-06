"""Reading Wrapped: year scoping, standout reads, sourced theme breakdown."""

from __future__ import annotations

import datetime

from app.wrapped import compute_wrapped, year_bounds
from ingest.models import (
    Author,
    Book,
    DailyActivity,
    ReadingStat,
    ReadingState,
    ReadingStatus,
    Source,
    SourceKind,
    ThemeTag,
)

_EPOCH = datetime.date(1970, 1, 1).toordinal()


def _ordinal(y: int, m: int, d: int) -> int:
    return datetime.date(y, m, d).toordinal() - _EPOCH


def _finished_state(title: str, theme: str, read_seconds: int, ts: int) -> ReadingState:
    src = Source(SourceKind.CURATED_LIST, "curated-list:x", "2026-06-05", theme)
    book = Book(
        book_id=title, title=title, authors=(Author("A"),), theme_tags=(ThemeTag(theme, src),)
    )
    stat = ReadingStat(
        key=title,
        title=title,
        authors=("A",),
        pages_read=100,
        total_pages=100,
        read_time_seconds=read_seconds,
        last_read_ts=ts,
        sessions=3,
    )
    return ReadingState(
        title=title, authors=("A",), status=ReadingStatus.FINISHED, book=book, stat=stat
    )


def test_year_bounds() -> None:
    lo, hi = year_bounds(2024)
    assert lo == _ordinal(2024, 1, 1)
    assert hi == _ordinal(2025, 1, 1)


def test_wrapped_scopes_to_year() -> None:
    ts_2024 = int(datetime.datetime(2024, 6, 1, tzinfo=datetime.UTC).timestamp())
    ts_2023 = int(datetime.datetime(2023, 6, 1, tzinfo=datetime.UTC).timestamp())
    states = [
        _finished_state("In Year", "trans", 7200, ts_2024),
        _finished_state("Last Year", "trans", 9999, ts_2023),
    ]
    day = _ordinal(2024, 6, 1)
    activity = [DailyActivity(day_ordinal=day, seconds=3600, pages=40)]
    wrapped = compute_wrapped(states, activity, 2024)
    assert wrapped.books_finished == 1
    assert wrapped.standout_reads[0].title == "In Year"
    assert dict(wrapped.theme_breakdown).get("trans") == 1
    assert wrapped.days_read == 1


def test_standouts_ranked_by_time() -> None:
    ts = int(datetime.datetime(2024, 3, 1, tzinfo=datetime.UTC).timestamp())
    states = [
        _finished_state("Short", "a", 1000, ts),
        _finished_state("Long", "a", 9000, ts),
    ]
    wrapped = compute_wrapped(states, [], 2024)
    assert [r.title for r in wrapped.standout_reads] == ["Long", "Short"]
    assert wrapped.standout_reads[0].read_time_hours == 2.5


def test_wrapped_with_real_demo(states: list, daily_activity: list) -> None:
    # The demo canon was read in 2024 (timestamps ~1.71e9).
    wrapped = compute_wrapped(states, daily_activity, 2024)
    assert wrapped.books_finished >= 1
    assert wrapped.read_time_hours > 0
