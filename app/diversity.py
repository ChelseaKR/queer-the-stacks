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
   descriptors into reader-legible lenses (see :data:`DEFAULT_DIMENSIONS`). The
   grouping is a *view over book tags*; it ships as an auditable built-in
   default and can be overridden by a validated ``data/lenses.toml`` (see
   :func:`load_lens_config`) so it is adaptable without patching source. It is
   not a classifier and it is never applied to a person.
3. **Provenance** — where the descriptors came from (Calibre vs OpenLibrary vs a
   curated list), so the reader can weigh how the picture was built. The lens
   *grouping itself* also carries provenance — built-in defaults vs a named
   config file — surfaced on :class:`DiversityReport`.

Everything is a pure function over the unified reading state, deterministic, and
local-only.
"""

from __future__ import annotations

import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ingest.models import ReadingState, ReadingStatus

#: The built-in, auditable grouping of *sourced book descriptors* into
#: reader-legible lenses. Published in code as the default/fallback: it is a
#: view, not an inference, and never touches author identity. Deployments
#: personalize this via ``data/lenses.toml`` (see :func:`load_lens_config`)
#: instead of patching this constant. Labels are matched case-insensitively
#: against a book's sourced theme tags; a book counts toward a dimension if it
#: carries *any* of that dimension's descriptors.
DEFAULT_DIMENSIONS: tuple[tuple[str, frozenset[str]], ...] = (
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

#: Back-compat alias — ``tests/test_diversity.py`` and any external callers
#: importing the old module-level constant keep working unchanged.
DIMENSIONS = DEFAULT_DIMENSIONS

#: Label shown when the built-in defaults are in effect (no config, or the
#: config degraded). Rendered verbatim in the diversity section for provenance.
BUILTIN_LENS_SOURCE = "built-in defaults"


class LensValidationError(Exception):
    """Raised when a diversity-lens config is malformed or ambiguous."""


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
    # Provenance of the *lens grouping itself* — "built-in defaults" or the
    # config file path that produced `dimensions`, plus a degradation warning
    # (never blank) when a configured file fell back to the defaults.
    lens_source: str = BUILTIN_LENS_SOURCE
    lens_warning: Optional[str] = None

    @property
    def undescribed_books(self) -> int:
        """Books with no sourced descriptor — surfaced, never hidden."""
        return self.total_books - self.described_books

    @property
    def coverage_pct(self) -> float:
        """Fraction of the considered shelf that carries any sourced descriptor."""
        return self.described_books / self.total_books if self.total_books > 0 else 0.0


def compute_diversity(
    states: list[ReadingState],
    dimensions: tuple[tuple[str, frozenset[str]], ...] = DEFAULT_DIMENSIONS,
    *,
    lens_source: str = BUILTIN_LENS_SOURCE,
    lens_warning: Optional[str] = None,
) -> DiversityReport:
    """Compute the diverse-shelf report from sourced book descriptors only.

    Considers books you've actually engaged with (reading + finished), matching
    the stats theme-mix; unread owned books are excluded so the picture reflects
    your reading, not your shelf's backlog.

    ``dimensions`` is the lens grouping to apply — the built-in defaults unless
    a caller has loaded + validated a config override (see
    :func:`load_lens_config`). ``lens_source``/``lens_warning`` are carried
    through unchanged for display provenance; this function never loads or
    validates config itself, keeping it pure over its inputs.
    """
    considered = [s for s in states if s.status is not ReadingStatus.UNREAD]
    total = len(considered)

    theme_counter: Counter[str] = Counter()
    provenance: Counter[str] = Counter()
    described = 0
    # Per-dimension book counts + the concrete labels that matched (transparency).
    dim_books: dict[str, int] = {name: 0 for name, _ in dimensions}
    dim_labels: dict[str, set[str]] = {name: set() for name, _ in dimensions}

    for state in considered:
        labels = {t.normalized for t in state.theme_tags}
        if labels:
            described += 1
        for label in labels:
            theme_counter[label] += 1
        # Provenance is counted per descriptor (a book can be described by several).
        for tag in state.theme_tags:
            provenance[str(tag.source.kind)] += 1
        for name, descriptors in dimensions:
            hit = labels & descriptors
            if hit:
                dim_books[name] += 1
                dim_labels[name] |= hit

    dim_stats = tuple(
        DimensionStat(
            name=name,
            books=dim_books[name],
            described_total=described,
            matched_labels=tuple(sorted(dim_labels[name])),
        )
        for name, _ in dimensions
        if dim_books[name] > 0  # only surface lenses your shelf actually populates
    )

    return DiversityReport(
        total_books=total,
        described_books=described,
        theme_breakdown=tuple(theme_counter.most_common()),
        dimensions=dim_stats,
        source_provenance=tuple(provenance.most_common()),
        lens_source=lens_source,
        lens_warning=lens_warning,
    )


def validate_dimensions(dims: tuple[tuple[str, frozenset[str]], ...]) -> None:
    """Assert a lens grouping has non-empty, unique labels and non-empty sets.

    Modeled on :func:`recommender.lists.validate_lists`: mandatory provenance
    for a *config*, mandatory shape for a *lens*. Raises on the first problem.
    """
    seen: set[str] = set()
    for name, descriptors in dims:
        if not name.strip():
            raise LensValidationError("a lens must have a name")
        key = name.strip().lower()
        if key in seen:
            raise LensValidationError(f"duplicate lens label: {name!r}")
        seen.add(key)
        if not descriptors:
            raise LensValidationError(f"lens {name!r} has no descriptors")


def load_dimensions(
    records: list[dict[str, object]],
) -> tuple[tuple[str, frozenset[str]], ...]:
    """Build a lens grouping from plain records (e.g. parsed from committed TOML).

    Each record needs ``name`` and ``descriptors`` (a list of strings);
    descriptors are normalized to lowercase to match
    :attr:`~ingest.models.ThemeTag.normalized`. The result is validated before
    being returned — raises :class:`LensValidationError` on any problem.
    """
    out: list[tuple[str, frozenset[str]]] = []
    for r in records:
        name = str(r.get("name", ""))
        raw = r.get("descriptors", [])
        descriptors = (
            frozenset(str(d).strip().lower() for d in raw if str(d).strip())
            if isinstance(raw, list)
            else frozenset()
        )
        out.append((name, descriptors))
    result = tuple(out)
    validate_dimensions(result)
    return result


@dataclass(frozen=True)
class LensConfig:
    """The resolved lens grouping plus where it came from, for display."""

    dimensions: tuple[tuple[str, frozenset[str]], ...]
    source: str  # BUILTIN_LENS_SOURCE, or the config file path as a string
    warning: Optional[str] = None  # set only when a configured file degraded


def load_lens_config(path: Optional[Path]) -> LensConfig:
    """Load + validate a ``[[lenses]]`` TOML file, degrading to the defaults.

    Never raises: any problem reading, parsing, or validating ``path`` produces
    a ``LensConfig`` carrying :data:`DEFAULT_DIMENSIONS` and a human-readable
    ``warning`` describing what went wrong — mirroring the FIX-09 degradation
    surface (visible, never a silent or blank fallback). ``path is None`` is
    the ordinary "no override configured" case and carries no warning.
    """
    if path is None:
        return LensConfig(dimensions=DEFAULT_DIMENSIONS, source=BUILTIN_LENS_SOURCE)

    def _degraded(warning: str) -> LensConfig:
        return LensConfig(
            dimensions=DEFAULT_DIMENSIONS, source=BUILTIN_LENS_SOURCE, warning=warning
        )

    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except OSError as exc:
        return _degraded(f"could not read lens config {path}: {exc} — using {BUILTIN_LENS_SOURCE}")
    except tomllib.TOMLDecodeError as exc:
        return _degraded(f"invalid TOML in lens config {path}: {exc} — using {BUILTIN_LENS_SOURCE}")

    records = data.get("lenses")
    if not isinstance(records, list) or not records:
        return _degraded(
            f"lens config {path} has no [[lenses]] entries — using {BUILTIN_LENS_SOURCE}"
        )

    try:
        dims = load_dimensions([r for r in records if isinstance(r, dict)])
    except LensValidationError as exc:
        return _degraded(f"lens config {path} is invalid: {exc} — using {BUILTIN_LENS_SOURCE}")

    return LensConfig(dimensions=dims, source=str(path))
