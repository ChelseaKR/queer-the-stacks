"""Eval: the content recommender beats the popularity baseline, deterministically."""

from __future__ import annotations

from ingest.models import Author, Book, Source, SourceKind, ThemeTag
from recommender.eval import (
    average_precision_at_k,
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


def test_no_ground_truth_is_not_a_win(states: list, candidates: tuple, lists: tuple) -> None:
    """With nothing flagged ``on_canon`` the verdict is absent, not True.

    Every metric is zero over an empty ``positives`` set, so the tie-break in
    ``to_report`` answered True and ``stacks eval`` exited 0: the claim read the same
    whether the content model beat popularity or nothing was compared at all. Three
    ways to reach that state, all of which used to publish a win.
    """
    from dataclasses import replace

    unflagged = [replace(c, on_canon=False) for c in candidates]
    for label, these_states, these_candidates in (
        ("no candidate is on_canon", states, unflagged),
        ("no candidates at all", states, []),
        ("no reading history and no ground truth", [], unflagged),
    ):
        report = to_report(evaluate(these_states, these_candidates, lists=lists, k=5))
        assert report["n_positives"] == 0, label
        assert report["content_beats_popularity"] is None, label


def test_a_real_loss_is_still_reported_as_one(
    states: list, candidates: tuple, lists: tuple
) -> None:
    """The absent verdict must not swallow a genuine failure to beat the baseline.

    Ground truth exists here, so the comparison happened; only its answer is bad.
    """
    from dataclasses import replace

    results = evaluate(states, list(candidates), lists=lists, k=5)
    beaten = replace(results["content"], map_at_k=0.0, recall_at_k=0.0)
    report = to_report({**results, "content": beaten})
    assert report["n_positives"] > 0
    assert report["content_beats_popularity"] is False


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
    assert intra_list_diversity(same, 5) < intra_list_diversity(varied, 5)
    assert intra_list_diversity([], 5) == 0.0


def test_report_includes_diversity(states: list, candidates: tuple, lists: tuple) -> None:
    results = evaluate(states, list(candidates), lists=lists, k=5)
    books = [c.book for c in candidates]
    report = to_report(results, top_books=books, k=5)
    assert "intra_list_diversity_at_k" in report
