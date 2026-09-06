"""The conformance suite, as functions that return failures rather than raise.

A suite written only as ``assert`` statements can check that the two adapters in
the tree are correct. It cannot check *itself* -- that it would actually reject a
bad adapter -- because there is no way to run it and survive the failure.

So every check here returns :class:`ConformanceFailure` values. The tests assert
that the registered adapters produce none, and that a deliberately bad fixture
adapter produces specific ones. The second assertion is the negative control, and
it is a permanent part of the suite rather than something run once by hand: if a
check silently stops rejecting the bad adapter, the build fails.

Each failure names the adapter, the check, and the offending value, because
"conformance failed" is not actionable and the offending request is the whole
point of the egress check.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from urllib.parse import unquote_plus

from app.diversity import AGGREGATED_LABEL, REDACTED_LABEL, SENSITIVE_DESCRIPTORS
from ingest.models import PERMITTED_SOURCES, Book

from recommender.adapters.contract import AdapterSpec, CatalogAdapter
from recommender.catalogs import ALLOWED_HOSTS, BLOCKED_HOSTS, SourceNotAllowed, assert_allowed
from recommender.sources import ETHICAL_SOURCES

#: ``retrieved_at`` is a date, not a decorative string. A source that stamps a
#: constant, an empty string, or the epoch is the "absence rendered as a value"
#: defect this project has already fixed once (PR #75, PR #79).
_ISO_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")

#: Labels the privacy layer substitutes when it redacts. They are placeholders,
#: never facts, and an adapter that emits one as a sourced descriptor would be
#: publishing a redaction as though a catalog had asserted it.
_PLACEHOLDER_LABELS = frozenset({REDACTED_LABEL, AGGREGATED_LABEL})


@dataclass(frozen=True)
class ConformanceFailure:
    """One way an adapter failed the contract."""

    adapter: str
    check: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.adapter}] {self.check}: {self.detail}"


def check_declared_hosts(spec: AdapterSpec) -> tuple[ConformanceFailure, ...]:
    """The adapter's declared hosts, against the hard allowlist.

    Declaring nothing is a failure too. An adapter with an empty host set would
    pass a "every declared host is allowlisted" check vacuously, which is the
    gate-that-cannot-fail shape this repository keeps finding.
    """
    out: list[ConformanceFailure] = []
    if not spec.hosts:
        out.append(
            ConformanceFailure(
                spec.name, "declared-hosts", "declares no hosts; nothing would be checked"
            )
        )
    for host in sorted(spec.hosts):
        if host in BLOCKED_HOSTS:
            out.append(
                ConformanceFailure(spec.name, "declared-hosts", f"{host} is a blocked source")
            )
        elif host not in ALLOWED_HOSTS:
            out.append(
                ConformanceFailure(
                    spec.name, "declared-hosts", f"{host} is not on the catalog allowlist"
                )
            )
    return tuple(out)


def check_compliance_card(spec: AdapterSpec) -> tuple[ConformanceFailure, ...]:
    """Every adapter must be covered by a committed compliance card.

    The card is where the license, attribution, auth and rate-limit obligations
    live, and those differ materially between Open Library (CC0), Hardcover
    (token-gated, in flux) and Bookwyrm (per-instance ToS). An adapter without
    one is an adapter whose obligations nobody has written down.
    """
    cards = {source.host: source for source in ETHICAL_SOURCES}
    card = cards.get(spec.compliance_card_host)
    if card is None:
        return (
            ConformanceFailure(
                spec.name,
                "compliance-card",
                f"no compliance card for {spec.compliance_card_host!r} in recommender.sources; "
                "add an EthicalSource entry stating its licence, attribution, auth and "
                "rate-limit obligations",
            ),
        )
    if spec.compliance_card_host not in spec.hosts:
        return (
            ConformanceFailure(
                spec.name,
                "compliance-card",
                f"card host {spec.compliance_card_host!r} is not among the declared hosts "
                f"{sorted(spec.hosts)}",
            ),
        )
    return ()


def check_source_kind(spec: AdapterSpec) -> tuple[ConformanceFailure, ...]:
    """The provenance kind must be one the model permits (never an inference)."""
    if spec.source_kind not in PERMITTED_SOURCES:
        return (
            ConformanceFailure(
                spec.name, "source-kind", f"{spec.source_kind!r} is not a permitted source kind"
            ),
        )
    return ()


def check_request_urls(
    adapter: CatalogAdapter, queries: Sequence[str]
) -> tuple[ConformanceFailure, ...]:
    """Every URL the adapter builds must survive ``assert_allowed`` and be declared.

    An adapter is free to build its URL however it likes; it is not free to build
    one that reaches a host it did not declare. Checking against the *spec* and
    not only against the global allowlist is what makes a contributed adapter
    reviewable: the declaration is the claim, and this is the check.
    """
    out: list[ConformanceFailure] = []
    if not queries:
        return (
            ConformanceFailure(
                adapter.spec.name, "request-url", "no probe queries; nothing would be checked"
            ),
        )
    for query in queries:
        try:
            url = adapter.request_url(query)
        except SourceNotAllowed as exc:
            out.append(
                ConformanceFailure(
                    adapter.spec.name, "request-url", f"refused its own probe {query!r}: {exc}"
                )
            )
            continue
        try:
            assert_allowed(url)
        except SourceNotAllowed as exc:
            out.append(
                ConformanceFailure(
                    adapter.spec.name, "request-url", f"built a URL the allowlist refuses: {exc}"
                )
            )
            continue
        host = url.split("/")[2].split("@")[-1].split(":")[0].lower()
        if host not in adapter.spec.hosts:
            out.append(
                ConformanceFailure(
                    adapter.spec.name,
                    "request-url",
                    f"built a URL on {host!r}, which it did not declare",
                )
            )
    return tuple(out)


def check_refuses_off_allowlist(adapter: CatalogAdapter) -> tuple[ConformanceFailure, ...]:
    """A blocked host must raise, not return.

    An adapter that quietly returns a Goodreads URL and leaves the refusal to the
    fetch path is one refactor away from being the hole.
    """
    for hostile in ("https://www.goodreads.com/list/1.json", "http://openlibrary.org/subjects/x"):
        try:
            adapter.request_url(hostile)
        except SourceNotAllowed:
            continue
        except Exception:  # noqa: BLE001, S112 - any refusal is acceptable; silence is not
            continue
        return (
            ConformanceFailure(
                adapter.spec.name,
                "off-allowlist",
                f"did not refuse {hostile!r}",
            ),
        )
    return ()


def check_provenance(spec: AdapterSpec, books: Iterable[Book]) -> tuple[ConformanceFailure, ...]:
    """Every emitted fact carries a source, a real retrieval date, and a permitted kind."""
    out: list[ConformanceFailure] = []
    for book in books:
        for tag in book.theme_tags:
            source = tag.source
            if not source.citation.strip():
                out.append(
                    ConformanceFailure(
                        spec.name, "provenance", f"tag {tag.label!r} carries an empty citation"
                    )
                )
            if not _ISO_DATE.match(source.retrieved_at or ""):
                out.append(
                    ConformanceFailure(
                        spec.name,
                        "provenance",
                        f"tag {tag.label!r} has retrieved_at "
                        f"{source.retrieved_at!r}, which is not an ISO date",
                    )
                )
            if source.kind not in PERMITTED_SOURCES:
                out.append(
                    ConformanceFailure(
                        spec.name, "provenance", f"tag {tag.label!r} has kind {source.kind!r}"
                    )
                )
            if tag.label in _PLACEHOLDER_LABELS:
                out.append(
                    ConformanceFailure(
                        spec.name,
                        "provenance",
                        f"emitted the privacy placeholder {tag.label!r} as a sourced descriptor",
                    )
                )
    return tuple(out)


def check_identity_declaration(
    spec: AdapterSpec, books: Iterable[Book]
) -> tuple[ConformanceFailure, ...]:
    """An adapter that emits identity descriptors must have said so.

    The privacy toggle hides descriptors by label. A source that introduces
    identity vocabulary while declaring it does not is a source whose tags the
    toggle would render in the clear on a screen-shared page.
    """
    if spec.emits_identity_descriptors:
        return ()
    found = sorted(
        {
            tag.label
            for book in books
            for tag in book.theme_tags
            if tag.normalized in SENSITIVE_DESCRIPTORS
        }
    )
    if found:
        return (
            ConformanceFailure(
                spec.name,
                "identity-descriptors",
                f"declares emits_identity_descriptors=False but emitted {found}",
            ),
        )
    return ()


#: Everything that is punctuation, separator, or encoding rather than content.
#: A leak does not arrive spelled the way the library spells it: ``requests``
#: percent-encodes the space, so an author smuggled into a query string reaches
#: the wire as ``author=Torrey%20Peters``. Scanning the raw text for
#: ``"torrey peters"`` finds nothing and reports the adapter clean, which is a
#: check that cannot fail on the very thing it exists for. Measured here: the
#: leaky fixture adapter passed the first version of this function.
_NOT_CONTENT = re.compile(r"[^a-z0-9]+")


def _squash(value: str) -> str:
    """A string reduced to its letters and digits, lowercased."""
    return _NOT_CONTENT.sub("", value.lower())


def _searchable(text: str) -> str:
    """One request, percent-decoded and squashed, so encoding cannot hide a signal."""
    return _squash(unquote_plus(text))


def query_leaks(
    spec: AdapterSpec, request_texts: Iterable[str], signals: Iterable[str]
) -> tuple[ConformanceFailure, ...]:
    """Requests that carry a reading signal, each named in full.

    ``request_texts`` come from the request-capture harness, so this is what
    would actually have left the machine -- URL, headers and body -- not what the
    adapter meant to send. ``signals`` are the titles, authors and taste words
    planted in the probe library.

    The offending request is quoted in the failure. "An adapter leaked" is not
    actionable; the URL that carried the author is.
    """
    prepared = [(text, _searchable(text)) for text in request_texts]
    out: list[ConformanceFailure] = []
    for signal in signals:
        needle = _squash(signal)
        if not needle:
            continue
        for original, text in prepared:
            if needle in text:
                out.append(
                    ConformanceFailure(
                        spec.name,
                        "query-leak",
                        f"request carried the reading signal {signal!r}: {original}",
                    )
                )
    return tuple(out)


def check_adapter(
    adapter: CatalogAdapter, queries: Sequence[str], books: Iterable[Book]
) -> tuple[ConformanceFailure, ...]:
    """Every check that needs no network, in one call.

    The egress check (:func:`query_leaks`) is separate because it needs the
    request-capture harness to have run the adapter first.
    """
    spec = adapter.spec
    materialised = tuple(books)
    return (
        check_declared_hosts(spec)
        + check_compliance_card(spec)
        + check_source_kind(spec)
        + check_request_urls(adapter, queries)
        + check_refuses_off_allowlist(adapter)
        + check_provenance(spec, materialised)
        + check_identity_declaration(spec, materialised)
    )
