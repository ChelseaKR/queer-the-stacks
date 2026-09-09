"""Retention and provable deletion (#111).

Three things these tests exist to stop, in descending order of how much damage
each would do:

1. **A deletion that did not delete.** A row left in the store, in the search
   index, or in a timestamped backup is the feature failing at the only thing it
   claims. So the backup assertions restore-then-query rather than trusting a
   return value, and the index is queried by name.
2. **A deletion rendered as a reading of zero.** "You read nothing in 2023" and
   "2023 is outside the history you keep" produce identical numbers, and this
   repository has already shipped that defect once (the 1970 Wrapped). Every
   absence assertion here has a positive control beside it, because a change
   that suppressed *everything* would satisfy a suite that only checked for
   absence.
3. **A forget that silently comes back.** The source libraries are read-only and
   out of scope for deletion, so an instruction that is not remembered is undone
   by the next refresh with nothing said.

Expected values are pinned to literals, never recomputed from the constant under
test: a test that reads ``DEFAULT_HISTORY_DAYS`` on both sides of its own
assertion passes for every possible value of it.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from app.render import (
    ACTIVITY_NOT_RETAINED_NOTE,
    ALL_YEARS_NOT_RETAINED_NOTE,
    NO_DAILY_ACTIVITY_NOTE,
    NO_WRAPPED_YEAR_NOTE,
    NOT_RETAINED_NOTE,
    READING_SOURCE_ACTIVITY_NOT_RETAINED,
    READING_SOURCE_PER_BOOK_ONLY,
)
from app.stats import compute_stats
from app.view import _infer_today_and_year, build_view, render_view
from app.wrapped import (
    NOT_RETAINED_LABEL,
    UNMEASURED_YEAR_LABEL,
    Wrapped,
    compute_wrapped,
    year_bounds,
)
from ingest.backup import backup_store, list_backups, restore_store
from ingest.forget import forget
from ingest.models import (
    Author,
    Book,
    DailyActivity,
    DeviceProgress,
    ReadingStat,
    ReadingState,
    ReadingStatus,
    Source,
    SourceKind,
    ThemeTag,
)
from ingest.retention import (
    SECONDS_PER_DAY,
    PruneCounts,
    RetentionPolicy,
    RetentionState,
    apply_policy,
    day_ordinal,
    iso_to_ordinal,
    ordinal_to_iso,
    store_digest,
)
from ingest.store import Store

# --- fixtures ---------------------------------------------------------------

#: 2026-01-01. Every timestamp below is derived from this, so a horizon in these
#: tests is arithmetic a reader can check, not a wall clock.
NOW = 20454 * SECONDS_PER_DAY


def _book(book_id: str, title: str) -> Book:
    src = Source(SourceKind.CALIBRE_TAG, "calibre:local", "2026-01-01", "queer fiction")
    return Book(
        book_id=book_id,
        title=title,
        authors=(Author(name="A Writer"),),
        theme_tags=(ThemeTag(label="queer", source=src),),
    )


def _state(
    book_id: str,
    title: str,
    *,
    last_read_day: int,
    sessions: int = 4,
    highlights: int = 7,
    progress_day: int | None = None,
) -> ReadingState:
    progress = ()
    if progress_day is not None:
        progress = (
            DeviceProgress(
                document=f"doc-{book_id}",
                percentage=0.5,
                device="kobo",
                timestamp=progress_day * SECONDS_PER_DAY,
            ),
        )
    return ReadingState(
        title=title,
        authors=("A Writer",),
        status=ReadingStatus.FINISHED,
        book=_book(book_id, title),
        stat=ReadingStat(
            key=book_id,
            title=title,
            authors=("A Writer",),
            pages_read=300,
            total_pages=300,
            read_time_seconds=7200,
            last_read_ts=last_read_day * SECONDS_PER_DAY,
            sessions=sessions,
            highlights=highlights,
        ),
        progress=progress,
    )


def _three_years() -> tuple[list[ReadingState], list[DailyActivity]]:
    """Three calendar years of reading: 2023, 2024, 2025."""
    states = [
        _state("b-2023", "Old Book", last_read_day=year_bounds(2023)[0] + 10),
        _state("b-2024", "Middle Book", last_read_day=year_bounds(2024)[0] + 10),
        _state("b-2025", "Recent Book", last_read_day=year_bounds(2025)[0] + 10),
    ]
    activity = []
    for year in (2023, 2024, 2025):
        lo, _ = year_bounds(year)
        for offset in range(0, 30):
            activity.append(DailyActivity(day_ordinal=lo + offset, seconds=1800, pages=40))
    return states, activity


# --- the horizon ------------------------------------------------------------


def test_a_365_day_horizon_over_three_years_retains_one():
    """#111's first acceptance criterion, with the counts pinned to literals."""
    states, activity = _three_years()
    # 90 activity days exist across three years; 2025's 30 are inside a 365-day
    # horizon taken from 2026-01-01, and the earlier 60 are not.
    assert len(activity) == 90

    result = apply_policy(states, activity, RetentionPolicy(history_days=365), NOW)

    assert len(result.daily_activity) == 30
    assert result.counts.activity_days == 60
    assert {ordinal_to_iso(d.day_ordinal)[:4] for d in result.daily_activity} == {"2025"}
    # Two of the three books had their history cleared; none were removed.
    assert result.counts.states_history_cleared == 2
    assert result.counts.states_forgotten == 0
    assert len(result.states) == 3


