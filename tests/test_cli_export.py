"""Static dashboard export must use the same view-affecting config as the server."""

from __future__ import annotations

from pathlib import Path

import app.view
import pytest
from ingest.cli import main


def test_export_forwards_every_view_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.conftest import seed_store_from_env

    monkeypatch.setenv("STACKS_DEMO", "1")
    monkeypatch.setenv("STACKS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STACKS_EMBEDDINGS", "1")
    monkeypatch.setenv("STACKS_DNF_SIGNALS", "1")
    monkeypatch.setenv("STACKS_GOAL_HOURS", "77")
    monkeypatch.setenv("STACKS_HIDE_SENSITIVE", "1")
    seed_store_from_env()

    captured: dict[str, object] = {}
    real_view_from_store = app.view.view_from_store

    def capture_view_flags(*args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return real_view_from_store(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(app.view, "view_from_store", capture_view_flags)
    output = tmp_path / "dashboard.html"

    assert main(["export", "--out", str(output)]) == 0
    assert output.is_file()
    assert captured["use_embeddings"] is True
    assert captured["dnf_signals"] is True
    assert captured["goal_hours"] == 77
    assert captured["hide_sensitive_descriptors"] is True
