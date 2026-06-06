"""Authentication for the self-hosted app — required, single-user, private.

Security guardrail (README + audit §F): the dashboard is reachable *only* behind
auth. This module holds the pure credential check so it can be unit-tested
independently of the web wiring; the FastAPI dependency in :mod:`app.server`
calls :func:`check_credentials` on every request.

The expected token comes from the environment (``QSR_AUTH_TOKEN``), never source.
Comparison is constant-time (``hmac.compare_digest``) to avoid timing leaks. In
demo mode (``QSR_DEMO=1``) a fixed demo token is used so the app still requires
auth — there is no unauthenticated path.
"""

from __future__ import annotations

import hmac
import os
from collections.abc import Mapping
from typing import Optional

DEMO_TOKEN = "demo-token"  # noqa: S105 - not a secret; only used when QSR_DEMO=1
AUTH_ENV = "QSR_AUTH_TOKEN"
DEMO_ENV = "QSR_DEMO"


class AuthNotConfigured(Exception):
    """Raised when the app starts with no auth token and demo mode is off."""


def expected_token(env: Optional[Mapping[str, str]] = None) -> str:
    """Resolve the required token from the environment.

    Demo mode yields a fixed token (auth is still enforced); otherwise
    ``QSR_AUTH_TOKEN`` must be set, or startup fails closed.
    """
    resolved: Mapping[str, str] = os.environ if env is None else env
    if resolved.get(DEMO_ENV) == "1":
        return resolved.get(AUTH_ENV) or DEMO_TOKEN
    token = resolved.get(AUTH_ENV)
    if not token:
        raise AuthNotConfigured(
            f"{AUTH_ENV} is not set; refusing to serve an unauthenticated dashboard"
        )
    return token


def check_credentials(presented: Optional[str], env: Optional[Mapping[str, str]] = None) -> bool:
    """Constant-time check of a presented token against the expected one."""
    if not presented:
        return False
    return hmac.compare_digest(presented, expected_token(env))
