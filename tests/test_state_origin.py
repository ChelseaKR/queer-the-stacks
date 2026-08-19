"""Fixture-vs-real provenance: the store records which world wrote it.

The demo world and the real libraries share one store path by default
(``make dev`` sets ``STACKS_DEMO=1`` and leaves ``STACKS_DATA_DIR`` alone), so
"where did this state come from" is not inferable from the current config at
read time. These tests pin the two failure modes that produced:

1. a real refresh silently *skipping* because a demo refresh had already
   populated the store and stamped it with the real sources' mtimes, leaving
   fixture books to be served as the reader's own library; and
2. a dashboard/OPDS feed rendering fixture titles with no label at all, while
   the CLI's ``stacks recommend`` had said "these are fixture titles" since the
   recommend fix.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from app import opds
from app.render import FIXTURE_CANDIDATES_NOTICE, FIXTURE_STATES_NOTICE
from app.share import (
    CARD_SOURCE_FIXTURE,
    CARD_SOURCE_REAL,
    FIXTURE_CARD_LINE,
    FIXTURE_PAGE_NOTICE,
    build_share_cards,
    render_share_page,
    render_share_svg,
)
from app.view import render_view, view_from_store
from ingest.config import Config, load_config
from ingest.demo import build_demo_dbs
from ingest.refresh import refresh
from ingest.store import ORIGIN_DEMO, ORIGIN_REAL, Store


def _drop_origin_row(path: Path) -> None:
    """Make a store look like one written before the origin field existed.

    A pre-fix store has no ``state_origin`` row at all, so the row is deleted
    rather than blanked — the test then exercises the real legacy shape.
    """
    conn = sqlite3.connect(path)
    conn.execute("DELETE FROM app_state WHERE key = 'state_origin'")
    conn.commit()
    conn.close()


def _config(tmp_path: Path, *, demo: bool) -> Config:
    """Real-shaped config over on-disk SQLite; ``demo`` flips the world only."""
    metadata_db, statistics_db = build_demo_dbs(tmp_path / "lib")
    env = {
        "STACKS_CALIBRE_DB": str(metadata_db),
        "STACKS_KOREADER_DB": str(statistics_db),
        "STACKS_DATA_DIR": str(tmp_path / "data"),
    }
    if demo:
        env["STACKS_DEMO"] = "1"
    return load_config(env=env, config_path=tmp_path / "absent.toml")


# --- the store records its own provenance -----------------------------------


def test_real_refresh_records_real_origin(tmp_path: Path) -> None:
    config = _config(tmp_path, demo=False)
    with Store(config.store_path) as store:
        refresh(config, store, now=1_000)
        assert store.state_origin() == ORIGIN_REAL


def test_demo_refresh_records_demo_origin(tmp_path: Path) -> None:
    config = _config(tmp_path, demo=True)
    with Store(config.store_path) as store:
        refresh(config, store, now=1_000)
        assert store.state_origin() == ORIGIN_DEMO


def test_demo_refresh_claims_no_source_mtimes(tmp_path: Path) -> None:
    """Demo states must not assert a lineage to files that did not produce them."""
    config = _config(tmp_path, demo=True)
    with Store(config.store_path) as store:
        refresh(config, store, now=1_000)
        assert store.source_mtimes() == {}


def test_unrecorded_origin_is_none_not_real(tmp_path: Path) -> None:
    """A store written before this field must read as "unknown", never "real"."""
    path = tmp_path / "legacy.sqlite"
    with Store(path) as store:
        store.save([], [], refreshed_at=1_000)
    _drop_origin_row(path)
    with Store(path) as store:
        assert store.state_origin() is None


# --- the freshness guard may not skip over fixture state --------------------


def test_real_refresh_after_demo_refresh_reingests(tmp_path: Path) -> None:
    """The regression: demo state must never satisfy a real refresh's skip check."""
    demo_config = _config(tmp_path, demo=True)
    with Store(demo_config.store_path) as store:
        refresh(demo_config, store, now=1_000)
        demo_states = store.load_states()

    real_config = _config(tmp_path, demo=False)
    with Store(real_config.store_path) as store:
        result = refresh(real_config, store, now=2_000)
        assert result.refreshed, "a real refresh skipped over demo-authored state"
        assert result.reason != "sources unchanged since last refresh"
        assert store.state_origin() == ORIGIN_REAL
        # The fixture books are gone, replaced by the real ingest.
        assert store.load_states() != demo_states


def test_real_refresh_still_skips_after_a_real_refresh(tmp_path: Path) -> None:
    """The guard keeps working for its actual purpose: unchanged real sources."""
    config = _config(tmp_path, demo=False)
    with Store(config.store_path) as store:
        refresh(config, store, now=1_000)
        result = refresh(config, store, now=2_000)
        assert not result.refreshed
        assert result.reason == "sources unchanged since last refresh"


def test_legacy_store_reingests_once(tmp_path: Path) -> None:
    """Unrecorded provenance re-ingests rather than trusting itself."""
    config = _config(tmp_path, demo=False)
    with Store(config.store_path) as store:
        refresh(config, store, now=1_000)
    _drop_origin_row(config.store_path)
    with Store(config.store_path) as store:
        result = refresh(config, store, now=2_000)
        assert result.refreshed
        assert store.state_origin() == ORIGIN_REAL


