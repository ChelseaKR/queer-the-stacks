"""Per-shelf near-miss surface (EXP-02 follow-up): wiring `explain_absence`
into the dashboard as "why not others?" for the best candidates that didn't
make the recommendation shelf.
"""

from __future__ import annotations

from ingest.models import Author, Book, Source, SourceKind, ThemeTag
from recommender.explain import near_misses


def test_near_misses_excludes_already_recommended_and_owned(
    states: list, candidates: tuple, lists: tuple
) -> None:
    all_ids = {c.book.book_id for c in candidates}
    exclude_ids = frozenset(list(all_ids)[:2])
    misses = near_misses(states, tuple(c.book for c in candidates), lists, exclude_ids, limit=50)

    miss_ids = {m.book.book_id for m in misses}
    assert miss_ids.isdisjoint(exclude_ids)
    # Every near miss is sourced (the transparency guardrail every explanation
    # on this dashboard carries).
    for m in misses:
        assert m.explanation.signals
        assert m.explanation.sources


def test_near_misses_respects_limit_and_is_ranked_best_first(
    states: list, candidates: tuple, lists: tuple
) -> None:
    all_books = tuple(c.book for c in candidates)
    misses = near_misses(states, all_books, lists, frozenset(), limit=3)
    assert len(misses) <= 3

    from recommender.model import build_taste_profile, score_candidate

    taste = build_taste_profile(states)
    scores = [score_candidate(taste, m.book, lists)[0] for m in misses]
    assert scores == sorted(scores, reverse=True)


def test_near_misses_is_deterministic(states: list, candidates: tuple, lists: tuple) -> None:
    all_books = tuple(c.book for c in candidates)
    first = near_misses(states, all_books, lists, frozenset(), limit=5)
    second = near_misses(states, all_books, lists, frozenset(), limit=5)
    assert [m.book.book_id for m in first] == [m.book.book_id for m in second]


def test_near_misses_skips_a_candidate_with_no_sourced_signal_to_cite(states: list) -> None:
    """A book with zero theme tags and no list hit has nothing an explanation
    can honestly cite (an author match alone carries no source) — it's
    skipped rather than crashing on Explanation's non-empty-sources guardrail.
    """
    untagged = Book(
        book_id="ol:untagged-mystery",
        title="An Untagged Book",
        authors=(Author("Nobody Recorded"),),
        theme_tags=(),
    )
    misses = near_misses(states, (untagged,), (), frozenset(), limit=5)
    assert misses == []


def test_near_misses_includes_a_book_whose_only_signal_is_a_list_hit(
    states: list, lists: tuple
) -> None:
    """An untagged book that's on a curated list still has a real source (the
    list itself) to cite, so it's a legitimate near miss.
    """
    on_a_list_id = lists[0].book_ids[0]
    listed = Book(
        book_id=on_a_list_id,
        title="Untagged But Listed",
        authors=(Author("Nobody Recorded"),),
        theme_tags=(),
    )
    misses = near_misses(states, (listed,), lists, frozenset(), limit=5)
    assert len(misses) == 1
    assert any(s.kind == "list" for s in misses[0].explanation.signals)


def test_near_misses_excludes_owned_book_by_normalized_key(states: list) -> None:
    src = Source(
        SourceKind.OPENLIBRARY_SUBJECT,
        "https://openlibrary.org/subjects/x",
        "2026-06-05",
        "speculative",
    )
    owned_book = Book(
        book_id="ol:kindred-again",
        title="Kindred",
        authors=(Author("Octavia E. Butler"),),
        theme_tags=(ThemeTag("speculative", src),),
    )
    misses = near_misses(states, (owned_book,), (), frozenset(), limit=5)
    assert misses == []
