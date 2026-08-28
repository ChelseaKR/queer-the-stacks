"""The gates' hand-maintained lists still match what exists.

A merge-blocking gate driven by a literal list is only as complete as that
list. Nothing fails when a new directory is simply not added to it: the gate
runs, finds nothing in the places it was told about, and reports success. This
is the same shape as the accessibility gate's page list (see
``tests/test_a11y.py``), applied to the marker-hygiene scan.

``Makefile``'s ``marker-hygiene`` target refuses to run when one of its scan
roots is missing or when the roots hold no Python files, so a *renamed*
directory now fails there. What it cannot see is a directory that was never
listed, which is what this file covers.
"""

from __future__ import annotations

from pathlib import Path

import app
import ingest
import recommender

from tests.makefilevars import makefile_list

REPO_ROOT = Path(__file__).resolve().parent.parent


def _first_party_roots() -> set[str]:
    """Every directory holding first-party Python, plus the test suite.

    Derived from the imported packages rather than listed here, so this side of
    the comparison cannot go stale in the same way the Makefile's side could.
    """
    packages = {
        Path(pkg.__file__).parent.resolve().relative_to(REPO_ROOT).as_posix()
        for pkg in (ingest, recommender, app)
        if pkg.__file__
    }
    return packages | {"tests"}


def test_marker_hygiene_scans_every_first_party_root() -> None:
    """The scan covers each package that exists, and names no root that does not."""
    scanned = set(makefile_list("MARKER_ROOTS"))
    expected = _first_party_roots()
    assert scanned == expected, (
        f"marker-hygiene scans {sorted(scanned)} but the first-party roots are "
        f"{sorted(expected)}. A package missing from MARKER_ROOTS is never "
        "scanned for bare work markers or un-coded suppressions, and nothing "
        "else would report it."
    )


def test_every_marker_root_exists_and_holds_python() -> None:
    """Non-vacuity: a root that is gone would make its share of the scan empty."""
    for root in makefile_list("MARKER_ROOTS"):
        directory = REPO_ROOT / root
        assert directory.is_dir(), f"MARKER_ROOTS names {root!r}, which is not a directory"
        assert any(directory.rglob("*.py")), f"{root!r} holds no Python files to scan"
