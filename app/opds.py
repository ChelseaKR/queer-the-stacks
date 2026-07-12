"""Render your own shelves as a read-only OPDS 1.2 catalog.

OPDS (Open Publication Distribution System) is the feed format e-reader apps
like KOReader and Readest use to browse a remote catalog over HTTP: a
navigation feed listing sub-catalogs, and one acquisition feed per sub-catalog
listing its books. This module only *renders* — the same separation as
:mod:`app.render` / :mod:`app.view` keep for the HTML dashboard — so it is a
pure function of an already-assembled :class:`~app.view.DashboardView` and is
covered by ordinary unit tests, not the (coverage-omitted) FastAPI wiring in
:mod:`app.server`.

Shelves exposed, one acquisition feed each:

* ``to-read`` — the taste-ranked to-read shelf (:func:`app.shelf.to_read`).
* ``currently-reading`` — books in progress right now, across devices.
* ``series-next`` — unread books continuing a series you've already started.
* ``recommendations`` — hybrid recs; each entry's ``<content>`` carries the
  same sourced "why" shown on the dashboard (never an inferred label — see
  :class:`ingest.models.Explanation`).

``<updated>`` is a fixed epoch, not wall-clock time, so two renders of the same
view are byte-identical — the same guarantee the HTML renderer gives under
``tests/test_reproducibility.py``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional
from urllib.parse import quote
from xml.sax.saxutils import escape

from ingest.models import ReadingState, Recommendation

from app.shelf import SeriesNext

if TYPE_CHECKING:
    from app.view import DashboardView

ATOM_NS = "http://www.w3.org/2005/Atom"
OPDS_NS = "http://opds-spec.org/2010/catalog"
NAV_TYPE = "application/atom+xml;profile=opds-catalog;kind=navigation"
ACQ_TYPE = "application/atom+xml;profile=opds-catalog;kind=acquisition"

#: Fixed epoch used for every ``<updated>``: deterministic, not wall-clock, so
#: the feed stays byte-identical across builds of the same view.
FIXED_UPDATED = "1970-01-01T00:00:00Z"

#: (shelf id, nav-entry title, nav-entry blurb) for the four shelves served,
#: in the order they're listed on the root navigation feed.
SHELVES: tuple[tuple[str, str, str], ...] = (
    ("to-read", "To read", "Unread, owned books ranked by fit to your sourced taste."),
    ("currently-reading", "Currently reading", "Books in progress right now, across devices."),
    ("series-next", "Series next", "Unread books that continue a series you've already started."),
    ("recommendations", "Recommendations", "Hybrid picks, each with a sourced why and citation."),
)

#: Shelf id -> human title, for the acquisition feed's own ``<title>``.
SHELF_TITLES: dict[str, str] = {shelf_id: title for shelf_id, title, _ in SHELVES}


@dataclass(frozen=True)
class OpdsEntry:
    """One catalog entry — pure data; escaped only when rendered to XML."""

    entry_id: str
    title: str
    authors: tuple[str, ...]
    content: str
    updated: str = FIXED_UPDATED


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "book"


def _stable_ids(shelf_id: str, titles: Sequence[str]) -> list[str]:
    """Build ``urn:qts:<shelf>:<slug>`` ids, de-duped with a stable suffix."""
    seen: dict[str, int] = {}
    ids: list[str] = []
    for title in titles:
        slug = _slugify(title)
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        ids.append(f"urn:qts:{shelf_id}:{slug}" if n == 0 else f"urn:qts:{shelf_id}:{slug}-{n + 1}")
    return ids


def _reading_state_entries(
    shelf_id: str, states: Sequence[ReadingState], label: str
) -> list[OpdsEntry]:
    ids = _stable_ids(shelf_id, [s.title for s in states])
    return [
        OpdsEntry(entry_id=entry_id, title=s.title, authors=s.authors, content=label)
        for entry_id, s in zip(ids, states, strict=True)
    ]


def to_read_entries(shelf_id: str, states: Sequence[ReadingState]) -> list[OpdsEntry]:
    """Map the to-read shelf's owned-but-unread books to catalog entries."""
    return _reading_state_entries(shelf_id, states, "On your to-read shelf.")


def currently_reading_entries(shelf_id: str, states: Sequence[ReadingState]) -> list[OpdsEntry]:
    """Map in-progress books to catalog entries."""
    return _reading_state_entries(shelf_id, states, "Currently reading.")


def series_next_entries(shelf_id: str, items: Sequence[SeriesNext]) -> list[OpdsEntry]:
    """Map "up next in a series" picks to catalog entries."""
    ids = _stable_ids(shelf_id, [i.title for i in items])
    entries = []
    for entry_id, item in zip(ids, items, strict=True):
        content = (
            f"Continues the {item.series} series."
            if item.series
            else "Continues a series you've started."
        )
        entries.append(
            OpdsEntry(entry_id=entry_id, title=item.title, authors=item.authors, content=content)
        )
    return entries


