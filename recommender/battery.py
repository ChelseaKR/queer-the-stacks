"""The synthetic-world eval battery: a falsifiable replacement for the single,
trivially-saturated demo-fixture gate in :mod:`recommender.eval`.

``docs/audits/eval-report.json`` used to show content and hybrid at a perfect
1.0 on every metric over the one hand-built demo fixture — a gate that cannot
fail short of catastrophe. :func:`run_battery` instead builds ``N`` seeded
synthetic worlds (:func:`recommender.synth.synth_world`), runs the same
content/hybrid/popularity eval on each, and gates on a **median MAP@k uplift**
of content over popularity plus a **no-losing-seed** guarantee — a
distribution, not a single boolean. It also runs two ablations per seed
(dropping curated lists, shuffling a slice of candidate tags) so a future
change that quietly guts either signal shows up as a tracked, explainable
delta even if it does not flip ``passed``.

Everything is deterministic per seed (``random.Random(seed)`` only) and fully
offline, matching the project's no-egress / reproducibility guardrails.
"""

from __future__ import annotations

import random
import re
import statistics
from collections.abc import Iterable
from dataclasses import replace
from typing import TypedDict

from ingest.demo import Candidate
from ingest.models import Book, ThemeTag

from recommender.embeddings import book_text
from recommender.eval import average_precision_at_k, evaluate
from recommender.hybrid import recommend_hybrid
from recommender.lists import CuratedList
from recommender.synth import synth_world

#: Calibrated margin: on the default seed battery (range(0, 10), k=5) the
#: observed median content-vs-popularity MAP@5 uplift is ~0.68 (see
#: docs/audits/eval-battery.json). Zeroing ``recommender/model.py::AUTHOR_BONUS``
#: — the falsifiability check in tests/test_synth_eval.py — drops that median
#: to ~0.37. 0.5 sits in between with real headroom on both sides: a healthy
#: recommender clears it by ~0.18, and a real regression that guts the
#: author-loyalty signal misses it by ~0.13 — comfortably outside either
#: measurement's noise floor (both are point values over 10 fixed seeds, not
#: sampled at runtime, so there is no run-to-run jitter to buffer against).
MARGIN = 0.5

#: The fraction of (candidate, tag) pairs the tag-shuffle ablation scrambles.
SHUFFLE_TAG_FRAC = 0.2

#: The default battery: 10 independent seeds, fixed so CI is deterministic.
DEFAULT_SEEDS: tuple[int, ...] = tuple(range(10))


class SeedRow(TypedDict):
    seed: int
    content_map: float
    hybrid_map: float
    popularity_map: float
    uplift: float
    content_wins: bool
    ablation_no_lists_content_map: float
    ablation_shuffled_content_map: float
    #: The same hybrid, re-ranked with the local embedding signal switched ON.
    #: Reported only. It gates nothing, and the flag stays off by default (#94).
    hybrid_embeddings_map: float
    #: Median tokens the embedder actually sees per candidate, and the share of
    #: them that are theme-tag tokens the content model already matches exactly.
    embeddable_tokens_median: float
    embeddable_tag_token_share: float


