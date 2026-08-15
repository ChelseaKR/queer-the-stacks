"""Security guardrail — the dashboard is reachable only behind auth (merge-blocking).

The auth claim in ``docs/audits/reading-privacy.md`` is enforced here by
*enumerating the route table*, not by naming a couple of paths. Auth is applied
per route (``dependencies=[Depends(require_auth)]``) rather than app-wide, so
omitting it on a new route is a one-line mistake with no compile-time
consequence — the enumeration is what turns it into a failing build instead of a
later discovery.

:data:`PUBLIC_PATHS` is the whole point: every path served without credentials
is listed there with the reason it is safe, so adding one is a deliberate,
reviewable act. Anything not on that list must answer 401 to an anonymous
request, and the public ones are separately asserted to carry no reading content
and to name no private route.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import pytest
from app.auth import (
    SESSION_TTL_SECONDS,
    AuthNotConfigured,
    LoginLockoutTracker,
    check_credentials,
    expected_token,
    sign_session,
    verify_session,
)

#: Paths deliberately reachable without credentials, each with why it is safe.
#: Everything else must 401. Keep the reason: it is what makes an addition here
#: reviewable rather than routine.
PUBLIC_PATHS: dict[str, str] = {
    "/healthz": "liveness for a container/reverse proxy; returns only {'status': 'ok'}",
    "/livez": "liveness; no dependency calls, no reading content",
    "/readyz": "readiness; fail-closed status only, never a path or exception text",
    "/version": "installed package version only (REL-19), no internal detail",
    "/login": "the entry point by necessity; an empty form, no reading content",
    "/logout": "clears the session cookie and redirects to /login",
}

#: Every (path, method) the app registers. Pinned so that adding a route is a
#: deliberate change to this file too — the enumeration below already fails on an
#: ungated route, and this makes a *gated* addition visible in review as well.
EXPECTED_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("/healthz", "GET"),
        ("/livez", "GET"),
        ("/version", "GET"),
        ("/readyz", "GET"),
        ("/login", "GET"),
        ("/login", "POST"),
        ("/logout", "GET"),
        ("/", "GET"),
        ("/browse", "GET"),
        ("/opds", "GET"),
        ("/opds/to-read", "GET"),
        ("/opds/currently-reading", "GET"),
        ("/opds/series-next", "GET"),
        ("/opds/recommendations", "GET"),
        ("/share", "GET"),
        ("/share/card.svg", "GET"),
    }
)

#: Documentation surfaces FastAPI can mount by default. All three must be closed:
#: ``/openapi.json`` publishes the app's route inventory, its query-parameter
#: names, and the session cookie name to anyone who asks.
DOC_SURFACES: tuple[str, ...] = ("/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect")


def _registered_routes(app: object) -> set[tuple[str, str]]:
    """Every (path, method) the app serves, ignoring HEAD/OPTIONS bookkeeping."""
    found: set[tuple[str, str]] = set()
    for route in app.routes:  # type: ignore[attr-defined] # FastAPI/Starlette app
        path: Optional[str] = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or {"GET"}
        if not path:
            continue
        found.update((path, method) for method in methods if method not in {"HEAD", "OPTIONS"})
    return found


def test_demo_mode_uses_demo_token() -> None:
    env = {"STACKS_DEMO": "1"}
    assert expected_token(env) == "demo-token"
    assert check_credentials("demo-token", env) is True
    assert check_credentials("wrong", env) is False
    assert check_credentials(None, env) is False


def test_real_mode_requires_env_token() -> None:
    with pytest.raises(AuthNotConfigured):
        expected_token({})  # no demo, no token -> fail closed


def test_real_mode_token_from_env() -> None:
    env = {"STACKS_AUTH_TOKEN": "s3cr3t-token-value"}
    assert check_credentials("s3cr3t-token-value", env) is True
    assert check_credentials("nope", env) is False


def test_non_ascii_token_is_rejected_not_a_crash() -> None:
    """A latin-1/unicode bearer token must yield False (-> 401), never TypeError.

    ``hmac.compare_digest`` raises TypeError on non-ASCII *strings*; HTTP header
    values may legally carry latin-1 bytes, so a crafted token used to turn every
    such request into an unhandled 500.
    """
    env = {"STACKS_AUTH_TOKEN": "s3cr3t-token-value"}
    assert check_credentials("caf\xe9", env) is False
    assert check_credentials("caf\xe9", {"STACKS_DEMO": "1"}) is False
    # A correct token that itself contains non-ASCII still matches.
    env_unicode = {"STACKS_AUTH_TOKEN": "tok\xe9n"}
    assert check_credentials("tok\xe9n", env_unicode) is True


def test_server_rejects_unauthenticated_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The FastAPI app returns 401 with no/invalid token and 200 with a valid one."""
    fastapi = pytest.importorskip("fastapi")

    from fastapi.testclient import TestClient

    from tests.conftest import seed_store_from_env

    # Demo mode + a throwaway data dir so the server never touches the repo's data/.
    monkeypatch.setenv("STACKS_DEMO", "1")
    monkeypatch.setenv("STACKS_DATA_DIR", str(tmp_path))
    from app.server import create_app

    # The server never ingests inside a request (FIX-14) — populate the store
    # explicitly first, the same way `stacks refresh` would.
    seed_store_from_env()

    client = TestClient(create_app())

    # Health is open; the dashboard is not.
    assert client.get("/healthz").status_code == 200
    assert client.get("/").status_code == 401
    assert client.get("/", headers={"Authorization": "Bearer wrong"}).status_code == 401

    ok = client.get("/", headers={"Authorization": "Bearer demo-token"})
    assert ok.status_code == 200
    assert "Queer the Stacks" in ok.text
    assert fastapi  # used