def recommendation_entries(shelf_id: str, recs: Sequence[Recommendation]) -> list[OpdsEntry]:
    """Map recommendations to catalog entries, ``<content>`` carrying the sourced why.

    Reuses the same signal kind/detail pairs the dashboard shows under "Why
    recommended" (:func:`app.render._signals_html`) plus the explanation
    summary — never anything beyond what :class:`~ingest.models.Explanation`
    already carries, so the feed can't say more than the sourced why.
    """
    ids = _stable_ids(shelf_id, [r.book.title for r in recs])
    entries = []
    for entry_id, rec in zip(ids, recs, strict=True):
        why = "; ".join(f"{s.kind}: {s.detail}" for s in rec.explanation.signals)
        content = f"{rec.explanation.summary} Why: {why}" if why else rec.explanation.summary
        entries.append(
            OpdsEntry(
                entry_id=entry_id,
                title=rec.book.title,
                authors=rec.book.author_names,
                content=content,
            )
        )
    return entries


def entries_for_shelf(shelf_id: str, view: DashboardView) -> list[OpdsEntry]:
    """Pick the right mapper for one of the four served shelves."""
    if shelf_id == "to-read":
        return to_read_entries(shelf_id, view.to_read)
    if shelf_id == "currently-reading":
        return currently_reading_entries(shelf_id, view.currently_reading)
    if shelf_id == "series-next":
        return series_next_entries(shelf_id, view.series_next)
    if shelf_id == "recommendations":
        return recommendation_entries(shelf_id, view.recommendations)
    raise ValueError(f"unknown OPDS shelf: {shelf_id!r}")


def _author_xml(authors: tuple[str, ...]) -> str:
    if not authors:
        return "<author><name>Unknown</name></author>"
    return "".join(f"<author><name>{escape(a)}</name></author>" for a in authors)


def _entry_xml(entry: OpdsEntry, *, calibre_web_url: Optional[str] = None) -> str:
    alt_link = ""
    if calibre_web_url:
        href = f"{calibre_web_url.rstrip('/')}/search?query={quote(entry.title)}"
        alt_link = f'<link rel="alternate" href="{escape(href)}" type="text/html"/>'
    return (
        "<entry>"
        f"<id>{escape(entry.entry_id)}</id>"
        f"<title>{escape(entry.title)}</title>"
        f"{_author_xml(entry.authors)}"
        f"<updated>{escape(entry.updated)}</updated>"
        f'<content type="text">{escape(entry.content)}</content>'
        f"{alt_link}"
        "</entry>"
    )


def build_root_navigation(view: DashboardView) -> str:
    """Render the root OPDS navigation feed — one ``<entry>`` per shelf feed.

    ``profile=opds-catalog;kind=navigation`` per OPDS 1.2; carries ``rel="self"``
    and ``rel="start"`` links to itself, as OPDS clients expect at the root.
    """
    counts = {shelf_id: len(entries_for_shelf(shelf_id, view)) for shelf_id, _, _ in SHELVES}
    entries = "".join(
        "<entry>"
        f"<title>{escape(title)}</title>"
        f"<id>urn:qts:{escape(shelf_id)}</id>"
        f"<updated>{FIXED_UPDATED}</updated>"
        f'<link rel="subsection" href="/opds/{escape(shelf_id)}" type="{ACQ_TYPE}"/>'
        f'<content type="text">{escape(blurb)} '
        f"({counts[shelf_id]} book{'' if counts[shelf_id] == 1 else 's'}.)</content>"
        "</entry>"
        for shelf_id, title, blurb in SHELVES
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<feed xmlns="{ATOM_NS}" xmlns:opds="{OPDS_NS}">'
        "<id>urn:qts:root</id>"
        "<title>Queer the Stacks</title>"
        f"<updated>{FIXED_UPDATED}</updated>"
        f'<link rel="self" href="/opds" type="{NAV_TYPE}"/>'
        f'<link rel="start" href="/opds" type="{NAV_TYPE}"/>'
        f"{entries}"
        "</feed>"
    )


def build_shelf_acquisition(
    shelf_id: str,
    title: str,
    entries: Sequence[OpdsEntry],
    *,
    calibre_web_url: Optional[str] = None,
) -> str:
    """Render one acquisition feed: one ``<entry>`` per book on this shelf.

    ``calibre_web_url`` is config-driven (never hardcoded) and only ever
    embedded as a link's ``href`` text in the returned XML — it is never
    fetched here, so no egress is introduced. Omit it (leave ``None``) to
    render entries without the optional alternate link.
    """
    body = "".join(_entry_xml(e, calibre_web_url=calibre_web_url) for e in entries)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<feed xmlns="{ATOM_NS}" xmlns:opds="{OPDS_NS}">'
        f"<id>urn:qts:{escape(shelf_id)}</id>"
        f"<title>{escape(title)}</title>"
        f"<updated>{FIXED_UPDATED}</updated>"
        f'<link rel="self" href="/opds/{escape(shelf_id)}" type="{ACQ_TYPE}"/>'
        f'<link rel="start" href="/opds" type="{NAV_TYPE}"/>'
        f"{body}"
        "</feed>"
    )
