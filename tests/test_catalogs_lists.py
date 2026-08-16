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
    lst = CuratedList(
        name="My List",
        citation="curated-list:my-list",
        book_ids=("ol:x",),
        retrieved_at="2026-06-05",
    )
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
    bad = (CuratedList(name="X", citation="", book_ids=("ol:1",), retrieved_at="2026-06-05"),)
    with pytest.raises(ListValidationError, match="citation"):
        validate_lists(bad)


def test_validate_rejects_empty_list() -> None:
    bad = (CuratedList(name="X", citation="c", book_ids=(), retrieved_at="2026-06-05"),)
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


def test_curated_list_has_no_default_retrieval_date() -> None:
    """The field must stay required, so no caller can omit provenance silently.

    This is the shape of the original defect: a plausible-looking constant
    supplied by a default, reaching `stacks lists new`, the stored `lists.json`,
    and every citation rendered from them.
    """
    import dataclasses

    field = next(f for f in dataclasses.fields(CuratedList) if f.name == "retrieved_at")
    assert field.default is dataclasses.MISSING
    assert field.default_factory is dataclasses.MISSING


def test_load_lists_refuses_a_record_with_no_retrieval_date() -> None:
    with pytest.raises(ListValidationError, match="no retrieved_at date"):
        load_lists([{"name": "X", "citation": "c:x", "book_ids": ["ol:1"]}])


def test_load_lists_keeps_the_date_a_record_states() -> None:
    (lst,) = load_lists(
        [
            {
                "name": "X",
                "citation": "https://bookwyrm.social/list/42",
                "book_ids": ["ol:1"],
                "retrieved_at": "2026-08-15",
            }
        ]
    )
    assert lst.retrieved_at == "2026-08-15"
    assert lst.as_source().retrieved_at == "2026-08-15"
