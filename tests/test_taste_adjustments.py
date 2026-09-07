"""Explicit, reversible taste feedback (#107).

The tests are organised around the ways this feature could look like it works
while being wrong, because most of them are quiet:

* it could move numbers the reader never touched — the whole committed eval
  corpus was produced with no adjustments, and a blend that leaks when the set
  is empty would restate every published figure without anyone noticing;
* it could demote a book for having no sourced descriptor, which is this
  project's oldest failure mode wearing new clothes ("unknown" scored as low
  rather than as unknown);
* a lens could quietly become a penalty on everything outside it;
* undo could restore *approximately* the previous ranking;
* the privacy toggle could be defeated by the undo button that removes a hidden
  row;
* and the explanation could name an adjustment it did not actually read.

Each of those has a test below that fails when it happens.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ingest.archive import (
    ARCHIVE_SCHEMA_VERSION,
    ArchiveVersionError,
    build_archive,
    restore_archive,
)
from ingest.backup import backup_store, restore_store
from ingest.models import Author, Book, ReadingState, ReadingStatus, Source, SourceKind, ThemeTag
from ingest.store import Store
from ingest.taste import (
    MAGNITUDES,
    MAX_TOTAL_DELTA,
    AdjustmentError,
    TasteAdjustment,
    TasteAdjustments,
    validate,
)
from recommender.hybrid import recommend_hybrid
from recommender.model import adjustment_delta, resolve_adjustments

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- fixtures ---------------------------------------------------------------

_SRC = Source(SourceKind.CALIBRE_TAG, "calibre:local", "2026-06-05")


def _tag(label: str) -> ThemeTag:
    return ThemeTag(label, _SRC)


def _book(book_id: str, *labels: str, title: str | None = None) -> Book:
    return Book(
        book_id=book_id,
        title=title or book_id,
        authors=(Author("Some Author"),),
        theme_tags=tuple(_tag(label) for label in labels),
    )


def _finished(book: Book) -> ReadingState:
    return ReadingState(
        title=book.title,
        authors=tuple(a.name for a in book.authors),
        status=ReadingStatus.FINISHED,
        book=book,
    )


def _adj(
    target: str,
    direction: str = "more",
    magnitude: str = "moderate",
    kind: str = "theme",
) -> TasteAdjustment:
    return TasteAdjustment(
        kind=kind, target=target, direction=direction, magnitude=magnitude, created_at=1_700_000_000
    )


def _set(*adjustments: TasteAdjustment) -> TasteAdjustments:
    out = TasteAdjustments()
    for adjustment in adjustments:
        out = out.with_added(adjustment)
    return out


def _translated_world() -> tuple[list[ReadingState], tuple[Book, ...]]:
    """A reader who finishes literary fiction, and candidates that vary by one tag.

    Deliberately more than a couple of candidates: a ranking over one or two
    rows has almost no order to lose, so a blend that did nothing would still
    look like it had preserved the order.
    """
    states = [_finished(_book("own-1", "literary", "queer"))]
    candidates = (
        _book("cand-translated-a", "literary", "translated"),
        _book("cand-translated-b", "literary", "translated", "queer"),
        _book("cand-plain-a", "literary"),
        _book("cand-plain-b", "literary", "queer"),
        _book("cand-plain-c", "literary", "historical"),
        _book("cand-plain-d", "queer"),
    )
    return states, candidates


def _ranking(
    states: list[ReadingState], candidates: tuple[Book, ...], adjustments: TasteAdjustments
) -> list[tuple[str, float]]:
    resolved = resolve_adjustments(adjustments)
    return [
        (rec.book.book_id, rec.score)
        for rec in recommend_hybrid(states, candidates, k=len(candidates), adjustments=resolved)
    ]


# --- the constraint that matters most ---------------------------------------


def test_an_empty_adjustment_set_changes_no_score_at_all() -> None:
    """Every committed eval number was produced with no adjustments.

    So the empty set must be the identity, not merely close to it. Compared as
    full ``(id, score)`` pairs rather than as an order, because a blend that
    shifted every score by the same amount would preserve the order and still
    restate every published figure.
    """
    states, candidates = _translated_world()
    baseline = [
        (rec.book.book_id, rec.score)
        for rec in recommend_hybrid(states, candidates, k=len(candidates))
    ]
    with_empty = _ranking(states, candidates, TasteAdjustments())
    assert with_empty == baseline
    assert len(baseline) >= 4, "fixture too small for an order to be observable"


def test_the_committed_eval_report_still_holds_its_published_numbers() -> None:
    """The single-fixture report, pinned to literals rather than recomputed.

    Reading the expected values out of the same artifact under test would make
    this assertion true by construction — the mistake that lets a wrong constant
    through. These are the figures ``docs/audits/source-ethics.md`` and
    ``docs/USER-RESEARCH.md`` quote in prose, transcribed by hand from
    ``origin/main`` before this feature existed.
    """
    report = json.loads((REPO_ROOT / "docs/audits/eval-report.json").read_text(encoding="utf-8"))
    assert report["k"] == 5
    assert report["n_positives"] == 5
    assert report["content_beats_popularity"] is True
    assert report["intra_list_diversity_at_k"] == 0.68
    assert report["models"]["content"]["map_at_k"] == 1.0
    assert report["models"]["hybrid"]["map_at_k"] == 1.0
    assert report["models"]["popularity"]["map_at_k"] == 0.13
    assert report["models"]["popularity"]["ndcg_at_k"] == 0.2773


def test_the_committed_battery_still_holds_its_published_numbers() -> None:
    """The distribution report's headline figures, likewise pinned to literals."""
    battery = json.loads((REPO_ROOT / "docs/audits/eval-battery.json").read_text(encoding="utf-8"))
    assert battery["n_seeds"] == 10
    assert battery["median_content_map"] == 0.71
    assert battery["median_hybrid_map"] == 0.8
    assert battery["median_popularity_map"] == 0.0
    assert battery["median_uplift"] == 0.6766
    assert battery["min_uplift"] == 0.1333
    assert battery["max_uplift"] == 0.8
    assert battery["ablation_drop_lists_median_delta"] == 0.355
    assert battery["embeddable_tag_token_share"] == 0.6794
    assert battery["passed"] is True
    # The new probe's only acceptable value, and it gates `passed`.
    assert battery["adjustment_collateral_total"] == 0
    assert battery["adjustment_seeds_moved"] > 0


