"""FTS5 search over the reader's own library (issue #104).

``app/browse.py::filter_states`` linearly scans every state per request. That is
fine at a hundred books and wrong at five thousand. This builds an SQLite FTS5
index over the facts already ingested — title, authors, series, sourced theme
tags, publisher and language — inside the same app-state database, rebuilt at
``stacks refresh``.

Everything here is local: the index lives in the reader's own SQLite file, the
ranking is FTS5's own BM25 over the reader's own data, and no source is
weighted, so a small-press title with a matching tag ranks like any other.

The failure this module is shaped around
----------------------------------------

An empty, missing or stale index returns **no rows**, and "no rows" is
indistinguishable from "no matches" — to the reader, and to a test. A reader
who searches their own library and sees nothing concludes they own nothing on
the subject. That is this project's documented defect class (plausible output
detached from real input) in the place it hides best, so *every* way of getting
zero rows is a distinct, named outcome here rather than an empty list:

``ok``
    The index was built from the current states and the query genuinely
    matched this many rows. Zero hits means zero matches, and only this
    outcome may say so.
``not_built``
    No index has ever been written. ``documents`` is ``None``, not ``0`` —
    "never counted" is not "counted none".
``stale``
    An index exists but was built from a *different* set of states: the store's
    view revision has moved past the one recorded at build time. Its rowids
    point into a list that no longer exists, so the rows it would return are
    not about the books the reader has. Refusing is the only honest answer;
    returning them is exactly the "report not derived from the data it claims"
    failure.
``unavailable``
    This SQLite build has no FTS5. The caller falls back to
    :func:`search_states`, which is slower and returns the same rows. It is
    in *this* module, not ``app.browse``, because "the same rows" only holds
    if both paths are derived from one definition of what is searched:
    ``app.browse.filter_states`` covers a different set of fields, and using
    it here meant a query for a series, publisher or language found books
    through the index and nothing without it.

:class:`SearchOutcome` carries the status, so a surface can say which of these
happened instead of rendering four different situations as one empty table.
"""

from __future__ import annotations

import json
import sqlite3
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Optional

from ingest.models import ReadingState
from ingest.store import Store

#: How many hits a search returns at most. Both paths apply it, and both
#: report the untruncated total, so "200 results" is never mistaken for "200
#: books match".
DEFAULT_LIMIT = 200

#: Rows of the FTS table, in the order they are inserted. ``matched_field``
#: reports which of these the query hit, so a result can say *why* it matched.
INDEXED_FIELDS: tuple[str, ...] = (
    "title",
    "authors",
    "series",
    "tags",
    "publisher",
    "language",
)

_TABLE = "search_index"
_META_KEY = "search_index_meta"


@dataclass(frozen=True)
class IndexStatus:
    """What the index is, and whether anything may be believed about it."""

    #: FTS5 is compiled into this SQLite build.
    available: bool
    #: An index has been written at least once.
    built: bool
    #: Documents indexed, or ``None`` when never built. Never defaulted to 0 —
    #: a library that was never indexed has not been measured as empty.
    documents: Optional[int]
    #: Epoch seconds the index was built, or ``None``.
    built_at: Optional[int]
    #: The store view revision the index was built from, or ``None``.
    view_revision: Optional[int]
    #: Which world produced the indexed states (``real``/``demo``), or ``None``.
    origin: Optional[str]
    #: Whether sensitive lens descriptors were excluded at build time.
    hide_sensitive: bool
    #: The index was built from states the store has since replaced.
    stale: bool

    @property
    def usable(self) -> bool:
        return self.available and self.built and not self.stale


@dataclass(frozen=True)
class SearchHit:
    """One matching book, with the field that matched it."""

    #: Position of the state in :meth:`Store.load_states` order at build time.
    position: int
    title: str
    #: The authors exactly as indexed — one string, names space-joined. It is
    #: not re-split into names: the index stores the joined text, so splitting
    #: it back on spaces turns "Leslie Feinberg" into two authors, and the
    #: index-free path would then have to reproduce that error to agree.
    authors: str
    matched_field: str


@dataclass(frozen=True)
class SearchOutcome:
    """The result of a search, including the reason there are no hits."""

    #: ``ok`` | ``not_built`` | ``stale`` | ``unavailable``
    status: str
    hits: tuple[SearchHit, ...]
    status_detail: str
    #: Books that matched, before ``limit`` was applied. ``None`` when no
    #: search ran (``not_built``, ``stale``) — never 0, for the same reason
    #: :attr:`IndexStatus.documents` is not: nothing was counted.
    total: Optional[int] = None
    #: Whether ranking by relevance was available. The index ranks by BM25;
    #: without it the fallback can only return library order, and a reader
    #: told "these are your results" deserves to know they are not ranked.
    ranked: bool = True

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def truncated(self) -> bool:
        """More books matched than were returned."""
        return self.total is not None and self.total > len(self.hits)


