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
from ingest.taste import MAX_TOTAL_DELTA, TasteAdjustment, TasteAdjustments
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


@dataclass(frozen=True)
class ResolvedAdjustment:
    """One :class:`~ingest.taste.TasteAdjustment` with its descriptors resolved.

    A theme adjustment resolves to the single descriptor it names. A lens
    adjustment resolves to every descriptor grouped under that lens by whichever
    lens vocabulary is actually in force (``app.diversity`` owns that grouping;
    resolving *there* and passing the result in is what keeps ``recommender``
    from importing ``app``). An adjustment that resolves to no descriptors at
    all is kept, with an empty set: it then matches nothing and moves nothing,
    which is the truthful outcome for a lens the reader's vocabulary no longer
    defines — better than dropping it silently, since the reader can still see
    and undo it.
    """

    adjustment: TasteAdjustment
    descriptors: frozenset[str]


@dataclass(frozen=True)
class AdjustmentReason:
    """Why one adjustment moved one book, for the explanation."""

    adjustment: TasteAdjustment
    #: The book's own sourced descriptors that this adjustment matched, sorted.
    matched: tuple[str, ...]

    @property
    def raised(self) -> bool:
        return self.adjustment.direction == "more"


def resolve_adjustments(
    adjustments: TasteAdjustments,
    lens_descriptors: dict[str, frozenset[str]] | None = None,
) -> tuple[ResolvedAdjustment, ...]:
    """Attach each adjustment's descriptor set, ready for :func:`adjustment_delta`.

    ``lens_descriptors`` maps a lens *name* to its normalized descriptors. Lens
    names are matched case-insensitively, because the reader types the label
    they see and the built-in lenses are title-cased ("Trans & nonbinary").
    """
    by_lens = {
        " ".join(name.strip().lower().split()): frozenset(label.strip().lower() for label in labels)
        for name, labels in (lens_descriptors or {}).items()
    }
    resolved: list[ResolvedAdjustment] = []
    for adjustment in adjustments:
        if adjustment.kind == "lens":
            descriptors = by_lens.get(adjustment.match_key, frozenset())
        else:
            descriptors = frozenset({adjustment.match_key})
        resolved.append(ResolvedAdjustment(adjustment=adjustment, descriptors=descriptors))
    return tuple(resolved)


def adjustment_delta(
    book: Book, resolved: tuple[ResolvedAdjustment, ...]
) -> tuple[float, tuple[AdjustmentReason, ...]]:
    """The reader's explicit feedback, as a bounded score delta plus its reasons.

    THE ONLY WAY A BOOK IS TOUCHED IS BY A DESCRIPTOR IT ACTUALLY CARRIES. The
    match is an intersection with ``book.tag_labels``, so a book with no sourced
    descriptors gets exactly ``0.0`` from every adjustment that exists — it is
    never demoted for being undescribed, and no adjustment can ever be the sole
    reason a book appears on the shelf (a book with nothing to cite still has
    nothing to cite).

    An adjustment counts **once** however many of its descriptors match: a lens
    grouping nine labels must not be worth nine times a theme naming one, or the
    magnitude the reader chose would mean something different depending on how
    the lens file happens to be written.

    The sum is clamped to ±:data:`~ingest.taste.MAX_TOTAL_DELTA` so feedback
    stays a nudge. Reasons are returned unclamped and in full, because the
    reader is owed the list of what they asked for even when the clamp meant
    the last one changed nothing.
    """
    labels = book.tag_labels
    if not labels:
        return 0.0, ()
    total = 0.0
    reasons: list[AdjustmentReason] = []
    for entry in resolved:
        matched = tuple(sorted(labels & entry.descriptors))
        if not matched:
            continue
        total += entry.adjustment.signed_weight
        reasons.append(AdjustmentReason(adjustment=entry.adjustment, matched=matched))
    clamped = max(-MAX_TOTAL_DELTA, min(MAX_TOTAL_DELTA, total))
    return round(clamped, 6), tuple(reasons)


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
    adjustments: tuple[ResolvedAdjustment, ...] = (),
) -> list[Recommendation]:
    """Rank ``candidates`` for the reader described by ``states``.

    Owned/read books are excluded by normalized key. Ties break on ``book_id`` so
    the ordering is fully deterministic.

    ``adjustments`` is the reader's explicit taste feedback, applied on the same
    terms as in :func:`recommender.hybrid.recommend_hybrid`. It is here because
    ``stacks recommend`` says in its own docstring that it "reads the same store
    the dashboard reads, so the two never disagree" — and a preference honoured
    on the dashboard and ignored at the command line would make that false. With
    the default empty set this function is unchanged.
    """
    taste = build_taste_profile(states)
    scored: list[Recommendation] = []
    for book in candidates:
        if book_key(book) in taste.owned_keys:
            continue
        score, overlap, loved_author, lists_hit = score_candidate(taste, book, lists)
        adj_delta, adj_reasons = adjustment_delta(book, adjustments)
        score += adj_delta
        if score <= 0.0:
            continue
        if not book.theme_tags and not lists_hit:
            # Nothing here can be cited. A candidate carrying no sourced theme
            # tag and sitting on no curated list has no provenance to show, and
            # an author-only match produces a signal but no source, so
            # ``build_explanation`` would refuse it — the transparency guardrail
            # working as intended. ``recommender.explain.near_misses`` already
            # skips exactly this candidate for exactly this reason; the shelf
            # never learned to, and raised ValueError instead of ranking.
            # Catalog data really is like this: ``parse_hardcover_books`` and
            # ``parse_bookwyrm_list`` both build a Book with ``theme_tags=()``
            # when the response carries no tag block.
            continue
        explanation = build_explanation(
            book, overlap, loved_author, lists_hit, score, adjustment_reasons=adj_reasons
        )
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
