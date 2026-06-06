"""Reading-stats math: totals, streaks, and the sourced theme/genre mix.

Pure functions over the unified :class:`~ingest.models.ReadingState` list plus
per-day :class:`~ingest.models.DailyActivity`. Everything is deterministic — the
"today" reference for the current streak is injected, never read from the wall
clock — so stats reconcile exactly with KOReader and are reproducible.

The theme mix is built only from *sourced* theme tags; it never invents a theme
and never labels an author.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ingest.models import DailyActivity, ReadingState, ReadingStatus


@dataclass(frozen=True)
class ReadingStats:
    """The numbers the dashboard's stats panel renders."""

    books_finished: int
    books_reading: int
    pages_read: int
    read_time_seconds: int
    current_streak_days: int
    longest_streak_days: int
    active_days: int
    total_highlights: int = 0
    theme_mix: tuple[tuple[str, int], ...] = ()  # (theme label, count), desc
    top_authors: tuple[tuple[str, int], ...] = ()  # (author, finished count), desc
    most_annotated: tuple[tuple[str, int], ...] = ()  # (title, highlight count), desc

    @property
    def read_time_hours(self) -> float:
        return round(self.read_time_seconds / 3600, 1)


def _streaks(days: list[DailyActivity], today_ordinal: int) -> tuple[int, int]:
    """Return (current_streak, longest_streak) from active-day ordinals.

    The current streak counts back from ``today_ordinal`` (or yesterday, so a day
    you simply haven't read *yet* doesn't break it); the longest streak is the
    longest run of consecutive active days anywhere in history.
    """
    ordinals = sorted({d.day_ordinal for d in days})
    if not ordinals:
        return 0, 0

    longest = run = 1
    for prev, cur in zip(ordinals, ordinals[1:], strict=False):
        run = run + 1 if cur == prev + 1 else 1
        longest = max(longest, run)

    active = set(ordinals)
    current = 0
    # Allow today to be "not yet read" without breaking the streak.
    cursor = today_ordinal if today_ordinal in active else today_ordinal - 1
    while cursor in active:
        current += 1
        cursor -= 1
    return current, longest


def compute_stats(
    states: list[ReadingState],
    daily_activity: list[DailyActivity],
    today_ordinal: int,
) -> ReadingStats:
    """Compute the full reading-stats summary deterministically."""
    finished = [s for s in states if s.status is ReadingStatus.FINISHED]
    reading = [s for s in states if s.status is ReadingStatus.READING]

    pages = sum(s.stat.pages_read for s in states if s.stat)
    seconds = sum(s.stat.read_time_seconds for s in states if s.stat)

    theme_counter: Counter[str] = Counter()
    for s in states:
        if s.status is ReadingStatus.UNREAD:
            continue
        for tag in s.theme_tags:
            theme_counter[tag.normalized] += 1

    author_counter: Counter[str] = Counter()
    for s in finished:
        for author in s.authors:
            author_counter[author] += 1

    current, longest = _streaks(daily_activity, today_ordinal)

    total_highlights = sum(s.stat.highlights for s in states if s.stat)
    annotated = Counter(
        {s.title: s.stat.highlights for s in states if s.stat and s.stat.highlights > 0}
    )

    return ReadingStats(
        books_finished=len(finished),
        books_reading=len(reading),
        pages_read=pages,
        read_time_seconds=seconds,
        current_streak_days=current,
        longest_streak_days=longest,
        active_days=len({d.day_ordinal for d in daily_activity}),
        total_highlights=total_highlights,
        theme_mix=tuple(theme_counter.most_common()),
        top_authors=tuple(author_counter.most_common(5)),
        most_annotated=tuple(annotated.most_common(5)),
    )
