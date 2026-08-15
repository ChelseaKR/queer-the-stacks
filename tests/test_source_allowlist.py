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


@pytest.mark.parametrize(
    "url",
    [
        "http://bookwyrm.social/list/123",
        "https://reader:secret@bookwyrm.social/list/123",
        "https://bookwyrm.social/list/123#private-note",
        "https://bookwyrm.social:8443/list/123",
        "https://bookwyrm.social:not-a-port/list/123",
    ],
)
def test_transport_and_url_ambiguities_are_rejected(url: str) -> None:
    with pytest.raises(SourceNotAllowed):
        assert_allowed(url)


def test_goodreads_is_blocked_not_allowlisted() -> None:
    assert "goodreads.com" in BLOCKED_HOSTS
    assert not any("goodreads" in h for h in ALLOWED_HOSTS)
    assert not any("amazon" in h for h in ALLOWED_HOSTS)


# --- The same allowlist, applied to what the page renders as a link ----------


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("science fiction", "science_fiction"),
        ("Science Fiction", "science_fiction"),
        ("  short   stories  ", "short_stories"),
        ("queer", "queer"),
        ("time travel", "time_travel"),
        ("sci/fi", "sci%2Ffi"),
    ],
)
def test_subject_slug_is_a_url_path_segment(subject: str, expected: str) -> None:
    from recommender.catalogs import subject_slug, subject_url

    assert subject_slug(subject) == expected
    assert subject_url(subject) == f"https://openlibrary.org/subjects/{expected}"


def test_every_subject_url_is_fetchable_and_citable() -> None:
    """A subject citation must satisfy both the fetch gate and the display gate.

    `https://openlibrary.org/subjects/science fiction` satisfied neither, and
    was rendered as a link anyway.
    """
    from recommender.catalogs import assert_allowed, is_citable_url, subject_url

    for subject in ("science fiction", "short stories", "time travel", "queer"):
        url = subject_url(subject)
        assert assert_allowed(url) == url
        assert is_citable_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://openlibrary.org/subjects/science fiction",  # the shipped defect
        "https://openlibrary.org/subjects/queer ",
        " https://openlibrary.org/subjects/queer",
        "https://openlibrary.org/subjects/a\tb",
        "http://openlibrary.org/subjects/queer",  # cleartext
        "https://www.goodreads.com/book/show/1",  # blocked host
        "https://example.com/list/1",  # off allowlist
        "curated-list:trans-spec-fic-canon",  # local citation, not a URL
        "",
    ],
)
def test_uncitable_urls_are_not_rendered_as_links(url: str) -> None:
    from app.render import _source_item
    from recommender.catalogs import is_citable_url

    assert not is_citable_url(url)
    # And the renderer agrees: no anchor, but the citation is still visible.
    html = _source_item("openlibrary-subject", url, "2026-08-15")
    assert "<a " not in html
    assert 'class="local-citation"' in html


def test_a_good_url_is_still_rendered_as_a_link() -> None:
    from app.render import _source_item

    html = _source_item(
        "openlibrary-subject", "https://openlibrary.org/subjects/queer", "2026-08-15"
    )
    assert '<a href="https://openlibrary.org/subjects/queer"' in html
    assert 'rel="noopener noreferrer external"' in html
