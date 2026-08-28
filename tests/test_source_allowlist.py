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
    """Denied by the *blocked* branch, not merely by falling off the allowlist.

    ``assert_allowed`` has two independent deny branches, and no Goodreads or
    Amazon host is in ``ALLOWED_HOSTS``, so the default-deny branch already
    raises for every URL here. A bare ``pytest.raises(SourceNotAllowed)`` cannot
    tell the two apart, which left the values-based exclusion this file's
    docstring claims to prove — "explicitly excluded, not merely absent" —
    untested: reorder the two checks, or let the blocked branch become
    unreachable, and nothing failed. Matching the message pins which branch
    fired.
    """
    with pytest.raises(SourceNotAllowed, match="blocked source"):
        assert_allowed(url)


def test_unknown_host_is_default_denied() -> None:
    """And the other branch is pinned too, so the two cannot be confused."""
    with pytest.raises(SourceNotAllowed, match="default-deny"):
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


def test_the_blocked_branch_is_reachable_at_all() -> None:
    """Every blocked host must be denied *as blocked*, for every entry.

    ``BLOCKED_HOSTS`` is small today, but the parametrized cases above name
    three URLs by hand. Iterating the frozenset means a host added to it later
    is held to the same standard without anyone remembering to add a case, and
    an emptied ``BLOCKED_HOSTS`` fails the non-emptiness assertion rather than
    passing a loop over nothing.
    """
    assert BLOCKED_HOSTS, "BLOCKED_HOSTS is empty; the values-based exclusion is gone"
    for host in sorted(BLOCKED_HOSTS):
        with pytest.raises(SourceNotAllowed, match="blocked source"):
            assert_allowed(f"https://{host}/anything")


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
