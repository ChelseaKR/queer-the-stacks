"""No-reading-content-in-logs guarantee.

Reading data is sensitive, so the **core** is kept log-free: no module in
ingest/recommender/app imports the logging machinery or configures handlers —
except the deliberately-audited web-request boundary. With the core log-free, a
reading title or progress value can never reach a log line.

The request boundary (``app/logging_config.py`` + its wiring in ``app/server.py``)
does emit structured JSON access logs, but only request *metadata* — method,
path (never the query string), status, latency, request id. That PII-safety is
asserted separately in ``tests/test_observability.py``. The CLI prints to stdout
by design (the user ran it); that is not logging.
"""

from __future__ import annotations

from pathlib import Path

import app
import ingest
import recommender

LOGGING_TOKENS = ("import logging", "getLogger", "logging.basicConfig", "logging.getLogger")

# The only files permitted to use the logging machinery: the audited request
# logger and the server module that wires it in. Everything else stays log-free.
LOG_ALLOWED = {"logging_config.py", "server.py"}


def _source_files() -> list[Path]:
    roots = [Path(pkg.__file__).parent for pkg in (ingest, recommender, app)]
    return [p for root in roots for p in root.rglob("*.py")]


def test_core_is_log_free() -> None:
    for path in _source_files():
        if path.name in LOG_ALLOWED:
            continue
        text = path.read_text(encoding="utf-8")
        for token in LOGGING_TOKENS:
            assert token not in text, f"{path.name} uses logging ({token}); keep the core log-free"


def test_request_logger_is_confined_to_the_web_boundary() -> None:
    """Logging lives only in the two audited files — never spread into the core."""
    users = {
        path.name
        for path in _source_files()
        if any(token in path.read_text(encoding="utf-8") for token in LOGGING_TOKENS)
    }
    assert users <= LOG_ALLOWED, f"logging leaked into non-boundary modules: {users - LOG_ALLOWED}"
