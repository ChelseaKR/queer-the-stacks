"""Diverse-shelf analytics — sourced-only, honest coverage, no author labels."""

from __future__ import annotations

from app.diversity import DIMENSIONS, compute_diversity
from ingest.models import (
    Author,
    Book,
    ReadingStat,
    ReadingState,
    ReadingStatus,
    Source,
    SourceKind,
    ThemeTag,
)


def _tag(label: str, kind: SourceKind = SourceKind.CALIBRE_TAG) -> ThemeTag:
    return ThemeTag(label, Source(kind, "calibre:local", "2026-06-05", label))


def _state(
    title: str,
    status: ReadingStatus,
    tags: tuple[ThemeTag, ...],
) -> ReadingState:
    book = Book(book_id=title, title=title, authors=(Author("A"),), theme_tags=tags)
    stat = ReadingStat(title, title, ("A",), 100, 100, 3600, 1_700_000_000, 3)
    return ReadingState(title=title, authors=("A",), status=status, book=book, stat=stat)


def test_excludes_unread_and_counts_described() -> None:
    states = [
        _state("Read trans", ReadingStatus.FINISHED, (_tag("trans"), _tag("literary"))),
        _state("Reading queer", ReadingStatus.READING, (_tag("queer"),)),
        _state("No tags", ReadingStatus.FINISHED, ()),
        _state("Unread queer", ReadingStatus.UNREAD, (_tag("queer"),)),  # excluded
    ]
    report = compute_diversity(states)
    assert report.total_books == 3  # the unread one is not considered
    assert report.described_books == 2  # "No tags" carries no sourced descriptor
    assert report.undescribed_books == 1
    assert round(report.coverage_pct, 3) == round(2 / 3, 3)


def test_dimensions_group_sourced_descriptors_only() -> None:
    states = [
        _state("A", ReadingStatus.FINISHED, (_tag("trans"),)),
        _state("B", ReadingStatus.FINISHED, (_tag("queer"),)),
        _state("C", ReadingStatus.FINISHED, (_tag("speculative"),)),
    ]
    report = compute_diversity(states)
    by_name = {d.name: d for d in report.dimensions}
    assert by_name["Trans & nonbinary"].books == 1
    assert by_name["Queer / LGBTQ+"].books == 1
    assert by_name["Speculative / SFF"].books == 1
    # % is a share of *described* books, never the whole shelf.
    assert round(by_name["Trans & nonbinary"].pct, 3) == round(1 / 3, 3)
    # The concrete sourced labels are surfaced for transparency.
    assert by_name["Trans & nonbinary"].matched_labels == ("trans",)


def test_empty_lenses_are_omitted() -> None:
    report = compute_diversity([_state("A", ReadingStatus.FINISHED, (_tag("trans"),))])
    names = {d.name for d in report.dimensions}
    assert names == {"Trans & nonbinary"}  # only populated lenses surface


def test_provenance_counts_by_source_kind() -> None:
    states = [
        _state("A", ReadingStatus.FINISHED, (_tag("trans", SourceKind.CALIBRE_TAG),)),
        _state(
            "B",
            ReadingStatus.FINISHED,
            (_tag("queer", SourceKind.OPENLIBRARY_SUBJECT),),
        ),
    ]
    report = compute_diversity(states)
    prov = dict(report.source_provenance)
    assert prov["calibre-tag"] == 1
    assert prov["openlibrary-subject"] == 1


def test_empty_shelf_is_safe() -> None:
    report = compute_diversity([])
    assert report.total_books == 0
    assert report.coverage_pct == 0.0
    assert report.dimensions == ()


def test_dimensions_constant_has_no_author_identity_intent() -> None:
    """The lens grouping describes books; its names must not label a person."""
    for name, labels in DIMENSIONS:
        assert name and labels
        # Lenses are descriptors of works, never claims about an author.
        assert "author" not in name.lower()


def test_demo_diversity_reflects_the_canon(states: list) -> None:
    report = compute_diversity(states)
    assert report.described_books >= 7
    by_name = {d.name: d for d in report.dimensions}
    assert by_name["Trans & nonbinary"].books >= 3
    assert by_name["Speculative / SFF"].books >= 3