# --- the view reports provenance, and the surfaces say it -------------------


def test_view_flags_demo_authored_states(tmp_path: Path) -> None:
    config = _config(tmp_path, demo=True)
    with Store(config.store_path) as store:
        refresh(config, store, now=1_000)
        view = view_from_store(store, user="you", demo_mode=True)
    assert view.fixture_states
    assert view.fixture_candidates is False, (
        "the demo refresh persisted a real candidate pool, so no substitution happened"
    )


def test_view_separates_real_states_from_fixture_candidates(tmp_path: Path) -> None:
    """The `make dev` shape: a real store served with demo candidates on top."""
    config = _config(tmp_path, demo=False)
    with Store(config.store_path) as store:
        refresh(config, store, now=1_000)
        view = view_from_store(store, user="you", demo_mode=True)
    assert view.fixture_states is False, "real-ingested states were labelled as fixtures"
    assert view.fixture_candidates, "substituted demo candidates went unlabelled"


def test_real_view_flags_nothing(tmp_path: Path) -> None:
    config = _config(tmp_path, demo=False)
    with Store(config.store_path) as store:
        refresh(config, store, now=1_000)
        view = view_from_store(store, user="you", demo_mode=False)
    assert view.fixture_states is False
    assert view.fixture_candidates is False


@pytest.mark.parametrize(
    ("fixture_states", "fixture_candidates", "expected"),
    [
        (True, True, (FIXTURE_STATES_NOTICE, FIXTURE_CANDIDATES_NOTICE)),
        (False, True, (FIXTURE_CANDIDATES_NOTICE,)),
        (True, False, (FIXTURE_STATES_NOTICE,)),
    ],
)
def test_dashboard_names_fixture_content(
    tmp_path: Path,
    fixture_states: bool,
    fixture_candidates: bool,
    expected: tuple[str, ...],
) -> None:
    config = _config(tmp_path, demo=False)
    with Store(config.store_path) as store:
        refresh(config, store, now=1_000)
        view = view_from_store(store, user="you")
    html = render_view(
        replace(view, fixture_states=fixture_states, fixture_candidates=fixture_candidates)
    )
    for notice in expected:
        assert notice in html
    for notice in (FIXTURE_STATES_NOTICE, FIXTURE_CANDIDATES_NOTICE):
        if notice not in expected:
            assert notice not in html


def test_real_dashboard_carries_no_fixture_banner(tmp_path: Path) -> None:
    config = _config(tmp_path, demo=False)
    with Store(config.store_path) as store:
        refresh(config, store, now=1_000)
        html = render_view(view_from_store(store, user="you"))
    assert FIXTURE_STATES_NOTICE not in html
    assert FIXTURE_CANDIDATES_NOTICE not in html
    # The data-status panel still states provenance positively, so "no banner"
    # is a claim the page makes rather than an absence the reader must infer.
    assert "your configured libraries" in html
    assert "your stored catalog pool" in html


def test_data_status_names_the_fixture_sources(tmp_path: Path) -> None:
    config = _config(tmp_path, demo=True)
    with Store(config.store_path) as store:
        refresh(config, store, now=1_000)
        html = render_view(view_from_store(store, user="you", demo_mode=True))
    assert "built-in demo world (fixture books)" in html


# --- OPDS: the same claim, in the feed an e-reader browses ------------------


def test_opds_subtitle_flags_fixture_states(tmp_path: Path) -> None:
    config = _config(tmp_path, demo=True)
    with Store(config.store_path) as store:
        refresh(config, store, now=1_000)
        view = view_from_store(store, user="you", demo_mode=True)
    assert opds.fixture_subtitle(view) == opds.FIXTURE_STATES_SUBTITLE
    assert opds.FIXTURE_STATES_SUBTITLE in opds.build_root_navigation(view)
    feed = opds.build_shelf_acquisition(
        "to-read", "To read", [], subtitle=opds.fixture_subtitle(view, "to-read")
    )
    assert f"<subtitle>{opds.FIXTURE_STATES_SUBTITLE}</subtitle>" in feed


def test_opds_fixture_candidates_flag_only_the_recommendations_shelf(tmp_path: Path) -> None:
    config = _config(tmp_path, demo=False)
    with Store(config.store_path) as store:
        refresh(config, store, now=1_000)
        view = view_from_store(store, user="you", demo_mode=True)
    assert opds.fixture_subtitle(view, "recommendations") == opds.FIXTURE_CANDIDATES_SUBTITLE
    # The reader's own shelves are real here and must not be disclaimed.
    assert opds.fixture_subtitle(view, "to-read") == ""
    assert opds.fixture_subtitle(view, "currently-reading") == ""


