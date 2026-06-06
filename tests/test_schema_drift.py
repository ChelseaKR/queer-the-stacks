"""Schema-drift tolerance: readers cope with older/variant Calibre + KOReader DBs.

Calibre and KOReader change their schemas across versions. The readers probe for
optional tables/columns, so a library on a different version must still ingest
rather than crash — verified here with hand-built variant schemas.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ingest.calibre import read_books
from ingest.koreader import read_stats
from ingest.snapshot import open_readonly


def test_koreader_without_optional_columns(tmp_path: Path) -> None:
    """An older KOReader `book` table lacking highlights/total_read_pages reads."""
    db = tmp_path / "old.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE book (id INTEGER PRIMARY KEY, title TEXT, authors TEXT,
            last_open INTEGER, pages INTEGER, md5 TEXT, total_read_time INTEGER);
        INSERT INTO book (id, title, authors, last_open, pages, md5, total_read_time)
        VALUES (1, 'Old Format', 'Author', 100, 200, 'md5x', 600);
        """
    )
    conn.commit()
    conn.close()
    with open_readonly(db) as ro:
        stats = read_stats(ro)
    assert len(stats) == 1
    s = stats[0]
    assert s.title == "Old Format"
    assert s.highlights == 0  # column absent -> default
    assert s.pages_read == 0  # total_read_pages absent -> default
    assert s.read_time_seconds == 600


def test_calibre_without_series_or_identifiers(tmp_path: Path) -> None:
    db = tmp_path / "cal.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, series_index REAL, pubdate TEXT);
        CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT, sort TEXT);
        CREATE TABLE books_authors_link (id INTEGER PRIMARY KEY, book INTEGER, author INTEGER);
        CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE books_tags_link (id INTEGER PRIMARY KEY, book INTEGER, tag INTEGER);
        INSERT INTO books (id, title, series_index, pubdate) VALUES (1, 'No Series', NULL, NULL);
        INSERT INTO authors (id, name, sort) VALUES (1, 'Writer', 'Writer');
        INSERT INTO books_authors_link (book, author) VALUES (1, 1);
        INSERT INTO tags (id, name) VALUES (1, 'queer');
        INSERT INTO books_tags_link (book, tag) VALUES (1, 1);
        """
    )
    conn.commit()
    conn.close()
    with open_readonly(db) as ro:
        books = read_books(ro, retrieved_at="2026-06-06")
    assert len(books) == 1
    assert books[0].series is None  # series table absent -> None
    assert books[0].identifiers == {}  # identifiers table absent -> empty
    assert "queer" in books[0].tag_labels  # tags still sourced