# --- app/auth.py: signed session cookies -----------------------------------


def test_sign_and_verify_session_round_trip() -> None:
    env = {"STACKS_AUTH_TOKEN": "s3cr3t-token-value"}
    now = 1_700_000_000
    cookie = sign_session(now, env)
    assert "." in cookie
    assert verify_session(cookie, now, env) is True
    assert verify_session(cookie, now + 60, env) is True  # comfortably within TTL


def test_verify_session_rejects_tampered_cookie() -> None:
    env = {"STACKS_AUTH_TOKEN": "s3cr3t-token-value"}
    now = 1_700_000_000
    cookie = sign_session(now, env)
    issued_at_b64, _, sig = cookie.partition(".")

    tampered_sig = "0" * len(sig) if sig[0] != "0" else "1" * len(sig)
    assert verify_session(f"{issued_at_b64}.{tampered_sig}", now, env) is False

    # a cookie signed under a different token must not verify under this one
    other = sign_session(now, {"STACKS_AUTH_TOKEN": "different-token-value"})
    assert verify_session(other, now, env) is False

    assert verify_session(None, now, env) is False
    assert verify_session("no-dot-at-all", now, env) is False
    assert verify_session("", now, env) is False
    assert verify_session(".", now, env) is False  # empty issued-at and empty sig


def test_verify_session_rejects_correctly_signed_but_undecodable_payload() -> None:
    """A validly-signed cookie whose payload isn't a base64-encoded integer must
    still fail closed (defends against a signing-key/payload-format mismatch)."""
    import hashlib
    import hmac as hmac_module

    from app.auth import _signing_key  # noqa: PLC0415 - internal, test-only reach-in

    env = {"STACKS_AUTH_TOKEN": "s3cr3t-token-value"}
    bogus_payload = "not-a-valid-b64-int"
    sig = hmac_module.new(
        _signing_key(env), bogus_payload.encode("ascii"), hashlib.sha256
    ).hexdigest()
    assert verify_session(f"{bogus_payload}.{sig}", 1_700_000_000, env) is False


def test_verify_session_fails_closed_when_auth_not_configured() -> None:
    # No STACKS_AUTH_TOKEN and no demo mode -> expected_token() raises -> reject.
    assert verify_session("YW55.deadbeef", 1_700_000_000, {}) is False


def test_verify_session_rejects_expired_cookie() -> None:
    env = {"STACKS_AUTH_TOKEN": "s3cr3t-token-value"}
    now = 1_700_000_000
    cookie = sign_session(now, env)

    assert verify_session(cookie, now + SESSION_TTL_SECONDS + 1, env) is False
    assert verify_session(cookie, now + SESSION_TTL_SECONDS, env) is True  # exactly at TTL edge
    assert verify_session(cookie, now - 1, env) is False  # backdated relative to "now" -> reject


# --- app/auth.py: failed-login lockout tracker ------------------------------


def test_lockout_tracker_locks_after_n_failures_and_expires() -> None:
    tracker = LoginLockoutTracker(max_failures=3, window_seconds=900)
    now = 1_700_000_000

    assert tracker.is_locked_out("1.2.3.4", now) is False
    tracker.record_failure("1.2.3.4", now)
    tracker.record_failure("1.2.3.4", now)
    assert tracker.is_locked_out("1.2.3.4", now) is False  # 2 failures, not yet locked
    tracker.record_failure("1.2.3.4", now)
    assert tracker.is_locked_out("1.2.3.4", now) is True  # 3rd failure trips it

    assert tracker.is_locked_out("5.6.7.8", now) is False  # a different IP is unaffected

    assert tracker.is_locked_out("1.2.3.4", now + 901) is False  # window has elapsed


