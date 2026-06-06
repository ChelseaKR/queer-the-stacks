"""Reproducibility guardrail — deterministic recommendations + render (merge-blocking).

Same library in, byte-identical dashboard out. This guards against any hidden
nondeterminism (dict ordering, unstable sorts, wall-clock reads) creeping into
the recommender, the stats, or the renderer.
"""

from __future__ import annotations

from pathlib import Path

from app.render import render_dashboard
from app.view import demo_view


def _render(view: object) -> str:
    v = view  # type: ignore[assignment]
    return render_dashboard(
        v.currently_reading,  # type: ignore[attr-defined]
        v.finished,  # type: ignore[attr-defined]
        v.stats,  # type: ignore[attr-defined]
        v.wrapped,  # type: ignore[attr-defined]
        v.recommendations,  # type: ignore[attr-defined]
        user=v.user,  # type: ignore[attr-defined]
    )


def test_two_builds_are_byte_identical(tmp_path: Path) -> None:
    view_a = demo_view(tmp_path / "a")
    view_b = demo_view(tmp_path / "b")
    assert _render(view_a) == _render(view_b)


def test_recommendation_order_stable(tmp_path: Path) -> None:
    a = [r.book.book_id for r in demo_view(tmp_path / "a").recommendations]
    b = [r.book.book_id for r in demo_view(tmp_path / "b").recommendations]
    assert a == b
    assert a  # non-empty
