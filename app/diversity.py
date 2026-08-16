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

import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ingest.models import ReadingState, ReadingStatus

#: A transparent, auditable grouping of *sourced book descriptors* into
#: reader-legible lenses. This is intentionally published in code: it is a view,
#: not an inference, and never touches author identity. Edit it to match your own
#: shelf's vocabulary. Labels are matched case-insensitively against a book's
#: sourced theme tags; a book counts toward a dimension if it carries *any* of
#: that dimension's descriptors.
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

#: Back-compat alias for callers importing the original constant.
DIMENSIONS = DEFAULT_DIMENSIONS

#: Label shown when the built-in defaults are in effect.
BUILTIN_LENS_SOURCE = "built-in defaults"


class LensValidationError(Exception):
    """Raised when a diversity-lens config is malformed or ambiguous."""


#: The *built-in* lenses whose descriptors are identity-adjacent — the ones a
#: reading history could be used to *out* someone by (EV-PRIVACY). When the
#: privacy toggle is on, the granular descriptors behind these lenses are
#: aggregated/hidden in the diverse-shelf view; the coarse lens *counts* stay, so
#: the picture isn't lost. A configured lens file marks its own sensitivity (see
#: :func:`resolve_sensitive_descriptors`); these names remain the default for a
#: configured lens that reuses one of them.
SENSITIVE_DIMENSIONS: frozenset[str] = frozenset({"Trans & nonbinary", "Queer / LGBTQ+"})

#: The concrete sourced descriptors that fall under a *built-in* sensitive lens.
#: This is the floor, never the whole set: redaction always unions this with the
#: descriptors of whatever sensitive lenses are actually in use, so a custom lens
#: file that drops ``queer`` from its lists cannot un-redact ``queer`` for a book
#: that carries it.
SENSITIVE_DESCRIPTORS: frozenset[str] = frozenset(
    label for name, labels in DIMENSIONS if name in SENSITIVE_DIMENSIONS for label in labels
)

#: Stand-in labels used when the privacy toggle redacts granular sensitive tags.
REDACTED_LABEL = "(hidden for privacy)"
AGGREGATED_LABEL = "(sensitive descriptors — aggregated for privacy)"


