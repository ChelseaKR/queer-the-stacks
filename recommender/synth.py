"""Seeded synthetic-library generator for the falsifiable eval battery.

``recommender/eval.py`` originally ran on exactly one hand-built fixture
(:mod:`ingest.demo`) — trivially separable, so every model scored a perfect
1.0 and the merge-blocking gate could not distinguish a real recommender from
a broken one short of catastrophe. This module builds a *family* of synthetic
libraries instead: for any integer seed, :func:`synth_world` deterministically
generates a reader's taste profile plus a candidate pool with a known,
independently-planted ground truth (``Candidate.on_canon``), so
:mod:`recommender.battery` can run the eval across many worlds and require a
*margin*, not a single boolean.

Everything here uses only :class:`random.Random(seed)` — no numpy, no module-
level global RNG, no wall-clock or filesystem reads — so a given seed always
reproduces byte-identical output. Tag samples are always sorted before being
turned into :class:`~ingest.models.ThemeTag` tuples so ordering never depends
on set/dict iteration, only on the seeded draw itself.
"""

from __future__ import annotations

import random

from ingest.demo import Candidate
from ingest.models import (
    Author,
    Book,
    ReadingState,
    ReadingStatus,
    Source,
    SourceKind,
    ThemeTag,
)

_RETRIEVED_AT = "2026-07-01"


def _tag_pool(tag_vocab: int) -> list[str]:
    return [f"tag-{i:02d}" for i in range(tag_vocab)]


def _theme_tags(labels: list[str]) -> tuple[ThemeTag, ...]:
    """Turn sorted labels into sourced tags (synthetic OpenLibrary-shaped provenance)."""
    return tuple(
        ThemeTag(
            label=label,
            source=Source(
                kind=SourceKind.OPENLIBRARY_SUBJECT,
                citation=f"https://openlibrary.org/subjects/{label}",
                retrieved_at=_RETRIEVED_AT,
                detail=label,
            ),
        )
        for label in labels
    )


def _sample_sorted(rng: random.Random, pool: list[str], n: int) -> list[str]:
    """Sample ``n`` (clamped) items from ``pool`` and sort — never rely on set order."""
    n = max(0, min(n, len(pool)))
    if n == 0:
        return []
    return sorted(rng.sample(pool, n))


def _mixed_tags(
    rng: random.Random, primary_pool: list[str], secondary_pool: list[str], n: int, noise: float
) -> list[str]:
    """Draw ~``n`` tags mostly from ``primary_pool``, each slot independently
    swapped to ``secondary_pool`` with probability ``noise``.

    This is what keeps the eval from being trivially separable: on-canon
    candidates occasionally carry an off-canon tag, and — crucially —
    distractors occasionally carry a real canon tag, so the content model's
    win over the popularity baseline is genuine signal-in-noise, not a
    guaranteed zero-overlap partition. A repeated draw just yields fewer
    effective tags (realistic — books repeat subjects); the result is always
    sorted so it never depends on set/dict iteration order.
    """
    chosen: set[str] = set()
    for _ in range(n):
        pool = secondary_pool if (secondary_pool and rng.random() < noise) else primary_pool
        if not pool:
            pool = secondary_pool or primary_pool
        if not pool:
            continue
        chosen.add(rng.choice(pool))
    return sorted(chosen)


def _readers(rng: random.Random, *, on_canon: bool, pop_canon_corr: float) -> int:
    """Popularity proxy: canon-fit books skew modest, distractors skew high.

    Both groups are drawn from the *same* heavy-tailed (log-normal) base
    distribution — real popularity overlaps a lot in practice — then nudged
    by ``pop_canon_corr`` (a simplified anti-correlation knob, not a literal
    Pearson coefficient): negative values shrink on-canon readers and inflate
    distractor readers by the same modest fraction. This keeps the popularity
    baseline *usually* preferring distractors without guaranteeing a clean
    partition, so the content-vs-popularity margin has real variance instead
    of maxing out on every seed.
    """
    corr = max(-1.0, min(1.0, pop_canon_corr))
    base = rng.lognormvariate(10.5, 1.3)
    nudge = 0.6 * corr  # e.g. corr=-0.3 -> nudge=-0.18
    factor = (1.0 + nudge) if on_canon else (1.0 - nudge)
    return max(1, round(base * max(0.1, factor)))


