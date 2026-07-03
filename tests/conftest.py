"""Shared fixtures — the offline demo world, built on a temp directory."""

from __future__ import annotations

from pathlib import Path

import pytest
from ingest.demo import (
    DEMO_USER,
    build_demo_dbs,
    demo_candidates,
    demo_reading_states,
)
from ingest.koreader import load_daily_activity
from recommender.lists import DEMO_LISTS


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def demo_dbs(workdir: Path) -> tuple[Path, Path]:
    return build_demo_dbs(workdir)


@pytest.fixture
def states(workdir: Path) -> list:
    return demo_reading_states(workdir)


@pytest.fixture
def daily_activity(demo_dbs: tuple[Path, Path], workdir: Path) -> list:
    _, statistics_db = demo_dbs
    return load_daily_activity(statistics_db, workdir / "snapshots")


@pytest.fixture
def candidates() -> tuple:
    return demo_candidates()


@pytest.fixture
def lists() -> tuple:
    return DEMO_LISTS


@pytest.fixture
def demo_user() -> str:
    return DEMO_USER


@pytest.fixture
def full_view(workdir: Path):
    from app.view import demo_view

    return demo_view(workdir)


def seed_store_from_env() -> None:
    """Populate the app-state store for the currently-configured ``STACKS_*`` env.

    The server never ingests inside a request (FIX-14): routes 503 until the
    store has been refreshed. Tests that exercise data routes through a
    TestClient call this after ``monkeypatch``-ing ``STACKS_DEMO``/
    ``STACKS_DATA_DIR`` and before making requests — the same effect as
    running ``stacks refresh`` once against that data dir.
    """
    import time

    from ingest.config import load_config
    from ingest.refresh import refresh
    from ingest.store import Store

    config = load_config()
    store = Store(config.store_path)
    try:
        refresh(config, store, now=int(time.time()))
    finally:
        store.close()
