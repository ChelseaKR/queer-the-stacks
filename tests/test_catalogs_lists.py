"""Catalog source interface + curated-list helpers."""

from __future__ import annotations

import pytest
from ingest.models import Author, Book, SourceKind
from recommender.catalogs import FixtureCatalog
from recommender.lists import (
    DEMO_LISTS,
    CuratedList,
    ListValidationError,
    lists_for,
    load_lists,
    validate_lists,
)


def test_fixture_catalog_returns_books() -> None:
    book = Book(book_id="b1", title="T", authors=(Author("A"),))
    cat = FixtureCatalog((book,))
    assert cat.candidates() == (book,)


def test_curated_list_as_source() -> None:
    lst = CuratedList(name="My List", citation="curated-list:my-list", book_ids=("ol:x",))
    src = lst.as_source()
    assert src.kind is SourceKind.CURATED_LIST
    assert src.detail == "My List"
    assert lst.contains("ol:x")
    assert not lst.contains("ol:y")


def test_lists_for_finds_membership() -> None:
    hits = lists_for("ol:nevada", DEMO_LISTS)
    assert any(lst.name == "Trans & Spec-Fic Canon" for lst in hits)
    assert lists_for("ol:does-not-exist", DEMO_LISTS) == ()


def test_demo_lists_are_valid() -> None:
    validate_lists(DEMO_LISTS)  # all carry citation + retrieved_at + books


def test_validate_rejects_missing_citation() -> None:
    bad = (CuratedList(name="X", citation="", book_ids=("ol:1",)),)
    with pytest.raises(ListValidationError, match="citation"):
        validate_lists(bad)


def test_validate_rejects_empty_list() -> None:
    bad = (CuratedList(name="X", citation="c", book_ids=()),)
    with pytest.raises(ListValidationError, match="no books"):
        validate_lists(bad)


def test_load_lists_from_records() -> None:
    records: list[dict[str, object]] = [
        {
            "name": "Trans Futures",
            "citation": "curated-list:trans-futures",
            "book_ids": ["ol:nevada", "ol:dawn-butler"],
            "retrieved_at": "2026-06-05",
        }
    ]
    lists = load_lists(records)
    assert lists[0].name == "Trans Futures"
    assert lists[0].contains("ol:nevada")


def test_load_lists_validates() -> None:
    with pytest.raises(ListValidationError):
        load_lists([{"name": "No Citation", "book_ids": ["ol:1"]}])
