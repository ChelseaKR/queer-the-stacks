"""Privacy guardrail — no telemetry, and network egress confined (merge-blocking).

Reading data is sensitive (it can out a reader). These are source-level
guarantees: the core must not import an analytics SDK, and it must not open a
network connection anywhere except the two explicit, documented client paths —
the KOReader sync client (the user's own data, to the user's own server) and the
ethical-catalog client.
"""

from __future__ import annotations

from pathlib import Path

import app
import ingest
import recommender

TELEMETRY_TOKENS = (
    "mixpanel",
    "segment.analytics",
    "amplitude",
    "posthog",
    "sentry_sdk",
    "datadog",
    "google.analytics",
    "googleanalytics",
)

# Network may only be reached from these modules.
NETWORK_ALLOWED = {"kosync.py", "catalogs.py"}
NETWORK_TOKENS = ("import requests", "urllib.request", "http.client", "import socket")


def _source_files() -> list[Path]:
    roots = [Path(pkg.__file__).parent for pkg in (ingest, recommender, app)]
    return [p for root in roots for p in root.rglob("*.py")]


def test_core_imports_no_telemetry_sdk() -> None:
    for path in _source_files():
        text = path.read_text(encoding="utf-8").lower()
        for token in TELEMETRY_TOKENS:
            assert token not in text, f"{path.name} references telemetry: {token}"


def test_network_access_is_confined_to_clients() -> None:
    for path in _source_files():
        if path.name in NETWORK_ALLOWED:
            continue
        text = path.read_text(encoding="utf-8")
        for token in NETWORK_TOKENS:
            assert token not in text, f"{path.name} opens network outside a client: {token}"


def test_reading_history_is_never_sent_to_a_catalog() -> None:
    """The catalog client only GETs public metadata; it never posts reading data."""
    catalogs = (Path(recommender.__file__).parent / "catalogs.py").read_text(encoding="utf-8")
    assert "requests.post" not in catalogs
    assert ".post(" not in catalogs
