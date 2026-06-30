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
class DiversityReport:
    """The committed shape of the diverse-shelf analytics view."""

    total_books: int  # books on the shelf/history considered (reading + finished)
    described_books: int  # of those, how many carry >= 1 sourced descriptor
    theme_breakdown: tuple[tuple[str, int], ...]  # (sourced label, books), desc
    dimensions: tuple[DimensionStat, ...]
    source_provenance: tuple[tuple[str, int], ...]  # (source-kind, descriptor count), desc

    @property
    def undescribed_books(self) -> int:
        """Books with no sourced descriptor — surfaced, never hidden."""
        return self.total_books - self.described_books

    @property
    def coverage_pct(self) -> float:
        """Fraction of the considered shelf that carries any sourced descriptor."""
        return self.described_books / self.total_books if self.total_books > 0 else 0.0


def compute_diversity(states: list[ReadingState]) -> DiversityReport:
    """Compute the diverse-shelf report from sourced book descriptors only.

    Considers books you've actually engaged with (reading + finished), matching
    the stats theme-mix; unread owned books are excluded so the picture reflects
    your reading, not your shelf's backlog.
    """
    considered = [s for s in states if s.status is not ReadingStatus.UNREAD]
    total = len(considered)

    theme_counter: Counter[str] = Counter()
    provenance: Counter[str] = Counter()
    described = 0
    # Per-dimension book counts + the concrete labels that matched (transparency).
    dim_books: dict[str, int] = {name: 0 for name, _ in DIMENSIONS}
    dim_labels: dict[str, set[str]] = {name: set() for name, _ in DIMENSIONS}

    for state in considered:
        labels = {t.normalized for t in state.theme_tags}
        if labels:
            described += 1
        for label in labels:
            theme_counter[label] += 1
        # Provenance is counted per descriptor (a book can be described by several).
        for tag in state.theme_tags:
            provenance[str(tag.source.kind)] += 1
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
            matched_labels=tuple(sorted(dim_labels[name])),
        )
        for name, _ in DIMENSIONS
        if dim_books[name] > 0  # only surface lenses your shelf actually populates
    )

    return DiversityReport(
        total_books=total,
        described_books=described,
        theme_breakdown=tuple(theme_counter.most_common()),
        dimensions=dimensions,
        source_provenance=tuple(provenance.most_common()),
    )