def test_lockout_tracker_reset_clears_history() -> None:
    tracker = LoginLockoutTracker(max_failures=3, window_seconds=900)
    now = 1_700_000_000
    for _ in range(3):
        tracker.record_failure("9.9.9.9", now)
    assert tracker.is_locked_out("9.9.9.9", now) is True

    tracker.reset("9.9.9.9")
    assert tracker.is_locked_out("9.9.9.9", now) is False


# --- app/server.py: browser session flow, via FastAPI TestClient -----------


@pytest.fixture(autouse=True)
def _reset_server_lockout() -> None:
    """The server's lockout tracker is process-local (module-level singleton) so
    it survives real restarts too — but that means every TestClient in this file
    shares it (they all present the same synthetic ``testclient`` IP). Reset it
    between tests so failures recorded by one test can't lock out another."""
    pytest.importorskip("fastapi")
    from app.server import _lockout

    _lockout._failures.clear()
    yield
    _lockout._failures.clear()


def _demo_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    monkeypatch.setenv("STACKS_DEMO", "1")
    monkeypatch.setenv("STACKS_DATA_DIR", str(tmp_path))
    from tests.conftest import seed_store_from_env

    seed_store_from_env()
    from app.server import create_app

    # https:// base_url: the session cookie is Secure, so an http:// test client
    # would silently withhold it on every subsequent request (correctly mirroring
    # real browser behaviour) and every cookie-carrying assertion below would fail.
    return TestClient(create_app(), base_url="https://testserver")


def test_server_tampered_cookie_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    client = _demo_client(tmp_path, monkeypatch)
    client.cookies.set("stacks_session", "not-a-real-payload.deadbeefdeadbeef")
    assert client.get("/").status_code == 401


def test_server_expired_cookie_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    client = _demo_client(tmp_path, monkeypatch)
    stale = sign_session(int(time.time()) - SESSION_TTL_SECONDS - 10, {"STACKS_DEMO": "1"})
    client.cookies.set("stacks_session", stale)
    assert client.get("/").status_code == 401


def test_server_valid_cookie_reaches_dashboard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    client = _demo_client(tmp_path, monkeypatch)
    fresh = sign_session(int(time.time()), {"STACKS_DEMO": "1"})
    client.cookies.set("stacks_session", fresh)
    ok = client.get("/")
    assert ok.status_code == 200
    assert "Queer the Stacks" in ok.text