def fts5_available(conn: sqlite3.Connection) -> bool:
    """Whether this SQLite build can create an FTS5 table.

    Probed by actually creating one in a temporary table rather than by
    reading ``compile_options``: the option list has been wrong on rebuilt
    system libraries, and a capability check that does not exercise the
    capability is the kind of gate that passes without testing anything.
    """
    try:
        conn.execute("CREATE VIRTUAL TABLE temp.__fts5_probe USING fts5(x)")
    except sqlite3.Error:
        return False
    conn.execute("DROP TABLE temp.__fts5_probe")
    return True


def _tags_for(state: ReadingState, hidden: frozenset[str]) -> str:
    """Sourced theme tags as one indexable string, minus any hidden descriptor.

    The privacy toggle applies at *index* time, not at query time: a descriptor
    excluded only when rendering is still on disk and still matchable, which
    would let a query confirm its presence. ``hidden`` is compared on the tag's
    ``normalized`` form, the same key ``merge_tags`` de-duplicates on.
    """
    labels = [tag.label for tag in state.theme_tags if tag.normalized not in hidden]
    return " ".join(labels)


def _row_for(state: ReadingState, hidden: frozenset[str]) -> tuple[str, ...]:
    book = state.book
    return (
        state.title,
        " ".join(state.authors),
        (book.series if book and book.series else ""),
        _tags_for(state, hidden),
        (book.publisher if book and book.publisher else ""),
        (" ".join(book.languages) if book and book.languages else ""),
    )


def hidden_descriptors_for(config: object) -> frozenset[str]:
    """The descriptors the privacy toggle excludes, resolved once for both paths.

    ``stacks refresh`` excludes these at index time and the index-free
    fallback has to exclude the same ones at query time, or the toggle would
    hide a descriptor from one path and not the other. Resolving it in one
    place is what stops those two from drifting apart.

    Imported locally, as ``ingest.refresh`` already does, so the ingest layer
    does not take a module-level dependency on the app layer.
    """
    if not getattr(config, "hide_sensitive_descriptors", False):
        return frozenset()
    from app.diversity import load_lens_config, resolve_sensitive_descriptors

    lenses = load_lens_config(config.lens_config)  # type: ignore[attr-defined]
    return resolve_sensitive_descriptors(
        lenses.dimensions, sensitive_lens_names=lenses.sensitive_lens_names
    )


def tokenize(text: str) -> tuple[str, ...]:
    """Split ``text`` the way FTS5's default ``unicode61`` tokenizer does.

    The fallback in :func:`search_states` runs precisely when FTS5 is *not*
    available, so it cannot ask SQLite to tokenize for it — it has to agree
    with a tokenizer it cannot call. Three rules reproduce ``unicode61`` with
    its default ``remove_diacritics 1``:

    1. decompose and drop combining marks, so ``Café`` and ``Cafe`` are one
       token (SQLite folds these together and a substring match does not);
    2. split on every character that is not alphanumeric, so ``co-operate``
       and ``l'étranger`` are two tokens each;
    3. lower-case with :meth:`str.lower`, **not** :meth:`str.casefold` —
       casefold expands ``ß`` to ``ss`` and SQLite does not, which was the one
       divergence found when this was checked against ``fts5vocab``.

    That check is a test, not a claim: ``test_tokenizer_agrees_with_sqlite``
    asserts this function's token set equals the terms SQLite actually stored
    for the same corpus.
    """
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    tokens: list[str] = []
    current: list[str] = []
    for ch in stripped:
        if ch.isalnum():
            current.append(ch)
        elif current:
            tokens.append("".join(current).lower())
            current = []
    if current:
        tokens.append("".join(current).lower())
    return tuple(tokens)


