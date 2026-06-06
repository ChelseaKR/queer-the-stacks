"""N4: highlights, series/TBR intelligence, and search/browse."""

from __future__ import annotations

from app.browse import available_facets, filter_states
from app.shelf import series_continuations, to_read
from app.stats import compute_stats
from ingest.models import (
    Author,
    Book,
    ReadingState,
    ReadingStatus,
    Source,
    SourceKind,
    ThemeTag,
)


def _src() -> Source:
    return Source(SourceKind.CALIBRE_TAG, "calibre:local", "2026-06-05", "x")


def _owned(title: str, author: str, status: ReadingStatus, *, series=None, index=None, themes=()):
    tags = tuple(ThemeTag(t, _src()) for t in themes)
    book = Book(
        book_id=title,
        title=title,
        authors=(Author(author),),
        series=series,
        series_index=index,
        theme_tags=tags,
    )
    return ReadingState(title=title, authors=(author,), status=status, book=book)


# --- highlights -------------------------------------------------------------


def test_highlights_surfaced_in_stats(states: list, daily_activity: list) -> None:
    today = max(d.day_ordinal for d in daily_activity)
    stats = compute_stats(states, daily_activity, today)
    assert stats.total_highlights > 0
    assert stats.most_annotated  # (title, count) pairs
    assert all(count > 0 for _title, count in stats.most_annotated)


# --- series continuations ---------------------------------------------------


def test_series_continuation_detected() -> None:
    states = [
        _owned("Earthseed 1", "Butler", ReadingStatus.FINISHED, series="Earthseed", index=1.0),
        _owned("Earthseed 2", "Butler", ReadingStatus.UNREAD, series="Earthseed", index=2.0),
        _owned("Standalone", "X", ReadingStatus.UNREAD),  # not a continuation
    ]
    cont = series_continuations(states)
    assert [c.title for c in cont] == ["Earthseed 2"]
    assert cont[0].series == "Earthseed"


def test_no_continuation_if_series_not_started() -> None:
    states = [
        _owned("Series A 1", "X", ReadingStatus.UNREAD, series="A", index=1.0),
        _owned("Series A 2", "X", ReadingStatus.UNREAD, series="A", index=2.0),
    ]
    assert series_continuations(states) == []


# --- to-read shelf ----------------------------------------------------------


def test_to_read_floats_continuations_and_fit() -> None:
    states = [
        _owned("Loved", "Butler", ReadingStatus.FINISHED, series="S", index=1.0, themes=("trans",)),
        _owned("Next in S", "Butler", ReadingStatus.UNREAD, series="S", index=2.0),
        _owned("Ontheme", "Y", ReadingStatus.UNREAD, themes=("trans",)),
        _owned("Offtheme", "Z", ReadingStatus.UNREAD, themes=("thriller",)),
    ]
    shelf = [s.title for s in to_read(states)]
    assert shelf[0] == "Next in S"  # continuation first
    assert shelf.index("Ontheme") < shelf.index("Offtheme")  # better fit ranks higher


# --- browse / search --------------------------------------------------------


def test_filter_by_theme_author_status() -> None:
    states = [
        _owned("A", "Plett", ReadingStatus.FINISHED, themes=("trans", "literary")),
        _owned("B", "Butler", ReadingStatus.UNREAD, themes=("speculative",)),
    ]
    assert [s.title for s in filter_states(states, theme="trans")] == ["A"]
    assert [s.title for s in filter_states(states, author="butler")] == ["B"]
    assert [s.title for s in filter_states(states, status="unread")] == ["B"]
    assert [s.title for s in filter_states(states, q="a")] == ["A"]  # matches title


def test_filter_and_semantics() -> None:
    states = [
        _owned("A", "Plett", ReadingStatus.FINISHED, themes=("trans",)),
        _owned("B", "Plett", ReadingStatus.UNREAD, themes=("trans",)),
    ]
    # theme AND status -> only the unread trans book
    assert [s.title for s in filter_states(states, theme="trans", status="unread")] == ["B"]
    assert filter_states(states) == states  # no filters -> all


def test_available_facets() -> None:
    states = [
        _owned("A", "Plett", ReadingStatus.FINISHED, series="S", themes=("trans",)),
        _owned("B", "Butler", ReadingStatus.UNREAD, themes=("speculative",)),
    ]
    facets = available_facets(states)
    assert facets.themes == ("speculative", "trans")
    assert "Butler" in facets.authors and "Plett" in facets.authors
    assert facets.series == ("S",)
    assert "finished" in facets.statuses


# --- integration: view + render include the new sections --------------------


def test_demo_view_has_library_and_shelf(full_view: object) -> None:
    assert full_view.library  # type: ignore[attr-defined]
    assert full_view.series_next  # type: ignore[attr-defined] - Earthseed/MaddAddam started
    assert full_view.to_read is not None  # type: ignore[attr-defined]


def test_render_includes_new_sections(full_view: object) -> None:
    from app.view import render_view

    html = render_view(full_view)  # type: ignore[arg-type]
    for heading in ("Up next in your series", "To-read shelf", "Browse your library"):
        assert heading in html
    assert "Highlights" in html
