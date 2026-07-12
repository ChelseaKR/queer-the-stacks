"""Live-path contract tests for the three network clients, via recorded cassettes.

``KosyncClient``, ``OpenLibraryClient``, and ``BookwyrmClient`` were previously
``pragma: no cover`` — network calls were integration-verified only. These tests
stub ``requests.get`` with a lightweight fake response loaded from a recorded
JSON body under ``tests/cassettes/`` (no VCR dependency, no real network), so the
request-building, status handling, and JSON -> parse wiring is exercised.

The cassette bodies mirror the real API shapes already asserted against in
``tests/test_catalog_parsers.py``; only structural fields (title/authors/tags/
percentage) are asserted, never ``retrieved_at`` (stamped via ``time.strftime``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ingest.kosync import KosyncClient
from ingest.models import DeviceProgress
from recommender.catalogs import (
    BookwyrmClient,
    OpenLibraryClient,
    ResponseCache,
    etiquette_headers,
)

CASSETTES = Path(__file__).parent / "cassettes"


def _load(name: str) -> str:
    return (CASSETTES / name).read_text(encoding="utf-8")


class _FakeResponse:
    """A minimal stand-in for ``requests.Response``: .text, .status_code, .raise_for_status()."""

    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400 and self.status_code != 404:
            raise RuntimeError(f"http {self.status_code}")


# --- KosyncClient -------------------------------------------------------------


def test_kosync_client_progress_for(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_get(url: str, headers: dict[str, str], timeout: int) -> _FakeResponse:
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        return _FakeResponse(_load("kosync_progress.json"))

    monkeypatch.setattr("requests.get", fake_get)

    client = KosyncClient("chelsea", "deadbeefdeadbeefdeadbeefdeadbeef")
    dp = client.progress_for("a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4")

    assert dp == DeviceProgress(
        document="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
        percentage=0.42,
        device="kobo",
        timestamp=1700000000,
    )
    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == (
        "https://sync.koreader.rocks/syncs/progress/a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
    )
    assert call["headers"]["x-auth-user"] == "chelsea"
    assert call["headers"]["x-auth-key"] == "deadbeefdeadbeefdeadbeefdeadbeef"
    assert call["headers"]["accept"] == "application/vnd.koreader.v1+json"


def test_kosync_client_404_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "requests.get", lambda url, headers, timeout: _FakeResponse("", status_code=404)
    )

    client = KosyncClient("chelsea", "deadbeefdeadbeefdeadbeefdeadbeef")
    assert client.progress_for("no-such-document") is None


# --- OpenLibraryClient ----------------------------------------------------------


def test_openlibrary_client_subject_and_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_get(url: str, timeout: int, headers: dict[str, str]) -> _FakeResponse:
        assert headers == etiquette_headers()
        calls.append(url)
        return _FakeResponse(_load("openlibrary_subject.json"))

    monkeypatch.setattr("requests.get", fake_get)

    cache = ResponseCache(tmp_path / "cache.json")
    client = OpenLibraryClient(cache=cache)

    books = client.subject("queer")
    assert len(books) == 2
    assert books[0].title == "Nevada"
    assert books[0].author_names == ("Imogen Binnie",)
    assert books[0].tag_labels == frozenset({"queer"})
    assert books[1].title == "Detransition, Baby"
    assert books[1].author_names == ("Torrey Peters",)
    assert len(calls) == 1

    # Second call for the same subject is served from cache — no second request.
    again = client.subject("queer")
    assert again == books
    assert len(calls) == 1

    # The cache file on disk holds the raw cassette body.
    cached_raw = json.loads((tmp_path / "cache.json").read_text(encoding="utf-8"))
    assert len(cached_raw) == 1


# --- BookwyrmClient -------------------------------------------------------------


def test_bookwyrm_client_fetch_list(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, timeout: int, headers: dict[str, str]) -> _FakeResponse:
        assert headers == etiquette_headers()
        return _FakeResponse(_load("bookwyrm_list.json"))

    monkeypatch.setattr("requests.get", fake_get)

    client = BookwyrmClient()
    books = client.fetch_list("https://bookwyrm.social/list/7")

    assert len(books) == 2
    assert books[0].book_id == "bookwyrm:42"
    assert books[0].title == "Confessions of the Fox"
    assert books[0].author_names == ("Jordy Rosenberg",)
    assert books[0].tag_labels == frozenset({"trans", "speculative", "historical"})
    assert books[1].book_id == "bookwyrm:43"
    assert books[1].tag_labels == frozenset({"afrofuturism", "queer"})