def test_the_horizon_clears_history_but_keeps_the_book_on_the_shelf():
    states, activity = _three_years()
    result = apply_policy(states, activity, RetentionPolicy(history_days=365), NOW)
    by_id = {s.book.book_id: s for s in result.states if s.book}

    old = by_id["b-2023"]
    assert old.stat is not None, "the book itself is a catalog fact, not history"
    assert old.status is ReadingStatus.FINISHED, "that you finished it is not a session log"
    assert old.stat.sessions == 0
    assert old.stat.highlights == 0
    assert old.stat.read_time_seconds == 0
    assert old.stat.last_read_ts == 0
    # Position survives: it describes the bookmark, not when you read.
    assert old.stat.pages_read == 300

    recent = by_id["b-2025"]
    assert recent.stat is not None
    assert recent.stat.sessions == 4, "positive control: inside the horizon, untouched"
    assert recent.stat.highlights == 7


def test_no_horizon_is_the_default_and_removes_nothing():
    states, activity = _three_years()
    result = apply_policy(states, activity, RetentionPolicy(), NOW)
    assert result.counts == PruneCounts()
    assert result.earliest_retained_ordinal is None
    assert len(result.daily_activity) == 90
    assert len(result.states) == 3


def test_a_never_opened_book_is_never_pruned_by_a_horizon():
    """A book with no reading history has none to delete — and is not history."""
    owned = ReadingState(
        title="Owned, Unread",
        authors=("A Writer",),
        status=ReadingStatus.UNREAD,
        book=_book("b-owned", "Owned, Unread"),
    )
    result = apply_policy([owned], [], RetentionPolicy(history_days=365), NOW)
    assert len(result.states) == 1
    assert result.counts.states_history_cleared == 0


def test_device_progress_older_than_the_horizon_is_dropped():
    old_progress = _state(
        "b-old-progress",
        "Old Progress",
        last_read_day=year_bounds(2025)[0] + 10,
        progress_day=year_bounds(2023)[0] + 5,
    )
    result = apply_policy([old_progress], [], RetentionPolicy(history_days=365), NOW)
    assert result.counts.progress_entries == 1
    assert result.states[0].progress == ()


def test_a_negative_or_absent_horizon_never_deletes_everything():
    """The destructive reading of a bad value is the one that must not happen."""
    states, activity = _three_years()
    for policy in (RetentionPolicy(history_days=0), RetentionPolicy(history_days=-5)):
        result = apply_policy(states, activity, policy, NOW)
        assert result.counts.total == 0
        assert len(result.daily_activity) == 90


# --- the absence rule -------------------------------------------------------


def test_a_deleted_year_is_not_retained_and_never_not_measured():
    """#111's Wrapped criterion: two pruned years, each named as deleted."""
    _, activity = _three_years()
    retention = RetentionState(
        policy=RetentionPolicy(history_days=365),
        earliest_retained_ordinal=year_bounds(2025)[0],
    )
    for year in (2023, 2024):
        wrapped = compute_wrapped([], activity, year, retention=retention)
        assert wrapped.retention_coverage == "none"
        assert wrapped.absence_label == NOT_RETAINED_LABEL
        assert wrapped.absence_label != UNMEASURED_YEAR_LABEL
        assert not wrapped.reportable
        # The year is still named. A deleted year the reader can see named is
        # legible; a blank is just a gap.
        assert wrapped.year_label == str(year)

    # Positive control: the retained year still reports real figures.
    kept = compute_wrapped([], activity, 2025, retention=retention)
    assert kept.reportable
    assert kept.pages_read == 1200
    assert kept.retention_coverage == "full"