def _contains_phrase(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    """Whether ``needle`` appears as a contiguous run of tokens in ``haystack``.

    This is what ``MATCH '"a b"'`` means: an FTS5 phrase matches a column when
    the query's tokens appear in it consecutively. A phrase with no tokens
    (a query of only punctuation) matches nothing, which is also what SQLite
    does.
    """
    if not needle:
        return False
    span = len(needle)
    return any(haystack[i : i + span] == needle for i in range(len(haystack) - span + 1))


def build_index(
    store: Store,
    states: Sequence[ReadingState],
    *,
    now: int,
    hide_sensitive: bool = False,
    hidden_descriptors: Iterable[str] = (),
) -> IndexStatus:
    """(Re)build the index from ``states`` and record what it was built from.

    The meta row is written in the SAME transaction as the rows, so an index
    can never be present while claiming a build that did not happen, nor claim
    a view revision it was not built at. Recording the revision is what makes
    :func:`search` able to notice that the states moved underneath it.
    """
    conn = store.connection
    if not fts5_available(conn):
        return index_status(store)

    hidden = frozenset(d.strip().lower() for d in hidden_descriptors if d.strip())
    rows = [_row_for(state, hidden if hide_sensitive else frozenset()) for state in states]

    with conn:
        conn.execute(f"DROP TABLE IF EXISTS {_TABLE}")  # noqa: S608 - see below
        conn.execute(f"CREATE VIRTUAL TABLE {_TABLE} USING fts5({', '.join(INDEXED_FIELDS)})")
        # On the S608 suppressions below: the only interpolated values are `_TABLE` and
        # `INDEXED_FIELDS`, both module-level literals in this file. SQLite
        # cannot parameterise an identifier, so a table and column list must be
        # interpolated. Every reader-supplied value is bound (`?`), including
        # the query text in `search` below.
        insert_sql = f"INSERT INTO {_TABLE} (rowid, {', '.join(INDEXED_FIELDS)}) VALUES (?, {', '.join('?' for _ in INDEXED_FIELDS)})"  # noqa: S608,E501 - identifiers are module literals; values are bound
        conn.executemany(
            insert_sql,
            [(position, *row) for position, row in enumerate(rows)],
        )
        conn.execute(
            "INSERT INTO app_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (
                _META_KEY,
                json.dumps(
                    {
                        "built_at": int(now),
                        "documents": len(rows),
                        "view_revision": store.view_revision(),
                        "origin": store.state_origin(),
                        "hide_sensitive": bool(hide_sensitive),
                    }
                ),
            ),
        )
    return index_status(store)


def index_status(store: Store) -> IndexStatus:
    """Report the index without trusting it."""
    conn = store.connection
    available = fts5_available(conn)
    row = conn.execute("SELECT value FROM app_state WHERE key = ?", (_META_KEY,)).fetchone()
    raw = json.loads(row[0]) if row else None
    if not isinstance(raw, dict):
        return IndexStatus(
            available=available,
            built=False,
            # Never 0: an index that was never built has not counted anything.
            documents=None,
            built_at=None,
            view_revision=None,
            origin=None,
            hide_sensitive=False,
            stale=False,
        )
    recorded = raw.get("view_revision")
    recorded_revision = int(recorded) if isinstance(recorded, int) else None
    return IndexStatus(
        available=available,
        built=True,
        documents=int(raw.get("documents", 0)),
        built_at=int(raw["built_at"]) if isinstance(raw.get("built_at"), int) else None,
        view_revision=recorded_revision,
        origin=raw.get("origin") if isinstance(raw.get("origin"), str) else None,
        hide_sensitive=bool(raw.get("hide_sensitive", False)),
        # An index built at a revision the store has moved past describes books
        # the reader may no longer have, in an order that no longer applies.
        stale=recorded_revision is None or recorded_revision != store.view_revision(),
    )


def _escape(query: str) -> str:
    """Quote the query as one FTS5 phrase.

    Reader input is never interpolated as FTS5 syntax: a stray ``"`` or a bare
    ``NEAR`` would otherwise be a query error the caller would see as "no
    results" — an empty table that means something else again.
    """
    return '"' + query.replace('"', '""') + '"'


