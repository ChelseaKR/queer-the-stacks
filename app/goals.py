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
    name: str
    current: int
    target: int

    @property
    def pct(self) -> float:
        return min(1.0, self.current / self.target) if self.target > 0 else 0.0

    @property
    def met(self) -> bool:
        return self.target > 0 and self.current >= self.target


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
    """
    out: list[Goal] = []
    if books_target > 0:
        out.append(Goal(f"Books in {wrapped.year}", wrapped.books_finished, books_target))
    if pages_target > 0:
        out.append(Goal(f"Pages in {wrapped.year}", wrapped.pages_read, pages_target))
    if hours_target > 0:
        out.append(Goal(f"Hours in {wrapped.year}", round(wrapped.read_time_hours), hours_target))
    if streak_target > 0:
        out.append(Goal("Longest streak (days)", stats.longest_streak_days, streak_target))
    return tuple(out)
