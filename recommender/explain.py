"""Build the why-and-source explanation attached to every recommendation.

Transparency guardrail (README + audit §D): every recommendation shows *why*
(the signals) and *where it came from* (the sources). This module guarantees a
non-empty, honest explanation — shared themes, a loved author, and any curated
list the book appears on — with the actual citations behind each.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ingest.models import Book, Explanation, ReadingState, Signal, Source, SourceKind

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
                # The anchoring list's own date. This used to be the literal
                # "2026-06-05", so a list fetched today was cited as fetched in
                # June — and, because `_list_signals` dates the *same* list from
                # `as_source()`, one page could show one citation under two
                # different retrieval dates.
                retrieved_at=anchor.list_retrieved_at,
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


@dataclass(frozen=True)
class NearMiss:
    """A candidate that didn't make the recommendation shelf, sourced-explained.

    Pairs a book with its :func:`explain_absence` counterfactual — the
    per-shelf near-miss surface EXP-02 scoped as a follow-up to the pure
    function. Deliberately has no ``rank``/``score`` field the way
    :class:`~ingest.models.Recommendation` does: a near miss is not a pick,
    and giving it a badge-worthy number would misrepresent it as one.
    """

    book: Book
    explanation: Explanation


def near_misses(
    states: list[ReadingState],
    candidates: tuple[Book, ...],
    lists: tuple[CuratedList, ...],
    exclude_ids: frozenset[str],
    *,
    limit: int = 5,
) -> list[NearMiss]:
    """The best-scoring candidates that did not land on the recommendation shelf.

    ``exclude_ids`` is the set of book ids already shown as hits (from
    whichever recommender actually renders the shelf, hybrid or otherwise),
    so a near miss is never a book the reader already sees explained as a
    pick. Ranked by the plain content score
    (:func:`recommender.model.score_candidate`) descending, ties broken on
    book id, for a fully deterministic order — the same reproducibility
    guarantee every other shelf on the dashboard carries.

    Owned/read books are excluded the same way :func:`recommender.model.recommend`
    excludes them: by normalized key, not by id, since an owned copy and a
    catalog candidate for the same book carry different ids.

    A candidate with no sourced theme tags of its own and no curated-list hit
    is skipped rather than explained: :func:`explain_absence` (like
    :func:`build_explanation`) enforces the transparency guardrail that every
    explanation cite at least one source, and an untagged, unlisted candidate
    genuinely has none to give — an author-only match doesn't produce a
    source. That is a fact about the candidate's catalog data, not a bug to
    paper over by inventing a citation.
    """
    from ingest.unify import book_key

    from recommender.model import build_taste_profile, score_candidate

    taste = build_taste_profile(states)
    ranked: list[tuple[float, Book]] = []
    for book in candidates:
        if book.book_id in exclude_ids or book_key(book) in taste.owned_keys:
            continue
        score, _overlap, _loved_author, lists_hit = score_candidate(taste, book, lists)
        if not book.theme_tags and not lists_hit:
            continue
        ranked.append((score, book))

    ranked.sort(key=lambda pair: (-pair[0], pair[1].book_id))
    return [
        NearMiss(book=book, explanation=explain_absence(taste, book, lists))
        for _score, book in ranked[:limit]
    ]