# --- unknown stays first-class ----------------------------------------------


def test_a_book_with_no_sourced_descriptor_is_never_moved_by_any_adjustment() -> None:
    """The absence rule. An undescribed book is unknown, not disliked.

    Checked against the *strongest* negative set that can be built, so this is
    not passing merely because the fixture was gentle.
    """
    undescribed = _book("cand-untagged")
    every_direction = _set(
        _adj("literary", "less", "strong"),
        _adj("queer", "less", "strong"),
        _adj("translated", "more", "strong"),
    )
    delta, reasons = adjustment_delta(undescribed, resolve_adjustments(every_direction))
    assert delta == 0.0
    assert reasons == ()


def test_an_adjustment_naming_an_absence_is_refused() -> None:
    """ "Less of the books we know nothing about" is a preference about coverage."""
    for target in ("unknown", "no sourced descriptor", "(hidden for privacy)", "   "):
        with pytest.raises(AdjustmentError, match="absence"):
            validate(_adj(target, "less"))


def test_an_adjustment_can_never_be_the_only_reason_a_book_appears() -> None:
    """An untagged candidate stays off the shelf however hard it is boosted.

    It has nothing to cite, and the transparency guardrail is that a pick shows
    its source. A boost that could carry an unciteable book onto the shelf would
    be a recommendation with no provenance.
    """
    states = [_finished(_book("own-1", "literary"))]
    candidates = (_book("cand-untagged"), _book("cand-tagged", "literary"))
    ids = [bid for bid, _ in _ranking(states, candidates, _set(_adj("literary", "more", "strong")))]
    assert "cand-untagged" not in ids
    assert "cand-tagged" in ids


