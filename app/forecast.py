"""Honest, ranged time-to-finish forecasts from recent reading pace.

KOReader records page-level durations, but only :class:`~ingest.models.DailyActivity`
(day-level seconds/pages) is surfaced in the unified models. So pace is derived
from *recent active days* — the most recent ``window_days`` days you actually
read — rather than a single point estimate. A forecast is always a range (the
25th–75th percentile of per-page seconds across those days), never a single
number, because a point estimate reads as false precision. When there isn't
enough recent reading to say anything honest, the forecast says so instead of
guessing.

Pure module: no I/O, no wall clock, no randomness. Caller supplies the
remaining-pages count (``total_pages - pages_read`` from a
:class:`~ingest.models.ReadingStat`) and the day-level activity to derive pace
from.
"""

from __future__ import annotations

from dataclasses import dataclass

from ingest.models import DailyActivity

#: How many of the most recent active days to draw the pace sample from.
DEFAULT_WINDOW_DAYS = 30

#: Fewer valid days than this and we don't have enough signal to forecast honestly.
MIN_DAYS_FOR_ESTIMATE = 5

_UNKNOWN_BASIS = "not enough recent reading to estimate"


@dataclass(frozen=True)
class Forecast:
    """A ranged time-to-finish estimate, never a single point."""

    low_hours: float
    high_hours: float
    basis: str
    estimable: bool = True

    @staticmethod
    def unknown() -> Forecast:
        """The thin-data variant: no honest range can be computed yet."""
        return Forecast(low_hours=0.0, high_hours=0.0, basis=_UNKNOWN_BASIS, estimable=False)


def _recent_per_page_seconds(daily: list[DailyActivity], window_days: int) -> list[float]:
    """Per-page seconds for each of the most recent (up to) ``window_days`` active days.

    Only days with ``pages > 0`` are usable (seconds/pages is undefined otherwise).
    Sorted by ``day_ordinal`` descending before windowing, so "recent" means
    recent in reading history, not insertion order.
    """
    recent = sorted(daily, key=lambda d: d.day_ordinal, reverse=True)[:window_days]
    return [d.seconds / d.pages for d in recent if d.pages > 0]


def _quantiles(xs: list[float]) -> tuple[float, float]:
    """Return (p25, p75) of ``xs`` via linear interpolation (like numpy's default)."""
    ys = sorted(xs)
    n = len(ys)
    if n == 0:
        return 0.0, 0.0
    if n == 1:
        return ys[0], ys[0]

    def _pct(p: float) -> float:
        rank = p * (n - 1)
        lo = int(rank)
        hi = min(lo + 1, n - 1)
        frac = rank - lo
        return ys[lo] + (ys[hi] - ys[lo]) * frac

    return _pct(0.25), _pct(0.75)


def forecast_book(
    remaining_pages: int,
    daily: list[DailyActivity],
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> Forecast:
    """Forecast hours-to-finish for a single book from recent per-page pace.

    Returns the thin-data :meth:`Forecast.unknown` when there are fewer than
    :data:`MIN_DAYS_FOR_ESTIMATE` valid recent-activity days, or when
    ``remaining_pages`` is not positive (nothing left, or a data glitch).
    """
    if remaining_pages <= 0:
        return Forecast.unknown()

    sample = _recent_per_page_seconds(daily, window_days)
    if len(sample) < MIN_DAYS_FOR_ESTIMATE:
        return Forecast.unknown()

    p25, p75 = _quantiles(sample)
    low_hours = round(remaining_pages * p25 / 3600, 1)
    high_hours = round(remaining_pages * p75 / 3600, 1)
    days_in_sample = min(len(daily), window_days)
    basis = f"from your last {days_in_sample} reading days"
    return Forecast(low_hours=low_hours, high_hours=high_hours, basis=basis)


def forecast_series(
    remaining_pages_total: int,
    daily: list[DailyActivity],
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> Forecast:
    """Forecast hours-to-finish for a whole series (or any multi-book total).

    Reuses :func:`forecast_book`'s math over the combined remaining-pages count.
    When the high end is large, the basis also expresses it in weeks (at ~2
    reading-hours/day-equivalent pacing implied by the same sample) — still a
    range, never a single number.
    """
    result = forecast_book(remaining_pages_total, daily, window_days=window_days)
    if not result.estimable or result.high_hours < 24:
        return result

    high_days = result.high_hours / 24
    high_weeks = round(high_days / 7, 1)
    basis = f"{result.basis} (up to ~{high_weeks} weeks at that pace)"
    return Forecast(
        low_hours=result.low_hours,
        high_hours=result.high_hours,
        basis=basis,
        estimable=True,
    )
