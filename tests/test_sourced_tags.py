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

from dataclasses import make_dataclass

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


#: Exactly what an author is allowed to be, in this project: a name and a sort
#: key. Not a denylist. The hard guardrail is "never auto-assign a reductive
#: identity label to a person", and a denylist can only refuse the labels
#: someone thought to write down.
AUTHOR_FIELDS = frozenset({"name", "sort"})


def test_author_carries_exactly_a_name_and_a_sort_key() -> None:
    """The Author dataclass is pinned as an equality, not screened by a denylist.

    This was a set intersection against eight exact strings — ``gender``,
    ``sex``, ``sexuality``, ``orientation``, ``identity``, ``race``,
    ``ethnicity``, ``pronouns``. ``Author`` has only ever had two fields, so
    the equality was available and strictly stronger, and the denylist let
    through every near miss: ``gender_identity``, ``pronoun`` singular,
    ``queerness``, ``identity_labels``, ``demographic``, ``lgbtq``. Each of
    those is exactly the field the README's hardest rule exists to forbid, and
    each passed.

    Adding a field to ``Author`` now fails here by construction, which makes it
    a decision someone has to defend in review rather than a name they have to
    have anticipated.
    """
    assert set(Author.__dataclass_fields__) == set(AUTHOR_FIELDS), (
        f"Author's fields are {sorted(Author.__dataclass_fields__)}, expected "
        f"{sorted(AUTHOR_FIELDS)}. Books are described by sourced theme tags; "
        "people are not labelled. A new field here needs an explicit decision."
    )


#: The denylist this file used to screen ``Author`` with, kept only so the
#: differential test below can show what it let through. Not used by any
#: assertion about the real dataclass.
SUPERSEDED_DENYLIST = frozenset(
    {"gender", "sex", "sexuality", "orientation", "identity", "race", "ethnicity", "pronouns"}
)


@pytest.mark.parametrize(
    "field_name",
    [
        "gender_identity",
        "pronoun",
        "queerness",
        "identity_labels",
        "demographic",
        "lgbtq",
        "author_race",
    ],
)
def test_a_near_miss_field_passed_the_denylist_and_fails_the_pin(field_name: str) -> None:
    """Differential: build the violating class and run both checks on it.

    Each name below is an identity label on a person — precisely what the
    README's hardest rule forbids — and each one passes the eight-string
    denylist this file used to run, because set intersection matches only
    exact names. The equality pin rejects every one.
    """
    probe = make_dataclass("AuthorProbe", [("name", str), ("sort", str), (field_name, str)])
    fields = set(probe.__dataclass_fields__)

    assert not (fields & SUPERSEDED_DENYLIST), (
        f"{field_name!r} was supposed to demonstrate a denylist miss, but the "
        "denylist catches it; pick a different name for this case"
    )
    assert fields != set(AUTHOR_FIELDS), f"the pin accepted an Author with {field_name!r}"


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
