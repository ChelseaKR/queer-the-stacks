"""Privacy guardrail — no telemetry, and network egress confined (merge-blocking).

Reading data is sensitive (it can out a reader), so "reading data never leaves
the instance" is the project's headline promise. This file enforces it in two
layers, because a source-text scan alone cannot.

**Layer 1 — a real import scan (lint-shaped).** :func:`network_imports` parses
each first-party module with :mod:`ast` and resolves every ``import`` /
``from ... import`` / ``import_module("...")`` against
:data:`NETWORK_MODULE_PREFIXES`. It catches the forms a substring list cannot:
``from requests import post``, ``from http import client``, ``import httpx``,
``import aiohttp``. The set of modules that can reach the network is asserted to
be *exactly* the two declared clients — no module is exempted by filename, and a
declared client that stopped importing a client library would fail the same
assertion rather than pass silently.

**Layer 2 — runtime measurement.** :func:`tests.netguard.no_network` traps the
socket primitives every Python HTTP client goes through, and the ingest, render,
and dashboard-route paths are executed inside it. They cannot make a connection
without failing the test. The two paths that *are* allowed to make requests are
then asserted positively, below ``requests.get`` via
:func:`tests.netguard.capture_requests`: exactly which URLs, carrying exactly
what, with redirects off — never exempted, always measured.

**What this file does NOT establish.** Stated plainly so the audit doc does not
overclaim on its behalf:

* It covers *first-party* modules under ``app/``, ``ingest/``, ``recommender/``.
  A third-party dependency that fetches on its own behalf is out of scope; so is
  anything the deployment (uvicorn, a reverse proxy, the container) does.
* Layer 1 resolves module names statically. A dynamic import built from a
  computed string (``import_module(name)``) is invisible to it — which is why
  layer 2 exists, and why ``subprocess`` is on the denylist too.
* Layer 2 proves the absence of egress *only for the code paths it executes*. A
  path no test drives is unproven, not proven safe.
* Neither layer says anything about what the *user* does with rendered output
  (share cards are composed locally and copied by hand; nothing posts them).
"""

from __future__ import annotations

import ast
import inspect
import time
from pathlib import Path
from typing import Optional

import app
import ingest
import pytest
import recommender
from ingest.kosync import KosyncClient, SyncNotAllowed
from recommender.catalog_pool import fetch_catalog_pool
from recommender.catalogs import ALLOWED_HOSTS, BookwyrmClient, OpenLibraryClient, SourceNotAllowed

from tests.netguard import EgressAttempted, capture_requests, no_network

REPO_ROOT = Path(__file__).resolve().parent.parent

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

#: Module prefixes that can carry data off this machine. Deliberately broad and
#: fail-closed: ``asyncio`` is listed whole because its connection APIs cannot be
#: separated from the rest of it by import name, and ``subprocess`` because
#: shelling out to ``curl`` is egress too. Adding one of these to a module is a
#: reviewable act, not an accident.
NETWORK_MODULE_PREFIXES: frozenset[str] = frozenset(
    {
        "aiohttp",
        "asyncio",
        "boto3",
        "botocore",
        "ftplib",
        "grpc",
        "http.client",
        "http.server",
        "httplib2",
        "httpx",
        "imaplib",
        "poplib",
        "pycurl",
        "requests",
        "smtplib",
        "socket",
        "socketserver",
        "subprocess",
        "urllib",
        "urllib3",
        "webbrowser",
        "websocket",
        "websockets",
        "xmlrpc",
    }
)

#: Members of a denied namespace that open nothing. Checked longest-prefix-first,
#: so ``urllib.parse.quote`` is allowed while ``urllib.request.urlopen`` is not.
NETWORK_MODULE_EXCEPTIONS: frozenset[str] = frozenset({"urllib.parse", "urllib.error"})