# --- lenses are boost-only ---------------------------------------------------


def test_a_lens_may_not_be_asked_for_less_of() -> None:
    with pytest.raises(AdjustmentError, match="only ever raise"):
        validate(_adj("Feminist", "less", kind="lens"))
    # ...while the same request against a plain sourced descriptor is allowed.
    assert validate(_adj("feminist", "less")).direction == "less"


def test_a_lens_adjustment_raises_its_members_and_lowers_nothing() -> None:
    states, candidates = _translated_world()
    before = dict(_ranking(states, candidates, TasteAdjustments()))
    lens = {"Values": frozenset({"translated"})}
    resolved = resolve_adjustments(_set(_adj("Values", "more", "strong", kind="lens")), lens)
    after = {
        rec.book.book_id: rec.score
        for rec in recommend_hybrid(states, candidates, k=len(candidates), adjustments=resolved)
    }
    for book_id, score in before.items():
        assert after[book_id] >= score, f"{book_id} was lowered by a boost-only lens"
    assert after["cand-translated-a"] > before["cand-translated-a"]


def test_a_lens_the_reader_no_longer_defines_matches_nothing_and_is_kept() -> None:
    """Kept with an empty descriptor set, so the reader can still see and undo it."""
    resolved = resolve_adjustments(_set(_adj("Gone", "more", kind="lens")), {})
    assert len(resolved) == 1
    assert resolved[0].descriptors == frozenset()
    delta, reasons = adjustment_delta(_book("b", "literary"), resolved)
    assert (delta, reasons) == (0.0, ())


# --- bounded and monotone ----------------------------------------------------


def test_the_summed_delta_is_clamped_however_many_adjustments_match() -> None:
    book = _book("b", *[f"t{i}" for i in range(12)])
    piled_on = _set(*[_adj(f"t{i}", "more", "strong") for i in range(12)])
    delta, reasons = adjustment_delta(book, resolve_adjustments(piled_on))
    assert delta == MAX_TOTAL_DELTA
    # Every reason is still reported, even the ones the clamp absorbed: the
    # reader is owed the list of what they asked for.
    assert len(reasons) == 12


def test_the_negative_side_is_clamped_too() -> None:
    book = _book("b", *[f"t{i}" for i in range(12)])
    piled_on = _set(*[_adj(f"t{i}", "less", "strong") for i in range(12)])
    delta, _ = adjustment_delta(book, resolve_adjustments(piled_on))
    assert delta == -MAX_TOTAL_DELTA


def test_a_larger_magnitude_never_moves_a_book_less() -> None:
    book = _book("b", "literary")
    ordered = sorted(MAGNITUDES, key=lambda m: MAGNITUDES[m])
    deltas = [
        adjustment_delta(book, resolve_adjustments(_set(_adj("literary", "more", m))))[0]
        for m in ordered
    ]
    assert deltas == sorted(deltas)
    assert deltas[0] < deltas[-1], "the closed set must have distinct magnitudes"


def test_one_adjustment_counts_once_however_many_of_its_descriptors_match() -> None:
    """A nine-label lens must not be worth nine times a one-label theme."""
    book = _book("b", "a", "b", "c")
    lens = {"Wide": frozenset({"a", "b", "c"})}
    wide = adjustment_delta(
        book, resolve_adjustments(_set(_adj("Wide", "more", "moderate", kind="lens")), lens)
    )[0]
    narrow = adjustment_delta(book, resolve_adjustments(_set(_adj("a", "more", "moderate"))))[0]
    assert wide == narrow


# --- the issue's own acceptance criteria ------------------------------------


