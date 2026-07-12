"""Renderer + view assembly: content, escaping, and the wired demo view."""

from __future__ import annotations

from pathlib import Path

from app.a11y_check import check_html
from app.render import render_dashboard
from app.view import build_view, demo_view, render_view
from ingest.models import (
    Author,
    Book,
    DailyActivity,
    ReadingState,
    ReadingStatus,
    Source,
    SourceKind,
    ThemeTag,
)


def test_demo_view_has_expected_shape(tmp_path: Path) -> None:
    view = demo_view(tmp_path)
    assert view.user == "demo"
    assert view.currently_reading
    assert view.finished
    assert view.recommendations
    assert view.stats.books_finished >= 7
    assert view.wrapped.year == 2024


def test_render_contains_all_sections(tmp_path: Path) -> None:
    view = demo_view(tmp_path)
    html = render_dashboard(
        view.currently_reading,
        view.finished,
        view.stats,
        view.wrapped,
        view.recommendations,
        user=view.user,
    )
    for heading in (
        "Currently reading",
        "Reading stats",
        "Reading Wrapped",
        "Recommended for you",
        "Recently finished",
    ):
        assert heading in html
    # Every rec card shows a source link and a why.
    assert "Why recommended" in html
    assert "Sources" in html
    # Themes are rendered as text chips, not colour-only.
    assert 'class="tag"' in html


def test_render_escapes_user_content() -> None:
    src = Source(SourceKind.CALIBRE_TAG, "calibre:local", "2026-06-05", "x")
    book = Book(
        book_id="b",
        title="<script>alert(1)</script>",
        authors=(Author("A & B"),),
        theme_tags=(ThemeTag("queer", src),),
    )
    state = ReadingState(
        title=book.title, authors=("A & B",), status=ReadingStatus.READING, book=book
    )
    from app.stats import compute_stats
    from app.wrapped import compute_wrapped

    stats = compute_stats([state], [], 0)
    wrapped = compute_wrapped([state], [], 2024)
    html = render_dashboard([state], [], stats, wrapped, [], user="me")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "A &amp; B" in html


def test_build_view_empty_inputs() -> None:
    view = build_view([], [], (), lists=())
    assert view.recommendations == ()
    assert view.stats.books_finished == 0
    assert view.currently_reading == ()


def test_render_handles_empty_view() -> None:
    view = build_view([], [DailyActivity(0, 0, 0)], ())
    html = render_dashboard(
        view.currently_reading,
        view.finished,
        view.stats,
        view.wrapped,
        view.recommendations,
    )
    assert "Nothing in progress" in html
    assert "No recommendations yet" in html


def test_render_data_status_never_refreshed() -> None:
    view = build_view([], [DailyActivity(0, 0, 0)], ())
    html = render_dashboard(
        view.currently_reading,
        view.finished,
        view.stats,
        view.wrapped,
        view.recommendations,
    )
    assert "Data status" in html
    assert "never refreshed" in html
    assert "stacks refresh" in html
    assert 'role="status"' not in html  # no stamp yet -> no staleness banner either


def test_render_data_status_shows_stamp_and_no_banner_when_fresh() -> None:
    view = build_view([], [DailyActivity(0, 0, 0)], ())
    html = render_dashboard(
        view.currently_reading,
        view.finished,
        view.stats,
        view.wrapped,
        view.recommendations,
        refreshed_at=1_700_000_000,
        stale=False,
    )
    assert "Data status" in html
    assert "2023-11-14T22:13:20Z" in html  # ISO-8601 UTC of the epoch stamp
    assert 'role="status"' not in html


def test_render_data_status_stale_banner_is_visible_text() -> None:
    view = build_view([], [DailyActivity(0, 0, 0)], ())
    html = render_dashboard(
        view.currently_reading,
        view.finished,
        view.stats,
        view.wrapped,
        view.recommendations,
        refreshed_at=1_700_000_000,
        stale=True,
    )
    assert 'role="status"' in html
    assert "Stale" in html  # staleness named in text, not colour-only


# --- R4: descriptor provenance surfaced in the diversity section --------------


def _diversity_section(html: str) -> str:
    start = html.index("Reading diversity")
    return html[start : html.index("Reading Wrapped", start)]


def test_diversity_provenance_shows_source_and_date(tmp_path: Path) -> None:
    html = render_view(demo_view(tmp_path))
    section = _diversity_section(html)
    # Every diverse-shelf tag shows the source that asserted it and when (R4).
    assert "Per-descriptor provenance" in section
    assert "calibre-tag" in section
    assert "2026-06-05" in section
    # Sensitive descriptors are flagged in text (never colour-only).
    assert "(sensitive)" in section


def test_hide_sensitive_redacts_diversity_section(states: list, candidates: tuple) -> None:
    view = build_view(states, [], candidates, hide_sensitive_descriptors=True)
    html = render_view(view)
    section = _diversity_section(html)
    # Identity-adjacent labels are aggregated out of the diverse-shelf view.
    assert "trans" not in section and "queer" not in section
    assert "aggregated for privacy" in section
    assert "Privacy:" in section
    # The redacted page is still fully accessible (the a11y contract holds).
    assert check_html(html) == []
