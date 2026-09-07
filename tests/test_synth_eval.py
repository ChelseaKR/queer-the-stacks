"""The synthetic-world eval battery: determinism, falsifiability, ablations.

Companion to tests/test_eval.py, which covers the (now-informational) single
demo fixture. This file exercises the FIX-13 replacement — the seeded battery
that actually gates the merge (see recommender/battery.py, ingest/cli.py's
``eval --synthetic``).
"""

from __future__ import annotations

import pytest
from ingest.demo import demo_candidates
from ingest.models import Book
from recommender.battery import (
    DEFAULT_SEEDS,
    MARGIN,
    embeddable_text_profile,
    run_battery,
    shuffle_tags,
)
from recommender.synth import synth_world


def test_synth_world_is_deterministic() -> None:
    """Same seed in -> byte-identical world out, every field."""
    states_a, candidates_a = synth_world(7)
    states_b, candidates_b = synth_world(7)
    assert states_a == states_b
    assert candidates_a == candidates_b


def test_synth_world_differs_across_seeds() -> None:
    _, candidates_0 = synth_world(0)
    _, candidates_1 = synth_world(1)
    assert candidates_0 != candidates_1


def test_synth_world_has_positives_and_distractors() -> None:
    states, candidates = synth_world(3)
    assert any(c.on_canon for c in candidates)
    assert any(not c.on_canon for c in candidates)
    assert states  # a nonempty taste profile


def test_synth_world_book_ids_are_unique() -> None:
    states, candidates = synth_world(5)
    book_ids = [c.book.book_id for c in candidates]
    assert len(book_ids) == len(set(book_ids))
    owned_ids = [s.book.book_id for s in states if s.book is not None]
    assert len(owned_ids) == len(set(owned_ids))


def test_run_battery_is_deterministic() -> None:
    """Same seeds in -> byte-identical report out (the merge-gate must be stable)."""
    a = run_battery(range(5), k=5)
    b = run_battery(range(5), k=5)
    assert a == b


def test_run_battery_default_seeds_passes() -> None:
    """The calibrated default battery clears its own margin with a healthy recommender."""
    report = run_battery(DEFAULT_SEEDS, k=5)
    assert report["passed"] is True
    assert report["no_losing_seed"] is True
    assert report["median_uplift"] >= MARGIN
    assert len(report["rows"]) == len(DEFAULT_SEEDS)


def test_run_battery_requires_seeds() -> None:
    with pytest.raises(ValueError):
        run_battery([], k=5)


def test_run_battery_report_has_falsifiable_structure() -> None:
    """It's a distribution, not a boolean: per-seed rows + margin, not one number."""
    report = run_battery(range(4), k=5)
    assert report["n_seeds"] == 4
    for row in report["rows"]:
        assert "content_map" in row
        assert "popularity_map" in row
        assert "uplift" in row
    assert "median_uplift" in report
    assert "margin" in report


def test_author_bonus_zero_narrows_uplift(monkeypatch: pytest.MonkeyPatch) -> None:
    """Falsifiability: killing the author-loyalty signal must visibly hurt the eval.

    This is the check that proves the battery *can* fail — a saturated 1.0
    gate (the thing FIX-13 replaces) could never distinguish this from a
    healthy recommender.
    """
    baseline = run_battery(DEFAULT_SEEDS, k=5)

    import recommender.model as model

    monkeypatch.setattr(model, "AUTHOR_BONUS", 0.0)
    degraded = run_battery(DEFAULT_SEEDS, k=5)

    assert degraded["median_uplift"] < baseline["median_uplift"]
    # The whole point: the merge gate actually flips to failing.
    assert degraded["passed"] is False
    assert baseline["passed"] is True


def test_shuffling_tags_never_improves_content_map() -> None:
    """The tag-shuffle ablation only ever removes signal, never adds it.

    (recommender/synth.py deliberately gives the author-bonus-only picks a
    single non-matching tag rather than none, so they always have a citable
    source; recommender/battery.py::shuffle_tags in turn excludes
    single-tag candidates from the shuffle pool so this ablation can never
    accidentally *gift* them real theme signal — see both modules'
    docstrings.)
    """
    for seed in DEFAULT_SEEDS:
        states, candidates = synth_world(seed)
        from recommender.eval import evaluate

        full = evaluate(states, candidates, k=5)
        shuffled = evaluate(states, shuffle_tags(seed, candidates), k=5)
        assert shuffled["content"].map_at_k <= full["content"].map_at_k, seed


