"""Representation guardrail — sourced theme tags only; never label an author.

The README's hard rule: books are described via *sourced* theme/genre tags, never
reductive auto-assigned identity labels, and authors are never labelled at all.
These tests prove, structurally:

1. A :class:`ThemeTag` cannot exist without a :class:`Source` — there is no
   unsourced/auto-assigned tag path.
2. No permitted :class:`SourceKind` is inference-shaped (no NLP/classifier/guess).
3. :class:`Author` exposes no gender/sexuality/identity field — there is nowhere
   to put a reductive label on a person.
"""

from __future__ import annotations

import pytest
from ingest.models import (
    PERMITTED_SOURCES,
    Author,
    Book,
    ProvenanceError,
    Source,
    SourceKind,
    ThemeTag,
)

FORBIDDEN_TOKENS = frozenset(
    {"infer", "guess", "predict", "heuristic", "classify", "nlp", "model", "auto"}
)


def test_theme_tag_requires_a_source() -> None:
    """You cannot build a ThemeTag without passing a Source (it is required)."""
    with pytest.raises(TypeError):
        ThemeTag(label="queer")  # type: ignore[call-arg]


def test_source_requires_a_citation() -> None:
    with pytest.raises(ProvenanceError):
        Source(kind=SourceKind.CALIBRE_TAG, citation="   ", retrieved_at="2026-06-05")


def test_no_source_kind_is_inference_shaped() -> None:
    for kind in SourceKind:
        haystack = f"{kind.name} {kind.value}".lower()
        for token in FORBIDDEN_TOKENS:
            assert token not in haystack, f"{kind!r} looks inference-derived"


def test_permitted_sources_is_closed() -> None:
    assert frozenset(SourceKind) == PERMITTED_SOURCES


def test_author_has_no_identity_fields() -> None:
    """The Author dataclass must not carry any identity/gender/sexuality label."""
    fields = set(Author.__dataclass_fields__)
    forbidden = {
        "gender",
        "sex",
        "sexuality",
        "orientation",
        "identity",
        "race",
        "ethnicity",
        "pronouns",
    }
    assert not (fields & forbidden), f"Author must not label people: {fields & forbidden}"


def test_themes_describe_books_not_people() -> None:
    """A ThemeTag attaches to a Book; nothing attaches identity to an Author."""
    src = Source(SourceKind.CURATED_LIST, "curated-list:x", "2026-06-05", "trans")
    book = Book(
        book_id="b1", title="T", authors=(Author("A"),), theme_tags=(ThemeTag("trans", src),)
    )
    assert book.tag_labels == frozenset({"trans"})
    # The author carries only a name.
    assert book.authors[0].name == "A"
    assert not hasattr(book.authors[0], "gender")


def test_empty_label_rejected() -> None:
    src = Source(SourceKind.CALIBRE_TAG, "calibre:local", "2026-06-05")
    with pytest.raises(ProvenanceError):
        ThemeTag(label="  ", source=src)
