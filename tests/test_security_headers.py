"""Defense-in-depth response headers — merge-blocking (FIX-05).

Verifies that every route (gated and ungated, success and failure) carries the
full security-header set, that the served CSP's inline-script/style hashes are
derived from the actual source (a drift test fails CI if an inline
script/style edit forgets to keep the CSP in sync), and that external citation
links carry safe ``rel`` attributes.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest


def _make_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A TestClient in demo mode with a throwaway data dir (never touches data/)."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("STACKS_DEMO", "1")
    monkeypatch.setenv("STACKS_DATA_DIR", str(tmp_path))
    from tests.conftest import seed_store_from_env

    seed_store_from_env()
    from app.server import create_app

    return TestClient(create_app())


def _sha256_b64(text: str) -> str:
    return base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii")


# --- header set on every route ------------------------------------------------


@pytest.mark.parametrize("path", ["/healthz", "/livez", "/readyz"])
def test_open_probe_routes_carry_the_full_header_set(
    path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _make_client(tmp_path, monkeypatch)
    resp = client.get(path)
    assert resp.status_code == 200
    assert "Content-Security-Policy" in resp.headers
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in resp.headers["Content-Security-Policy"]
    assert resp.headers["Cross-Origin-Opener-Policy"] == "same-origin"


@pytest.mark.parametrize("path", ["/", "/browse"])
def test_gated_routes_carry_the_full_header_set_when_authenticated(
    path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _make_client(tmp_path, monkeypatch)
    resp = client.get(path, headers={"Authorization": "Bearer demo-token"})
    assert resp.status_code == 200
    assert "Content-Security-Policy" in resp.headers
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in resp.headers["Content-Security-Policy"]
    assert resp.headers["Cross-Origin-Opener-Policy"] == "same-origin"


@pytest.mark.parametrize("path", ["/", "/browse"])
def test_headers_are_present_even_on_401_unauthenticated_responses(
    path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The middleware must not be bypassed by require_auth's early 401."""
    client = _make_client(tmp_path, monkeypatch)
    resp = client.get(path)  # no Authorization header
    assert resp.status_code == 401
    assert "Content-Security-Policy" in resp.headers
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Cross-Origin-Opener-Policy"] == "same-origin"


def test_x_frame_options_denies_framing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(tmp_path, monkeypatch)
    resp = client.get("/healthz")
    assert resp.headers.get("X-Frame-Options") == "DENY"


# --- CSP hash drift test: recompute from the actual inline source ------------


def test_csp_hashes_are_derived_from_the_served_inline_script_and_style_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any edit to an inline <script>/<style> without matching hashes fails here.

    Recomputes sha256 hashes directly from the imported source constants
    (independent of app.security_headers' own computation) and asserts they
    show up in the CSP header actually served on a live route.
    """
    from app.render import _FILTER_JS, _STYLE
    from app.share import _COPY_JS, _SHARE_STYLE

    filter_js_inner = _FILTER_JS.removeprefix("<script>").removesuffix("</script>")
    copy_js_inner = _COPY_JS.removeprefix("<script>").removesuffix("</script>")

    expected_hashes = {
        f"'sha256-{_sha256_b64(filter_js_inner)}'",
        f"'sha256-{_sha256_b64(copy_js_inner)}'",
        f"'sha256-{_sha256_b64(_STYLE)}'",
        f"'sha256-{_sha256_b64(_SHARE_STYLE)}'",
    }

    client = _make_client(tmp_path, monkeypatch)
    resp = client.get("/healthz")
    csp = resp.headers["Content-Security-Policy"]

    for expected in expected_hashes:
        assert expected in csp, f"CSP missing hash for current inline source: {expected}"


def test_csp_denies_by_default_and_scopes_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _make_client(tmp_path, monkeypatch)
    csp = client.get("/healthz").headers["Content-Security-Policy"]
    assert "default-src 'none'" in csp
    assert "img-src 'self' data:" in csp
    assert "base-uri 'none'" in csp
    assert "form-action 'none'" in csp


# --- external citation links carry safe rel attributes -----------------------


def test_dashboard_external_citation_links_carry_safe_rel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _make_client(tmp_path, monkeypatch)
    resp = client.get("/", headers={"Authorization": "Bearer demo-token"})
    assert resp.status_code == 200
    html = resp.text
    assert 'href="http' in html, "expected at least one external citation link in demo data"
    assert 'rel="noopener noreferrer external"' in html
