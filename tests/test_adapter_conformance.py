"""The conformance suite every catalog adapter must pass (merge-blocking).

The allowlist, the provenance model and the no-egress promise are the product.
Before this file they were protected by tests that named Open Library and
Bookwyrm explicitly, so a third source contributed by someone else would have
been protected by none of them: every guard would have kept passing while
knowing nothing about the new adapter.

Two properties make this suite worth trusting.

**It is checked against a failing adapter, permanently.** :class:`LeakyAdapter`
appends the reader's author to its query, declares a host it may not reach, and
claims no compliance card. The tests below assert that the suite *rejects* it,
naming the offending request. A conformance check that quietly stopped rejecting
it would fail the build rather than reporting green over nothing -- which is what
a suite made only of ``assert`` statements cannot do for itself.

**It cannot pass over an empty set.** Every parametrised test would pass
vacuously if the registry were empty or the request-capture harness caught
nothing, so the adapter count is pinned and each egress test asserts that
requests were actually made before asserting what they contained.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ingest.models import Author, Book, Source, SourceKind, ThemeTag
from recommender.adapters import (
    REGISTERED_ADAPTERS,
    AdapterSpec,
    CatalogAdapter,
    QueryGrammar,
    check_adapter,
    query_leaks,
)
from recommender.adapters.conformance import (
    check_compliance_card,
    check_declared_hosts,
    check_identity_declaration,
    check_provenance,
    check_request_urls,
)
from recommender.adapters.registry import adapter_card_statuses, compliance_card_status
from recommender.catalogs import ALLOWED_HOSTS, SourceNotAllowed

from tests.netguard import capture_requests

CASSETTES = Path(__file__).parent / "cassettes"

#: The probe query each adapter is driven with, in its own declared grammar.
PROBES: dict[QueryGrammar, str] = {
    QueryGrammar.PREDECLARED_SUBJECT: "queer",
    QueryGrammar.PREDECLARED_LIST_URL: "https://bookwyrm.social/list/7.json",
}

#: The cassette that stands in for each grammar's response body.
BODIES: dict[QueryGrammar, str] = {
    QueryGrammar.PREDECLARED_SUBJECT: (CASSETTES / "openlibrary_subject.json").read_text(
        encoding="utf-8"
    ),
    QueryGrammar.PREDECLARED_LIST_URL: (CASSETTES / "bookwyrm_list.json").read_text(
        encoding="utf-8"
    ),
}

#: Signals planted in a hypothetical reader's library. None of these may appear
#: in any outbound request: they are the titles, authors and taste words that
#: identify a person by what they read.
READER_SIGNALS: tuple[str, ...] = (
    "Detransition, Baby",
    "Torrey Peters",
    "Imogen Binnie",
    "Confessions of the Fox",
    "Jordy Rosenberg",
    "my-favourite-genre",
)


def _probe(adapter: CatalogAdapter) -> str:
    return PROBES[adapter.spec.grammar]


def _body(adapter: CatalogAdapter) -> str:
    return BODIES[adapter.spec.grammar]


def _parsed(adapter: CatalogAdapter) -> tuple[Book, ...]:
    citation = adapter.request_url(_probe(adapter))
    return adapter.parse(_body(adapter), citation, "2026-09-06")


# ---------------------------------------------------------------------------
# The deliberately bad adapter. It is the negative control, and it is permanent.
# ---------------------------------------------------------------------------


class LeakyAdapter:
    """An adapter that does the three things a contributed adapter must not do.

    It appends the reader's author to the query string, so the request carries
    what the reader has read; it declares a host that is not on the allowlist;
    and it names a compliance card that does not exist. Each is checked below.
    """

    spec = AdapterSpec(
        name="Leaky",
        hosts=frozenset({"openlibrary.org", "example.invalid"}),
        grammar=QueryGrammar.PREDECLARED_SUBJECT,
        source_kind=SourceKind.OPENLIBRARY_SUBJECT,
        compliance_card_host="example.invalid",
        emits_identity_descriptors=False,
    )
    #: The author this adapter smuggles into every request.
    LEAKED_AUTHOR = "Torrey Peters"

    def request_url(self, query: str) -> str:
        # The defect: a "personalised" subject request that carries an author.
        return f"https://openlibrary.org/subjects/{query}.json?author={self.LEAKED_AUTHOR}"

    def parse(self, body: str, citation: str, retrieved_at: str) -> tuple[Book, ...]:
        payload = json.loads(body)
        return tuple(
            Book(
                book_id=f"leak:{w['title']}",
                title=str(w["title"]),
                authors=(Author(name="x"),),
                # An identity descriptor, while declaring it emits none.
                theme_tags=(
                    ThemeTag(
                        "queer", Source(SourceKind.OPENLIBRARY_SUBJECT, citation, "", "queer")
                    ),
                ),
            )
            for w in payload.get("works", [])
            if w.get("title")
        )

    def fetch(self, query: str) -> tuple[Book, ...]:
        import requests

        url = self.request_url(query)
        response = requests.get(url, timeout=5, allow_redirects=False)
        return self.parse(response.text, url, "2026-09-06")


# ---------------------------------------------------------------------------
# The suite cannot pass over nothing.
# ---------------------------------------------------------------------------


def test_the_registry_is_not_empty_and_is_what_this_build_ships() -> None:
    """Every parametrised test below loops over the registry. Pin it, so an empty
    or shrunken registry is a failure rather than a quietly smaller loop."""
    names = sorted(adapter.spec.name for adapter in REGISTERED_ADAPTERS)
    assert names == ["Bookwyrm", "Open Library"], names


def test_every_registered_adapter_satisfies_the_protocol() -> None:
    for adapter in REGISTERED_ADAPTERS:
        assert isinstance(adapter, CatalogAdapter), adapter
        assert isinstance(adapter.spec, AdapterSpec)


# ---------------------------------------------------------------------------
# The registered adapters pass, unchanged.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("adapter", REGISTERED_ADAPTERS, ids=lambda a: a.spec.name)
def test_registered_adapter_passes_conformance(adapter: CatalogAdapter) -> None:
    failures = check_adapter(adapter, [_probe(adapter)], _parsed(adapter))
    assert failures == (), [str(f) for f in failures]


@pytest.mark.parametrize("adapter", REGISTERED_ADAPTERS, ids=lambda a: a.spec.name)
def test_registered_adapter_declares_only_allowlisted_hosts(adapter: CatalogAdapter) -> None:
    assert adapter.spec.hosts <= ALLOWED_HOSTS, adapter.spec.hosts - ALLOWED_HOSTS


@pytest.mark.parametrize("adapter", REGISTERED_ADAPTERS, ids=lambda a: a.spec.name)
def test_registered_adapter_emits_provenance_for_every_fact(adapter: CatalogAdapter) -> None:
    books = _parsed(adapter)
    assert books, f"{adapter.spec.name} parsed no books from its cassette"
    tags = [tag for book in books for tag in book.theme_tags]
    assert tags, f"{adapter.spec.name} emitted no tags; provenance would be checked over nothing"
    assert check_provenance(adapter.spec, books) == ()


@pytest.mark.parametrize("adapter", REGISTERED_ADAPTERS, ids=lambda a: a.spec.name)
def test_registered_adapter_sends_no_reading_signal(adapter: CatalogAdapter) -> None:
    """The egress check, below ``requests``: what would actually have left."""
    with capture_requests(body=_body(adapter)) as sent:
        adapter.fetch(_probe(adapter))
    assert sent, f"{adapter.spec.name} made no request; the leak check read nothing"
    texts = [request.as_text() for request in sent]
    assert query_leaks(adapter.spec, texts, READER_SIGNALS) == ()
    for request in sent:
        assert request.allow_redirects is False, request.url


@pytest.mark.parametrize("adapter", REGISTERED_ADAPTERS, ids=lambda a: a.spec.name)
def test_registered_adapter_refuses_a_blocked_host(adapter: CatalogAdapter) -> None:
    with pytest.raises(SourceNotAllowed):
        adapter.request_url("https://www.goodreads.com/list/1.json")


@pytest.mark.parametrize("adapter", REGISTERED_ADAPTERS, ids=lambda a: a.spec.name)
def test_registered_adapter_survives_404_timeout_and_malformed_bodies(
    adapter: CatalogAdapter,
) -> None:
    """A source that cannot be read yields nothing; it never yields a fact without
    provenance, and it never lets a transport failure through as data."""
    for body in ("", "not json", "{}", '{"works": "nope"}', '{"books": {}}'):
        try:
            books = adapter.parse(body, adapter.request_url(_probe(adapter)), "2026-09-06")
        except ValueError, TypeError, KeyError:
            continue  # refusing to parse rubbish is correct
        assert check_provenance(adapter.spec, books) == ()

    def _boom(_request: object) -> object:
        raise TimeoutError("connection timed out")

    # noqa: B017 on both - any propagated failure is acceptable here; the property
    # under test is that neither a timeout nor a 404 returns quietly as an empty
    # catalog, not which exception type carries the news.
    with (
        capture_requests(responder=_boom),
        pytest.raises(Exception),  # noqa: B017
    ):
        adapter.fetch(_probe(adapter))

    with (
        capture_requests(body="", status_code=404),
        pytest.raises(Exception),  # noqa: B017
    ):
        adapter.fetch(_probe(adapter))


# ---------------------------------------------------------------------------
# The negative control: the suite must reject a bad adapter, and say why.
# ---------------------------------------------------------------------------


def test_the_leaky_adapter_is_caught_carrying_an_author_and_the_request_is_named() -> None:
    """The headline check. An adapter that appends an author to its query fails,
    and the failure quotes the request that carried it."""
    leaky = LeakyAdapter()
    with capture_requests(body=BODIES[QueryGrammar.PREDECLARED_SUBJECT]) as sent:
        leaky.fetch("queer")
    assert sent, "the harness captured no request; the control would prove nothing"
    failures = query_leaks(leaky.spec, [r.as_text() for r in sent], READER_SIGNALS)
    assert failures, "the leak check did not reject an adapter that sends an author"
    assert any(LeakyAdapter.LEAKED_AUTHOR.lower() in f.detail.lower() for f in failures), failures
    # The offending request itself, not merely the fact that one leaked.
    assert any("openlibrary.org/subjects/queer.json?author=" in f.detail for f in failures), (
        f"the failure must name the request that carried the signal: {[str(f) for f in failures]}"
    )


def test_the_leaky_adapter_fails_on_an_undeclared_and_unallowlisted_host() -> None:
    failures = check_declared_hosts(LeakyAdapter.spec)
    assert any("example.invalid" in f.detail for f in failures), failures


def test_the_leaky_adapter_fails_for_having_no_compliance_card() -> None:
    failures = check_compliance_card(LeakyAdapter.spec)
    assert failures, "an adapter with no compliance card was accepted"
    assert "example.invalid" in failures[0].detail


def test_the_leaky_adapter_fails_for_undeclared_identity_descriptors() -> None:
    leaky = LeakyAdapter()
    books = leaky.parse(BODIES[QueryGrammar.PREDECLARED_SUBJECT], "https://openlibrary.org/x", "")
    failures = check_identity_declaration(leaky.spec, books)
    assert failures, "an adapter emitting 'queer' while declaring it emits none was accepted"


def test_the_leaky_adapter_fails_provenance_for_an_empty_retrieval_date() -> None:
    leaky = LeakyAdapter()
    books = leaky.parse(BODIES[QueryGrammar.PREDECLARED_SUBJECT], "https://openlibrary.org/x", "")
    failures = check_provenance(leaky.spec, books)
    assert any("retrieved_at" in f.detail for f in failures), failures


def test_an_adapter_declaring_no_hosts_fails_rather_than_passing_vacuously() -> None:
    """The gate-that-cannot-fail shape: an empty host set satisfies "every declared
    host is allowlisted" by having nothing to check."""
    spec = AdapterSpec(
        name="Empty",
        hosts=frozenset(),
        grammar=QueryGrammar.PREDECLARED_SUBJECT,
        source_kind=SourceKind.OPENLIBRARY_SUBJECT,
        compliance_card_host="openlibrary.org",
        emits_identity_descriptors=False,
    )
    assert check_declared_hosts(spec), "an adapter declaring no hosts was accepted"


