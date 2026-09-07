"""``stacks forget`` — deletion that can be checked, including in the backups.

:mod:`ingest.retention` decides *what* a policy removes; this module carries it
out against the live store, against the backups when asked, and writes the
receipt. It is deliberately separate from :mod:`ingest.refresh` because the two
answer different questions: a refresh asks "what does the library say now", a
forget asks "make this stop existing here, and show me that it did".

THREE THINGS A DELETION FEATURE CAN LIE ABOUT, and what is done about each:

1. **The rows are still in a backup.** A timestamped copy under ``data/backups``
   is as sensitive as the store. ``--include-backups`` rewrites each one through
   the same policy and re-reads it to confirm; without the flag, the receipt
   *names how many backups still hold matching history* rather than quietly
   leaving them. Silence there would be the most damaging default available.

2. **The receipt attests to the wrong moment.** The digest is taken over the
   store file AFTER the deletion, so it is evidence of the end state. A hash of
   the pre-delete file would be a receipt for the data still being present.

3. **It comes back.** The source libraries are read-only by rule and out of
   scope for deletion, so the next ``stacks refresh`` re-reads whatever a forget
   removed. The instruction is therefore persisted in the store's retention
   record and re-applied on every ingest — and the receipt says, in words, that
   the source library still holds the rows and where they are.

A receipt carries counts, ids the reader themselves supplied, and file digests.
It never carries a title.
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

from ingest.backup import list_backups
from ingest.models import ReadingState
from ingest.retention import (
    PruneCounts,
    RetentionPolicy,
    RetentionState,
    apply_policy,
    ordinal_to_iso,
    store_digest,
)
from ingest.store import Store


@dataclass(frozen=True)
class BackupOutcome:
    """What happened to one backup file."""

    name: str
    removed: int
    rewritten: bool


@dataclass(frozen=True)
class ForgetReceipt:
    """The record of one forget. Counts and digests only — never a title."""

    book_id: Optional[str]
    before: Optional[str]
    matched: bool
    counts: PruneCounts
    store_sha256: str
    backups: tuple[BackupOutcome, ...]
    source_libraries_still_hold_this: bool

    @property
    def backups_rewritten(self) -> tuple[str, ...]:
        return tuple(b.name for b in self.backups if b.rewritten)

    @property
    def backups_still_holding(self) -> tuple[str, ...]:
        return tuple(b.name for b in self.backups if b.removed > 0 and not b.rewritten)

    def as_dict(self) -> dict[str, object]:
        return {
            "book_id": self.book_id,
            "before": self.before,
            "matched": self.matched,
            "counts": self.counts.as_dict(),
            "store_sha256": self.store_sha256,
            "backups_rewritten": list(self.backups_rewritten),
            "backups_still_holding": list(self.backups_still_holding),
            "source_libraries_still_hold_this": self.source_libraries_still_hold_this,
        }


def _apply_to_store(
    store: Store, policy: RetentionPolicy, now: int, config: object = None
) -> PruneCounts:
    """Run a policy against one open store, persisting the surviving state."""
    result = apply_policy(store.load_states(), store.load_daily_activity(), policy, now)
    if result.counts.total:
        store.save(
            result.states,
            result.daily_activity,
            refreshed_at=store.refreshed_at() or now,
            source_mtimes=store.source_mtimes(),
            origin=store.state_origin() or "real",
        )
    # ORDER IS LOAD-BEARING. Both `save` and `save_retention` advance the view
    # revision, and `build_index` stamps the revision it was built at so a later
    # write makes the index report itself `stale` rather than answer from rows
    # that have moved. Rebuilding before the retention write left a freshly
    # correct index one revision behind and therefore refusing to answer — a
    # forgotten book then stayed "findable" only in the sense that search was
    # broken for everything. The index rebuild goes last, after every write.
    store.save_retention(
        RetentionState(
            policy=policy,
            earliest_retained_ordinal=result.earliest_retained_ordinal,
            last_counts=result.counts,
            applied_at=now,
        )
    )
    if result.counts.total:
        _rebuild_index(store, result.states, now, config)
    return result.counts


def _rebuild_index(
    store: Store, states: list[ReadingState], now: int, config: object = None
) -> None:
    """Rebuild the search index from the surviving states.

    Not optional and not cosmetic: the FTS5 table holds titles, authors and
    sourced tags copied out of the states. Deleting the state row and leaving
    the index alone would leave a forgotten book fully searchable, which is the
    deletion failing in the one surface most likely to be used to look for it.

    ``config`` carries the privacy toggle through, resolved by the SAME helper
    :mod:`ingest.refresh` uses. Rebuilding without it would silently re-index
    the sensitive descriptors a refresh had deliberately excluded — a forget
    that *widened* what the search index holds, which is the opposite of the
    thing being asked for.
    """
    from ingest.search_index import build_index, hidden_descriptors_for

    hide = bool(getattr(config, "hide_sensitive_descriptors", False))
    try:
        build_index(
            store,
            states,
            now=now,
            hide_sensitive=hide,
            hidden_descriptors=hidden_descriptors_for(config),
        )
    except sqlite3.Error:  # an index is an accelerator, never the record
        return


def _process_backup(
    path: Path, policy: RetentionPolicy, now: int, *, rewrite: bool, config: object = None
) -> BackupOutcome:
    """Measure (and optionally perform) the same deletion inside one backup.

    Always works on a temporary copy, so a *measurement* never mutates a backup
    file — the no-flag path must be able to report what a backup holds without
    touching it. The rewrite is a whole-file replace of the finished copy, so a
    crash mid-way leaves the original backup intact rather than a half-deleted
    one that reads as complete.
    """
    with tempfile.TemporaryDirectory(prefix="stacks-forget-") as tmp:
        scratch = Path(tmp) / path.name
        shutil.copy2(path, scratch)
        store = Store(scratch)
        try:
            counts = _apply_to_store(store, policy, now, config)
        finally:
            store.close()
        if rewrite and counts.total:
            shutil.copy2(scratch, path)
        return BackupOutcome(
            name=path.name, removed=counts.total, rewritten=bool(rewrite and counts.total)
        )


def forget(
    store: Store,
    *,
    store_path: Path,
    backups_dir: Path,
    now: int,
    book_id: Optional[str] = None,
    before: Optional[int] = None,
    include_backups: bool = False,
    config: object = None,
) -> ForgetReceipt:
    """Forget one book's history, or everything before a date, or both.

    ``before`` is a day ordinal (parse with :func:`ingest.retention.iso_to_ordinal`
    so a malformed date is refused at the edge rather than coerced here).

    An id that matches nothing is a no-op returning an empty receipt, and is
    deliberately NOT remembered: recording an unmatched id would arm a silent
    trap for a future book that happened to be given it, and "nothing matched"
    is the honest answer to give someone who mistyped.
    """
    stored = store.retention()
    candidate = stored.policy
    if book_id:
        candidate = candidate.with_forgotten_book(book_id)
    if before is not None:
        candidate = candidate.with_forgotten_before(before)

    # Measure against the live state before committing the policy, so an id that
    # matches nothing can be reported as a no-op rather than remembered forever.
    probe = apply_policy(store.load_states(), store.load_daily_activity(), candidate, now)
    matched = probe.counts.total > 0

    policy = candidate if matched else replace(stored.policy)
    counts = _apply_to_store(store, policy, now, config) if matched else PruneCounts()

    outcomes: tuple[BackupOutcome, ...] = ()
    if matched:
        outcomes = tuple(
            _process_backup(path, policy, now, rewrite=include_backups, config=config)
            for path in list_backups(backups_dir)
        )

    return ForgetReceipt(
        book_id=book_id,
        before=ordinal_to_iso(before) if before is not None else None,
        matched=matched,
        counts=counts,
        store_sha256=store_digest(store_path) if Path(store_path).is_file() else "",
        backups=outcomes,
        # Stated unconditionally rather than only when it bites. A reader who
        # deletes their history here and is not told that Calibre/KOReader still
        # hold it has been given a false sense of what they just achieved.
        source_libraries_still_hold_this=matched,
    )