#: Telemetry/analytics SDK module prefixes — none may be imported anywhere.
TELEMETRY_MODULE_PREFIXES: frozenset[str] = frozenset(
    {
        "amplitude",
        "analytics",
        "datadog",
        "ddtrace",
        "mixpanel",
        "newrelic",
        "opentelemetry",
        "posthog",
        "segment",
        "sentry_sdk",
        "statsd",
    }
)

#: The only first-party modules permitted to reach the network, and why. This is
#: an equality assertion, not an exemption: these two are held to the *stronger*
#: request-level checks at the bottom of this file.
DECLARED_NETWORK_CLIENTS: dict[str, str] = {
    "ingest/kosync.py": "KOReader sync: the user's own progress, to the user's own server",
    "recommender/catalogs.py": "catalog client: predeclared public subjects and list URLs only",
}


def _source_files() -> list[Path]:
    roots = [Path(pkg.__file__).parent for pkg in (ingest, recommender, app)]
    return sorted(p for root in roots for p in root.rglob("*.py"))


def _relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def _module_prefixes(name: str) -> list[str]:
    """``a.b.c`` -> ``['a.b.c', 'a.b', 'a']`` (longest first)."""
    parts = name.split(".")
    return [".".join(parts[: len(parts) - i]) for i in range(len(parts))]


def _classify(name: str, denied: frozenset[str], exceptions: frozenset[str]) -> bool:
    """True if ``name`` resolves to a denied namespace, most-specific rule wins."""
    for prefix in _module_prefixes(name):
        if prefix in exceptions:
            return False
        if prefix in denied:
            return True
    return False


