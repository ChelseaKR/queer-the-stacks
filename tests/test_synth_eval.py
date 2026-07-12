"""The synthetic-world eval battery: determinism, falsifiability, ablations.

Companion to tests/test_eval.py, which covers the (now-informational) single
demo fixture. This file exercises the FIX-13 replacement — the seeded battery
that actually gates the merge (see recommender/battery.py, ingest/cli.py's
``eval --synthetic``).
"""

from __future__ import annotations

import pytest
from recommender.battery import DEFAULT_SEEDS, MARGIN, run_battery, shuffle_tags
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
