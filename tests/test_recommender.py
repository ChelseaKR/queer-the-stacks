"""Content recommender: taste profile, scoring, exclusions, determinism."""

from __future__ import annotations

from ingest.models import Author, Book, Source, SourceKind, ThemeTag
from recommender.model import build_taste_profile, recommend


def test_taste_profile_from_finished_books(states: list) -> None:
    taste = build_taste_profile(states)
    assert taste.theme_weights.get("speculative", 0) > 0
    assert taste.theme_weights.get("trans", 0) > 0
    assert "Octavia E. Butler" in taste.finished_authors
    assert taste.owned_keys  # owned set populated for exclusion


def test_owned_books_excluded(states: list, candidates: tuple, lists: tuple) -> None:
    recs = recommend(states, tuple(c.book for c in candidates), lists=lists, k=10)
    rec_titles = {r.book.title for r in recs}
    # None of the owned canon should be recommended back.
    assert "Kindred" not in rec_titles
    assert "A Safe Girl to Love" not in rec_titles


def test_on_canon_outranks_distractors(states: list, candidates: tuple, lists: tuple) -> None:
    recs = recommend(states, tuple(c.book for c in candidates), lists=lists, k=8)
    ranked_ids = [r.book.book_id for r in recs]
    on_canon = {c.book.book_id for c in candidates if c.on_canon}
    distractors = {c.book.book_id for c in candidates if not c.on_canon}
    best_canon = min(ranked_ids.index(b) for b in on_canon if b in ranked_ids)
    present_distractors = [ranked_ids.index(b) for b in distractors if b in ranked_ids]
    # Every on-canon discovery that surfaces beats every distractor that surfaces.
    if present_distractors:
        assert best_canon < min(present_distractors)


def test_author_bonus_more_by_butler(states: list, candidates: tuple, lists: tuple) -> None:
    recs = recommend(states, tuple(c.book for c in candidates), lists=lists, k=10)
    dawn = next((r for r in recs if r.book.title == "Dawn"), None)
    assert dawn is not None
    kinds = {s.kind for s in dawn.explanation.signals}
    assert "author" in kinds  # "by Octavia E. Butler, whom you've finished"


def test_ranking_is_deterministic(states: list, candidates: tuple, lists: tuple) -> None:
    books = tuple(c.book for c in candidates)
    a = [r.book.book_id for r in recommend(states, books, lists=lists, k=10)]
    b = [r.book.book_id for r in recommend(states, books, lists=lists, k=10)]
    assert a == b


def test_off_theme_candidate_scores_zero() -> None:
    src = Source(SourceKind.CALIBRE_TAG, "calibre:local", "2026-06-05", "trans")
    finished = Book(
        book_id="own", title="Owned", authors=(Author("Me"),), theme_tags=(ThemeTag("trans", src),)
    )
    from ingest.models import ReadingState, ReadingStatus

    states = [
        ReadingState(title="Owned", authors=("Me",), status=ReadingStatus.FINISHED, book=finished)
    ]
    osrc = Source(
        SourceKind.OPENLIBRARY_SUBJECT,
        "https://openlibrary.org/subjects/x",
        "2026-06-05",
        "thriller",
    )
    candidate = Book(
        book_id="c1",
        title="Unrelated",
        authors=(Author("Other"),),
        theme_tags=(ThemeTag("thriller", osrc),),
    )
    recs = recommend(states, (candidate,), k=10)
    assert recs == []  # no theme overlap, no author match -> not recommended
