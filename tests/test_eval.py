"""Eval: the content recommender beats the popularity baseline, deterministically."""

from __future__ import annotations

from recommender.eval import (
    average_precision_at_k,
    evaluate,
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
