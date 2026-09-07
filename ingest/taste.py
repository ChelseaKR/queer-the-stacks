"""Explicit, reversible taste feedback — the reader's own words, stored locally.

Until now taste was *inferred*: :func:`recommender.model.build_taste_profile`
weights a sourced theme by how completely its books were read, and the optional
DNF signal infers dislike from a stall. Both are guesses about intent read off
behaviour. A reader who wanted more translated work before owning any, or less
of a theme without finishing fewer books, had no way to say so.

An adjustment is the honest alternative: a bounded, dated, reversible record the
reader wrote on purpose, blended into the ranking and quoted back verbatim in the
explanation of every pick it moved. It is not derived from catalog data, it is
never shared, and it lives only in the local app-state store.

FOUR RULES, EACH OF WHICH IS A REFUSAL SOMEWHERE BELOW.

1. **Bounded.** Magnitude comes from a closed set of three
   (:data:`MAGNITUDES`), and the summed effect on any one book is clamped to
   ±:data:`MAX_TOTAL_DELTA`. Feedback nudges the ranking; it never replaces it.
   Without the clamp, "strong" repeated eight times would be a manual ordering
   wearing a recommender's clothes.

2. **Lenses are boost-only.** A lens (``Trans & nonbinary``, ``Feminist``) is a
   grouping of identity-adjacent descriptors, and this project's values-lens
   pattern is that such a lens may raise a book and may never lower one. "More
   small press" must not become a penalty on everything that is not small press,
   because that penalty would land on books whose descriptors are simply
   *unrecorded*. ``less`` on a lens is refused by name.

3. **Unknown stays first-class.** An adjustment may only ever match a book by a
   descriptor the book actually carries, so a book with no sourced descriptors
   receives a delta of exactly zero from every adjustment that exists — it is
   never demoted for being undescribed. And an adjustment may not *target*
   absence: :data:`UNADJUSTABLE_TARGETS` refuses the undescribed bucket and the
   privacy toggle's placeholder labels, because "less of the books we know
   nothing about" is a preference about this app's coverage gaps, not about
   books, and acting on it would bury exactly the books whose data is thinnest.

4. **Reversible, exactly.** :meth:`TasteAdjustments.without` removes one record
   by its stable key and nothing else, so undo restores the previous ranking
   byte-for-byte rather than approximately — the ranking is a pure function of
   the profile and the adjustment set, and the set is back to what it was.

Nothing here reads the wall clock; ``created_at`` is always passed in, so a
dated record is as testable as any other pure value in this package.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

#: The closed set of magnitudes, in score units.
#:
#: Calibrated against the signals already in the score so feedback is legible
#: next to them rather than dominant: a curated-list hit adds 0.05, a
#: finished-author match 0.15 (``recommender.model.AUTHOR_BONUS``), and the
#: collaborative anchor 0.2 (``recommender.hybrid.COLLAB_WEIGHT``). So "slight"
#: is worth about one curated-list hit, and "strong" a little more than a loved
#: author — a reader's explicit statement can outweigh an inference, which is
#: the point, but not by an order of magnitude.
MAGNITUDES: dict[str, float] = {"slight": 0.05, "moderate": 0.10, "strong": 0.20}

#: The most any book's score may move, in either direction, from all
#: adjustments combined.
MAX_TOTAL_DELTA = 0.30

#: Both directions. ``less`` is legal on a theme and refused on a lens (rule 2).
DIRECTIONS: tuple[str, ...] = ("more", "less")

#: What an adjustment may be about.
KINDS: tuple[str, ...] = ("theme", "lens")

#: Targets that name an absence rather than a descriptor, refused by
#: :func:`validate`. The first is the diversity view's undescribed bucket; the
#: other two are the placeholder labels the privacy toggle substitutes for
#: sensitive descriptors, which are not descriptors a book carries and would
#: match nothing while looking as though they had been recorded.
UNADJUSTABLE_TARGETS: frozenset[str] = frozenset(
    {
        "",
        "unknown",
        "no sourced descriptor",
        "(hidden for privacy)",
        "(sensitive descriptors — aggregated for privacy)",
    }
)


class AdjustmentError(ValueError):
    """Raised when an adjustment is malformed, unbounded, or about an absence."""


def normalize_target(raw: str) -> str:
    """Lower-case and collapse whitespace, matching ``ThemeTag.normalized``.

    Theme labels are matched case-insensitively everywhere else in this project
    (``app.diversity`` says so explicitly), so an adjustment written as
    "Speculative" and a tag recorded as "speculative" must be the same thing.
    Lens *names* are matched by their own exact label and are normalized the same
    way only for the purpose of the refusal check below.
    """
    return " ".join(raw.strip().lower().split())


@dataclass(frozen=True)
class TasteAdjustment:
    """One bounded, dated weight the reader asked for, in their own words.

    ``target`` is stored as the reader typed it (trimmed) so the explanation can
    quote it verbatim; ``match_key`` is the normalized form the recommender
    compares against sourced descriptors.
    """

    kind: str
    target: str
    direction: str
    magnitude: str
    created_at: int

    @property
    def match_key(self) -> str:
        return normalize_target(self.target)

    @property
    def key(self) -> str:
        """Stable identity for undo. One record per (kind, target) at a time."""
        return f"{self.kind}:{self.match_key}"

    @property
    def handle(self) -> str:
        """An opaque, stable id for this record, safe to put in rendered HTML.

        The undo control needs to name which adjustment to remove. Naming it by
        :attr:`key` would write the descriptor into a form value — and when the
        privacy toggle is on, the whole point is that sensitive descriptors do
        not appear in the document at all. A shoulder-surfer reading
        ``value="theme:trans"`` out of an undo button would have exactly what
        the toggle was hiding two sections above.

        So the control carries a digest instead, and the server resolves it
        against the reader's own set (:meth:`TasteAdjustments.by_handle`). It is
        derived, not random, so it is stable across renders without any stored
        mapping.
        """
        import hashlib

        return hashlib.blake2s(self.key.encode("utf-8"), digest_size=8).hexdigest()

    @property
    def signed_weight(self) -> float:
        """The score contribution of this record, before the total clamp."""
        weight = MAGNITUDES[self.magnitude]
        return weight if self.direction == "more" else -weight

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "target": self.target,
            "direction": self.direction,
            "magnitude": self.magnitude,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(raw: object) -> Optional[TasteAdjustment]:
        """Rebuild one record, or ``None`` if it is not one this build accepts.

        Deliberately lenient in shape and strict in content: a persisted record
        written by a future build with an unknown magnitude is dropped rather
        than coerced to a known one, because coercion would silently apply a
        weight the reader never chose.
        """
        if not isinstance(raw, dict):
            return None
        kind = str(raw.get("kind", ""))
        target = str(raw.get("target", ""))
        direction = str(raw.get("direction", ""))
        magnitude = str(raw.get("magnitude", ""))
        created = raw.get("created_at")
        if not isinstance(created, int):
            return None
        try:
            return validate(
                TasteAdjustment(
                    kind=kind,
                    target=target,
                    direction=direction,
                    magnitude=magnitude,
                    created_at=created,
                )
            )
        except AdjustmentError:
            return None


def validate(adjustment: TasteAdjustment) -> TasteAdjustment:
    """Return ``adjustment`` unchanged, or raise :class:`AdjustmentError`.

    Every refusal here is one of the four rules in the module docstring, and
    each is a refusal rather than a silent correction: an adjustment the reader
    did not get is a thing they can see and retype, while an adjustment quietly
    turned into a different one is not.
    """
    if adjustment.kind not in KINDS:
        raise AdjustmentError(f"kind must be one of {', '.join(KINDS)}, not {adjustment.kind!r}")
    if adjustment.direction not in DIRECTIONS:
        raise AdjustmentError(
            f"direction must be one of {', '.join(DIRECTIONS)}, not {adjustment.direction!r}"
        )
    if adjustment.magnitude not in MAGNITUDES:
        raise AdjustmentError(
            f"magnitude must be one of {', '.join(sorted(MAGNITUDES))}, "
            f"not {adjustment.magnitude!r}"
        )
    if adjustment.match_key in UNADJUSTABLE_TARGETS:
        raise AdjustmentError(
            f"{adjustment.target!r} names an absence, not a descriptor: a book with no "
            "sourced descriptor is undescribed, not disliked, and may not be adjusted "
            "against"
        )
    if adjustment.kind == "lens" and adjustment.direction == "less":
        raise AdjustmentError(
            "a lens may only ever raise a book, never lower one — leaning toward a lens "
            "must not become a penalty on books whose descriptors are simply unrecorded"
        )
    if adjustment.created_at < 0:
        raise AdjustmentError("created_at must be a non-negative unix timestamp")
    return adjustment


@dataclass(frozen=True)
class TasteAdjustments:
    """The reader's current adjustment set: an ordered, deduplicated collection.

    Ordering is by ``key`` rather than by insertion, so the persisted document,
    the rendered list, and the archive export are all deterministic and a
    re-saved set is byte-identical to the one before it.
    """

    records: tuple[TasteAdjustment, ...] = ()

    def __len__(self) -> int:
        return len(self.records)

    def __iter__(self):  # type: ignore[no-untyped-def] # tuple's own iterator
        return iter(self.records)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(a.key for a in self.records)

    def with_added(self, adjustment: TasteAdjustment) -> TasteAdjustments:
        """Add or replace the record for this ``(kind, target)``.

        Replacing rather than accumulating is what keeps the set bounded in the
        way a reader would expect: asking twice for "more feminist" is the same
        request, not double the weight.
        """
        validate(adjustment)
        kept = [a for a in self.records if a.key != adjustment.key]
        kept.append(adjustment)
        return replace(self, records=tuple(sorted(kept, key=lambda a: a.key)))

    def without(self, key: str) -> TasteAdjustments:
        """Remove exactly the record with this key; everything else is untouched."""
        return replace(self, records=tuple(a for a in self.records if a.key != key))

    def by_handle(self, handle: str) -> Optional[TasteAdjustment]:
        """The record whose opaque :attr:`TasteAdjustment.handle` matches, if any.

        Resolved by scanning the reader's own set rather than by inverting the
        digest, so a handle for an adjustment they do not have resolves to
        nothing instead of to some other reader's record.
        """
        for record in self.records:
            if record.handle == handle:
                return record
        return None

    def cleared(self) -> TasteAdjustments:
        return replace(self, records=())

    def as_dict(self) -> dict[str, object]:
        return {"records": [a.as_dict() for a in self.records]}

    @staticmethod
    def from_dict(raw: object) -> TasteAdjustments:
        """Rebuild from a persisted document, tolerating its absence.

        A store written before this feature existed yields the empty set, which
        is the honest reading: the reader never asked for anything, and the
        ranking is exactly what it was.
        """
        if not isinstance(raw, dict):
            return TasteAdjustments()
        rows = raw.get("records")
        if not isinstance(rows, list):
            return TasteAdjustments()
        parsed = [a for a in (TasteAdjustment.from_dict(row) for row in rows) if a is not None]
        deduped: dict[str, TasteAdjustment] = {}
        for record in parsed:
            deduped[record.key] = record
        return TasteAdjustments(records=tuple(sorted(deduped.values(), key=lambda a: a.key)))


#: The empty set, as a module-level singleton.
#:
#: Used as the default argument wherever an adjustment set is optional. The type
#: is frozen, so sharing one instance is safe; naming it also makes "no
#: adjustments" a thing the signatures say out loud rather than a constructor
#: call in a default (ruff B008).
NO_ADJUSTMENTS: TasteAdjustments = TasteAdjustments()
