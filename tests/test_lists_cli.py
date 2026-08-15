"""End-to-end: ``stacks lists new/add/export`` via the CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ingest.cli import main
from recommender.lists_store import load_stored_lists


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STACKS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STACKS_CONFIG", str(tmp_path / "no-such-config.toml"))


def test_lists_new_add_export_round_trip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "lists",
                "new",
                "My Canon",
                "--citation",
                "curated-list:my-canon",
                "--book",
                "ol:nevada",
            ]
        )
        == 0
    )
    assert main(["lists", "add", "My Canon", "--book", "ol:fifth-season"]) == 0

    out_path = tmp_path / "out.json"
    assert main(["lists", "export", "--out", str(out_path)]) == 0

    captured = capsys.readouterr()
    assert "created list" in captured.out
    assert "now has 2 book(s)" in captured.out
    assert "exported 1 list(s)" in captured.out

    reimported = load_stored_lists(out_path)
    assert len(reimported) == 1
    assert reimported[0].name == "My Canon"
    assert reimported[0].book_ids == ("ol:nevada", "ol:fifth-season")


def test_lists_export_to_stdout_is_valid_json(capsys: pytest.CaptureFixture[str]) -> None:
    main(["lists", "new", "A", "--citation", "curated-list:a", "--book", "ol:1"])
    capsys.readouterr()  # discard the "created list" line
    assert main(["lists", "export"]) == 0
    body = capsys.readouterr().out
    parsed = json.loads(body)
    assert parsed[0]["name"] == "A"


def test_lists_ls_reports_authored_lists(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["lists", "ls"]) == 0
    assert "no authored lists yet" in capsys.readouterr().out

    main(["lists", "new", "A", "--citation", "curated-list:a", "--book", "ol:1"])
    capsys.readouterr()
    assert main(["lists", "ls"]) == 0
    assert "A — curated-list:a — 1 book(s)" in capsys.readouterr().out


def test_lists_new_duplicate_name_fails() -> None:
    main(["lists", "new", "A", "--citation", "curated-list:a", "--book", "ol:1"])
    with pytest.raises(Exception, match="already exists"):
        main(["lists", "new", "A", "--citation", "curated-list:b", "--book", "ol:2"])


def test_lists_add_to_missing_list_fails() -> None:
    with pytest.raises(Exception, match="no list named"):
        main(["lists", "add", "Does Not Exist", "--book", "ol:1"])


def test_lists_new_stamps_today_not_a_constant() -> None:
    """A list authored today is dated today, and never the old literal.

    `CuratedList.retrieved_at` used to default to "2026-06-05", so every list
    `stacks lists new` created claimed a June retrieval date no matter when it
    was made — a provenance field that is a constant, which reads as evidence
    while carrying none.
    """
    import datetime

    from ingest.config import load_config
    from recommender.lists_store import list_store_path

    today = datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%d")

    assert main(["lists", "new", "Made Today", "--citation", "c:x", "--book", "ol:1"]) == 0

    stored = load_stored_lists(list_store_path(load_config()))
    assert stored[0].retrieved_at == today
    assert stored[0].retrieved_at != "2026-06-05"


def test_lists_new_accepts_a_known_fetch_date() -> None:
    """Transcribing a list fetched on a known day records that day, not today."""
    from ingest.config import load_config
    from recommender.lists_store import list_store_path

    assert (
        main(
            [
                "lists",
                "new",
                "Fetched Earlier",
                "--citation",
                "https://bookwyrm.social/list/42",
                "--book",
                "ol:1",
                "--retrieved-at",
                "2026-07-19",
            ]
        )
        == 0
    )

    stored = load_stored_lists(list_store_path(load_config()))
    assert stored[0].retrieved_at == "2026-07-19"
