"""Core domain models — where the project's hard guardrails live as invariants.

The README guardrails are enforced *here*, in the type system, not merely in tests:

1. **Theme/genre tags are sourced, never auto-assigned.** A :class:`ThemeTag`
   cannot be constructed without a :class:`Source` citing where it came from
   (a Calibre tag, an OpenLibrary subject, a curated list…). There is no
   :class:`SourceKind` member representing an inference, an NLP guess, or an
   identity classifier.
2. **We describe books, we do not label authors.** :class:`Author` has *no*
   gender / sexuality / identity field. There is deliberately no place to put a
   reductive auto-assigned identity label on a person.
3. **Reading data is sensitive.** The models that carry it (:class:`ReadingStat`,
   :class:`DeviceProgress`) are plain local records; nothing here imports a
   network or analytics client. Egress is confined to the explicit API clients.
4. Every recommendation carries an :class:`Explanation` with a non-empty "why"
   and the source behind every pick (see :mod:`recommender.explain`).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional


class ProvenanceError(Exception):
    """Raised when a theme tag or recommendation lacks required provenance."""


class SourceKind(enum.Enum):
    """The **only** permitted provenance kinds for a theme/genre tag.

    Crucially there is no member here for an NLP classifier, a name-based guess,
    a cover-image model, or any other inference. Every kind names a *catalog or
    list a human or institution curated*. The sourced-tags test asserts this
    enum contains nothing inference-shaped and that the resolver accepts nothing
    else.
    """

    CALIBRE_TAG = "calibre-tag"  # a tag you (or a metadata source) put in Calibre
    OPENLIBRARY_SUBJECT = "openlibrary-subject"  # OpenLibrary subject heading
    HARDCOVER_TAG = "hardcover-tag"  # Hardcover community tag
    BOOKWYRM_SHELF = "bookwyrm-shelf"  # a federated Bookwyrm shelf/tag
    CURATED_LIST = "curated-list"  # a named, cited community reading list

    def __str__(self) -> str:
        return self.value


#: Every permitted source kind. Equal to the enum's members, by construction.
PERMITTED_SOURCES: frozenset[SourceKind] = frozenset(SourceKind)


@dataclass(frozen=True)
class Source:
    """A single citation for a theme tag or recommendation, with a fetch date.

    ``retrieved_at`` gives every tag data lineage (Quality §9 — data quality &
    lineage). A source must carry a non-empty citation.
    """

    kind: SourceKind
    citation: str  # stable reference: a list URL, an OpenLibrary key, "calibre:local"…
    retrieved_at: str  # ISO-8601 date the value was fetched
    detail: str = ""  # the raw value the source asserted (e.g. "lesbian fiction")

    def __post_init__(self) -> None:
        if not self.citation.strip():
            raise ProvenanceError("a Source must carry a non-empty citation")
        if self.kind not in PERMITTED_SOURCES:  # pragma: no cover - enum-exhaustive
            raise ProvenanceError(f"{self.kind!r} is not a permitted source")


@dataclass(frozen=True)
class ThemeTag:
    """A theme/genre descriptor *about a book*, always carrying its source.

    This is how the system represents "queer", "trans", "speculative",
    "own-voices" etc. — as a *sourced* property of a work, never an inference
    and never a label applied to a person. Two tags are equal iff their label
    and source kind match (so the same theme from two catalogs de-dupes by
    ``normalized``/kind in :func:`merge_tags`).
    """

    label: str
    source: Source

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ProvenanceError("a ThemeTag must have a non-empty label")

    @property
    def normalized(self) -> str:
        return self.label.strip().lower()


def merge_tags(tags: list[ThemeTag]) -> tuple[ThemeTag, ...]:
    """De-duplicate theme tags by normalized label, keeping first-seen provenance."""
    seen: dict[str, ThemeTag] = {}
    for tag in tags:
        seen.setdefault(tag.normalized, tag)
    return tuple(seen.values())


@dataclass(frozen=True)
class Author:
    """An author/creator.

    There is deliberately **no** identity, gender, or sexuality field here. The
    project describes *books* via sourced theme tags; it never auto-assigns a
    reductive identity label to a person. The no-author-labels test asserts this
    class exposes none of those fields.
    """

    name: str
    sort: str = ""

    @property
    def display(self) -> str:
        return self.name


@dataclass(frozen=True)
class Book:
    """A book as known to the system, keyed by a stable ``book_id``.

    ``languages`` and ``publisher`` are sourced catalog facts — read from the
    library (e.g. Calibre's ``languages``/``publishers`` tables), never
    inferred or guessed. Unknown stays first-class: an empty tuple / ``None``,
    not a heuristic. These describe the *book*, not a person, so the
    no-author-labels guardrail on :class:`Author` is untouched.
    """

    book_id: str
    title: str
    authors: tuple[Author, ...] = ()
    series: Optional[str] = None
    series_index: Optional[float] = None
    identifiers: dict[str, str] = field(default_factory=dict)  # e.g. {"isbn": "…"}
    theme_tags: tuple[ThemeTag, ...] = ()
    pubdate: Optional[str] = None
    languages: tuple[str, ...] = ()  # BCP-47 codes, sourced from Calibre
    publisher: Optional[str] = None

    @property
    def author_names(self) -> tuple[str, ...]:
        return tuple(a.name for a in self.authors)

    @property
    def tag_labels(self) -> frozenset[str]:
        return frozenset(t.normalized for t in self.theme_tags)

    @property
    def languages_lower(self) -> frozenset[str]:
        """Lowercased language codes, for case-insensitive lens matching."""
        return frozenset(lang.lower() for lang in self.languages)


@dataclass(frozen=True)
class ReadingStat:
    """Per-book reading statistics, read from KOReader (sensitive, local-only)."""

    key: str  # md5 or normalized title|author — the join key to a Book
    title: str
    authors: tuple[str, ...]
    pages_read: int
    total_pages: int
    read_time_seconds: int
    last_read_ts: int  # unix seconds; 0 if never opened
    sessions: int
    highlights: int = 0  # count of KOReader highlights for this book

    @property
    def percent_complete(self) -> float:
        if self.total_pages <= 0:
            return 0.0
        return min(1.0, self.pages_read / self.total_pages)

    @property
    def is_finished(self) -> bool:
        return self.total_pages > 0 and self.pages_read >= self.total_pages


@dataclass(frozen=True)
class DeviceProgress:
    """Cross-device progress for one document, from the KOReader sync server."""

    document: str  # KOReader document hash
    percentage: float  # 0..1
    device: str
    timestamp: int  # unix seconds

    def __post_init__(self) -> None:
        if not (0.0 <= self.percentage <= 1.0):
            raise ValueError("percentage must be in [0, 1]")


@dataclass(frozen=True)
class DailyActivity:
    """Reading activity aggregated to one calendar day (for streaks + Wrapped).

    ``day_ordinal`` is ``start_time // 86400`` (UTC days since the epoch) so day
    arithmetic — consecutive-day streaks — is exact and timezone-stable.
    """

    day_ordinal: int
    seconds: int
    pages: int


class ReadingStatus(enum.Enum):
    READING = "reading"
    FINISHED = "finished"
    UNREAD = "unread"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ReadingState:
    """A book unified across Calibre metadata + KOReader stats + device progress.

    This is the single per-book record the dashboard renders: the catalog facts,
    the local reading stats, and the freshest cross-device progress.
    """

    title: str
    authors: tuple[str, ...]
    status: ReadingStatus
    book: Optional[Book] = None
    stat: Optional[ReadingStat] = None
    progress: tuple[DeviceProgress, ...] = ()

    @property
    def percent_complete(self) -> float:
        if self.progress:
            return max(p.percentage for p in self.progress)
        return self.stat.percent_complete if self.stat else 0.0

    @property
    def latest_device(self) -> Optional[str]:
        if not self.progress:
            return None
        return max(self.progress, key=lambda p: p.timestamp).device

    @property
    def theme_tags(self) -> tuple[ThemeTag, ...]:
        return self.book.theme_tags if self.book else ()


# --- Recommendation models --------------------------------------------------


@dataclass(frozen=True)
class Signal:
    """One reason a recommendation surfaced (the "why")."""

    kind: str  # "theme" | "author" | "series" | "list" | "canon"
    detail: str
    weight: float


@dataclass(frozen=True)
class Explanation:
    """The full, human-readable justification attached to every recommendation.

    Enforces the transparency guardrail: every recommendation must show *why*
    (non-empty signals) and *where it came from* (at least one source).
    """

    signals: tuple[Signal, ...]
    sources: tuple[Source, ...]
    summary: str

    def __post_init__(self) -> None:
        if not self.signals:
            raise ProvenanceError("every recommendation must carry at least one signal")
        if not self.sources:
            raise ProvenanceError("every recommendation must cite at least one source")
        if not self.summary.strip():
            raise ProvenanceError("every recommendation must carry a non-empty summary")


@dataclass(frozen=True)
class Recommendation:
    """A scored, explained book recommendation. Immutable."""

    book: Book
    score: float
    explanation: Explanation
    rank: int = 0

    def with_rank(self, rank: int) -> Recommendation:
        from dataclasses import replace

        return replace(self, rank=rank)