def test_an_unmeasured_year_and_a_deleted_year_do_not_render_alike():
    unmeasured = Wrapped.unmeasured()
    deleted = Wrapped.not_retained(2023)
    assert unmeasured.absence_label == UNMEASURED_YEAR_LABEL
    assert deleted.absence_label == NOT_RETAINED_LABEL
    assert not unmeasured.reportable and not deleted.reportable
    assert unmeasured.year_label == UNMEASURED_YEAR_LABEL
    assert deleted.year_label == "2023"


def test_a_year_the_horizon_cuts_through_says_its_figures_are_partial():
    """Pruning happens on the ingest path; Wrapped labels what it is given.

    So this runs the policy first, exactly as `ingest.refresh` does, and then
    computes — otherwise the test would assert against unpruned rows that the
    store would never actually hold.
    """
    states, activity = _three_years()
    cutoff = year_bounds(2025)[0] + 15
    pruned = apply_policy(
        states,
        activity,
        RetentionPolicy(forgotten_before_ordinal=cutoff),
        NOW,
    )
    retention = RetentionState(
        policy=RetentionPolicy(forgotten_before_ordinal=cutoff),
        earliest_retained_ordinal=cutoff,
    )
    wrapped = compute_wrapped(pruned.states, pruned.daily_activity, 2025, retention=retention)
    assert wrapped.retention_coverage == "partial"
    assert wrapped.partially_retained
    assert wrapped.reportable, "a partial year is still a measurement, just not a whole one"
    assert wrapped.pages_read == 600, "15 of 30 days survive, at 40 pages each"


def test_the_dashboard_says_not_retained_and_not_a_zero():
    _, activity = _three_years()
    retention = RetentionState(
        policy=RetentionPolicy(history_days=365),
        earliest_retained_ordinal=year_bounds(2026)[0],
    )
    states, _ = _three_years()
    html = render_view(build_view(states, activity, (), retention=retention))
    assert NOT_RETAINED_NOTE in html
    assert NOT_RETAINED_LABEL in html
    # The wording for "no source connected" must not appear for a deletion.
    assert "No reading-data source is connected" not in html

    # Positive control: with no policy the same data renders real figures and
    # none of the retention wording.
    plain = render_view(build_view(states, activity, ()))
    assert NOT_RETAINED_NOTE not in plain
    assert NOT_RETAINED_LABEL not in plain


# --- forget -----------------------------------------------------------------


def _populated_store(tmp_path: Path) -> tuple[Store, Path]:
    store_path = tmp_path / "app-state.sqlite"
    store = Store(store_path)
    states, activity = _three_years()
    store.save(states, activity, refreshed_at=NOW, source_mtimes={"calibre": 1}, origin="real")
    return store, store_path


def test_forget_a_book_removes_its_history_and_leaves_the_others(tmp_path: Path):
    store, store_path = _populated_store(tmp_path)
    try:
        receipt = forget(
            store,
            store_path=store_path,
            backups_dir=tmp_path / "backups",
            now=NOW,
            book_id="b-2024",
        )
        assert receipt.matched
        assert receipt.counts.states_forgotten == 1
        surviving = {s.book.book_id for s in store.load_states() if s.book}
        assert surviving == {"b-2023", "b-2025"}
    finally:
        store.close()


def test_forgetting_an_unknown_id_is_a_no_op_with_an_empty_receipt(tmp_path: Path):
    store, store_path = _populated_store(tmp_path)
    try:
        before_states = len(store.load_states())
        receipt = forget(
            store,
            store_path=store_path,
            backups_dir=tmp_path / "backups",
            now=NOW,
            book_id="b-does-not-exist",
        )
        assert not receipt.matched
        assert receipt.counts == PruneCounts()
        assert receipt.backups == ()
        assert len(store.load_states()) == before_states
        # And it is NOT remembered: an unmatched id must not arm a trap for a
        # future book that happens to be given it.
        assert store.retention().policy.forgotten_book_ids == ()
    finally:
        store.close()


def test_the_receipt_hash_is_of_the_state_after_the_deletion(tmp_path: Path):
    store, store_path = _populated_store(tmp_path)
    try:
        receipt = forget(
            store,
            store_path=store_path,
            backups_dir=tmp_path / "backups",
            now=NOW,
            book_id="b-2024",
        )
    finally:
        store.close()
    # Recomputed independently, after the connection closed: the receipt must
    # describe the file as it now is, not as it was before the delete.
    assert receipt.store_sha256 == store_digest(store_path)
    assert len(receipt.store_sha256) == 64


