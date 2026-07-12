"""Diverse-shelf analytics — "how diverse is my reading?", honestly sourced.

This view answers the diversity question **without ever inferring an author's
identity**. It reuses the project's one and only representation primitive: the
:class:`~ingest.models.ThemeTag`, which is a *sourced descriptor of a book*
(a Calibre tag, an OpenLibrary subject, a curated-list label) and can never exist
without a :class:`~ingest.models.Source`. There is deliberately no name-based,
cover-image, or NLP guess anywhere here — the same guardrail the models enforce.

Three honest lenses, all derived only from sourced book descriptors:

1. **Coverage** — how much of the shelf even *carries* a sourced descriptor. An
   untagged book is reported as "no sourced descriptor", never silently counted
   as "not diverse". We are honest about what we don't know.
2. **Dimensions** — a transparent, editable grouping of those sourced
   descriptors into reader-legible lenses (see :data:`DIMENSIONS`). The grouping
   is a *view over book tags*, published here in code so it is auditable; it is
   not a classifier and it is never applied to a person.
3. **Provenance** — where the descriptors came from (Calibre vs OpenLibrary vs a
   curated list), so the reader can weigh how the picture was built.

Everything is a pure function over the unified reading state, deterministic, and
local-only.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ingest.models import ReadingState, ReadingStatus

#: A transparent, auditable grouping of *sourced book descriptors* into
#: reader-legible lenses. This is intentionally published in code: it is a view,
#: not an inference, and never touches author identity. Edit it to match your own
#: shelf's vocabulary. Labels are matched case-insensitively against a book's
#: sourced theme tags; a book counts toward a dimension if it carries *any* of
#: that dimension's descriptors.
DIMENSIONS: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "Trans & nonbinary",
        frozenset({"trans", "transgender", "nonbinary", "non-binary", "genderqueer"}),
    ),
    (
        "Queer / LGBTQ+",
        frozenset({"queer", "lgbtq", "lgbtq+", "lesbian", "gay", "bisexual", "sapphic"}),
    ),
    (
        "Speculative / SFF",
        frozenset(
            {
                "speculative",
                "science fiction",
                "sci-fi",
                "fantasy",
                "epic fantasy",
                "dystopia",
                "time travel",
                "fabulist",
                "horror",
            }
        ),
    ),
    ("Feminist", frozenset({"feminist", "feminism", "womanist"})),
    ("Literary", frozenset({"literary", "short stories", "essays"})),
    ("Historical", frozenset({"historical", "history"})),
)

#: The lenses whose descriptors are identity-adjacent — the ones a reading
#: history could be used to *out* someone by (EV-PRIVACY). When the privacy toggle
#: is on, the granular descriptors behind these lenses are aggregated/hidden in the
#: diverse-shelf view; the coarse lens *counts* stay, so the picture isn't lost.
SENSITIVE_DIMENSIONS: frozenset[str] = frozenset({"Trans & nonbinary", "Queer / LGBTQ+"})

#: The concrete sourced descriptors that fall under a sensitive lens.
SENSITIVE_DESCRIPTORS: frozenset[str] = frozenset(
    label for name, labels in DIMENSIONS if name in SENSITIVE_DIMENSIONS for label in labels
)

#: Stand-in labels used when the privacy toggle redacts granular sensitive tags.
REDACTED_LABEL = "(hidden for privacy)"
AGGREGATED_LABEL = "(sensitive descriptors — aggregated for privacy)"


@dataclass(frozen=True)
class DimensionStat:
    """One diversity lens: how many described books carry any of its descriptors."""

    name: str
    books: int  # books carrying at least one of this dimension's sourced descriptors
    described_total: int  # books carrying any sourced descriptor (the honest denominator)
    matched_labels: tuple[str, ...]  # the actual sourced labels seen, for transparency

    @property
    def pct(self) -> float:
        """Share of *described* books in this lens (never of the whole shelf)."""
        return self.books / self.described_total if self.described_total > 0 else 0.0


@dataclass(frozen=True)
class SourceRef:
    """One distinct citation that asserted a descriptor: kind + where + when."""

    kind: str  # str(SourceKind), e.g. "calibre-tag", "openlibrary-subject"
    citation: str  # the stable reference the source carried
    retrieved_at: str  # ISO-8601 date the value was fetched


@dataclass(frozen=True)
class DescriptorProvenance:
    """A single diverse-shelf descriptor with its source(s) + fetch date (R4).

    Surfaces, for every diverse-shelf tag, the :class:`~ingest.models.Source`
    kind(s), citation, and ``retrieved_at`` already stored on the tag — so the
    reader can see *who asserted* each theme/identity descriptor and when. An
    ``aggregated`` row stands in for the hidden sensitive descriptors when the
    privacy toggle is on.
    """

    label: str
    books: int  # how many considered books carry this descriptor
    sources: tuple[SourceRef, ...]
    sensitive: bool  # identity-adjacent (could out a reader)
    aggregated: bool = False  # True when this row redacts hidden sensitive labels

    @property
    def latest_retrieved_at(self) -> str:
        """The freshest fetch date across this descriptor's sources."""
        return max((s.retrieved_at for s in self.sources), default="")

    @property
    def source_kinds(self) -> tuple[str, ...]:
        """The distinct source kinds that asserted this descriptor, sorted."""
        return tuple(sorted({s.kind for s in self.sources}))