def test_asking_for_more_translated_raises_a_translated_candidate_and_says_so() -> None:
    states, candidates = _translated_world()
    before = dict(_ranking(states, candidates, TasteAdjustments()))
    adjustments = _set(_adj("translated", "more", "strong"))
    resolved = resolve_adjustments(adjustments)
    recs = recommend_hybrid(states, candidates, k=len(candidates), adjustments=resolved)
    after = {rec.book.book_id: rec.score for rec in recs}

    raised = [bid for bid, score in after.items() if score > before.get(bid, 0.0)]
    assert "cand-translated-a" in raised

    moved = next(rec for rec in recs if rec.book.book_id == "cand-translated-a")
    details = [s.detail for s in moved.explanation.signals if s.kind == "adjustment"]
    assert details, "the pick the adjustment moved does not name the adjustment"
    # Quoted back in the reader's own words, not the normalized match key.
    assert "translated" in details[0]
    assert "you asked for more" in details[0]

    # ...and a candidate that carries none of it is not named.
    untouched = next(rec for rec in recs if rec.book.book_id == "cand-plain-b")
    assert [s for s in untouched.explanation.signals if s.kind == "adjustment"] == []


def test_undo_restores_the_byte_identical_prior_ranking() -> None:
    states, candidates = _translated_world()
    before = _ranking(states, candidates, TasteAdjustments())
    adjustments = _set(_adj("translated", "more", "strong"), _adj("historical", "less", "slight"))
    during = _ranking(states, candidates, adjustments)
    assert during != before, "the fixture must actually be moved, or undo proves nothing"

    undone = adjustments
    for key in list(adjustments.keys):
        undone = undone.without(key)
    assert len(undone) == 0
    assert _ranking(states, candidates, undone) == before


def test_removing_one_adjustment_leaves_the_others_exactly_as_they_were() -> None:
    states, candidates = _translated_world()
    keep = _adj("translated", "more", "strong")
    drop = _adj("historical", "less", "slight")
    only_keep = _ranking(states, candidates, _set(keep))
    both = _set(keep, drop)
    assert _ranking(states, candidates, both.without(drop.key)) == only_keep


def test_asking_twice_for_the_same_thing_is_the_same_request_not_double() -> None:
    states, candidates = _translated_world()
    once = _ranking(states, candidates, _set(_adj("translated", "more", "moderate")))
    twice = _ranking(
        states,
        candidates,
        _set(_adj("translated", "more", "moderate"), _adj("Translated", "more", "moderate")),
    )
    assert twice == once


# --- the analysis path actually reads its input ------------------------------


def test_the_delta_is_read_from_the_book_under_test_not_from_somewhere_else() -> None:
    """The repo's own bug class: a plausible answer detached from its real input.

    Swap the book for one that carries none of the adjusted descriptors and the
    answer must collapse to zero. Without this, a delta computed from the
    adjustment set alone would look right on every book that happened to match.
    """
    adjustments = resolve_adjustments(_set(_adj("literary", "more", "strong")))
    assert adjustment_delta(_book("hit", "literary"), adjustments)[0] > 0.0
    assert adjustment_delta(_book("miss", "thriller"), adjustments)[0] == 0.0
    assert adjustment_delta(_book("empty"), adjustments)[0] == 0.0


# --- the battery probe -------------------------------------------------------


def test_the_battery_probe_reports_nothing_when_there_is_nothing_to_probe() -> None:
    """No descriptor anywhere means no probe, reported as such rather than as a pass.

    ``("", 0, 0)`` and "zero collateral" are the same trailing zeros, and the
    battery gates on the third value. This pins the degenerate case so a world
    with no sourced descriptors cannot read as a clean probe result.
    """
    from recommender.battery import _adjustment_probe

    descriptor, moved, collateral = _adjustment_probe([], (_book("a"), _book("b")), ())
    assert (descriptor, moved, collateral) == ("", 0, 0)


