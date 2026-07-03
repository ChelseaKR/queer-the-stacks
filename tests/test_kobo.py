"""Kobo native reader: per-book stats from `KoboReader.sqlite`'s `content` table."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from ingest.kobo import load_stats, read_stats
from ingest.snapshot import open_readonly

_CREATE_CONTENT = """
CREATE TABLE content (
    ContentID TEXT PRIMARY KEY,
    ContentType INTEGER,
    MimeType TEXT,
    BookID TEXT,
    Title TEXT,
    Attribution TEXT,
    ___PercentRead INTEGER,
    ReadStatus INTEGER,
    TimeSpentReading INTEGER,
    ___NumPages INTEGER,
    DateLastRead TEXT
);
"""


def _make_db(path: Path, rows: list[tuple]) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(_CREATE_CONTENT)
    conn.executemany(
        """
        INSERT INTO content (
            ContentID, ContentType, MimeType, BookID, Title, Attribution,
            ___PercentRead, ReadStatus, TimeSpentReading, ___NumPages, DateLastRead
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def test_reads_finished_reading_and_unread_books(tmp_path: Path) -> None:
    db = tmp_path / "KoboReader.sqlite"
    _make_db(
        db,
        [
            (
                "file:///finished.kepub.epub",
                6,
                "application/x-kobo-epub+zip",
                None,
                "Kindred",
                "Octavia E. Butler",
                100,
                2,
                12000,
                287,
                "2026-05-01T10:00:00.000",
            ),
            (
                "file:///reading.kepub.epub",
                6,
                "application/x-kobo-epub+zip",
                None,
                "Stone Butch Blues",
                "Leslie Feinberg",
                42,
                1,
                3000,
                300,
                "2026-05-15T20:30:00.000",
            ),
            (
                "file:///unread.kepub.epub",
                6,
                "application/x-kobo-epub+zip",
                None,
                "Gender Outlaw",
                "Kate Bornstein",
                0,
                0,
                0,
                200,
                None,
            ),
        ],
    )
    with open_readonly(db) as conn:
        stats = read_stats(conn)
    assert len(stats) == 3
    by_title = {s.title: s for s in stats}

    kindred = by_title["Kindred"]
    assert kindred.authors == ("Octavia E. Butler",)
    assert kindred.total_pages == 287
    assert kindred.is_finished
    assert kindred.pages_read == 287
    assert kindred.read_time_seconds == 12000
    assert kindred.last_read_ts > 0
    assert kindred.sessions == 0
    assert kindred.key  # non-empty title|author join key

    sbb = by_title["Stone Butch Blues"]
    assert not sbb.is_finished
    assert 0.0 < sbb.percent_complete < 1.0
    assert sbb.pages_read == round(42 / 100 * 300)

    unread = by_title["Gender Outlaw"]
    assert unread.pages_read == 0
    assert unread.read_time_seconds == 0
    assert unread.last_read_ts == 0


def test_deduplicates_chapter_rows_to_the_volume_row(tmp_path: Path) -> None:
    """Kobo stores one `content` row per chapter; only the volume row should surface."""
    db = tmp_path / "KoboReader.sqlite"
    _make_db(
        db,
        [
            (
                "file:///book.kepub.epub",
                6,
                "application/x-kobo-epub+zip",
                None,  # volume row: BookID is NULL / self
                "Beloved",
                "Toni Morrison",
                55,
                1,
                5000,
                350,
                "2026-06-01T08:00:00.000",
            ),
            (
                "file:///book.kepub.epub!chapter1",
                6,
                "application/xhtml+xml",
                "file:///book.kepub.epub",  # chapter row: BookID points at the volume
                "Beloved",
                "Toni Morrison",
                None,
                None,
                None,
                None,
                None,
            ),
            (
                "file:///book.kepub.epub!chapter2",
                6,
                "application/xhtml+xml",
                "file:///book.kepub.epub",
                "Beloved",
                "Toni Morrison",
                None,
                None,
                None,
                None,
                None,
            ),
        ],
    )
    with open_readonly(db) as conn:
        stats = read_stats(conn)
    assert len(stats) == 1
    assert stats[0].total_pages == 350
    assert stats[0].pages_read == round(55 / 100 * 350)


def test_kobo_without_optional_columns(tmp_path: Path) -> None:
    """An older/variant Kobo `content` table lacking optional columns still reads."""
    db = tmp_path / "old.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE content (
            ContentID TEXT PRIMARY KEY, ContentType INTEGER,
            Title TEXT, Attribution TEXT, ___PercentRead INTEGER
        );
        INSERT INTO content (ContentID, ContentType, Title, Attribution, ___PercentRead)
        VALUES ('file:///old.epub', 6, 'Old Format', 'Author', 50);
        """
    )
    conn.commit()
    conn.close()
    with open_readonly(db) as ro:
        stats = read_stats(ro)
    assert len(stats) == 1
    s = stats[0]
    assert s.title == "Old Format"
    assert s.authors == ("Author",)
    assert s.total_pages == 0  # ___NumPages absent -> default
    assert s.pages_read == 0  # no total_pages to compute a fraction against
    assert s.read_time_seconds == 0  # TimeSpentReading absent -> default
    assert s.last_read_ts == 0  # DateLastRead absent -> default
    assert s.sessions == 0
    assert s.highlights == 0


def test_date_last_read_formats(tmp_path: Path) -> None:
    """Zulu-suffixed and unparsable `DateLastRead` values are handled gracefully."""
    db = tmp_path / "KoboReader.sqlite"
    _make_db(
        db,
        [
            (
                "file:///zulu.epub",
                6,
                "application/x-kobo-epub+zip",
                None,
                "Zulu Time",
                "Author One",
                10,
                1,
                60,
                100,
                "2026-06-10T12:00:00Z",
            ),
            (
                "file:///garbage.epub",
                6,
                "application/x-kobo-epub+zip",
                None,
                "Garbage Date",
                "Author Two",
                10,
                1,
                60,
                100,
                "not-a-date",
            ),
        ],
    )
    with open_readonly(db) as conn:
        stats = read_stats(conn)
    by_title = {s.title: s for s in stats}
    assert by_title["Zulu Time"].last_read_ts > 0
    assert by_title["Garbage Date"].last_read_ts == 0


def test_content_table_without_content_id_column(tmp_path: Path) -> None:
    """A `content` table missing `ContentID` skips dedup but still reads rows."""
    db = tmp_path / "no_id.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE content (
            ContentType INTEGER, Title TEXT, Attribution TEXT, ___PercentRead INTEGER
        );
        INSERT INTO content (ContentType, Title, Attribution, ___PercentRead)
        VALUES (6, 'No ID Book', 'Author', 25);
        """
    )
    conn.commit()
    conn.close()
    with open_readonly(db) as ro:
        stats = read_stats(ro)
    assert len(stats) == 1
    assert stats[0].title == "No ID Book"


def test_empty_kobo_db(tmp_path: Path) -> None:
    db = tmp_path / "empty.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript("CREATE TABLE unrelated (x INTEGER);")
    conn.commit()
    conn.close()
    with open_readonly(db) as ro:
        assert read_stats(ro) == []


def test_load_stats_snapshots_and_reads(tmp_path: Path) -> None:
    db = tmp_path / "KoboReader.sqlite"
    _make_db(
        db,
        [
            (
                "file:///a.epub",
                6,
                "application/x-kobo-epub+zip",
                None,
                "A Book",
                "Some Author",
                10,
                1,
                60,
                100,
                "2026-06-10T00:00:00.000",
            )
        ],
    )
    stats = load_stats(db, tmp_path / "snapshots")
    assert len(stats) == 1
    assert stats[0].title == "A Book"


def test_load_stats_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_stats(tmp_path / "nope.sqlite", tmp_path / "snapshots")
