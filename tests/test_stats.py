"""Reading-stats math: totals, deterministic streaks, sourced theme mix."""

from __future__ import annotations

from app.stats import compute_stats
from ingest.models import DailyActivity


def test_totals_reconcile_with_states(states: list, daily_activity: list) -> None:
    today = max(d.day_ordinal for d in daily_activity)
    stats = compute_stats(states, daily_activity, today)
    assert stats.books_finished >= 7
    assert stats.books_reading >= 1
    assert stats.pages_read > 0
    assert stats.read_time_hours > 0


def test_theme_mix_from_sourced_tags(states: list, daily_activity: list) -> None:
    today = max(d.day_ordinal for d in daily_activity)
    stats = compute_stats(states, daily_activity, today)
    themes = dict(stats.theme_mix)
    # The canon is trans + speculative heavy.
    assert themes.get("speculative", 0) >= 3
    assert themes.get("trans", 0) >= 3


def test_streaks_consecutive_days() -> None:
    days = [DailyActivity(day_ordinal=o, seconds=600, pages=10) for o in (100, 101, 102, 105)]
    stats = compute_stats([], days, today_ordinal=102)
    assert stats.longest_streak_days == 3
    assert stats.current_streak_days == 3  # 100,101,102 ending today


def test_current_streak_allows_unread_today() -> None:
    days = [DailyActivity(day_ordinal=o, seconds=600, pages=10) for o in (200, 201)]
    # Today is 202 (not yet read) — streak counts back through 201, 200.
    stats = compute_stats([], days, today_ordinal=202)
    assert stats.current_streak_days == 2


def test_broken_streak_is_zero() -> None:
    days = [DailyActivity(day_ordinal=300, seconds=600, pages=10)]
    stats = compute_stats([], days, today_ordinal=400)
    assert stats.current_streak_days == 0
    assert stats.longest_streak_days == 1


def test_no_activity() -> None:
    stats = compute_stats([], [], today_ordinal=0)
    assert stats.current_streak_days == 0
    assert stats.longest_streak_days == 0
    assert stats.active_days == 0
