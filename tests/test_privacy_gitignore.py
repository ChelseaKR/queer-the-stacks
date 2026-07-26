"""Sensitive runtime artifacts must be impossible to stage accidentally."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _ignored(paths: list[str]) -> set[str]:
    result = subprocess.run(  # noqa: S603 - fixed local git diagnostic
        ["git", "check-ignore", "--no-index", "--stdin"],  # noqa: S607 - fixed executable
        cwd=ROOT,
        input="\n".join(paths),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode in {0, 1}, result.stderr
    return set(result.stdout.splitlines())


def test_sensitive_runtime_artifacts_are_ignored() -> None:
    sensitive = [
        "stacks.toml",
        "data/app-state.sqlite-wal",
        "data/app-state.sqlite-shm",
        "data/app-state.sqlite-journal",
        "data/catalog-response-cache.json",
        "data/lists.json",
        "data/lenses.toml",
        "data/backups/20260725.sqlite",
    ]
    assert _ignored(sensitive) == set(sensitive)


def test_shipped_lens_example_remains_trackable() -> None:
    assert _ignored(["examples/lenses.example.toml"]) == set()
