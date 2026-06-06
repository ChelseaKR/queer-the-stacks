"""Search + browse over your library: pure filters and facet listings.

These power the dashboard's "Browse your library" section and the ``/browse``
route. Filtering is by *sourced* theme, author, series, status, and a free-text
title/author query — all over local data, deterministic, never inferred.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ingest.models import ReadingState, ReadingStatus


@dataclass(frozen=True)
class Facets:
    """The distinct values available to filter by, each sorted."""

    themes: tuple[str, ...]
    authors: tuple[str, ...]
    series: tuple[str, ...]
    statuses: tuple[str, ...]


def available_facets(states: list[ReadingState]) -> Facets:
    themes: set[str] = set()
    authors: set[str] = set()
    series: set[str] = set()
    for s in states:
        themes.update(t.normalized for t in s.theme_tags)
        authors.update(s.authors)
        if s.book and s.book.series:
            series.add(s.book.series)
    return Facets(
        themes=tuple(sorted(themes)),
        authors=tuple(sorted(authors)),
        series=tuple(sorted(series)),
        statuses=tuple(st.value for st in ReadingStatus),
    )


def filter_states(
    states: list[ReadingState],
    *,
    theme: Optional[str] = None,
    author: Optional[str] = None,
    series: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
) -> list[ReadingState]:
    """Return the states matching every provided filter (AND semantics)."""
    out = states
    if theme:
        needle = theme.strip().lower()
        out = [s for s in out if needle in {t.normalized for t in s.theme_tags}]
    if author:
        needle = author.strip().lower()
        out = [s for s in out if any(needle in a.lower() for a in s.authors)]
    if series:
        needle = series.strip().lower()
        out = [s for s in out if s.book and s.book.series and needle == s.book.series.lower()]
    if status:
        needle = status.strip().lower()
        out = [s for s in out if s.status.value == needle]
    if q:
        needle = q.strip().lower()
        out = [
            s
            for s in out
            if needle in s.title.lower() or any(needle in a.lower() for a in s.authors)
        ]
    return out
