"""Observability contract — structured JSON request logs + /livez /readyz.

Verifies (per OBSERVABILITY-STANDARD §3/§6) that:
  * ``/livez`` is a dependency-free 200 liveness probe,
  * ``/readyz`` reflects the app-state store's health (200 ready / 503 fail-closed),
  * each request log line is valid JSON with exactly the expected fields,
  * the log stream carries **no** reading content, search terms, or auth tokens,
  * logs go to **stdout only** (local-only / no-egress posture reinforced).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from app.logging_config import (
    LOGGER_NAME,
    JsonLogFormatter,
    RequestLoggingMiddleware,
    configure_logging,
    get_logger,
)


def _make_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, populated: bool = False):
    """A TestClient in demo mode with a throwaway data dir (never touches data/).

    Data routes 503 until the store is refreshed (FIX-14) — pass
    ``populated=True`` for tests that need a working dashboard/browse route.
    """
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("STACKS_DEMO", "1")
    monkeypatch.setenv("STACKS_DATA_DIR", str(tmp_path))
    if populated:
        from tests.conftest import seed_store_from_env

        seed_store_from_env()
    from app.server import create_app

    return TestClient(create_app())


class _CaptureHandler(logging.Handler):
    """Collect emitted records so we can assert on the exact log line shape."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


# --- health & readiness ------------------------------------------------------


def test_livez_is_ok_and_unauthenticated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(tmp_path, monkeypatch)
    resp = client.get("/livez")  # no Authorization header
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_reports_ready_when_store_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _make_client(tmp_path, monkeypatch)
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"]["store"] == "ok"


def test_readyz_fails_closed_when_dependency_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("STACKS_DEMO", "1")
    monkeypatch.setenv("STACKS_DATA_DIR", str(tmp_path))
    from app import server

    def _boom() -> dict[str, str]:
        raise RuntimeError("store file at /secret/path/app-state.sqlite is corrupt")

    monkeypatch.setattr(server, "readiness_probe", _boom)
    client = TestClient(server.create_app())

    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json() == {"status": "unavailable"}
    # Fail-closed response leaks no internal detail: no exception text, no path.
    assert "corrupt" not in resp.text
    assert "/secret/path" not in resp.text
    assert str(tmp_path) not in resp.text


# --- structured JSON logging + PII safety ------------------------------------


def test_request_emits_valid_json_log_without_pii(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = _CaptureHandler()
    logger = configure_logging()
    logger.addHandler(capture)
    try:
        client = _make_client(tmp_path, monkeypatch, populated=True)
        # A request whose query string carries would-be-sensitive reading data,
        # plus an auth token in the header — none of it may reach the log.
        resp = client.get(
            "/browse",
            params={"q": "A Very Private Reading Title", "author": "Some Secret Author"},
            headers={"Authorization": "Bearer demo-token"},
        )
        assert resp.status_code == 200
    finally:
        logger.removeHandler(capture)

    assert capture.records, "the middleware emitted no log record"
    line = JsonLogFormatter().format(capture.records[-1])
    obj = json.loads(line)  # one valid JSON object per line

    expected_fields = {"ts", "level", "msg", "request_id", "method", "path", "status", "latency_ms"}
    assert set(obj) == expected_fields
    assert obj["level"] == "info"
    assert obj["msg"] == "http_request"
    assert obj["method"] == "GET"
    assert obj["path"] == "/browse"  # path only — never the query string
    assert obj["status"] == 200
    assert isinstance(obj["latency_ms"], (int, float))
    assert isinstance(obj["request_id"], str) and obj["request_id"]

    # PRIVACY / no-egress: reading terms and the auth token never appear.
    assert "A Very Private Reading Title" not in line
    assert "Some Secret Author" not in line
    assert "demo-token" not in line
    assert "?" not in line and "q=" not in line  # no query string anywhere in the line


def test_json_formatter_serializes_only_the_allowlisted_fields() -> None:
    record = logging.LogRecord(
        name=LOGGER_NAME,
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="readyz_unavailable",
        args=(),
        exc_info=None,
    )
    record.error_type = "RuntimeError"
    record.request_id = "abc123"
    record.reading_title = "should never be logged"  # not on the allowlist

    obj = json.loads(JsonLogFormatter().format(record))
    assert obj["level"] == "warning"
    assert obj["msg"] == "readyz_unavailable"
    assert obj["error_type"] == "RuntimeError"
    assert obj["request_id"] == "abc123"
    assert "reading_title" not in obj
    assert "should never be logged" not in json.dumps(obj)


def test_health_probes_are_excluded_from_access_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = _CaptureHandler()
    logger = configure_logging()
    logger.addHandler(capture)
    try:
        client = _make_client(tmp_path, monkeypatch)
        client.get("/livez")
        client.get("/readyz")
        client.get("/healthz")
    finally:
        logger.removeHandler(capture)

    logged_paths = [getattr(rec, "path", None) for rec in capture.records]
    assert "/livez" not in logged_paths
    assert "/readyz" not in logged_paths
    assert "/healthz" not in logged_paths


def test_configure_logging_is_idempotent() -> None:
    logger = configure_logging()
    before = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
    logger2 = configure_logging()
    after = [h for h in logger2.handlers if isinstance(h, logging.StreamHandler)]
    assert logger is logger2
    assert len(before) == len(after)  # no duplicate stdout handler added


def test_request_logger_writes_to_a_stream_and_never_off_host() -> None:
    """Local-only/no-egress: logs go to a stdout stream, never to a network sink."""
    from logging.handlers import DatagramHandler, HTTPHandler, SMTPHandler, SocketHandler

    logger = configure_logging()
    stream_handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
    assert stream_handlers, "expected a stdout stream handler"
    # Its stream is a stdout-like text stream (not a socket/file to a remote).
    assert all(hasattr(h.stream, "write") for h in stream_handlers)
    # No handler can ship a log record off the host.
    egress_handlers = (SocketHandler, DatagramHandler, HTTPHandler, SMTPHandler)
    assert not any(isinstance(h, egress_handlers) for h in logger.handlers)
    assert logger.propagate is False


def test_observability_module_opens_no_network() -> None:
    """The request-logging module reaches no network (reinforces no-egress)."""
    import app.logging_config as lc

    src = Path(lc.__file__).read_text(encoding="utf-8")
    for token in ("import requests", "urllib.request", "http.client", "import socket", "httpx"):
        assert token not in src, f"observability module reaches network: {token}"
    assert RequestLoggingMiddleware is not None  # imported symbol is used
    assert get_logger().name == LOGGER_NAME
