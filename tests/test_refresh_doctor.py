"""Refresh orchestration (real + demo paths, mtime guard) and doctor diagnostics."""

from __future__ import annotations

from pathlib import Path

import pytest
from ingest.config import Config, load_config
from ingest.demo import build_demo_dbs
from ingest.kosync import FixtureKosync
from ingest.models import DeviceProgress, ReadingStat
from ingest.refresh import (
    _resolve_progress,
    _stat_signature,
    doctor,
    fetch_progress,
    ingest_states,
    refresh,
    source_mtimes,
)
from ingest.store import Store


def _real_config(tmp_path: Path) -> Config:
    """A non-demo config pointed at on-disk demo SQLite (real readers, no network)."""
    metadata_db, statistics_db = build_demo_dbs(tmp_path / "lib")
    return load_config(
        env={
            "STACKS_CALIBRE_DB": str(metadata_db),
            "STACKS_KOREADER_DB": str(statistics_db),
            "STACKS_DATA_DIR": str(tmp_path / "data"),
        },
        config_path=tmp_path / "absent.toml",
    )


def test_demo_refresh_populates_store(tmp_path: Path) -> None:
    cfg = load_config(
        env={"STACKS_DEMO": "1", "STACKS_DATA_DIR": str(tmp_path / "data")},
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
        env={"STACKS_CALIBRE_DB": str(tmp_path / "missing.db")},
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
        env={
            "STACKS_CALIBRE_DB": str(tmp_path / "nope.db"),
            "STACKS_DATA_DIR": str(tmp_path / "d"),
        },
        config_path=tmp_path / "absent.toml",
    )
    checks = doctor(cfg)
    failing = [c for c in checks if not c.ok]
    assert any("Calibre" in c.name for c in failing)


def test_doctor_demo_mode(tmp_path: Path) -> None:
    cfg = load_config(env={"STACKS_DEMO": "1"}, config_path=tmp_path / "absent.toml")
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
        env={"STACKS_DEMO": "1", "STACKS_DATA_DIR": str(tmp_path / "data")},
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


# --- fetch_progress: batched, bounded-concurrency kosync fetch (FIX-08) -----


class _FlakySource:
    """A fake ProgressSource that raises for some keys and succeeds for others."""

    def __init__(self, fail_keys: set[str]) -> None:
        self._fail = fail_keys

    def progress_for(self, document: str) -> DeviceProgress:
        if document in self._fail:
            raise RuntimeError(f"boom:{document}")
        return DeviceProgress(document=document, percentage=0.5, device="Kobo", timestamp=1)


def test_fetch_progress_batches_and_records_error_outcomes() -> None:
    source = _FlakySource(fail_keys={"b"})
    result = fetch_progress(source, ["a", "b", "c", ""], max_workers=4)

    # Empty keys are dropped before dispatch; the rest are all attempted.
    assert set(result.progress) == {"a", "c"}
    assert result.fetched == 2
    assert result.errors == 1

    by_key = {o.key: o for o in result.outcomes}
    assert by_key["a"].ok is True and by_key["a"].found is True
    assert by_key["c"].ok is True and by_key["c"].found is True
    assert by_key["b"].ok is False and by_key["b"].found is False
    assert "boom:b" in by_key["b"].error
    assert "" not in by_key

    # Deterministic ordering regardless of which fetch finishes first.
    assert [o.key for o in result.outcomes] == sorted(by_key)


def test_fetch_progress_no_progress_is_not_an_error() -> None:
    result = fetch_progress(FixtureKosync({}), ["missing"])
    assert result.progress == {}
    assert result.fetched == 0
    assert result.errors == 0
    outcome = result.outcomes[0]
    assert outcome.key == "missing"
    assert outcome.ok is True
    assert outcome.found is False


def test_fetch_progress_handles_no_source_or_no_keys() -> None:
    assert fetch_progress(None, ["a"]).progress == {}
    assert fetch_progress(FixtureKosync({}), []).progress == {}


