"""Build the why-and-source explanation attached to every recommendation.

Transparency guardrail (README + audit §D): every recommendation shows *why*
(the signals) and *where it came from* (the sources). This module guarantees a
non-empty, honest explanation — shared themes, a loved author, and any curated
list the book appears on — with the actual citations behind each.
"""

from __future__ import annotations

from ingest.models import Book, Explanation, Signal, Source

from recommender.lists import CuratedList


def _dedup_sources(sources: list[Source]) -> tuple[Source, ...]:
    seen: dict[tuple[str, str], Source] = {}
    for s in sources:
        seen.setdefault((str(s.kind), s.citation), s)
    return tuple(seen.values())


def build_explanation(
    book: Book,
    overlap_themes: tuple[str, ...],
    loved_author: str | None,
    lists_hit: tuple[CuratedList, ...],
    theme_score: float,
) -> Explanation:
    """Assemble signals + the citations behind them into an :class:`Explanation`."""
    signals: list[Signal] = []
    sources: list[Source] = []

    if overlap_themes:
        shown = ", ".join(overlap_themes[:4])
        signals.append(
            Signal(
                kind="theme", detail=f"shares your themes: {shown}", weight=round(theme_score, 4)
            )
        )
        # Cite the source of each overlapping theme tag (its provenance).
        wanted = set(overlap_themes)
        for tag in book.theme_tags:
            if tag.normalized in wanted:
                sources.append(tag.source)

    if loved_author is not None:
        signals.append(
            Signal(kind="author", detail=f"by {loved_author}, whom you've finished", weight=1.0)
        )

    for lst in lists_hit:
        signals.append(Signal(kind="list", detail=f"on the curated list “{lst.name}”", weight=0.5))
        sources.append(lst.as_source())

    # Guarantee a non-empty why + at least one source even for a thin candidate:
    # fall back to the book's own sourced theme tags.
    if not signals:
        signals.append(Signal(kind="theme", detail="appears in an ethical catalog", weight=0.0))
    if not sources:
        sources.extend(tag.source for tag in book.theme_tags)
    if not sources:  # pragma: no cover - candidates always carry sourced tags
        raise ValueError("a recommendation must carry at least one source")

    summary = f"Recommended because it {signals[0].detail}."
    return Explanation(
        signals=tuple(signals),
        sources=_dedup_sources(sources),
        summary=summary,
    )
