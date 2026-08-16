"""Reading-pace forecasts: pinned percentile math + thin-data fallback."""

from __future__ import annotations

from app.forecast import (
    MIN_DAYS_FOR_ESTIMATE,
    Forecast,
    _quantiles,
    _recent_per_page_seconds,
    forecast_book,
)
from ingest.models import DailyActivity

# 8 active days, 10 pages each, seconds chosen so per-page seconds are exactly
# 10, 20, 30, ..., 80 — hand-computable p25/p75 via linear interpolation:
#   sorted = [10, 20, 30, 40, 50, 60, 70, 80], n=8
#   p25: rank = 0.25 * 7 = 1.75 -> 20 + 0.75*(30-20) = 27.5
#   p75: rank = 0.75 * 7 = 5.25 -> 60 + 0.25*(70-60) = 62.5
_DAYS = [DailyActivity(day_ordinal=100 + i, seconds=(i + 1) * 100, pages=10) for i in range(8)]


def test_recent_per_page_seconds_pinned() -> None:
    sample = _recent_per_page_seconds(_DAYS, window_days=30)
    assert sorted(sample) == [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0]


def test_recent_per_page_seconds_skips_zero_page_days() -> None:
    days = [*_DAYS, DailyActivity(day_ordinal=200, seconds=999, pages=0)]
    sample = _recent_per_page_seconds(days, window_days=30)
    assert len(sample) == 8


def test_recent_per_page_seconds_windows_to_most_recent() -> None:
    # Only the 3 most-recent (highest day_ordinal) days should be taken.
    sample = _recent_per_page_seconds(_DAYS, window_days=3)
    assert sorted(sample) == [60.0, 70.0, 80.0]


def test_quantiles_pinned() -> None:
    xs = [float(v) for v in [10, 20, 30, 40, 50, 60, 70, 80]]
    p25, p75 = _quantiles(xs)
    assert p25 == 27.5
    assert p75 == 62.5


def test_quantiles_empty() -> None:
    assert _quantiles([]) == (0.0, 0.0)


def test_quantiles_single_value() -> None:
    assert _quantiles([42.0]) == (42.0, 42.0)


def test_forecast_book_pinned_range() -> None:
    result = forecast_book(100, _DAYS)
    # low = 100 * 27.5 / 3600 = 0.763... -> 0.8
    # high = 100 * 62.5 / 3600 = 1.736... -> 1.7
    assert result.low_hours == 0.8
    assert result.high_hours == 1.7
    assert result.estimable is True
    assert result.basis == "from your last 8 reading days"


def test_forecast_book_basis_discloses_window() -> None:
    # window_days smaller than the number of days provided narrows the sample.
    result = forecast_book(100, _DAYS, window_days=5)
    assert result.basis == "from your last 5 reading days"


def test_forecast_book_thin_data() -> None:
    assert len(_DAYS[:4]) < MIN_DAYS_FOR_ESTIMATE
    result = forecast_book(100, _DAYS[:4])
    assert result == Forecast.unknown()
    assert result.estimable is False
    assert result.basis == "not enough recent reading to estimate"


def test_forecast_book_zero_remaining_pages() -> None:
    result = forecast_book(0, _DAYS)
    assert result.estimable is False
    assert result.basis == "not enough recent reading to estimate"


def test_forecast_book_negative_remaining_pages() -> None:
    result = forecast_book(-5, _DAYS)
    assert result.estimable is False


def test_forecast_book_no_daily_activity() -> None:
    result = forecast_book(100, [])
    assert result == Forecast.unknown()


def test_forecast_never_a_single_point() -> None:
    result = forecast_book(100, _DAYS)
    assert result.low_hours != result.high_hours


# --- The basis line must name the sample it came from ------------------------


def test_basis_names_the_days_that_contributed_not_the_days_on_record() -> None:
    """More days on record than valid days: the basis must name the valid count.

    The basis line is this module's entire honesty mechanism — it is what a
    reader weighs the range against, and `app/render.py` prints it verbatim into
    the "Time to finish" table. It used to be `min(len(daily), window_days)`,
    every day in the record including days with no pages turned, which
    `_recent_per_page_seconds` had already discarded. This is the test that
    would have caught it.
    """
    quiet_days = [
        DailyActivity(day_ordinal=200 + i, seconds=1800, pages=0)
        for i in range(20)  # on record, contributing nothing
    ]
    daily = [*_DAYS, *quiet_days]

    assert len(daily) == 28
    assert len(_recent_per_page_seconds(daily, window_days=30)) == 8

    result = forecast_book(100, daily)
    assert result.estimable is True
    assert result.basis == "from your last 8 reading days"


def test_basis_count_never_exceeds_the_window() -> None:
    """A window narrower than the record still names what was sampled."""
    many = [DailyActivity(day_ordinal=100 + i, seconds=(i + 1) * 100, pages=10) for i in range(40)]
    result = forecast_book(100, many, window_days=30)
    assert result.basis == "from your last 30 reading days"


def test_forecast_series_is_gone() -> None:
    """The unreachable whole-series helper is removed, not left dormant.

    It had no caller, and the number it needed — remaining pages across the
    *unread* books of a series — does not exist in the models: page counts live
    on ``ReadingStat`` (KOReader, so read books only) and ``Book`` carries none
    from Calibre. Its weeks clause divided by an unstated 24-hours-a-day
    assumption while its docstring claimed ~2 hours/day, and the test covering
    that line asserted only that the word "weeks" appeared, never the number.
    """
    import app.forecast as forecast_module

    assert not hasattr(forecast_module, "forecast_series")
