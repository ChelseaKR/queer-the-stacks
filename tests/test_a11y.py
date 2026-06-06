"""Accessibility gate — the rendered dashboard has zero mechanical violations."""

from __future__ import annotations

from pathlib import Path

from app.a11y_check import check_html, main
from app.render import render_dashboard
from app.view import demo_view


def _html(tmp_path: Path) -> str:
    view = demo_view(tmp_path)
    return render_dashboard(
        view.currently_reading,
        view.finished,
        view.stats,
        view.wrapped,
        view.recommendations,
        user=view.user,
    )


def test_demo_dashboard_has_zero_violations(tmp_path: Path) -> None:
    assert check_html(_html(tmp_path)) == []


def test_checker_catches_missing_landmarks() -> None:
    bad = "<!doctype html><html><head></head><body><p>hi</p></body></html>"
    violations = check_html(bad)
    assert any("lang" in v for v in violations)
    assert any("viewport" in v for v in violations)
    assert any("<h1>" in v or "h1" in v for v in violations)
    assert any("main" in v for v in violations)
    assert any("skip" in v for v in violations)


def test_checker_catches_table_without_caption() -> None:
    bad = (
        '<!doctype html><html lang="en"><head>'
        '<meta name="viewport" content="width=device-width"></head><body>'
        '<a class="skip" href="#main">skip</a><main id="main"><h1>T</h1>'
        "<table><tr><th>no scope</th></tr></table></main></body></html>"
    )
    violations = check_html(bad)
    assert any("caption" in v for v in violations)
    assert any("scope" in v for v in violations)


def test_checker_catches_heading_jump() -> None:
    bad = (
        '<!doctype html><html lang="en"><head>'
        '<meta name="viewport" content="x"></head><body>'
        '<a class="skip" href="#main">skip</a><main id="main"><h1>T</h1>'
        "<h4>jumped</h4></main></body></html>"
    )
    assert any("jump" in v for v in check_html(bad))


def test_main_passes_on_demo(tmp_path: Path) -> None:
    out = tmp_path / "dash.html"
    out.write_text(_html(tmp_path), encoding="utf-8")
    assert main([str(out)]) == 0


def test_main_fails_on_violations(tmp_path: Path) -> None:
    out = tmp_path / "bad.html"
    out.write_text("<html><body></body></html>", encoding="utf-8")
    assert main([str(out)]) == 1


def test_main_usage_without_args() -> None:
    assert main([]) == 2