def imported_modules(source: str) -> set[str]:
    """Every module name a source file can pull in, resolved statically.

    Covers ``import x.y``, ``from x.y import z`` (recording ``x.y`` and
    ``x.y.z``, since the imported name may itself be a submodule), and a literal
    ``importlib.import_module("x")`` / ``__import__("x")``. Relative imports are
    first-party and skipped.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call):
            func = node.func
            called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if called in {"__import__", "import_module"} and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    found.add(first.value)
    return found


def network_imports(source: str) -> set[str]:
    """The imports in ``source`` that can open an outbound connection."""
    return {
        name
        for name in imported_modules(source)
        if _classify(name, NETWORK_MODULE_PREFIXES, NETWORK_MODULE_EXCEPTIONS)
    }


def telemetry_imports(source: str) -> set[str]:
    """The imports in ``source`` that belong to an analytics/telemetry SDK."""
    return {
        name
        for name in imported_modules(source)
        if _classify(name, TELEMETRY_MODULE_PREFIXES, frozenset())
    }


# --- Layer 1: the import scan ------------------------------------------------


def test_core_references_no_telemetry_sdk_by_name() -> None:
    """Text scan: not even a mention of an analytics SDK in the core."""
    for path in _source_files():
        text = path.read_text(encoding="utf-8").lower()
        for token in TELEMETRY_TOKENS:
            assert token not in text, f"{_relative(path)} references telemetry: {token}"


def test_no_module_imports_a_telemetry_sdk() -> None:
    """Import scan: no analytics SDK is reachable from any first-party module."""
    offenders = {
        _relative(path): sorted(hits)
        for path in _source_files()
        if (hits := telemetry_imports(path.read_text(encoding="utf-8")))
    }
    assert offenders == {}, f"telemetry SDK imported: {offenders}"


def test_network_capable_modules_are_exactly_the_declared_clients() -> None:
    """The set of modules that *can* reach the network is asserted, not exempted.

    Equality in both directions. A new module importing an HTTP client fails
    here; so does a declared client that quietly stopped being one, because then
    the request-level assertions below would be guarding nothing.
    """
    networked = {
        _relative(path): sorted(hits)
        for path in _source_files()
        if (hits := network_imports(path.read_text(encoding="utf-8")))
    }
    assert set(networked) == set(DECLARED_NETWORK_CLIENTS), (
        "the set of network-capable modules changed; every entry needs a "
        f"documented reason in DECLARED_NETWORK_CLIENTS. found={networked}"
    )


@pytest.mark.parametrize(
    "snippet",
    [
        "import requests",
        "from requests import post",
        "import httpx",
        "import aiohttp",
        "from http import client",
        "import http.client",
        "from urllib.request import urlopen",
        "import urllib.request",
        "import socket",
        "import subprocess",
        "import asyncio",
        "from importlib import import_module\nc = import_module('httpx')",
        "m = __import__('requests')",
    ],
)
def test_import_scan_detects_every_egress_form(snippet: str) -> None:
    """The scanner is measured against the forms that must not slip past it.

    The previous guardrail was a four-token substring list; ``import httpx``,
    ``from requests import post``, ``from http import client`` and
    ``import aiohttp`` all went through it while ``httpx`` sat in the dev
    dependency set, importable. Each of those is a case below.
    """
    assert network_imports(snippet), f"import scan missed an egress form: {snippet!r}"


@pytest.mark.parametrize(
    "snippet",
    [
        "from urllib.parse import urlparse, quote",
        "import urllib.parse",
        "from importlib.metadata import version",
        "import sqlite3",
        "import json",
    ],
)
def test_import_scan_does_not_flag_offline_stdlib(snippet: str) -> None:
    """The scan must stay usable: no false positive on the offline stdlib."""
    assert network_imports(snippet) == set(), f"import scan false-positived on {snippet!r}"


# --- Layer 2: runtime measurement, reading paths ------------------------------


def _demo_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STACKS_DEMO", "1")
    monkeypatch.setenv("STACKS_DATA_DIR", str(tmp_path))
    for name in (
        "STACKS_CATALOG_OUTBOUND",
        "STACKS_OPENLIBRARY_SUBJECTS",
        "STACKS_BOOKWYRM_LISTS",
        "STACKS_KOSYNC_HOST",
        "STACKS_KOSYNC_USER",
        "STACKS_KOSYNC_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def test_ingest_and_render_open_no_socket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole local pipeline runs with the network trapped: refresh, then render.

    This is the measurement behind "reading data never leaves it" for the path a
    reader actually runs. Catalog egress is off (the default), so nothing here
    has any business opening a connection.
    """
    from app.view import render_view, view_from_store
    from ingest.config import load_config
    from ingest.refresh import doctor, refresh
    from ingest.store import Store

    _demo_env(tmp_path, monkeypatch)

    with no_network() as attempts:
        config = load_config()
        store = Store(config.store_path)
        try:
            refresh(config, store, now=int(time.time()))
            doctor(config, store)
            html = render_view(view_from_store(store, user="demo", demo_mode=True))
        finally:
            store.close()

    assert attempts == [], f"the local pipeline attempted egress: {attempts}"
    assert "Queer the Stacks" in html


def test_every_dashboard_route_opens_no_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Serving any route — authenticated or not — opens no connection."""
    pytest.importorskip("fastapi")
    from app.server import create_app
    from fastapi.testclient import TestClient

    from tests.conftest import seed_store_from_env

    _demo_env(tmp_path, monkeypatch)
    seed_store_from_env()
    client = TestClient(create_app(), base_url="https://testserver")
    auth = {"Authorization": "Bearer demo-token"}

    with no_network() as attempts:
        for route in create_app().routes:
            path = getattr(route, "path", "")
            if not path or "{" in path:
                continue
            client.get(path, headers=auth)
            client.get(path)  # and unauthenticated

    assert attempts == [], f"serving a route attempted egress: {attempts}"


def test_catalog_refresh_with_egress_off_opens_no_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Configured sources with outbound mode off must still open nothing.

    Fail-closed consent, asserted at the socket rather than inferred from the
    absence of a client call.
    """
    from ingest.config import load_config

    _demo_env(tmp_path, monkeypatch)
    monkeypatch.setenv("STACKS_OPENLIBRARY_SUBJECTS", "speculative_fiction")
    monkeypatch.setenv("STACKS_BOOKWYRM_LISTS", "https://bookwyrm.social/list/7")

    config = load_config()
    assert config.catalog_egress_enabled is False

    with no_network() as attempts:
        result = fetch_catalog_pool(config)

    assert attempts == [], f"catalog refresh attempted egress with outbound off: {attempts}"
    assert result.attempted == 0


