"""Calibre reader: books, authors, sourced tags, series, schema-drift tolerance."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ingest.calibre import load_library, read_books
from ingest.models import SourceKind


def test_reads_all_books_with_authors(demo_dbs: tuple[Path, Path], workdir: Path) -> None:
    metadata_db, _ = demo_dbs
    books = load_library(metadata_db, workdir / "snapshots", retrieved_at="2026-06-05")
    assert len(books) >= 8
    titles = {b.title for b in books}
    assert "Kindred" in titles
    butler = next(b for b in books if b.title == "Kindred")
    assert "Octavia E. Butler" in butler.author_names


def test_tags_are_sourced_from_calibre(demo_dbs: tuple[Path, Path], workdir: Path) -> None:
    metadata_db, _ = demo_dbs
    books = load_library(metadata_db, workdir / "snapshots", retrieved_at="2026-06-05")
    plett = next(b for b in books if b.title == "A Safe Girl to Love")
    assert "trans" in plett.tag_labels
    for tag in plett.theme_tags:
        assert tag.source.kind is SourceKind.CALIBRE_TAG
        assert tag.source.retrieved_at == "2026-06-05"
        assert tag.source.citation  # non-empty provenance


def test_series_is_read(demo_dbs: tuple[Path, Path], workdir: Path) -> None:
    metadata_db, _ = demo_dbs
    books = load_library(metadata_db, workdir / "snapshots")
    sower = next(b for b in books if b.title == "Parable of the Sower")
    assert sower.series == "Earthseed"


def test_tolerates_missing_optional_tables(workdir: Path) -> None:
    """A minimal Calibre DB without tags/series/identifiers still ingests."""
    db = workdir / "minimal.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, series_index REAL, pubdate TEXT);
        CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT, sort TEXT);
        CREATE TABLE books_authors_link (id INTEGER PRIMARY KEY, book INTEGER, author INTEGER);
        INSERT INTO books (id, title, series_index, pubdate) VALUES (1, 'Solo', NULL, NULL);
        INSERT INTO authors (id, name, sort) VALUES (1, 'Writer', 'Writer');
        INSERT INTO books_authors_link (book, author) VALUES (1, 1);
        """
    )
    conn.commit()
    conn.close()
    from ingest.snapshot import open_readonly

    with open_readonly(db) as ro:
        books = read_books(ro)
    assert len(books) == 1
    assert books[0].theme_tags == ()
    assert books[0].series is None
    assert books[0].languages == ()
    assert books[0].publisher is None


def test_languages_and_publisher_are_read(workdir: Path) -> None:
    """FIX-11: Calibre's languages/publishers tables populate sourced Book facts."""
    db = workdir / "with_lang_pub.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, series_index REAL, pubdate TEXT);
        CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT, sort TEXT);
        CREATE TABLE books_authors_link (id INTEGER PRIMARY KEY, book INTEGER, author INTEGER);
        CREATE TABLE languages (id INTEGER PRIMARY KEY, lang_code TEXT);
        CREATE TABLE books_languages_link (
            id INTEGER PRIMARY KEY, book INTEGER, lang_code INTEGER, item_order INTEGER
        );
        CREATE TABLE publishers (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE books_publishers_link (
            id INTEGER PRIMARY KEY, book INTEGER, publisher INTEGER
        );
        INSERT INTO books (id, title, series_index, pubdate)
            VALUES (1, 'Translated Novel', NULL, NULL);
        INSERT INTO books (id, title, series_index, pubdate)
            VALUES (2, 'Unknown Facts', NULL, NULL);
        INSERT INTO authors (id, name, sort) VALUES (1, 'Writer', 'Writer');
        INSERT INTO books_authors_link (book, author) VALUES (1, 1);
        INSERT INTO books_authors_link (book, author) VALUES (2, 1);
        INSERT INTO languages (id, lang_code) VALUES (1, 'eng');
        INSERT INTO languages (id, lang_code) VALUES (2, 'fra');
        INSERT INTO books_languages_link (book, lang_code, item_order) VALUES (1, 1, 0);
        INSERT INTO books_languages_link (book, lang_code, item_order) VALUES (1, 2, 1);
        INSERT INTO publishers (id, name) VALUES (1, 'Small Press');
        INSERT INTO books_publishers_link (book, publisher) VALUES (1, 1);
        """
    )
    conn.commit()
    conn.close()
    from ingest.snapshot import open_readonly

    with open_readonly(db) as ro:
        books = read_books(ro)
    translated = next(b for b in books if b.title == "Translated Novel")
    assert translated.languages == ("eng", "fra")
    assert translated.publisher == "Small Press"

    unknown = next(b for b in books if b.title == "Unknown Facts")
    assert unknown.languages == ()
    assert unknown.publisher is None


def test_author_names_unescape_calibre_pipe(workdir: Path) -> None:
    """Calibre escapes a comma in ``authors.name`` as ``|``; ingest restores it.

    Found by running the ingest against a real 1,907-book library, where 53
    books rendered names like ``Collins| Buck`` on the dashboard. The ``sort``
    column stores the same string already comma-formed, which is what confirms
    the convention.
    """
    db = workdir / "escaped_authors.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, series_index REAL, pubdate TEXT);
        CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT, sort TEXT);
        CREATE TABLE books_authors_link (id INTEGER PRIMARY KEY, book INTEGER, author INTEGER);
        INSERT INTO books (id, title, series_index, pubdate) VALUES (1, 'Custer Died', NULL, NULL);
        INSERT INTO books (id, title, series_index, pubdate) VALUES (2, 'Plain Name', NULL, NULL);
        INSERT INTO authors (id, name, sort)
            VALUES (1, 'Vine Deloria| Jr.', 'Vine Deloria, Jr.');
        INSERT INTO authors (id, name, sort)
            VALUES (2, 'Octavia E. Butler', 'Butler, Octavia E.');
        INSERT INTO books_authors_link (book, author) VALUES (1, 1);
        INSERT INTO books_authors_link (book, author) VALUES (2, 2);
        """
    )
    conn.commit()
    conn.close()
    from ingest.snapshot import open_readonly

    with open_readonly(db) as ro:
        books = read_books(ro)
    escaped = next(b for b in books if b.title == "Custer Died")
    assert escaped.author_names == ("Vine Deloria, Jr.",)
    assert "|" not in escaped.author_names[0]

    # A name with no escape is passed through untouched.
    plain = next(b for b in books if b.title == "Plain Name")
    assert plain.author_names == ("Octavia E. Butler",)
