"""A self-hosted "Reading Wrapped" — a private year-in-review.

No third-party service ever sees this. It is computed locally from the same
unified reading state + per-day activity the dashboard uses, scoped to a single
year. The theme breakdown is built only from sourced theme tags.

Two scopes live in here and they are not interchangeable:

* Everything summed from :class:`~ingest.models.DailyActivity` — pages, hours,
  reading days, the monthly table — is **within the year**, because that record
  is timestamped per day.
* :class:`StandoutRead` hours are **all-time per book**, because KOReader keeps
  one cumulative ``total_read_time`` per book and no per-year breakdown. The
  year only decides *which* books qualify (those finished in it), never how many
  of their hours to count.

So the standouts do not partition the year's hours and can exceed them. Every
name and docstring here says which scope it means; a surface that renders them
must say so too.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ingest.koreader import SECONDS_PER_DAY
from ingest.models import DailyActivity, ReadingState, ReadingStatus

#: Said wherever a Wrapped year cannot be named. A year is inferred from the
#: reading record itself, so with no reading-data source connected there is no
#: year to infer — and the epoch fallback that used to fill the gap rendered as
#: "Reading Wrapped 1970" over a row of confident zeros.
UNMEASURED_YEAR_LABEL = "not measured"


def _jan1_ordinal(year: int) -> int:
    import datetime

    return datetime.date(year, 1, 1).toordinal() - datetime.date(1970, 1, 1).toordinal()


def year_bounds(year: int) -> tuple[int, int]:
    """Return (first_day_ordinal, last_day_ordinal_exclusive) for ``year``."""
    return _jan1_ordinal(year), _jan1_ordinal(year + 1)


@dataclass(frozen=True)
class StandoutRead:
    """A book finished in the Wrapped year, with its **all-time** read time.

    The field is named for its scope on purpose. KOReader keeps one cumulative
    ``total_read_time`` per book and no per-year breakdown, so the only per-book
    duration this project has is a lifetime one. A book finished in March that
    was started the previous autumn carries the autumn's hours here.

    That makes these totals *not* a partition of :attr:`Wrapped.read_time_hours`,
    which is summed from :class:`~ingest.models.DailyActivity` inside the year:
    the standouts can, and in the demo world do, sum to more than the year holds.
    Anything rendering this must say which number it is showing — see
    :func:`app.render._wrapped_table`.
    """

    title: str
    authors: tuple[str, ...]
    total_read_time_seconds: int

    @property
    def total_read_time_hours(self) -> float:
        """All-time hours for this book, not the hours spent on it in the year."""
        return round(self.total_read_time_seconds / 3600, 1)


@dataclass(frozen=True)
class Wrapped:
    """The committed shape of a year-in-review.

    :attr:`year` is ``None`` when there is no reading record to infer a year
    from. That is a distinct state from "a year in which you read nothing", and
    the two must not render alike: every figure below is zero in both cases, but
    only one of them is a measurement. Mirrors :attr:`app.forecast.Forecast.estimable`
    and :attr:`app.diversity.DiversityReport.shelf_fallback` — this module's
    neighbours already refuse to guess; this one used to answer 1970.
    """

    year: Optional[int]
    books_finished: int
    pages_read: int
    read_time_seconds: int
    days_read: int
    theme_breakdown: tuple[tuple[str, int], ...]
    #: Books finished in :attr:`year`, carrying **all-time** hours each — not a
    #: breakdown of :attr:`read_time_seconds`. See :class:`StandoutRead`.
    standout_reads: tuple[StandoutRead, ...]
    monthly: tuple[MonthStat, ...] = ()  # 12 entries, Jan..Dec
    pace_pages_per_day: float = 0.0  # mean pages on days you actually read

    @staticmethod
    def unmeasured() -> Wrapped:
        """The no-source variant: no year, and nothing counted within one.

        The zeros here are structural padding, never findings. :attr:`measured`
        is the flag a surface keys off; it is False exactly when :attr:`year`
        is None, kept as a named property so render sites read as intent rather
        than as a null check.
        """
        return Wrapped(
            year=None,
            books_finished=0,
            pages_read=0,
            read_time_seconds=0,
            days_read=0,
            theme_breakdown=(),
            standout_reads=(),
        )

    @property
    def measured(self) -> bool:
        """Whether this Wrapped describes a real year of reading records."""
        return self.year is not None

    @property
    def year_label(self) -> str:
        """The year as rendered — never a fabricated one."""
        return UNMEASURED_YEAR_LABEL if self.year is None else str(self.year)

    @property
    def read_time_hours(self) -> float:
        """Hours read **inside** :attr:`year`, summed from per-day activity."""
        return round(self.read_time_seconds / 3600, 1)

    @property
    def standouts_exceed_the_year(self) -> bool:
        """True when the standouts' all-time hours add up to more than the year.

        Not an error: it just means at least one standout was started before
        :attr:`year`. The renderer uses it to name the discrepancy in place
        rather than leaving the reader to notice it and distrust the panel.
        """
        return sum(r.total_read_time_seconds for r in self.standout_reads) > self.read_time_seconds


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
    year: Optional[int],
    *,
    top_n: int = 5,
) -> Wrapped:
    """Compute a private year-in-review for ``year`` from local reading state.

    ``year`` is ``None`` when no reading record exists to infer one from (see
    :func:`app.view._infer_today_and_year`), and the result is
    :meth:`Wrapped.unmeasured` — not a zeroed year, which would be a claim.
    """
    if year is None:
        return Wrapped.unmeasured()
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

    # Ranked by all-time read time, because that is the only per-book duration
    # KOReader records. The year scoping lives in `finished_this_year` (which
    # books qualify), never in the hours (how long each took overall).
    standouts = sorted(
        (
            StandoutRead(
                title=s.title,
                authors=s.authors,
                total_read_time_seconds=s.stat.read_time_seconds if s.stat else 0,
            )
            for s in finished_this_year
        ),
        key=lambda r: (-r.total_read_time_seconds, r.title),
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
