"""Reproducibility guardrail — deterministic recommendations + render (merge-blocking).

Same library in, byte-identical documents out. This guards against hidden
nondeterminism (dict ordering, unstable sorts, wall-clock reads) creeping into
the recommender, the stats, or the renderer.

**It has to compare the document the app serves.** The previous version called
``render_dashboard`` directly with five of its twenty-three arguments, letting
the other eighteen default. Everything they carry — the goals section, the
library table, the data-status panel, the diversity report, the near-miss
shelf, the forecasts, the authored lists, the browse filter state — was absent
from the comparison, which covered 27,197 of the served page's 37,315 bytes:
72.9%. Set-iteration order introduced into any of those sections produced an
unstable dashboard with this test green.

``render_view`` is what ``app/server.py`` and ``app/build_static.py`` both call,
so it is what gets compared now, alongside the share page — the one document
designed to leave the instance, and therefore the one whose byte-stability a
reader might rely on.

**Two renders in one process cannot establish build reproducibility.** Python
randomizes string hashing per process, so set-iteration order is *stable within*
a run and varies *between* runs. Both the old and the new same-process
comparisons therefore pass with real set-iteration nondeterminism in the
renderer — measured, not assumed: injecting ``set(...)`` into the diversity
coverage table gives three different document digests under three
``PYTHONHASHSEED`` values while every same-process assertion stays green.

The cross-process anchor is the committed artifact. ``docs/audits/*.html`` are
written by ``make a11y`` in an earlier, separate process, so comparing today's
in-process render against them is a comparison across two process lifetimes and
two hash seeds. That also makes the committed artifacts provably current
instead of merely present, which is what the accessibility gate needs of them.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from app.share import build_share_cards, render_share_page
from app.view import DashboardView, demo_view, render_view


def _share(view: DashboardView) -> str:
    return render_share_page(
        build_share_cards(view), user=view.user, fixture_states=view.fixture_states
    )


def test_two_builds_of_the_served_dashboard_are_byte_identical(tmp_path: Path) -> None:
    assert render_view(demo_view(tmp_path / "a")) == render_view(demo_view(tmp_path / "b"))


def test_two_builds_of_the_share_page_are_byte_identical(tmp_path: Path) -> None:
    assert _share(demo_view(tmp_path / "a")) == _share(demo_view(tmp_path / "b"))


def test_the_comparison_covers_more_than_the_old_five_argument_call(tmp_path: Path) -> None:
    """Non-vacuity: pin the gap, so it cannot silently reopen.

    A renderer that returned ``""`` on both builds would satisfy the equalities
    above. This asserts the compared string is a complete document and that it
    is strictly larger than the five-argument call the old test used, with at
    least one section that call could not produce at all.
    """
    from app.render import render_dashboard

    view = demo_view(tmp_path)
    html = render_view(view)
    narrow = render_dashboard(
        view.currently_reading,
        view.finished,
        view.stats,
        view.wrapped,
        view.recommendations,
        user=view.user,
    )

    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    assert len(html) > len(narrow), (
        "the served document is no longer larger than the five-argument render; "
        "either the extra sections stopped rendering or render_view changed shape"
    )
    # The diversity report is reachable only through render_view's `diversity=`
    # argument, so its presence proves the wider call is what is being compared.
    assert "Reading diversity" in html
    assert "Reading diversity" not in narrow


def test_the_served_dashboard_does_not_read_the_wall_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same library renders the same bytes whatever ``time.time`` says.

    Scoped precisely to ``time.time``: a renderer reaching for
    ``datetime.now()`` instead would not be caught here, and this test does not
    claim otherwise. What it does establish is that the reproducibility
    docstring's "wall-clock reads" is a checked property rather than a hope —
    the two builds above run milliseconds apart in one process, so a clock read
    at second or day granularity would return the same value to both and the
    equality would hold regardless.
    """
    baseline = render_view(demo_view(tmp_path / "now"))
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 400 * 24 * 3600)
    assert render_view(demo_view(tmp_path / "later")) == baseline


#: Documents written by ``make a11y`` (``python -m app.build_static``) and
#: committed. Each was produced by a different process than the one running
#: this test, which is the property the same-process comparisons cannot have.
COMMITTED_ARTIFACTS = {
    "docs/audits/dashboard.html": "the dashboard at GET /",
    "docs/audits/share.html": "the share page at GET /share",
    "docs/audits/login.html": "the sign-in page at GET /login",
}

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_the_render_matches_the_committed_artifact_from_another_process(
    tmp_path: Path,
) -> None:
    """Byte-identical across process lifetimes, not merely within one.

    Python randomizes string hashing per process, so set-iteration order is
    stable inside a run and varies between runs. Every same-process assertion
    above therefore passes even when the renderer genuinely is order-dependent.
    Comparing against artifacts a previous process wrote closes that.

    If this fails after a deliberate render change, the fix is `make a11y`
    (or `make audit`) and committing the regenerated artifacts, which
    `DEFINITION_OF_DONE.md` already asks for. If it fails without a render
    change, the renderer has become order-dependent.
    """
    from app.server import _render_login_page

    view = demo_view(tmp_path)
    produced = {
        "docs/audits/dashboard.html": render_view(view),
        "docs/audits/share.html": _share(view),
        "docs/audits/login.html": _render_login_page(),
    }
    assert set(produced) == set(COMMITTED_ARTIFACTS)

    for relative, description in sorted(COMMITTED_ARTIFACTS.items()):
        path = REPO_ROOT / relative
        assert path.is_file(), f"{relative} is missing; run `make a11y` to write it"
        committed = path.read_text(encoding="utf-8")
        assert committed, f"{relative} is empty"
        assert produced[relative] == committed, (
            f"{relative} ({description}) does not match what the renderer produces "
            "now. Either the renderer became order-dependent between processes, "
            "or a deliberate render change landed without regenerating the "
            "committed artifact — run `make a11y` and commit the result."
        )


def test_recommendation_order_stable(tmp_path: Path) -> None:
    a = [r.book.book_id for r in demo_view(tmp_path / "a").recommendations]
    b = [r.book.book_id for r in demo_view(tmp_path / "b").recommendations]
    assert a == b
    assert a  # non-empty
