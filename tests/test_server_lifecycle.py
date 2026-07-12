"""FIX-14 — serving-path lifecycle: startup checks, view cache, 503-until-refreshed.

Covers what `app/server.py` is actually responsible for now that first-run
ingest no longer runs inside a request:
  * data routes work end-to-end against a populated store (behind auth),
  * data routes fail closed with 503 against a never-refreshed store,
  * the built `DashboardView` is cached and only rebuilt when the store's
    `refreshed_at()` stamp (or the view-relevant config) actually changes,
  * the FastAPI lifespan fails closed on bad config / an unreachable store.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

AUTH = {"Authorization": "Bearer demo-token"}


def _demo_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STACKS_DEMO", "1")
    monkeypatch.setenv("STACKS_DATA_DIR", str(tmp_path))


# --- (a) full route coverage against a populated store -----------------------


def test_all_data_routes_serve_against_a_populated_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    from app import server
    from fastapi.testclient import TestClient

    from tests.conftest import seed_store_from_env

    _demo_env(monkeypatch, tmp_path)
    seed_store_from_env()

    with TestClient(server.create_app()) as client:
        dashboard = client.get("/", headers=AUTH)
        assert dashboard.status_code == 200
        assert "Queer the Stacks" in dashboard.text

        browse = client.get("/browse", headers=AUTH, params={"q": "a"})
        assert browse.status_code == 200

        share = client.get("/share", headers=AUTH)
        assert share.status_code == 200
        assert "Share cards" in share.text

        svg = client.get("/share/card.svg", headers=AUTH)
        assert svg.status_code == 200
        assert svg.headers["content-type"].startswith("image/svg+xml")


# --- (b) 503 fail-closed on an unpopulated store ------------------------------


def test_data_routes_503_until_the_store_is_refreshed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    from app import server
    from fastapi.testclient import TestClient

    _demo_env(monkeypatch, tmp_path)
    # Deliberately do NOT seed the store — no `stacks refresh` has ever run.

    with TestClient(server.create_app()) as client:
        for path in ("/", "/browse", "/share", "/share/card.svg"):
            resp = client.get(path, headers=AUTH)
            assert resp.status_code == 503, path


def test_healthz_and_livez_never_503_when_unpopulated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    from app import server
    from fastapi.testclient import TestClient

    _demo_env(monkeypatch, tmp_path)
    with TestClient(server.create_app()) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/livez").status_code == 200


# --- (c) the view cache is stamp+config keyed ---------------------------------


def test_view_cache_reuses_the_built_view_until_the_store_is_refreshed_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    from app import server
    from fastapi.testclient import TestClient
    from ingest.config import load_config
    from ingest.refresh import refresh
    from ingest.store import Store

    from tests.conftest import seed_store_from_env

    _demo_env(monkeypatch, tmp_path)
    seed_store_from_env()

    calls = {"n": 0}
    real_view_from_store = server.view_from_store

    def counting_view_from_store(*args: object, **kwargs: object) -> object:
        calls["n"] += 1
        return real_view_from_store(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(server, "view_from_store", counting_view_from_store)

    app = server.create_app()
    with TestClient(app) as client:
        first = client.get("/", headers=AUTH)
        second = client.get("/", headers=AUTH)
        assert first.status_code == second.status_code == 200
        assert calls["n"] == 1, "second request should hit the cache, not rebuild"

        # /browse only replaces .library on the cached base view — still no rebuild.
        browse = client.get("/browse", headers=AUTH)
        assert browse.status_code == 200
        assert calls["n"] == 1

        # Bump refreshed_at (as `stacks refresh` would) -> the next request rebuilds.
        config = load_config()
        store = Store(config.store_path)
        try:
            refresh(config, store, now=int(time.time()) + 3600, force=True)
        finally:
            store.close()

        third = client.get("/", headers=AUTH)
        assert third.status_code == 200
        assert calls["n"] == 2, "a new refreshed_at stamp must invalidate the cache"


def test_view_cache_key_changes_with_view_relevant_config(tmp_path: Path) -> None:
    import dataclasses

    from app import server
    from ingest.config import Config

    base = Config(
        calibre_db=None,
        koreader_db=None,
        data_dir=tmp_path,
        kosync_host=None,
        kosync_user=None,
        kosync_key=None,
        demo=True,
    )
    varied = dataclasses.replace(base, goal_books=42)
    assert server._cache_key(base, 100) != server._cache_key(varied, 100)
    assert server._cache_key(base, 100) == server._cache_key(base, 100)
    assert server._cache_key(base, 100) != server._cache_key(base, 200)


# --- (d) lifespan validation fails closed -------------------------------------


def test_lifespan_fails_closed_on_invalid_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    from app import server
    from fastapi.testclient import TestClient

    bad_config = tmp_path / "stacks.toml"
    bad_config.write_text("this is not valid TOML [[[", encoding="utf-8")
    monkeypatch.setenv("STACKS_CONFIG", str(bad_config))

    with pytest.raises(server.ConfigInvalid), TestClient(server.create_app()):
        pass  # pragma: no cover - startup must raise before we get here


def test_lifespan_fails_closed_on_unreachable_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    from app import server
    from fastapi.testclient import TestClient

    # A regular file where the store's data dir should be: Store's mkdir(parents=True)
    # cannot create a directory there, so opening the store raises at startup.
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("STACKS_DEMO", "1")
    monkeypatch.setenv("STACKS_DATA_DIR", str(blocker / "data"))

    with pytest.raises(server.StoreUnavailable), TestClient(server.create_app()):
        pass  # pragma: no cover - startup must raise before we get here


def test_lifespan_does_not_block_startup_when_store_is_unpopulated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty store is a warning, not a startup failure — routes 503 instead."""
    pytest.importorskip("fastapi")
    from app import server
    from fastapi.testclient import TestClient

    _demo_env(monkeypatch, tmp_path)
    with TestClient(server.create_app()) as client:
        assert client.get("/healthz").status_code == 200
