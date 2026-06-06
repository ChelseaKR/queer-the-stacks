"""N6: expanded Wrapped (monthly + pace), local goals, progressive filter UI."""

from __future__ import annotations

import datetime
from pathlib import Path

from app.a11y_check import check_html
from app.goals import Goal, compute_goals
from app.view import build_view, render_view
from app.wrapped import compute_wrapped
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


def _ord(y: int, m: int, d: int) -> int:
    return datetime.date(y, m, d).toordinal() - _EPOCH


def _finished(title: str, ts: int) -> ReadingState:
    src = Source(SourceKind.CURATED_LIST, "curated-list:x", "2026-06-05", "trans")
    book = Book(
        book_id=title, title=title, authors=(Author("A"),), theme_tags=(ThemeTag("trans", src),)
    )
    stat = ReadingStat(title, title, ("A",), 100, 100, 3600, ts, 3)
    return ReadingState(
        title=title, authors=("A",), status=ReadingStatus.FINISHED, book=book, stat=stat
    )


# --- Wrapped: monthly + pace ------------------------------------------------


def test_wrapped_monthly_and_pace() -> None:
    days = [
        DailyActivity(_ord(2024, 1, 5), 3600, 30),
        DailyActivity(_ord(2024, 1, 6), 3600, 30),
        DailyActivity(_ord(2024, 3, 1), 1800, 20),
    ]
    ts = int(datetime.datetime(2024, 1, 5, tzinfo=datetime.UTC).timestamp())
    wrapped = compute_wrapped([_finished("Book", ts)], days, 2024)
    months = {m.month: m for m in wrapped.monthly}
    assert months[1].pages == 60 and months[1].days_read == 2
    assert months[3].pages == 20
    assert wrapped.pace_pages_per_day == round(80 / 3, 1)


# --- Goals ------------------------------------------------------------------


def test_compute_goals_only_set_ones() -> None:
    days = [DailyActivity(_ord(2024, 1, 5), 3600, 30)]
    from app.stats import compute_stats

    states = [_finished("B", int(datetime.datetime(2024, 1, 5, tzinfo=datetime.UTC).timestamp()))]
    stats = compute_stats(states, days, _ord(2024, 1, 5))
    wrapped = compute_wrapped(states, days, 2024)
    goals = compute_goals(stats, wrapped, books_target=12, pages_target=0, streak_target=0)
    assert len(goals) == 1
    assert goals[0].name.startswith("Books")
    assert goals[0].target == 12


def test_goal_progress_and_met() -> None:
    g = Goal("Books", 12, 12)
    assert g.met and g.pct == 1.0
    half = Goal("Books", 6, 12)
    assert not half.met and half.pct == 0.5
    assert Goal("x", 5, 0).pct == 0.0  # unset target never divides


# --- render + a11y ----------------------------------------------------------


def test_render_includes_monthly_and_filter(full_view: object) -> None:
    html = render_view(full_view)  # type: ignore[arg-type]
    assert "Monthly reading" in html
    assert 'id="lib-filter"' in html
    assert 'id="lib-table"' in html
    assert "<script>" in html
    # No-JS safety: filtering is also offered via the /browse route.
    assert "/browse route" in html


def test_goals_section_renders_and_is_accessible() -> None:
    days = [DailyActivity(_ord(2024, 1, 5), 3600, 30)]
    states = [_finished("B", int(datetime.datetime(2024, 1, 5, tzinfo=datetime.UTC).timestamp()))]
    view = build_view(states, days, (), goal_books=10, goal_pages=1000, goal_streak_days=5)
    assert view.goals
    html = render_view(view)
    assert "<h2>Goals</h2>" in html
    assert check_html(html) == []  # the goal-configured page is still a11y-clean


def test_filter_js_has_no_angle_brackets_inside() -> None:
    from app.render import _FILTER_JS

    inner = _FILTER_JS.replace("<script>", "").replace("</script>", "")
    assert "<" not in inner  # keeps the static a11y parser happy


def test_demo_render_still_zero_violations(tmp_path: Path) -> None:
    from app.view import demo_view

    assert check_html(render_view(demo_view(tmp_path))) == []
