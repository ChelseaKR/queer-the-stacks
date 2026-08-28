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


def makefile_recipe(target: str, path: Path | None = None) -> str:
    """The recipe body of one Makefile target, tabs stripped, as a single string.

    Some of what keeps a gate able to fail lives in the recipe rather than in a
    variable: ``marker-hygiene`` is only honest because it inspects each grep's
    exit code instead of discarding it. A test can assert that here, so removing
    the discipline is a test failure rather than a silent return to a scan that
    reports success having read nothing.
    """
    lines = (path or MAKEFILE).read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(lines) if line.split("#")[0].rstrip() == f"{target}:"]
    assert len(starts) == 1, f"expected exactly one `{target}:` recipe, found {len(starts)}"
    body: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if line.startswith("\t"):
            body.append(line[1:])
            continue
        if not line.strip() or line.startswith("#"):
            continue
        break
    assert body, f"the {target} target has an empty recipe"
    return "\n".join(body)


def makefile_prerequisites(target: str, path: Path | None = None) -> list[str]:
    """The prerequisites of one Makefile target, in order, comments stripped.

    ``verify`` is nothing but its prerequisite list: drop a stage from it and
    ``make verify`` still runs to completion and still prints that every gate is
    green, having skipped one. Reading the list back lets a test tie it to the
    stages CI runs.
    """
    lines = (path or MAKEFILE).read_text(encoding="utf-8").splitlines()
    matches = [line for line in lines if line.startswith(f"{target}:")]
    assert len(matches) == 1, f"expected exactly one `{target}:` rule, found {len(matches)}"
    _, _, rest = matches[0].partition(":")
    prerequisites = rest.split("##")[0].split("#")[0].split()
    assert prerequisites, f"the {target} target has no prerequisites"
    return prerequisites
