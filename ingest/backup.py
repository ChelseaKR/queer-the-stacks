"""Backup + restore for the persisted app-state store.

The store under ``data/`` holds derived reading state (sensitive, local). These
helpers make a timestamped copy and restore from one, so a tired on-call human
can recover after a bad refresh or a disk move. Backups stay local — they are as
sensitive as the store itself.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def backup_store(store_path: Path, backups_dir: Path, stamp: str) -> Path:
    """Copy the store to ``backups_dir/app-state.<stamp>.sqlite`` and return it.

    ``stamp`` is passed in (e.g. an ISO timestamp) so the function stays
    deterministic and testable — it never reads the wall clock.
    """
    store_path = Path(store_path)
    if not store_path.is_file():
        raise FileNotFoundError(f"no store to back up at {store_path}")
    backups_dir = Path(backups_dir)
    backups_dir.mkdir(parents=True, exist_ok=True)
    dest = backups_dir / f"{store_path.stem}.{stamp}{store_path.suffix}"
    shutil.copy2(store_path, dest)
    return dest


def restore_store(backup_path: Path, store_path: Path) -> Path:
    """Restore the store from a backup, overwriting the live store."""
    backup_path = Path(backup_path)
    if not backup_path.is_file():
        raise FileNotFoundError(f"backup not found: {backup_path}")
    store_path = Path(store_path)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_path, store_path)
    return store_path


def list_backups(backups_dir: Path) -> list[Path]:
    """All backup files under ``backups_dir``, newest filename last (sorted)."""
    backups_dir = Path(backups_dir)
    if not backups_dir.is_dir():
        return []
    return sorted(backups_dir.glob("app-state.*.sqlite"))