def resolve_sensitive_descriptors(
    dimensions: tuple[tuple[str, frozenset[str]], ...],
    sensitive_lens_names: Optional[frozenset[str]] = None,
) -> frozenset[str]:
    """The descriptors the privacy toggle must hide, for *these* lenses.

    The toggle exists for one situation: screen-sharing a queer or trans reading
    history. A reader personalizes ``data/lenses.toml`` precisely because the
    built-in vocabulary does not describe their shelf — so the readers most
    likely to have a custom lens file are the ones whose descriptors are furthest
    from the shipped defaults, and often the ones with the most to lose from a
    disclosure. Redacting only the twelve built-in strings protects the wrong
    person.

    Resolution:

    * ``sensitive_lens_names`` given (the configured-file path, where each
      ``[[lenses]]`` entry carries an explicit or defaulted ``sensitive`` flag) —
      honour it.
    * Not given, and the grouping *is* the built-in default — use
      :data:`SENSITIVE_DIMENSIONS`, so default behaviour is unchanged.
    * Not given, and the grouping is something else — **fail closed**: treat
      every lens as sensitive. An unmarked custom grouping carries no sensitivity
      information, and over-redacting errs the right way for what this toggle is
      for.

    The result is always unioned with :data:`SENSITIVE_DESCRIPTORS`.
    """
    if sensitive_lens_names is None:
        names = (
            SENSITIVE_DIMENSIONS
            if dimensions == DEFAULT_DIMENSIONS
            else frozenset(name for name, _ in dimensions)
        )
    else:
        names = sensitive_lens_names
    configured = {label for name, labels in dimensions if name in names for label in labels}
    return frozenset(configured | SENSITIVE_DESCRIPTORS)


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
    hide_sensitive: bool = False  # privacy toggle: *requested*, not necessarily effective
    lens_source: str = BUILTIN_LENS_SOURCE
    lens_warning: Optional[str] = None
    shelf_fallback: bool = False  # counts describe the whole shelf, not reading history
    #: How many distinct descriptors were actually removed from this report.
    #: ``hide_sensitive`` records only that the toggle was *asked for*; a view
    #: that claims descriptors are hidden while listing all of them is worse than
    #: no claim, so the renderer keys its assurance off this instead.
    redacted_descriptor_count: int = 0
    #: The sensitive vocabulary in effect, so a caller can see what "sensitive"
    #: resolved to for this reader's lenses rather than assuming the built-ins.
    sensitive_descriptors: frozenset[str] = frozenset()

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
    hide_sensitive: bool = False,
    sensitive_lens_names: Optional[frozenset[str]] = None,
) -> DiversityReport:
    """Compute the diverse-shelf report from sourced book descriptors only.

    Considers books you've actually engaged with (reading + finished), matching
    the stats theme-mix; unread owned books are excluded so the picture reflects
    your reading, not your shelf's backlog.

    Every descriptor carries its full provenance — the :class:`SourceRef`\\ s that
    assert it, each with a citation and ``retrieved_at`` (R4). With
    ``hide_sensitive=True`` the *granular* sensitive descriptors are aggregated
    into a single redacted row and the matching lens labels are masked — a
    privacy posture for screen-sharing a queer/trans reading history
    (EV-PRIVACY) — while the coarse lens names and counts stay.

    What counts as sensitive is resolved from the lens grouping actually in use,
    not from the module constant: see :func:`resolve_sensitive_descriptors`. Pass
    ``sensitive_lens_names`` to say which of ``dimensions`` are identity-adjacent
    (:func:`load_lens_config` does this from the reader's own file); omit it and
    a non-default grouping is treated as sensitive throughout, fail-closed.
    """
    considered = [s for s in states if s.status is not ReadingStatus.UNREAD]
    # A Calibre-only install has no reading status at all, so the reading filter
    # empties the report and the panel renders blank — which reads as "your
    # shelf isn't diverse" rather than "nothing here knows what you've read".
    # Fall back to the whole shelf and say so, the same honesty this module
    # already applies to books carrying no sourced descriptor.
    shelf_fallback = not considered and bool(states)
    if shelf_fallback:
        considered = list(states)
    total = len(considered)

    sensitive = resolve_sensitive_descriptors(dimensions, sensitive_lens_names)

    theme_counter: Counter[str] = Counter()
    provenance: Counter[str] = Counter()
    desc_sources: dict[str, set[SourceRef]] = {}
    described = 0
    sensitive_books = 0  # distinct considered books carrying any sensitive descriptor
    # Per-dimension book counts + the concrete labels that matched (transparency).
    dim_books: dict[str, int] = {name: 0 for name, _ in dimensions}
    dim_labels: dict[str, set[str]] = {name: set() for name, _ in dimensions}

    for state in considered:
        labels = {t.normalized for t in state.theme_tags}
        if labels:
            described += 1
        if labels & sensitive:
            sensitive_books += 1
        for label in labels:
            theme_counter[label] += 1
        # Provenance is counted per descriptor (a book can be described by several).
        for tag in state.theme_tags:
            provenance[str(tag.source.kind)] += 1
            ref = SourceRef(str(tag.source.kind), tag.source.citation, tag.source.retrieved_at)
            desc_sources.setdefault(tag.normalized, set()).add(ref)
        for name, descriptors in dimensions:
            hit = labels & descriptors
            if hit:
                dim_books[name] += 1
                dim_labels[name] |= hit

    dimension_stats = tuple(
        DimensionStat(
            name=name,
            books=dim_books[name],
            described_total=described,
            # Mask the whole matched set for a lens whose vocabulary is
            # sensitive, not just its sensitive members: leaving the rest
            # in place narrows the hidden ones by elimination.
            matched_labels=(
                (REDACTED_LABEL,)
                if hide_sensitive and descriptors & sensitive
                else tuple(sorted(dim_labels[name]))
            ),
        )
        for name, descriptors in dimensions
        if dim_books[name] > 0  # only surface lenses your shelf actually populates
    )

    # Count what was *actually* removed, not what was asked for.
    redacted = sum(1 for label in theme_counter if label in sensitive) if hide_sensitive else 0

    return DiversityReport(
        total_books=total,
        described_books=described,
        theme_breakdown=_theme_breakdown(theme_counter, hide_sensitive, sensitive_books, sensitive),
        dimensions=dimension_stats,
        source_provenance=tuple(provenance.most_common()),
        descriptor_provenance=_descriptor_provenance(
            theme_counter, desc_sources, hide_sensitive, sensitive_books, sensitive
        ),
        hide_sensitive=hide_sensitive,
        lens_source=lens_source,
        lens_warning=lens_warning,
        shelf_fallback=shelf_fallback,
        redacted_descriptor_count=redacted,
        sensitive_descriptors=sensitive,
    )


def _sort_ref(ref: SourceRef) -> tuple[str, str, str]:
    return (ref.kind, ref.citation, ref.retrieved_at)


def _theme_breakdown(
    theme_counter: Counter[str],
    hide_sensitive: bool,
    sensitive_books: int,
    sensitive_descriptors: frozenset[str],
) -> tuple[tuple[str, int], ...]:
    """The (label, books) breakdown, redacting sensitive labels when asked."""
    if not hide_sensitive:
        return tuple(theme_counter.most_common())
    visible = [(lbl, n) for lbl, n in theme_counter.items() if lbl not in sensitive_descriptors]
    if sensitive_books:
        visible.append((AGGREGATED_LABEL, sensitive_books))
    return tuple(sorted(visible, key=lambda item: (-item[1], item[0])))


