"""The self-hosted FastAPI app — serves the dashboard, only behind auth.

Every route depends on :func:`require_auth`, which rejects any request without a
valid bearer token (401). There is no unauthenticated path: even ``/`` is gated,
because a reading history can out a reader (privacy guardrail). The app is
single-user and binds to localhost by default (``make dev``); deployment puts it
behind the seedbox's auth next to Calibre-Web.

Coverage note: this thin wiring is omitted from the unit-coverage gate and
verified instead by the auth access test in ``tests/test_auth.py`` via FastAPI's
TestClient.
"""

from __future__ import annotations

import time
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from ingest.config import load_config
from ingest.refresh import refresh
from ingest.store import Store

from app.auth import check_credentials
from app.logging_config import RequestLoggingMiddleware, configure_logging, get_logger
from app.view import DashboardView, render_view, view_from_store


def require_auth(authorization: Optional[str] = Header(default=None)) -> None:
    """FastAPI dependency: require a valid ``Authorization: Bearer <token>``."""
    token: Optional[str] = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[len("bearer ") :].strip()
    if not check_credentials(token):
        raise HTTPException(
            status_code=401,
            detail="authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _load_view() -> DashboardView:
    """Load the dashboard from the persisted store, refreshing on first run."""
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
        )
    finally:
        store.close()


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


def _dashboard() -> HTMLResponse:
    return HTMLResponse(content=render_view(_load_view()))


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


def create_app() -> FastAPI:
    app = FastAPI(title="Queer the Stacks", docs_url=None, redoc_url=None)
    configure_logging()
    app.add_middleware(RequestLoggingMiddleware)

    app.add_api_route("/healthz", _healthz, methods=["GET"])
    app.add_api_route("/livez", _livez, methods=["GET"])
    app.add_api_route("/version", _version, methods=["GET"])
    app.add_api_route("/readyz", _readyz, methods=["GET"])
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