def test_errored_fetch_stays_stale_and_is_retried(tmp_path: Path) -> None:
    """A transport error must not be cached as "checked, no progress".

    If the sync server is down during one refresh, the affected key must be
    re-fetched on the next refresh even though the local stat is unchanged —
    otherwise one transient outage silently suppresses that book's progress
    until the user next reads it on-device (the exact failure mode FIX-08
    exists to kill).
    """
    stat = ReadingStat("k1", "Nevada", ("Imogen Binnie",), 50, 250, 3600, 1_700_000_000, 2)
    with Store(tmp_path / "progress.sqlite") as store:
        # First refresh: the source errors for k1 -> visible error outcome.
        down = _resolve_progress(_FlakySource(fail_keys={"k1"}), [stat], store, now=1)
        assert down.errors == 1
        assert down.progress == {}
        # The errored key must still be stale — not persisted as "checked".
        assert "k1" in store.stale_progress_keys({"k1": _stat_signature(stat)})

        # Second refresh with the server back up and the *same* local stat:
        # the key is re-fetched and resolves instead of being skipped.
        up = _resolve_progress(_FlakySource(fail_keys=set()), [stat], store, now=2)
        assert up.errors == 0
        assert "k1" in up.progress
        assert store.cached_progress()["k1"].device == "Kobo"
        # And now that it succeeded, an unchanged stat is no longer stale.
        assert store.stale_progress_keys({"k1": _stat_signature(stat)}) == set()


# --- RefreshResult surfaces per-source progress outcomes (FIX-08 -> FIX-09) -


def test_refresh_result_exposes_progress_counts(tmp_path: Path) -> None:
    cfg = load_config(
        env={"STACKS_DEMO": "1", "STACKS_DATA_DIR": str(tmp_path / "data")},
        config_path=tmp_path / "absent.toml",
    )
    with Store(cfg.store_path) as store:
        result = refresh(cfg, store, now=1_700_000_000)
    assert result.progress_fetched > 0
    assert result.progress_errors == 0
    assert len(result.progress_outcomes) >= result.progress_fetched


# --- store-backed cache: unchanged stats skip re-fetch (FIX-08) ------------


def test_store_progress_cache_skips_unchanged_stats(tmp_path: Path) -> None:
    with Store(tmp_path / "progress.sqlite") as store:
        signatures = {"k1": "sig-a", "k2": "sig-b"}
        assert store.stale_progress_keys(signatures) == {"k1", "k2"}

        dp = DeviceProgress(document="k1", percentage=0.3, device="Kobo", timestamp=10)
        store.save_progress({"k1": dp}, signatures, fetched_at=100)

        assert store.cached_progress() == {"k1": dp}
        # k2 had no progress found, but it was checked — not stale if unchanged.
        assert store.stale_progress_keys(signatures) == set()

        # Only the key whose signature actually changed is reported stale.
        changed = {"k1": "sig-a", "k2": "sig-c"}
        assert store.stale_progress_keys(changed) == {"k2"}


def test_refresh_reuses_cached_progress_when_stats_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second refresh with unchanged local stats must not re-fetch kosync."""
    import ingest.refresh as refresh_mod

    real_fetch_progress = refresh_mod.fetch_progress
    calls: list[tuple[str, ...]] = []

    def counting_fetch_progress(source: object, keys: object, *, max_workers: int = 8):
        keys = list(keys)  # type: ignore[arg-type]
        calls.append(tuple(sorted(keys)))
        return real_fetch_progress(source, keys, max_workers=max_workers)

    monkeypatch.setattr(refresh_mod, "fetch_progress", counting_fetch_progress)

    cfg = load_config(
        env={"STACKS_DEMO": "1", "STACKS_DATA_DIR": str(tmp_path / "data")},
        config_path=tmp_path / "absent.toml",
    )
    with Store(cfg.store_path) as store:
        first = refresh(cfg, store, now=1, force=True)
        assert len(calls) == 1
        assert calls[0]  # first refresh has nothing cached, fetches every key
        assert first.progress_fetched > 0

        second = refresh(cfg, store, now=2, force=True)
        # Local stats are unchanged (same demo world) -> cache fully covers it,
        # so fetch_progress is never called a second time.
        assert len(calls) == 1
        assert second.progress_fetched == first.progress_fetched
