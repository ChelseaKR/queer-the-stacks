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
    """A named reading list with a citation and the book ids it contains."""

    name: str
    citation: str
    book_ids: tuple[str, ...]
    retrieved_at: str = "2026-06-05"

    def as_source(self) -> Source:
        return Source(
            kind=SourceKind.CURATED_LIST,
            citation=self.citation,
            retrieved_at=self.retrieved_at,
            detail=self.name,
        )

    def contains(self, book_id: str) -> bool:
        return book_id in self.book_ids


#: The seed lists used by demo mode + the eval. Each cites where it came from.
DEMO_LISTS: tuple[CuratedList, ...] = (
    CuratedList(
        name="Trans & Spec-Fic Canon",
        citation="curated-list:trans-spec-fic-canon",
        book_ids=("ol:nevada", "ol:confessions-fox", "ol:unkindness-ghosts"),
    ),
    CuratedList(
        name="Speculative Feminist Classics",
        citation="curated-list:speculative-feminist-classics",
        book_ids=("ol:fifth-season", "ol:dawn-butler", "ol:unkindness-ghosts"),
    ),
)


def lists_for(book_id: str, lists: tuple[CuratedList, ...]) -> tuple[CuratedList, ...]:
    """Every curated list that contains ``book_id``."""
    return tuple(lst for lst in lists if lst.contains(book_id))
