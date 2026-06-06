"""Catalog source interface + curated-list helpers."""

from __future__ import annotations

from ingest.models import Author, Book, SourceKind
from recommender.catalogs import FixtureCatalog
from recommender.lists import DEMO_LISTS, CuratedList, lists_for


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
