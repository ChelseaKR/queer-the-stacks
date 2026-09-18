"""Absence renders as absence — never as a zero, a 0%, or the year 1970.

A Calibre-only install has no KOReader ``statistics.sqlite``: every book reads
as ``UNREAD``, ``daily_activity`` is empty, and every derived total is zero.
That is "no reading-data source is connected", not "this reader has read
nothing", and the two used to render identically.

The worst of it was a year. ``_infer_today_and_year`` had no sentinel, so it
answered **1970** — the epoch escaping through ordinal arithmetic — and that
reached "Reading Wrapped 1970", "Standout reads of 1970", "Books in 1970:
0 / 52 — 0%", and a ``/share`` card composing "My 1970 in books · 0 books ·
0 pages · 0.0 hours across 0 reading days" for public posting.

These tests are written against the shape of the maintainer's real library —
owned books, no reading source — and every one of them has a positive control
beside it, because a fix that suppressed *everything* would pass a suite that
only checked for absence.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from app import opds
from app.goals import compute_goals
from app.render import (
    NO_DAILY_ACTIVITY_NOTE,
    NO_READING_SOURCE_NOTE,
    NOT_MEASURED,
    READING_SOURCE_CONNECTED,
    READING_SOURCE_MISSING,
    READING_SOURCE_PER_BOOK_ONLY,
)
from app.share import build_share_cards, render_share_page, year_in_books_card
from app.stats import compute_stats
from app.view import _infer_today_and_year, build_view, demo_view, render_view
from app.wrapped import UNMEASURED_YEAR_LABEL, Wrapped, compute_wrapped
from ingest.models import (
    Author,
    Book,
    DailyActivity,
    ReadingStat,
    ReadingState,
    ReadingStatus,
    Source,
    SourceKind,
    ThemeTag,
)

# --- the library shape this whole issue is about ----------------------------


def _owned_only(count: int = 3) -> list[ReadingState]:
    """Owned books with no reading record at all — a Calibre-only library.

    No ``stat``, no ``progress``, status ``UNREAD``. Titles are invented for the
    test; nothing here comes from a real library.
    """
    src = Source(SourceKind.OPENLIBRARY_SUBJECT, "https://openlibrary.org/subjects/x", "x", "t")
    return [
        ReadingState(
            title=f"Book {i}",
            authors=(f"Author {i}",),
            status=ReadingStatus.UNREAD,
            book=Book(
                book_id=f"b{i}",
                title=f"Book {i}",
                authors=(Author(f"Author {i}"),),
                theme_tags=(ThemeTag("speculative", src),),
            ),
        )
        for i in range(count)
    ]


def _read_something() -> tuple[list[ReadingState], list[DailyActivity]]:
    """The positive control: one finished book and a day of activity."""
    src = Source(SourceKind.OPENLIBRARY_SUBJECT, "https://openlibrary.org/subjects/x", "x", "t")
    # 2024-05-29 as a day ordinal; `last_read_ts` sits inside the same year.
    day = 19_872
    stat = ReadingStat("b0", "Book 0", ("Author 0",), 300, 300, 36_000, day * 86_400, 4)
    state = ReadingState(
        title="Book 0",
        authors=("Author 0",),
        status=ReadingStatus.FINISHED,
        book=Book(
            book_id="b0",
            title="Book 0",
            authors=(Author("Author 0"),),
            theme_tags=(ThemeTag("speculative", src),),
        ),
        stat=stat,
    )
    return [state, *_owned_only(2)], [DailyActivity(day, 120, 3_600)]


# --- 1. the root cause: no activity means no year, not the epoch ------------


def test_no_activity_infers_no_year() -> None:
    assert _infer_today_and_year(_owned_only(), []) == (0, None)


def test_activity_still_infers_its_year() -> None:
    states, activity = _read_something()
    today, year = _infer_today_and_year(states, activity)
    assert today == 19_872
    assert year == 2024


def test_compute_wrapped_without_a_year_is_unmeasured() -> None:
    wrapped = compute_wrapped(_owned_only(), [], None)
    assert wrapped == Wrapped.unmeasured()
    assert wrapped.year is None
    assert wrapped.measured is False
    assert wrapped.year_label == UNMEASURED_YEAR_LABEL


def test_a_measured_wrapped_keeps_its_year() -> None:
    states, activity = _read_something()
    wrapped = compute_wrapped(states, activity, 2024)
    assert wrapped.measured
    assert wrapped.year == 2024
    assert wrapped.year_label == "2024"


# --- 2. stats say "not measured" rather than eight confident zeros ----------


def test_stats_from_no_reading_source_are_not_measured() -> None:
    stats = compute_stats(_owned_only(), [], 0)
    assert stats.measured is False
    # The zeros are still there — they are just no longer presented as findings.
    assert stats.books_finished == 0


def test_stats_are_measured_from_a_single_per_book_stat() -> None:
    """One stat and no per-day rows is still a measurement, just a thin one.

    ...of *pages and time*. It is not a measurement of a streak, which is what
    `activity_measured` separates out — see the partial-source tests below.
    """
    states, _ = _read_something()
    stats = compute_stats(states, [], 0)
    assert stats.measured
    assert stats.activity_measured is False


def test_stats_table_prints_no_imputed_zero() -> None:
    html = render_view(build_view(_owned_only(), [], ()))
    assert NO_READING_SOURCE_NOTE in html
    assert html.count(NOT_MEASURED) >= 8  # one per stats row
    assert "Books finished</th><td>0</td>" not in html


# --- 2b. the partial-source residual: per-book stats are not a streak -------
#
# `measured` is one OR over eight metrics from three kinds of source. Three of
# them — both streaks and the active-day count — are computed *only* from
# `daily_activity`, and `ingest.refresh` builds that from KOReader alone. So a
# reader on Kobo or Calibre-Web (both documented, supported sources) got three
# metrics no configured source can produce, rendered as confident zeros beside
# two real ones, and a streak goal reported 0% complete against a target
# nothing had checked. Issue #78 fixed the no-source-at-all case; this is the
# partial-source residual it left.


def _kobo_only() -> list[ReadingState]:
    """One real per-book stat and no per-day rows — the Kobo-only shape.

    Kobo supplies per-book totals and no per-session log (`ingest/kobo.py` sets
    ``sessions=0`` for exactly this reason), so `daily_activity` is empty while
    pages and time are genuinely measured.
    """
    states, _ = _read_something()
    return states


def test_streak_metrics_are_not_measured_without_per_day_rows() -> None:
    stats = compute_stats(_kobo_only(), [], today_ordinal=19_872)
    # The pages and time really were measured...
    assert stats.measured
    assert stats.pages_read == 300
    # ...and no quantity of per-book stats is evidence of a streak.
    assert stats.activity_measured is False


def test_a_kobo_only_reader_is_not_shown_a_streak_of_zero() -> None:
    """The rendered failure: "Longest streak (days) 0 / 30 — 0%"."""
    html = render_view(build_view(_kobo_only(), [], (), goal_streak_days=30))
    for label in ("Current streak (days)", "Longest streak (days)", "Active reading days"):
        assert f'<tr><th scope="row">{label}</th><td>{NOT_MEASURED}</td></tr>' in html
    # The goal says "unknown", not "you are 0% of the way to a 30-day streak".
    assert f"<td>{NOT_MEASURED} / 30</td>" in html
    assert "<td>0 / 30</td>" not in html
    assert "<td>0%</td>" not in html
    # Positive control: the metrics that *were* measured still show their values.
    assert '<tr><th scope="row">Pages read</th><td>300</td></tr>' in html
    assert '<tr><th scope="row">Books finished</th><td>1</td></tr>' in html


def test_a_partial_source_page_does_not_contradict_its_own_numbers() -> None:
    """The page must not deny the source whose figures it is printing.

    Keyed off the single OR'd flag, this reader was told "No reading-data source
    is connected … Connect KOReader to measure reading" on the same page as
    "Pages read 300", and the data-status row asserted "KOReader statistics"
    were present for a reader with no KOReader at all.
    """
    html = render_view(build_view(_kobo_only(), [], (), goal_streak_days=30))
    assert NO_READING_SOURCE_NOTE not in html
    assert READING_SOURCE_CONNECTED not in html
    assert READING_SOURCE_MISSING not in html
    # What it says instead is specific and true: the per-day log is what is absent.
    assert NO_DAILY_ACTIVITY_NOTE in html
    assert READING_SOURCE_PER_BOOK_ONLY in html


def test_a_full_koreader_reader_keeps_every_measured_streak() -> None:
    """The control that stops "render fewer numbers" from passing this suite."""
    states, activity = _read_something()
    stats = compute_stats(states, activity, today_ordinal=19_872)
    assert stats.activity_measured
    assert stats.longest_streak_days == 1
    html = render_view(build_view(states, activity, (), goal_streak_days=30))
    assert '<tr><th scope="row">Longest streak (days)</th><td>1</td></tr>' in html
    assert "<td>1 / 30</td>" in html
    assert NO_DAILY_ACTIVITY_NOTE not in html
    assert READING_SOURCE_CONNECTED in html


# --- 3. the year never reaches a rendered surface ---------------------------


def test_no_rendered_surface_names_1970_or_none() -> None:
    html = render_view(build_view(_owned_only(), [], ()))
    assert "1970" not in html
    assert "Reading Wrapped None" not in html
    assert f"Reading Wrapped {UNMEASURED_YEAR_LABEL}" in html
    assert "Standout reads of" not in html


def test_a_measured_view_still_names_its_year() -> None:
    states, activity = _read_something()
    html = render_view(build_view(states, activity, ()))
    assert "Reading Wrapped 2024" in html
    assert "Standout reads of 2024" in html
    # Scoped to the year claim: the unread books on the shelf below legitimately
    # still report "Progress: not measured", which is the point of this fix.
    assert f"Reading Wrapped {UNMEASURED_YEAR_LABEL}" not in html
    assert NO_READING_SOURCE_NOTE not in html


# --- 4. goals: unknown progress, not 0% -------------------------------------


def test_goals_without_reading_data_drop_the_year_and_the_percentage() -> None:
    states = _owned_only()
    wrapped = compute_wrapped(states, [], None)
    stats = compute_stats(states, [], 0)
    goals = compute_goals(stats, wrapped, books_target=52, pages_target=15_000, hours_target=200)
    assert [g.name for g in goals] == ["Books", "Pages", "Hours"]
    assert not any(g.measurable for g in goals)
    assert not any(g.met for g in goals)


def test_goals_with_reading_data_keep_their_year() -> None:
    states, activity = _read_something()
    wrapped = compute_wrapped(states, activity, 2024)
    stats = compute_stats(states, activity, 19_872)
    goals = compute_goals(stats, wrapped, books_target=52)
    assert goals[0].name == "Books in 2024"
    assert goals[0].measurable


def test_goals_section_renders_not_measured_instead_of_zero_percent() -> None:
    html = render_view(
        build_view(_owned_only(), [], (), goal_books=52, goal_pages=15_000, goal_hours=200)
    )
    assert "Books in 1970" not in html
    assert f"<td>{NOT_MEASURED} / 52</td>" in html
    assert "<td>0%</td>" not in html


# --- 5. /share stops composing a year nobody measured -----------------------


def test_no_year_card_without_a_measured_year() -> None:
    view = build_view(_owned_only(), [], ())
    assert build_share_cards(view) == ()


def test_the_honest_empty_share_message_is_reachable() -> None:
    """It was dead code: the year card was emitted unconditionally."""
    view = build_view(_owned_only(), [], ())
    page = render_share_page(build_share_cards(view), user="you")
    assert "No share cards yet" in page
    assert "1970" not in page


def test_a_measured_view_still_gets_a_year_card() -> None:
    states, activity = _read_something()
    cards = build_share_cards(build_view(states, activity, ()))
    assert [c.kind for c in cards] == ["year", "finished"]
    assert "My 2024 in books" in cards[0].post_text()


def test_composing_a_year_card_without_a_year_is_an_error() -> None:
    with pytest.raises(ValueError, match="measured year"):
        year_in_books_card(Wrapped.unmeasured())


# --- 6. an unopened book has no progress, not 0% ----------------------------


def _owned_with_an_all_zero_stat(count: int = 3) -> list[ReadingState]:
    """A per-device library: every owned book carries a stat that measured nothing.

    This is the shape `ingest.kobo.read_stats` produces. Kobo's ``content``
    table has a row for every book on the device, opened or not, so an
    untouched book arrives as a real ``ReadingStat`` whose every reading field
    is zero — while ``total_pages`` is a genuine catalog fact.

    ``_owned_only`` cannot catch a renderer that draws a meter unconditionally:
    it carries no ``stat`` at all, so ``progress_recorded`` is ``False`` there
    by construction and the assertions below hold for any renderer. This
    fixture is where the failure is possible.
    """
    return [
        replace(
            state,
            stat=ReadingStat(
                key=f"b{i}",
                title=state.title,
                authors=state.authors,
                pages_read=0,
                total_pages=200,
                read_time_seconds=0,
                last_read_ts=0,
                sessions=0,
            ),
        )
        for i, state in enumerate(_owned_only(count))
    ]


def test_books_with_no_progress_record_render_no_meter() -> None:
    html = render_view(build_view(_owned_only(), [], ()))
    assert "0% complete" not in html
    assert '<progress max="100" value="0"' not in html
    assert f"Progress: {NOT_MEASURED}" in html


def test_a_stat_that_measured_nothing_is_not_a_progress_record() -> None:
    """The Kobo re-opening of this defect (#126), asserted where it can fail."""
    states = _owned_with_an_all_zero_stat()
    assert all(s.stat is not None for s in states)
    assert all(s.stat is not None and s.stat.measured is False for s in states)
    assert all(s.progress_recorded is False for s in states)
    html = render_view(build_view(states, [], ()))
    assert "0% complete" not in html
    assert '<progress max="100" value="0"' not in html
    assert f"Progress: {NOT_MEASURED}" in html


def test_an_all_zero_stat_is_not_evidence_for_the_stats_panel() -> None:
    """The same row must not make eight zeros read as eight measurements."""
    assert compute_stats(_owned_with_an_all_zero_stat(), [], 0).measured is False
    opened = replace(
        _owned_with_an_all_zero_stat(1)[0].stat or ReadingStat("", "", (), 0, 0, 0, 0, 0),
        read_time_seconds=600,
    )
    states = [replace(_owned_with_an_all_zero_stat(1)[0], stat=opened)]
    assert compute_stats(states, [], 0).measured is True


def test_a_book_with_progress_still_renders_its_meter() -> None:
    states, activity = _read_something()
    html = render_view(build_view(states, activity, ()))
    assert "100% complete" in html
    assert "<progress" in html


def test_progress_recorded_separates_unopened_from_unstarted() -> None:
    unopened = _owned_only(1)[0]
    assert unopened.percent_complete == 0.0
    assert unopened.progress_recorded is False
    just_opened = ReadingState(
        title="Book 0",
        authors=("Author 0",),
        status=ReadingStatus.READING,
        stat=ReadingStat("b0", "Book 0", ("Author 0",), 300, 0, 0, 0, 0),
    )
    assert just_opened.percent_complete == 0.0
    assert just_opened.progress_recorded is True


# --- 7. alphabetical order is not personalization ---------------------------


def test_to_read_is_not_claimed_as_taste_ranked_without_a_taste() -> None:
    view = build_view(_owned_only(), [], ())
    assert view.to_read_taste_ranked is False
    # The measured claim: the shelf really is byte-for-byte alphabetical here.
    assert [s.title for s in view.to_read] == sorted(s.title for s in view.to_read)
    html = render_view(view)
    assert "Listed alphabetically by title" in html
    assert "ranked by fit to your sourced themes" not in html


def test_to_read_is_taste_ranked_once_a_finished_book_exists() -> None:
    states, activity = _read_something()
    view = build_view(states, activity, ())
    assert view.to_read_taste_ranked
    html = render_view(view)
    assert "ranked by fit to your sourced themes" in html
    assert "Listed alphabetically by title" not in html


def test_opds_to_read_blurb_matches_the_order_it_actually_used() -> None:
    unranked = build_view(_owned_only(), [], ())
    feed = opds.build_root_navigation(unranked)
    assert opds.TO_READ_BLURB_ALPHABETICAL in feed
    assert opds.TO_READ_BLURB_RANKED not in feed

    states, activity = _read_something()
    ranked = opds.build_root_navigation(build_view(states, activity, ()))
    assert opds.TO_READ_BLURB_RANKED in ranked
    assert opds.TO_READ_BLURB_ALPHABETICAL not in ranked


# --- 8. the dashboard says which reading sources are connected --------------


def test_data_status_names_the_missing_reading_source() -> None:
    html = render_view(build_view(_owned_only(), [], ()))
    assert READING_SOURCE_MISSING in html
    assert READING_SOURCE_CONNECTED not in html


def test_data_status_names_a_connected_reading_source() -> None:
    states, activity = _read_something()
    html = render_view(build_view(states, activity, ()))
    assert READING_SOURCE_CONNECTED in html
    assert READING_SOURCE_MISSING not in html


# --- 9. the demo world is unaffected ----------------------------------------


def test_the_demo_world_still_reports_its_real_year(tmp_path: Path) -> None:
    """The fixtures do carry reading data, so nothing here should go quiet."""
    view = demo_view(tmp_path)
    assert view.wrapped.measured
    assert view.stats.measured
    assert view.to_read_taste_ranked
    html = render_view(view)
    assert NO_READING_SOURCE_NOTE not in html
    assert UNMEASURED_YEAR_LABEL not in html