def test_the_battery_probe_finds_movement_and_no_collateral_on_a_real_world() -> None:
    from recommender.battery import _adjustment_probe

    states, candidates = _translated_world()
    descriptor, moved, collateral = _adjustment_probe(states, candidates, ())
    assert descriptor, "the fixture must carry a descriptor for the probe to use"
    assert moved > 0
    assert collateral == 0


# --- persistence, backup, archive -------------------------------------------


def test_the_store_round_trips_an_adjustment_set_and_bumps_the_view_revision(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "app-state.sqlite")
    try:
        assert len(store.taste_adjustments()) == 0, "a fresh store must read as no adjustments"
        before = store.view_revision()
        wanted = _set(_adj("translated", "more"), _adj("Feminist", "more", kind="lens"))
        store.save_taste_adjustments(wanted)
        assert store.taste_adjustments() == wanted
        assert store.view_revision() > before, "a cached page would show the old shelf"
    finally:
        store.close()


def test_a_persisted_record_this_build_cannot_read_is_dropped_not_coerced(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "app-state.sqlite")
    try:
        store._put(  # noqa: SLF001 - exercising the tolerant loader on purpose
            "taste_adjustments",
            {
                "records": [
                    {
                        "kind": "theme",
                        "target": "ok",
                        "direction": "more",
                        "magnitude": "moderate",
                        "created_at": 1,
                    },
                    {
                        "kind": "theme",
                        "target": "future",
                        "direction": "more",
                        "magnitude": "colossal",
                        "created_at": 1,
                    },
                ]
            },
        )
        loaded = store.taste_adjustments()
        assert loaded.keys == ("theme:ok",)
    finally:
        store.close()


def test_adjustments_survive_backup_and_restore(tmp_path: Path) -> None:
    store_path = tmp_path / "app-state.sqlite"
    wanted = _set(_adj("translated", "more", "strong"))
    store = Store(store_path)
    try:
        store.save_taste_adjustments(wanted)
    finally:
        store.close()

    backup = backup_store(store_path, tmp_path / "backups", "2026-09-07T00-00-00")

    store = Store(store_path)
    try:
        store.save_taste_adjustments(TasteAdjustments())
        assert len(store.taste_adjustments()) == 0
    finally:
        store.close()

    restore_store(backup, store_path)
    store = Store(store_path)
    try:
        assert store.taste_adjustments() == wanted
    finally:
        store.close()


def test_adjustments_appear_in_the_archive_export_and_round_trip() -> None:
    wanted = _set(_adj("translated", "more"), _adj("historical", "less", "slight"))
    bundle = build_archive([], [], generated_at=0, taste_adjustments=wanted)
    assert bundle["manifest"]["schema_version"] == ARCHIVE_SCHEMA_VERSION
    assert "taste_adjustments" in bundle["manifest"]["members"]
    assert bundle["taste_adjustments"]["records"][0]["target"] in {"historical", "translated"}
    _states, _activity, restored = restore_archive(bundle)
    assert restored == wanted


def test_a_version_1_archive_still_reads_and_restores_as_no_adjustments() -> None:
    """A preservation format that refuses last year's bundle is not one."""
    v1 = build_archive([], [], generated_at=0)
    v1["manifest"] = dict(v1["manifest"], schema_version=1)
    del v1["taste_adjustments"]
    _states, _activity, restored = restore_archive(v1)
    assert len(restored) == 0


def test_an_unreadable_future_archive_version_is_still_refused() -> None:
    bundle = build_archive([], [], generated_at=0)
    bundle["manifest"] = dict(bundle["manifest"], schema_version=99)
    with pytest.raises(ArchiveVersionError):
        restore_archive(bundle)


# --- privacy -----------------------------------------------------------------


def test_the_undo_handle_never_contains_the_descriptor_it_removes() -> None:
    """The privacy toggle must not be defeated by the button that removes a row."""
    adjustment = _adj("trans", "more")
    assert "trans" not in adjustment.handle
    assert adjustment.handle == _adj("trans", "less", "strong").handle, (
        "the handle must identify the (kind, target), so undo works whatever the "
        "direction or magnitude currently is"
    )
    found = _set(adjustment).by_handle(adjustment.handle)
    assert found is not None and found.key == "theme:trans"
    assert _set(adjustment).by_handle("deadbeefdeadbeef") is None


