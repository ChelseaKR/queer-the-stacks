"""Assemble the dashboard view from ingest → stats → Wrapped → recommender.

One place builds the whole picture so the FastAPI server, the static a11y build,
and the CLI all render identical content. The pure :func:`build_view` takes
already-ingested data; :func:`demo_view` walks the full offline demo pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ingest.models import DailyActivity, ReadingState, Recommendation
from ingest.unify import currently_reading, finished
from recommender.eval import PopCandidate
from recommender.lists import CuratedList
from recommender.model import recommend

from app.stats import ReadingStats, compute_stats
from app.wrapped import Wrapped, compute_wrapped


@dataclass(frozen=True)
class DashboardView:
    """Everything the dashboard renders, assembled once."""

    currently_reading: tuple[ReadingState, ...]
    finished: tuple[ReadingState, ...]
    stats: ReadingStats
    wrapped: Wrapped
    recommendations: tuple[Recommendation, ...]
    user: str = "demo"


def _infer_today_and_year(
    states: list[ReadingState], daily_activity: list[DailyActivity]
) -> tuple[int, int]:
    """Derive a deterministic 'today' + Wrapped year from the data itself."""
    import datetime

    today_ordinal = max((d.day_ordinal for d in daily_activity), default=0)
    epoch = datetime.date(1970, 1, 1).toordinal()
    year = datetime.date.fromordinal(epoch + today_ordinal).year if today_ordinal else 1970
    return today_ordinal, year


def build_view(
    states: list[ReadingState],
    daily_activity: list[DailyActivity],
    candidates: tuple[object, ...],
    *,
    lists: tuple[CuratedList, ...] = (),
    user: str = "demo",
) -> DashboardView:
    """Build the dashboard view from unified state + candidates (pure)."""
    today_ordinal, year = _infer_today_and_year(states, daily_activity)
    stats = compute_stats(states, daily_activity, today_ordinal)
    wrapped = compute_wrapped(states, daily_activity, year)
    candidate_books = tuple(c.book for c in candidates)  # type: ignore[attr-defined]
    recs = recommend(states, candidate_books, lists=lists, k=10)
    return DashboardView(
        currently_reading=tuple(currently_reading(states)),
        finished=tuple(finished(states)),
        stats=stats,
        wrapped=wrapped,
        recommendations=tuple(recs),
        user=user,
    )


def view_from_store(store: object, *, user: str = "you") -> DashboardView:
    """Build the dashboard view from persisted derived state in the store.

    Recommendations are drawn from the built-in curated seed catalog (real books
    on cited community lists); live catalog adapters arrive in phase N2.
    """
    from ingest.demo import demo_candidates
    from recommender.lists import DEMO_LISTS

    states = store.load_states()  # type: ignore[attr-defined]
    activity = store.load_daily_activity()  # type: ignore[attr-defined]
    return build_view(states, activity, demo_candidates(), lists=DEMO_LISTS, user=user)


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
