"""Retention policy and provable deletion for the derived app-state store.

Reading history can out a reader. Until now this app kept it indefinitely — in
``data/app-state.sqlite``, in every timestamped backup, and in every archive
export — with no way to say "keep two years" or "forget that I ever read this".
A privacy tool that cannot delete is only half a privacy tool.

Two mechanisms live here, and they reduce to the same arithmetic:

* a **horizon** (``[retention] history_days``) applied on every refresh, and
* an explicit **forget** (``stacks forget``), which is a horizon for one book or
  one date, remembered so it stays forgotten.

THE ABSENCE RULE, WHICH IS THE WHOLE POINT. A pruned window is not an empty
window. "You read nothing in 2023", "no reading source is connected", and "2023
is outside your retention horizon" are three different facts that produce the
same zeros, and rendering the third as either of the first two is a lie the
reader has no way to catch. So this module never silently drops data: it records
what it removed, and :attr:`RetentionState.earliest_retained_ordinal` is the
boundary every surface asks about before it prints a number about a window.

WHY A FORGET MUST BE REMEMBERED. The source libraries (Calibre, KOReader, Kobo,
Calibre-Web) are read-only by rule and are explicitly out of scope for deletion —
so the very next ``stacks refresh`` would re-import the history a forget just
removed, and the reader would never be told. That would be worse than not having
the feature. :attr:`RetentionPolicy.forgotten_book_ids` is therefore persisted
and re-applied on the ingest path every time, and the receipt says plainly that
the source library still holds the rows.

Nothing here reads the wall clock; ``now`` is always injected, so a retention
horizon is as testable as any other pure function in this package.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

from ingest.models import DailyActivity, DeviceProgress, ReadingStat, ReadingState

#: Seconds in a UTC day. Day arithmetic is done in whole ordinals so a horizon
#: never lands mid-day differently on two machines in two timezones.
SECONDS_PER_DAY = 86400

#: Retention is OFF unless the reader configures it. The issue that asked for
#: this feature states no default horizon, and a default that silently deletes
#: someone's reading history is a product decision this code has no business
#: making on its own. Zero means "keep everything", which is exactly today's
#: behaviour, so installing this release changes nothing until asked.
DEFAULT_HISTORY_DAYS = 0


def day_ordinal(timestamp: int) -> int:
    """UTC days since the epoch for a unix timestamp."""
    return timestamp // SECONDS_PER_DAY


def ordinal_to_iso(ordinal: int) -> str:
    """Render a day ordinal as an ISO date, for receipts and rendered copy."""
    import datetime

    return (datetime.date(1970, 1, 1) + datetime.timedelta(days=ordinal)).isoformat()


def iso_to_ordinal(value: str) -> int:
    """Parse an ISO ``YYYY-MM-DD`` date into a day ordinal.

    Raises :class:`ValueError` on anything else. Deliberately strict: a
    mistyped date silently coerced to today would delete everything.
    """
    import datetime

    parsed = datetime.date.fromisoformat(value.strip())
    return parsed.toordinal() - datetime.date(1970, 1, 1).toordinal()


@dataclass(frozen=True)
class RetentionPolicy:
    """What the reader has asked this instance to keep, and to forget.

    ``history_days`` is configuration; the two ``forgotten_*`` fields are
    persisted consequences of explicit ``stacks forget`` runs. They are kept
    apart because they answer different questions — "what is my policy" versus
    "what have I already asked to be destroyed" — and only the second must
    survive a config change.
    """

    history_days: int = DEFAULT_HISTORY_DAYS
    forgotten_book_ids: tuple[str, ...] = ()
    forgotten_before_ordinal: Optional[int] = None

    @property
    def horizon_enabled(self) -> bool:
        return self.history_days > 0

    def horizon_cutoff(self, now: int) -> Optional[int]:
        """The earliest day ordinal the horizon retains, or ``None`` when off."""
        if not self.horizon_enabled:
            return None
        return day_ordinal(now) - self.history_days

    def earliest_retained_ordinal(self, now: int) -> Optional[int]:
        """The earliest day any surface may still report on, or ``None``.

        The stricter of the rolling horizon and any explicit ``forget --before``
        wins, because both are the reader saying "do not keep this".
        """
        cutoffs = [
            c for c in (self.horizon_cutoff(now), self.forgotten_before_ordinal) if c is not None
        ]
        return max(cutoffs) if cutoffs else None

    def with_forgotten_book(self, book_id: str) -> RetentionPolicy:
        if not book_id or book_id in self.forgotten_book_ids:
            return self
        return replace(self, forgotten_book_ids=tuple(sorted({*self.forgotten_book_ids, book_id})))

    def with_forgotten_before(self, ordinal: int) -> RetentionPolicy:
        current = self.forgotten_before_ordinal
        return replace(
            self, forgotten_before_ordinal=max(ordinal, current) if current is not None else ordinal
        )


@dataclass(frozen=True)
class PruneCounts:
    """What a prune actually removed. Every field is a count, never a title."""

    activity_days: int = 0
    states_forgotten: int = 0
    states_history_cleared: int = 0
    sessions: int = 0
    highlights: int = 0
    read_time_seconds: int = 0
    progress_entries: int = 0

    @property
    def total(self) -> int:
        return (
            self.activity_days
            + self.states_forgotten
            + self.states_history_cleared
            + self.progress_entries
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "activity_days": self.activity_days,
            "states_forgotten": self.states_forgotten,
            "states_history_cleared": self.states_history_cleared,
            "sessions": self.sessions,
            "highlights": self.highlights,
            "read_time_seconds": self.read_time_seconds,
            "progress_entries": self.progress_entries,
        }


@dataclass(frozen=True)
class PruneResult:
    """The surviving state, plus what it cost to get there."""

    states: list[ReadingState]
    daily_activity: list[DailyActivity]
    counts: PruneCounts
    earliest_retained_ordinal: Optional[int]


def _last_activity_ordinal(state: ReadingState) -> Optional[int]:
    """The most recent day this book shows any reading evidence, if any.

    ``None`` means the book has no reading history at all — an owned,
    never-opened book. Such a book is never pruned: there is nothing to prune,
    and removing it would delete a *catalog* fact under a *history* policy.
    """
    stamps: list[int] = []
    if state.stat is not None and state.stat.last_read_ts > 0:
        stamps.append(state.stat.last_read_ts)
    stamps.extend(p.timestamp for p in state.progress if p.timestamp > 0)
    return day_ordinal(max(stamps)) if stamps else None


def _strip_history(stat: ReadingStat) -> ReadingStat:
    """Drop the *history* fields of a stat, keeping its position facts.

    ``pages_read``/``total_pages`` describe where the reader is in the book —
    a property of the bookmark, not a log of when they read. Sessions, read
    time, highlight counts and the last-read timestamp are the history, and
    they are what a horizon is asked to forget.
    """
    return replace(stat, read_time_seconds=0, last_read_ts=0, sessions=0, highlights=0)


def apply_policy(
    states: list[ReadingState],
    daily_activity: list[DailyActivity],
    policy: RetentionPolicy,
    now: int,
) -> PruneResult:
    """Apply a retention policy to derived state. Pure — no I/O, no clock.

    Order matters and is deliberate: explicit forgets first (the reader asked
    directly), then the rolling horizon (a standing instruction). A book that is
    both forgotten and outside the horizon is counted once, as forgotten.
    """
    cutoff = policy.earliest_retained_ordinal(now)
    forgotten = frozenset(policy.forgotten_book_ids)

    kept_states: list[ReadingState] = []
    counts = {
        "activity_days": 0,
        "states_forgotten": 0,
        "states_history_cleared": 0,
        "sessions": 0,
        "highlights": 0,
        "read_time_seconds": 0,
        "progress_entries": 0,
    }

    for state in states:
        book_id = state.book.book_id if state.book is not None else None
        if book_id is not None and book_id in forgotten:
            # An explicitly forgotten book leaves no reading record at all. The
            # book itself stays on the shelf only if the reader still owns it —
            # which is the catalog's business, re-derived on the next refresh —
            # so the whole state row goes.
            counts["states_forgotten"] += 1
            if state.stat is not None:
                counts["sessions"] += state.stat.sessions
                counts["highlights"] += state.stat.highlights
                counts["read_time_seconds"] += state.stat.read_time_seconds
            counts["progress_entries"] += len(state.progress)
            continue

        if cutoff is None:
            kept_states.append(state)
            continue

        last = _last_activity_ordinal(state)
        surviving_progress: tuple[DeviceProgress, ...] = tuple(
            p for p in state.progress if day_ordinal(p.timestamp) >= cutoff
        )
        dropped_progress = len(state.progress) - len(surviving_progress)

        stat = state.stat
        stat_is_stale = stat is not None and (last is None or last < cutoff)
        if stat_is_stale and stat is not None:
            counts["states_history_cleared"] += 1
            counts["sessions"] += stat.sessions
            counts["highlights"] += stat.highlights
            counts["read_time_seconds"] += stat.read_time_seconds
            stat = _strip_history(stat)

        counts["progress_entries"] += dropped_progress
        if stat is not state.stat or dropped_progress:
            kept_states.append(replace(state, stat=stat, progress=surviving_progress))
        else:
            kept_states.append(state)

    if cutoff is None:
        kept_activity = list(daily_activity)
    else:
        kept_activity = [d for d in daily_activity if d.day_ordinal >= cutoff]
        counts["activity_days"] = len(daily_activity) - len(kept_activity)

    return PruneResult(
        states=kept_states,
        daily_activity=kept_activity,
        counts=PruneCounts(**counts),
        earliest_retained_ordinal=cutoff,
    )


@dataclass(frozen=True)
class RetentionState:
    """The persisted retention picture a rendering surface reads.

    ``earliest_retained_ordinal`` is the single question every surface asks:
    *may I say anything about this day?* ``None`` means no policy is in force
    and the whole record is retained, which is this project's default.
    """

    policy: RetentionPolicy = RetentionPolicy()
    earliest_retained_ordinal: Optional[int] = None
    last_counts: PruneCounts = PruneCounts()
    applied_at: Optional[int] = None

    @property
    def active(self) -> bool:
        """Whether anything at all is being withheld from the record."""
        return self.earliest_retained_ordinal is not None or bool(self.policy.forgotten_book_ids)

    def retains_day(self, ordinal: int) -> bool:
        cutoff = self.earliest_retained_ordinal
        return cutoff is None or ordinal >= cutoff

    def deleted_every_activity_day(self, retained_days: int) -> bool:
        """Whether this policy is why no per-day activity is left to read.

        An empty per-day record has two causes that produce identical zeros:
        no connected source ever wrote one (Kobo and Calibre-Web write none),
        or the reader's own horizon deleted the one that existed. Only the
        second is their configuration working, and telling them the first is
        the failure :data:`app.render.NOT_RETAINED_NOTE` exists to prevent, one
        window further out than :meth:`coverage_of` can see: with every day
        gone there is no year left to ask ``coverage_of`` about.

        Both halves come from records that were really read, never inferred.
        ``last_counts.activity_days`` is what the prune that wrote this state
        actually removed — ``ingest.refresh`` re-applies the policy to the
        freshly ingested record on every run, so it stays a live count rather
        than a first-run relic — and ``retained_days`` is what the store holds
        now. A zero prune count answers ``False`` however active the policy is,
        because nothing was deleted.
        """
        return retained_days == 0 and self.last_counts.activity_days > 0

    def coverage_of(self, lo_ordinal: int, hi_ordinal: int) -> str:
        """How much of the half-open window ``[lo, hi)`` survives the policy.

        Three answers, never two. ``"full"`` is an ordinary measured window;
        ``"none"`` is a window that has been deleted and about which no number
        may be printed; ``"partial"`` is the one that is easy to forget and
        easy to get wrong — a year the horizon cuts through, whose totals are
        real but incomplete, and which must say so rather than pass as whole.
        """
        cutoff = self.earliest_retained_ordinal
        if cutoff is None or lo_ordinal >= cutoff:
            return "full"
        if hi_ordinal <= cutoff:
            return "none"
        return "partial"

    @property
    def earliest_retained_date(self) -> Optional[str]:
        cutoff = self.earliest_retained_ordinal
        return None if cutoff is None else ordinal_to_iso(cutoff)

    def as_dict(self) -> dict[str, object]:
        return {
            "history_days": self.policy.history_days,
            "forgotten_book_ids": list(self.policy.forgotten_book_ids),
            "forgotten_before_ordinal": self.policy.forgotten_before_ordinal,
            "earliest_retained_ordinal": self.earliest_retained_ordinal,
            "last_counts": self.last_counts.as_dict(),
            "applied_at": self.applied_at,
        }

    @staticmethod
    def from_dict(raw: object) -> RetentionState:
        """Rebuild from a persisted document, tolerating an absent/old record.

        A store written before retention existed yields the default (retain
        everything) — the honest reading, since nothing was ever pruned from it.
        """
        if not isinstance(raw, dict):
            return RetentionState()
        forgotten = raw.get("forgotten_book_ids")
        before = raw.get("forgotten_before_ordinal")
        earliest = raw.get("earliest_retained_ordinal")
        counts = raw.get("last_counts")
        applied = raw.get("applied_at")
        policy = RetentionPolicy(
            history_days=int(raw.get("history_days", 0) or 0),
            forgotten_book_ids=tuple(str(b) for b in forgotten if isinstance(b, str))
            if isinstance(forgotten, list)
            else (),
            forgotten_before_ordinal=int(before) if isinstance(before, int) else None,
        )
        return RetentionState(
            policy=policy,
            earliest_retained_ordinal=int(earliest) if isinstance(earliest, int) else None,
            last_counts=PruneCounts(
                **{
                    k: int(v)
                    for k, v in counts.items()
                    if isinstance(v, int) and k in PruneCounts().as_dict()
                }
            )
            if isinstance(counts, dict)
            else PruneCounts(),
            applied_at=int(applied) if isinstance(applied, int) else None,
        )


def store_digest(path: Path) -> str:
    """SHA-256 of the store file, for a forget receipt.

    Computed over the file AFTER deletion, which is the only ordering that
    proves anything: a hash of the pre-delete state would be a receipt for the
    data still being there. Never covers titles — it is a hash of bytes on disk,
    quoted so a reader can check two runs agree, and nothing else.
    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
