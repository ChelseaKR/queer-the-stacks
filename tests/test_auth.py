"""Security guardrail — the dashboard is reachable only behind auth (merge-blocking)."""

from __future__ import annotations

import pytest
from app.auth import AuthNotConfigured, check_credentials, expected_token


def test_demo_mode_uses_demo_token() -> None:
    env = {"QSR_DEMO": "1"}
    assert expected_token(env) == "demo-token"
    assert check_credentials("demo-token", env) is True
    assert check_credentials("wrong", env) is False
    assert check_credentials(None, env) is False


def test_real_mode_requires_env_token() -> None:
    with pytest.raises(AuthNotConfigured):
        expected_token({})  # no demo, no token -> fail closed


def test_real_mode_token_from_env() -> None:
    env = {"QSR_AUTH_TOKEN": "s3cr3t-token-value"}
    assert check_credentials("s3cr3t-token-value", env) is True
    assert check_credentials("nope", env) is False


def test_server_rejects_unauthenticated_requests() -> None:
    """The FastAPI app returns 401 with no/invalid token and 200 with a valid one."""
    fastapi = pytest.importorskip("fastapi")
    import os

    from fastapi.testclient import TestClient

    os.environ["QSR_DEMO"] = "1"
    from app.server import create_app

    client = TestClient(create_app())

    # Health is open; the dashboard is not.
    assert client.get("/healthz").status_code == 200
    assert client.get("/").status_code == 401
    assert client.get("/", headers={"Authorization": "Bearer wrong"}).status_code == 401

    ok = client.get("/", headers={"Authorization": "Bearer demo-token"})
    assert ok.status_code == 200
    assert "Queer &amp; Spec-Fic Reader" in ok.text
    assert fastapi  # used
