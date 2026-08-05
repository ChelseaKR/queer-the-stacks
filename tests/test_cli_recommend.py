"""``stacks recommend`` must never pass demo fixtures off as real output.

The command used to call ``_demo_states_and_candidates()`` unconditionally, so
a reader who had configured a real library and run ``stacks refresh`` still got
fixture titles — with fit scores and explanations, and nothing on screen saying
"demo". Running it against a real 1,907-book library surfaced how bad that is:
three of the five printed picks were books already in that library, which makes
the fixture output indistinguishable from a real recommendation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ingest.cli import main
from ingest.demo import build_demo_dbs

#: Titles that only ever come from the demo fixture set.
FIXTURE_TITLES = ("An Unkindness of Ghosts", "The Fifth Season", "Confessions of the Fox")


def _configure_real_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    metadata_db, statistics_db = build_demo_dbs(tmp_path / "lib")
    monkeypatch.delenv("STACKS_DEMO", raising=False)
    monkeypatch.setenv("STACKS_CALIBRE_DB", str(metadata_db))
    monkeypatch.setenv("STACKS_KOREADER_DB", str(statistics_db))
    monkeypatch.setenv("STACKS_DATA_DIR", str(tmp_path / "data"))


def test_real_mode_never_falls_back_to_fixtures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With a real library and no candidates, say so — do not print fixtures."""
    from tests.conftest import seed_store_from_env

    _configure_real_library(tmp_path, monkeypatch)
    seed_store_from_env()

    assert main(["recommend"]) == 1
    out = capsys.readouterr()
    combined = out.out + out.err
    for title in FIXTURE_TITLES:
        assert title not in combined, f"demo fixture {title!r} leaked into real output"
    assert "no recommendation candidates" in combined
    assert "catalog egress" in combined


def test_unrefreshed_store_asks_for_a_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A configured library that was never ingested is a distinct, actionable state."""
    _configure_real_library(tmp_path, monkeypatch)

    assert main(["recommend"]) == 1
    combined = capsys.readouterr().err
    assert "stacks refresh" in combined
    for title in FIXTURE_TITLES:
        assert title not in combined


def test_demo_mode_still_recommends_but_labels_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Demo mode keeps working — it just stops pretending to be a real library."""
    monkeypatch.setenv("STACKS_DEMO", "1")
    monkeypatch.setenv("STACKS_DATA_DIR", str(tmp_path / "data"))

    assert main(["recommend"]) == 0
    out = capsys.readouterr().out
    assert "demo mode" in out
    assert any(title in out for title in FIXTURE_TITLES)
