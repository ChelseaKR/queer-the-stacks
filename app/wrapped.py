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
    monthly: tuple[MonthStat, ...] = ()  # 12 entries, Jan..Dec
    pace_pages_per_day: float = 0.0  # mean pages on days you actually read

    @property
    def read_time_hours(self) -> float:
        return round(self.read_time_seconds / 3600, 1)


@dataclass(frozen=True)
class MonthStat:
    """One month of a Wrapped year."""

    month: int  # 1..12
    pages: int
    hours: float
    days_read: int


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

    monthly = _monthly(days)
    pace = round(pages / len(days), 1) if days else 0.0

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
        monthly=monthly,
        pace_pages_per_day=pace,
    )


def _monthly(days: list[DailyActivity]) -> tuple[MonthStat, ...]:
    """Aggregate a year's active days into 12 month buckets (only non-empty ones)."""
    import datetime

    epoch = datetime.date(1970, 1, 1).toordinal()
    by_month: dict[int, list[int]] = {}
    for d in days:
        month = datetime.date.fromordinal(epoch + d.day_ordinal).month
        bucket = by_month.setdefault(month, [0, 0, 0])  # pages, seconds, days
        bucket[0] += d.pages
        bucket[1] += d.seconds
        bucket[2] += 1
    return tuple(
        MonthStat(month=m, pages=v[0], hours=round(v[1] / 3600, 1), days_read=v[2])
        for m, v in sorted(by_month.items())
    )
