"""Curated, cited community reading lists — the canon-grounding layer.

These are *named, attributable* lists (not algorithmic bestseller feeds). They
give the recommender a values-aligned prior and let "appears on a curated list"
be a transparent, sourced reason for a pick. Membership becomes a
``CURATED_LIST`` :class:`~ingest.models.Source` on the surfaced recommendation.

The lists here are small, illustrative seeds; in deployment they are loaded from
committed, attributable sources (the reusable "ethical book-data sources" list in
the GTM plan).
"""

from __future__ import annotations

from dataclasses import dataclass

from ingest.models import Source, SourceKind


@dataclass(frozen=True)
class CuratedList:
    """A named reading list with a citation and the book ids it contains.

    ``retrieved_at`` has no default on purpose. It used to default to the
    literal ``"2026-06-05"``, which meant every caller that did not think about
    provenance still produced a plausible-looking one: ``stacks lists new``
    stamped a list authored today as retrieved in June. A retrieval date that is
    a constant is worse than no retrieval date, because it reads as evidence.
    Every construction site now has to name a date, and
    :func:`~recommender.lists_store.new_list` makes the caller supply it rather
    than reading a clock inside a pure module.
    """

    name: str
    citation: str
    book_ids: tuple[str, ...]
    retrieved_at: str

    def as_source(self) -> Source:
        return Source(
            kind=SourceKind.CURATED_LIST,
            citation=self.citation,
            retrieved_at=self.retrieved_at,
            detail=self.name,
        )

    def contains(self, book_id: str) -> bool:
        return book_id in self.book_ids


#: The day the seed lists below were compiled. It matches the rest of the demo
#: world (``ingest.demo._FETCHED``) and is duplicated rather than imported: this
#: module must not pull in the demo builder, which reaches the KOReader sync
#: client transitively. This is a real fact about a fixture, not a placeholder
#: standing in for a fact — which is precisely why it is no longer a *default*
#: on :class:`CuratedList`, where it would silently date a reader's own lists.
DEMO_LISTS_RETRIEVED_AT = "2026-06-05"

#: The seed lists used by demo mode + the eval. Each cites where it came from.
DEMO_LISTS: tuple[CuratedList, ...] = (
    CuratedList(
        name="Trans & Spec-Fic Canon",
        citation="curated-list:trans-spec-fic-canon",
        book_ids=("ol:nevada", "ol:confessions-fox", "ol:unkindness-ghosts"),
        retrieved_at=DEMO_LISTS_RETRIEVED_AT,
    ),
    CuratedList(
        name="Speculative Feminist Classics",
        citation="curated-list:speculative-feminist-classics",
        book_ids=("ol:fifth-season", "ol:dawn-butler", "ol:unkindness-ghosts"),
        retrieved_at=DEMO_LISTS_RETRIEVED_AT,
    ),
)


def lists_for(book_id: str, lists: tuple[CuratedList, ...]) -> tuple[CuratedList, ...]:
    """Every curated list that contains ``book_id``."""
    return tuple(lst for lst in lists if lst.contains(book_id))


class ListValidationError(Exception):
    """Raised when a curated list is missing required provenance."""


def validate_lists(lists: tuple[CuratedList, ...]) -> None:
    """Assert every list carries a citation + retrieved_at and at least one book.

    Provenance is mandatory: a list with no citation may not influence
    recommendations (the source-ethics commitment). Raises on the first problem.
    """
    for lst in lists:
        if not lst.name.strip():
            raise ListValidationError("a curated list must have a name")
        if not lst.citation.strip():
            raise ListValidationError(f"list {lst.name!r} has no citation")
        if not lst.retrieved_at.strip():
            raise ListValidationError(f"list {lst.name!r} has no retrieved_at date")
        if not lst.book_ids:
            raise ListValidationError(f"list {lst.name!r} contains no books")


def load_lists(records: list[dict[str, object]]) -> tuple[CuratedList, ...]:
    """Build curated lists from plain records (e.g. parsed from a committed file).

    Each record needs ``name``, ``citation``, ``book_ids`` **and**
    ``retrieved_at``. A missing date used to be filled with the literal
    ``"2026-06-05"``, so a record with no provenance came back carrying an
    authoritative-looking one; now it raises. ``validate_lists`` already refused
    an empty date, which is the same rule applied one step earlier.
    """
    out: list[CuratedList] = []
    for r in records:
        raw_ids = r.get("book_ids", [])
        book_ids = (
            tuple(str(b) for b in raw_ids if isinstance(b, str))
            if isinstance(raw_ids, list)
            else ()
        )
        name = str(r.get("name", ""))
        retrieved_at = r.get("retrieved_at")
        if retrieved_at is None:
            raise ListValidationError(
                f"list {name!r} has no retrieved_at date — a stored list must record "
                "when it was fetched or authored; there is no date to guess"
            )
        out.append(
            CuratedList(
                name=name,
                citation=str(r.get("citation", "")),
                book_ids=book_ids,
                retrieved_at=str(retrieved_at),
            )
        )
    result = tuple(out)
    validate_lists(result)
    return result