def _synthetic_lists(seed: int, candidates: list[Candidate]) -> tuple[CuratedList, ...]:
    """A small synthetic curated list over a third of this seed's on-canon books.

    Deterministic by sorted book id (no RNG needed) so the "drop curated
    lists" ablation has something real to drop.
    """
    on_canon_ids = sorted(c.book.book_id for c in candidates if c.on_canon)
    if not on_canon_ids:
        return ()
    picked = tuple(on_canon_ids[: max(1, len(on_canon_ids) // 3)])
    return (
        CuratedList(
            name=f"synthetic-canon-{seed}",
            citation=f"synthetic-seed:{seed}",
            book_ids=picked,
            retrieved_at="2026-07-01",
        ),
    )


def shuffle_tags(
    seed: int, candidates: list[Candidate], frac: float = SHUFFLE_TAG_FRAC
) -> list[Candidate]:
    """Scramble which candidate owns ~``frac`` of all (candidate, tag) pairs.

    Uses a seeded RNG derived from, but distinct from, the world-generation
    stream (so ablating never perturbs :func:`synth_world` itself). This
    destroys some of the theme-tag signal that ties on-canon candidates to the
    canon, so it should never *help* the content model versus the unablated
    world.

    Only candidates carrying 2+ theme tags participate as donor or recipient.
    :func:`recommender.synth.synth_world`'s author-bonus-only picks carry
    exactly one (deliberately non-matching) tag purely so every recommendation
    has a citable source — they carry no real theme *signal* to shuffle, and
    letting them receive a stray canon tag would let this ablation randomly
    *gift* them content score instead of only ever removing it.
    """
    rng = random.Random(seed * 7919 + 104729)  # noqa: S311 - deterministic ablation, not security
    eligible = [ci for ci, c in enumerate(candidates) if len(c.book.theme_tags) >= 2]
    pairs: list[tuple[int, ThemeTag]] = [
        (ci, tag) for ci in eligible for tag in candidates[ci].book.theme_tags
    ]
    if not pairs:
        return list(candidates)
    n = max(1, round(len(pairs) * frac))
    idx = sorted(rng.sample(range(len(pairs)), min(n, len(pairs))))
    shuffled_tags = [pairs[i][1] for i in idx]
    rng.shuffle(shuffled_tags)
    for pos, i in enumerate(idx):
        ci, _old_tag = pairs[i]
        pairs[i] = (ci, shuffled_tags[pos])

    by_candidate: dict[int, list[ThemeTag]] = {ci: [] for ci in eligible}
    for ci, tag in pairs:
        by_candidate[ci].append(tag)

    eligible_set = set(eligible)
    return [
        replace(c, book=replace(c.book, theme_tags=tuple(by_candidate[ci])))
        if ci in eligible_set
        else c
        for ci, c in enumerate(candidates)
    ]


_EMBED_TOKEN = re.compile(r"[a-z0-9]+")


def embeddable_text_profile(books: Iterable[Book]) -> tuple[float, float]:
    """How much text the embedder has to work with, and how much of it is new.

    Returns ``(median tokens per book, share of tokens that are theme-tag tokens)``.

    This exists because a MAP delta of zero from the embedding signal has two very
    different explanations — "semantic similarity does not help here" and "there was
    nothing to embed" — and reporting the delta without this pair would publish the
    first when the truth is the second. :func:`recommender.embeddings.book_text` is
    the whole input: a book's title plus its sourced theme-tag labels. There is no
    description, synopsis or blurb field on :class:`ingest.models.Book`, so the share
    below is the fraction of the embedder's input that the content model is already
    matching on exactly.
    """
    total = 0
    tag_tokens = 0
    per_book: list[int] = []
    for book in books:
        tokens = _EMBED_TOKEN.findall(book_text(book).lower())
        labels: set[str] = set()
        for tag in book.theme_tags:
            labels |= set(_EMBED_TOKEN.findall(tag.label.lower()))
        total += len(tokens)
        tag_tokens += sum(1 for token in tokens if token in labels)
        per_book.append(len(tokens))
    if not per_book or total == 0:
        return (0.0, 0.0)
    return (statistics.median(per_book), round(tag_tokens / total, 4))


def _run_seed(seed: int, k: int) -> SeedRow:
    states, candidates = synth_world(seed)
    lists = _synthetic_lists(seed, candidates)

    full = evaluate(states, list(candidates), lists=lists, k=k)
    content_map = full["content"].map_at_k
    hybrid_map = full["hybrid"].map_at_k
    popularity_map = full["popularity"].map_at_k

    no_lists = evaluate(states, list(candidates), lists=(), k=k)
    shuffled_candidates = shuffle_tags(seed, candidates)
    shuffled = evaluate(states, list(shuffled_candidates), lists=lists, k=k)

    # The embeddings arm. `evaluate()` is deliberately left alone — it calls
    # `recommend_hybrid` with the flag at its default — so this re-ranks the same
    # candidates directly with `use_embeddings=True` and scores the result with the
    # same MAP@k the other arms use. Nothing here changes a default: the signal is
    # off everywhere else, and whether to turn it on is #94's open question.
    books = tuple(c.book for c in candidates)
    positives = {c.book.book_id for c in candidates if c.on_canon}
    embeddings_ranked = [
        rec.book.book_id
        for rec in recommend_hybrid(
            states,
            books,
            lists=lists,
            k=len(books),
            aperture_strength=0.0,
            use_embeddings=True,
        )
    ]
    tokens_median, tag_share = embeddable_text_profile(books)

    return SeedRow(
        seed=seed,
        content_map=content_map,
        hybrid_map=hybrid_map,
        popularity_map=popularity_map,
        uplift=round(content_map - popularity_map, 4),
        content_wins=content_map >= popularity_map,
        ablation_no_lists_content_map=no_lists["content"].map_at_k,
        ablation_shuffled_content_map=shuffled["content"].map_at_k,
        hybrid_embeddings_map=round(average_precision_at_k(embeddings_ranked, positives, k), 4),
        embeddable_tokens_median=tokens_median,
        embeddable_tag_token_share=tag_share,
    )


def run_battery(seeds: Iterable[int] = DEFAULT_SEEDS, k: int = 5) -> dict[str, object]:
    """Run the eval across every seed and return a JSON-able distribution report.

    ``passed`` requires (a) the median content-vs-popularity MAP@k uplift is at
    least :data:`MARGIN`, and (b) content never *loses* to popularity on any
    individual seed (``content_map >= popularity_map`` everywhere). Ablation
    deltas (drop curated lists, shuffle 20% of candidate tags) are computed and
    reported per seed but do not gate ``passed`` — they are tracked evidence
    that the two non-baseline signals (curated lists, clean tags) are actually
    load-bearing, for a human or a follow-up test to assert on.
    """
    rows = [_run_seed(seed, k) for seed in seeds]
    if not rows:
        raise ValueError("run_battery requires at least one seed")

    uplifts = [row["uplift"] for row in rows]
    median_uplift = round(statistics.median(uplifts), 4)
    no_losing_seed = all(row["content_wins"] for row in rows)
    passed = bool(median_uplift >= MARGIN and no_losing_seed)

    ablation_no_lists_deltas = [
        round(row["content_map"] - row["ablation_no_lists_content_map"], 4) for row in rows
    ]
    ablation_shuffle_deltas = [
        round(row["content_map"] - row["ablation_shuffled_content_map"], 4) for row in rows
    ]
    # Embeddings arm: reported, never gating. See `docs/audits/embeddings-evaluation.md`
    # and #94 — turning the signal on is a decision, not a measurement.
    embedding_deltas = [round(row["hybrid_embeddings_map"] - row["hybrid_map"], 4) for row in rows]

    return {
        "k": k,
        "seeds": [row["seed"] for row in rows],
        "n_seeds": len(rows),
        "rows": [dict(row) for row in rows],
        "median_content_map": round(statistics.median(row["content_map"] for row in rows), 4),
        "median_hybrid_map": round(statistics.median(row["hybrid_map"] for row in rows), 4),
        "median_popularity_map": round(statistics.median(row["popularity_map"] for row in rows), 4),
        "median_uplift": median_uplift,
        "min_uplift": round(min(uplifts), 4),
        "max_uplift": round(max(uplifts), 4),
        "margin": MARGIN,
        "no_losing_seed": no_losing_seed,
        "ablation_drop_lists_median_delta": round(statistics.median(ablation_no_lists_deltas), 4),
        "ablation_shuffle_tags_median_delta": round(statistics.median(ablation_shuffle_deltas), 4),
        "median_hybrid_embeddings_map": round(
            statistics.median(row["hybrid_embeddings_map"] for row in rows), 4
        ),
        "embeddings_median_delta": round(statistics.median(embedding_deltas), 4),
        "embeddings_seeds_helped": sum(1 for d in embedding_deltas if d > 0),
        "embeddings_seeds_hurt": sum(1 for d in embedding_deltas if d < 0),
        "embeddings_seeds_unchanged": sum(1 for d in embedding_deltas if d == 0),
        # Why a zero delta above is not evidence that semantic similarity cannot help
        # here: it is also what "there was nothing to embed" looks like.
        "embeddable_tokens_median": round(
            statistics.median(row["embeddable_tokens_median"] for row in rows), 4
        ),
        "embeddable_tag_token_share": round(
            statistics.median(row["embeddable_tag_token_share"] for row in rows), 4
        ),
        "passed": passed,
    }
