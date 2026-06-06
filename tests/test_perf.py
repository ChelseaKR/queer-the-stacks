"""Performance budget (Quality §2): the dashboard render stays well under budget.

A full Lighthouse/k6 pass is review-gated (needs a browser/load harness); this is
the mechanical, CI-runnable floor: building + rendering the whole demo dashboard
must complete comfortably within a generous budget, so a regression that makes
rendering pathologically slow fails the build.
"""

from __future__ import annotations

import time
from pathlib import Path

from app.view import demo_view, render_view

#: Generous ceiling — the pure render is milliseconds; this only catches blowups.
RENDER_BUDGET_S = 1.0
PIPELINE_BUDGET_S = 5.0


def test_render_within_budget(tmp_path: Path) -> None:
    view = demo_view(tmp_path)  # warm: build the view first
    start = time.perf_counter()
    for _ in range(20):
        html = render_view(view)
    elapsed = (time.perf_counter() - start) / 20
    assert html  # non-empty
    assert elapsed < RENDER_BUDGET_S, f"render took {elapsed:.3f}s (budget {RENDER_BUDGET_S}s)"


def test_full_pipeline_within_budget(tmp_path: Path) -> None:
    start = time.perf_counter()
    view = demo_view(tmp_path)
    render_view(view)
    elapsed = time.perf_counter() - start
    assert elapsed < PIPELINE_BUDGET_S, (
        f"pipeline took {elapsed:.3f}s (budget {PIPELINE_BUDGET_S}s)"
    )
