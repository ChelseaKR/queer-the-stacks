"""Unify: cross-device progress, status classification, history completeness."""

from __future__ import annotations

from ingest.models import Author, Book, ReadingStat, ReadingStatus
from ingest.unify import (
    currently_reading,
    finished,
    normalize_key,
    unify,
)


def test_currently_reading_and_finished(states: list) -> None:
    reading = currently_reading(states)
    done = finished(states)
    reading_titles = {s.title for s in reading}
    assert "Stone Butch Blues" in reading_titles
    assert all(s.status is ReadingStatus.READING for s in reading)
    assert all(s.status is ReadingStatus.FINISHED for s in done)
    assert "Kindred" in {s.title for s in done}


def test_cross_device_progress_attached(states: list) -> None:
    sbb = next(s for s in states if s.title == "Stone Butch Blues")
    assert sbb.progress  # device progress present
    assert sbb.latest_device == "Kobo"
    assert 0.4 < sbb.percent_complete < 0.5


def test_normalize_key_is_stable() -> None:
    # Same title with case/spacing/punctuation noise resolves to one key, so a
    # Calibre book and its KOReader stat join even when stored slightly differently.
    assert normalize_key("The Handmaid's Tale", ("Margaret Atwood",)) == normalize_key(
        "  the handmaid's TALE ", ["Margaret  Atwood"]
    )


def test_status_classification() -> None:
    book = Book(book_id="b1", title="Half Read", authors=(Author("X"),))
    stat = ReadingStat(
        key="k",
        title="Half Read",
        authors=("X",),
        pages_read=50,
        total_pages=100,
        read_time_seconds=600,
        last_read_ts=1_700_000_000,
        sessions=2,
    )
    states = unify([book], [stat], None)
    assert states[0].status is ReadingStatus.READING


def test_unread_book_with_no_stats() -> None:
    book = Book(book_id="b1", title="Untouched", authors=(Author("X"),))
    states = unify([book], [], None)
    assert states[0].status is ReadingStatus.UNREAD
    assert states[0].percent_complete == 0.0


def test_stat_without_calibre_book_is_surfaced() -> None:
    """A book read in KOReader but absent from Calibre still appears."""
    stat = ReadingStat(
        key="k",
        title="Sideloaded Zine",
        authors=("Zinester",),
        pages_read=30,
        total_pages=30,
        read_time_seconds=900,
        last_read_ts=1_700_000_000,
        sessions=1,
    )
    states = unify([], [stat], None)
    assert len(states) == 1
    assert states[0].title == "Sideloaded Zine"
    assert states[0].book is None
    assert states[0].status is ReadingStatus.FINISHED
