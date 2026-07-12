"""Load smoke (Quality §2, merge-blocking): p95 < 500ms on the dashboard route.

Not part of the pytest suite — this is a Locust scenario invoked headlessly by
``scripts/perf-smoke.sh`` (``make perf-load``) against a real, locally-running
instance of the app in demo mode. It reuses the existing demo-auth path
(``STACKS_DEMO=1`` -> ``app.auth.DEMO_TOKEN``) so no secrets are needed and no
real reading data is ever touched.

Kept intentionally small: constant load, two read-only routes, no login flow
(auth is a static bearer header, not a session).
"""

from __future__ import annotations

from locust import HttpUser, between, task

#: Matches app.auth.DEMO_TOKEN, valid only when the server under test was
#: started with STACKS_DEMO=1 (see scripts/perf-smoke.sh).
DEMO_TOKEN = "demo-token"  # noqa: S105 - not a secret; demo-mode fixed token


class DashboardUser(HttpUser):
    """Simulated reader loading the dashboard and hitting the readiness probe."""

    # Short, near-continuous think time — this is a smoke test for latency
    # under light constant load, not a capacity/stress test.
    wait_time = between(0.1, 0.5)

    def on_start(self) -> None:
        self.client.headers.update({"Authorization": f"Bearer {DEMO_TOKEN}"})

    @task(3)
    def dashboard(self) -> None:
        self.client.get("/", name="/")

    @task(1)
    def readyz(self) -> None:
        self.client.get("/readyz", name="/readyz")
