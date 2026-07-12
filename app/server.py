"""The self-hosted FastAPI app — serves the dashboard, only behind auth.

Every content route depends on :func:`require_auth`, which rejects any request
without a valid bearer token *or* a valid signed session cookie (401). There is
no unauthenticated path: even ``/`` is gated, because a reading history can out
a reader (privacy guardrail). The app is single-user and binds to localhost by
default (``make dev``); deployment puts it behind the seedbox's auth next to
Calibre-Web.

Browser session auth (FIX-04): a phone/desktop browser can't attach an
``Authorization`` header on plain navigation, so ``GET /login`` renders a form
and ``POST /login`` exchanges the same bearer token for a signed, HttpOnly,
``SameSite=Strict``, ``Secure`` cookie (see :mod:`app.auth` for the signing and
TTL). ``GET /logout`` clears it. The ``Secure`` attribute means the cookie is
only ever sent by the browser over HTTPS — deployment must terminate TLS in
front of this app (the seedbox's reverse proxy) or otherwise ensure the
browser reaches it only over a secure/loopback channel, or the cookie flow
simply won't work (by design: no session ever traverses plain HTTP).

Every other route stays GET-only, so CSRF exposure elsewhere stays nil.
``POST /login`` is the one deliberate exception: putting the bearer token in a
``GET`` query string would leak it into browser history, referrers, and access
logs, which is worse than the (nil, since it only ever *creates* a session
using a secret the client already proved knowledge of, and SameSite=Strict
blocks cross-site delivery of any ambient cookie) CSRF exposure of a POST form.

Coverage note: this thin wiring is omitted from the unit-coverage gate and
verified instead by the auth access test in ``tests/test_auth.py`` via FastAPI's
TestClient.
"""

from __future__ import annotations

import os
import time
from html import escape
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version
from typing import Optional

from fastapi import Cookie, Depends, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from ingest.config import load_config
from ingest.refresh import refresh
from ingest.store import Store
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app import opds
from app.auth import (
    SESSION_TTL_SECONDS,
    LoginLockoutTracker,
    check_credentials,
    sign_session,
    verify_session,
)
from app.logging_config import RequestLoggingMiddleware, configure_logging, get_logger
from app.security_headers import SECURITY_HEADERS
from app.view import DashboardView, render_view, view_from_store

SESSION_COOKIE = "stacks_session"  # noqa: S105 - cookie name, not a secret


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach the fixed defense-in-depth header set to every response.

    Runs on ALL routes — dashboard, ``/browse``, ``/share``, and the
    health/ready probes — including 401s from :func:`require_auth`, since
    headers are applied to whatever ``call_next`` returns regardless of
    status code.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        return response


# Process-local: single-user, single-process self-hosted app. A restart resets
# any in-progress lockouts.
_lockout = LoginLockoutTracker()


def require_auth(
    authorization: Optional[str] = Header(default=None),
    stacks_session: Optional[str] = Cookie(default=None),
) -> None:
    """Require a valid bearer token or signed session cookie."""
    token: Optional[str] = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[len("bearer ") :].strip()
    if check_credentials(token):
        return
    if verify_session(stacks_session, int(time.time())):
        return
    raise HTTPException(
        status_code=401,
        detail="authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _render_login_page(error: Optional[str] = None) -> str:
    """Render the minimal sign-in form (same escaping + a11y discipline as the
    dashboard renderer: lang, viewport, one h1, a main landmark, a skip link,
    and a label linked to its input).
    """
    error_html = f'<p role="alert" class="error">{escape(error)}</p>' if error else ""
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Queer the Stacks — sign in</title>"
        "<style>"
        ":root { color-scheme: light dark; }"
        "body { font-family: system-ui, sans-serif; max-width: 40ch; margin: 3rem auto; "
        "padding: 1rem; }"
        "a:focus, .skip:focus, input:focus, button:focus { outline: 3px solid; }"
        ".skip { position: absolute; left: -999px; }"
        ".skip:focus { left: 1rem; top: 1rem; }"
        "label { display: block; margin: 1rem 0 0.25rem; }"
        "input { width: 100%; padding: 0.5rem; font-size: 1rem; }"
        "button { margin-top: 1rem; padding: 0.5rem 1rem; font-size: 1rem; }"
        ".error { border: 1px solid; border-radius: 4px; padding: 0.5rem; }"
        "</style></head><body>"
        '<a class="skip" href="#main">Skip to the sign-in form</a>'
        '<main id="main">'
        "<h1>Queer the Stacks</h1>"
        "<p>Sign in with your access token to reach your private reading "
        "dashboard.</p>"
        f"{error_html}"
        '<form method="post" action="/login">'
        '<label for="token">Access token</label>'
        '<input id="token" name="token" type="password" autocomplete="current-password" '
        "required autofocus>"
        '<button type="submit">Sign in</button>'
        "</form>"
        "</main></body></html>"
    )


