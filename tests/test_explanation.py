"""Transparency guardrail — every recommendation shows why + source (100%)."""

from __future__ import annotations

import pytest
from ingest.models import Explanation, ProvenanceError, Signal, Source, SourceKind
from recommender.model import recommend


def test_every_recommendation_has_why_and_source(
    states: list, candidates: tuple, lists: tuple
) -> None:
    recs = recommend(states, tuple(c.book for c in candidates), lists=lists, k=10)
    assert recs
    for rec in recs:
        assert rec.explanation.signals, f"{rec.book.title} has no why"
        assert rec.explanation.sources, f"{rec.book.title} has no source"
        assert rec.explanation.summary.strip()


def test_explanation_cites_theme_sources(states: list, candidates: tuple, lists: tuple) -> None:
    recs = recommend(states, tuple(c.book for c in candidates), lists=lists, k=10)
    nevada = next(r for r in recs if r.book.title == "Nevada")
    kinds = {str(s.kind) for s in nevada.explanation.sources}
    # Nevada is on a curated list and its themes are list-sourced.
    assert "curated-list" in kinds


def test_explanation_requires_signals() -> None:
    src = Source(SourceKind.CURATED_LIST, "curated-list:x", "2026-06-05")
    with pytest.raises(ProvenanceError):
        Explanation(signals=(), sources=(src,), summary="x")


def test_explanation_requires_sources() -> None:
    with pytest.raises(ProvenanceError):
        Explanation(signals=(Signal("theme", "d", 1.0),), sources=(), summary="x")


def test_explanation_requires_summary() -> None:
    src = Source(SourceKind.CURATED_LIST, "curated-list:x", "2026-06-05")
    with pytest.raises(ProvenanceError):
        Explanation(signals=(Signal("theme", "d", 1.0),), sources=(src,), summary="  ")
