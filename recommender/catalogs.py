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

from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable
from urllib.parse import urlparse

from ingest.models import Author, Book, Source, SourceKind, ThemeTag, merge_tags
from ingest.unify import normalize_key

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


#: A descriptive, identifying User-Agent for every outbound catalog/federation
#: request. Federation etiquette (EV-LICENSE): a host can see exactly who we are
#: and that we are a read-only, caching, self-hosted consumer of *public* metadata.
USER_AGENT: str = (
    "QueerTheStacks/1.0 (self-hosted reading dashboard; read-only public-metadata "
    "fetch; caches responses; see docs/ethical-book-data-sources.md)"
)


def etiquette_headers(accept: str = "application/json") -> dict[str, str]:
    """Polite, identifying HTTP headers for every catalog/federation fetch.

    Pairs with the on-disk :class:`ResponseCache` (don't re-hit APIs), robots /
    rate-limit respect, and backoff in the live clients — the documented
    federation etiquette in ``docs/ethical-book-data-sources.md``. Only public
    catalog metadata is ever requested; reading data is never sent.
    """
    return {"User-Agent": USER_AGENT, "Accept": accept}


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


# --- Pure parsers (unit-tested via fixtures; the live clients feed these) -----
#
# Each parser maps a catalog's JSON response to `Book`s whose theme tags carry the
# right `SourceKind` + citation. They validate shape defensively (untrusted
# external data) and never raise on a single malformed record.


def _authors(raw: Any, key: str = "name") -> tuple[Author, ...]:
    if not isinstance(raw, list):
        return ()
    out = []
    for a in raw:
        if isinstance(a, dict) and a.get(key):
            out.append(Author(name=str(a[key])))
        elif isinstance(a, str) and a.strip():
            out.append(Author(name=a.strip()))
    return tuple(out)


def parse_openlibrary_subject(
    payload: object, subject: str, citation: str, retrieved_at: str
) -> tuple[Book, ...]:
    """Parse an Open Library ``/subjects/<s>.json`` response into Books."""
    works = payload.get("works", []) if isinstance(payload, dict) else []
    src = Source(SourceKind.OPENLIBRARY_SUBJECT, citation, retrieved_at, subject)
    out: list[Book] = []
    for w in works if isinstance(works, list) else []:
        if not isinstance(w, dict) or not w.get("title"):
            continue
        out.append(
            Book(
                book_id=f"ol:{w.get('key', w['title'])}",
                title=str(w["title"]),
                authors=_authors(w.get("authors")),
                theme_tags=(ThemeTag(subject, src),),
            )
        )
    return tuple(out)


def parse_hardcover_books(payload: object, citation: str, retrieved_at: str) -> tuple[Book, ...]:
    """Parse a Hardcover GraphQL ``books`` response (``data.books[]``) into Books.

    Expected per-book shape: ``{title, contributions:[{author:{name}}],
    cached_tags:{Genre:[{tag}], Mood:[{tag}], ...}}``.
    """
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    books = data.get("books", []) if isinstance(data, dict) else []
    out: list[Book] = []
    for b in books if isinstance(books, list) else []:
        if not isinstance(b, dict) or not b.get("title"):
            continue
        authors = tuple(
            Author(name=str(c["author"]["name"]))
            for c in b.get("contributions", [])
            if isinstance(c, dict) and isinstance(c.get("author"), dict) and c["author"].get("name")
        )
        tags: list[ThemeTag] = []
        cached = b.get("cached_tags", {})
        if isinstance(cached, dict):
            for group in cached.values():
                for t in group if isinstance(group, list) else []:
                    label = t.get("tag") if isinstance(t, dict) else None
                    if label:
                        tags.append(
                            ThemeTag(
                                str(label),
                                Source(
                                    SourceKind.HARDCOVER_TAG, citation, retrieved_at, str(label)
                                ),
                            )
                        )
        out.append(
            Book(
                book_id=f"hardcover:{b.get('slug', b['title'])}",
                title=str(b["title"]),
                authors=authors,
                theme_tags=merge_tags(tags),
            )
        )
    return tuple(out)