def test_a_receipt_carries_no_title(tmp_path: Path):
    store, store_path = _populated_store(tmp_path)
    try:
        receipt = forget(
            store,
            store_path=store_path,
            backups_dir=tmp_path / "backups",
            now=NOW,
            book_id="b-2024",
        )
    finally:
        store.close()
    blob = repr(receipt.as_dict())
    for title in ("Old Book", "Middle Book", "Recent Book", "A Writer"):
        assert title not in blob


def test_forget_is_remembered_so_a_refresh_cannot_resurrect_it(tmp_path: Path):
    """The source library still holds the rows; the instruction must outlive the run."""
    store, store_path = _populated_store(tmp_path)
    try:
        forget(
            store,
            store_path=store_path,
            backups_dir=tmp_path / "backups",
            now=NOW,
            book_id="b-2024",
        )
        assert store.retention().policy.forgotten_book_ids == ("b-2024",)

        # Simulate the next ingest re-reading everything from the source library.
        reingested, activity = _three_years()
        result = apply_policy(reingested, activity, store.retention().policy, NOW)
        assert {s.book.book_id for s in result.states if s.book} == {"b-2023", "b-2025"}
    finally:
        store.close()


def test_forget_before_a_date_removes_the_earlier_history(tmp_path: Path):
    store, store_path = _populated_store(tmp_path)
    try:
        receipt = forget(
            store,
            store_path=store_path,
            backups_dir=tmp_path / "backups",
            now=NOW,
            before=iso_to_ordinal("2025-01-01"),
        )
        assert receipt.matched
        assert receipt.before == "2025-01-01"
        remaining = store.load_daily_activity()
        assert len(remaining) == 30
        assert all(d.day_ordinal >= iso_to_ordinal("2025-01-01") for d in remaining)
    finally:
        store.close()


def test_a_lowered_horizon_cannot_resurrect_an_explicit_forget(tmp_path: Path):
    store, store_path = _populated_store(tmp_path)
    try:
        forget(
            store,
            store_path=store_path,
            backups_dir=tmp_path / "backups",
            now=NOW,
            before=iso_to_ordinal("2025-01-01"),
        )
        policy = store.retention().policy
        # The reader turns the rolling horizon off entirely.
        relaxed = RetentionPolicy(
            history_days=0,
            forgotten_book_ids=policy.forgotten_book_ids,
            forgotten_before_ordinal=policy.forgotten_before_ordinal,
        )
        states, activity = _three_years()
        result = apply_policy(states, activity, relaxed, NOW)
        assert len(result.daily_activity) == 30, "the explicit forget still holds"
    finally:
        store.close()


# --- backups ----------------------------------------------------------------


def test_without_the_flag_a_backup_still_holding_history_is_named(tmp_path: Path):
    store, store_path = _populated_store(tmp_path)
    backups = tmp_path / "backups"
    try:
        backup_store(store_path, backups, "20260101T000000")
        receipt = forget(
            store,
            store_path=store_path,
            backups_dir=backups,
            now=NOW,
            book_id="b-2024",
        )
    finally:
        store.close()
    assert receipt.backups_still_holding == ("app-state.20260101T000000.sqlite",)
    assert receipt.backups_rewritten == ()


def test_include_backups_leaves_no_row_in_the_store_or_any_backup(tmp_path: Path):
    """#111's second criterion, checked by restoring the backup and querying it."""
    store, store_path = _populated_store(tmp_path)
    backups = tmp_path / "backups"
    try:
        backup_store(store_path, backups, "20260101T000000")
        backup_store(store_path, backups, "20260102T000000")
        receipt = forget(
            store,
            store_path=store_path,
            backups_dir=backups,
            now=NOW,
            book_id="b-2024",
            include_backups=True,
        )
    finally:
        store.close()

    assert len(receipt.backups_rewritten) == 2
    assert receipt.backups_still_holding == ()

    # Restore each backup over a fresh path and query it: the only proof that
    # matters is that the row is not there when you go looking for it.
    for path in list_backups(backups):
        restored_path = tmp_path / f"restored-{path.name}"
        restore_store(path, restored_path)
        restored = Store(restored_path)
        try:
            ids = {s.book.book_id for s in restored.load_states() if s.book}
            assert "b-2024" not in ids, f"{path.name} still holds the forgotten book"
            assert ids == {"b-2023", "b-2025"}, "positive control: the rest survived"
        finally:
            restored.close()


