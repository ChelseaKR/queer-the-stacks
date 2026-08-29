"""Defense-in-depth response headers — merge-blocking (FIX-05).

Verifies that every route (gated and ungated, success and failure) carries the
full security-header set, that the served CSP covers exactly the inline
scripts and styles the app actually serves, and that external citation links
carry safe ``rel`` attributes.

**Both of the last two used to be unfalsifiable, in different ways.**

The CSP drift test recomputed ``sha256(_STYLE)`` in the test and compared it to
``app/security_headers.py``'s ``sha256(_STYLE)``. Same pure function, same
constant, so it matched by construction: ``f(x) == f(x)``. Editing an inline
block changed both sides identically, and the test never read a rendered page
at all — only the header. What it could not catch is the failure that matters:
a *sixth* inline block added to a rendered document with no hash in the CSP,
which every real browser blocks while this test stays green.

The check below reads the served documents instead, extracts every inline
``<script>`` and ``<style>`` body, and asserts set equality against the hashes
in the CSP. Equality in both directions: an unhashed block fails, and so does a
hash left in the CSP for a block nothing serves any more.

The ``rel`` test asserted ``'href="http' in html`` and
``'rel="noopener noreferrer external"' in html`` — two independent substring
searches over one document. They proved that at least one external link exists
and that the rel string appears somewhere, never that they were the same
anchor. A second external-link emitter with no ``rel`` was invisible. Every
external anchor is now checked individually.
"""

from __future__ import annotations

import base64
import hashlib
import re
from html.parser import HTMLParser
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


#: Every HTML document the app serves to a person. `/browse` renders the
#: dashboard template, and is included anyway so a future divergence is caught.
SERVED_HTML_ROUTES: tuple[str, ...] = ("/", "/browse", "/login", "/share")


class _InlineBlocks(HTMLParser):
    """Collect the raw body of every inline ``<script>`` and ``<style>``.

    ``convert_charrefs=False`` and the two ``handle_*ref`` hooks keep the text
    byte-identical to what the browser hashes: a CSP hash is taken over the
    element's literal content, so any unescaping here would silently produce a
    different digest than the browser computes.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.scripts: list[str] = []
        self.styles: list[str] = []
        self._open: str = ""
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._open = tag
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == self._open:
            body = "".join(self._buf)
            (self.scripts if tag == "script" else self.styles).append(body)
            self._open = ""

    def handle_data(self, data: str) -> None:
        if self._open:
            self._buf.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._open:
            self._buf.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._open:
            self._buf.append(f"&#{name};")


def _served_inline_hashes(client: object) -> tuple[set[str], set[str]]:
    """(script hashes, style hashes) over every HTML document the app serves."""
    auth = {"Authorization": "Bearer demo-token"}
    scripts: set[str] = set()
    styles: set[str] = set()
    for path in SERVED_HTML_ROUTES:
        response = client.get(path, headers=auth)  # type: ignore[attr-defined] # TestClient
        assert response.status_code == 200, f"{path} answered {response.status_code}"
        parser = _InlineBlocks()
        parser.feed(response.text)
        scripts |= {_sha256_b64(body) for body in parser.scripts}
        styles |= {_sha256_b64(body) for body in parser.styles}
    return scripts, styles


def _csp_hashes(csp: str, directive: str) -> set[str]:
    """The ``'sha256-...'`` digests listed under one CSP directive."""
    for chunk in csp.split(";"):
        chunk = chunk.strip()
        if chunk.startswith(f"{directive} "):
            return set(re.findall(r"'sha256-([A-Za-z0-9+/=]+)'", chunk))
    return set()


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


def test_csp_covers_exactly_the_inline_blocks_the_app_serves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CSP's hash set equals the hash set of what is actually rendered.

    The previous version of this test recomputed the hashes from the same
    constants ``app/security_headers.py`` hashes, with the same function, and
    asserted they matched. They always did: ``f(x) == f(x)``. It never opened a
    rendered document, so a new inline block with no hash in the CSP — blocked
    by every browser, invisible here — could not fail it.

    Reading the served documents makes both directions real. Add an inline
    block without a hash and the left side grows; leave a stale hash for a
    block nothing renders and the right side does.
    """
    client = _make_client(tmp_path, monkeypatch)
    served_scripts, served_styles = _served_inline_hashes(client)
    csp = client.get("/healthz").headers["Content-Security-Policy"]

    assert served_scripts, "no inline <script> found in any served document"
    assert served_styles, "no inline <style> found in any served document"

    assert served_scripts == _csp_hashes(csp, "script-src"), (
        "the CSP's script-src hashes and the inline scripts actually served "
        "have drifted apart. Unhashed served scripts: "
        f"{sorted(served_scripts - _csp_hashes(csp, 'script-src'))}; "
        f"hashes for nothing served: {sorted(_csp_hashes(csp, 'script-src') - served_scripts)}"
    )
    assert served_styles == _csp_hashes(csp, "style-src"), (
        "the CSP's style-src hashes and the inline styles actually served have "
        "drifted apart. Unhashed served styles: "
        f"{sorted(served_styles - _csp_hashes(csp, 'style-src'))}; "
        f"hashes for nothing served: {sorted(_csp_hashes(csp, 'style-src') - served_styles)}"
    )


