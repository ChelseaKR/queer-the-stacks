"""Reliability: restart-recovery and graceful degradation when kosync is down."""

from __future__ import annotations

from pathlib import Path

from ingest.config import load_config
from ingest.models import (
    Author,
    Book,
    DeviceProgress,
    ReadingStat,
    ReadingStatus,
)
from ingest.refresh import refresh
from ingest.store import Store
from ingest.unify import unify


def test_restart_recovery(tmp_path: Path) -> None:
    """State written by one process is readable + renderable after a 'restart'."""
    cfg = load_config(
        env={"STACKS_DEMO": "1", "STACKS_DATA_DIR": str(tmp_path / "data")},
        config_path=tmp_path / "absent.toml",
    )
    with Store(cfg.store_path) as s:
        refresh(cfg, s, now=1_700_000_000)

    # New process: reopen the store and render — no re-ingest needed.
    from app.view import render_view, view_from_store

    with Store(cfg.store_path) as s:
        assert s.is_populated
        view = view_from_store(s, user="demo")
    assert "Currently reading" in render_view(view)


class _DownKosync:
    """A kosync source that always errors, simulating the server being down."""

    def progress_for(self, document: str) -> DeviceProgress:
        raise ConnectionError("sync.koreader.rocks unreachable")


def test_kosync_down_degrades_to_stats() -> None:
    book = Book(book_id="b", title="Kindred", authors=(Author("Octavia E. Butler"),))
    stat = ReadingStat("md5", "Kindred", ("Octavia E. Butler",), 287, 287, 5000, 1, 8)
    # Even though the progress source raises, unify still produces state.
    states = unify([book], [stat], _DownKosync())
    assert len(states) == 1
    assert states[0].progress == ()  # degraded: no device progress
    assert states[0].status is ReadingStatus.FINISHED  # from KOReader stats alone
