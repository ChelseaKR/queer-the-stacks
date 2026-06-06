"""A content-based recommender over sourced themes + authors, with explanations.

The taste profile is built from the reader's own finished/in-progress books:
their *sourced* theme tags, weighted by how completely the book was read, plus
the set of authors they have finished. Candidate books from ethical catalogs are
scored by cosine similarity of their theme vector to that profile, with a bonus
for "more by an author you've finished" and curated-list membership.

Everything is deterministic (stable sorts, no RNG), so the same library yields
the same ranking — the merge-blocking reproducibility metric. Identity is never
inferred: the only signals are sourced theme tags, authorship, and curated lists.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ingest.models import Book, ReadingState, ReadingStatus, Recommendation
from ingest.unify import book_key, normalize_key

from recommender.explain import build_explanation
from recommender.lists import CuratedList, lists_for


@dataclass(frozen=True)
class TasteProfile:
    """The reader's taste, derived only from sourced signals."""

    theme_weights: dict[str, float] = field(default_factory=dict)
    finished_authors: frozenset[str] = frozenset()
    owned_keys: frozenset[str] = frozenset()

    @property
    def norm(self) -> float:
        return math.sqrt(sum(w * w for w in self.theme_weights.values()))


#: A reading book stalled below this completion is treated as a soft DNF.
DNF_MAX_PCT = 0.2


def build_taste_profile(states: list[ReadingState], *, dnf_signals: bool = False) -> TasteProfile:
    """Weight each sourced theme by how completely its books were read.

    With ``dnf_signals`` on (opt-in), a book stalled below :data:`DNF_MAX_PCT`
    contributes a *gentle negative* weight to its themes — a soft "less of this,
    please" — instead of a positive one. Off by default; finished books always
    dominate, so this only nudges.
    """
    weights: dict[str, float] = {}
    finished_authors: set[str] = set()
    owned: set[str] = set()
    for s in states:
        owned.add(normalize_key(s.title, s.authors))
        if s.status is ReadingStatus.UNREAD:
            continue
        if s.status is ReadingStatus.FINISHED:
            weight = 1.0
            finished_authors.update(s.authors)
        elif dnf_signals and s.percent_complete < DNF_MAX_PCT:
            weight = -0.5  # soft DNF: nudge away from these themes
        else:
            weight = max(0.1, s.percent_complete)
        for tag in s.theme_tags:
            weights[tag.normalized] = weights.get(tag.normalized, 0.0) + weight
    return TasteProfile(
        theme_weights=weights,
        finished_authors=frozenset(finished_authors),
        owned_keys=frozenset(owned),
    )


#: A loved-author match adds this to a candidate's theme-similarity score.
AUTHOR_BONUS = 0.15


def _cosine(taste: TasteProfile, book: Book) -> tuple[float, tuple[str, ...]]:
    """Cosine similarity of a book's (binary) theme vector to the taste vector.

    Returns (similarity, overlapping_theme_labels).
    """
    book_labels = book.tag_labels
    if not book_labels or taste.norm == 0.0:
        return 0.0, ()
    overlap = sorted(label for label in book_labels if label in taste.theme_weights)
    dot = sum(taste.theme_weights[label] for label in overlap)
    sim = dot / (taste.norm * math.sqrt(len(book_labels)))
    return sim, tuple(overlap)


def score_candidate(
    taste: TasteProfile, book: Book, lists: tuple[CuratedList, ...]
) -> tuple[float, tuple[str, ...], str | None, tuple[CuratedList, ...]]:
    """Score one candidate; return (score, overlap_themes, loved_author, lists_hit)."""
    sim, overlap = _cosine(taste, book)
    loved_author: str | None = None
    for author in book.author_names:
        if author in taste.finished_authors:
            loved_author = author
            break
    lists_hit = lists_for(book.book_id, lists)
    score = sim + (AUTHOR_BONUS if loved_author else 0.0) + (0.05 * len(lists_hit))
    return score, overlap, loved_author, lists_hit


def recommend(
    states: list[ReadingState],
    candidates: tuple[Book, ...],
    *,
    lists: tuple[CuratedList, ...] = (),
    k: int = 10,
) -> list[Recommendation]:
    """Rank ``candidates`` for the reader described by ``states``.

    Owned/read books are excluded by normalized key. Ties break on ``book_id`` so
    the ordering is fully deterministic.
    """
    taste = build_taste_profile(states)
    scored: list[Recommendation] = []
    for book in candidates:
        if book_key(book) in taste.owned_keys:
            continue
        score, overlap, loved_author, lists_hit = score_candidate(taste, book, lists)
        if score <= 0.0:
            continue
        explanation = build_explanation(book, overlap, loved_author, lists_hit, score)
        scored.append(Recommendation(book=book, score=round(score, 6), explanation=explanation))

    scored.sort(key=lambda r: (-r.score, r.book.book_id))
    return [r.with_rank(i) for i, r in enumerate(scored[:k], start=1)]


def ranked_ids(
    states: list[ReadingState],
    candidates: tuple[Book, ...],
    *,
    lists: tuple[CuratedList, ...] = (),
) -> list[str]:
    """The full deterministic ranking of candidate ids (used by the eval)."""
    return [r.book.book_id for r in recommend(states, candidates, lists=lists, k=len(candidates))]
