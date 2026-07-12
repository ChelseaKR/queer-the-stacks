"""Counterfactual guardrail — every candidate gets a sourced "why not" (EXP-02).

`explain_absence` is the audit-mode twin of `build_explanation`: it never
skips a candidate, and its wording only ever cites sourced tags, curated
lists, and authorship — the same honesty guardrail as the "why" shown for
winners.
"""

from __future__ import annotations

from ingest.models import Author, Book, Source, SourceKind, ThemeTag
from recommender.explain import explain_absence
from recommender.model import build_taste_profile

#: The only signal kinds an absence explanation may emit (sourced-only guardrail).
PERMITTED_ABSENCE_KINDS = {"theme", "author", "list", "collaborative", "aperture", "excluded"}


def test_every_candidate_gets_a_sourced_absence_explanation(
    states: list, candidates: tuple, lists: tuple
) -> None:
    taste = build_taste_profile(states)
    for c in candidates:
        explanation = explain_absence(taste, c.book, lists)
        assert explanation.signals, f"{c.book.title} has no why-not"
        assert explanation.sources, f"{c.book.title} has no source"
        assert explanation.summary.strip()


def test_owned_book_is_flagged_excluded(states: list) -> None:
    taste = build_taste_profile(states)
    # "Kindred" by Octavia E. Butler is a finished/owned book in the demo library.
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
    explanation = explain_absence(taste, owned_book, ())
    details = {s.detail for s in explanation.signals}
    assert "excluded: already on your shelf" in details


def test_no_overlap_and_no_list_yield_counterfactual_signals(states: list) -> None:
    taste = build_taste_profile(states)
    src = Source(
        SourceKind.OPENLIBRARY_SUBJECT,
        "https://openlibrary.org/subjects/y",
        "2026-06-05",
        "thriller",
    )
    off_theme = Book(
        book_id="ol:off-theme",
        title="Totally Unrelated",
        authors=(Author("Some Other Author"),),
        theme_tags=(ThemeTag("thriller", src),),
    )
    explanation = explain_absence(taste, off_theme, ())
    details = {s.detail for s in explanation.signals}
    assert "no sourced tags overlap your taste" in details
    assert "would rise if on a cited list" in details
    assert "no finished-author match" in details


def test_absence_signal_kinds_are_sourced_only(
    states: list, candidates: tuple, lists: tuple
) -> None:
    taste = build_taste_profile(states)
    for c in candidates:
        explanation = explain_absence(taste, c.book, lists)
        for signal in explanation.signals:
            assert signal.kind in PERMITTED_ABSENCE_KINDS, (
                f"{c.book.title}: unexpected signal kind {signal.kind!r}"
            )
        for source in explanation.sources:
            assert source.citation.strip(), f"{c.book.title}: source with no citation"