def test_egress_trap_itself_detects_a_real_connection() -> None:
    """The guard is proved to fire, so a green run above means something.

    Without this, every ``attempts == []`` assertion above would also pass if
    :func:`no_network` had quietly stopped patching anything.
    """
    import socket as socket_module

    with no_network() as attempts, pytest.raises(EgressAttempted):
        socket_module.create_connection(("example.invalid", 443), timeout=1)
    assert attempts, "the egress trap recorded nothing for a real connection attempt"


# --- Layer 2: the two allowed paths, asserted rather than exempted ------------


def test_fetch_catalog_pool_cannot_receive_reading_state() -> None:
    """The catalog refresh entry point takes configuration and nothing else.

    Structural, not stylistic: if no reading state can be passed in, no reading
    state can reach a URL. Adding a parameter here is the change that would make
    the URL assertions below insufficient.
    """
    assert list(inspect.signature(fetch_catalog_pool).parameters) == ["config"]


def test_catalog_requests_carry_only_predeclared_public_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With egress on, assert what actually goes out — URL, headers, body.

    The old check for the substring ``.post(`` was orthogonal to the property:
    a GET carries its payload in the URL. This asserts the exact outbound URL
    set, and that nothing derived from the library appears anywhere in the
    request.
    """
    from ingest.config import load_config
    from ingest.demo import demo_reading_states

    _demo_env(tmp_path, monkeypatch)
    monkeypatch.setenv("STACKS_CATALOG_OUTBOUND", "public-metadata")
    monkeypatch.setenv("STACKS_OPENLIBRARY_SUBJECTS", "speculative_fiction")
    monkeypatch.setenv("STACKS_BOOKWYRM_LISTS", "https://bookwyrm.social/list/7")

    config = load_config()
    assert config.catalog_egress_enabled is True

    with capture_requests(body='{"works": [], "books": []}') as sent, no_network() as attempts:
        fetch_catalog_pool(config)

    assert attempts == [], f"a request escaped the capture and hit the socket: {attempts}"
    assert [r.url for r in sent] == [
        "https://openlibrary.org/subjects/speculative_fiction.json?limit=50",
        "https://bookwyrm.social/list/7",
    ]

    for request in sent:
        assert request.method == "GET"
        assert request.body is None, "a catalog request carried a body"
        assert request.allow_redirects is False
        assert request.url.split("/")[2] in ALLOWED_HOSTS

    # Nothing the reader has read may appear in any part of any request.
    outbound = " ".join(r.as_text() for r in sent)
    reading_data: set[str] = set()
    for state in demo_reading_states(tmp_path / "demo"):
        reading_data.add(state.book.title.lower())
        reading_data.update(name.lower() for name in state.book.author_names)
    assert reading_data, "the fixture library is empty; this assertion would be vacuous"
    leaked = sorted(item for item in reading_data if item in outbound)
    assert leaked == [], f"reading data reached a catalog request: {leaked}"


@pytest.mark.parametrize("status_code", [301, 302, 307, 308])
def test_catalog_client_refuses_a_redirect_instead_of_following_it(status_code: int) -> None:
    """A redirect is refused at the first hop; no second request is made."""
    with capture_requests(status_code=status_code) as sent:
        with pytest.raises(SourceNotAllowed, match="redirects are disabled"):
            OpenLibraryClient().subject("speculative_fiction")
        with pytest.raises(SourceNotAllowed, match="redirects are disabled"):
            BookwyrmClient().fetch_list("https://bookwyrm.social/list/7")
    assert len(sent) == 2, f"a redirect produced a follow-on request: {[r.url for r in sent]}"


def test_kosync_request_carries_only_the_document_key_and_the_users_own_credentials() -> None:
    """The sync client sends the reader's own key to the reader's own host.

    The document key is a KOReader partial-MD5 of the file, and it is the *only*
    reading-derived value in the request: no title, no author, no descriptor, no
    progress history. Asserted against a whole-request string so a future header
    or query parameter cannot smuggle one in unnoticed.
    """
    document = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
    with capture_requests(body=f'{{"document": "{document}", "percentage": 0.42}}') as sent:
        client = KosyncClient(
            "reader",
            "deadbeefdeadbeefdeadbeefdeadbeef",
            host="https://sync.example.org",
        )
        client.progress_for(document)

    assert len(sent) == 1
    request = sent[0]
    assert request.method == "GET"
    assert request.body is None
    assert request.allow_redirects is False
    assert request.url == f"https://sync.example.org/syncs/progress/{document}"

    permitted = {document, "reader", "deadbeefdeadbeefdeadbeefdeadbeef"}
    remainder = request.as_text()
    for value in permitted:
        remainder = remainder.replace(value.lower(), " ")
    for forbidden in ("title", "author", "percentage", "progress=", "history"):
        assert forbidden not in remainder, f"kosync request carried {forbidden!r}"


@pytest.mark.parametrize("status_code", [301, 302, 307, 308])
def test_kosync_client_does_not_follow_a_redirect_with_the_auth_key(status_code: int) -> None:
    """A redirect must not carry ``x-auth-key`` and the document key to a new host.

    ``requests`` strips ``Authorization`` when a redirect changes host, but not
    arbitrary headers — so a compromised or hostile sync endpoint could have
    bounced the reader's credential and document key anywhere. Refused at the
    first hop instead.
    """
    with capture_requests(status_code=status_code) as sent:
        client = KosyncClient("reader", "deadbeefdeadbeefdeadbeefdeadbeef")
        with pytest.raises(SyncNotAllowed, match="redirects are disabled"):
            client.progress_for("a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4")
    assert len(sent) == 1, f"a redirect produced a follow-on request: {[r.url for r in sent]}"


@pytest.mark.parametrize(
    "document",
    ["../../../etc/passwd", "a b/c?x=1", "https://evil.example/steal"],
)
def test_kosync_document_key_cannot_reshape_the_url(document: str) -> None:
    """A document key is percent-encoded into one path segment, never a new path."""
    prefix = "https://sync.koreader.rocks/syncs/progress/"
    with capture_requests(body='{"document": ""}') as sent:
        KosyncClient("reader", "deadbeefdeadbeefdeadbeefdeadbeef").progress_for(document)

    assert len(sent) == 1
    url = sent[0].url
    assert url.startswith(prefix), url
    tail = url[len(prefix) :]
    assert "/" not in tail and "?" not in tail and "#" not in tail, url


def test_kosync_progress_is_not_fetched_when_unconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No kosync configuration means no kosync request, asserted at the socket."""
    from ingest.config import load_config
    from ingest.refresh import refresh
    from ingest.store import Store

    _demo_env(tmp_path, monkeypatch)
    config = load_config()
    assert config.kosync_configured is False

    with no_network() as attempts:
        store = Store(config.store_path)
        try:
            refresh(config, store, now=int(time.time()))
        finally:
            store.close()
    assert attempts == []


def test_reading_privacy_audit_cites_the_checks_that_exist() -> None:
    """The audit doc must name real tests — a citation to a deleted test is worse
    than none, because a reader stops at the name."""
    audit = (REPO_ROOT / "docs" / "audits" / "reading-privacy.md").read_text(encoding="utf-8")
    here = Path(__file__).read_text(encoding="utf-8")
    cited: set[str] = set()
    for line in audit.splitlines():
        if "tests/test_no_egress.py::" in line:
            for chunk in line.split("`"):
                if chunk.startswith("tests/test_no_egress.py::"):
                    cited.add(chunk.split("::", 1)[1])
    assert cited, "the privacy audit no longer cites this guardrail at all"
    missing: Optional[list[str]] = sorted(name for name in cited if f"def {name}(" not in here)
    assert missing == [], f"the privacy audit cites tests that do not exist: {missing}"
