"""Authentication for the self-hosted app — required, single-user, private.

Security guardrail (README + audit §F): the dashboard is reachable *only* behind
auth. This module holds the pure credential check so it can be unit-tested
independently of the web wiring; the FastAPI dependency in :mod:`app.server`
calls :func:`check_credentials` on every request.

The expected token comes from the environment (``STACKS_AUTH_TOKEN``), never source.
Comparison is constant-time (``hmac.compare_digest``) to avoid timing leaks. In
demo mode (``STACKS_DEMO=1``) a fixed demo token is used so the app still requires
auth — there is no unauthenticated path.

Browser session cookies (FIX-04): a phone/desktop browser can't send an
``Authorization`` header on plain navigation, so ``/login`` (see
:mod:`app.server`) exchanges the bearer token for a signed, short-lived session
cookie. The signing key is *derived* from :func:`expected_token` (an HMAC over a
fixed salt) rather than a new secret, so no extra configuration is required —
whoever can already prove the bearer token can also mint sessions, and nothing
is served unauthenticated. The cookie is only ever meant to be sent over TLS:
the ``Secure`` attribute means browsers will withhold it entirely on a plain
HTTP connection, so deployment must terminate TLS in front of this app (the
seedbox/reverse proxy in front of Calibre-Web) or bind strictly to localhost
where the browser and server share the loopback interface.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from collections import defaultdict
from collections.abc import Mapping
from typing import Optional

DEMO_TOKEN = "demo-token"  # noqa: S105 - not a secret; only used when STACKS_DEMO=1
AUTH_ENV = "STACKS_AUTH_TOKEN"
DEMO_ENV = "STACKS_DEMO"

# --- Session cookies -----------------------------------------------------
SESSION_TTL_SECONDS = 12 * 60 * 60  # 12h
_SIGNING_SALT = b"queer-the-stacks:session-signing-key:v1"  # noqa: S105 - salt, not a secret

# --- Failed-login lockout --------------------------------------------------
LOCKOUT_MAX_FAILURES = 5
LOCKOUT_WINDOW_SECONDS = 15 * 60  # 15m


class AuthNotConfigured(Exception):
    """Raised when the app starts with no auth token and demo mode is off."""


def expected_token(env: Optional[Mapping[str, str]] = None) -> str:
    """Resolve the required token from the environment.

    Demo mode yields a fixed token (auth is still enforced); otherwise
    ``STACKS_AUTH_TOKEN`` must be set, or startup fails closed.
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


def _signing_key(env: Optional[Mapping[str, str]] = None) -> bytes:
    """Derive the session-signing key from the configured auth token.

    No new secret/config is introduced: the key is an HMAC of a fixed salt
    keyed by the same token :func:`check_credentials` already validates.
    Rotating ``STACKS_AUTH_TOKEN`` rotates this key too, invalidating sessions.
    """
    return hmac.new(expected_token(env).encode("utf-8"), _SIGNING_SALT, hashlib.sha256).digest()


def sign_session(now: int, env: Optional[Mapping[str, str]] = None) -> str:
    """Mint a signed session-cookie value stamped with issue time ``now``.

    Payload shape: ``base64(issued_at).hex(hmac_sha256)``. The signature covers
    the encoded issued-at so any tamper (including backdating) invalidates it.
    """
    issued_at = base64.urlsafe_b64encode(str(now).encode("ascii")).decode("ascii")
    sig = hmac.new(_signing_key(env), issued_at.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{issued_at}.{sig}"


def verify_session(
    cookie_value: Optional[str], now: int, env: Optional[Mapping[str, str]] = None
) -> bool:
    """Verify a session-cookie value: valid signature and within the TTL.

    Returns ``False`` (never raises) on any malformed, tampered, or expired
    value so callers can fail closed with a plain 401.
    """
    if not cookie_value or "." not in cookie_value:
        return False
    issued_at_b64, _, sig = cookie_value.partition(".")
    if not issued_at_b64 or not sig:
        return False
    try:
        expected_key = _signing_key(env)
    except AuthNotConfigured:
        return False
    expected_sig = hmac.new(expected_key, issued_at_b64.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return False
    try:
        issued_at = int(base64.urlsafe_b64decode(issued_at_b64.encode("ascii")).decode("ascii"))
    except ValueError, UnicodeDecodeError:
        return False
    age = now - issued_at
    return not (age < 0 or age > SESSION_TTL_SECONDS)


class LoginLockoutTracker:
    """Pure, in-memory failed-login tracker: N failures within a window locks out.

    Deliberately process-local (no persistence, no distributed state) — this is
    a single-user, single-process self-hosted app. A restart resets lockouts,
    which is an acceptable tradeoff for a homelab deployment.
    """

    def __init__(
        self, max_failures: int = LOCKOUT_MAX_FAILURES, window_seconds: int = LOCKOUT_WINDOW_SECONDS
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[str, list[int]] = defaultdict(list)

    def record_failure(self, ip: str, now: Optional[int] = None) -> None:
        """Record a failed login attempt from ``ip`` at time ``now``."""
        moment = int(time.time()) if now is None else now
        self._failures[ip].append(moment)

    def reset(self, ip: str) -> None:
        """Clear failure history for ``ip`` (call on successful login)."""
        self._failures.pop(ip, None)

    def is_locked_out(self, ip: str, now: Optional[int] = None) -> bool:
        """Return True if ``ip`` has >= max_failures within the trailing window."""
        moment = int(time.time()) if now is None else now
        cutoff = moment - self.window_seconds
        recent = [t for t in self._failures.get(ip, []) if t > cutoff]
        self._failures[ip] = recent
        return len(recent) >= self.max_failures