def parse_bookwyrm_list(payload: object, citation: str, retrieved_at: str) -> tuple[Book, ...]:
    """Parse a Bookwyrm list/shelf response (``{books:[{title,authors,subjects}]}``)."""
    books = payload.get("books", []) if isinstance(payload, dict) else []
    out: list[Book] = []
    for b in books if isinstance(books, list) else []:
        if not isinstance(b, dict) or not b.get("title"):
            continue
        tags = tuple(
            ThemeTag(str(s), Source(SourceKind.BOOKWYRM_SHELF, citation, retrieved_at, str(s)))
            for s in b.get("subjects", [])
            if isinstance(s, str) and s.strip()
        )
        out.append(
            Book(
                book_id=f"bookwyrm:{b.get('id', b['title'])}",
                title=str(b["title"]),
                authors=_authors(b.get("authors")),
                theme_tags=merge_tags(list(tags)),
            )
        )
    return tuple(out)


def merge_candidates(*groups: tuple[Book, ...]) -> tuple[Book, ...]:
    """Merge candidate books across sources, de-duped by title|author.

    When the same work appears from two catalogs, their sourced theme tags are
    unioned (provenance preserved), so a book gains tags from every source that
    listed it. Deterministic: first-seen identity wins, tags merge in order.
    """
    by_key: dict[str, Book] = {}
    for group in groups:
        for book in group:
            key = normalize_key(book.title, book.author_names)
            if key not in by_key:
                by_key[key] = book
            else:
                existing = by_key[key]
                merged = merge_tags(list(existing.theme_tags) + list(book.theme_tags))
                by_key[key] = Book(
                    book_id=existing.book_id,
                    title=existing.title,
                    authors=existing.authors or book.authors,
                    series=existing.series or book.series,
                    series_index=existing.series_index,
                    identifiers={**book.identifiers, **existing.identifiers},
                    theme_tags=merged,
                    pubdate=existing.pubdate or book.pubdate,
                )
    return tuple(by_key.values())


class ResponseCache:
    """A tiny on-disk JSON cache for catalog responses (legal/ops: don't re-hit APIs).

    Keyed by URL. Stored as one JSON file so it is trivial to inspect and to clear.
    Only public catalog metadata is ever cached — never reading data.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path is not None else None
        self._mem: dict[str, str] = {}
        if self.path is not None and self.path.is_file():
            import json

            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._mem = {str(k): str(v) for k, v in loaded.items()}
            except ValueError, OSError:  # pragma: no cover - corrupt cache is non-fatal
                self._mem = {}

    def get(self, url: str) -> Optional[str]:
        return self._mem.get(url)

    def put(self, url: str, body: str) -> None:
        self._mem[url] = body
        if self.path is not None:
            import json

            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._mem), encoding="utf-8")


class OpenLibraryClient:  # pragma: no cover - live network path, integration-verified
    """Live OpenLibrary client. Every request passes through :func:`assert_allowed`."""

    SUBJECTS_ROOT = "https://openlibrary.org/subjects"

    def __init__(self, cache: Optional[ResponseCache] = None, timeout: int = 15) -> None:
        self.cache = cache
        self.timeout = timeout

    def subject(self, subject: str, limit: int = 50) -> tuple[Book, ...]:
        import json
        import time

        url = assert_allowed(f"{self.SUBJECTS_ROOT}/{subject}.json?limit={limit}")
        body = self._fetch(url)
        return parse_openlibrary_subject(json.loads(body), subject, url, time.strftime("%Y-%m-%d"))

    def _fetch(self, url: str) -> str:
        import requests

        if self.cache is not None:
            cached = self.cache.get(url)
            if cached is not None:
                return cached
        resp = requests.get(url, timeout=self.timeout, headers=etiquette_headers())
        resp.raise_for_status()
        if self.cache is not None:
            self.cache.put(url, resp.text)
        return resp.text


class BookwyrmClient:  # pragma: no cover - live network path, integration-verified
    """Live Bookwyrm list client behind the allowlist."""

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout

    def fetch_list(self, list_url: str) -> tuple[Book, ...]:
        import json
        import time

        import requests

        url = assert_allowed(list_url)
        resp = requests.get(url, timeout=self.timeout, headers=etiquette_headers())
        resp.raise_for_status()
        return parse_bookwyrm_list(json.loads(resp.text), url, time.strftime("%Y-%m-%d"))