def synth_world(
    seed: int,
    *,
    library_size: int = 40,
    tag_vocab: int = 30,
    canon_frac: float = 0.25,
    pop_canon_corr: float = -0.3,
    tag_noise: float = 0.2,
) -> tuple[list[ReadingState], list[Candidate]]:
    """Build one deterministic synthetic library + candidate pool for ``seed``.

    - A ``canon`` subset of the tag vocabulary is drawn (``canon_frac`` of
      ``tag_vocab``). On-canon candidates draw most of their theme tags from
      that subset, with a ``tag_noise`` fraction of off-canon tags mixed in
      (real canon-fit books are never 100% on-theme); distractors draw mostly
      from off-canon tags, with the same ``tag_noise`` fraction of genuine
      canon tags leaking in (real distractors are not perfectly on-brand
      either) — this is what keeps the eval from being trivially separable.
    - ``canon_frac`` of ``library_size`` candidates are planted as genuine
      canon-fit discoveries (``on_canon=True``); the rest are popular
      off-theme distractors (``on_canon=False``) — the eval's premise, same
      shape as the hand-built demo fixture but sampled, not hand-picked.
    - Popularity (``readers``) anti-correlates with canon-fit per
      ``pop_canon_corr`` (see :func:`_readers`).
    - The reader's taste profile is a handful of FINISHED books, tagged with
      canon themes and written by a small pool of "canon authors" that a
      subset of the on-canon candidates also share — so both the theme signal
      and the author-loyalty signal (``recommender.model.AUTHOR_BONUS``) point
      at the same canon.

    Same ``seed`` in -> byte-identical ``(states, candidates)`` out. Different
    seeds draw independent worlds.
    """
    rng = random.Random(seed)  # noqa: S311 - deterministic simulation, not security
    tags = _tag_pool(tag_vocab)
    n_canon_tags = max(2, round(tag_vocab * canon_frac))
    canon_tags = _sample_sorted(rng, tags, n_canon_tags)
    off_tags = sorted(set(tags) - set(canon_tags))

    n_canon_books = max(3, round(library_size * canon_frac))
    n_distractors = max(1, library_size - n_canon_books)

    n_canon_authors = max(2, n_canon_books // 3)
    canon_authors = [f"Canon Author {seed}-{i}" for i in range(n_canon_authors)]
    n_distractor_authors = max(2, n_distractors // 4)
    distractor_authors = [f"Bestseller Author {seed}-{i}" for i in range(n_distractor_authors)]

    candidates: list[Candidate] = []

    # -- On-canon candidates: two discovery pathways, per the real recommender
    # (recommender/model.py::score_candidate = cosine-sim + AUTHOR_BONUS +
    # list bonus). Most are a "more by an author you've finished" pick — by a
    # canon author, carrying exactly one off-canon tag (a real, sourced tag —
    # every recommendation needs one, see recommender/explain.py — but it
    # shares nothing with the taste profile, so ``_cosine`` scores it 0.0).
    # The entire score for this group is the AUTHOR_BONUS. The rest are pure
    # theme-only discoveries by an unrelated author, with clean canon signal
    # and no bonus. Zeroing AUTHOR_BONUS should collapse the first group's
    # score to (near) zero without touching the second — the falsifiability
    # check in tests/test_synth_eval.py exercises exactly this. Keeping the
    # author-bonus group's tag list to a single off-canon tag also limits how
    # much material the tag-shuffle ablation
    # (recommender/battery.py::shuffle_tags) can accidentally gift them.
    for i in range(n_canon_books):
        # Most on-canon books are the author-bonus pathway (only one in five
        # is a pure theme-only discovery), so AUTHOR_BONUS is load-bearing for
        # top-k coverage rather than a rare edge case — real enough to make it
        # falsifiable (see the module docstring).
        is_author_pick = i % 5 != 0
        n_tags_i = rng.randint(2, 4)
        chosen = (
            _sample_sorted(rng, off_tags, 1)
            if is_author_pick
            else _mixed_tags(rng, canon_tags, off_tags, n_tags_i, tag_noise)
        )
        author = (
            canon_authors[i % len(canon_authors)]
            if is_author_pick
            else f"Discovery Author {seed}-{i}"
        )
        readers = _readers(rng, on_canon=True, pop_canon_corr=pop_canon_corr)
        candidates.append(
            Candidate(
                book=Book(
                    book_id=f"syn:{seed}:canon:{i}",
                    title=f"Synthetic Canon Discovery {seed}-{i}",
                    authors=(Author(name=author),),
                    theme_tags=_theme_tags(chosen),
                    identifiers={},
                ),
                readers=readers,
                on_canon=True,
            )
        )

    # -- Distractors: popular, mostly off-theme, never by a canon author. A
    # thin (``tag_noise / 4``) slice of canon tags leaks in too (real
    # distractors are not always thematically pure) — enough that the content
    # model's separation from popularity is real signal-in-noise, not a
    # zero-overlap tautology, but diluted (more filler tags, low leak rate)
    # so a lucky leak stays *below* a single AUTHOR_BONUS. That is what makes
    # the AUTHOR_BONUS falsification test below meaningful: with the bonus
    # zeroed, the author-bonus on-canon books (no theme overlap at all) drop
    # to a zero score and lose to exactly this noise floor.
    for i in range(n_distractors):
        n_tags_i = rng.randint(5, 7)
        chosen = _mixed_tags(rng, off_tags, canon_tags, n_tags_i, tag_noise / 4)
        author = distractor_authors[i % len(distractor_authors)]
        readers = _readers(rng, on_canon=False, pop_canon_corr=pop_canon_corr)
        candidates.append(
            Candidate(
                book=Book(
                    book_id=f"syn:{seed}:distractor:{i}",
                    title=f"Synthetic Bestseller {seed}-{i}",
                    authors=(Author(name=author),),
                    theme_tags=_theme_tags(chosen),
                    identifiers={},
                ),
                readers=readers,
                on_canon=False,
            )
        )

    # -- Reader taste profile: finished books by the canon authors, each
    # tagged with one *distinct* canon theme (no repeats), so every taste
    # weight is a clean 1.0 — the taste vector's norm stays predictable, which
    # keeps a single leaked distractor tag's cosine contribution reliably
    # below one AUTHOR_BONUS (see the distractor loop above).
    n_finished = min(len(canon_tags), max(4, n_canon_authors * 2))
    finished_tags = _sample_sorted(rng, canon_tags, n_finished)
    states: list[ReadingState] = []
    for i in range(n_finished):
        author = canon_authors[i % len(canon_authors)]
        chosen = [finished_tags[i]]
        book = Book(
            book_id=f"syn:{seed}:owned:{i}",
            title=f"Synthetic Owned Canon Book {seed}-{i}",
            authors=(Author(name=author),),
            theme_tags=_theme_tags(chosen),
            identifiers={},
        )
        states.append(
            ReadingState(
                title=book.title,
                authors=(author,),
                status=ReadingStatus.FINISHED,
                book=book,
            )
        )

    return states, candidates
