"""A fully-offline demo world: real Calibre + KOReader SQLite DBs, built on disk.

So the read-only readers are exercised against *genuine* SQLite (not mocks), this
module writes a Calibre ``metadata.db`` and a KOReader ``statistics.sqlite`` with
the real table shapes, then reads them back through :mod:`ingest.calibre` /
:mod:`ingest.koreader`. The library is grounded in the user's stated canon —
Plett, Peters, Thom, Butler, Atwood — so demo mode, the eval, and tests all run
with no network and no real library.

The candidate catalog and curated lists for the recommender live here too, with
sourced theme tags from OpenLibrary subjects and curated community lists.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ingest.koreader import load_stats
from ingest.kosync import FixtureKosync
from ingest.models import (
    Book,
    DeviceProgress,
    ReadingState,
    Source,
    SourceKind,
    ThemeTag,
)
from ingest.unify import unify

DEMO_USER = "demo"
_FETCHED = "2026-06-05"


@dataclass(frozen=True)
class _OwnedBook:
    title: str
    author: str
    author_sort: str
    tags: tuple[str, ...]
    series: str | None
    total_pages: int
    pages_read: int
    read_time_seconds: int
    last_open: int
    sessions: int
    md5: str
    device: str
    device_percentage: float  # cross-device progress, 0..1


# The user's real canon, as owned + (mostly) finished books. -------------------
_OWNED: tuple[_OwnedBook, ...] = (
    _OwnedBook(
        "A Safe Girl to Love",
        "Casey Plett",
        "Plett, Casey",
        ("trans", "short stories", "literary", "queer"),
        None,
        220,
        220,
        41000,
        1_717_000_000,
        7,
        "md5-plett-asgtl",
        "Kobo",
        1.0,
    ),
    _OwnedBook(
        "Detransition, Baby",
        "Torrey Peters",
        "Peters, Torrey",
        ("trans", "literary", "queer"),
        None,
        352,
        352,
        60000,
        1_716_000_000,
        9,
        "md5-peters-db",
        "Kobo",
        1.0,
    ),
    _OwnedBook(
        "Fierce Femmes and Notorious Liars",
        "Kai Cheng Thom",
        "Thom, Kai Cheng",
        ("trans", "speculative", "queer", "fabulist"),
        None,
        240,
        240,
        38000,
        1_715_000_000,
        6,
        "md5-thom-ffnl",
        "Readest",
        1.0,
    ),
    _OwnedBook(
        "Kindred",
        "Octavia E. Butler",
        "Butler, Octavia E.",
        ("speculative", "science fiction", "time travel"),
        None,
        287,
        287,
        52000,
        1_714_000_000,
        8,
        "md5-butler-kindred",
        "Kobo",
        1.0,
    ),
    _OwnedBook(
        "Parable of the Sower",
        "Octavia E. Butler",
        "Butler, Octavia E.",
        ("speculative", "science fiction", "dystopia"),
        "Earthseed",
        345,
        345,
        58000,
        1_713_000_000,
        10,
        "md5-butler-sower",
        "Kobo",
        1.0,
    ),
    _OwnedBook(
        "The Handmaid's Tale",
        "Margaret Atwood",
        "Atwood, Margaret",
        ("speculative", "dystopia", "feminist"),
        None,
        311,
        311,
        50000,
        1_712_000_000,
        9,
        "md5-atwood-hmt",
        "Calibre-Web",
        1.0,
    ),
    _OwnedBook(
        "Oryx and Crake",
        "Margaret Atwood",
        "Atwood, Margaret",
        ("speculative", "science fiction", "dystopia"),
        "MaddAddam",
        376,
        376,
        61000,
        1_711_000_000,
        11,
        "md5-atwood-oc",
        "Kobo",
        1.0,
    ),
    # Currently reading — cross-device, partway through.
    _OwnedBook(
        "Stone Butch Blues",
        "Leslie Feinberg",
        "Feinberg, Leslie",
        ("trans", "queer", "literary", "historical"),
        None,
        320,
        150,
        21000,
        1_718_200_000,
        5,
        "md5-feinberg-sbb",
        "Kobo",
        0.47,
    ),
)


def _connect_new(path: Path) -> sqlite3.Connection:
    if path.exists():
        path.unlink()
    return sqlite3.connect(path)


def build_calibre_db(path: Path) -> Path:
    """Write a Calibre-shaped ``metadata.db`` from the owned canon."""
    conn = _connect_new(path)
    try:
        conn.executescript(
            """
            CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT,
                sort TEXT, series_index REAL, pubdate TEXT);
            CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT, sort TEXT);
            CREATE TABLE books_authors_link (id INTEGER PRIMARY KEY, book INTEGER, author INTEGER);
            CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE books_tags_link (id INTEGER PRIMARY KEY, book INTEGER, tag INTEGER);
            CREATE TABLE series (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE books_series_link (id INTEGER PRIMARY KEY, book INTEGER, series INTEGER);
            CREATE TABLE identifiers (id INTEGER PRIMARY KEY, book INTEGER, type TEXT, val TEXT);
            """
        )
        author_ids: dict[str, int] = {}
        tag_ids: dict[str, int] = {}
        series_ids: dict[str, int] = {}
        for bid, ob in enumerate(_OWNED, start=1):
            conn.execute(
                "INSERT INTO books (id, title, sort, series_index, pubdate) VALUES (?,?,?,?,?)",
                (bid, ob.title, ob.title, 1.0 if ob.series else None, None),
            )
            if ob.author not in author_ids:
                author_ids[ob.author] = len(author_ids) + 1
                conn.execute(
                    "INSERT INTO authors (id, name, sort) VALUES (?,?,?)",
                    (author_ids[ob.author], ob.author, ob.author_sort),
                )
            conn.execute(
                "INSERT INTO books_authors_link (book, author) VALUES (?,?)",
                (bid, author_ids[ob.author]),
            )
            for tag in ob.tags:
                if tag not in tag_ids:
                    tag_ids[tag] = len(tag_ids) + 1
                    conn.execute("INSERT INTO tags (id, name) VALUES (?,?)", (tag_ids[tag], tag))
                conn.execute(
                    "INSERT INTO books_tags_link (book, tag) VALUES (?,?)", (bid, tag_ids[tag])
                )
            if ob.series:
                if ob.series not in series_ids:
                    series_ids[ob.series] = len(series_ids) + 1
                    conn.execute(
                        "INSERT INTO series (id, name) VALUES (?,?)",
                        (series_ids[ob.series], ob.series),
                    )
                conn.execute(
                    "INSERT INTO books_series_link (book, series) VALUES (?,?)",
                    (bid, series_ids[ob.series]),
                )
        conn.commit()
    finally:
        conn.close()
    return path


def build_koreader_db(path: Path) -> Path:
    """Write a KOReader-shaped ``statistics.sqlite`` from the owned canon."""
    conn = _connect_new(path)
    try:
        conn.executescript(
            """
            CREATE TABLE book (id INTEGER PRIMARY KEY, title TEXT, authors TEXT,
                notes INTEGER, last_open INTEGER, highlights INTEGER, pages INTEGER,
                series TEXT, language TEXT, md5 TEXT,
                total_read_time INTEGER, total_read_pages INTEGER);
            CREATE TABLE page_stat_data (id_book INTEGER, page INTEGER,
                start_time INTEGER, duration INTEGER, total_pages INTEGER);
            """
        )
        for bid, ob in enumerate(_OWNED, start=1):
            conn.execute(
                """INSERT INTO book (id, title, authors, notes, last_open, highlights,
                   pages, series, language, md5, total_read_time, total_read_pages)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    bid,
                    ob.title,
                    ob.author,
                    0,
                    ob.last_open,
                    0,
                    ob.total_pages,
                    ob.series or "",
                    "en",
                    ob.md5,
                    ob.read_time_seconds,
                    ob.pages_read,
                ),
            )
            # Synthesize page views forming `sessions` clusters, so session
            # reconstruction in ingest.koreader has real data to group.
            per = max(1, ob.pages_read // ob.sessions)
            page = 1
            base = ob.last_open - ob.read_time_seconds
            for s in range(ob.sessions):
                session_start = base + s * (ob.read_time_seconds // ob.sessions + 7200)
                for j in range(per):
                    conn.execute(
                        """INSERT INTO page_stat_data
                           (id_book, page, start_time, duration, total_pages)
                           VALUES (?,?,?,?,?)""",
                        (bid, page, session_start + j * 60, 60, ob.total_pages),
                    )
                    page += 1
        conn.commit()
    finally:
        conn.close()
    return path


def build_demo_dbs(directory: Path) -> tuple[Path, Path]:
    """Build both demo DBs in ``directory`` and return (metadata_db, statistics_db)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    return (
        build_calibre_db(directory / "metadata.db"),
        build_koreader_db(directory / "statistics.sqlite"),
    )


def demo_kosync() -> FixtureKosync:
    """Cross-device progress keyed by KOReader md5 (matches the stats' keys)."""
    progress = {
        ob.md5: DeviceProgress(
            document=ob.md5,
            percentage=ob.device_percentage,
            device=ob.device,
            timestamp=ob.last_open,
        )
        for ob in _OWNED
    }
    return FixtureKosync(progress)


def demo_reading_states(directory: Path) -> list[ReadingState]:
    """Build the demo DBs, read them read-only, and unify into reading state.

    This walks the *entire* real ingest path — snapshot, read-only Calibre +
    KOReader parse, kosync progress, unify — so demo mode proves the pipeline.
    """
    from ingest.calibre import load_library

    metadata_db, statistics_db = build_demo_dbs(directory)
    snap = directory / "snapshots"
    books = load_library(metadata_db, snap, retrieved_at=_FETCHED)
    stats = load_stats(statistics_db, snap)
    return unify(books, stats, demo_kosync())


# --- Recommender fixtures: a candidate catalog + curated lists ----------------


def _src(kind: SourceKind, citation: str, detail: str = "") -> Source:
    return Source(kind=kind, citation=citation, retrieved_at=_FETCHED, detail=detail)


def _ol_tags(*labels: str) -> tuple[ThemeTag, ...]:
    return tuple(
        ThemeTag(
            label=lbl,
            source=_src(
                SourceKind.OPENLIBRARY_SUBJECT, f"https://openlibrary.org/subjects/{lbl}", lbl
            ),
        )
        for lbl in labels
    )


def _list_tags(list_name: str, *labels: str) -> tuple[ThemeTag, ...]:
    return tuple(
        ThemeTag(
            label=lbl,
            source=_src(SourceKind.CURATED_LIST, f"curated-list:{list_name}", lbl),
        )
        for lbl in labels
    )


@dataclass(frozen=True)
class Candidate:
    """A not-yet-owned book the recommender may surface, with a popularity proxy."""

    book: Book
    readers: int  # popularity proxy (the baseline ranks by this), e.g. "want to read"
    on_canon: bool  # eval ground-truth: is this a genuine canon-fit discovery?


def _candidate(
    book_id: str,
    title: str,
    author: str,
    tags: tuple[ThemeTag, ...],
    readers: int,
    on_canon: bool,
    series: str | None = None,
) -> Candidate:
    from ingest.models import Author as _Author

    return Candidate(
        book=Book(
            book_id=book_id,
            title=title,
            authors=(_Author(name=author),),
            series=series,
            theme_tags=tags,
            identifiers={},
        ),
        readers=readers,
        on_canon=on_canon,
    )


#: Candidates: on-canon discoveries (modest popularity) + popular off-theme
#: distractors. A popularity baseline ranks the distractors first and misses the
#: discoveries; the content recommender recovers them. This is the eval's premise.
_CANDIDATES: tuple[Candidate, ...] = (
    _candidate(
        "ol:nevada",
        "Nevada",
        "Imogen Binnie",
        _list_tags("trans-spec-fic-canon", "trans", "literary", "queer"),
        90_000,
        True,
    ),
    _candidate(
        "ol:confessions-fox",
        "Confessions of the Fox",
        "Jordy Rosenberg",
        _ol_tags("trans", "speculative", "queer", "historical"),
        60_000,
        True,
    ),
    _candidate(
        "ol:unkindness-ghosts",
        "An Unkindness of Ghosts",
        "Rivers Solomon",
        _ol_tags("speculative", "science fiction", "queer"),
        110_000,
        True,
    ),
    _candidate(
        "ol:fifth-season",
        "The Fifth Season",
        "N. K. Jemisin",
        _ol_tags("speculative", "science fiction", "dystopia"),
        400_000,
        True,
    ),
    _candidate(
        "ol:dawn-butler",
        "Dawn",
        "Octavia E. Butler",
        _ol_tags("speculative", "science fiction"),
        150_000,
        True,
    ),
    # Popular off-theme distractors (no overlap with the canon's theme vocab).
    _candidate(
        "ol:thriller",
        "The Airport Thriller",
        "A. Bestseller",
        _ol_tags("thriller", "bestseller", "crime"),
        5_000_000,
        False,
    ),
    _candidate(
        "ol:memoir",
        "Celebrity: A Memoir",
        "V. Famous",
        _ol_tags("memoir", "bestseller", "celebrity"),
        4_200_000,
        False,
    ),
    _candidate(
        "ol:fantasy-doorstop",
        "The Doorstop Saga, Book 9",
        "G. Epic",
        _ol_tags("epic fantasy", "bestseller", "dragons"),
        3_800_000,
        False,
    ),
)


def demo_candidates() -> tuple[Candidate, ...]:
    return _CANDIDATES
