"""The self-hosted FastAPI app — serves the dashboard, only behind auth.

Every route depends on :func:`require_auth`, which rejects any request without a
valid bearer token (401). There is no unauthenticated path: even ``/`` is gated,
because a reading history can out a reader (privacy guardrail). The app is
single-user and binds to localhost by default (``make dev``); deployment puts it
behind the seedbox's auth next to Calibre-Web.

Startup fails closed (mirrors ``app.auth.AuthNotConfigured``): the FastAPI
``lifespan`` resolves config and probes the app-state store once, raising
:class:`ConfigInvalid` or :class:`StoreUnavailable` rather than booting a server
that would otherwise fail every request one at a time. An unpopulated (never
refreshed) store is *not* a startup failure — it only logs a warning; data
routes fail closed with 503 until an explicit ``stacks refresh`` populates the
store. No route ever runs ingest inline.

The built :class:`~app.view.DashboardView` is cached on ``app.state`` keyed by
``Store.refreshed_at()`` plus a hash of the view-relevant config fields, so a
request only rebuilds stats/wrapped/diversity/recommendations when the store
was actually refreshed or the config actually changed — not on every request.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from ingest.config import Config, load_config
from ingest.store import Store

from app.auth import check_credentials
from app.logging_config import RequestLoggingMiddleware, configure_logging, get_logger
from app.view import DashboardView, render_view, view_from_store

# (store_path, refreshed_at stamp, hash of view-relevant config fields)
_ViewCacheKey = tuple[str, Optional[int], int]
_ViewCacheEntry = tuple[_ViewCacheKey, DashboardView]


class ConfigInvalid(Exception):
    """Raised at startup when the app configuration cannot be resolved."""


class StoreUnavailable(Exception):
    """Raised at startup when the app-state store cannot be opened or probed."""


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


def _cache_key(config: Config, stamp: Optional[int]) -> _ViewCacheKey:
    return (str(config.store_path), stamp, hash(config.view_cache_fields()))


def _load_view(app: FastAPI) -> DashboardView:
    """Load the dashboard view, cached on ``app.state`` by (store stamp, config).

    Fails closed with 503 if the store has never been refreshed — ingest never
    runs inside a request; run ``stacks refresh`` first to populate it.
    """
    config = load_config()
    store = Store(config.store_path)
    try:
        stamp = store.refreshed_at()
        if stamp is None:
            raise HTTPException(
                status_code=503,
                detail="dashboard not yet populated — run `stacks refresh` first",
            )
        key = _cache_key(config, stamp)
        cached: Optional[_ViewCacheEntry] = app.state.view_cache
        if cached is not None and cached[0] == key:
            return cached[1]
        view = view_from_store(
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
        app.state.view_cache = (key, view)
        return view
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


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Fail closed at startup, like ``app.auth.AuthNotConfigured``.

    A broken config file or an unreachable/unwritable app-state store must
    never surface as a server that looks up and then fails every request one
    at a time — it should refuse to boot. An empty (never-refreshed) store is
    NOT a startup failure: it only warns, since running ingest at startup can
    be slow/blocking; ``_load_view`` fails closed with 503 per-request instead.
    """
    try:
        config = load_config()
    except Exception as exc:  # config resolution itself failed (e.g. bad TOML)
        raise ConfigInvalid("failed to resolve app configuration at startup") from exc

    try:
        store = Store(config.store_path)
        try:
            populated = store.refreshed_at() is not None  # same probe /readyz uses
        finally:
            store.close()
    except Exception as exc:  # store unreachable/unwritable/corrupt
        raise StoreUnavailable("app-state store is unavailable at startup") from exc

    if not populated:
        get_logger().warning("startup_store_unpopulated")

    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Queer the Stacks", docs_url=None, redoc_url=None, lifespan=_lifespan)
    app.state.view_cache = None  # set unconditionally: independent of whether lifespan ran
    configure_logging()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/livez")
    def livez() -> dict[str, str]:
        """Liveness: process is up and not deadlocked. No dependency calls."""
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> Response:
        """Readiness: fail closed with 503 if the app-state store is unavailable."""
        try:
            checks = readiness_probe()
        except Exception as exc:  # fail closed on ANY dependency error
            # Log the failure type only — never the exception text or a path.
            get_logger().warning("readyz_unavailable", extra={"error_type": type(exc).__name__})
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return JSONResponse(status_code=200, content={"status": "ok", "checks": checks})

    @app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
    def dashboard() -> HTMLResponse:
        return HTMLResponse(content=render_view(_load_view(app)))

    @app.get("/browse", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
    def browse(
        theme: Optional[str] = None,
        author: Optional[str] = None,
        series: Optional[str] = None,
        status: Optional[str] = None,
        q: Optional[str] = None,
    ) -> HTMLResponse:
        import dataclasses

        from app.browse import filter_states

        view = _load_view(app)
        filtered = filter_states(
            list(view.library),
            theme=theme,
            author=author,
            series=series,
            status=status,
            q=q,
        )
        return HTMLResponse(content=render_view(dataclasses.replace(view, library=tuple(filtered))))

    @app.get("/share", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
    def share() -> HTMLResponse:
        """Locally-composed share cards. Nothing is posted; the user copies them."""
        from app.share import build_share_cards, render_share_page

        view = _load_view(app)
        cards = build_share_cards(view)
        return HTMLResponse(content=render_share_page(cards, user=view.user))

    @app.get("/share/card.svg", dependencies=[Depends(require_auth)])
    def share_card_svg(kind: str = "year") -> Response:
        """Serve a single share card as a self-contained SVG image for download."""
        from app.share import build_share_cards

        view = _load_view(app)
        cards = build_share_cards(view)
        chosen = next((c for c in cards if c.kind == kind), cards[0] if cards else None)
        if chosen is None:
            raise HTTPException(status_code=404, detail="no share card available")
        from app.share import render_share_svg

        return Response(content=render_share_svg(chosen), media_type="image/svg+xml")

    return app


app = create_app()