def test_login_success_sets_cookie_and_grants_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    client = _demo_client(tmp_path, monkeypatch)

    form = client.get("/login")
    assert form.status_code == 200
    assert '<label for="token">' in form.text
    assert '<input id="token" name="token"' in form.text
    assert 'aria-invalid="true"' not in form.text
    assert 'aria-describedby="login-error"' not in form.text

    resp = client.post("/login", data={"token": "demo-token"}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"

    set_cookie = resp.headers.get("set-cookie", "")
    assert "stacks_session=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "secure" in set_cookie.lower()
    assert "samesite=strict" in set_cookie.lower()

    # the cookie now stored on the client reaches the dashboard with no header
    ok = client.get("/")
    assert ok.status_code == 200
    assert "Queer the Stacks" in ok.text


def test_login_failure_does_not_grant_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    client = _demo_client(tmp_path, monkeypatch)

    resp = client.post("/login", data={"token": "wrong"})
    assert resp.status_code == 401
    assert '<p id="login-error" role="alert" class="error">Incorrect token.</p>' in resp.text
    assert 'aria-invalid="true"' in resp.text
    assert 'aria-describedby="login-error"' in resp.text
    assert "set-cookie" not in {k.lower() for k in resp.headers}
    assert client.get("/").status_code == 401


def test_logout_clears_cookie(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    client = _demo_client(tmp_path, monkeypatch)

    client.post("/login", data={"token": "demo-token"})
    assert client.get("/").status_code == 200

    resp = client.get("/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"

    assert client.get("/").status_code == 401


def test_lockout_after_n_failed_logins_returns_429(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    from app.auth import LOCKOUT_MAX_FAILURES

    client = _demo_client(tmp_path, monkeypatch)

    for _ in range(LOCKOUT_MAX_FAILURES):
        resp = client.post("/login", data={"token": "wrong"})
        assert resp.status_code == 401

    locked = client.post("/login", data={"token": "wrong"})
    assert locked.status_code == 429

    # even the correct token is refused while locked out
    still_locked = client.post("/login", data={"token": "demo-token"})
    assert still_locked.status_code == 429
    assert client.get("/").status_code == 401


# --- The route table itself: every route, not two of them -------------------


def _seeded_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """A TestClient over a demo app whose store has been refreshed once."""
    from app.server import create_app
    from fastapi.testclient import TestClient

    from tests.conftest import seed_store_from_env

    monkeypatch.setenv("STACKS_DEMO", "1")
    monkeypatch.setenv("STACKS_DATA_DIR", str(tmp_path))
    seed_store_from_env()
    app_obj = create_app()
    return app_obj, TestClient(app_obj, base_url="https://testserver")


def test_the_registered_route_table_is_exactly_what_is_declared() -> None:
    """Pin the route table so a new route is visible in review.

    The enumeration below already fails on an *ungated* route. This catches the
    other half: a route added *with* auth still has to be looked at, because the
    reason it is safe to serve is a human judgement, not a status code.
    """
    pytest.importorskip("fastapi")
    from app.server import create_app

    assert _registered_routes(create_app()) == EXPECTED_ROUTES


def test_every_registered_route_is_authed_or_explicitly_public(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No route answers without credentials unless it is on PUBLIC_PATHS.

    This replaces asserting 401 on ``/`` alone and inferring the other sixteen.
    The previous check verified 2 routes of 17, and the one route that had
    slipped through — ``/openapi.json``, registered by FastAPI rather than by
    this project's own code — was not one of the two. A hand-written list of
    paths could not have covered it; enumerating ``app.routes`` does.
    """
    pytest.importorskip("fastapi")
    app_obj, client = _seeded_client(tmp_path, monkeypatch)

    gated: list[tuple[str, str]] = []
    for path, method in sorted(_registered_routes(app_obj)):
        if path in PUBLIC_PATHS:
            continue
        response = client.request(method, path)
        assert response.status_code == 401, (
            f"{method} {path} answered {response.status_code} with no credentials; "
            "every route must require auth or be listed in PUBLIC_PATHS with a reason"
        )
        gated.append((path, method))

    # A loop that iterated nothing would also "pass" every assertion above, so
    # pin how many routes were actually exercised. Counted as (path, method)
    # pairs: /login is public on both GET and POST.
    public_pairs = {(path, method) for path, method in EXPECTED_ROUTES if path in PUBLIC_PATHS}
    assert len(gated) == len(EXPECTED_ROUTES) - len(public_pairs)
    assert set(PUBLIC_PATHS) <= {path for path, _ in EXPECTED_ROUTES}


@pytest.mark.parametrize("path", DOC_SURFACES)
def test_no_api_documentation_surface_is_served(
    path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``/openapi.json`` must not exist, with or without credentials.

    ``docs_url=None, redoc_url=None`` closed two of the three doc surfaces;
    ``openapi_url`` was not set alongside them, so FastAPI still served the
    schema: every private path, each route's query-parameter names, and the
    session cookie name, to an anonymous caller. Asserted for the authenticated
    case too, because the fix is that the document is not generated — not that
    it is merely gated.
    """
    pytest.importorskip("fastapi")
    _, client = _seeded_client(tmp_path, monkeypatch)

    assert client.get(path).status_code == 404
    assert client.get(path, headers={"Authorization": "Bearer demo-token"}).status_code == 404


def test_public_routes_leak_no_reading_content_and_name_no_private_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Being public is only safe if the response says nothing.

    Asserts the absence of the unsafe outcome rather than the presence of a
    status code: no title, no author, and no private route path anywhere an
    anonymous caller can read.
    """
    pytest.importorskip("fastapi")
    from ingest.demo import demo_reading_states

    _, client = _seeded_client(tmp_path, monkeypatch)

    reading_data: set[str] = set()
    for state in demo_reading_states(tmp_path / "demo"):
        reading_data.add(state.book.title.lower())
        reading_data.update(name.lower() for name in state.book.author_names)
    assert reading_data, "the fixture library is empty; this assertion would be vacuous"

    # "/" is a substring of every path, so it is covered by its own 401 above.
    private_paths = {
        path for path, _ in EXPECTED_ROUTES if path not in PUBLIC_PATHS and len(path) > 1
    }
    assert private_paths, "no private routes to check for"

    for path in sorted(PUBLIC_PATHS):
        body = client.get(path).text.lower()
        leaked = sorted(item for item in reading_data if item in body)
        assert leaked == [], f"{path} served reading content without credentials: {leaked}"
        named = sorted(p for p in private_paths if p in body)
        assert named == [], f"{path} named private routes without credentials: {named}"
