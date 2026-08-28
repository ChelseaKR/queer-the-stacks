"""Read the Makefile's ``:=`` variables, so tests can check the gate's own lists.

Several merge-blocking gates are driven by a hand-maintained list in the
``Makefile`` — ``A11Y_PAGES``, ``MARKER_ROOTS`` — and a list that silently stops
matching reality is a gate that silently stops covering something. These helpers
let a test compare such a list against what the code actually produces.

Only the two forms this Makefile uses are handled: simple ``:=`` assignment, and
``$(NAME)`` references to earlier assignments. Anything else is left as written,
which surfaces as an unexpanded ``$(`` in the value and fails the assertion that
consumes it rather than passing quietly. A ``make`` subprocess would be the
authoritative expander, but this repository's test suite deliberately shells out
nowhere, and ``ruff``'s bandit subset flags ``subprocess`` besides.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = REPO_ROOT / "Makefile"


def makefile_variables(path: Path | None = None) -> dict[str, str]:
    """Expand every ``NAME := value`` assignment in the Makefile, in order."""
    source = (path or MAKEFILE).read_text(encoding="utf-8")
    values: dict[str, str] = {}
    for line in source.splitlines():
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


def makefile_list(name: str, path: Path | None = None) -> list[str]:
    """One whitespace-separated Makefile variable, fully expanded.

    Raises :class:`AssertionError` rather than returning a half-expanded value,
    so a caller can never compare against ``$(SOMETHING)`` and call it a match.
    """
    variables = makefile_variables(path)
    assert name in variables, f"the Makefile no longer defines {name}"
    value = variables[name]
    assert "$(" not in value, f"{name} did not fully expand: {value!r}"
    items = value.split()
    assert items, f"{name} is empty"
    return items
