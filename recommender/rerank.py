"""The aperture lens — a boost-only re-rank that widens discovery.

Mainstream recommenders narrow you toward what's popular. The aperture lens does
the opposite: it gives a small **boost** to candidates that introduce themes you
have *less* of, widening the aperture beyond your current mix. It is strictly
boost-only — it never lowers or drops a candidate — mirroring the "unknown is
first-class, never penalised" discipline from the sibling project.

``aperture_strength`` of 0 disables it entirely.
"""

from __future__ import annotations

from ingest.models import Book

from recommender.model import TasteProfile


def novelty_themes(taste: TasteProfile, book: Book) -> tuple[str, ...]:
    """Sourced themes on the book that are absent from (or thin in) the taste profile."""
    return tuple(sorted(label for label in book.tag_labels if label not in taste.theme_weights))


def aperture_boost(
    taste: TasteProfile, book: Book, strength: float
) -> tuple[float, tuple[str, ...]]:
    """Return (boost, broadening_themes). Boost is >= 0, scaled by ``strength``.

    The boost grows with how many *new-to-you* themes the book introduces, but is
    capped so it widens rather than dominates the ranking.
    """
    if strength <= 0.0:
        return 0.0, ()
    new_themes = novelty_themes(taste, book)
    if not new_themes:
        return 0.0, ()
    # Diminishing returns: 1 new theme matters most; cap the multiplier at ~3.
    factor = min(3, len(new_themes))
    return round(strength * 0.05 * factor, 6), new_themes
