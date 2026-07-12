"""Reading-pace forecasts: pinned percentile math + thin-data fallback."""

from __future__ import annotations

from app.forecast import (
    MIN_DAYS_FOR_ESTIMATE,
    Forecast,
    _quantiles,
    _recent_per_page_seconds,
    forecast_book,
    forecast_series,
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


def test_forecast_series_aggregates_remaining_pages() -> None:
    # Two "books" with remaining pages 40 and 60 -> total 100, same math as
    # the single-book pinned case since forecast_series reuses forecast_book.
    book_a_remaining = 40
    book_b_remaining = 60
    result = forecast_series(book_a_remaining + book_b_remaining, _DAYS)
    assert result.low_hours == 0.8
    assert result.high_hours == 1.7
    assert result.basis == "from your last 8 reading days"


def test_forecast_series_expresses_large_high_end_in_weeks() -> None:
    # remaining_pages_total chosen so high_hours = 1400 * 62.5 / 3600 = 24.3 >= 24
    result = forecast_series(1400, _DAYS)
    assert result.estimable is True
    assert result.low_hours == 10.7
    assert result.high_hours == 24.3
    assert "weeks" in result.basis
    assert result.basis.startswith("from your last 8 reading days")


def test_forecast_series_thin_data() -> None:
    result = forecast_series(1000, _DAYS[:2])
    assert result.estimable is False
    assert result.basis == "not enough recent reading to estimate"