def search(store: Store, query: str, *, limit: int = DEFAULT_LIMIT) -> SearchOutcome:
    """Search the index, or say precisely why the answer is not a result set."""
    text = query.strip()
    status = index_status(store)
    if not status.available:
        return SearchOutcome(
            status="unavailable",
            hits=(),
            status_detail=("this SQLite build has no FTS5, so the slower scan answered instead"),
        )
    if not status.built:
        return SearchOutcome(
            status="not_built",
            hits=(),
            status_detail=(
                "no search index has been built yet — run `stacks refresh`. "
                "This is not the same as finding nothing."
            ),
        )
    if status.stale:
        return SearchOutcome(
            status="stale",
            hits=(),
            status_detail=(
                "the search index was built from an earlier refresh and no "
                "longer describes this library — run `stacks refresh`. "
                "Returning its rows would report books you may not have."
            ),
        )
    if not text:
        return SearchOutcome(status="ok", hits=(), status_detail="empty query", total=0)

    conn = store.connection
    columns = ", ".join(INDEXED_FIELDS)
    try:
        select_sql = f"SELECT rowid, {columns} FROM {_TABLE} WHERE {_TABLE} MATCH ? ORDER BY bm25({_TABLE}), rowid LIMIT ?"  # noqa: S608,E501 - identifiers are module literals; the query text is bound
        rows = conn.execute(select_sql, (_escape(text), int(limit))).fetchall()
        # Counted separately rather than inferred from `len(rows)`: with a
        # LIMIT applied, `len(rows)` is the size of the page, and reporting a
        # page size as a match count is the same "absence rendered as a value"
        # move in its other direction — a truncated answer read as a whole one.
        count_sql = f"SELECT count(*) FROM {_TABLE} WHERE {_TABLE} MATCH ?"  # noqa: S608 - identifier is a module literal; the query text is bound
        total = int(conn.execute(count_sql, (_escape(text),)).fetchone()[0])
    except sqlite3.OperationalError as exc:  # pragma: no cover - defensive
        return SearchOutcome(
            status="unavailable",
            hits=(),
            status_detail=f"the index could not be queried ({exc})",
        )

    needle_tokens = tokenize(text)
    hits = []
    for row in rows:
        position = int(row[0])
        # strict=True: the SELECT names exactly INDEXED_FIELDS after rowid, so a
        # length mismatch means the table and this module have diverged.
        values = dict(zip(INDEXED_FIELDS, row[1:], strict=True))
        hits.append(
            SearchHit(
                position=position,
                title=str(values["title"]),
                authors=str(values["authors"]),
                # FTS5 matched on a token this tokenizer cannot attribute to a
                # column. Saying so beats naming a field that did not match.
                matched_field=_matched_field(values, needle_tokens) or "another indexed field",
            )
        )
    return SearchOutcome(
        status="ok",
        hits=tuple(hits),
        status_detail=_detail(len(hits), total, "the search index"),
        total=total,
        ranked=True,
    )


def _matched_field(values: Mapping[str, object], needle_tokens: tuple[str, ...]) -> Optional[str]:
    """Which indexed field the query hit, or ``None`` if none of them did.

    Tokenized rather than substring-tested. A substring test disagrees with
    FTS5 on exactly the cases the tokenizer exists for — ``Café`` matched by
    ``cafe``, ``co-operate`` matched by ``operate`` — and would then fail to
    name a field that plainly did match.

    The two callers read ``None`` differently, and correctly: for the indexed
    path FTS5 has already decided the row matches, so ``None`` means "matched
    on something this tokenizer cannot attribute"; for the index-free path
    this function *is* the match test, so ``None`` means the row does not
    match at all.
    """
    for field in INDEXED_FIELDS:
        if _contains_phrase(tokenize(str(values.get(field, ""))), needle_tokens):
            return field
    return None


def _detail(shown: int, total: int, source: str) -> str:
    if total > shown:
        return f"showing the first {shown} of {total} match(es) from {source}"
    return f"{total} match(es) from {source}"


def search_states(
    states: Sequence[ReadingState],
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    hide_sensitive: bool = False,
    hidden_descriptors: Iterable[str] = (),
) -> SearchOutcome:
    """Answer the same query as :func:`search`, without an index.

    This exists because "the same query without FTS5 returns the same rows"
    is a promise, and the two paths have to be *derived from one definition*
    to keep it. Both read :data:`INDEXED_FIELDS` through :func:`_row_for`, so
    a field added to the index is searched here on the same commit; both
    tokenize with :func:`tokenize`; both apply the privacy exclusion by the
    same rule.

    Before this existed the fallback was ``app.browse.filter_states``, which
    searches a *different* set of fields — title, authors, status and theme
    tags — and by substring rather than by token. Measured on the four-book
    test library, five queries in twelve disagreed, in both directions: a
    query for a publisher or a series or a language found books through the
    index and **nothing** through the fallback, so a reader on a SQLite build
    without FTS5 was told no book in their library matched, about a book that
    was in their library.

    One difference remains, and it is named rather than hidden: without the
    index there is no BM25, so hits come back in library order and
    :attr:`SearchOutcome.ranked` is ``False``.
    """
    text = query.strip()
    if not text:
        return SearchOutcome(
            status="unavailable",
            hits=(),
            status_detail="empty query",
            total=0,
            ranked=False,
        )

    hidden = frozenset(d.strip().lower() for d in hidden_descriptors if d.strip())
    needle_tokens = tokenize(text)
    hits: list[SearchHit] = []
    total = 0
    for position, state in enumerate(states):
        row = _row_for(state, hidden if hide_sensitive else frozenset())
        values = dict(zip(INDEXED_FIELDS, row, strict=True))
        matched = _matched_field(values, needle_tokens)
        if matched is None:
            continue
        total += 1
        if len(hits) < limit:
            hits.append(
                SearchHit(
                    position=position,
                    title=str(values["title"]),
                    authors=str(values["authors"]),
                    matched_field=matched,
                )
            )
    return SearchOutcome(
        status="unavailable",
        hits=tuple(hits),
        status_detail=_detail(len(hits), total, "a scan of your library (no index)"),
        total=total,
        ranked=False,
    )
