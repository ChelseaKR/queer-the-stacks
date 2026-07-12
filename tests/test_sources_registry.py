"""The ethical-sources registry stays in lockstep with the catalog allowlist."""

from __future__ import annotations

from recommender.catalogs import ALLOWED_HOSTS, BLOCKED_HOSTS, USER_AGENT, etiquette_headers
from recommender.sources import (
    ETHICAL_SOURCES,
    EXCLUDED_SOURCES,
    FETCH_ETIQUETTE,
    allowed_hosts,
    to_markdown,
)


def test_every_ethical_source_is_on_the_allowlist() -> None:
    # The human-readable registry can never sanction a host the code won't allow.
    assert allowed_hosts() <= ALLOWED_HOSTS


def test_excluded_sources_are_actually_blocked() -> None:
    for s in EXCLUDED_SOURCES:
        assert s.host in BLOCKED_HOSTS
    assert any(s.name == "Goodreads" for s in EXCLUDED_SOURCES)


def test_every_source_has_rationale_and_license() -> None:
    for s in ETHICAL_SOURCES:
        assert s.why.strip()
        assert s.license_note.strip()
        assert s.kind in {"open-data", "api", "federated"}


def test_every_source_has_full_compliance_card() -> None:
    # R5: each source spells out its distinct obligations, not a single blob.
    for s in ETHICAL_SOURCES:
        assert s.attribution.strip()
        assert s.auth.strip()
        assert s.rate_limit.strip()
        assert s.contact.strip()
        assert s.terms_url.startswith("https://")


def test_three_distinct_license_obligations_are_captured() -> None:
    # The EV-LICENSE finding: CC0 vs token-gated/"in flux" vs per-instance ToS.
    by_name = {s.name: s for s in ETHICAL_SOURCES}
    assert "CC0" in by_name["Open Library"].license_note
    assert "in flux" in by_name["Hardcover"].license_note.lower()
    assert "token" in by_name["Hardcover"].auth.lower()
    assert "localhost" in by_name["Hardcover"].auth.lower()
    assert "per-instance" in by_name["Bookwyrm"].license_note.lower()


def test_etiquette_headers_identify_a_polite_read_only_client() -> None:
    # R11: every fetch identifies the client and declares read-only intent.
    headers = etiquette_headers()
    assert "QueerTheStacks" in headers["User-Agent"]
    assert headers["Accept"] == "application/json"
    assert etiquette_headers("text/html")["Accept"] == "text/html"
    assert "read-only" in USER_AGENT.lower()
    # The documented policy never sends reading data and always caches.
    joined = " ".join(FETCH_ETIQUETTE).lower()
    assert "reading history is never sent" in joined
    assert "cache" in joined


def test_markdown_renders_cards_etiquette_and_excluded() -> None:
    md = to_markdown()
    assert "Open Library" in md
    assert "Goodreads" in md
    assert "Excluded" in md
    # R5: per-source compliance cards with the obligations.
    assert "Per-source compliance cards" in md
    assert "Attribution" in md
    assert "Auth / token" in md
    # R11: the documented federation/fetch etiquette policy.
    assert "Federation & fetch etiquette" in md
