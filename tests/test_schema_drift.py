"""Schema-drift CI matrix: readers cope with recorded source-DB versions.

Calibre, KOReader, and Calibre-Web all change their schemas across releases.
The readers probe for optional tables/columns
(:func:`ingest.snapshot.table_exists` / :func:`ingest.snapshot.columns`), so a
library on a different version must still ingest rather than crash. This module
replaces the old two hand-written fixtures with a *recorded matrix*: every
`.sql` file under ``tests/schemas/{calibre,koreader,calibre_web}/`` is a real
DDL snippet keyed by version/era, parametrized here so adding a version is just
dropping in a new fixture file. See ``tests/schemas/MATRIX.md`` for the full
matrix and provenance of each fixture.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from ingest.calibre import read_books
from ingest.calibre_web import read_state
from ingest.koreader import read_stats
from ingest.models import Author, Book
from ingest.snapshot import open_readonly

SCHEMAS_DIR = Path(__file__).parent / "schemas"
CALIBRE_FIXTURES = sorted((SCHEMAS_DIR / "calibre").glob("*.sql"))
KOREADER_FIXTURES = sorted((SCHEMAS_DIR / "koreader").glob("*.sql"))
CALIBRE_WEB_FIXTURES = sorted((SCHEMAS_DIR / "calibre_web").glob("*.sql"))

# The recorded matrix of record: which optional tables/columns each fixture
# has, mirrored in tests/schemas/MATRIX.md. Kept here too so the assertions
# check the *specific* fallback branch each era is meant to exercise, not just
# "it didn't crash" — and so a fixture with no matching entry fails loudly
# (see test_matrix_covers_every_fixture_file below).
CALIBRE_MATRIX: dict[str, dict[str, bool]] = {
    "calibre_2.x": {"series": False, "identifiers": False},
    "calibre_5.x": {"series": True, "identifiers": False},
    "calibre_7.x": {"series": True, "identifiers": True},
}

KOREADER_MATRIX: dict[str, dict[str, bool]] = {
    "koreader_2021": {"total_read_pages": False, "highlights": False, "page_stat_data": False},
    "koreader_2023": {"total_read_pages": True, "highlights": False, "page_stat_data": True},
    "koreader_current": {"total_read_pages": True, "highlights": True, "page_stat_data": True},
}

# Calibre-Web's app.db drifts on two axes: whether `book_read_link` has migrated
# from `is_read` to `read_status`, and whether the Kobo-sync tables exist *and*
# have anything in them. "Absent" and "present but empty" are separate rows
# because they reach the parser by different paths and must agree.
CALIBRE_WEB_MATRIX: dict[str, dict[str, bool]] = {
    "calibre_web_0.6.4": {"read_status": False, "kobo_tables": False, "kobo_measured": False},
    "calibre_web_0.6.7": {"read_status": True, "kobo_tables": True, "kobo_measured": False},
    "calibre_web_current": {"read_status": True, "kobo_tables": True, "kobo_measured": True},
}

#: The Calibre catalog every Calibre-Web fixture's `book_id`s point into.
#: app.db stores no titles, so the parser can only name rows it can join here.
CALIBRE_WEB_BOOKS = [
    Book(book_id="calibre:1", title="Stone Butch Blues", authors=(Author("Leslie Feinberg"),)),
    Book(book_id="calibre:2", title="Nevada", authors=(Author("Imogen Binnie"),)),
]


def _build_db(sql_path: Path, tmp_path: Path) -> Path:
    """Materialize a fixture's DDL/inserts into a real temp SQLite file."""
    db = tmp_path / f"{sql_path.stem}.sqlite"
    conn = sqlite3.connect(db)
    try:
        conn.executescript(sql_path.read_text())
        conn.commit()
    finally:
        conn.close()
    return db


def test_matrix_covers_every_fixture_file() -> None:
    """A fixture dropped without a matrix entry (or vice versa) fails here."""
    assert {p.stem for p in CALIBRE_FIXTURES} == set(CALIBRE_MATRIX)
    assert {p.stem for p in KOREADER_FIXTURES} == set(KOREADER_MATRIX)
    assert {p.stem for p in CALIBRE_WEB_FIXTURES} == set(CALIBRE_WEB_MATRIX)


