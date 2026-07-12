"""Schema-drift CI matrix: readers cope with recorded Calibre/KOReader DB versions.

Calibre and KOReader change their schemas across releases. The readers probe
for optional tables/columns (:func:`ingest.snapshot.table_exists` /
:func:`ingest.snapshot.columns`), so a library on a different version must
still ingest rather than crash. This module replaces the old two hand-written
fixtures with a *recorded matrix*: every `.sql` file under
``tests/schemas/calibre/`` and ``tests/schemas/koreader/`` is a real DDL
snippet keyed by version/era, parametrized here so adding a version is just
dropping in a new fixture file. See ``tests/schemas/MATRIX.md`` for the full
matrix and provenance of each fixture.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from ingest.calibre import read_books
from ingest.koreader import read_stats
from ingest.snapshot import open_readonly

SCHEMAS_DIR = Path(__file__).parent / "schemas"
CALIBRE_FIXTURES = sorted((SCHEMAS_DIR / "calibre").glob("*.sql"))
KOREADER_FIXTURES = sorted((SCHEMAS_DIR / "koreader").glob("*.sql"))

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
