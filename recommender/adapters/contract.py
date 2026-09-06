"""The contract a catalog adapter must satisfy before it may be wired.

Adding a source used to mean touching the allowlist, a client, a parser, the
provenance model and the no-egress tests by hand, with the project's invariants
protected only by tests that knew the current two sources. A third source added
by a contributor would have been protected by nothing, because every guard named
Open Library or Bookwyrm explicitly.

This module states the invariants once, as data an adapter declares plus a small
protocol it implements, so :mod:`recommender.adapters.conformance` can check any
adapter -- including one this repository has never seen -- without knowing what
it is.

The declarations are deliberately narrow. An adapter says which hosts it may
reach and which *shape* of query it may issue, and both are checked against the
hard allowlist in :mod:`recommender.catalogs`. There is no free-text query
grammar, because a free-text query is how a title or an author leaves the
machine: the only permitted inputs are the operator's own predeclared broad
subjects and explicit public list URLs. That is the property the whole project
rests on, so it is in the type rather than in a review comment.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ingest.models import Book, SourceKind

#: A broad Open Library subject slug, the only free-form input any adapter takes.
#: Narrow on purpose: letters, digits, underscore and hyphen, no dots and no
#: slashes, so a query can never be a path, a URL, or a title with spaces in it.
#: :mod:`recommender.catalog_pool` validates configured subjects against this same
#: object, so the shape the refresh path accepts and the shape an adapter will
#: build a URL from cannot drift apart.
SUBJECT_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")


class QueryGrammar(enum.Enum):
    """The shapes of query an adapter may issue. There are only two, on purpose.

    Both are *operator-predeclared*: a broad subject slug or an explicit public
    list URL, written into configuration by the person running the instance.
    Neither can carry a title, an author, or anything derived from what the
    reader has read. There is deliberately no per-title or per-ISBN member --
    such a request would carry a book the reader owns, which is exactly the
    thing that must not leave.
    """

    PREDECLARED_SUBJECT = "predeclared-subject"
    PREDECLARED_LIST_URL = "predeclared-list-url"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class AdapterSpec:
    """What an adapter declares about itself, before it is allowed to run.

    Every field is checked by the conformance suite against something outside
    the adapter: ``hosts`` against the catalog allowlist, ``compliance_card_host``
    against the committed ethical-sources registry, ``source_kind`` against the
    permitted provenance kinds, and ``emits_identity_descriptors`` against the
    tags the adapter actually produces.
    """

    #: Human-readable name, used in ``stacks doctor`` output and failure text.
    name: str

    #: Every host this adapter may reach. Must be a subset of the catalog
    #: allowlist; declaring a host that is not allowlisted is a conformance
    #: failure rather than a silent default-deny at request time.
    hosts: frozenset[str]

    #: The one query shape this adapter issues.
    grammar: QueryGrammar

    #: The provenance kind stamped on every tag this adapter emits.
    source_kind: SourceKind

    #: The host whose compliance card in :mod:`recommender.sources` covers this
    #: adapter. An adapter with no card cannot be registered: the card is where
    #: the license, attribution, auth and rate-limit obligations are recorded,
    #: and those obligations differ materially between sources.
    compliance_card_host: str

    #: Whether this adapter can emit identity-adjacent descriptors ("queer",
    #: "trans", ...). Declaring ``False`` and then emitting one is a conformance
    #: failure: the privacy toggle hides descriptors by label, so a source that
    #: quietly introduces identity vocabulary the lens config does not know about
    #: would publish it un-hidden.
    emits_identity_descriptors: bool


@runtime_checkable
class CatalogAdapter(Protocol):
    """A catalog source, in the only shape the recommender will accept.

    Three members, each one of them a place an invariant is checked:

    ``spec``
        The declaration above.

    ``request_url``
        Builds the URL for one predeclared query. It must return a URL that
        :func:`recommender.catalogs.assert_allowed` accepts, and it must raise
        rather than return for anything off the allowlist. This is the choke
        point the no-egress checks measure.

    ``parse``
        Turns a recorded response body into ``Book``s whose every theme tag
        carries a :class:`~ingest.models.Source` with a citation and a
        ``retrieved_at``. It must not raise on a malformed record; a source that
        cannot be read yields nothing rather than something unprovenanced.
    """

    spec: AdapterSpec

    def request_url(self, query: str) -> str: ...

    def parse(self, body: str, citation: str, retrieved_at: str) -> tuple[Book, ...]: ...

    def fetch(self, query: str) -> tuple[Book, ...]: ...