@pytest.mark.parametrize("sql_path", CALIBRE_FIXTURES, ids=lambda p: p.stem)
def test_calibre_reads_every_recorded_schema_version(sql_path: Path, tmp_path: Path) -> None:
    expect = CALIBRE_MATRIX[sql_path.stem]
    db = _build_db(sql_path, tmp_path)
    with open_readonly(db) as ro:
        books = read_books(ro, retrieved_at="2026-07-02")

    assert len(books) >= 1, f"{sql_path.name} produced no books"
    for book in books:
        assert book.title
        assert book.authors, f"{sql_path.name}: {book.title!r} has no authors"

    has_series = any(b.series is not None for b in books)
    assert has_series == expect["series"], (
        f"{sql_path.name}: expected series presence={expect['series']}, got {has_series}"
    )
    has_identifiers = any(b.identifiers for b in books)
    assert has_identifiers == expect["identifiers"], (
        f"{sql_path.name}: expected identifiers presence={expect['identifiers']}, "
        f"got {has_identifiers}"
    )


@pytest.mark.parametrize("sql_path", KOREADER_FIXTURES, ids=lambda p: p.stem)
def test_koreader_reads_every_recorded_schema_version(sql_path: Path, tmp_path: Path) -> None:
    expect = KOREADER_MATRIX[sql_path.stem]
    db = _build_db(sql_path, tmp_path)
    with open_readonly(db) as ro:
        stats = read_stats(ro)

    assert len(stats) >= 1, f"{sql_path.name} produced no stats"
    for stat in stats:
        assert stat.title

    has_pages_read = any(s.pages_read > 0 for s in stats)
    assert has_pages_read == expect["total_read_pages"], (
        f"{sql_path.name}: expected total_read_pages presence="
        f"{expect['total_read_pages']}, got {has_pages_read}"
    )
    has_highlights = any(s.highlights > 0 for s in stats)
    assert has_highlights == expect["highlights"], (
        f"{sql_path.name}: expected highlights presence={expect['highlights']}, "
        f"got {has_highlights}"
    )
    has_sessions = any(s.sessions > 0 for s in stats)
    assert has_sessions == expect["page_stat_data"], (
        f"{sql_path.name}: expected page_stat_data presence="
        f"{expect['page_stat_data']}, got {has_sessions}"
    )


@pytest.mark.parametrize("sql_path", CALIBRE_WEB_FIXTURES, ids=lambda p: p.stem)
def test_calibre_web_reads_every_recorded_schema_version(sql_path: Path, tmp_path: Path) -> None:
    expect = CALIBRE_WEB_MATRIX[sql_path.stem]
    db = _build_db(sql_path, tmp_path)
    with open_readonly(db) as ro:
        state = read_state(ro, CALIBRE_WEB_BOOKS)

    assert len(state.stats) >= 1, f"{sql_path.name} produced no read-state"
    for stat in state.stats:
        assert stat.title
        # Calibre-Web records no page counts in any era; a fixture that made one
        # appear would mean the parser had started inventing them.
        assert stat.total_pages == 0
        assert stat.pages_read == 0

    # "Finished" is the one assertion every recorded era can make, and it
    # reaches `unify` as device progress rather than as a fabricated page count.
    assert any(p.percentage == 1.0 for p in state.progress.values()), (
        f"{sql_path.name}: no finished book surfaced"
    )

    has_read_time = any(s.read_time_seconds > 0 for s in state.stats)
    assert has_read_time == expect["kobo_measured"], (
        f"{sql_path.name}: expected measured reading time={expect['kobo_measured']}, "
        f"got {has_read_time}"
    )
    has_partial = any(0.0 < p.percentage < 1.0 for p in state.progress.values())
    assert has_partial == expect["kobo_measured"], (
        f"{sql_path.name}: expected a measured mid-book position="
        f"{expect['kobo_measured']}, got {has_partial}"
    )
    has_sessions = any(s.sessions > 0 for s in state.stats)
    assert has_sessions == expect["read_status"], (
        f"{sql_path.name}: `times_started_reading` arrived with `read_status`; "
        f"expected sessions presence={expect['read_status']}, got {has_sessions}"
    )
