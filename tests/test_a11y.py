"""Accessibility gate — every served document has zero mechanical violations."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.a11y_check import check_html, main
from app.render import render_dashboard
from app.server import _render_login_page
from app.view import demo_view

from tests.makefilevars import makefile_list, makefile_variables

REPO_ROOT = Path(__file__).resolve().parent.parent


def _html(tmp_path: Path) -> str:
    view = demo_view(tmp_path)
    return render_dashboard(
        view.currently_reading,
        view.finished,
        view.stats,
        view.wrapped,
        view.recommendations,
        user=view.user,
    )


def test_demo_dashboard_has_zero_violations(tmp_path: Path) -> None:
    assert check_html(_html(tmp_path)) == []


def test_login_documents_have_zero_structural_violations() -> None:
    assert check_html(_render_login_page()) == []
    assert check_html(_render_login_page("Incorrect token.")) == []


def test_checker_catches_missing_landmarks() -> None:
    bad = "<!doctype html><html><head></head><body><p>hi</p></body></html>"
    violations = check_html(bad)
    assert any("lang" in v for v in violations)
    assert any("viewport" in v for v in violations)
    assert any("<h1>" in v or "h1" in v for v in violations)
    assert any("main" in v for v in violations)
    assert any("skip" in v for v in violations)


def test_checker_catches_table_without_caption() -> None:
    bad = (
        '<!doctype html><html lang="en"><head>'
        '<meta name="viewport" content="width=device-width"></head><body>'
        '<a class="skip" href="#main">skip</a><main id="main"><h1>T</h1>'
        "<table><tr><th>no scope</th></tr></table></main></body></html>"
    )
    violations = check_html(bad)
    assert any("caption" in v for v in violations)
    assert any("scope" in v for v in violations)


def test_checker_catches_heading_jump() -> None:
    bad = (
        '<!doctype html><html lang="en"><head>'
        '<meta name="viewport" content="x"></head><body>'
        '<a class="skip" href="#main">skip</a><main id="main"><h1>T</h1>'
        "<h4>jumped</h4></main></body></html>"
    )
    assert any("jump" in v for v in check_html(bad))


def test_main_passes_on_demo(tmp_path: Path) -> None:
    out = tmp_path / "dash.html"
    out.write_text(_html(tmp_path), encoding="utf-8")
    assert main([str(out)]) == 0


def test_main_fails_on_violations(tmp_path: Path) -> None:
    out = tmp_path / "bad.html"
    out.write_text("<html><body></body></html>", encoding="utf-8")
    assert main([str(out)]) == 1


def test_main_usage_without_args() -> None:
    assert main([]) == 2


# --- `main` reads every document it is handed, and says how many -------------
#
# It read `args[0]` and dropped the rest. Handed the four documents
# `A11Y_PAGES` names, it checked one, printed `a11y: 0 violations` and exited
# 0 — a green line over three unread files. The `make a11y` recipe loops one
# page at a time, so this was latent; the next line of that same recipe is
# `node scripts/a11y-browser-check.js $(A11Y_PAGES)`, which does take a list,
# and collapsing the loop to match would have quietly reduced the gate to its
# first page.


def _clean(tmp_path: Path, name: str) -> Path:
    out = tmp_path / name
    out.write_text(_html(tmp_path), encoding="utf-8")
    return out


def _broken(tmp_path: Path, name: str) -> Path:
    out = tmp_path / name
    out.write_text("<html><body></body></html>", encoding="utf-8")
    return out


def test_main_checks_every_file_it_is_handed_not_just_the_first(tmp_path: Path) -> None:
    """The defect, in the position it hid in: a violation after the first file.

    Reading only ``args[0]`` returns 0 here, because the first document is
    clean. The violation sits in the second, third and fourth arguments — the
    ones a single-file read never opens.
    """
    first_clean = _clean(tmp_path, "dashboard.html")
    for position in range(1, 4):
        paths = [first_clean, _clean(tmp_path, "a.html"), _clean(tmp_path, "b.html")]
        paths.insert(position, _broken(tmp_path, "bad.html"))
        assert main([str(p) for p in paths]) == 1, (
            f"a document with violations at argument {position} did not fail the "
            "gate; only the first path is being read"
        )


def test_main_reports_how_many_documents_it_read(capsys: pytest.CaptureFixture[str]) -> None:
    """The count is in the program's output, not only in the Makefile.

    ``a11y: 0 violations`` over one file and over four is the same sentence,
    which is precisely why nobody noticed it was one. The census is asserted
    against the real ``A11Y_PAGES`` set so that a page leaving the list changes
    a number a reader can see.
    """
    pages = makefile_list("A11Y_PAGES")
    assert len(pages) > 1, "A11Y_PAGES lists one page; this assertion proves nothing"

    assert main([str(REPO_ROOT / page) for page in pages]) == 0
    out = capsys.readouterr().out
    assert f"{len(pages)} file(s) checked" in out, (
        f"the passing line was {out.strip()!r}; it must state how many documents "
        "it read, or a run over one page is indistinguishable from a run over all"
    )


def test_main_refuses_a_file_it_cannot_read(tmp_path: Path) -> None:
    """An unreadable document is not a document with no violations.

    Every path is read before anything is reported, so a run missing one of its
    inputs refuses rather than passing on the ones it managed to open.
    """
    assert main([str(_clean(tmp_path, "ok.html")), str(tmp_path / "absent.html")]) == 2


# --- The gate's page list is itself asserted ---------------------------------
#
# A gate cannot fail on a page it never loads. `make a11y` scans exactly the
# files `app.build_static.build_all()` writes, so the risk is not a broken check
# but a template that never enters the list. These two tests make that a build
# failure instead of a silent hole.

#: Each HTML route, and the audited document that covers its template. `/browse`
#: renders the same `app.view.render_view` output as `/` with a filtered
#: library, so `dashboard.html` covers it; add an entry here (and a page to
#: `build_all`) when a new HTML route appears.
HTML_ROUTE_COVERAGE: dict[str, str] = {
    "/": "docs/audits/dashboard.html",
    "/browse": "docs/audits/dashboard.html",
    "/login": "docs/audits/login.html",
    "/share": "docs/audits/share.html",
    # NOT dashboard.html: /search can render a status banner the dashboard
    # template never emits, so it needs a document of its own or that banner
    # goes unaudited. See app.build_static.build_search.
    "/search": "docs/audits/search.html",
}


def test_every_html_route_is_covered_by_an_audited_document() -> None:
    from app import server
    from fastapi.responses import HTMLResponse

    app = server.create_app()
    html_routes = {
        route.path for route in app.routes if getattr(route, "response_class", None) is HTMLResponse
    }

    assert html_routes == set(HTML_ROUTE_COVERAGE), (
        "an HTML route is not mapped to an audited document; add it to "
        "app.build_static.build_all() and to HTML_ROUTE_COVERAGE"
    )


def test_build_all_writes_every_audited_document(tmp_path: Path) -> None:
    """``build_all`` itself is called, not the three builders it happens to call.

    The previous version hand-called ``build``, ``build_login`` and
    ``build_share`` and never invoked ``build_all``. That made the one thing
    the function exists to guarantee untested: change it to
    ``return build(), build_login()`` and this stayed green. ``make a11y``
    would then stop regenerating ``docs/audits/share.html`` — but that file is
    committed, so the stale copy still satisfies the Makefile's ``test -s``
    check and the share page silently goes unaudited forever. That is exactly
    the regression ``app/build_static.py``'s docstring says the design exists
    to prevent.
    """
    from app import build_static

    written = build_static.build_all(tmp_path)
    expected_names = {Path(p).name for p in HTML_ROUTE_COVERAGE.values()}

    assert {p.name for p in written} == expected_names, (
        f"build_all() wrote {sorted(p.name for p in written)}, but the audited "
        f"document set is {sorted(expected_names)}"
    )
    assert len(written) == len(expected_names), (
        f"build_all() returned {len(written)} paths for {len(expected_names)} "
        "documents; a duplicate would hide a missing one"
    )
    for path in written:
        assert path.is_file() and path.stat().st_size > 0
        assert check_html(path.read_text(encoding="utf-8")) == [], path.name


def test_the_makefile_scans_exactly_the_documents_build_all_writes(tmp_path: Path) -> None:
    """Tie the gate's page list to the generator, so neither can drift alone.

    ``Makefile``'s ``A11Y_PAGES`` is a hand-maintained literal. Nothing
    compared it to ``build_static.build_all()`` or to ``HTML_ROUTE_COVERAGE``,
    so a fourth user-facing document could be added to two of the three and the
    a11y gate would simply never load it — no failure anywhere, because the
    Makefile's own Layer 0 guard only checks that the pages it *does* list are
    present and non-empty.
    """
    from app import build_static

    scanned = set(makefile_list("A11Y_PAGES"))

    generated = {
        (build_static.DEFAULT_OUT_DIR / path.name).as_posix()
        for path in build_static.build_all(tmp_path)
    }
    assert scanned == generated, (
        f"the a11y gate scans {sorted(scanned)} but build_all writes "
        f"{sorted(generated)}. A page in one list and not the other is either "
        "never audited, or audited as a stale committed file."
    )
    assert scanned == {str(path) for path in HTML_ROUTE_COVERAGE.values()}, (
        f"the a11y gate scans {sorted(scanned)} but HTML_ROUTE_COVERAGE maps "
        f"routes to {sorted(str(p) for p in HTML_ROUTE_COVERAGE.values())}"
    )


def test_the_makefile_variable_expander_works() -> None:
    """The expander is measured, so an empty result cannot pass as agreement."""
    assert makefile_variables().get("A11Y_HTML") == "docs/audits/dashboard.html"
    assert makefile_list("A11Y_PAGES") == [
        "docs/audits/dashboard.html",
        "docs/audits/login.html",
        "docs/audits/share.html",
        "docs/audits/search.html",
    ]