def test_inline_block_extractor_reads_what_a_browser_would_hash() -> None:
    """The extractor is measured, so a green equality above means something.

    An extractor that silently returned nothing would make the equality above
    compare two empty sets on a CSP with no hashes, and an extractor that
    unescaped entities would hash different bytes than the browser does.
    """
    parser = _InlineBlocks()
    parser.feed(
        "<html><head><style>body { color: CanvasText; }</style></head>"
        "<body><p>not script</p><script>if (a &amp;&amp; b) { x(); }</script>"
        "<style>a &gt; b { color: red; }</style></body></html>"
    )
    assert parser.scripts == ["if (a &amp;&amp; b) { x(); }"]
    assert parser.styles == ["body { color: CanvasText; }", "a &gt; b { color: red; }"]


def test_csp_denies_by_default_and_scopes_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _make_client(tmp_path, monkeypatch)
    csp = client.get("/healthz").headers["Content-Security-Policy"]
    assert "default-src 'none'" in csp
    assert "img-src 'self' data:" in csp
    assert "base-uri 'none'" in csp
    assert "form-action 'self'" in csp
    assert "form-action https:" not in csp


def test_login_form_is_allowed_only_to_submit_same_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _make_client(tmp_path, monkeypatch)
    response = client.get("/login")
    assert response.status_code == 200
    assert '<form method="post" action="/login">' in response.text
    assert "form-action 'self'" in response.headers["Content-Security-Policy"]


def test_login_style_has_explicit_contrast_and_reflow_guards() -> None:
    from app.security_headers import LOGIN_STYLE

    assert "* { box-sizing: border-box; }" in LOGIN_STYLE
    assert "color: CanvasText" in LOGIN_STYLE
    assert "background-color: Canvas" in LOGIN_STYLE


# --- external citation links carry safe rel attributes -----------------------


#: Every ``<a ...>`` open tag, captured whole so its attributes can be read.
_ANCHOR_TAG = re.compile(r"<a\s[^>]*>", re.IGNORECASE)
_HREF = re.compile(r'href="([^"]*)"', re.IGNORECASE)
_REL = re.compile(r'rel="([^"]*)"', re.IGNORECASE)

#: What an external anchor must carry: ``noreferrer`` stops the private
#: dashboard's URL reaching a catalog host in a ``Referer``, and ``noopener``
#: stops the opened page reaching back through ``window.opener``.
REQUIRED_EXTERNAL_REL = frozenset({"noopener", "noreferrer", "external"})


@pytest.mark.parametrize("path", SERVED_HTML_ROUTES)
def test_every_external_link_carries_safe_rel(
    path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every external anchor, not merely one of them, on every served document.

    The previous check was two independent substring searches over the
    dashboard: ``'href="http' in html`` and
    ``'rel="noopener noreferrer external"' in html``. That proves an external
    link exists somewhere and the rel string exists somewhere, never that they
    belong to the same anchor. Today ``_EXTERNAL_REL`` is applied at exactly one
    site in ``app/render.py``, which is what made it look green; a second
    emitter without it would have leaked a ``Referer`` from an authenticated,
    privacy-sensitive page with this test still passing.
    """
    client = _make_client(tmp_path, monkeypatch)
    response = client.get(path, headers={"Authorization": "Bearer demo-token"})
    assert response.status_code == 200

    external = [
        tag
        for tag in _ANCHOR_TAG.findall(response.text)
        if (m := _HREF.search(tag)) and m.group(1).lower().startswith(("http://", "https://"))
    ]
    for tag in external:
        rel = _REL.search(tag)
        assert rel is not None, f"external anchor on {path} carries no rel: {tag}"
        assert set(rel.group(1).split()) >= REQUIRED_EXTERNAL_REL, (
            f"external anchor on {path} is missing "
            f"{sorted(REQUIRED_EXTERNAL_REL - set(rel.group(1).split()))}: {tag}"
        )


def test_the_dashboard_actually_renders_an_external_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-vacuity: the loop above must have something to iterate over.

    Kept separate from the per-anchor check so that a demo dataset which stops
    producing citations fails here, naming the real cause, instead of turning
    the parametrized test into a silent no-op on every page.
    """
    client = _make_client(tmp_path, monkeypatch)
    html = client.get("/", headers={"Authorization": "Bearer demo-token"}).text
    external = [
        tag
        for tag in _ANCHOR_TAG.findall(html)
        if (m := _HREF.search(tag)) and m.group(1).lower().startswith(("http://", "https://"))
    ]
    assert external, "the dashboard rendered no external citation link to check"