# --- the rendered surface ----------------------------------------------------


def _render(view, **kwargs: object) -> str:
    import dataclasses

    from app.view import render_view

    return render_view(dataclasses.replace(view, **kwargs))  # type: ignore[arg-type]


def test_the_dashboard_states_an_empty_adjustment_set_rather_than_omitting_it(
    full_view: object,
) -> None:
    html = _render(full_view)
    assert "Your taste adjustments" in html
    assert "You have not adjusted anything yet" in html


def test_the_controls_are_plain_forms_that_work_without_javascript(full_view: object) -> None:
    html = _render(full_view, taste_adjustments=_set(_adj("queer", "more")))
    assert '<form method="post" action="/taste">' in html
    assert '<form class="feedback" method="post" action="/taste">' in html
    # Every control the section renders is inside a form with a submit button;
    # none of it is wired by script.
    section = html.split('<h2 id="taste-h">')[1].split("</section>")[0]
    assert "<script" not in section
    assert 'type="submit"' in section


def test_a_pick_offers_only_descriptors_that_pick_actually_carries(full_view: object) -> None:
    """The other half of the wrong-source guard, on the rendered page.

    ``_pick_feedback_form`` must read the book in front of it. A form built from
    the reader's whole vocabulary would look identical on a screenshot and offer
    to adjust on a descriptor this pick does not have.
    """
    from app.render import _pick_feedback_form

    rec = full_view.recommendations[0]  # type: ignore[attr-defined]
    form = _pick_feedback_form(rec, frozenset())
    for label in rec.book.tag_labels:
        assert f'value="{label}"' in form
    absent = "a-descriptor-this-book-does-not-have"
    assert absent not in form
    # Swap in a book with nothing sourced and the form must say so rather than
    # render an empty select that looks operable.
    import dataclasses

    bare = dataclasses.replace(rec, book=_book("bare"))
    assert "No adjustment available" in _pick_feedback_form(bare, frozenset())


def test_a_withheld_target_is_shown_as_withheld_and_never_dropped(full_view: object) -> None:
    html = _render(
        full_view,
        taste_adjustments=_set(_adj("trans", "more"), _adj("literary", "more")),
    )
    from app.diversity import REDACTED_LABEL

    hidden_html = _render(
        full_view,
        taste_adjustments=_set(_adj("trans", "more"), _adj("literary", "more")),
    )
    assert "trans" in html  # nothing hidden by default
    del hidden_html

    # With the toggle on, the row survives, the descriptor does not, and the
    # undo control still works because it carries a handle rather than the key.
    from app.render import _taste_section

    adjustments = _set(_adj("trans", "more"), _adj("literary", "more"))
    section = _taste_section(adjustments, ["trans", "literary"], ["Feminist"], frozenset({"trans"}))
    assert section.count("<tr>") == 3  # header + two rows: neither was dropped
    assert REDACTED_LABEL in section
    assert ">trans<" not in section
    assert 'value="trans"' not in section
    assert 'value="theme:trans"' not in section


# --- the route ---------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from tests.conftest import seed_store_from_env

    monkeypatch.setenv("STACKS_DEMO", "1")
    monkeypatch.setenv("STACKS_DATA_DIR", str(tmp_path))
    seed_store_from_env()
    from app.server import create_app

    return TestClient(create_app(), base_url="https://testserver")


def _auth(client) -> dict[str, str]:  # type: ignore[no-untyped-def]
    from app.auth import DEMO_TOKEN

    return {"Authorization": f"Bearer {DEMO_TOKEN}"}


