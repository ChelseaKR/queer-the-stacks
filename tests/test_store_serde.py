"""Serde round-trip fidelity + the persisted app-state store."""

from __future__ import annotations

from pathlib import Path

from ingest.models import Book, DailyActivity
from ingest.serde import (
    _book_from_dict,
    _book_to_dict,
    activity_from_dict,
    activity_to_dict,
    state_from_dict,
    state_to_dict,
)
from ingest.store import Store


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
        assert len(store.load_states()) == 1
