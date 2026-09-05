"""Calibre-Web read-state: what `app.db` measured, and what it refuses to invent.

Three properties carry the whole adapter, and each has a positive control beside
it so a change that suppressed everything could not pass:

1. **Nothing is fabricated.** Calibre-Web stores no page counts, so a finished
   book arrives with ``0/0`` pages and its "finished" reaches ``unify`` as
   device progress instead.
2. **Unmeasured is not zero.** An in-progress row with no synced position and no
   reading time is dropped rather than rendered as "0% read".
3. **Nobody else's reading gets imported.** A shared ``app.db`` with no reader
   configured raises instead of blending two people's history.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from ingest.calibre_web import (
    DEVICE,
    CalibreWebUserError,
    load_state,
    read_state,
    resolve_user_id,
)
from ingest.kosync import FixtureKosync
from ingest.models import Author, Book, ReadingStatus
from ingest.snapshot import open_readonly
from ingest.unify import unify

_MODERN_SCHEMA = """
CREATE TABLE user (id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE book_read_link (
    id INTEGER PRIMARY KEY,
    book_id INTEGER,
    user_id INTEGER,
    read_status INTEGER,
    last_modified DATETIME,
    last_time_started_reading DATETIME,
    times_started_reading INTEGER
);
CREATE TABLE kobo_reading_state (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    book_id INTEGER,
    last_modified DATETIME,
    priority_timestamp DATETIME
);
CREATE TABLE kobo_statistics (
    id INTEGER PRIMARY KEY,
    kobo_reading_state_id INTEGER,
    last_modified DATETIME,
    remaining_time_minutes INTEGER,
    spent_reading_minutes INTEGER
);
CREATE TABLE kobo_bookmark (
    id INTEGER PRIMARY KEY,
    kobo_reading_state_id INTEGER,
    last_modified DATETIME,
    location_source TEXT,
    location_type TEXT,
    location_value TEXT,
    progress_percent FLOAT,
    content_source_progress_percent FLOAT
);
"""

BOOKS = [
    Book(book_id="calibre:1", title="Stone Butch Blues", authors=(Author("Leslie Feinberg"),)),
    Book(book_id="calibre:2", title="Nevada", authors=(Author("Imogen Binnie"),)),
    Book(book_id="calibre:3", title="Zami", authors=(Author("Audre Lorde"),)),
]


def _make_db(path: Path, script: str) -> Path:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(script)
        conn.commit()
    finally:
        conn.close()
    return path


def _modern_db(path: Path, rows: str) -> Path:
    return _make_db(path, _MODERN_SCHEMA + rows)


# --- 1. finished is carried without inventing a page count ------------------


def test_finished_without_kobo_sync_yields_progress_not_pages(tmp_path: Path) -> None:
    db = _modern_db(
        tmp_path / "app.db",
        """
        INSERT INTO user (id, name) VALUES (1, 'reader');
        INSERT INTO book_read_link
            (id, book_id, user_id, read_status, last_modified,
             last_time_started_reading, times_started_reading)
        VALUES (1, 1, 1, 1, '2026-03-02 09:15:00.000000',
                '2026-02-28 21:00:00.000000', 3);
        """,
    )
    with open_readonly(db) as conn:
        state = read_state(conn, BOOKS)

    assert len(state.stats) == 1
    stat = state.stats[0]
    assert stat.title == "Stone Butch Blues"
    assert stat.authors == ("Leslie Feinberg",)
    # Calibre-Web knows no page counts. Anything but 0/0 here would be invented.
    assert (stat.pages_read, stat.total_pages) == (0, 0)
    assert stat.read_time_seconds == 0
    assert stat.sessions == 3
    assert stat.last_read_ts > 0

    progress = state.progress[stat.key]
    assert progress.percentage == 1.0
    assert progress.device == DEVICE
    assert progress.timestamp > 0


def test_finished_book_reaches_unify_as_finished(tmp_path: Path) -> None:
    """The zero-changes-to-`unify` bar: the join classifies this with no help."""
    db = _modern_db(
        tmp_path / "app.db",
        """
        INSERT INTO user (id, name) VALUES (1, 'reader');
        INSERT INTO book_read_link
            (id, book_id, user_id, read_status, last_modified,
             last_time_started_reading, times_started_reading)
        VALUES (1, 1, 1, 1, '2026-03-02 09:15:00.000000', NULL, 0);
        """,
    )
    with open_readonly(db) as conn:
        state = read_state(conn, BOOKS)

    states = unify(BOOKS, list(state.stats), FixtureKosync(state.progress))
    by_title = {s.title: s for s in states}
    assert by_title["Stone Butch Blues"].status is ReadingStatus.FINISHED
    assert by_title["Stone Butch Blues"].percent_complete == 1.0
    assert by_title["Stone Butch Blues"].latest_device == DEVICE
    # Positive control: the books Calibre-Web says nothing about stay untouched.
    assert by_title["Nevada"].status is ReadingStatus.UNREAD
    assert by_title["Nevada"].stat is None


def test_kobo_sync_supplies_measured_time_and_position(tmp_path: Path) -> None:
    db = _modern_db(
        tmp_path / "app.db",
        """
        INSERT INTO user (id, name) VALUES (1, 'reader');
        INSERT INTO book_read_link
            (id, book_id, user_id, read_status, last_modified,
             last_time_started_reading, times_started_reading)
        VALUES (1, 2, 1, 2, '2026-04-12 08:20:00.000000',
                '2026-04-11 22:40:00.000000', 2);
        INSERT INTO kobo_reading_state (id, user_id, book_id, last_modified, priority_timestamp)
        VALUES (11, 1, 2, '2026-04-12 08:20:00.000000', '2026-04-12 08:20:00.000000');
        INSERT INTO kobo_statistics
            (id, kobo_reading_state_id, last_modified, remaining_time_minutes,
             spent_reading_minutes)
        VALUES (21, 11, '2026-04-12 08:20:00.000000', 95, 75);
        INSERT INTO kobo_bookmark
            (id, kobo_reading_state_id, last_modified, location_source, location_type,
             location_value, progress_percent, content_source_progress_percent)
        VALUES (31, 11, '2026-04-12 08:20:00.000000', 'ch05.xhtml', 'KoboSpan',
                'kobo.5.2', 41.5, 41.5);
        """,
    )
    with open_readonly(db) as conn:
        state = read_state(conn, BOOKS)

    stat = state.stats[0]
    assert stat.title == "Nevada"
    assert stat.read_time_seconds == 75 * 60
    assert (stat.pages_read, stat.total_pages) == (0, 0)
    assert state.progress[stat.key].percentage == pytest.approx(0.415)

    states = unify(BOOKS, list(state.stats), FixtureKosync(state.progress))
    nevada = next(s for s in states if s.title == "Nevada")
    assert nevada.status is ReadingStatus.READING


# --- 2. unmeasured is not a zero --------------------------------------------


def test_in_progress_with_nothing_measured_is_dropped(tmp_path: Path) -> None:
    """ "Started, position unknown" must not render as "0% read"."""
    db = _modern_db(
        tmp_path / "app.db",
        """
        INSERT INTO user (id, name) VALUES (1, 'reader');
        INSERT INTO book_read_link
            (id, book_id, user_id, read_status, last_modified,
             last_time_started_reading, times_started_reading)
        VALUES (1, 2, 1, 2, '2026-03-04 07:30:00.000000',
                '2026-03-04 07:30:00.000000', 1);
        """,
    )
    with open_readonly(db) as conn:
        state = read_state(conn, BOOKS)

    assert state.stats == ()
    assert state.progress == {}

    states = unify(BOOKS, list(state.stats), FixtureKosync(state.progress))
    nevada = next(s for s in states if s.title == "Nevada")
    # Unmeasured, so no meter is drawn at all — not a meter pinned to zero.
    assert nevada.progress_recorded is False


def test_explicitly_unread_rows_carry_no_reading_record(tmp_path: Path) -> None:
    db = _modern_db(
        tmp_path / "app.db",
        """
        INSERT INTO user (id, name) VALUES (1, 'reader');
        INSERT INTO book_read_link
            (id, book_id, user_id, read_status, last_modified,
             last_time_started_reading, times_started_reading)
        VALUES (1, 1, 1, 0, '2026-03-02 09:15:00.000000', NULL, 0);
        """,
    )
    with open_readonly(db) as conn:
        state = read_state(conn, BOOKS)
    assert state.stats == ()


def test_a_row_whose_book_is_not_in_calibre_is_dropped(tmp_path: Path) -> None:
    """app.db stores no titles, so an unjoinable row cannot be named honestly."""
    db = _modern_db(
        tmp_path / "app.db",
        """
        INSERT INTO user (id, name) VALUES (1, 'reader');
        INSERT INTO book_read_link
            (id, book_id, user_id, read_status, last_modified,
             last_time_started_reading, times_started_reading)
        VALUES
            (1, 99, 1, 1, '2026-03-02 09:15:00.000000', NULL, 0),
            (2, 1, 1, 1, '2026-03-02 09:15:00.000000', NULL, 0);
        """,
    )
    with open_readonly(db) as conn:
        state = read_state(conn, BOOKS)
    # Positive control beside it: the joinable row still comes through.
    assert [s.title for s in state.stats] == ["Stone Butch Blues"]


# --- 3. whose reading is this? ----------------------------------------------


_TWO_READERS = """
INSERT INTO user (id, name) VALUES (1, 'chelsea'), (2, 'housemate');
INSERT INTO book_read_link
    (id, book_id, user_id, read_status, last_modified,
     last_time_started_reading, times_started_reading)
VALUES
    (1, 1, 1, 1, '2026-03-02 09:15:00.000000', NULL, 0),
    (2, 3, 2, 1, '2026-03-03 09:15:00.000000', NULL, 0);
"""


def test_two_readers_without_a_configured_user_refuses_to_guess(tmp_path: Path) -> None:
    db = _modern_db(tmp_path / "app.db", _TWO_READERS)
    with open_readonly(db) as conn, pytest.raises(CalibreWebUserError) as excinfo:
        read_state(conn, BOOKS)
    assert "STACKS_CALIBRE_WEB_USER" in str(excinfo.value)


def test_a_configured_user_imports_only_their_own_reading(tmp_path: Path) -> None:
    db = _modern_db(tmp_path / "app.db", _TWO_READERS)
    with open_readonly(db) as conn:
        state = read_state(conn, BOOKS, user="Chelsea")  # matched case-insensitively
    assert [s.title for s in state.stats] == ["Stone Butch Blues"]
    with open_readonly(db) as conn:
        other = read_state(conn, BOOKS, user="housemate")
    assert [s.title for s in other.stats] == ["Zami"]


def test_an_unknown_user_names_the_users_that_do_exist(tmp_path: Path) -> None:
    db = _modern_db(tmp_path / "app.db", _TWO_READERS)
    with open_readonly(db) as conn, pytest.raises(CalibreWebUserError) as excinfo:
        resolve_user_id(conn, "nobody")
    message = str(excinfo.value)
    assert "chelsea" in message and "housemate" in message


def test_one_reader_needs_no_configuration(tmp_path: Path) -> None:
    db = _modern_db(
        tmp_path / "app.db",
        """
        INSERT INTO user (id, name) VALUES (1, 'reader');
        INSERT INTO book_read_link
            (id, book_id, user_id, read_status, last_modified,
             last_time_started_reading, times_started_reading)
        VALUES (1, 1, 1, 1, '2026-03-02 09:15:00.000000', NULL, 0);
        """,
    )
    with open_readonly(db) as conn:
        assert resolve_user_id(conn) is None


# --- schema drift and the read-only entry point -----------------------------


def test_a_file_without_read_state_reads_as_empty(tmp_path: Path) -> None:
    """A Calibre-Web app.db with no `book_read_link` at all is empty, not an error."""
    db = _make_db(tmp_path / "app.db", "CREATE TABLE user (id INTEGER PRIMARY KEY, name TEXT);")
    with open_readonly(db) as conn:
        state = read_state(conn, BOOKS)
    assert state.stats == ()
    assert state.progress == {}


def test_load_state_snapshots_and_never_writes_the_source(tmp_path: Path) -> None:
    db = _modern_db(
        tmp_path / "app.db",
        """
        INSERT INTO user (id, name) VALUES (1, 'reader');
        INSERT INTO book_read_link
            (id, book_id, user_id, read_status, last_modified,
             last_time_started_reading, times_started_reading)
        VALUES (1, 1, 1, 1, '2026-03-02 09:15:00.000000', NULL, 0);
        """,
    )
    before = db.read_bytes()
    snapshot_dir = tmp_path / "snapshots"
    state = load_state(db, snapshot_dir, BOOKS)
    assert len(state.stats) == 1
    assert db.read_bytes() == before, "load_state must never write to the source app.db"
    assert (snapshot_dir / "app.snapshot.db").is_file()


def test_an_unparsable_timestamp_reads_as_no_timestamp(tmp_path: Path) -> None:
    """A malformed DateTime is 0 — never today, never 1970 rendered as a real date."""
    db = _modern_db(
        tmp_path / "app.db",
        """
        INSERT INTO user (id, name) VALUES (1, 'reader');
        INSERT INTO book_read_link
            (id, book_id, user_id, read_status, last_modified,
             last_time_started_reading, times_started_reading)
        VALUES (1, 1, 1, 1, 'not-a-date', 'also-not-a-date', 1);
        """,
    )
    with open_readonly(db) as conn:
        state = read_state(conn, BOOKS)
    assert state.stats[0].last_read_ts == 0
    assert state.progress[state.stats[0].key].timestamp == 0


# --- drift and defensive fallbacks -------------------------------------------
#
# Every branch below is a shape a real app.db can take. They are tested because
# an untested fallback is how a "0" that means "we could not look" gets
# published as a "0" that means "nothing was there".


def test_reading_time_without_a_position_still_counts_as_reading(tmp_path: Path) -> None:
    """Kobo sync recorded minutes but no bookmark: measured time, no percentage."""
    db = _modern_db(
        tmp_path / "app.db",
        """
        INSERT INTO user (id, name) VALUES (1, 'reader');
        INSERT INTO book_read_link
            (id, book_id, user_id, read_status, last_modified,
             last_time_started_reading, times_started_reading)
        VALUES (1, 2, 1, 2, '2026-04-12 08:20:00.000000', NULL, 1);
        INSERT INTO kobo_reading_state (id, user_id, book_id, last_modified, priority_timestamp)
        VALUES (11, 1, 2, '2026-04-12 08:20:00.000000', NULL);
        INSERT INTO kobo_statistics
            (id, kobo_reading_state_id, last_modified, remaining_time_minutes,
             spent_reading_minutes)
        VALUES (21, 11, '2026-04-12 08:20:00.000000', NULL, 40);
        """,
    )
    with open_readonly(db) as conn:
        state = read_state(conn, BOOKS)
    assert state.stats[0].read_time_seconds == 40 * 60
    # No position was recorded, so none is asserted.
    assert state.progress == {}
    states = unify(BOOKS, list(state.stats), FixtureKosync(state.progress))
    assert next(s for s in states if s.title == "Nevada").status is ReadingStatus.READING


def test_a_null_progress_percent_is_not_a_position(tmp_path: Path) -> None:
    db = _modern_db(
        tmp_path / "app.db",
        """
        INSERT INTO user (id, name) VALUES (1, 'reader');
        INSERT INTO book_read_link
            (id, book_id, user_id, read_status, last_modified,
             last_time_started_reading, times_started_reading)
        VALUES (1, 2, 1, 2, '2026-04-12 08:20:00.000000', NULL, 1);
        INSERT INTO kobo_reading_state (id, user_id, book_id, last_modified, priority_timestamp)
        VALUES (11, 1, 2, '2026-04-12 08:20:00.000000', NULL);
        INSERT INTO kobo_bookmark
            (id, kobo_reading_state_id, last_modified, location_source, location_type,
             location_value, progress_percent, content_source_progress_percent)
        VALUES (31, 11, '2026-04-12 08:20:00.000000', NULL, NULL, NULL, NULL, NULL);
        """,
    )
    with open_readonly(db) as conn:
        state = read_state(conn, BOOKS)
    assert state.stats == ()
    assert state.progress == {}


def test_a_minimal_single_user_app_db_reads_without_a_user_table(tmp_path: Path) -> None:
    """No `user` table, no `user_id`, no Kobo tables — the 0.6.4-and-narrower shape."""
    db = _make_db(
        tmp_path / "app.db",
        """
        CREATE TABLE book_read_link (id INTEGER PRIMARY KEY, book_id INTEGER, is_read BOOLEAN);
        INSERT INTO book_read_link (id, book_id, is_read) VALUES (1, 1, 1), (2, 2, 0);
        """,
    )
    with open_readonly(db) as conn:
        assert resolve_user_id(conn) is None
        state = read_state(conn, BOOKS)
    assert [s.title for s in state.stats] == ["Stone Butch Blues"]
    assert state.stats[0].sessions == 0  # the column does not exist in this shape
    assert state.progress[state.stats[0].key].percentage == 1.0


def test_a_file_with_no_read_state_table_needs_no_reader_chosen(tmp_path: Path) -> None:
    """With no `book_read_link` there is no read-state to attribute to anyone."""
    db = _make_db(tmp_path / "app.db", "CREATE TABLE user (id INTEGER PRIMARY KEY, name TEXT);")
    with open_readonly(db) as conn:
        assert resolve_user_id(conn) is None
        assert resolve_user_id(conn, "anyone") is None


def test_a_read_link_table_without_book_ids_reads_as_empty(tmp_path: Path) -> None:
    db = _make_db(
        tmp_path / "app.db",
        "CREATE TABLE book_read_link (id INTEGER PRIMARY KEY, read_status INTEGER);",
    )
    with open_readonly(db) as conn:
        assert read_state(conn, BOOKS).stats == ()


def test_rows_with_no_status_column_fall_back_to_what_was_measured(tmp_path: Path) -> None:
    """Neither `read_status` nor `is_read`: only a synced position can speak."""
    db = _make_db(
        tmp_path / "app.db",
        """
        CREATE TABLE book_read_link (id INTEGER PRIMARY KEY, book_id INTEGER, user_id INTEGER);
        CREATE TABLE kobo_reading_state (
            id INTEGER PRIMARY KEY, user_id INTEGER, book_id INTEGER, last_modified DATETIME
        );
        CREATE TABLE kobo_bookmark (
            id INTEGER PRIMARY KEY, kobo_reading_state_id INTEGER, progress_percent FLOAT
        );
        INSERT INTO book_read_link (id, book_id, user_id) VALUES (1, 1, 1), (2, 2, 1);
        INSERT INTO kobo_reading_state (id, user_id, book_id, last_modified)
        VALUES (11, 1, 2, '2026-04-12 08:20:00.000000');
        INSERT INTO kobo_bookmark (id, kobo_reading_state_id, progress_percent) VALUES (31, 11, 60);
        """,
    )
    with open_readonly(db) as conn:
        state = read_state(conn, BOOKS)
    assert [s.title for s in state.stats] == ["Nevada"]
    assert state.progress[state.stats[0].key].percentage == pytest.approx(0.6)


def test_kobo_tables_missing_their_columns_are_ignored(tmp_path: Path) -> None:
    db = _make_db(
        tmp_path / "app.db",
        """
        CREATE TABLE book_read_link (
            id INTEGER PRIMARY KEY, book_id INTEGER, read_status INTEGER
        );
        CREATE TABLE kobo_reading_state (id INTEGER PRIMARY KEY, book_id INTEGER);
        CREATE TABLE kobo_statistics (id INTEGER PRIMARY KEY, remaining_time_minutes INTEGER);
        CREATE TABLE kobo_bookmark (id INTEGER PRIMARY KEY, location_value TEXT);
        INSERT INTO book_read_link (id, book_id, read_status) VALUES (1, 1, 1);
        INSERT INTO kobo_reading_state (id, book_id) VALUES (11, 1);
        """,
    )
    with open_readonly(db) as conn:
        state = read_state(conn, BOOKS)
    assert state.stats[0].read_time_seconds == 0
    assert state.progress[state.stats[0].key].percentage == 1.0


def test_a_kobo_reading_state_without_book_ids_is_ignored(tmp_path: Path) -> None:
    db = _make_db(
        tmp_path / "app.db",
        """
        CREATE TABLE book_read_link (
            id INTEGER PRIMARY KEY, book_id INTEGER, read_status INTEGER
        );
        CREATE TABLE kobo_reading_state (id INTEGER PRIMARY KEY, last_modified DATETIME);
        INSERT INTO book_read_link (id, book_id, read_status) VALUES (1, 1, 1);
        """,
    )
    with open_readonly(db) as conn:
        assert read_state(conn, BOOKS).stats[0].title == "Stone Butch Blues"


def test_null_ids_on_either_side_are_skipped(tmp_path: Path) -> None:
    db = _modern_db(
        tmp_path / "app.db",
        """
        INSERT INTO user (id, name) VALUES (1, 'reader');
        INSERT INTO book_read_link
            (id, book_id, user_id, read_status, last_modified,
             last_time_started_reading, times_started_reading)
        VALUES
            (1, NULL, 1, 1, '2026-03-02 09:15:00.000000', NULL, 0),
            (2, 1, 1, 1, '2026-03-02 09:15:00.000000', NULL, 'not-a-number');
        INSERT INTO kobo_reading_state (id, user_id, book_id, last_modified, priority_timestamp)
        VALUES (11, 1, NULL, '2026-04-12 08:20:00.000000', NULL);
        """,
    )
    with open_readonly(db) as conn:
        state = read_state(conn, BOOKS)
    assert [s.title for s in state.stats] == ["Stone Butch Blues"]
    # A text value in an INTEGER column reads as 0, not as a crash.
    assert state.stats[0].sessions == 0


def test_a_book_id_that_is_not_a_calibre_id_cannot_be_joined(tmp_path: Path) -> None:
    """Only `calibre:<int>` ids can bridge to app.db's integer `book_id`."""
    db = _modern_db(
        tmp_path / "app.db",
        """
        INSERT INTO user (id, name) VALUES (1, 'reader');
        INSERT INTO book_read_link
            (id, book_id, user_id, read_status, last_modified,
             last_time_started_reading, times_started_reading)
        VALUES (1, 1, 1, 1, '2026-03-02 09:15:00.000000', NULL, 0);
        """,
    )
    odd_books = [
        Book(book_id="openlibrary:OL1M", title="Elsewhere", authors=(Author("Someone"),)),
        Book(book_id="calibre:not-a-number", title="Odd", authors=(Author("Someone"),)),
    ]
    with open_readonly(db) as conn:
        assert read_state(conn, odd_books).stats == ()


def test_timestamps_that_carry_a_zone_or_nothing_at_all(tmp_path: Path) -> None:
    db = _modern_db(
        tmp_path / "app.db",
        """
        INSERT INTO user (id, name) VALUES (1, 'reader');
        INSERT INTO book_read_link
            (id, book_id, user_id, read_status, last_modified,
             last_time_started_reading, times_started_reading)
        VALUES
            (1, 1, 1, 1, '2026-03-02T09:15:00Z', '   ', 0),
            (2, 2, 1, 1, '', NULL, 0);
        """,
    )
    with open_readonly(db) as conn:
        state = read_state(conn, BOOKS)
    by_title = {s.title: s for s in state.stats}
    # A blank "last started" is no timestamp; the Z-suffixed modification time parses.
    assert by_title["Stone Butch Blues"].last_read_ts == 0
    assert state.progress[by_title["Stone Butch Blues"].key].timestamp > 0
    assert state.progress[by_title["Nevada"].key].timestamp == 0
