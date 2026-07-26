"""Serde round-trip fidelity + the persisted app-state store."""

from __future__ import annotations

from pathlib import Path

from ingest.models import Author, Book, DailyActivity
from ingest.serde import (
    _book_from_dict,
    _book_to_dict,
    activity_from_dict,
    activity_to_dict,
    state_from_dict,
    state_to_dict,
)
from ingest.store import CatalogSourceUpdate, Store


def test_state_round_trips_with_full_fidelity(states: list) -> None:
    for s in states:
        assert state_from_dict(state_to_dict(s)) == s


def test_activity_round_trips() -> None:
    a = DailyActivity(day_ordinal=19000, seconds=1234, pages=42)
    assert activity_from_dict(activity_to_dict(a)) == a


def test_book_languages_and_publisher_round_trip() -> None:
    """FIX-11: sourced languages/publisher facts survive a to_dict/from_dict cycle."""
    b = Book(
        book_id="calibre:1",
        title="Translated Novel",
        languages=("eng", "fra"),
        publisher="Small Press",
    )
    d = _book_to_dict(b)
    assert d["languages"] == ["eng", "fra"]
    assert d["publisher"] == "Small Press"
    assert _book_from_dict(d) == b


def test_book_languages_and_publisher_backward_compat() -> None:
    """Old persisted snapshots lack the new keys; unknown stays first-class."""
    d = {"book_id": "calibre:2", "title": "Old Snapshot", "authors": []}
    b = _book_from_dict(d)
    assert b.languages == ()
    assert b.publisher is None


def test_store_save_and_load(states: list, daily_activity: list, tmp_path: Path) -> None:
    store = Store(tmp_path / "state.sqlite")
    try:
        assert store.is_populated is False
        store.save(states, daily_activity, refreshed_at=1_700_000_000, source_mtimes={"calibre": 5})
        assert store.is_populated is True
        assert store.refreshed_at() == 1_700_000_000
        assert store.view_revision() == 1
        assert store.source_mtimes() == {"calibre": 5}
        loaded = store.load_states()
        assert loaded == states
        assert store.load_daily_activity() == daily_activity
    finally:
        store.close()


def test_store_empty_reads(tmp_path: Path) -> None:
    with Store(tmp_path / "empty.sqlite") as store:
        assert store.load_states() == []
        assert store.load_daily_activity() == []
        assert store.refreshed_at() is None
        assert store.source_mtimes() == {}


def test_store_overwrites_on_resave(states: list, tmp_path: Path) -> None:
    with Store(tmp_path / "s.sqlite") as store:
        store.save(states, [], refreshed_at=1)
        store.save(states[:1], [], refreshed_at=2)
        assert store.refreshed_at() == 2
        assert store.view_revision() == 2
        assert len(store.load_states()) == 1


def test_catalog_pool_preserves_last_good_source_on_failure(tmp_path: Path) -> None:
    book = Book(book_id="ol:1", title="A Public Book", authors=(Author("Writer"),))
    source_id = "openlibrary:subject:queer_fiction"
    with Store(tmp_path / "catalog.sqlite") as store:
        store.save_catalog_refresh(
            (CatalogSourceUpdate(source_id=source_id, books=(book,)),),
            active_source_ids={source_id},
            attempted_at=100,
            outbound_mode="public-metadata",
        )
        assert store.view_revision() == 1
        assert store.load_catalog_candidates() == (book,)
        assert store.catalog_pool_status().state == "fresh"

        store.save_catalog_refresh(
            (CatalogSourceUpdate(source_id=source_id, ok=False, error="Timeout"),),
            active_source_ids={source_id},
            attempted_at=200,
            outbound_mode="public-metadata",
        )
        assert store.view_revision() == 2
        assert store.load_catalog_candidates() == (book,)
        status = store.catalog_pool_status()
        assert status.state == "degraded"
        assert status.attempted_at == 200
        assert status.candidate_count == 1
        assert status.sources[0].fetched_at == 100
        assert status.sources[0].error == "Timeout"


def test_catalog_mode_off_is_explicit_and_keeps_cached_public_metadata(tmp_path: Path) -> None:
    book = Book(book_id="ol:1", title="Cached")
    source_id = "openlibrary:subject:queer_fiction"
    with Store(tmp_path / "catalog.sqlite") as store:
        store.save_catalog_refresh(
            (CatalogSourceUpdate(source_id=source_id, books=(book,)),),
            active_source_ids={source_id},
            attempted_at=100,
            outbound_mode="public-metadata",
        )
        store.save_catalog_mode("off", {source_id})
        assert store.catalog_pool_status().state == "off"
        assert store.load_catalog_candidates() == (book,)
