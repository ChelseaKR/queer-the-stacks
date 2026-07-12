"""Reading goals: the time (hours) goal + its config wiring; render integration."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from app.a11y_check import check_html
from app.goals import compute_goals
from app.stats import compute_stats
from app.view import build_view, render_view
from app.wrapped import compute_wrapped
from ingest.config import load_config
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


def _finished(title: str, ts: int, read_seconds: int) -> ReadingState:
    src = Source(SourceKind.CURATED_LIST, "curated-list:x", "2026-06-05", "trans")
    book = Book(
        book_id=title, title=title, authors=(Author("A"),), theme_tags=(ThemeTag("trans", src),)
    )
    stat = ReadingStat(title, title, ("A",), 100, 100, read_seconds, ts, 3)
    return ReadingState(
        title=title, authors=("A",), status=ReadingStatus.FINISHED, book=book, stat=stat
    )


def test_hours_goal_tracks_rounded_read_time() -> None:
    day = _ord(2024, 1, 5)
    ts = int(datetime.datetime(2024, 1, 5, tzinfo=datetime.UTC).timestamp())
    states = [_finished("B", ts, 9000)]
    # 2.5 hours of activity on the day → rounds to 2 hours read.
    days = [DailyActivity(day, 9000, 100)]
    stats = compute_stats(states, days, day)
    wrapped = compute_wrapped(states, days, 2024)
    goals = compute_goals(stats, wrapped, hours_target=10)
    assert len(goals) == 1
    g = goals[0]
    assert g.name == "Hours in 2024"
    assert g.target == 10
    assert g.current == round(wrapped.read_time_hours)


def test_config_reads_hours_goal_from_env_and_toml(tmp_path: Path) -> None:
    cfg = load_config(env={"STACKS_GOAL_HOURS": "120"}, config_path=tmp_path / "absent.toml")
    assert cfg.goal_hours == 120

    toml = tmp_path / "stacks.toml"
    toml.write_text("[goals]\nhours = 75\n", encoding="utf-8")
    assert load_config(env={}, config_path=toml).goal_hours == 75
    # Default is unset.
    assert load_config(env={}, config_path=tmp_path / "none.toml").goal_hours == 0


def test_all_four_goal_kinds_render_and_stay_accessible() -> None:
    days = [DailyActivity(_ord(2024, 1, 5), 3600, 30)]
    ts = int(datetime.datetime(2024, 1, 5, tzinfo=datetime.UTC).timestamp())
    view = build_view(
        [_finished("B", ts, 3600)],
        days,
        (),
        goal_books=10,
        goal_pages=1000,
        goal_hours=50,
        goal_streak_days=5,
    )
    assert len(view.goals) == 4
    html = render_view(view)
    assert "Hours in 2024" in html
    assert check_html(html) == []


def test_dashboard_shows_diversity_and_share_link(full_view: object) -> None:
    html = render_view(full_view)  # type: ignore[arg-type]
    assert "Reading diversity" in html
    assert 'href="/share"' in html
    # The honesty caveat is present, and the section is a real data table.
    assert "never infer an author" in html.lower() or "never auto-label" in html.lower()


def test_share_route_served_behind_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from tests.conftest import seed_store_from_env

    monkeypatch.setenv("STACKS_DEMO", "1")
    monkeypatch.setenv("STACKS_DATA_DIR", str(tmp_path))
    seed_store_from_env()  # data routes 503 until refreshed (FIX-14)
    from app.server import create_app

    client = TestClient(create_app())
    assert client.get("/share").status_code == 401
    ok = client.get("/share", headers={"Authorization": "Bearer demo-token"})
    assert ok.status_code == 200
    assert "Share cards" in ok.text

    svg = client.get("/share/card.svg", headers={"Authorization": "Bearer demo-token"})
    assert svg.status_code == 200
    assert svg.headers["content-type"].startswith("image/svg+xml")
