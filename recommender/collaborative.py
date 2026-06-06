"""A non-surveillance collaborative signal: curated-list co-membership.

Mainstream "people who read X also read Y" is built on tracking. Here the
collaborative signal comes only from *public, curated, cited* lists: a candidate
is boosted when it appears on a list **alongside a book by an author you've
finished**. The boost is explainable ("listed alongside Octavia E. Butler, whom
you've finished") and grounded in a source (the list), never in behavioural
surveillance.
"""

from __future__ import annotations

from dataclasses import dataclass

from ingest.models import Book, ReadingState, ReadingStatus

from recommender.lists import CuratedList, lists_for


@dataclass(frozen=True)
class CoAnchor:
    """A reason a candidate co-occurs with the reader's taste, with its source."""

    author: str  # the finished author the candidate is shelved alongside
    list_name: str
    list_citation: str


def _finished_authors(states: list[ReadingState]) -> frozenset[str]:
    return frozenset(a for s in states if s.status is ReadingStatus.FINISHED for a in s.authors)


def cooccurrence_anchors(
    states: list[ReadingState],
    candidates: tuple[Book, ...],
    lists: tuple[CuratedList, ...],
) -> dict[str, tuple[CoAnchor, ...]]:
    """Map each candidate id to the co-membership anchors that support it.

    A candidate is anchored when a curated list it appears on also contains a book
    by an author the reader has finished (a different book — not the candidate).
    Deterministic: anchors are returned sorted by (author, list_name).
    """
    pool: dict[str, Book] = {b.book_id: b for b in candidates}
    finished = _finished_authors(states)
    out: dict[str, tuple[CoAnchor, ...]] = {}
    for cand in candidates:
        anchors: set[CoAnchor] = set()
        for lst in lists_for(cand.book_id, lists):
            for member_id in lst.book_ids:
                if member_id == cand.book_id:
                    continue
                member = pool.get(member_id)
                if member is None:
                    continue
                for author in member.author_names:
                    if author in finished:
                        anchors.add(CoAnchor(author, lst.name, lst.citation))
        out[cand.book_id] = tuple(sorted(anchors, key=lambda a: (a.author, a.list_name)))
    return out
