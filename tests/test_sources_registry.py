"""The ethical-sources registry stays in lockstep with the catalog allowlist."""

from __future__ import annotations

from recommender.catalogs import ALLOWED_HOSTS, BLOCKED_HOSTS
from recommender.sources import (
    ETHICAL_SOURCES,
    EXCLUDED_SOURCES,
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


def test_markdown_renders_used_and_excluded() -> None:
    md = to_markdown()
    assert "Open Library" in md
    assert "Goodreads" in md
    assert "Excluded" in md