def _descriptor_provenance(
    theme_counter: Counter[str],
    desc_sources: dict[str, set[SourceRef]],
    hide_sensitive: bool,
    sensitive_books: int,
    sensitive_descriptors: frozenset[str],
) -> tuple[DescriptorProvenance, ...]:
    """Build per-descriptor provenance (R4), aggregating sensitive tags if hidden."""
    rows: list[DescriptorProvenance] = []
    aggregated_refs: set[SourceRef] = set()
    for label, books in theme_counter.items():
        refs = tuple(sorted(desc_sources.get(label, set()), key=_sort_ref))
        sensitive = label in sensitive_descriptors
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
    return load_lens_records(records)[0]


def load_lens_records(
    records: list[dict[str, object]],
) -> tuple[tuple[tuple[str, frozenset[str]], ...], frozenset[str]]:
    """Parse ``[[lenses]]`` records into a grouping plus its sensitive lens names.

    Each record needs ``name`` and ``descriptors`` (a list of strings);
    descriptors are normalized to lowercase to match
    :attr:`~ingest.models.ThemeTag.normalized`. The optional ``sensitive``
    boolean says whether the privacy toggle should hide that lens's granular
    descriptors.

    **Unmarked lenses default to sensitive.** A configured file exists because
    the built-in vocabulary did not fit this reader's shelf, and the toggle
    exists for the moment a queer or trans reading history is on a shared
    screen; the cost of over-redacting a lens is a duller chart, and the cost of
    under-redacting one is the thing the toggle is for. A reader who wants a
    lens shown in full writes ``sensitive = false`` on it — which is a decision
    they have made, rather than one the defaults made for them. (The shipped
    template marks its non-identity lenses that way, so copying it reproduces
    the built-in behaviour exactly.)

    Raises :class:`LensValidationError` on any shape problem.
    """
    out: list[tuple[str, frozenset[str]]] = []
    sensitive_names: set[str] = set()
    for r in records:
        name = str(r.get("name", ""))
        raw = r.get("descriptors", [])
        descriptors = (
            frozenset(str(d).strip().lower() for d in raw if str(d).strip())
            if isinstance(raw, list)
            else frozenset()
        )
        marked = r.get("sensitive")
        if marked is None:
            is_sensitive = True  # fail closed: unmarked means we do not know
        elif isinstance(marked, bool):
            is_sensitive = marked
        else:
            raise LensValidationError(f"lens {name!r}: 'sensitive' must be true or false")
        if is_sensitive:
            sensitive_names.add(name)
        out.append((name, descriptors))
    result = tuple(out)
    validate_dimensions(result)
    return result, frozenset(sensitive_names)


@dataclass(frozen=True)
class LensConfig:
    """The resolved lens grouping plus where it came from, for display."""

    dimensions: tuple[tuple[str, frozenset[str]], ...]
    source: str  # BUILTIN_LENS_SOURCE, or the config file path as a string
    warning: Optional[str] = None  # set only when a configured file degraded
    #: Which of ``dimensions`` the privacy toggle must hide. ``None`` means "not
    #: stated" and leaves the decision to :func:`resolve_sensitive_descriptors`,
    #: which is fail-closed for anything but the built-in grouping.
    sensitive_lens_names: Optional[frozenset[str]] = None


def load_lens_config(path: Optional[Path]) -> LensConfig:
    """Load + validate a ``[[lenses]]`` TOML file, degrading to the defaults.

    Never raises: any problem reading, parsing, or validating ``path`` produces
    a ``LensConfig`` carrying :data:`DEFAULT_DIMENSIONS` and a human-readable
    ``warning`` describing what went wrong — mirroring the FIX-09 degradation
    surface (visible, never a silent or blank fallback). ``path is None`` is
    the ordinary "no override configured" case and carries no warning.
    """
    if path is None:
        return LensConfig(
            dimensions=DEFAULT_DIMENSIONS,
            source=BUILTIN_LENS_SOURCE,
            sensitive_lens_names=SENSITIVE_DIMENSIONS,
        )

    def _degraded(warning: str) -> LensConfig:
        return LensConfig(
            dimensions=DEFAULT_DIMENSIONS,
            source=BUILTIN_LENS_SOURCE,
            warning=warning,
            sensitive_lens_names=SENSITIVE_DIMENSIONS,
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
        dims, sensitive_names = load_lens_records([r for r in records if isinstance(r, dict)])
    except LensValidationError as exc:
        return _degraded(f"lens config {path} is invalid: {exc} — using {BUILTIN_LENS_SOURCE}")

    return LensConfig(
        dimensions=dims,
        source=str(path),
        sensitive_lens_names=sensitive_names,
    )