@dataclass(frozen=True)
class DiversityReport:
    """The committed shape of the diverse-shelf analytics view."""

    total_books: int  # books on the shelf/history considered (reading + finished)
    described_books: int  # of those, how many carry >= 1 sourced descriptor
    theme_breakdown: tuple[tuple[str, int], ...]  # (sourced label, books), desc
    dimensions: tuple[DimensionStat, ...]
    source_provenance: tuple[tuple[str, int], ...]  # (source-kind, descriptor count), desc
    descriptor_provenance: tuple[DescriptorProvenance, ...] = ()  # per-tag Source + retrieved_at
    hide_sensitive: bool = False  # privacy toggle: sensitive descriptors aggregated/hidden

    @property
    def undescribed_books(self) -> int:
        """Books with no sourced descriptor — surfaced, never hidden."""
        return self.total_books - self.described_books

    @property
    def coverage_pct(self) -> float:
        """Fraction of the considered shelf that carries any sourced descriptor."""
        return self.described_books / self.total_books if self.total_books > 0 else 0.0


def compute_diversity(
    states: list[ReadingState], *, hide_sensitive: bool = False
) -> DiversityReport:
    """Compute the diverse-shelf report from sourced book descriptors only.

    Considers books you've actually engaged with (reading + finished), matching
    the stats theme-mix; unread owned books are excluded so the picture reflects
    your reading, not your shelf's backlog.

    Every descriptor carries its full provenance — the :class:`SourceRef`\\ s that
    assert it, each with a citation and ``retrieved_at`` (R4). With
    ``hide_sensitive=True`` the *granular* identity-adjacent descriptors
    (:data:`SENSITIVE_DESCRIPTORS`) are aggregated into a single redacted row and
    the matching lens labels are masked — a privacy posture for screen-sharing a
    queer/trans reading history (EV-PRIVACY) — while the coarse lens counts stay.
    """
    considered = [s for s in states if s.status is not ReadingStatus.UNREAD]
    total = len(considered)

    theme_counter: Counter[str] = Counter()
    provenance: Counter[str] = Counter()
    desc_sources: dict[str, set[SourceRef]] = {}
    described = 0
    sensitive_books = 0  # distinct considered books carrying any sensitive descriptor
    # Per-dimension book counts + the concrete labels that matched (transparency).
    dim_books: dict[str, int] = {name: 0 for name, _ in DIMENSIONS}
    dim_labels: dict[str, set[str]] = {name: set() for name, _ in DIMENSIONS}

    for state in considered:
        labels = {t.normalized for t in state.theme_tags}
        if labels:
            described += 1
        if labels & SENSITIVE_DESCRIPTORS:
            sensitive_books += 1
        for label in labels:
            theme_counter[label] += 1
        # Provenance is counted per descriptor (a book can be described by several).
        for tag in state.theme_tags:
            provenance[str(tag.source.kind)] += 1
            ref = SourceRef(str(tag.source.kind), tag.source.citation, tag.source.retrieved_at)
            desc_sources.setdefault(tag.normalized, set()).add(ref)
        for name, descriptors in DIMENSIONS:
            hit = labels & descriptors
            if hit:
                dim_books[name] += 1
                dim_labels[name] |= hit

    dimensions = tuple(
        DimensionStat(
            name=name,
            books=dim_books[name],
            described_total=described,
            matched_labels=(
                (REDACTED_LABEL,)
                if hide_sensitive and name in SENSITIVE_DIMENSIONS
                else tuple(sorted(dim_labels[name]))
            ),
        )
        for name, _ in DIMENSIONS
        if dim_books[name] > 0  # only surface lenses your shelf actually populates
    )

    return DiversityReport(
        total_books=total,
        described_books=described,
        theme_breakdown=_theme_breakdown(theme_counter, hide_sensitive, sensitive_books),
        dimensions=dimensions,
        source_provenance=tuple(provenance.most_common()),
        descriptor_provenance=_descriptor_provenance(
            theme_counter, desc_sources, hide_sensitive, sensitive_books
        ),
        hide_sensitive=hide_sensitive,
    )


def _sort_ref(ref: SourceRef) -> tuple[str, str, str]:
    return (ref.kind, ref.citation, ref.retrieved_at)


def _theme_breakdown(
    theme_counter: Counter[str], hide_sensitive: bool, sensitive_books: int
) -> tuple[tuple[str, int], ...]:
    """The (label, books) breakdown, redacting sensitive labels when asked."""
    if not hide_sensitive:
        return tuple(theme_counter.most_common())
    visible = [(lbl, n) for lbl, n in theme_counter.items() if lbl not in SENSITIVE_DESCRIPTORS]
    if sensitive_books:
        visible.append((AGGREGATED_LABEL, sensitive_books))
    return tuple(sorted(visible, key=lambda item: (-item[1], item[0])))


def _descriptor_provenance(
    theme_counter: Counter[str],
    desc_sources: dict[str, set[SourceRef]],
    hide_sensitive: bool,
    sensitive_books: int,
) -> tuple[DescriptorProvenance, ...]:
    """Build per-descriptor provenance (R4), aggregating sensitive tags if hidden."""
    rows: list[DescriptorProvenance] = []
    aggregated_refs: set[SourceRef] = set()
    for label, books in theme_counter.items():
        refs = tuple(sorted(desc_sources.get(label, set()), key=_sort_ref))
        sensitive = label in SENSITIVE_DESCRIPTORS
        if hide_sensitive and sensitive:
            aggregated_refs |= set(refs)
            continue
        rows.append(DescriptorProvenance(label, books, refs, sensitive))
    if hide_sensitive and sensitive_books:
        rows.append(
            DescriptorProvenance(
                AGGREGATED_LABEL,
                sensitive_books,
                tuple(sorted(aggregated_refs, key=_sort_ref)),
                sensitive=True,
                aggregated=True,
            )
        )
    return tuple(sorted(rows, key=lambda d: (-d.books, d.label)))
