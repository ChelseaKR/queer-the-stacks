"""Build the why-and-source explanation attached to every recommendation.

Transparency guardrail (README + audit §D): every recommendation shows *why*
(the signals) and *where it came from* (the sources). This module guarantees a
non-empty, honest explanation — shared themes, a loved author, and any curated
list the book appears on — with the actual citations behind each.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ingest.models import Book, Explanation, Signal, Source, SourceKind

from recommender.collaborative import CoAnchor
from recommender.lists import CuratedList

if TYPE_CHECKING:
    # Only for type-checking: recommender.model imports build_explanation from
    # this module, so a runtime import here would be circular.
    from recommender.model import TasteProfile


def _dedup_sources(sources: list[Source]) -> tuple[Source, ...]:
    seen: dict[tuple[str, str], Source] = {}
    for s in sources:
        seen.setdefault((str(s.kind), s.citation), s)
    return tuple(seen.values())


def _theme_signal(
    book: Book, overlap_themes: tuple[str, ...], theme_score: float
) -> tuple[Signal | None, list[Source]]:
    if not overlap_themes:
        return None, []
    shown = ", ".join(overlap_themes[:4])
    signal = Signal(
        kind="theme", detail=f"shares your themes: {shown}", weight=round(theme_score, 4)
    )
    # Cite the source of each overlapping theme tag (its provenance).
    wanted = set(overlap_themes)
    sources = [tag.source for tag in book.theme_tags if tag.normalized in wanted]
    return signal, sources


def _author_signal(loved_author: str | None) -> Signal | None:
    if loved_author is None:
        return None
    return Signal(kind="author", detail=f"by {loved_author}, whom you've finished", weight=1.0)


def _collab_signals(collab_anchors: tuple[CoAnchor, ...]) -> tuple[list[Signal], list[Source]]:
    signals: list[Signal] = []
    sources: list[Source] = []
    for anchor in collab_anchors:
        signals.append(
            Signal(
                kind="collaborative",
                detail=f"listed alongside {anchor.author}, whom you've finished, "
                f"on “{anchor.list_name}”",
                weight=0.6,
            )
        )
        sources.append(
            Source(
                kind=SourceKind.CURATED_LIST,
                citation=anchor.list_citation,
                retrieved_at="2026-06-05",
                detail=anchor.list_name,
            )
        )
    return signals, sources


def _aperture_signal(aperture_themes: tuple[str, ...]) -> Signal | None:
    if not aperture_themes:
        return None
    shown = ", ".join(aperture_themes[:4])
    return Signal(kind="aperture", detail=f"broadens your themes: {shown}", weight=0.05)


def _list_signals(lists_hit: tuple[CuratedList, ...]) -> tuple[list[Signal], list[Source]]:
    signals: list[Signal] = []
    sources: list[Source] = []
    for lst in lists_hit:
        signals.append(Signal(kind="list", detail=f"on the curated list “{lst.name}”", weight=0.5))
        sources.append(lst.as_source())
    return signals, sources


def _ensure_non_empty(book: Book, signals: list[Signal], sources: list[Source]) -> None:
    """Guarantee a non-empty why + at least one source even for a thin candidate.

    Falls back to the book's own sourced theme tags.
    """
    if not signals:
        signals.append(Signal(kind="theme", detail="appears in an ethical catalog", weight=0.0))
    if not sources:
        sources.extend(tag.source for tag in book.theme_tags)
    if not sources:  # pragma: no cover - candidates always carry sourced tags
        raise ValueError("a recommendation must carry at least one source")


def build_explanation(
    book: Book,
    overlap_themes: tuple[str, ...],
    loved_author: str | None,
    lists_hit: tuple[CuratedList, ...],
    theme_score: float,
    *,
    collab_anchors: tuple[CoAnchor, ...] = (),
    aperture_themes: tuple[str, ...] = (),
) -> Explanation:
    """Assemble signals + the citations behind them into an :class:`Explanation`."""
    signals: list[Signal] = []
    sources: list[Source] = []

    theme_signal, theme_sources = _theme_signal(book, overlap_themes, theme_score)
    if theme_signal is not None:
        signals.append(theme_signal)
        sources.extend(theme_sources)

    author_signal = _author_signal(loved_author)
    if author_signal is not None:
        signals.append(author_signal)

    collab_signals, collab_sources = _collab_signals(collab_anchors)
    signals.extend(collab_signals)
    sources.extend(collab_sources)

    aperture_signal = _aperture_signal(aperture_themes)
    if aperture_signal is not None:
        signals.append(aperture_signal)

    list_signals, list_sources = _list_signals(lists_hit)
    signals.extend(list_signals)
    sources.extend(list_sources)

    _ensure_non_empty(book, signals, sources)

    summary = f"Recommended because it {signals[0].detail}."
    return Explanation(
        signals=tuple(signals),
        sources=_dedup_sources(sources),
        summary=summary,
    )


def explain_absence(taste: TasteProfile, book: Book, lists: tuple[CuratedList, ...]) -> Explanation:
    """The counterfactual accounting: why ``book`` ranked low or was excluded.

    Every candidate — not just the winners — gets a sourced "why not" (audit
    §D, EXP-02): what it lacks (theme overlap, a curated-list hit, a
    finished-author match), and whether it was excluded outright as already
    owned. Signals here only ever cite sourced tags, curated lists, and
    authorship — the same honesty guardrail as :func:`build_explanation` — and
    the result is never empty, mirroring its non-empty guarantee.

    ``recommender.model`` is imported lazily: it imports :func:`build_explanation`
    from this module, so a top-level import here would be circular.
    """
    from ingest.unify import book_key

    from recommender.model import score_candidate

    signals: list[Signal] = []
    sources: list[Source] = []

    score, overlap, loved_author, lists_hit = score_candidate(taste, book, lists)

    if book_key(book) in taste.owned_keys:
        signals.append(
            Signal(kind="excluded", detail="excluded: already on your shelf", weight=0.0)
        )

    if overlap:
        shown = ", ".join(overlap[:4])
        signals.append(
            Signal(kind="theme", detail=f"shares your themes: {shown}", weight=round(score, 4))
        )
        wanted = set(overlap)
        for tag in book.theme_tags:
            if tag.normalized in wanted:
                sources.append(tag.source)
    else:
        signals.append(
            Signal(kind="theme", detail="no sourced tags overlap your taste", weight=0.0)
        )

    if loved_author is not None:
        signals.append(
            Signal(kind="author", detail=f"by {loved_author}, whom you've finished", weight=1.0)
        )
    else:
        signals.append(Signal(kind="author", detail="no finished-author match", weight=0.0))

    if lists_hit:
        for lst in lists_hit:
            signals.append(
                Signal(kind="list", detail=f"already on the curated list “{lst.name}”", weight=0.0)
            )
            sources.append(lst.as_source())
    else:
        signals.append(Signal(kind="list", detail="would rise if on a cited list", weight=0.0))

    # Cite the book's own sourced theme tags so the accounting is never bare,
    # even for a candidate with zero overlap and no list membership.
    if not sources:
        sources.extend(tag.source for tag in book.theme_tags)
    if not sources:  # pragma: no cover - candidates always carry sourced tags
        raise ValueError("an absence explanation must carry at least one source")

    summary = f"Ranked as it did because it {signals[0].detail}."
    return Explanation(
        signals=tuple(signals),
        sources=_dedup_sources(sources),
        summary=summary,
    )
