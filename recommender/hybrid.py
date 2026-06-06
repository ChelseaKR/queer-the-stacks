"""The hybrid recommender — content + curated-list co-occurrence + optional
local embeddings + a boost-only aperture lens, with a fully-explained result.

Score = content theme/author/list similarity (see :mod:`recommender.model`)
      + curated-list co-occurrence boost (see :mod:`recommender.collaborative`)
      + optional local-embedding semantic similarity (off by default)
      + boost-only aperture widening (see :mod:`recommender.rerank`).

Every component is sourced and explainable; nothing here infers identity or sends
reading data anywhere. Deterministic by construction (stable sorts, no RNG).
"""

from __future__ import annotations

from ingest.models import Book, ReadingState, ReadingStatus, Recommendation
from ingest.unify import book_key

from recommender.collaborative import cooccurrence_anchors
from recommender.embeddings import (
    DEFAULT_DIM,
    Embedder,
    HashingEmbedder,
    book_text,
    cosine,
    taste_vector,
)
from recommender.explain import build_explanation
from recommender.lists import CuratedList
from recommender.model import build_taste_profile, score_candidate

#: Blend weights for the non-content signals (content score is ~0..1 already).
COLLAB_WEIGHT = 0.2
EMBEDDING_WEIGHT = 0.1


def _taste_texts(states: list[ReadingState]) -> list[str]:
    return [
        book_text(s.book)
        for s in states
        if s.book is not None and s.status is not ReadingStatus.UNREAD
    ]


def recommend_hybrid(
    states: list[ReadingState],
    candidates: tuple[Book, ...],
    *,
    lists: tuple[CuratedList, ...] = (),
    k: int = 10,
    aperture_strength: float = 0.0,
    use_embeddings: bool = False,
    dnf_signals: bool = False,
    embedder: Embedder | None = None,
) -> list[Recommendation]:
    """Rank candidates by the full hybrid score, each with a sourced explanation."""
    from recommender.rerank import aperture_boost  # local import avoids a cycle

    taste = build_taste_profile(states, dnf_signals=dnf_signals)
    anchors_by_id = cooccurrence_anchors(states, candidates, lists)

    emb: Embedder | None = None
    taste_vec: list[float] = []
    if use_embeddings:
        emb = embedder or HashingEmbedder(DEFAULT_DIM)
        taste_vec = taste_vector(_taste_texts(states), emb)

    scored: list[Recommendation] = []
    for book in candidates:
        if book_key(book) in taste.owned_keys:
            continue
        content, overlap, loved_author, lists_hit = score_candidate(taste, book, lists)

        anchors = anchors_by_id.get(book.book_id, ())
        collab = COLLAB_WEIGHT if anchors else 0.0

        emb_sim = 0.0
        if emb is not None and taste_vec:
            emb_sim = max(0.0, cosine(taste_vec, emb.embed(book_text(book))))
        emb_boost = EMBEDDING_WEIGHT * emb_sim

        ap_boost, ap_themes = aperture_boost(taste, book, aperture_strength)

        total = content + collab + emb_boost + ap_boost
        if total <= 0.0:
            continue

        explanation = build_explanation(
            book,
            overlap,
            loved_author,
            lists_hit,
            content,
            collab_anchors=anchors,
            aperture_themes=ap_themes,
        )
        scored.append(Recommendation(book=book, score=round(total, 6), explanation=explanation))

    scored.sort(key=lambda r: (-r.score, r.book.book_id))
    return [r.with_rank(i) for i, r in enumerate(scored[:k], start=1)]
