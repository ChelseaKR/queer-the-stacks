"""Serde round-trip fidelity + the persisted app-state store."""

from __future__ import annotations

from pathlib import Path

from ingest.models import DailyActivity
from ingest.serde import (
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
