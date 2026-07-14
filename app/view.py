"""Assemble the dashboard view from ingest → stats → Wrapped → recommender.

One place builds the whole picture so the FastAPI server, the static a11y build,
and the CLI all render identical content. The pure :func:`build_view` takes
already-ingested data; :func:`demo_view` walks the full offline demo pipeline.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ingest.models import DailyActivity, ReadingState, Recommendation
from ingest.unify import currently_reading, finished
from recommender.eval import PopCandidate
from recommender.hybrid import recommend_hybrid
from recommender.lists import CuratedList

from app.diversity import DEFAULT_DIMENSIONS, DiversityReport, compute_diversity, load_lens_config
from app.forecast import Forecast, forecast_book
from app.goals import Goal, compute_goals
from app.shelf import SeriesNext, series_continuations, to_read
from app.stats import ReadingStats, compute_stats
from app.wrapped import Wrapped, compute_wrapped

# How old the persisted refresh stamp can get before the dashboard calls it
# stale. A module constant (not a magic number inline) so tests can exercise
# the boundary without patching.
STALE_AFTER_SECONDS = 7 * 24 * 60 * 60  # 7 days


@dataclass(frozen=True)
class BookForecast:
    """A currently-reading book paired with its time-to-finish forecast."""

    title: str
    authors: tuple[str, ...]
    forecast: Forecast


@dataclass(frozen=True)
class DashboardView:
    """Everything the dashboard renders, assembled once."""

    currently_reading: tuple[ReadingState, ...]
    finished: tuple[ReadingState, ...]
    stats: ReadingStats
    wrapped: Wrapped
    recommendations: tuple[Recommendation, ...]
    forecasts: tuple[BookForecast, ...] = ()
    series_next: tuple[SeriesNext, ...] = ()
    to_read: tuple[ReadingState, ...] = ()
    library: tuple[ReadingState, ...] = ()
    goals: tuple[Goal, ...] = ()
    diversity: Optional[DiversityReport] = None
    authored_lists: tuple[CuratedList, ...] = ()
    user: str = "demo"
    refreshed_at: Optional[int] = None
    stale: bool = False


def _infer_today_and_year(
    states: list[ReadingState], daily_activity: list[DailyActivity]
) -> tuple[int, int]:
    """Derive a deterministic 'today' + Wrapped year from the data itself."""
    import datetime

    today_ordinal = max((d.day_ordinal for d in daily_activity), default=0)
    epoch = datetime.date(1970, 1, 1).toordinal()
    year = datetime.date.fromordinal(epoch + today_ordinal).year if today_ordinal else 1970
    return today_ordinal, year


def _remaining_pages(state: ReadingState) -> int:
    """Pages left in a book from its reading stat; 0 when it can't be known.

    ``forecast_book`` treats a non-positive remaining count as unestimable, so a
    book with no page stat honestly reports "not enough recent reading to
    estimate" rather than a guessed range.
    """
    stat = state.stat
    if stat is None or stat.total_pages <= 0:
        return 0
    return max(0, stat.total_pages - stat.pages_read)


def build_view(
    states: list[ReadingState],
    daily_activity: list[DailyActivity],
    candidates: tuple[object, ...],
    *,
    lists: tuple[CuratedList, ...] = (),
    authored_lists: tuple[CuratedList, ...] = (),
    user: str = "demo",
    aperture_strength: float = 0.0,
    use_embeddings: bool = False,
    dnf_signals: bool = False,
    goal_books: int = 0,
    goal_pages: int = 0,
    goal_hours: int = 0,
    goal_streak_days: int = 0,
    lens_dimensions: tuple[tuple[str, frozenset[str]], ...] = DEFAULT_DIMENSIONS,
    lens_source: str = "built-in defaults",
    lens_warning: Optional[str] = None,
    hide_sensitive_descriptors: bool = False,
    refreshed_at: Optional[int] = None,
    now: Optional[int] = None,
) -> DashboardView:
    """Build the dashboard view from unified state + candidates (pure).

    ``refreshed_at`` is the persisted store stamp (epoch seconds), if any;
    ``now`` defaults to the wall clock but is overridable so staleness is
    testable without patching time. Staleness is silent (``False``) when
    there is no stamp at all — "never refreshed" is its own, distinct state,
    rendered as text rather than the staleness banner.
    """
    today_ordinal, year = _infer_today_and_year(states, daily_activity)
    stats = compute_stats(states, daily_activity, today_ordinal)
    wrapped = compute_wrapped(states, daily_activity, year)
    goals = compute_goals(
        stats,
        wrapped,
        books_target=goal_books,
        pages_target=goal_pages,
        hours_target=goal_hours,
        streak_target=goal_streak_days,
    )
    diversity = compute_diversity(
        states,
        lens_dimensions,
        lens_source=lens_source,
        lens_warning=lens_warning,
        hide_sensitive=hide_sensitive_descriptors,
    )
    candidate_books = tuple(c.book for c in candidates)  # type: ignore[attr-defined]
    recs = recommend_hybrid(
        states,
        candidate_books,
        lists=lists,
        k=10,
        aperture_strength=aperture_strength,
        use_embeddings=use_embeddings,
        dnf_signals=dnf_signals,
    )
    library = sorted(states, key=lambda s: (s.title.lower(), s.authors))
    reading_now = tuple(currently_reading(states))
    forecasts = tuple(
        BookForecast(
            title=s.title,
            authors=s.authors,
            forecast=forecast_book(_remaining_pages(s), daily_activity),
        )
        for s in reading_now
    )
    stale = False
    if refreshed_at is not None:
        current = int(time.time()) if now is None else now
        stale = (current - refreshed_at) > STALE_AFTER_SECONDS
    return DashboardView(
        currently_reading=reading_now,
        finished=tuple(finished(states)),
        stats=stats,
        wrapped=wrapped,
        recommendations=tuple(recs),
        forecasts=forecasts,
        series_next=tuple(series_continuations(states)),
        to_read=tuple(to_read(states)),
        library=tuple(library),
        goals=goals,
        diversity=diversity,
        authored_lists=authored_lists,
        user=user,
        refreshed_at=refreshed_at,
        stale=stale,
    )


def render_view(view: DashboardView) -> str:
    """Render a :class:`DashboardView` to HTML (one place, used everywhere)."""
    from app.render import render_dashboard

    return render_dashboard(
        view.currently_reading,
        view.finished,
        view.stats,
        view.wrapped,
        view.recommendations,
        forecasts=view.forecasts,
        series_next=view.series_next,
        to_read=view.to_read,
        library=view.library,
        goals=view.goals,
        diversity=view.diversity,
        authored_lists=view.authored_lists,
        user=view.user,
        refreshed_at=view.refreshed_at,
        stale=view.stale,
    )


def view_from_store(
    store: object,
    *,
    user: str = "you",
    aperture_strength: float = 0.0,
    use_embeddings: bool = False,
    dnf_signals: bool = False,
    goal_books: int = 0,
    goal_pages: int = 0,
    goal_hours: int = 0,
    goal_streak_days: int = 0,
    lens_config: Optional[Path] = None,
    hide_sensitive_descriptors: bool = False,
    authored_lists: tuple[CuratedList, ...] = (),
) -> DashboardView:
    """Build the dashboard view from persisted derived state in the store.

    Recommendations draw on the built-in curated seed catalog (real books on cited
    community lists) plus the hybrid signals; live catalog candidate pools land
    when configured (phase N2 adapters).

    ``lens_config``, if given, points at a validated ``[[lenses]]`` TOML file
    (see :func:`app.diversity.load_lens_config`) that overrides the built-in
    diversity-lens grouping; any read/parse/validation failure degrades to the
    built-in defaults with a visible warning surfaced in the diversity section,
    never a blank one.
    """
    from ingest.demo import demo_candidates
    from recommender.lists import DEMO_LISTS

    states = store.load_states()  # type: ignore[attr-defined]
    activity = store.load_daily_activity()  # type: ignore[attr-defined]
    lenses = load_lens_config(lens_config)
    refreshed_at = store.refreshed_at()  # type: ignore[attr-defined]
    return build_view(
        states,
        activity,
        demo_candidates(),
        lists=DEMO_LISTS,
        authored_lists=authored_lists,
        user=user,
        aperture_strength=aperture_strength,
        use_embeddings=use_embeddings,
        dnf_signals=dnf_signals,
        goal_books=goal_books,
        goal_pages=goal_pages,
        goal_hours=goal_hours,
        goal_streak_days=goal_streak_days,
        lens_dimensions=lenses.dimensions,
        lens_source=lenses.source,
        lens_warning=lenses.warning,
        hide_sensitive_descriptors=hide_sensitive_descriptors,
        refreshed_at=refreshed_at,
    )


def demo_view(workdir: Path) -> DashboardView:
    """Walk the full offline demo pipeline and return a ready-to-render view."""
    from ingest.calibre import load_library
    from ingest.demo import DEMO_USER, build_demo_dbs, demo_candidates, demo_kosync
    from ingest.koreader import load_daily_activity, load_stats
    from ingest.unify import unify
    from recommender.lists import DEMO_LISTS

    workdir = Path(workdir)
    metadata_db, statistics_db = build_demo_dbs(workdir)
    snap = workdir / "snapshots"
    books = load_library(metadata_db, snap, retrieved_at="2026-06-05")
    stats = load_stats(statistics_db, snap)
    activity = load_daily_activity(statistics_db, snap)
    states = unify(books, stats, demo_kosync())
    candidates: tuple[PopCandidate, ...] = demo_candidates()
    return build_view(states, activity, candidates, lists=DEMO_LISTS, user=DEMO_USER)
