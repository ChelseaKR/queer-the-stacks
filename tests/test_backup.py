"""Backup + restore of the app-state store."""

from __future__ import annotations

from pathlib import Path

import pytest
from ingest.backup import backup_store, list_backups, restore_store
from ingest.store import Store


def _populated(path: Path, states: list) -> None:
    with Store(path) as s:
        s.save(states, [], refreshed_at=1_700_000_000)


def test_backup_and_restore_round_trip(states: list, tmp_path: Path) -> None:
    store_path = tmp_path / "app-state.sqlite"
    _populated(store_path, states)

    backup = backup_store(store_path, tmp_path / "backups", "20260606T000000")
    assert backup.exists()
    assert list_backups(tmp_path / "backups") == [backup]

    # Corrupt the live store, then restore.
    store_path.write_bytes(b"corrupted")
    restore_store(backup, store_path)
    with Store(store_path) as s:
        assert s.refreshed_at() == 1_700_000_000
        assert len(s.load_states()) == len(states)


def test_backup_missing_store(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        backup_store(tmp_path / "nope.sqlite", tmp_path / "backups", "stamp")


def test_restore_missing_backup(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        restore_store(tmp_path / "nope.sqlite", tmp_path / "store.sqlite")


def test_list_backups_empty(tmp_path: Path) -> None:
    assert list_backups(tmp_path / "absent") == []
