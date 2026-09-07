"""FTS5 search index (issue #104).

The load-bearing tests here are not the ones proving search finds a book. They
are the ones proving that when search *cannot* answer, it says so instead of
returning an empty result set that reads as "you own nothing on this subject".

This repository's documented defect class is plausible output detached from its
real input, so three of these tests exist specifically to swap the input out
from under the index:

* ``test_index_built_from_an_empty_library_is_not_the_same_as_never_built``
* ``test_index_built_from_another_library_is_refused_not_answered``
* ``test_search_after_a_new_refresh_without_reindexing_is_refused``
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from ingest.models import (
    Author,
    Book,
    ReadingState,
    ReadingStatus,
    Source,
    SourceKind,
    ThemeTag,
)
from ingest.search_index import (
    DEFAULT_LIMIT,
    INDEXED_FIELDS,
    _row_for,
    build_index,
    fts5_available,
    index_status,
    search,
    search_states,
    tokenize,
)
from ingest.store import ORIGIN_REAL, Store

NOW = 1_700_000_000


def _source(label: str) -> Source:
    return Source(SourceKind.CALIBRE_TAG, "calibre:local", "2026-09-06", label)


def _state(
    title: str,
    author: str = "A. Writer",
    *,
    series: str | None = None,
    tags: tuple[str, ...] = (),
    publisher: str | None = None,
    languages: tuple[str, ...] = (),
) -> ReadingState:
    book = Book(
        book_id=title.lower().replace(" ", "-"),
        title=title,
        authors=(Author(name=author),),
        series=series,
        theme_tags=tuple(ThemeTag(label=t, source=_source(t)) for t in tags),
        publisher=publisher,
        languages=languages,
    )
    return ReadingState(
        title=title,
        authors=(author,),
        status=ReadingStatus.FINISHED,
        book=book,
    )


LIBRARY = [
    _state("Stone Butch Blues", "Leslie Feinberg", tags=("trans", "memoir")),
    _state("The Argonauts", "Maggie Nelson", tags=("queer", "memoir")),
    _state("Gideon the Ninth", "Tamsyn Muir", series="The Locked Tomb", tags=("speculative",)),
    _state("Nevada", "Imogen Binnie", publisher="Topside Press", languages=("eng",)),
]

OTHER_LIBRARY = [
    _state("Dune", "Frank Herbert", tags=("speculative",)),
    _state("Piranesi", "Susanna Clarke", tags=("speculative",)),
]


@pytest.fixture()
def store(tmp_path: Path) -> Store:
    s = Store(tmp_path / "app-state.sqlite")
    yield s
    s.close()


def _save(store: Store, states: list[ReadingState], refreshed_at: int = NOW) -> None:
    store.save(states, [], refreshed_at=refreshed_at, origin=ORIGIN_REAL)


def _requires_fts5(store: Store) -> None:
    if not fts5_available(store.connection):
        pytest.skip("this SQLite build has no FTS5")


# --- the index answers, and says what matched ------------------------------


def test_finds_a_book_by_title(store: Store) -> None:
    _requires_fts5(store)
    _save(store, LIBRARY)
    build_index(store, LIBRARY, now=NOW)
    outcome = search(store, "Argonauts")
    assert outcome.ok
    assert [hit.title for hit in outcome.hits] == ["The Argonauts"]
    assert outcome.hits[0].matched_field == "title"


@pytest.mark.parametrize(
    ("query", "expected_title", "expected_field"),
    [
        ("Feinberg", "Stone Butch Blues", "authors"),
        ("Locked Tomb", "Gideon the Ninth", "series"),
        ("speculative", "Gideon the Ninth", "tags"),
        ("Topside", "Nevada", "publisher"),
    ],
)
def test_matches_every_indexed_field_and_names_it(
    store: Store, query: str, expected_title: str, expected_field: str
) -> None:
    _requires_fts5(store)
    _save(store, LIBRARY)
    build_index(store, LIBRARY, now=NOW)
    outcome = search(store, query)
    assert outcome.ok
    assert expected_title in [hit.title for hit in outcome.hits]
    hit = next(h for h in outcome.hits if h.title == expected_title)
    assert hit.matched_field == expected_field
    assert hit.matched_field in INDEXED_FIELDS


def test_a_genuine_miss_is_ok_with_zero_hits(store: Store) -> None:
    """The ONE case where zero rows may mean 'nothing matched'."""
    _requires_fts5(store)
    _save(store, LIBRARY)
    build_index(store, LIBRARY, now=NOW)
    outcome = search(store, "zzzznotathing")
    assert outcome.status == "ok"
    assert outcome.hits == ()


def test_a_quote_in_the_query_is_not_a_syntax_error(store: Store) -> None:
    """A stray quote must not become an empty result that means something else."""
    _requires_fts5(store)
    _save(store, LIBRARY)
    build_index(store, LIBRARY, now=NOW)
    outcome = search(store, 'Nevada" OR ')
    assert outcome.status == "ok"


# --- absence is never rendered as a value ----------------------------------


def test_never_built_reports_not_built_not_an_empty_result(store: Store) -> None:
    _requires_fts5(store)
    _save(store, LIBRARY)
    # deliberately no build_index call
    outcome = search(store, "Argonauts")
    assert outcome.status == "not_built"
    assert outcome.hits == ()
    assert "not the same as finding nothing" in outcome.status_detail


def test_never_built_counts_no_documents_rather_than_zero(store: Store) -> None:
    _requires_fts5(store)
    _save(store, LIBRARY)
    status = index_status(store)
    assert status.built is False
    # The distinction the whole module turns on: never counted is not counted-none.
    assert status.documents is None


def test_index_built_from_an_empty_library_is_not_the_same_as_never_built(
    store: Store,
) -> None:
    """A genuinely empty library HAS been measured, and measures zero."""
    _requires_fts5(store)
    _save(store, [])
    build_index(store, [], now=NOW)
    status = index_status(store)
    assert status.built is True
    assert status.documents == 0
    outcome = search(store, "Argonauts")
    # 'ok' with no hits — an empty library really does match nothing.
    assert outcome.status == "ok"


def test_index_built_from_another_library_is_refused_not_answered(store: Store) -> None:
    """The lane's bug class, directly.

    Build the index from one library, then persist a different one. The index
    still holds rows and would happily return them; every one of them would be
    about a book this reader does not have. The revision check must catch it.
    """
    _requires_fts5(store)
    _save(store, OTHER_LIBRARY)
    build_index(store, OTHER_LIBRARY, now=NOW)
    assert search(store, "Dune").ok  # the index answers about ITS library

    _save(store, LIBRARY, refreshed_at=NOW + 100)  # a different library lands
    outcome = search(store, "Dune")
    assert outcome.status == "stale"
    assert outcome.hits == ()
    assert "no longer describes this library" in outcome.status_detail


def test_search_after_a_new_refresh_without_reindexing_is_refused(store: Store) -> None:
    """Same shape, same library: a re-save moves the revision and voids the index."""
    _requires_fts5(store)
    _save(store, LIBRARY)
    build_index(store, LIBRARY, now=NOW)
    assert search(store, "Nevada").ok

    _save(store, LIBRARY, refreshed_at=NOW + 100)
    assert search(store, "Nevada").status == "stale"

    build_index(store, LIBRARY, now=NOW + 100)
    assert search(store, "Nevada").ok


def test_status_records_what_it_was_built_from(store: Store) -> None:
    _requires_fts5(store)
    _save(store, LIBRARY)
    build_index(store, LIBRARY, now=NOW)
    status = index_status(store)
    assert status.built and status.usable and not status.stale
    assert status.documents == len(LIBRARY)
    assert status.built_at == NOW
    assert status.origin == ORIGIN_REAL
    assert status.view_revision == store.view_revision()


# --- the privacy toggle applies at index time ------------------------------


def test_a_hidden_descriptor_is_absent_from_the_index(store: Store) -> None:
    _requires_fts5(store)
    _save(store, LIBRARY)
    build_index(store, LIBRARY, now=NOW, hide_sensitive=True, hidden_descriptors=["trans"])
    # Not merely hidden when rendering: not matchable at all.
    assert search(store, "trans").hits == ()
    assert index_status(store).hide_sensitive is True
    # The book itself is still findable by its title — only the descriptor went.
    assert search(store, "Stone Butch Blues").ok


def test_the_same_descriptor_is_present_when_not_hidden(store: Store) -> None:
    _requires_fts5(store)
    _save(store, LIBRARY)
    build_index(store, LIBRARY, now=NOW, hide_sensitive=False, hidden_descriptors=["trans"])
    outcome = search(store, "trans")
    assert outcome.ok
    assert [hit.title for hit in outcome.hits] == ["Stone Butch Blues"]
    assert index_status(store).hide_sensitive is False


# --- the capability probe actually probes ----------------------------------


def test_fts5_probe_leaves_no_table_behind(store: Store) -> None:
    _requires_fts5(store)
    assert fts5_available(store.connection) is True
    # Probing twice must work: a leaked temp table would make the second fail.
    assert fts5_available(store.connection) is True


class _NoFts5Connection:
    """A connection whose FTS5 module is missing, and nothing else.

    A real one cannot be simulated by patching :class:`sqlite3.Connection` —
    it is an immutable type. This delegates everything to a genuine connection
    except the FTS5 table creation, which fails the way a SQLite build without
    the module fails.
    """

    def __init__(self, real: sqlite3.Connection) -> None:
        self._real = real

    def execute(self, sql: str, *args: object, **kwargs: object) -> object:
        if "fts5" in sql.lower():
            raise sqlite3.OperationalError("no such module: fts5")
        return self._real.execute(sql, *args, **kwargs)

    def __getattr__(self, name: str) -> object:
        return getattr(self._real, name)


def test_fts5_detection_is_false_when_the_module_is_missing(store: Store) -> None:
    """The probe must actually notice, not report availability from a flag."""
    _requires_fts5(store)
    assert fts5_available(_NoFts5Connection(store.connection)) is False  # type: ignore[arg-type]


def test_missing_fts5_is_reported_as_unavailable(store: Store, monkeypatch) -> None:
    _requires_fts5(store)
    _save(store, LIBRARY)
    build_index(store, LIBRARY, now=NOW)
    assert search(store, "Nevada").ok

    monkeypatch.setattr("ingest.search_index.fts5_available", lambda conn: False)
    outcome = search(store, "Nevada")
    assert outcome.status == "unavailable"
    assert outcome.hits == ()
    assert "slower scan" in outcome.status_detail


# --- the fallback returns the SAME rows -------------------------------------
#
# "the same query without FTS5 returns the same rows via the fallback" is issue
# #104's third acceptance criterion, and it was the one left unmet. It was unmet
# because it was false: the fallback was `app.browse.filter_states`, which
# searches title / authors / status / theme-tags by substring, while the index
# covers title / authors / series / tags / publisher / language by token. The
# tests below are the criterion, held over a query set rather than one query.

SCALE_PUBLISHERS = ("Topside Press", "Arsenal Pulp", "Verso Books", "Feminist Press")
SCALE_LANGUAGES = ("eng", "spa", "fra", "deu")
SCALE_TAGS = ("trans", "queer", "memoir", "speculative", "history", "poetry")


def scale_library(count: int) -> list[ReadingState]:
    """A deterministic library big enough for order and ranking to be visible.

    Deliberately not one repeated book: a fixture whose rows are all alike has
    no order to get wrong and no field to confuse, which is the shape of
    fixture that lets a broken search pass. Every field the index covers
    varies, and titles carry diacritics and hyphens so the tokenizer is
    exercised rather than assumed.
    """
    states = []
    for i in range(count):
        marker = "café" if i % 7 == 0 else "co-op"
        states.append(
            _state(
                f"Book {i} {marker} Nº{i}",
                f"Author{i % 311} Surname{i % 53}",
                series=f"Series {i % 97}" if i % 3 == 0 else None,
                tags=(SCALE_TAGS[i % len(SCALE_TAGS)], SCALE_TAGS[(i + 2) % len(SCALE_TAGS)]),
                publisher=SCALE_PUBLISHERS[i % len(SCALE_PUBLISHERS)],
                languages=(SCALE_LANGUAGES[i % len(SCALE_LANGUAGES)],),
            )
        )
    return states


#: Queries chosen to hit every indexed field, plus the cases where a substring
#: test and a tokenizer disagree: a diacritic, a hyphenated word, a fragment of
#: a token, and a phrase.
EQUIVALENCE_QUERIES = (
    "Argonauts",
    "Feinberg",
    "Leslie Feinberg",
    "Locked Tomb",
    "speculative",
    "Topside",
    "eng",
    "memoir",
    "finished",  # a status: `filter_states` matches it, the index does not
    "arg",  # a fragment: substring matches, a token does not
    "Joy",
    "Nevada",
    "the",
    'Nevada" OR ',
    "...",
    "",
    "zzzznotathing",
)


@pytest.mark.parametrize("query", EQUIVALENCE_QUERIES)
def test_fallback_returns_the_same_rows_as_the_index(store: Store, query: str) -> None:
    _requires_fts5(store)
    _save(store, LIBRARY)
    build_index(store, LIBRARY, now=NOW)

    indexed = search(store, query)
    scanned = search_states(LIBRARY, query)

    assert sorted(h.position for h in indexed.hits) == sorted(h.position for h in scanned.hits)
    assert indexed.total == scanned.total
    # The field named must agree too: naming a different field for the same
    # row is a quieter version of the same divergence.
    assert {h.position: h.matched_field for h in indexed.hits} == {
        h.position: h.matched_field for h in scanned.hits
    }


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("Locked Tomb", "series"),
        ("Topside", "publisher"),
        ("eng", "language"),
    ],
)
def test_the_previous_fallback_missed_these_and_would_have_said_so(query: str, field: str) -> None:
    """The regression this pins: a real book reported as no match at all.

    ``app.browse.filter_states`` does not search series, publisher or language.
    On a SQLite build without FTS5 the route ran that filter, got nothing, and
    rendered "No book in your library matched ... Your library is not empty."
    about a book that *was* in the library. This asserts the old behaviour is
    genuinely absent, not merely unused.
    """
    from app.browse import filter_states

    assert filter_states(list(LIBRARY), q=query) == []
    scanned = search_states(LIBRARY, query)
    assert [h.matched_field for h in scanned.hits] == [field]
    assert len(scanned.hits) == 1


def test_the_fallback_says_it_could_not_rank(store: Store) -> None:
    """Without the index there is no BM25, and the reader is told so."""
    _requires_fts5(store)
    _save(store, LIBRARY)
    build_index(store, LIBRARY, now=NOW)
    assert search(store, "memoir").ranked is True
    assert search_states(LIBRARY, "memoir").ranked is False


def test_tokenizer_agrees_with_sqlite(store: Store) -> None:
    """The fallback tokenizes without SQLite, so prove it agrees with SQLite.

    Not over a chosen query set — over the whole corpus, by comparing against
    the terms FTS5 actually stored (``fts5vocab``). This is what caught
    ``str.casefold`` expanding ``ß`` where SQLite does not.
    """
    _requires_fts5(store)
    corpus = scale_library(400) + list(LIBRARY)
    _save(store, corpus)
    build_index(store, corpus, now=NOW)

    conn = store.connection
    # In the main schema, not `temp`: fts5vocab resolves its target table in
    # its own schema, and a temp one cannot see `search_index`.
    conn.execute("CREATE VIRTUAL TABLE vocab_probe USING fts5vocab(search_index, row)")
    try:
        sqlite_terms = {row[0] for row in conn.execute("SELECT term FROM vocab_probe")}
    finally:
        conn.execute("DROP TABLE vocab_probe")

    ours = {
        token
        for state in corpus
        for value in _row_for(state, frozenset())
        for token in tokenize(value)
    }
    assert ours == sqlite_terms


def test_a_wrong_source_changes_the_answer(store: Store) -> None:
    """Identical results from two different libraries would mean neither.

    The index path has this test already; the fallback needs its own, because
    a fallback that ignored ``states`` and returned a constant would pass
    every equivalence test above that happens to expect no rows.
    """
    _requires_fts5(store)
    ours = search_states(LIBRARY, "speculative")
    theirs = search_states(OTHER_LIBRARY, "speculative")
    assert [h.title for h in ours.hits] == ["Gideon the Ninth"]
    assert sorted(h.title for h in theirs.hits) == ["Dune", "Piranesi"]
    assert search_states([], "speculative").hits == ()
    assert search_states([], "speculative").total == 0


# --- at five thousand books -------------------------------------------------
#
# The size the issue names, and the size the linear scan was said to be wrong
# at. What is asserted here is correctness at that size, and that the index is
# actually consulted; a wall-clock p95 gate is deliberately not asserted — see
# `test_the_index_is_used_rather_than_scanned`.

SCALE = 5_000


@pytest.fixture(scope="module")
def scale_states() -> list[ReadingState]:
    return scale_library(SCALE)


@pytest.fixture()
def scale_store(tmp_path: Path, scale_states: list[ReadingState]) -> Store:
    s = Store(tmp_path / "app-state.sqlite")
    if not fts5_available(s.connection):
        s.close()
        pytest.skip("this SQLite build has no FTS5")
    s.save(scale_states, [], refreshed_at=NOW, origin=ORIGIN_REAL)
    build_index(s, scale_states, now=NOW)
    yield s
    s.close()


def test_five_thousand_books_answer_a_title_query_with_the_field_named(
    scale_store: Store, scale_states: list[ReadingState]
) -> None:
    outcome = search(scale_store, "Book 4321")
    assert outcome.ok
    assert [scale_states[h.position].title for h in outcome.hits] == ["Book 4321 co-op Nº4321"]
    assert outcome.hits[0].matched_field == "title"
    assert outcome.total == 1


@pytest.mark.parametrize(
    "query",
    ["Book 4321", "Author17 Surname17", "Verso Books", "Series 42", "spa", "poetry", "café"],
)
def test_the_two_paths_agree_at_five_thousand_books(
    scale_store: Store, scale_states: list[ReadingState], query: str
) -> None:
    indexed = search(scale_store, query, limit=SCALE)
    scanned = search_states(scale_states, query, limit=SCALE)
    assert indexed.total == scanned.total
    assert indexed.total > 0, "a query that matches nothing proves nothing here"
    assert {h.position: h.matched_field for h in indexed.hits} == {
        h.position: h.matched_field for h in scanned.hits
    }


def test_a_truncated_answer_reports_the_untruncated_total(
    scale_store: Store, scale_states: list[ReadingState]
) -> None:
    """A page of results must not be readable as the whole answer."""
    indexed = search(scale_store, "poetry")
    scanned = search_states(scale_states, "poetry")
    assert indexed.total > DEFAULT_LIMIT
    assert len(indexed.hits) == DEFAULT_LIMIT
    assert indexed.truncated and scanned.truncated
    assert indexed.total == scanned.total
    assert f"of {indexed.total} match(es)" in indexed.status_detail


def test_the_index_is_used_rather_than_scanned(scale_store: Store) -> None:
    """The speed claim, asserted structurally rather than by a stopwatch.

    A p95 wall-clock gate measures the machine it runs on: it goes red under
    load that has nothing to do with this code, and green on a fast runner
    whatever the query plan is. What makes the 5,000-book case answerable at
    all is that the query resolves through the FTS index instead of visiting
    every row, so that is what is asserted. The latency itself belongs in the
    perf-load job, on a quiet machine.
    """

    def plan(sql: str, *params: object) -> str:
        rows = scale_store.connection.execute("EXPLAIN QUERY PLAN " + sql, params)
        return " ".join(str(row[3]) for row in rows)

    matched = plan(
        "SELECT rowid FROM search_index WHERE search_index MATCH ? "
        "ORDER BY bm25(search_index), rowid LIMIT 10",
        '"poetry"',
    )
    unmatched = plan("SELECT rowid FROM search_index WHERE title LIKE ? LIMIT 10", "%poetry%")

    # An FTS5 table is always reported as SCAN; what says whether the full-text
    # index was consulted is the constraint suffix on `VIRTUAL TABLE INDEX`.
    # Asserted against the same table queried *without* MATCH, so this cannot
    # pass on a substring that happens to appear in every plan.
    assert "VIRTUAL TABLE INDEX 0:M" in matched, matched
    assert "VIRTUAL TABLE INDEX 0:M" not in unmatched, unmatched


def test_the_scan_visits_every_book_and_still_agrees(
    scale_store: Store, scale_states: list[ReadingState]
) -> None:
    """The fallback is linear — that is why it is the fallback, not the path.

    Asserted so the two are not quietly assumed to be the same mechanism: the
    scan reads all five thousand states to answer, and reaches the same
    answer the index reaches without doing so.
    """
    visited = 0

    class _Counting(list):  # type: ignore[type-arg]
        def __iter__(self):  # type: ignore[no-untyped-def]
            nonlocal visited
            for item in super().__iter__():
                visited += 1
                yield item

    scanned = search_states(_Counting(scale_states), "Series 42", limit=SCALE)
    assert visited == SCALE
    indexed = search(scale_store, "Series 42", limit=SCALE)
    assert {h.position for h in scanned.hits} == {h.position for h in indexed.hits}
