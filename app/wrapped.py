"""A self-hosted "Reading Wrapped" — a private year-in-review.

No third-party service ever sees this. It is computed locally from the same
unified reading state + per-day activity the dashboard uses, scoped to a single
year. Standout reads are chosen by read time (a sourced, honest signal), and the
theme breakdown is built only from sourced theme tags.
"""

from __future__ import annotations

from dataclasses import dataclass

from ingest.koreader import SECONDS_PER_DAY
from ingest.models import DailyActivity, ReadingState, ReadingStatus


def _jan1_ordinal(year: int) -> int:
    import datetime

    return datetime.date(year, 1, 1).toordinal() - datetime.date(1970, 1, 1).toordinal()


def year_bounds(year: int) -> tuple[int, int]:
    """Return (first_day_ordinal, last_day_ordinal_exclusive) for ``year``."""
    return _jan1_ordinal(year), _jan1_ordinal(year + 1)


@dataclass(frozen=True)
class StandoutRead:
    title: str
    authors: tuple[str, ...]
    read_time_seconds: int

    @property
    def read_time_hours(self) -> float:
        return round(self.read_time_seconds / 3600, 1)


@dataclass(frozen=True)
class Wrapped:
    """The committed shape of a year-in-review."""

    year: int
    books_finished: int
    pages_read: int
    read_time_seconds: int
    days_read: int
    theme_breakdown: tuple[tuple[str, int], ...]
    standout_reads: tuple[StandoutRead, ...]

    @property
    def read_time_hours(self) -> float:
        return round(self.read_time_seconds / 3600, 1)


def _in_year(ts: int, lo: int, hi: int) -> bool:
    day = ts // SECONDS_PER_DAY
    return lo <= day < hi


def compute_wrapped(
    states: list[ReadingState],
    daily_activity: list[DailyActivity],
    year: int,
    *,
    top_n: int = 5,
) -> Wrapped:
    """Compute a private year-in-review for ``year`` from local reading state."""
    lo, hi = year_bounds(year)

    finished_this_year = [
        s
        for s in states
        if s.status is ReadingStatus.FINISHED
        and s.stat is not None
        and _in_year(s.stat.last_read_ts, lo, hi)
    ]

    days = [d for d in daily_activity if lo <= d.day_ordinal < hi]
    pages = sum(d.pages for d in days)
    seconds = sum(d.seconds for d in days)

    from collections import Counter

    theme_counter: Counter[str] = Counter()
    for s in finished_this_year:
        for tag in s.theme_tags:
            theme_counter[tag.normalized] += 1

    standouts = sorted(
        (
            StandoutRead(
                title=s.title,
                authors=s.authors,
                read_time_seconds=s.stat.read_time_seconds if s.stat else 0,
            )
            for s in finished_this_year
        ),
        key=lambda r: (-r.read_time_seconds, r.title),
    )[:top_n]

    return Wrapped(
        year=year,
        books_finished=len(finished_this_year),
        pages_read=pages,
        read_time_seconds=seconds,
        days_read=len({d.day_ordinal for d in days}),
        theme_breakdown=tuple(theme_counter.most_common()),
        standout_reads=tuple(standouts),
    )
