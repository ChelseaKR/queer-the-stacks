"""KOReader reader: per-book stats, session reconstruction, daily activity."""

from __future__ import annotations

from pathlib import Path

from ingest.koreader import load_daily_activity, load_stats, read_stats
from ingest.snapshot import open_readonly


def test_reads_stats_for_owned_books(demo_dbs: tuple[Path, Path], workdir: Path) -> None:
    _, statistics_db = demo_dbs
    stats = load_stats(statistics_db, workdir / "snapshots")
    assert len(stats) >= 8
    kindred = next(s for s in stats if s.title == "Kindred")
    assert kindred.total_pages == 287
    assert kindred.is_finished
    assert kindred.read_time_seconds > 0
    assert kindred.key  # has an md5 join key


def test_in_progress_book_not_finished(demo_dbs: tuple[Path, Path], workdir: Path) -> None:
    _, statistics_db = demo_dbs
    stats = load_stats(statistics_db, workdir / "snapshots")
    sbb = next(s for s in stats if s.title == "Stone Butch Blues")
    assert not sbb.is_finished
    assert 0.0 < sbb.percent_complete < 1.0


def test_sessions_reconstructed(demo_dbs: tuple[Path, Path], workdir: Path) -> None:
    _, statistics_db = demo_dbs
    stats = load_stats(statistics_db, workdir / "snapshots")
    # Every read book should have at least one reconstructed session.
    assert all(s.sessions >= 1 for s in stats if s.read_time_seconds > 0)


def test_daily_activity_aggregates_by_day(demo_dbs: tuple[Path, Path], workdir: Path) -> None:
    _, statistics_db = demo_dbs
    activity = load_daily_activity(statistics_db, workdir / "snapshots")
    assert activity
    # Sorted ascending, each day positive.
    days = [d.day_ordinal for d in activity]
    assert days == sorted(days)
    assert all(d.seconds > 0 and d.pages > 0 for d in activity)


def test_empty_koreader_db(workdir: Path) -> None:
    import sqlite3

    db = workdir / "empty.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript("CREATE TABLE unrelated (x INTEGER);")
    conn.commit()
    conn.close()
    with open_readonly(db) as ro:
        assert read_stats(ro) == []
