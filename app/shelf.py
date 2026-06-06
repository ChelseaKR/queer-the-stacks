"""Series intelligence and a prioritized to-read shelf.

Both are pure functions over unified reading state. "Up next in a series" finds
books you *own but haven't read* in a series you've already started; the to-read
shelf orders your unread owned books by how well they fit your taste (sourced
themes), with series-continuations floated to the top.
"""

from __future__ import annotations

from dataclasses import dataclass

from ingest.models import ReadingState, ReadingStatus
from recommender.model import TasteProfile, build_taste_profile


@dataclass(frozen=True)
class SeriesNext:
    """An unread owned book that continues a series you've started."""

    series: str
    title: str
    authors: tuple[str, ...]
    series_index: float | None


def _series_index(state: ReadingState) -> float:
    if state.book and state.book.series_index is not None:
        return state.book.series_index
    return 0.0


def series_continuations(states: list[ReadingState]) -> list[SeriesNext]:
    """Unread owned books in series where at least one book is already finished.

    Ordered by series name, then series index, then title — deterministic.
    """
    started: set[str] = {
        s.book.series
        for s in states
        if s.book and s.book.series and s.status is ReadingStatus.FINISHED
    }
    out: list[SeriesNext] = []
    for s in states:
        if s.book and s.book.series in started and s.status is ReadingStatus.UNREAD:
            out.append(
                SeriesNext(
                    series=s.book.series or "",
                    title=s.title,
                    authors=s.authors,
                    series_index=s.book.series_index,
                )
            )
    return sorted(out, key=lambda x: (x.series, _idx(x.series_index), x.title))


def _idx(value: float | None) -> float:
    return value if value is not None else 0.0


def to_read(states: list[ReadingState], taste: TasteProfile | None = None) -> list[ReadingState]:
    """Unread owned books, best taste-fit first; series continuations float up.

    Fit is the count of a book's sourced themes that are in the taste profile, so
    the shelf leans toward what you already love without any inference.
    """
    profile = taste or build_taste_profile(states)
    continuation_titles = {c.title for c in series_continuations(states)}
    unread = [s for s in states if s.status is ReadingStatus.UNREAD and s.book is not None]

    def fit(state: ReadingState) -> int:
        return sum(1 for t in state.theme_tags if t.normalized in profile.theme_weights)

    return sorted(
        unread,
        key=lambda s: (
            0 if s.title in continuation_titles else 1,  # continuations first
            -fit(s),
            s.title,
        ),
    )
