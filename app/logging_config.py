"""Structured JSON request logging for the self-hosted FastAPI service surface.

This is the **only** logging in the app, and it is deliberately confined to the
web request boundary (this module + the middleware wiring in :mod:`app.server`).
Reading content — titles, authors, progress values, search terms — never enters
a log line: the middleware records only the request *method*, the *path* (never
the query string, which on ``/browse`` can carry a search term or an author
name), the response *status*, the *latency*, and a per-request id. It never logs
request headers (so no ``Authorization`` bearer token), request bodies, or
response content.

The core (``ingest`` / ``recommender`` and the pure ``app`` view/render/stats
modules) stays log-free — see ``tests/test_log_safety.py`` — so sensitive
reading data has no path into the log stream at all.

Per OBSERVABILITY-STANDARD §0/§10 this is a Tier-C, local-only, no-egress repo:
OTel tracing/metrics/SLOs are out-of-scope (no network surface). Logs are written
to **stdout only** and never egress anywhere. The non-tiered PII-in-logs gate
(§3) is enforced here by keeping the serialized field set to a fixed allowlist.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from datetime import UTC, datetime
from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

#: The dedicated request logger; distinct from the root logger so the core can
#: never accidentally emit through it.
LOGGER_NAME: Final = "queer_the_stacks.request"

#: A fixed, non-sensitive event name for the per-request line. It carries no
#: user data — the structured fields (method/path/status/latency) do.
REQUEST_EVENT: Final = "http_request"

#: Health/probe paths are excluded from access logs (OBSERVABILITY-STANDARD §6:
#: probes are "excluded from access logs" — no auth middleware, no log noise).
_UNLOGGED_PATHS: Final = frozenset({"/livez", "/readyz", "/healthz"})


class JsonLogFormatter(logging.Formatter):
    """Render each log record as exactly one compact JSON object per line.

    Fields: ``ts`` (ISO-8601 UTC), ``level``, ``msg``, and any *allowlisted*
    structured fields attached via ``extra`` (``request_id``, ``method``,
    ``path``, ``status``, ``latency_ms``, ``error_type``). Only the allowlist is
    ever serialized, so a caller cannot widen the log surface by passing an
    unexpected ``extra`` key — a hard privacy stop for the PII-in-logs gate.
    """

    #: The complete set of structured fields permitted in a log line. Anything
    #: else on the record (including accidental PII) is dropped, not logged.
    _ALLOWED_EXTRA: Final = (
        "request_id",
        "method",
        "path",
        "status",
        "latency_ms",
        "error_type",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "msg": record.getMessage(),
        }
        for key in self._ALLOWED_EXTRA:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def get_logger() -> logging.Logger:
    """Return the dedicated request logger (does not configure handlers)."""
    return logging.getLogger(LOGGER_NAME)


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Attach a single JSON-to-stdout handler to the request logger (idempotent).

    Safe to call more than once (e.g. per ``create_app``): a duplicate stream
    handler is never added. Propagation to the root logger is disabled so lines
    are emitted exactly once and only in the JSON shape defined here.
    """
    logger = get_logger()
    logger.setLevel(level)
    logger.propagate = False
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonLogFormatter())
        logger.addHandler(handler)
    return logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Emit one structured JSON line per request (health/probe paths excluded)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path  # path only — the query string is never read
        if path in _UNLOGGED_PATHS:
            return await call_next(request)

        request_id = uuid.uuid4().hex
        start = time.perf_counter()
        status = 500  # assume failure until a response is produced
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            latency_ms = round((time.perf_counter() - start) * 1000, 3)
            get_logger().info(
                REQUEST_EVENT,
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": path,
                    "status": status,
                    "latency_ms": latency_ms,
                },
            )
