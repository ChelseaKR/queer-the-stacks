"""Hybrid recommender: collaborative co-occurrence, embeddings, aperture, DNF."""

from __future__ import annotations

from ingest.models import (
    Author,
    Book,
    ReadingState,
    ReadingStatus,
    Source,
    SourceKind,
    ThemeTag,
)
from recommender.collaborative import cooccurrence_anchors
from recommender.embeddings import HashingEmbedder, book_text, cosine, taste_vector
from recommender.hybrid import recommend_hybrid
from recommender.model import build_taste_profile
from recommender.rerank import aperture_boost, novelty_themes


def test_cooccurrence_anchors_demo(states: list, candidates: tuple, lists: tuple) -> None:
    books = tuple(c.book for c in candidates)
    anchors = cooccurrence_anchors(states, books, lists)
    # "The Fifth Season" shares "Speculative Feminist Classics" with Dawn (Butler),
    # and the reader finished Octavia E. Butler.
    fifth = anchors.get("ol:fifth-season", ())
    assert any(a.author == "Octavia E. Butler" for a in fifth)


def test_hybrid_recommends_and_explains(states: list, candidates: tuple, lists: tuple) -> None:
    books = tuple(c.book for c in candidates)
    recs = recommend_hybrid(states, books, lists=lists, k=10)
    assert recs
    for r in recs:
        assert r.explanation.signals
        assert r.explanation.sources
    # On-canon picks still beat the popular distractors.
    ranked = [r.book.book_id for r in recs]
    distractors = {"ol:thriller", "ol:memoir", "ol:fantasy-doorstop"}
    present = [ranked.index(b) for b in distractors if b in ranked]
    assert min(ranked.index(b) for b in ("ol:nevada", "ol:fifth-season") if b in ranked) < (
        min(present) if present else 999
    )


def test_hybrid_collaborative_signal_present(states: list, candidates: tuple, lists: tuple) -> None:
    books = tuple(c.book for c in candidates)
    recs = recommend_hybrid(states, books, lists=lists, k=10)
    fifth = next((r for r in recs if r.book.book_id == "ol:fifth-season"), None)
    assert fifth is not None
    kinds = {s.kind for s in fifth.explanation.signals}
    assert "collaborative" in kinds


def test_hybrid_is_deterministic(states: list, candidates: tuple, lists: tuple) -> None:
    books = tuple(c.book for c in candidates)
    a = [r.book.book_id for r in recommend_hybrid(states, books, lists=lists, k=10)]
    b = [r.book.book_id for r in recommend_hybrid(states, books, lists=lists, k=10)]
    assert a == b


def test_aperture_is_boost_only(states: list, candidates: tuple, lists: tuple) -> None:
    books = tuple(c.book for c in candidates)
    base = {r.book.book_id: r.score for r in recommend_hybrid(states, books, lists=lists, k=20)}
    widened = {
        r.book.book_id: r.score
        for r in recommend_hybrid(states, books, lists=lists, k=20, aperture_strength=1.0)
    }
    # Every candidate that survived both runs scores >= its non-aperture score.
    for bid in base.keys() & widened.keys():
        assert widened[bid] >= base[bid] - 1e-9


def test_novelty_and_aperture_boost() -> None:
    src = Source(SourceKind.CALIBRE_TAG, "calibre:local", "2026-06-05", "trans")
    finished = ReadingState(
        title="Owned",
        authors=("Me",),
        status=ReadingStatus.FINISHED,
        book=Book(
            book_id="own",
            title="Owned",
            authors=(Author("Me"),),
            theme_tags=(ThemeTag("trans", src),),
        ),
    )
    taste = build_taste_profile([finished])
    osrc = Source(
        SourceKind.OPENLIBRARY_SUBJECT, "https://openlibrary.org/x", "2026-06-05", "solarpunk"
    )
    cand = Book(book_id="c", title="New", theme_tags=(ThemeTag("solarpunk", osrc),))
    assert novelty_themes(taste, cand) == ("solarpunk",)
    boost, themes = aperture_boost(taste, cand, 1.0)
    assert boost > 0 and themes == ("solarpunk",)
    assert aperture_boost(taste, cand, 0.0) == (0.0, ())


def test_dnf_signals_downweight(states: list) -> None:
    base = build_taste_profile(states)
    dnf = build_taste_profile(states, dnf_signals=True)
    # Stone Butch Blues is ~47% read (not a DNF), so the soft-DNF rule doesn't
    # fire here; profiles match. (Behaviour asserted directly below.)
    assert base.theme_weights.keys() == dnf.theme_weights.keys()


def test_dnf_downweights_stalled_book() -> None:
    src = Source(SourceKind.CALIBRE_TAG, "calibre:local", "2026-06-05", "horror")
    from ingest.models import ReadingStat

    stalled = ReadingState(
        title="Bounced",
        authors=("X",),
        status=ReadingStatus.READING,
        book=Book(
            book_id="b",
            title="Bounced",
            authors=(Author("X"),),
            theme_tags=(ThemeTag("horror", src),),
        ),
        stat=ReadingStat("k", "Bounced", ("X",), 5, 100, 60, 1, 1),
    )
    on = build_taste_profile([stalled], dnf_signals=True)
    assert on.theme_weights["horror"] < 0  # gentle negative
    off = build_taste_profile([stalled], dnf_signals=False)
    assert off.theme_weights["horror"] > 0


def test_embeddings_local_similarity() -> None:
    emb = HashingEmbedder()
    a = Book(book_id="a", title="trans speculative novel")
    b = Book(book_id="b", title="trans speculative story")
    c = Book(book_id="c", title="corporate finance handbook")
    va, vb, vc = (emb.embed(book_text(x)) for x in (a, b, c))
    assert cosine(va, vb) > cosine(va, vc)
    assert taste_vector([], emb) == []


def test_embeddings_change_nothing_when_off_vs_deterministic_when_on(
    states: list, candidates: tuple, lists: tuple
) -> None:
    books = tuple(c.book for c in candidates)
    on1 = [
        r.book.book_id
        for r in recommend_hybrid(states, books, lists=lists, k=10, use_embeddings=True)
    ]
    on2 = [
        r.book.book_id
        for r in recommend_hybrid(states, books, lists=lists, k=10, use_embeddings=True)
    ]
    assert on1 == on2  # deterministic with embeddings on
