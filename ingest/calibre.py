"""Read books, authors, tags, series, and identifiers from Calibre's metadata.db.

Strictly read-only (see :mod:`ingest.snapshot`). Calibre's tags become
:class:`ThemeTag` objects with a ``CALIBRE_TAG`` source — they are *sourced*
descriptors of a book, never inferred and never applied to an author.

The reader tolerates schema drift: every optional table is probed with
:func:`ingest.snapshot.table_exists` before it is queried, so a library missing
``series`` or ``identifiers`` still ingests cleanly (Quality §"resilient to
schema drift, versioned parsers").
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ingest.models import Author, Book, Source, SourceKind, ThemeTag, merge_tags
from ingest.snapshot import open_snapshot, table_exists

#: Citation marker for tags that came from the local Calibre library itself.
CALIBRE_CITATION = "calibre:metadata.db"


def _authors_for(conn: sqlite3.Connection, book_id: int) -> tuple[Author, ...]:
    rows = conn.execute(
        """
        SELECT a.name AS name, a.sort AS sort
        FROM books_authors_link l
        JOIN authors a ON a.id = l.author
        WHERE l.book = ?
        ORDER BY l.id
        """,
        (book_id,),
    ).fetchall()
    return tuple(Author(name=str(r["name"]), sort=str(r["sort"] or "")) for r in rows)


def _tags_for(conn: sqlite3.Connection, book_id: int, retrieved_at: str) -> tuple[ThemeTag, ...]:
    if not table_exists(conn, "tags"):
        return ()
    rows = conn.execute(
        """
        SELECT t.name AS name
        FROM books_tags_link l
        JOIN tags t ON t.id = l.tag
        WHERE l.book = ?
        ORDER BY t.name
        """,
        (book_id,),
    ).fetchall()
    tags = [
        ThemeTag(
            label=str(r["name"]),
            source=Source(
                kind=SourceKind.CALIBRE_TAG,
                citation=CALIBRE_CITATION,
                retrieved_at=retrieved_at,
                detail=str(r["name"]),
            ),
        )
        for r in rows
        if str(r["name"]).strip()
    ]
    return merge_tags(tags)


def _series_for(conn: sqlite3.Connection, book_id: int) -> tuple[str | None, float | None]:
    if not table_exists(conn, "series"):
        return None, None
    row = conn.execute(
        """
        SELECT s.name AS name
        FROM books_series_link l
        JOIN series s ON s.id = l.series
        WHERE l.book = ?
        LIMIT 1
        """,
        (book_id,),
    ).fetchone()
    return (str(row["name"]) if row else None), None


def _identifiers_for(conn: sqlite3.Connection, book_id: int) -> dict[str, str]:
    if not table_exists(conn, "identifiers"):
        return {}
    rows = conn.execute(
        "SELECT type AS type, val AS val FROM identifiers WHERE book = ?",
        (book_id,),
    ).fetchall()
    return {str(r["type"]): str(r["val"]) for r in rows}


def _languages_for(conn: sqlite3.Connection, book_id: int) -> tuple[str, ...]:
    """BCP-47 language codes for a book, sourced from Calibre's ``languages`` table.

    Unknown/missing stays an empty tuple — first-class, never guessed.
    """
    if not table_exists(conn, "books_languages_link") or not table_exists(conn, "languages"):
        return ()
    rows = conn.execute(
        """
        SELECT l2.lang_code AS lang_code
        FROM books_languages_link l
        JOIN languages l2 ON l2.id = l.lang_code
        WHERE l.book = ?
        ORDER BY l.item_order, l2.lang_code
        """,
        (book_id,),
    ).fetchall()
    return tuple(str(r["lang_code"]) for r in rows if str(r["lang_code"]).strip())


def _publisher_for(conn: sqlite3.Connection, book_id: int) -> str | None:
    """The publisher name for a book, sourced from Calibre's ``publishers`` table.

    Unknown/missing stays ``None`` — first-class, never guessed.
    """
    if not table_exists(conn, "books_publishers_link") or not table_exists(conn, "publishers"):
        return None
    row = conn.execute(
        """
        SELECT p.name AS name
        FROM books_publishers_link l
        JOIN publishers p ON p.id = l.publisher
        WHERE l.book = ?
        LIMIT 1
        """,
        (book_id,),
    ).fetchone()
    return str(row["name"]) if row else None


def read_books(conn: sqlite3.Connection, retrieved_at: str = "1970-01-01") -> list[Book]:
    """Read every book from an open read-only Calibre connection."""
    books: list[Book] = []
    rows = conn.execute("SELECT id, title, series_index, pubdate FROM books ORDER BY id").fetchall()
    for r in rows:
        bid = int(r["id"])
        series_name, _ = _series_for(conn, bid)
        try:
            series_index = float(r["series_index"]) if r["series_index"] is not None else None
        except TypeError, ValueError:
            series_index = None
        books.append(
            Book(
                book_id=f"calibre:{bid}",
                title=str(r["title"]),
                authors=_authors_for(conn, bid),
                series=series_name,
                series_index=series_index,
                identifiers=_identifiers_for(conn, bid),
                theme_tags=_tags_for(conn, bid, retrieved_at),
                pubdate=str(r["pubdate"]) if r["pubdate"] is not None else None,
                languages=_languages_for(conn, bid),
                publisher=_publisher_for(conn, bid),
            )
        )
    return books


def load_library(
    metadata_db: Path, snapshot_dir: Path, retrieved_at: str = "1970-01-01"
) -> list[Book]:
    """Snapshot the Calibre DB and return all books — the read-only entry point."""
    with open_snapshot(metadata_db, snapshot_dir) as conn:
        return read_books(conn, retrieved_at=retrieved_at)
