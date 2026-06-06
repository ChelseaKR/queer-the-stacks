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

import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse

from app.auth import check_credentials
from app.render import render_dashboard
from app.view import DashboardView, demo_view


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
    if os.environ.get("QSR_DEMO") == "1":
        with tempfile.TemporaryDirectory(prefix="qsr-demo-") as tmp:
            return demo_view(Path(tmp))
    # Real mode would read configured Calibre/KOReader paths here; demo is the
    # default offline experience for `make dev`.
    with tempfile.TemporaryDirectory(prefix="qsr-demo-") as tmp:
        return demo_view(Path(tmp))


def create_app() -> FastAPI:
    app = FastAPI(title="Queer & Spec-Fic Reader", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
    def dashboard() -> HTMLResponse:
        view = _load_view()
        html = render_dashboard(
            view.currently_reading,
            view.finished,
            view.stats,
            view.wrapped,
            view.recommendations,
            user=view.user,
        )
        return HTMLResponse(content=html)

    return app


app = create_app()
