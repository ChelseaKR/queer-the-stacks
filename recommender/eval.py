"""Offline evaluation: does the content recommender beat a popularity baseline?

Protocol (M3 acceptance criterion — "recs fit your canon better than popularity"):

1. Ground-truth positives = candidate books flagged ``on_canon`` (genuine
   canon-fit discoveries, curated independently of popularity).
2. Rank candidates two ways — the content recommender (sourced themes + authors +
   curated lists) and a popularity baseline (most readers first) — and score
   precision / recall / MAP@k.

The premise: the strongest canon fits are *not* the most popular books, so a
popularity feed misses them while the content model recovers them. Everything is
deterministic (stable sorts), so the eval is reproducible without a seed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol, runtime_checkable

from ingest.models import Book, ReadingState

from recommender.lists import CuratedList
from recommender.model import ranked_ids


@runtime_checkable
class PopCandidate(Protocol):
    """A candidate carrying a popularity proxy + the eval ground-truth flag."""

    @property
    def book(self) -> Book: ...

    @property
    def readers(self) -> int: ...

    @property
    def on_canon(self) -> bool: ...


@dataclass(frozen=True)
class EvalResult:
    model: str
    k: int
    precision_at_k: float
    recall_at_k: float
    map_at_k: float
    ndcg_at_k: float
    n_positives: int


def precision_recall_at_k(ranked: list[str], positives: set[str], k: int) -> tuple[float, float]:
    top = ranked[:k]
    if not top:
        return 0.0, 0.0
    hits = sum(1 for bid in top if bid in positives)
    precision = hits / len(top)
    recall = hits / len(positives) if positives else 0.0
    return precision, recall


def average_precision_at_k(ranked: list[str], positives: set[str], k: int) -> float:
    if not positives:
        return 0.0
    hits = 0
    cumulative = 0.0
    for i, bid in enumerate(ranked[:k], start=1):
        if bid in positives:
            hits += 1
            cumulative += hits / i
    return cumulative / min(len(positives), k)


def ndcg_at_k(ranked: list[str], positives: set[str], k: int) -> float:
    """Binary-relevance nDCG@k: rewards putting positives higher in the ranking."""
    import math

    if not positives:
        return 0.0
    dcg = sum(
        1.0 / math.log2(i + 1) for i, bid in enumerate(ranked[:k], start=1) if bid in positives
    )
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(positives), k) + 1))
    return dcg / ideal if ideal else 0.0


def intra_list_diversity(books: list[Book], k: int) -> float:
    """1 - mean pairwise Jaccard similarity of theme sets across the top-k.

    Higher = a more thematically varied slate (the anti-monoculture metric).
    """
    top = books[:k]
    tagsets = [b.tag_labels for b in top]
    pairs = [(a, b) for i, a in enumerate(tagsets) for b in tagsets[i + 1 :]]
    if not pairs:
        return 0.0
    sims = []
    for a, b in pairs:
        union = a | b
        sims.append(len(a & b) / len(union) if union else 0.0)
    return round(1.0 - sum(sims) / len(sims), 4)


def _score(model: str, ranked: list[str], positives: set[str], k: int) -> EvalResult:
    precision, recall = precision_recall_at_k(ranked, positives, k)
    return EvalResult(
        model=model,
        k=k,
        precision_at_k=round(precision, 4),
        recall_at_k=round(recall, 4),
        map_at_k=round(average_precision_at_k(ranked, positives, k), 4),
        ndcg_at_k=round(ndcg_at_k(ranked, positives, k), 4),
        n_positives=len(positives),
    )


def popularity_ranking(candidates: list[PopCandidate]) -> list[str]:
    """Baseline: candidates by reader count, descending (id tie-break)."""
    ordered = sorted(candidates, key=lambda c: (-c.readers, c.book.book_id))
    return [c.book.book_id for c in ordered]


def evaluate(
    states: list[ReadingState],
    candidates: list[PopCandidate],
    *,
    lists: tuple[CuratedList, ...] = (),
    k: int = 5,
) -> dict[str, EvalResult]:
    """Run the content model and the popularity baseline on the same candidates."""
    from recommender.hybrid import recommend_hybrid

    positives = {c.book.book_id for c in candidates if c.on_canon}
    books = tuple(c.book for c in candidates)
    content_ranked = ranked_ids(states, books, lists=lists)
    hybrid_recs = recommend_hybrid(states, books, lists=lists, k=len(books), aperture_strength=0.0)
    hybrid_ranked = [r.book.book_id for r in hybrid_recs]
    pop_ranked = popularity_ranking(candidates)
    return {
        "content": _score("content", content_ranked, positives, k),
        "hybrid": _score("hybrid", hybrid_ranked, positives, k),
        "popularity": _score("popularity", pop_ranked, positives, k),
    }


def to_report(
    results: dict[str, EvalResult], *, top_books: list[Book] | None = None, k: int = 5
) -> dict[str, object]:
    """A JSON-able report (the committed eval artifact)."""
    content = results["content"]
    popularity = results["popularity"]
    report: dict[str, object] = {
        "k": content.k,
        "n_positives": content.n_positives,
        "models": {name: asdict(res) for name, res in results.items()},
        "content_beats_popularity": (
            content.map_at_k > popularity.map_at_k
            or (
                content.map_at_k == popularity.map_at_k
                and content.recall_at_k >= popularity.recall_at_k
            )
        ),
    }
    if top_books is not None:
        report["intra_list_diversity_at_k"] = intra_list_diversity(top_books, k)
    return report
