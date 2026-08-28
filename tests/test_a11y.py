"""Accessibility gate — every served document has zero mechanical violations."""

from __future__ import annotations

from pathlib import Path

from app.a11y_check import check_html, main
from app.render import render_dashboard
from app.server import _render_login_page
from app.view import demo_view

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


def _makefile_variables() -> dict[str, str]:
    """Expand the ``NAME := value`` assignments in the Makefile.

    Only the two forms this Makefile uses are handled: simple ``:=``
    assignment, and ``$(NAME)`` references to earlier assignments. Anything
    else is left as written, which would show up as an unexpanded ``$(`` in
    the value and fail the assertion that consumes it.
    """
    values: dict[str, str] = {}
    for line in (REPO_ROOT / "Makefile").read_text(encoding="utf-8").splitlines():
        if line.startswith(("\t", " ")) or ":=" not in line:
            continue
        name, _, raw = line.partition(":=")
        name = name.strip()
        if not name.replace("_", "").isalnum():
            continue
        expanded = raw.split("#")[0].strip()
        for known, value in values.items():
            expanded = expanded.replace(f"$({known})", value)
        values[name] = expanded
    return values


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

    variables = _makefile_variables()
    assert "A11Y_PAGES" in variables, "Makefile no longer defines A11Y_PAGES"
    scanned = set(variables["A11Y_PAGES"].split())
    assert scanned, "the a11y gate's page list is empty"
    assert not any("$(" in page for page in scanned), (
        f"A11Y_PAGES did not fully expand: {sorted(scanned)}"
    )

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
    variables = _makefile_variables()
    assert variables.get("A11Y_HTML") == "docs/audits/dashboard.html"
    assert variables.get("A11Y_PAGES", "").split() == [
        "docs/audits/dashboard.html",
        "docs/audits/login.html",
        "docs/audits/share.html",
    ]
