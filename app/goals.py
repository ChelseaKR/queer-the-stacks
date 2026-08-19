"""Local reading-goal tracking — computed on-device, shared with no one.

Targets come from config (books / pages / time / streak). Progress is computed
against this year's Wrapped + current stats. A target of 0 means "no goal set"
and is omitted, so the Goals section only appears when you actually set one.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.stats import ReadingStats
from app.wrapped import Wrapped


@dataclass(frozen=True)
class Goal:
    """One target and progress toward it.

    :attr:`measurable` is False when nothing measured the metric behind the
    goal. Progress against an unmeasured metric is not 0% — it is unknown, and
    "Books in 1970: 0 / 52 — 0%" told a reader with no KOReader source that they
    were failing a goal nothing had checked.
    """

    name: str
    current: int
    target: int
    #: A reading record exists for this goal's metric. When False, :attr:`current`
    #: is structural padding and every surface must say so instead of rendering it.
    measurable: bool = True

    @property
    def pct(self) -> float:
        return min(1.0, self.current / self.target) if self.target > 0 else 0.0

    @property
    def met(self) -> bool:
        return self.measurable and self.target > 0 and self.current >= self.target


def compute_goals(
    stats: ReadingStats,
    wrapped: Wrapped,
    *,
    books_target: int = 0,
    pages_target: int = 0,
    hours_target: int = 0,
    streak_target: int = 0,
) -> tuple[Goal, ...]:
    """Return the goals that were actually set, with current progress.

    Time goals are tracked in whole hours read this year (rounded from the
    sourced KOReader read-time); streak goals track your longest streak.

    A year-scoped goal is named for its year only when there is one. With no
    reading source the year is unknown, so the name drops it rather than
    inheriting the epoch — "Books in 1970" named a year the reader never saw a
    single figure from.
    """
    out: list[Goal] = []
    scope = f" in {wrapped.year}" if wrapped.measured else ""
    if books_target > 0:
        out.append(Goal(f"Books{scope}", wrapped.books_finished, books_target, wrapped.measured))
    if pages_target > 0:
        out.append(Goal(f"Pages{scope}", wrapped.pages_read, pages_target, wrapped.measured))
    if hours_target > 0:
        out.append(
            Goal(f"Hours{scope}", round(wrapped.read_time_hours), hours_target, wrapped.measured)
        )
    if streak_target > 0:
        # Streaks come from per-day activity via `stats`, not from the Wrapped
        # year, so they carry their own measured flag.
        out.append(
            Goal("Longest streak (days)", stats.longest_streak_days, streak_target, stats.measured)
        )
    return tuple(out)
