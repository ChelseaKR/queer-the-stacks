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
