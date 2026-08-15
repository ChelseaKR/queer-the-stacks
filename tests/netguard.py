"""Runtime network guards for the privacy tests — measurement, not text search.

Two helpers, both used by ``tests/test_no_egress.py``:

* :func:`no_network` traps the socket primitives every Python HTTP client
  ultimately goes through (``connect``, ``connect_ex``, ``sendto``,
  ``create_connection``, ``getaddrinfo``, ``gethostbyname``) and raises on the
  first attempt. A code path executed inside it *cannot* silently reach the
  network: either it makes no connection, or the test fails. This is what makes
  the no-egress assertions measurements of behaviour rather than of source text.

* :func:`capture_requests` swaps ``requests.sessions.Session.send``, which sits
  *below* ``requests.get``. Everything above it stays real — URL assembly, query
  parameters, headers, redirect policy — so a test can assert exactly what would
  have gone on the wire without a wire being there.

Neither helper is a production control; they exist so the guardrail tests can
observe the real request path.
"""

from __future__ import annotations

import socket
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Optional


class EgressAttempted(AssertionError):
    """Raised when guarded code tries to open a network connection."""


@contextmanager
def no_network() -> Iterator[list[str]]:
    """Block (and record) every outbound socket operation inside the block.

    Yields the list of attempts. It stays empty for a code path that never
    reaches the network; any attempt both appends to it and raises
    :class:`EgressAttempted` at the call site, so a swallowed exception cannot
    hide the attempt from the assertion afterwards.
    """
    attempts: list[str] = []
    saved: list[tuple[object, str, object]] = []

    def _install(label: str, owner: Any, attr: str) -> None:
        original = getattr(owner, attr)

        def _blocked(*args: object, **kwargs: object) -> object:
            # Bound socket methods carry `self` first; module-level helpers do not.
            target = args[1] if (owner is socket.socket and len(args) > 1) else (args[:1] or "")
            attempts.append(f"{label}{target!r}")
            raise EgressAttempted(f"network egress attempted: {label}{target!r}")

        saved.append((owner, attr, original))
        setattr(owner, attr, _blocked)

    _install("socket.connect", socket.socket, "connect")
    _install("socket.connect_ex", socket.socket, "connect_ex")
    _install("socket.sendto", socket.socket, "sendto")
    _install("socket.create_connection", socket, "create_connection")
    _install("socket.getaddrinfo", socket, "getaddrinfo")
    _install("socket.gethostbyname", socket, "gethostbyname")
    try:
        yield attempts
    finally:
        for owner, attr, original in saved:
            setattr(owner, attr, original)


@dataclass(frozen=True)
class SentRequest:
    """One request as ``requests`` prepared it, captured below ``requests.get``."""

    method: str
    url: str
    headers: Mapping[str, str]
    body: Optional[object]
    allow_redirects: bool

    def as_text(self) -> str:
        """Everything that would have left this machine, as one lowercase string."""
        header_text = " ".join(f"{k}: {v}" for k, v in self.headers.items())
        return f"{self.method} {self.url} {header_text} {self.body or ''}".lower()


class _StubResponse:
    """The small ``requests.Response`` surface the clients actually use."""

    def __init__(self, text: str, status_code: int) -> None:
        self.text = text
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


@contextmanager
def capture_requests(
    body: str = "{}",
    status_code: int = 200,
    responder: Optional[Callable[[SentRequest], object]] = None,
) -> Iterator[list[SentRequest]]:
    """Capture every prepared request instead of sending it.

    Patches ``Session.send``, so URL building, headers, and redirect policy are
    the real ones. ``responder`` may return a custom stand-in response.
    """
    import requests

    sent: list[SentRequest] = []
    original = requests.sessions.Session.send

    def _send(self: object, request: Any, **kwargs: Any) -> object:
        captured = SentRequest(
            method=str(request.method),
            url=str(request.url),
            headers=dict(request.headers),
            body=request.body,
            allow_redirects=bool(kwargs.get("allow_redirects", True)),
        )
        sent.append(captured)
        if responder is not None:
            return responder(captured)
        return _StubResponse(body, status_code)

    requests.sessions.Session.send = _send  # type: ignore[method-assign] # test-only stub
    try:
        yield sent
    finally:
        requests.sessions.Session.send = original  # type: ignore[method-assign] # restore
