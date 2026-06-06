"""Catalog parsers (OpenLibrary / Hardcover / Bookwyrm), cache, and merging.

These cover the logic the live clients feed, using fixtures — no network. Each
parser must produce sourced theme tags with the right SourceKind + citation.
"""

from __future__ import annotations

from pathlib import Path

from ingest.models import SourceKind
from recommender.catalogs import (
    ResponseCache,
    merge_candidates,
    parse_bookwyrm_list,
    parse_hardcover_books,
    parse_openlibrary_subject,
)

_AT = "2026-06-05"


def test_parse_openlibrary_subject() -> None:
    payload = {
        "works": [
            {"key": "/works/OL1W", "title": "Nevada", "authors": [{"name": "Imogen Binnie"}]},
            {"title": "No Key Book", "authors": ["Plain String Author"]},
            {"no": "title"},  # skipped
            "not a dict",  # skipped
        ]
    }
    books = parse_openlibrary_subject(payload, "transgender", "https://openlibrary.org/x", _AT)
    assert len(books) == 2
    nevada = books[0]
    assert nevada.title == "Nevada"
    assert nevada.author_names == ("Imogen Binnie",)
    assert nevada.tag_labels == frozenset({"transgender"})
    src = nevada.theme_tags[0].source
    assert src.kind is SourceKind.OPENLIBRARY_SUBJECT
    assert src.retrieved_at == _AT
    assert books[1].author_names == ("Plain String Author",)


def test_parse_openlibrary_handles_garbage() -> None:
    assert parse_openlibrary_subject("nope", "x", "c", _AT) == ()
    assert parse_openlibrary_subject({"works": "bad"}, "x", "c", _AT) == ()


def test_parse_hardcover_books() -> None:
    payload = {
        "data": {
            "books": [
                {
                    "title": "An Unkindness of Ghosts",
                    "slug": "unkindness",
                    "contributions": [{"author": {"name": "Rivers Solomon"}}],
                    "cached_tags": {
                        "Genre": [{"tag": "science fiction"}, {"tag": "queer"}],
                        "Mood": [{"tag": "dark"}],
                    },
                },
                {"no_title": True},  # skipped
            ]
        }
    }
    books = parse_hardcover_books(payload, "https://api.hardcover.app/v1/graphql", _AT)
    assert len(books) == 1
    b = books[0]
    assert b.book_id == "hardcover:unkindness"
    assert b.author_names == ("Rivers Solomon",)
    assert b.tag_labels == frozenset({"science fiction", "queer", "dark"})
    assert all(t.source.kind is SourceKind.HARDCOVER_TAG for t in b.theme_tags)


def test_parse_bookwyrm_list() -> None:
    payload = {
        "books": [
            {
                "id": "42",
                "title": "Confessions of the Fox",
                "authors": [{"name": "Jordy Rosenberg"}],
                "subjects": ["trans", "speculative", "historical"],
            }
        ]
    }
    books = parse_bookwyrm_list(payload, "https://bookwyrm.social/list/7", _AT)
    assert len(books) == 1
    b = books[0]
    assert b.book_id == "bookwyrm:42"
    assert b.tag_labels == frozenset({"trans", "speculative", "historical"})
    assert all(t.source.kind is SourceKind.BOOKWYRM_SHELF for t in b.theme_tags)


def test_merge_candidates_unions_tags() -> None:
    ol = parse_openlibrary_subject(
        {
            "works": [
                {"key": "/works/OL1W", "title": "Nevada", "authors": [{"name": "Imogen Binnie"}]}
            ]
        },
        "trans",
        "https://openlibrary.org/x",
        _AT,
    )
    bw = parse_bookwyrm_list(
        {
            "books": [
                {
                    "id": "1",
                    "title": "Nevada",
                    "authors": [{"name": "Imogen Binnie"}],
                    "subjects": ["literary"],
                }
            ]
        },
        "https://bookwyrm.social/list/1",
        _AT,
    )
    merged = merge_candidates(ol, bw)
    assert len(merged) == 1  # same work, de-duped
    # Tags unioned across both sources, provenance preserved.
    assert merged[0].tag_labels == frozenset({"trans", "literary"})
    kinds = {t.source.kind for t in merged[0].theme_tags}
    assert kinds == {SourceKind.OPENLIBRARY_SUBJECT, SourceKind.BOOKWYRM_SHELF}


def test_response_cache_round_trip(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "cache.json")
    assert cache.get("https://openlibrary.org/x") is None
    cache.put("https://openlibrary.org/x", '{"ok":1}')
    assert cache.get("https://openlibrary.org/x") == '{"ok":1}'
    # Persisted: a fresh instance reads it back.
    assert ResponseCache(tmp_path / "cache.json").get("https://openlibrary.org/x") == '{"ok":1}'


def test_response_cache_memory_only() -> None:
    cache = ResponseCache()
    cache.put("u", "body")
    assert cache.get("u") == "body"
