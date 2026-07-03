"""KOReader cross-device progress, via the KOReader sync protocol.

Two implementations of :class:`ProgressSource`:

* :class:`KosyncClient` — the live HTTP client for a KOReader sync server
  (``sync.koreader.rocks`` or a self-hosted one). It sends only the user's own
  auth header and reads back the user's *own* progress — a round-trip of the
  user's data to the user's server, never a third party. Request-building and
  status handling are covered by recorded-cassette contract tests (network
  stubbed); real connectivity is integration-verified.
* :class:`FixtureKosync` — an offline, deterministic source built from a dict.
  Used by every test and by demo mode, so the whole system runs with no network.

Privacy note: this is the *only* place reading-progress data touches the network,
and it goes to the user's own sync endpoint. The no-egress test confines network
imports to this module and the catalog client.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from ingest.models import DeviceProgress

DEFAULT_SYNC_HOST = "https://sync.koreader.rocks"


@runtime_checkable
class ProgressSource(Protocol):
    """The cross-device-progress interface the unifier depends on."""

    def progress_for(self, document: str) -> Optional[DeviceProgress]: ...


class FixtureKosync:
    """A deterministic, offline :class:`ProgressSource` built from plain data."""

    def __init__(self, progress: dict[str, DeviceProgress]) -> None:
        self._progress = dict(progress)

    def progress_for(self, document: str) -> Optional[DeviceProgress]:
        return self._progress.get(document)


def parse_progress(payload: object) -> Optional[DeviceProgress]:
    """Parse a KOReader sync ``/syncs/progress`` response, validating shape.

    Returns ``None`` for an empty / "no progress yet" response.
    """
    if not isinstance(payload, dict):
        raise ValueError("progress payload must be an object")
    document = str(payload.get("document", "")).strip()
    if not document:
        return None
    try:
        pct = float(payload.get("percentage", 0.0))
    except (TypeError, ValueError):
        pct = 0.0
    pct = max(0.0, min(1.0, pct))
    try:
        ts = int(payload.get("timestamp", 0))
    except (TypeError, ValueError):
        ts = 0
    return DeviceProgress(
        document=document,
        percentage=pct,
        device=str(payload.get("device", "unknown")).strip() or "unknown",
        timestamp=ts,
    )


class KosyncClient:
    """Live KOReader sync client, exercised via recorded-cassette contract tests."""

    def __init__(
        self,
        username: str,
        userkey_md5: str,
        host: str = DEFAULT_SYNC_HOST,
        timeout: int = 15,
    ) -> None:
        if not username or not userkey_md5:
            raise ValueError("a kosync username and key are required")
        self.username = username
        self.userkey_md5 = userkey_md5
        self.host = host.rstrip("/")
        self.timeout = timeout

    def progress_for(self, document: str) -> Optional[DeviceProgress]:
        import json

        import requests

        url = f"{self.host}/syncs/progress/{document}"
        headers = {
            "x-auth-user": self.username,
            "x-auth-key": self.userkey_md5,
            "accept": "application/vnd.koreader.v1+json",
        }
        resp = requests.get(url, headers=headers, timeout=self.timeout)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return parse_progress(json.loads(resp.text))


def userkey(password: str) -> str:
    """Derive the kosync auth key (md5 of the password), as KOReader does.

    md5 here is the sync protocol's transport convention, not a security control;
    the connection itself is TLS. The user's password is never stored — only this
    derived key, held in the environment.
    """
    import hashlib

    return hashlib.md5(password.encode("utf-8")).hexdigest()  # noqa: S324