def test_shuffling_tags_is_deterministic() -> None:
    _, candidates = synth_world(2)
    a = shuffle_tags(2, candidates)
    b = shuffle_tags(2, candidates)
    assert a == b


def test_shuffling_tags_degrades_map_on_some_seeds() -> None:
    """Not a no-op: at least one seed in the default battery is actually degraded."""
    report = run_battery(DEFAULT_SEEDS, k=5)
    deltas = [row["content_map"] - row["ablation_shuffled_content_map"] for row in report["rows"]]
    assert any(d > 0 for d in deltas)


def test_dropping_curated_lists_never_improves_content_map() -> None:
    report = run_battery(DEFAULT_SEEDS, k=5)
    for row in report["rows"]:
        assert row["ablation_no_lists_content_map"] <= row["content_map"]


# --- The embeddings arm (#94) ------------------------------------------------
#
# These pin LITERALS. The battery reports a distribution, and a property assertion
# ("the delta is finite", "the share is between 0 and 1") would hold just as well
# against a broken measurement. What makes the arm evidence rather than decoration
# is that the specific numbers it publishes are named here, so a change to what the
# embedder sees, or to how it is blended, has to be argued for in a diff.


def test_embeddings_arm_is_measured_and_reported() -> None:
    """The battery actually exercises `use_embeddings=True` and publishes the delta.

    Before this, nothing anywhere evaluated the embedding signal: `evaluate()` calls
    `recommend_hybrid` with the flag at its default, so every committed eval number
    described the recommender with embeddings OFF.
    """
    report = run_battery(DEFAULT_SEEDS, k=5)
    assert report["median_hybrid_embeddings_map"] == 0.8
    assert report["embeddings_median_delta"] == 0.0
    assert report["embeddings_seeds_helped"] == 1
    assert report["embeddings_seeds_hurt"] == 0
    assert report["embeddings_seeds_unchanged"] == 9


def test_embeddings_arm_does_not_gate_passed() -> None:
    """The arm is evidence, not a merge gate.

    Turning the signal on is a decision recorded at #94 and it is the owner's. A
    battery that failed when the embedding delta went to zero would be making that
    decision by refusing to merge.
    """
    report = run_battery(DEFAULT_SEEDS, k=5)
    assert report["passed"] is True
    assert report["embeddings_median_delta"] == 0.0


def test_zero_embedding_delta_is_reported_next_to_how_little_there_is_to_embed() -> None:
    """A zero delta has two explanations, and the battery must not publish the wrong one.

    "Semantic similarity does not help here" and "there was nothing to embed" produce
    the identical number. `recommender.embeddings.book_text` is the entire input — a
    book's title plus its sourced theme-tag labels — because `ingest.models.Book` has
    no description, synopsis or blurb field at all. So most of what the embedder sees
    is the theme-tag text the content model is *already* matching on exactly, and the
    battery reports that share beside the delta rather than leaving the zero to be
    read as a finding about semantics.
    """
    report = run_battery(DEFAULT_SEEDS, k=5)
    assert report["embeddable_tokens_median"] == 14.0
    assert report["embeddable_tag_token_share"] == 0.6794
    assert not hasattr(Book("x", "t"), "description")


def test_embeddable_text_profile_on_the_demo_fixture() -> None:
    """The same measurement over the real-titled demo fixture, not just synthetic ones.

    Synthetic titles are formulaic ("Synthetic Canon Discovery 0-3"), so they could be
    the reason the embedder adds nothing. They are not the whole reason: the eight
    demo books carry real titles and the share is still a majority.
    """
    tokens_median, tag_share = embeddable_text_profile(c.book for c in demo_candidates())
    assert tokens_median == 6.5
    assert tag_share == 0.5962
