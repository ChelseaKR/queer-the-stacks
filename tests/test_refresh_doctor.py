"""Refresh orchestration (real + demo paths, mtime guard) and doctor diagnostics."""

from __future__ import annotations

from pathlib import Path

from ingest.config import Config, load_config
from ingest.demo import build_demo_dbs
from ingest.refresh import doctor, ingest_states, refresh, source_mtimes
from ingest.store import Store


def _real_config(tmp_path: Path) -> Config:
    """A non-demo config pointed at on-disk demo SQLite (real readers, no network)."""
    metadata_db, statistics_db = build_demo_dbs(tmp_path / "lib")
    return load_config(
        env={
            "QSR_CALIBRE_DB": str(metadata_db),
            "QSR_KOREADER_DB": str(statistics_db),
            "QSR_DATA_DIR": str(tmp_path / "data"),
        },
        config_path=tmp_path / "absent.toml",
    )


def test_demo_refresh_populates_store(tmp_path: Path) -> None:
    cfg = load_config(
        env={"QSR_DEMO": "1", "QSR_DATA_DIR": str(tmp_path / "data")},
        config_path=tmp_path / "absent.toml",
    )
    with Store(cfg.store_path) as store:
        result = refresh(cfg, store, now=1_700_000_000)
        assert result.refreshed is True
        assert result.n_states >= 8
        assert store.is_populated
        # Reading state actually round-tripped through the store.
        titles = {s.title for s in store.load_states()}
        assert "Kindred" in titles


def test_real_refresh_reads_sources(tmp_path: Path) -> None:
    cfg = _real_config(tmp_path)
    assert cfg.demo is False
    states, activity = ingest_states(cfg)
    assert any(s.title == "Kindred" for s in states)
    assert activity  # daily activity reconstructed from page stats


def test_mtime_guard_skips_unchanged(tmp_path: Path) -> None:
    cfg = _real_config(tmp_path)
    with Store(cfg.store_path) as store:
        first = refresh(cfg, store, now=100)
        assert first.refreshed is True
        # Nothing changed -> second refresh is skipped.
        second = refresh(cfg, store, now=200)
        assert second.refreshed is False
        assert "unchanged" in second.reason
        assert store.refreshed_at() == 100  # not overwritten
        # ...unless forced.
        forced = refresh(cfg, store, now=300, force=True)
        assert forced.refreshed is True
        assert store.refreshed_at() == 300


def test_source_mtimes_only_existing(tmp_path: Path) -> None:
    cfg = load_config(
        env={"QSR_CALIBRE_DB": str(tmp_path / "missing.db")},
        config_path=tmp_path / "absent.toml",
    )
    assert source_mtimes(cfg) == {}  # file does not exist


def test_doctor_real_sources_ok(tmp_path: Path) -> None:
    cfg = _real_config(tmp_path)
    with Store(cfg.store_path) as store:
        checks = doctor(cfg, store)
    by_name = {c.name: c for c in checks}
    assert by_name["Calibre file"].ok
    assert by_name["Calibre read-only access"].ok
    assert by_name["KOReader read-only access"].ok
    assert by_name["kosync"].ok  # reports "not configured" but is not a failure


def test_doctor_flags_missing_file(tmp_path: Path) -> None:
    cfg = load_config(
        env={"QSR_CALIBRE_DB": str(tmp_path / "nope.db"), "QSR_DATA_DIR": str(tmp_path / "d")},
        config_path=tmp_path / "absent.toml",
    )
    checks = doctor(cfg)
    failing = [c for c in checks if not c.ok]
    assert any("Calibre" in c.name for c in failing)


def test_doctor_demo_mode(tmp_path: Path) -> None:
    cfg = load_config(env={"QSR_DEMO": "1"}, config_path=tmp_path / "absent.toml")
    checks = doctor(cfg)
    mode = next(c for c in checks if c.name == "mode")
    assert "demo" in mode.detail
    assert all(c.ok for c in checks)


def test_doctor_runs_without_writing_to_calibre(tmp_path: Path) -> None:
    """Doctor must not mutate the source DB it inspects."""
    import hashlib

    cfg = _real_config(tmp_path)
    assert cfg.calibre_db is not None
    before = hashlib.sha256(cfg.calibre_db.read_bytes()).hexdigest()
    doctor(cfg)
    after = hashlib.sha256(cfg.calibre_db.read_bytes()).hexdigest()
    assert before == after


def test_view_from_store_renders(tmp_path: Path) -> None:
    from app.render import render_dashboard
    from app.view import view_from_store

    cfg = load_config(
        env={"QSR_DEMO": "1", "QSR_DATA_DIR": str(tmp_path / "data")},
        config_path=tmp_path / "absent.toml",
    )
    with Store(cfg.store_path) as store:
        refresh(cfg, store, now=1_700_000_000)
        view = view_from_store(store, user="demo")
    assert view.stats.books_finished >= 7
    assert view.recommendations
    html = render_dashboard(
        view.currently_reading,
        view.finished,
        view.stats,
        view.wrapped,
        view.recommendations,
        user=view.user,
    )
    assert "Recommended for you" in html