def test_probing_an_adapter_with_no_queries_fails_rather_than_passing_vacuously() -> None:
    failures = check_request_urls(REGISTERED_ADAPTERS[0], [])
    assert failures, "checking zero URLs reported success"


# ---------------------------------------------------------------------------
# `stacks doctor`
# ---------------------------------------------------------------------------


def test_doctor_reports_a_card_for_every_registered_adapter() -> None:
    statuses = adapter_card_statuses()
    assert len(statuses) == len(REGISTERED_ADAPTERS)
    assert all(status.ok for status in statuses), [s.detail for s in statuses if not s.ok]


def test_doctor_fails_an_adapter_registered_without_a_compliance_card() -> None:
    status = compliance_card_status(LeakyAdapter.spec)
    assert status.ok is False
    assert "no compliance card" in status.detail


def test_doctor_check_list_includes_the_adapters() -> None:
    from ingest.refresh import _adapter_checks

    checks = _adapter_checks()
    assert [c.name for c in checks] == [
        f"catalog adapter {a.spec.name}" for a in REGISTERED_ADAPTERS
    ]
    assert all(c.ok for c in checks)


def test_doctor_itself_runs_the_adapter_checks(tmp_path: Path) -> None:
    """Not the helper -- ``doctor`` itself.

    The test above calls ``_adapter_checks`` directly, so it passes whether or not
    ``doctor`` ever calls it. A negative control proved that: deleting the call
    from ``doctor`` left the whole conformance suite green. This drives the real
    entry point, which is the thing a person runs.
    """
    from ingest.config import load_config
    from ingest.demo import build_demo_dbs
    from ingest.refresh import doctor

    metadata_db, statistics_db = build_demo_dbs(tmp_path / "lib")
    config = load_config(
        env={
            "STACKS_CALIBRE_DB": str(metadata_db),
            "STACKS_KOREADER_DB": str(statistics_db),
            "STACKS_DATA_DIR": str(tmp_path / "data"),
        },
        config_path=tmp_path / "absent.toml",
    )
    names = [check.name for check in doctor(config)]
    expected = [f"catalog adapter {a.spec.name}" for a in REGISTERED_ADAPTERS]
    assert expected, "no adapters registered; this check would pass over nothing"
    missing = [name for name in expected if name not in names]
    assert not missing, f"`stacks doctor` does not report {missing}; it reported {names}"
