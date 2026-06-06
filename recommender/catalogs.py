"""Ethical book-data sources, behind a hard host allowlist.

Hard guardrail (README): **do not scrape Goodreads** (Amazon ToS + gatekeeping +
surveillance). Recommendations are sourced from OpenLibrary, Hardcover, and
Bookwyrm, each tagged with provenance. This module is the single choke point for
catalog network access, and :func:`assert_allowed` makes Goodreads/Amazon a
build-time impossibility: any request to a blocked host raises before a socket is
opened. The merge-blocking metric "Goodreads requests = 0" is enforced here plus
by the source-allowlist test.

Only public catalog metadata (subjects, lists, a lookup by title/ISBN) is ever
fetched; the user's reading history is never sent anywhere — that is the privacy
guardrail, checked by the no-egress test.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from urllib.parse import urlparse

from ingest.models import Book

#: Hosts the recommender is permitted to fetch from. Each is an ethical,
#: non-gatekept catalog with a usable API or open data.
ALLOWED_HOSTS: frozenset[str] = frozenset(
    {
        "openlibrary.org",
        "covers.openlibrary.org",
        "api.hardcover.app",
        "bookwyrm.social",
    }
)

#: Explicitly blocked hosts — recorded so the exclusion is legible, not implicit.
#: Goodreads (and its Amazon parent) are excluded on ToS + values grounds.
BLOCKED_HOSTS: frozenset[str] = frozenset(
    {
        "goodreads.com",
        "www.goodreads.com",
        "amazon.com",
        "www.amazon.com",
    }
)


class SourceNotAllowed(Exception):
    """Raised when a catalog request targets a blocked or non-allowlisted host."""


def assert_allowed(url: str) -> str:
    """Return ``url`` iff its host is allowlisted; otherwise raise.

    A blocked host (Goodreads/Amazon) raises with an explicit message; an
    unknown host raises too (default-deny). This runs before any request.
    """
    host = (urlparse(url).hostname or "").lower()
    if not host:
        raise SourceNotAllowed(f"no host in URL: {url!r}")
    if host in BLOCKED_HOSTS:
        raise SourceNotAllowed(
            f"{host} is a blocked source (Goodreads/Amazon excluded on ToS + values grounds)"
        )
    if host not in ALLOWED_HOSTS:
        raise SourceNotAllowed(f"{host} is not in the catalog allowlist (default-deny)")
    return url


@runtime_checkable
class CatalogSource(Protocol):
    """The catalog interface the recommender depends on."""

    def candidates(self) -> tuple[Book, ...]: ...


class FixtureCatalog:
    """A deterministic, offline :class:`CatalogSource` built from plain books."""

    def __init__(self, books: tuple[Book, ...]) -> None:
        self._books = books

    def candidates(self) -> tuple[Book, ...]:
        return self._books


class OpenLibraryClient:  # pragma: no cover - live network path, integration-verified
    """Live OpenLibrary client. Every request passes through :func:`assert_allowed`."""

    SUBJECTS_ROOT = "https://openlibrary.org/subjects"

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout

    def subject(self, subject: str, limit: int = 50) -> tuple[Book, ...]:
        import json

        import requests
        from ingest.models import Author, Source, SourceKind, ThemeTag

        url = assert_allowed(f"{self.SUBJECTS_ROOT}/{subject}.json?limit={limit}")
        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        payload = json.loads(resp.text)
        retrieved = __import__("time").strftime("%Y-%m-%d")
        works = payload.get("works", []) if isinstance(payload, dict) else []
        out: list[Book] = []
        for w in works:
            if not isinstance(w, dict):
                continue
            authors = tuple(
                Author(name=str(a.get("name", "")))
                for a in w.get("authors", [])
                if isinstance(a, dict)
            )
            tag = ThemeTag(
                label=subject,
                source=Source(
                    kind=SourceKind.OPENLIBRARY_SUBJECT,
                    citation=url,
                    retrieved_at=retrieved,
                    detail=subject,
                ),
            )
            out.append(
                Book(
                    book_id=f"ol:{w.get('key', '')}",
                    title=str(w.get("title", "")),
                    authors=authors,
                    theme_tags=(tag,),
                )
            )
        return tuple(out)
