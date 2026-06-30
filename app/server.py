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
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, Response
from ingest.config import load_config
from ingest.refresh import refresh
from ingest.store import Store

from app.auth import check_credentials
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


def create_app() -> FastAPI:
    app = FastAPI(title="Queer the Stacks", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
    def dashboard() -> HTMLResponse:
        return HTMLResponse(content=render_view(_load_view()))

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

    @app.get("/share", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
    def share() -> HTMLResponse:
        """Locally-composed share cards. Nothing is posted; the user copies them."""
        from app.share import build_share_cards, render_share_page

        view = _load_view()
        cards = build_share_cards(view)
        return HTMLResponse(content=render_share_page(cards, user=view.user))

    @app.get("/share/card.svg", dependencies=[Depends(require_auth)])
    def share_card_svg(kind: str = "year") -> Response:
        """Serve a single share card as a self-contained SVG image for download."""
        from app.share import build_share_cards

        view = _load_view()
        cards = build_share_cards(view)
        chosen = next((c for c in cards if c.kind == kind), cards[0] if cards else None)
        if chosen is None:
            raise HTTPException(status_code=404, detail="no share card available")
        from app.share import render_share_svg

        return Response(content=render_share_svg(chosen), media_type="image/svg+xml")

    return app


app = create_app()
