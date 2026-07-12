"""Reliability: restart-recovery and graceful degradation when kosync is down."""

from __future__ import annotations

from pathlib import Path

from ingest.config import load_config
from ingest.kosync import FixtureKosync
from ingest.models import (
    Author,
    Book,
    DeviceProgress,
    ReadingStat,
    ReadingStatus,
)
from ingest.refresh import fetch_progress, refresh
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
    """Graceful degradation now happens in fetch_progress, upstream of unify().

    FIX-08: unify() no longer swallows a raising ProgressSource itself — the
    outage is captured as a visible error outcome in fetch_progress, and unify()
    just reads whatever (possibly empty) map results from that.
    """
    book = Book(book_id="b", title="Kindred", authors=(Author("Octavia E. Butler"),))
    stat = ReadingStat("md5", "Kindred", ("Octavia E. Butler",), 287, 287, 5000, 1, 8)

    result = fetch_progress(_DownKosync(), [stat.key])
    assert result.errors == 1
    assert result.progress == {}
    assert "sync.koreader.rocks unreachable" in result.outcomes[0].error

    # The resolved (degraded) map still lets unify produce state from stats alone.
    states = unify([book], [stat], FixtureKosync(result.progress))
    assert len(states) == 1
    assert states[0].progress == ()  # degraded: no device progress
    assert states[0].status is ReadingStatus.FINISHED  # from KOReader stats alone
