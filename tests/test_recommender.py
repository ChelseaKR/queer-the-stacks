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


def test_untagged_author_match_does_not_crash_the_shelf(states: list) -> None:
    """A candidate the catalog returned with no tag block must not raise.

    `parse_hardcover_books` and `parse_bookwyrm_list` both build a Book with
    `theme_tags=()` when the response carries no tag block, so an untagged
    candidate is ordinary catalog data, not a malformed fixture. Matched only
    on a finished author it scores above zero (the author bonus) but carries
    no source, and `build_explanation` refuses it — correctly, since there is
    nothing honest to cite. `recommender.explain.near_misses` already screens
    exactly this candidate out for exactly this reason; the shelf must too.
    """
    from recommender.catalogs import parse_bookwyrm_list, parse_hardcover_books

    untagged = parse_hardcover_books(
        {
            "data": {
                "books": [
                    {
                        "title": "An Untagged Catalog Book",
                        "slug": "untagged-catalog-book",
                        "contributions": [{"author": {"name": "Octavia E. Butler"}}],
                    }
                ]
            }
        },
        "hardcover.app",
        "2026-09-06",
    ) + parse_bookwyrm_list(
        {
            "books": [
                {"id": "bw1", "title": "Another Untagged Book", "authors": ["Octavia E. Butler"]}
            ]
        },
        "bookwyrm.social",
        "2026-09-06",
    )
    assert all(not b.theme_tags for b in untagged)

    recs = recommend(states, untagged, k=10)
    assert recs == []


def test_an_untagged_candidate_does_not_hide_the_tagged_ones(
    states: list, candidates: tuple, lists: tuple
) -> None:
    """The skip removes only the uncitable candidate, not the whole shelf."""
    tagged = tuple(c.book for c in candidates)
    baseline = [r.book.book_id for r in recommend(states, tagged, lists=lists, k=10)]
    assert baseline

    untagged = Book(
        book_id="hardcover:untagged",
        title="An Untagged Catalog Book",
        authors=(Author("Octavia E. Butler"),),
        theme_tags=(),
    )
    with_untagged = [
        r.book.book_id for r in recommend(states, (untagged, *tagged), lists=lists, k=10)
    ]
    assert with_untagged == baseline


def test_an_untagged_book_on_a_curated_list_is_still_recommendable(
    states: list, lists: tuple
) -> None:
    """The list membership is a real citation, so this candidate keeps its place."""
    listed = Book(
        book_id=lists[0].book_ids[0],
        title="Untagged But Listed",
        authors=(Author("Octavia E. Butler"),),
        theme_tags=(),
    )
    recs = recommend(states, (listed,), lists=lists, k=5)
    assert [r.book.book_id for r in recs] == [listed.book_id]
    assert recs[0].explanation.sources