def _load_view(*, hide_sensitive: bool = False) -> DashboardView:
    """Load the dashboard from the persisted store, refreshing on first run.

    ``hide_sensitive`` is a per-request privacy override; it can only *add*
    aggregation on top of the configured default (you can always hide more).
    """
    from recommender.lists_store import list_store_path, load_stored_lists

    config = load_config()
    store = Store(config.store_path)
    try:
        if not store.is_populated:
            refresh(config, store, now=int(time.time()))
        return view_from_store(
            store,
            user="demo" if config.demo else "you",
            aperture_strength=config.aperture_strength,
            use_embeddings=config.embeddings_enabled,
            dnf_signals=config.dnf_signals,
            goal_books=config.goal_books,
            goal_pages=config.goal_pages,
            goal_hours=config.goal_hours,
            goal_streak_days=config.goal_streak_days,
            lens_config=config.lens_config,
            hide_sensitive_descriptors=config.hide_sensitive_descriptors or hide_sensitive,
            authored_lists=load_stored_lists(list_store_path(config)),
        )
    finally:
        store.close()


def _calibre_web_url() -> Optional[str]:
    """The optional, config-driven base URL of a sibling Calibre-Web instance.

    Never hardcoded: read from ``STACKS_CALIBRE_WEB_URL`` only, and omitted
    from OPDS entries entirely when unset. Used only as link text in rendered
    XML — never fetched, so it introduces no egress.
    """
    return os.environ.get("STACKS_CALIBRE_WEB_URL") or None


def readiness_probe() -> dict[str, str]:
    """Probe the derived-state store dependency; raise if it is unavailable.

    Fail-closed: any failure to resolve config or open/query the app-state store
    means the service is NOT ready to serve traffic. On success returns a
    component-status map. It never returns (or lets ``/readyz`` return) a path,
    an exception message, or any reading content.
    """
    config = load_config()
    store = Store(config.store_path)
    try:
        store.refreshed_at()  # exercises a real SELECT against the app-state DB
    finally:
        store.close()
    return {"store": "ok"}


# Route handlers are module-level (not nested inside create_app) and wired up
# via add_api_route below — the mccabe/C90 complexity gate (QW-10) counts a
# closure's branches against its enclosing function, and create_app() itself
# should stay a flat, low-complexity list of route registrations regardless of
# how many probe/route handlers exist.


def _healthz() -> dict[str, str]:
    return {"status": "ok"}


def _livez() -> dict[str, str]:
    """Liveness: process is up and not deadlocked. No dependency calls."""
    return {"status": "ok"}


def _version() -> dict[str, str]:
    """Report the installed package version (REL-19). No internal detail beyond semver."""
    try:
        return {"version": _package_version("queer-the-stacks")}
    except PackageNotFoundError:  # pragma: no cover - only if installed non-editable/unnamed
        return {"version": "unknown"}


def _readyz() -> Response:
    """Readiness: fail closed with 503 if the app-state store is unavailable."""
    try:
        checks = readiness_probe()
    except Exception as exc:  # fail closed on ANY dependency error
        # Log the failure type only — never the exception text or a path.
        get_logger().warning("readyz_unavailable", extra={"error_type": type(exc).__name__})
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return JSONResponse(status_code=200, content={"status": "ok", "checks": checks})


def _login_form() -> HTMLResponse:
    """Render the sign-in form. Unauthenticated by necessity (it's the entry
    point), but it reveals no reading content — just an empty form."""
    return HTMLResponse(content=_render_login_page())


def _login_submit(request: Request, token: str = Form(...)) -> Response:
    """Exchange the bearer token for a signed session cookie.

    The lone POST route in an otherwise GET-only app — see the module
    docstring for why a GET-with-query-param login was rejected. Failed
    attempts are rate-limited per client IP (5 / 15min) to blunt brute force.
    """
    now = int(time.time())
    ip = _client_ip(request)
    if _lockout.is_locked_out(ip, now):
        return HTMLResponse(
            content=_render_login_page("Too many attempts. Try again later."),
            status_code=429,
        )
    if not check_credentials(token):
        _lockout.record_failure(ip, now)
        return HTMLResponse(
            content=_render_login_page("Incorrect token."),
            status_code=401,
        )
    _lockout.reset(ip)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        sign_session(now),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )
    return response


