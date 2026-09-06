"""The two live sources, expressed as adapters.

These wrap :class:`~recommender.catalogs.OpenLibraryClient` and
:class:`~recommender.catalogs.BookwyrmClient` rather than replacing them. The
clients keep their URL building, status handling and parser wiring exactly as
they were, so the recorded-cassette contract tests in
``tests/test_live_clients_cassettes.py`` exercise the same code and the refresh
path behaves identically. The adapter is a declaration plus a thin call.

That is deliberate. Migrating the two existing sources onto the contract is
worth nothing if the migration is also a rewrite: the point is to show the
contract fits the sources that already work, and to have the conformance suite
pass against them unchanged.
"""

from __future__ import annotations

import json
import time

from ingest.models import Book, SourceKind

from recommender.adapters.contract import SUBJECT_SLUG, AdapterSpec, QueryGrammar
from recommender.catalogs import (
    SUBJECTS_ROOT,
    BookwyrmClient,
    OpenLibraryClient,
    SourceNotAllowed,
    assert_allowed,
    parse_bookwyrm_list,
    parse_openlibrary_subject,
)


class OpenLibraryAdapter:
    """Broad Open Library subject headings, the operator's own predeclared list."""

    spec = AdapterSpec(
        name="Open Library",
        hosts=frozenset({"openlibrary.org"}),
        grammar=QueryGrammar.PREDECLARED_SUBJECT,
        source_kind=SourceKind.OPENLIBRARY_SUBJECT,
        compliance_card_host="openlibrary.org",
        # Subject headings include "lgbtq", "lesbian fiction" and similar: this
        # source does carry identity vocabulary, and says so.
        emits_identity_descriptors=True,
    )

    def __init__(self, limit: int = 50) -> None:
        self._limit = limit
        self._client = OpenLibraryClient()

    def request_url(self, query: str) -> str:
        # The grammar is enforced here, not only where configuration is read.
        # Without it a "subject" containing a slash or a space builds a URL that
        # still lands on openlibrary.org, so `assert_allowed` passes it and the
        # declared grammar means nothing. The conformance suite caught exactly
        # that: this adapter accepted a full Goodreads URL as a subject.
        if not SUBJECT_SLUG.match(query):
            raise SourceNotAllowed(
                f"{query!r} is not a broad subject slug; Open Library requests carry "
                "operator-predeclared subjects only"
            )
        return assert_allowed(f"{SUBJECTS_ROOT}/{query}.json?limit={self._limit}")

    def parse(self, body: str, citation: str, retrieved_at: str) -> tuple[Book, ...]:
        subject = citation.rsplit("/", 1)[-1].split(".")[0]
        return parse_openlibrary_subject(json.loads(body), subject, citation, retrieved_at)

    def fetch(self, query: str) -> tuple[Book, ...]:
        return self._client.subject(query, limit=self._limit)


class BookwyrmAdapter:
    """Explicit public Bookwyrm list URLs, written into configuration by the operator."""

    spec = AdapterSpec(
        name="Bookwyrm",
        hosts=frozenset({"bookwyrm.social"}),
        grammar=QueryGrammar.PREDECLARED_LIST_URL,
        source_kind=SourceKind.BOOKWYRM_SHELF,
        compliance_card_host="bookwyrm.social",
        emits_identity_descriptors=True,
    )

    def __init__(self) -> None:
        self._client = BookwyrmClient()

    def request_url(self, query: str) -> str:
        return assert_allowed(query)

    def parse(self, body: str, citation: str, retrieved_at: str) -> tuple[Book, ...]:
        return parse_bookwyrm_list(json.loads(body), citation, retrieved_at)

    def fetch(self, query: str) -> tuple[Book, ...]:
        return self._client.fetch_list(query)


def today() -> str:
    """The retrieval date the live clients stamp, in one place."""
    return time.strftime("%Y-%m-%d")