def test_opds_real_view_emits_no_subtitle(tmp_path: Path) -> None:
    """No claim is better than an unverified reassurance."""
    config = _config(tmp_path, demo=False)
    with Store(config.store_path) as store:
        refresh(config, store, now=1_000)
        view = view_from_store(store, user="you")
    assert opds.fixture_subtitle(view) == ""
    assert "<subtitle>" not in opds.build_root_navigation(view)
    assert "<subtitle>" not in opds.build_shelf_acquisition("to-read", "To read", [])


# --- /share: the one surface built to be posted publicly --------------------
#
# Every other surface above keeps its disclosure on a page the reader is looking
# at. A share card is composed to *leave*: copied into Bookwyrm, or saved as an
# SVG and attached to a post. So the label has to travel with the card, not just
# sit on the page that produced it.


def _demo_authored_view(tmp_path: Path) -> object:
    """A demo-written store, read back the way a plain serve reads it.

    This is the `make dev` residue shape: one demo refresh populated the shared
    store, and the next serve does not set ``STACKS_DEMO=1``, so nothing in the
    live config says the state is fixtures. Only the persisted origin does.
    """
    config = _config(tmp_path, demo=True)
    with Store(config.store_path) as store:
        refresh(config, store, now=1_000)
    with Store(config.store_path) as store:
        return view_from_store(store, user="you", demo_mode=False)


def test_share_page_names_fixture_cards(tmp_path: Path) -> None:
    view = _demo_authored_view(tmp_path)
    assert view.fixture_states  # type: ignore[attr-defined]
    cards = build_share_cards(view)
    page = render_share_page(
        cards,
        user=view.user,  # type: ignore[attr-defined]
        fixture_states=view.fixture_states,  # type: ignore[attr-defined]
    )
    assert FIXTURE_PAGE_NOTICE in page
    assert FIXTURE_CARD_LINE in page
    assert CARD_SOURCE_FIXTURE in page
    assert CARD_SOURCE_REAL not in page


def test_every_share_card_from_a_fixture_view_is_marked(tmp_path: Path) -> None:
    """Both card kinds, not just the year one — a finished card names a book."""
    cards = build_share_cards(_demo_authored_view(tmp_path))
    assert {c.kind for c in cards} == {"year", "finished"}
    assert all(c.fixture for c in cards)


def test_fixture_disclosure_survives_leaving_the_page(tmp_path: Path) -> None:
    """The regression: the card was postable with nothing marking it as fixtures.

    Post text and the SVG are what actually reach Bookwyrm or Mastodon. A banner
    the reader left behind on ``/share`` does not travel with either.
    """
    for card in build_share_cards(_demo_authored_view(tmp_path)):
        assert FIXTURE_CARD_LINE in card.post_text(), card.kind
        assert FIXTURE_CARD_LINE in card.alt_text, card.kind
        assert FIXTURE_CARD_LINE in render_share_svg(card), card.kind


def test_real_share_page_and_cards_make_no_fixture_claim(tmp_path: Path) -> None:
    config = _config(tmp_path, demo=False)
    with Store(config.store_path) as store:
        refresh(config, store, now=1_000)
        view = view_from_store(store, user="you", demo_mode=False)
    assert view.fixture_states is False
    cards = build_share_cards(view)
    assert not any(c.fixture for c in cards)
    page = render_share_page(cards, user=view.user, fixture_states=view.fixture_states)
    assert FIXTURE_PAGE_NOTICE not in page
    assert FIXTURE_CARD_LINE not in page
    for card in cards:
        assert FIXTURE_CARD_LINE not in card.post_text()
        assert FIXTURE_CARD_LINE not in render_share_svg(card)
    # Stated positively, like the dashboard's data-status rows: "no banner" is a
    # claim the page makes, not an absence the reader has to infer.
    assert CARD_SOURCE_REAL in page


def test_share_routes_label_a_demo_authored_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end through the server, which is where the gap actually was.

    Seeds the shared store with a demo refresh, then serves with ``STACKS_DEMO``
    unset — one ``make dev`` run followed by a plain serve.
    """
    pytest.importorskip("fastapi")
    from app import server
    from fastapi.testclient import TestClient

    from tests.conftest import seed_store_from_env

    metadata_db, statistics_db = build_demo_dbs(tmp_path / "lib")
    monkeypatch.setenv("STACKS_CALIBRE_DB", str(metadata_db))
    monkeypatch.setenv("STACKS_KOREADER_DB", str(statistics_db))
    monkeypatch.setenv("STACKS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STACKS_DEMO", "1")
    seed_store_from_env()
    monkeypatch.delenv("STACKS_DEMO")
    # Demo mode is what supplies the built-in token; a plain serve must set one
    # or startup fails closed, so the test configures it the way a host would.
    monkeypatch.setenv("STACKS_AUTH_TOKEN", "route-test-token")

    auth = {"Authorization": "Bearer route-test-token"}
    with TestClient(server.create_app()) as client:
        page = client.get("/share", headers=auth)
        assert page.status_code == 200
        assert FIXTURE_PAGE_NOTICE in page.text
        assert FIXTURE_CARD_LINE in page.text

        svg = client.get("/share/card.svg", headers=auth)
        assert svg.status_code == 200
        assert FIXTURE_CARD_LINE in svg.text