def _logout() -> Response:
    """Clear the session cookie and send the browser back to /login."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=True,
        samesite="strict",
    )
    return response


def _dashboard(hide_sensitive: bool = False) -> HTMLResponse:
    return HTMLResponse(content=render_view(_load_view(hide_sensitive=hide_sensitive)))


def _browse(
    theme: Optional[str] = None,
    author: Optional[str] = None,
    series: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
) -> HTMLResponse:
    import dataclasses

    from app.browse import filter_states

    view = _load_view()
    filtered = filter_states(
        list(view.library),
        theme=theme,
        author=author,
        series=series,
        status=status,
        q=q,
    )
    return HTMLResponse(content=render_view(dataclasses.replace(view, library=tuple(filtered))))


def _share() -> HTMLResponse:
    """Locally-composed share cards. Nothing is posted; the user copies them."""
    from app.share import build_share_cards, render_share_page

    view = _load_view()
    cards = build_share_cards(view)
    return HTMLResponse(content=render_share_page(cards, user=view.user))


def _share_card_svg(kind: str = "year") -> Response:
    """Serve a single share card as a self-contained SVG image for download."""
    from app.share import build_share_cards

    view = _load_view()
    cards = build_share_cards(view)
    chosen = next((c for c in cards if c.kind == kind), cards[0] if cards else None)
    if chosen is None:
        raise HTTPException(status_code=404, detail="no share card available")
    from app.share import render_share_svg

    return Response(content=render_share_svg(chosen), media_type="image/svg+xml")


def _opds_root() -> Response:
    """Root OPDS navigation feed, browsable from KOReader/Readest."""
    return Response(content=opds.build_root_navigation(_load_view()), media_type=opds.NAV_TYPE)


def _opds_shelf(shelf_id: str) -> Response:
    view = _load_view()
    entries = opds.entries_for_shelf(shelf_id, view)
    feed = opds.build_shelf_acquisition(
        shelf_id,
        opds.SHELF_TITLES[shelf_id],
        entries,
        calibre_web_url=_calibre_web_url(),
    )
    return Response(content=feed, media_type=opds.ACQ_TYPE)


def _opds_to_read() -> Response:
    return _opds_shelf("to-read")


def _opds_currently_reading() -> Response:
    return _opds_shelf("currently-reading")


def _opds_series_next() -> Response:
    return _opds_shelf("series-next")


def _opds_recommendations() -> Response:
    return _opds_shelf("recommendations")


def create_app() -> FastAPI:
    app = FastAPI(title="Queer the Stacks", docs_url=None, redoc_url=None)
    configure_logging()
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    app.add_api_route("/healthz", _healthz, methods=["GET"])
    app.add_api_route("/livez", _livez, methods=["GET"])
    app.add_api_route("/version", _version, methods=["GET"])
    app.add_api_route("/readyz", _readyz, methods=["GET"])
    app.add_api_route(
        "/login",
        _login_form,
        methods=["GET"],
        response_class=HTMLResponse,
    )
    app.add_api_route(
        "/login",
        _login_submit,
        methods=["POST"],
    )
    app.add_api_route(
        "/logout",
        _logout,
        methods=["GET"],
    )
    app.add_api_route(
        "/",
        _dashboard,
        methods=["GET"],
        response_class=HTMLResponse,
        dependencies=[Depends(require_auth)],
    )
    app.add_api_route(
        "/browse",
        _browse,
        methods=["GET"],
        response_class=HTMLResponse,
        dependencies=[Depends(require_auth)],
    )
    app.add_api_route(
        "/opds",
        _opds_root,
        methods=["GET"],
        dependencies=[Depends(require_auth)],
    )
    app.add_api_route(
        "/opds/to-read",
        _opds_to_read,
        methods=["GET"],
        dependencies=[Depends(require_auth)],
    )
    app.add_api_route(
        "/opds/currently-reading",
        _opds_currently_reading,
        methods=["GET"],
        dependencies=[Depends(require_auth)],
    )
    app.add_api_route(
        "/opds/series-next",
        _opds_series_next,
        methods=["GET"],
        dependencies=[Depends(require_auth)],
    )
    app.add_api_route(
        "/opds/recommendations",
        _opds_recommendations,
        methods=["GET"],
        dependencies=[Depends(require_auth)],
    )
    app.add_api_route(
        "/share",
        _share,
        methods=["GET"],
        response_class=HTMLResponse,
        dependencies=[Depends(require_auth)],
    )
    app.add_api_route(
        "/share/card.svg",
        _share_card_svg,
        methods=["GET"],
        dependencies=[Depends(require_auth)],
    )
    return app


app = create_app()
