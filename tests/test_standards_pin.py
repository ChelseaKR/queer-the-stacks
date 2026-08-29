"""The portfolio-standards pin is recorded in the repo, and stays in lockstep.

``.github/workflows/standards.yml`` fetches the private
``ChelseaKR/portfolio-standards`` at a pinned ``ref:``, and carries the comment
"bump in lockstep with .standards-version". Two things were true before these
tests:

* ``.standards-version`` did not exist, and never had in this repository's
  history, while ``README.md`` and ``CONTRIBUTING.md`` both linked to it and
  told the reader that maintainer branches check the version recorded there.
* Nothing enforced the lockstep the comment describes, so the workflow's
  ``ref:`` and the recorded version could drift apart silently.

The first of those also broke the fork lane. GitHub withholds repository
secrets from forked pull requests by design, so a fork skips the deploy-key
checkout and the freshness gate, and its *only* remaining assertion is
``test -s .standards-version``. Against a repository that does not contain the
file, that assertion exits 1 every time: the ``standards`` check could not go
green on any forked pull request, for a reason that had nothing to do with the
missing credential.

These checks read two files and need no credential, no network, and no access
to the private policy repository, so they hold on a fork exactly as they hold
on a maintainer branch.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PIN_FILE = REPO_ROOT / ".standards-version"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "standards.yml"

#: The private policy repository the workflow pins. Named here so a rename
#: fails these tests loudly instead of making them silently scan for nothing.
STANDARDS_REPO = "ChelseaKR/portfolio-standards"

#: A ref the fetch step may pin: a tag, a branch, or a full commit SHA. Written
#: with explicit character classes rather than ``\w``/``\d`` so a look-alike
#: Unicode digit in a hand-edited ref cannot pass as ASCII.
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


def _read(path: Path) -> str:
    assert path.is_file(), f"{path.relative_to(REPO_ROOT)} is missing"
    return path.read_text(encoding="utf-8")


def _pinned_ref() -> str:
    """The ``ref:`` the standards workflow checks the policy repo out at.

    Scoped to the step that names :data:`STANDARDS_REPO`, and to that step's
    own ``with:`` block, so an unrelated ``ref:`` elsewhere in the workflow can
    never be mistaken for this one.
    """
    lines = _read(WORKFLOW).splitlines()
    repo_lines = [
        i for i, line in enumerate(lines) if line.strip() == f"repository: {STANDARDS_REPO}"
    ]
    assert len(repo_lines) == 1, (
        f"expected exactly one `repository: {STANDARDS_REPO}` line in "
        f"{WORKFLOW.name}, found {len(repo_lines)}"
    )
    start = repo_lines[0]
    indent = len(lines[start]) - len(lines[start].lstrip())
    refs: list[str] = []
    for line in lines[start + 1 :]:
        if not line.strip():
            continue
        # Leaving the `with:` mapping ends the step's own inputs.
        if len(line) - len(line.lstrip()) < indent:
            break
        key, _, value = line.strip().partition(":")
        if key == "ref":
            refs.append(value.split("#")[0].strip())
    assert len(refs) == 1, (
        f"expected exactly one `ref:` in the {STANDARDS_REPO} checkout step, found {refs}"
    )
    return refs[0]


def test_standards_version_is_recorded() -> None:
    """The file the fork lane asserts on, and the docs link to, exists.

    This is the same condition as the workflow's ``test -s
    .standards-version``, checked where a contributor can see it fail before
    pushing rather than only inside a lane that forks alone reach.
    """
    assert PIN_FILE.is_file(), (
        ".standards-version is missing. README.md and CONTRIBUTING.md link to "
        "it, and .github/workflows/standards.yml asserts it on every forked "
        "pull request; without it that lane cannot pass."
    )
    raw = PIN_FILE.read_text(encoding="utf-8")
    assert raw.strip(), ".standards-version is empty; `test -s` in the fork lane would fail"
    assert raw == raw.strip() + "\n", (
        ".standards-version must hold exactly one line with no leading or "
        f"trailing whitespace, got {raw!r}"
    )
    assert _REF.match(raw.strip()), (
        f".standards-version must be a git ref usable as a checkout `ref:`, got {raw.strip()!r}"
    )


def test_standards_version_matches_the_pinned_workflow_ref() -> None:
    """The lockstep the workflow comment promises, actually enforced.

    ``standards.yml`` says "bump in lockstep with .standards-version" next to
    its ``ref:``. Nothing made that true. Bumping either one alone now fails
    here, on forks and maintainer branches alike, because this reads the two
    files rather than the private repository they point at.
    """
    recorded = _read(PIN_FILE).strip()
    pinned = _pinned_ref()
    assert recorded == pinned, (
        f".standards-version records {recorded!r} but "
        f".github/workflows/standards.yml checks {STANDARDS_REPO} out at "
        f"{pinned!r}. They are documented as moving in lockstep; bump both."
    )


def test_fork_lane_still_asserts_the_recorded_pin() -> None:
    """The fork lane keeps an assertion, so it cannot degrade into an echo.

    A fork gets neither the deploy key nor the freshness gate, so if its step
    body were reduced to the explanatory ``echo`` alone, the ``standards``
    check would report success on a forked pull request having verified
    nothing at all.
    """
    workflow = _read(WORKFLOW)
    assert "test -s .standards-version" in workflow, (
        "the fork lane in standards.yml no longer asserts .standards-version, "
        "so the standards check would pass on a forked pull request without "
        "checking anything"
    )
