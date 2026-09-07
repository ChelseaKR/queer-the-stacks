"""``GET /search`` (issue #104).

``tests/test_search_index.py`` covers the index. This covers the three things
only the wired route can be wrong about: that it is auth-gated like every other
private surface, that it renders the reader's actual books, and that when the
index cannot answer it says so on the page rather than rendering an empty
library that reads as "you own nothing on this subject".
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from app.auth import sign_session
from ingest.store import Store


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    monkeypatch.setenv("STACKS_DEMO", "1")
    monkeypatch.setenv("STACKS_DATA_DIR", str(tmp_path))
    from tests.conftest import seed_store_from_env

    seed_store_from_env()
    from app.server import create_app

    client = TestClient(create_app(), base_url="https://testserver")
    client.cookies.set("stacks_session", sign_session(int(time.time()), {"STACKS_DEMO": "1"}))
    return client


def _store_path(tmp_path: Path) -> Path:
    monkey_config = tmp_path / "app-state.sqlite"
    if monkey_config.exists():
        return monkey_config
    matches = sorted(tmp_path.rglob("app-state.sqlite"))
    assert matches, f"no app-state store under {tmp_path}"
    return matches[0]


def test_search_requires_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    client = _client(tmp_path, monkeypatch)
    client.cookies.clear()
    assert client.get("/search?q=anything").status_code == 401


def test_search_returns_a_book_from_the_readers_own_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    client = _client(tmp_path, monkeypatch)

    store = Store(_store_path(tmp_path))
    try:
        titles = [state.title for state in store.load_states()]
    finally:
        store.close()
    assert titles, "the demo refresh persisted no states"

    target = titles[0]
    body = client.get("/search", params={"q": target}).text
    assert target in body
    # A result page that shows every book is not a search result.
    shown = [t for t in titles if t in body]
    assert len(shown) < len(titles) or len(titles) == 1


def test_a_stale_index_says_so_instead_of_rendering_an_empty_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lane's bug class at the route.

    Move the store's view revision past the index's without rebuilding. The
    rows in the index now describe a library that is not this one. The page
    must say that, not show an empty shelf.
    """
    pytest.importorskip("fastapi")
    client = _client(tmp_path, monkeypatch)

    store = Store(_store_path(tmp_path))
    try:
        states = store.load_states()
        title = states[0].title
        assert title in client.get("/search", params={"q": title}).text
        # A fresh save advances the view revision; the index is not rebuilt.
        store.save(states, [], refreshed_at=int(time.time()))
    finally:
        store.close()

    body = client.get("/search", params={"q": title}).text
    assert "Search did not run" in body
    assert "no longer describes this library" in body
    # The library table must NOT be emptied: "Your library is empty." would
    # turn a broken index into a false statement about what the reader owns.
    assert "Your library is empty." not in body
    assert title in body


def test_an_empty_query_is_not_treated_as_a_failed_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    client = _client(tmp_path, monkeypatch)
    response = client.get("/search", params={"q": "   "})
    assert response.status_code == 200
    assert "no longer describes this library" not in response.text


def test_the_query_string_never_reaches_a_log_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The issue requires it; `app/logging_config.py` already reads path only."""
    pytest.importorskip("fastapi")
    client = _client(tmp_path, monkeypatch)
    secret = "averydistinctivesearchterm"
    # Scoped to the application's own request logger. The TestClient's httpx
    # logger echoes the full URL it was handed, which says nothing about what
    # this app writes; asserting over every logger in the process would make
    # this test about the harness.
    with caplog.at_level("DEBUG", logger="queer_the_stacks.request"):
        client.get("/search", params={"q": secret})
    app_records = [r for r in caplog.records if r.name.startswith("queer_the_stacks")]
    assert app_records, "the app logged nothing, so this proved nothing"
    assert all(secret not in r.getMessage() for r in app_records)
    assert all(secret not in str(getattr(r, "path", "")) for r in app_records)


def test_without_fts5_the_route_still_finds_the_book_and_says_it_is_unranked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fallback answers the same query, over the same fields.

    Until this landed the fallback was ``app.browse.filter_states``, which
    does not search series, publisher or language. A reader on a SQLite build
    without FTS5 who searched for a publisher got zero rows and was told no
    book in their library matched — about a book that was in their library.
    """
    pytest.importorskip("fastapi")
    client = _client(tmp_path, monkeypatch)

    store = Store(_store_path(tmp_path))
    try:
        states = store.load_states()
    finally:
        store.close()
    in_a_series = [s for s in states if s.book and s.book.series]
    assert in_a_series, "the demo library records no series, so this proves nothing"
    series = in_a_series[0].book.series
    expected = sorted(s.title for s in states if s.book and s.book.series == series)

    # The old fallback searched title / authors / status / theme tags only, so
    # it found none of these — which is what made the page lie.
    from app.browse import filter_states

    assert filter_states(list(states), q=series) == []

    monkeypatch.setattr("ingest.search_index.fts5_available", lambda conn: False)
    body = client.get("/search", params={"q": series}).text

    for title in expected:
        assert title in body
    assert "Searched without the index" in body
    assert "not ranked by relevance" in body
    # The failure this replaces: a real book reported as no match at all.
    assert "No book in your library matched" not in body


def test_without_fts5_a_genuine_miss_still_says_the_library_is_not_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr("ingest.search_index.fts5_available", lambda conn: False)
    body = client.get("/search", params={"q": "zzzznotathinginanylibrary"}).text
    assert "Your library is not empty." in body
    assert "Your library is empty." not in body
