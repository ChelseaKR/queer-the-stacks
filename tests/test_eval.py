"""Eval: the content recommender beats the popularity baseline, deterministically."""

from __future__ import annotations

from ingest.models import Author, Book, Source, SourceKind, ThemeTag
from recommender.eval import (
    average_precision_at_k,
    diversity_pairs,
    evaluate,
    intra_list_diversity,
    ndcg_at_k,
    popularity_ranking,
    precision_recall_at_k,
    to_report,
)


def test_content_beats_popularity(states: list, candidates: tuple, lists: tuple) -> None:
    results = evaluate(states, list(candidates), lists=lists, k=5)
    report = to_report(results)
    assert report["content_beats_popularity"] is True
    assert results["content"].map_at_k > results["popularity"].map_at_k


def test_popularity_ranking_orders_by_readers(candidates: tuple) -> None:
    ranked = popularity_ranking(list(candidates))
    # The mega-popular distractors come first under the baseline.
    assert ranked[0] in {"ol:thriller", "ol:memoir", "ol:fantasy-doorstop"}


def test_precision_recall_math() -> None:
    p, r = precision_recall_at_k(["a", "b", "c"], {"a", "c", "z"}, k=3)
    assert p == 2 / 3
    assert r == 2 / 3


def test_precision_recall_empty() -> None:
    assert precision_recall_at_k([], {"a"}, k=3) == (0.0, 0.0)


def test_average_precision() -> None:
    # Hits at ranks 1 and 3 -> (1/1 + 2/3) / 2.
    ap = average_precision_at_k(["a", "x", "b"], {"a", "b"}, k=3)
    assert round(ap, 4) == round((1.0 + 2 / 3) / 2, 4)


def test_average_precision_no_positives() -> None:
    assert average_precision_at_k(["a"], set(), k=3) == 0.0


def test_report_is_deterministic(states: list, candidates: tuple, lists: tuple) -> None:
    a = to_report(evaluate(states, list(candidates), lists=lists, k=5))
    b = to_report(evaluate(states, list(candidates), lists=lists, k=5))
    assert a == b


def test_hybrid_is_evaluated(states: list, candidates: tuple, lists: tuple) -> None:
    results = evaluate(states, list(candidates), lists=lists, k=5)
    assert "hybrid" in results
    assert results["hybrid"].ndcg_at_k > results["popularity"].ndcg_at_k


def test_ndcg_rewards_higher_ranks() -> None:
    pos = {"a", "b"}
    top = ndcg_at_k(["a", "b", "x"], pos, 3)
    bottom = ndcg_at_k(["x", "a", "b"], pos, 3)
    assert top == 1.0
    assert bottom < top
    assert ndcg_at_k(["x"], set(), 3) == 0.0


def _book(bid: str, *themes: str) -> Book:
    src = Source(SourceKind.OPENLIBRARY_SUBJECT, "https://openlibrary.org/x", "2026-06-05")
    return Book(
        book_id=bid,
        title=bid,
        authors=(Author("A"),),
        theme_tags=tuple(ThemeTag(t, src) for t in themes),
    )


def test_intra_list_diversity() -> None:
    same = [_book("1", "trans"), _book("2", "trans")]
    varied = [_book("1", "trans"), _book("2", "space opera")]
    same_score, varied_score = intra_list_diversity(same, 5), intra_list_diversity(varied, 5)
    assert same_score is not None and varied_score is not None
    assert same_score < varied_score


def test_an_unmeasurable_slate_is_not_scored_zero() -> None:
    """Nothing to compare is not the bottom of the scale.

    An empty slate, a single book, and a slate whose books carry no sourced
    descriptor all used to return 0.0 — the monoculture end of a scale nothing
    had been measured against.
    """
    assert intra_list_diversity([], 5) is None
    assert intra_list_diversity([_book("1", "trans")], 5) is None
    assert intra_list_diversity([_book("1"), _book("2"), _book("3")], 5) is None


def test_books_with_no_descriptor_do_not_raise_the_score() -> None:
    """An undescribed book is not evidence of variety.

    Jaccard over an empty tag set reads as maximal dissimilarity, so before this
    was fixed two books on the identical theme scored 0.0 and the same two plus
    one book carrying no descriptor scored 0.6667: absence read as variety.
    """
    same = [_book("1", "trans"), _book("2", "trans")]
    assert intra_list_diversity(same, 5) == 0.0
    assert intra_list_diversity([*same, _book("3")], 5) == 0.0
    assert intra_list_diversity([*same, _book("3"), _book("4")], 5) == 0.0


def test_diversity_pairs_reports_the_denominator_it_used() -> None:
    """The score's denominator is published beside it, so a shrink is visible."""
    slate = [_book("1", "trans"), _book("2", "space opera"), _book("3")]
    assert diversity_pairs(slate, 5) == (1, 3)
    assert diversity_pairs([_book("1"), _book("2")], 5) == (0, 1)


def test_report_includes_diversity(states: list, candidates: tuple, lists: tuple) -> None:
    results = evaluate(states, list(candidates), lists=lists, k=5)
    books = [c.book for c in candidates]
    report = to_report(results, top_books=books, k=5)
    assert "intra_list_diversity_at_k" in report
    assert report["intra_list_diversity_pairs"] == {
        "compared": diversity_pairs(books, 5)[0],
        "in_slate": diversity_pairs(books, 5)[1],
    }
