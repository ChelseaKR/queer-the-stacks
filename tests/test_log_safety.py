"""No-reading-content-in-logs guarantee.

Reading data is sensitive, so the core is kept **log-free**: no module in
ingest/recommender/app imports the logging machinery or configures handlers.
With no logs, a reading title or progress value can never leak into one. The CLI
prints to stdout by design (the user ran it); that is not logging.
"""

from __future__ import annotations

from pathlib import Path

import app
import ingest
import recommender

LOGGING_TOKENS = ("import logging", "getLogger", "logging.basicConfig", "logging.getLogger")


def _source_files() -> list[Path]:
    roots = [Path(pkg.__file__).parent for pkg in (ingest, recommender, app)]
    return [p for root in roots for p in root.rglob("*.py")]


def test_core_is_log_free() -> None:
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        for token in LOGGING_TOKENS:
            assert token not in text, f"{path.name} uses logging ({token}); keep the core log-free"