def test_posting_an_adjustment_requires_auth(client) -> None:  # type: ignore[no-untyped-def]
    assert client.post("/taste", data={"action": "add", "target": "queer"}).status_code == 401


def test_the_route_adds_undoes_and_clears(client, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    headers = _auth(client)
    added = client.post(
        "/taste",
        data={
            "action": "add",
            "kind": "theme",
            "target": "queer",
            "direction": "more",
            "magnitude": "strong",
        },
        headers=headers,
        follow_redirects=False,
    )
    assert added.status_code == 303

    store = Store(tmp_path / "app-state.sqlite")
    try:
        current = store.taste_adjustments()
        assert current.keys == ("theme:queer",)
        handle = current.records[0].handle
    finally:
        store.close()

    undone = client.post(
        "/taste", data={"action": "undo", "handle": handle}, headers=headers, follow_redirects=False
    )
    assert undone.status_code == 303
    store = Store(tmp_path / "app-state.sqlite")
    try:
        assert len(store.taste_adjustments()) == 0
    finally:
        store.close()

    assert (
        client.post("/taste", data={"action": "clear"}, headers=headers, follow_redirects=False)
    ).status_code == 303


def test_the_route_refuses_rather_than_silently_ignoring(client) -> None:  # type: ignore[no-untyped-def]
    headers = _auth(client)
    for payload, fragment in (
        ({"action": "add", "target": "queer", "magnitude": "colossal"}, "magnitude"),
        (
            {"action": "add", "kind": "lens", "lens_target": "Feminist", "direction": "less"},
            "raise",
        ),
        ({"action": "add", "target": "unknown", "direction": "less"}, "absence"),
        ({"action": "undo", "handle": "0000000000000000"}, "no such adjustment"),
        ({"action": "detonate"}, "unknown taste action"),
    ):
        response = client.post("/taste", data=payload, headers=headers, follow_redirects=False)
        assert response.status_code == 400, payload
        assert fragment in response.json()["detail"]


# --- the CLI -----------------------------------------------------------------


def test_stacks_recommend_honours_the_same_adjustments_the_dashboard_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``_cmd_recommend``'s docstring promises the CLI and the dashboard never disagree.

    They did, at first: the dashboard read adjustments through ``view_from_store``
    and ``stacks recommend`` called the content recommender directly, so a
    preference honoured on the page was ignored at the command line. Caught by
    running the two by hand, not by a test — this is the test.
    """
    from ingest.cli import main

    monkeypatch.setenv("STACKS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("STACKS_DEMO", "1")

    assert main(["recommend", "--k", "3"]) == 0
    before = capsys.readouterr().out

    assert main(["taste", "--more", "historical", "--magnitude", "strong"]) == 0
    capsys.readouterr()
    assert main(["recommend", "--k", "3"]) == 0
    after = capsys.readouterr().out
    assert after != before, "the CLI ignored an adjustment the dashboard would honour"
    assert "historical" in after

    assert main(["taste", "--undo", "theme:historical"]) == 0
    capsys.readouterr()
    assert main(["recommend", "--k", "3"]) == 0
    assert capsys.readouterr().out == before, "undo did not restore the CLI shelf exactly"


def test_the_cli_shows_adds_undoes_and_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from ingest.cli import main

    monkeypatch.setenv("STACKS_DATA_DIR", str(tmp_path))

    assert main(["taste"]) == 0
    assert json.loads(capsys.readouterr().out) == {"records": []}

    assert main(["taste", "--more", "Translated", "--magnitude", "strong"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["records"][0]["target"] == "Translated"
    assert shown["records"][0]["magnitude"] == "strong"

    assert main(["taste", "--less", "Feminist", "--lens"]) == 2
    assert "only ever raise" in capsys.readouterr().err

    assert main(["taste", "--undo", "theme:nope"]) == 2
    assert "no adjustment with key" in capsys.readouterr().err

    assert main(["taste", "--undo", "theme:translated"]) == 0
    assert json.loads(capsys.readouterr().out) == {"records": []}