def test_measuring_a_backup_without_the_flag_does_not_modify_it(tmp_path: Path):
    store, store_path = _populated_store(tmp_path)
    backups = tmp_path / "backups"
    try:
        backup = backup_store(store_path, backups, "20260101T000000")
        before = store_digest(backup)
        forget(
            store,
            store_path=store_path,
            backups_dir=backups,
            now=NOW,
            book_id="b-2024",
        )
    finally:
        store.close()
    assert store_digest(backup) == before, "a measurement must not touch a backup"


# --- the index, and the wrong-source guard ----------------------------------


def test_a_forgotten_book_is_gone_from_the_search_index(tmp_path: Path):
    from ingest.search_index import build_index, search

    store, store_path = _populated_store(tmp_path)
    try:
        build_index(store, store.load_states(), now=NOW)
        found = search(store, "Middle")
        if found.status != "ok":  # pragma: no cover - SQLite build without FTS5
            pytest.skip(f"search unavailable here: {found.status}")
        assert found.total == 1, "positive control: it is findable before the forget"

        forget(
            store,
            store_path=store_path,
            backups_dir=tmp_path / "backups",
            now=NOW,
            book_id="b-2024",
        )
        after = search(store, "Middle")
        assert after.total == 0, "a forgotten book must not stay searchable by name"
        assert search(store, "Recent").total == 1, "positive control: others still index"
    finally:
        store.close()


def test_the_prune_reads_the_states_it_was_given_not_an_ambient_source():
    """Swap the input for an empty one and the answer must collapse.

    This repository's recurring defect is output that looks plausible without
    having consulted its real input. A prune that reported counts from anywhere
    but the list handed to it would pass every assertion above.
    """
    states, activity = _three_years()
    real = apply_policy(states, activity, RetentionPolicy(history_days=365), NOW)
    assert real.counts.total > 0

    empty = apply_policy([], [], RetentionPolicy(history_days=365), NOW)
    assert empty.counts == PruneCounts()
    assert empty.states == [] and empty.daily_activity == []

    # ...and a *different* library must not produce the same counts.
    other = apply_policy(
        [_state("b-x", "Something Else", last_read_day=year_bounds(2025)[0] + 1)],
        [],
        RetentionPolicy(history_days=365),
        NOW,
    )
    assert other.counts != real.counts


# --- archive export ---------------------------------------------------------


def test_the_archive_export_carries_only_retained_history(tmp_path: Path):
    from ingest.archive import build_archive

    store, store_path = _populated_store(tmp_path)
    try:
        forget(
            store,
            store_path=store_path,
            backups_dir=tmp_path / "backups",
            now=NOW,
            book_id="b-2024",
        )
        bundle = build_archive(store.load_states(), store.load_daily_activity(), generated_at=NOW)
    finally:
        store.close()
    blob = repr(bundle)
    assert "Middle Book" not in blob, "an export must not re-publish what was forgotten"
    assert "Recent Book" in blob, "positive control: retained history still exports"


# --- round-tripping the policy ----------------------------------------------


def test_retention_state_survives_the_store_round_trip(tmp_path: Path):
    store = Store(tmp_path / "s.sqlite")
    try:
        state = RetentionState(
            policy=RetentionPolicy(
                history_days=365,
                forgotten_book_ids=("b-1", "b-2"),
                forgotten_before_ordinal=19000,
            ),
            earliest_retained_ordinal=20089,
            last_counts=PruneCounts(activity_days=60, states_history_cleared=2),
            applied_at=NOW,
        )
        store.save_retention(state)
        assert store.retention() == state
    finally:
        store.close()


def test_a_store_written_before_retention_existed_retains_everything(tmp_path: Path):
    store = Store(tmp_path / "s.sqlite")
    try:
        assert store.retention() == RetentionState()
        assert store.retention().earliest_retained_ordinal is None
        assert not store.retention().active
    finally:
        store.close()


def test_day_ordinal_and_iso_round_trip():
    assert ordinal_to_iso(iso_to_ordinal("2026-01-01")) == "2026-01-01"
    assert day_ordinal(20454 * SECONDS_PER_DAY) == 20454
    with pytest.raises(ValueError):
        iso_to_ordinal("01/01/2026")


# --- the deletion that took the year with it (#127) -------------------------


