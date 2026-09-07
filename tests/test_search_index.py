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
    INDEXED_FIELDS,
    build_index,
    fts5_available,
    index_status,
    search,
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
