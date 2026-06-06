"""Source-ethics guardrail — "Goodreads requests = 0" (merge-blocking).

The recommender may only fetch from ethical, non-gatekept catalogs. Goodreads
(and its Amazon parent) are blocked at the single network choke point, before any
socket opens. These tests prove the choke point is default-deny and that
Goodreads is explicitly excluded, not merely absent.
"""

from __future__ import annotations

import pytest
from recommender.catalogs import (
    ALLOWED_HOSTS,
    BLOCKED_HOSTS,
    SourceNotAllowed,
    assert_allowed,
)


def test_allowlisted_hosts_pass() -> None:
    assert assert_allowed("https://openlibrary.org/subjects/transgender.json")
    assert assert_allowed("https://api.hardcover.app/v1/graphql")
    assert assert_allowed("https://bookwyrm.social/list/123")


@pytest.mark.parametrize(
    "url",
    [
        "https://www.goodreads.com/book/show/1",
        "https://goodreads.com/list/1",
        "https://www.amazon.com/dp/123",
    ],
)
def test_blocked_hosts_raise(url: str) -> None:
    with pytest.raises(SourceNotAllowed):
        assert_allowed(url)


def test_unknown_host_is_default_denied() -> None:
    with pytest.raises(SourceNotAllowed):
        assert_allowed("https://some-random-tracker.example/api")


def test_missing_host_raises() -> None:
    with pytest.raises(SourceNotAllowed):
        assert_allowed("not-a-url")


def test_goodreads_is_blocked_not_allowlisted() -> None:
    assert "goodreads.com" in BLOCKED_HOSTS
    assert not any("goodreads" in h for h in ALLOWED_HOSTS)
    assert not any("amazon" in h for h in ALLOWED_HOSTS)