def test_a_horizon_that_deleted_every_day_leaves_no_year_and_says_why():
    """`compute_wrapped` asked the year before it asked the policy that deleted it.

    `test_the_dashboard_says_not_retained_and_not_a_zero` above feeds
    **unpruned** activity beside a policy that deletes all of it — a store
    state `ingest.refresh` can never produce — so a year is still inferable
    there and the `year=2025` branch runs. Pruning first, exactly as
    `ingest.refresh` does, is what reaches `year is None`, and that return used
    to hand back `Wrapped.unmeasured()`: `retention_coverage="full"`,
    `retained` True, and no surface able to reach the deletion wording.
    """
    states, activity = _three_years()
    policy = RetentionPolicy(history_days=1)
    pruned = apply_policy(states, activity, policy, NOW)
    assert pruned.daily_activity == [], "the horizon really did take every per-day row"
    assert pruned.counts.activity_days == 90
    retention = RetentionState(
        policy=policy,
        earliest_retained_ordinal=pruned.earliest_retained_ordinal,
        last_counts=pruned.counts,
        applied_at=NOW,
    )

    today, year = _infer_today_and_year(pruned.states, pruned.daily_activity)
    assert (today, year) == (0, None)

    wrapped = compute_wrapped(pruned.states, pruned.daily_activity, year, retention=retention)
    assert wrapped.year is None
    assert wrapped.retained is False
    assert wrapped.reportable is False
    assert wrapped.absence_label == NOT_RETAINED_LABEL
    assert wrapped.year_label == NOT_RETAINED_LABEL, (
        "the year is unknowable, but the reason it is missing is known exactly"
    )

    # Positive control: with no policy in force the same rows are an ordinary
    # unmeasured year, so this state is reached by a deletion and not by any
    # empty activity list.
    assert compute_wrapped(pruned.states, pruned.daily_activity, year) == Wrapped.unmeasured()


def test_a_policy_that_deleted_nothing_is_not_read_as_a_deletion():
    """The flag rests on a prune that really removed rows, not on an active policy.

    A reader with a horizon set and no per-day source has nothing deleted, and
    telling them their setting removed a record they never had is the same
    class of false sentence pointed the other way.
    """
    states, _ = _three_years()
    retention = RetentionState(
        policy=RetentionPolicy(history_days=365),
        earliest_retained_ordinal=year_bounds(2026)[0],
        last_counts=PruneCounts(activity_days=0, states_history_cleared=2),
        applied_at=NOW,
    )
    assert retention.active
    assert retention.deleted_every_activity_day(0) is False
    assert compute_wrapped(states, [], None, retention=retention) == Wrapped.unmeasured()
    assert compute_stats(states, [], 0, retention=retention).activity_deleted is False
    # And the positive half: one deleted day with none retained is the state.
    deleted = replace(retention, last_counts=PruneCounts(activity_days=1))
    assert deleted.deleted_every_activity_day(0) is True
    assert deleted.deleted_every_activity_day(1) is False, (
        "days still in the store mean the year is partial, not gone"
    )


def test_the_page_blames_the_horizon_and_not_a_source_it_has():
    """Both false sentences #127 names, asserted on the rendered page."""
    states, activity = _three_years()
    policy = RetentionPolicy(history_days=1)
    pruned = apply_policy(states, activity, policy, NOW)
    retention = RetentionState(
        policy=policy,
        earliest_retained_ordinal=pruned.earliest_retained_ordinal,
        last_counts=pruned.counts,
        applied_at=NOW,
    )
    html = render_view(build_view(pruned.states, pruned.daily_activity, (), retention=retention))
    assert ALL_YEARS_NOT_RETAINED_NOTE in html
    assert ACTIVITY_NOT_RETAINED_NOTE in html
    assert READING_SOURCE_ACTIVITY_NOT_RETAINED in html
    assert NOT_RETAINED_LABEL in html
    # The three sentences that were published instead, each a statement about
    # sources this reader has.
    assert NO_WRAPPED_YEAR_NOTE not in html
    assert NO_DAILY_ACTIVITY_NOTE not in html
    assert READING_SOURCE_PER_BOOK_ONLY not in html

    # Positive control: the same pruned rows with no policy recorded are an
    # ordinary per-book-only library, and get the per-book-only wording back.
    plain = render_view(build_view(pruned.states, pruned.daily_activity, ()))
    assert NO_DAILY_ACTIVITY_NOTE in plain
    assert READING_SOURCE_PER_BOOK_ONLY in plain
    assert ALL_YEARS_NOT_RETAINED_NOTE not in plain
    assert ACTIVITY_NOT_RETAINED_NOTE not in plain
