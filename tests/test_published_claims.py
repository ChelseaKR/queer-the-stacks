"""Claims published in the docs are derived from the tree, not transcribed into it.

``tests/test_gate_lists.py`` guards the gates' own hand-maintained lists. This
file guards the other direction: the sentences the README and the audit docs
publish *about* those gates. A number written into prose has no way to notice
that the thing it counts has changed, and this repository had accumulated a run
of them:

* ``README.md`` said "3 workflows" while ``.github/workflows/`` held seven, and
  had held more than three since before that sentence was written.
* It said all of them were ``permissions: contents: read`` while ``scorecard.yml``
  declares ``read-all`` and several release jobs elevate to write scopes.
* It said ``make verify`` was "identical locally and in CI" while the
  ``Makefile``'s own header, four lines from the top, documents the two stages
  ``ci.yml`` runs that ``verify`` does not.
* It said the Trivy container scan was merge-blocking. It is path-filtered to
  the image inputs, so on a typical pull request it does not even start.
* It said the accessibility gate covered "dashboard + login" for the two weeks
  after a third page joined ``A11Y_PAGES``.
* Two audit docs written in the same pass gave two different test-file counts
  for the same tree, so at least one of them was wrong the day it was committed.

Each of those was true once. None of them had anything that could fail when it
stopped being true, which is the defect: a stale figure in a published document
reads exactly like a fresh one. So every check below re-derives its figure from
the artifact that decides it — the workflow directory, the ``Makefile``,
``pyproject.toml``, coverage's own configuration — and compares the document
against that. Correcting a literal only resets the clock; deriving it stops the
clock.

Where a figure is not worth deriving — a test count in a forward-looking
roadmap — the fix was to delete it rather than to refresh it, and the deletion
says so in place.

One claim in this area stays ungated on purpose. Which status checks the
``protect-main`` ruleset *requires* lives in GitHub's settings, not in the tree,
and this suite makes no network calls; it is recorded in
``.github/rulesets/README.md`` with the command that establishes it instead.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from tests.makefilevars import makefile_list, makefile_prerequisites

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
CI_WORKFLOW = WORKFLOW_DIR / "ci.yml"
CONTAINER_SCAN = WORKFLOW_DIR / "container-scan.yml"
ROADMAP = REPO_ROOT / "docs" / "ROADMAP.md"
RESPONSIBLE_TECH = REPO_ROOT / "docs" / "RESPONSIBLE-TECH-AUDITS.md"

#: Directories holding nothing this repository authored.
_NOT_OURS = frozenset({".git", ".venv", "node_modules", ".ruff_cache", ".pytest_cache", "htmlcov"})


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _workflows() -> list[Path]:
    """Every workflow file GitHub would run, derived from the directory."""
    found = sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))
    assert found, "no workflow files found; every claim below would pass vacuously"
    return found


def _authored_markdown() -> list[Path]:
    """Markdown someone in this repository wrote, excluding vendored trees."""
    found = [
        path
        for path in sorted(REPO_ROOT.rglob("*.md"))
        if not _NOT_OURS.intersection(path.relative_to(REPO_ROOT).parts)
    ]
    assert found, "no authored markdown found; the doc checks would pass vacuously"
    return found


def _table_row(text: str, label: str) -> str:
    """The third cell of the Standards-table row whose first cell is ``label``."""
    row = re.search(rf"\|\s*{re.escape(label)}\s*\|[^|]*\|([^|]*)\|", text)
    assert row, f"the README no longer has a {label!r} row"
    return row.group(1)


# --- The CI/CD row: workflow count, privilege, and pinning -------------------


def test_readme_states_the_number_of_workflows_that_exist() -> None:
    """The count in the Standards table is compared against the directory.

    It said "3 workflows" against a directory of seven. Adding a workflow is
    exactly the moment nobody re-reads the README, so the number has to be
    checked by something that runs on every merge.
    """
    names = [path.name for path in _workflows()]
    stated = re.search(r"([0-9]+) workflows", _table_row(_read(README), "CI/CD"))
    assert stated, "the README's CI/CD row no longer states a workflow count"
    assert int(stated.group(1)) == len(names), (
        f"the README's CI/CD row claims {stated.group(1)} workflows; "
        f".github/workflows/ holds {len(names)}: {names}"
    )


def _top_level_permission_scopes(source: str) -> list[str]:
    """The scopes the workflow-level ``permissions:`` key grants, as written.

    Only the top level is read: a line with no leading whitespace starts a
    top-level key, so a job's indented ``permissions:`` cannot be mistaken for
    the workflow's. ``permissions: read-all`` comes back as ``["read-all"]``,
    a block of ``contents: read`` as ``["contents: read"]``, and a workflow
    declaring nothing as ``[]``.
    """
    lines = source.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("permissions:"):
            continue
        inline = line.removeprefix("permissions:").split("#")[0].strip()
        if inline:
            return [inline]
        scopes = []
        for following in lines[index + 1 :]:
            if not following.strip():
                continue
            if not following.startswith((" ", "\t")):
                break
            scopes.append(following.split("#")[0].strip())
        return scopes
    return []


def _not_least_privilege() -> set[str]:
    """Workflows whose top-level permissions are not exactly ``contents: read``."""
    return {
        path.name
        for path in _workflows()
        if _top_level_permission_scopes(_read(path)) != ["contents: read"]
    }


def test_readme_names_every_workflow_that_is_not_least_privilege() -> None:
    """ "All least-privilege" was a claim about seven files, checked against none.

    ``scorecard.yml`` grants ``read-all`` at the workflow level because the
    OpenSSF scanner reads repository settings a build does not. That is a
    defensible exception, and it is now a named one. Both halves are derived, so
    the disclosure cannot outlive the thing it discloses: a second workflow
    acquiring a broader grant fails here until the README says so, and
    ``scorecard.yml`` narrowing back to ``contents: read`` fails here too,
    because the count of least-privilege workflows moves with it.
    """
    row = _table_row(_read(README), "CI/CD")
    unusual = _not_least_privilege()
    least_privilege = len(_workflows()) - len(unusual)
    stated = re.search(r"([0-9]+) of them declare `permissions: contents: read`", row)
    assert stated, "the README's CI/CD row no longer states how many workflows are least-privilege"
    assert int(stated.group(1)) == least_privilege, (
        f"the README says {stated.group(1)} workflows declare top-level "
        f"`permissions: contents: read`; {least_privilege} of "
        f"{len(_workflows())} do. The exceptions are {sorted(unusual)}."
    )
    missing = sorted(name for name in unusual if name not in row)
    assert missing == [], (
        f"the README's CI/CD row does not name {missing}, whose top-level "
        "permissions are not `contents: read`"
    )


def test_every_workflow_action_reference_is_sha_pinned() -> None:
    """The README's pinning claim is made true here rather than merely asserted.

    A tag is a moving target an upstream account can repoint. This was the one
    half of the CI/CD row that was accurate when audited, and it stays accurate
    because an unpinned ``uses:`` fails this test rather than quietly
    contradicting the sentence.
    """
    unpinned: list[str] = []
    total = 0
    for path in _workflows():
        for number, line in enumerate(_read(path).splitlines(), 1):
            stripped = line.strip().removeprefix("- ")
            if not stripped.startswith("uses:"):
                continue
            total += 1
            reference = stripped.split("uses:", 1)[1].split("#")[0].strip()
            if not re.fullmatch(r"[^@]+@[0-9a-f]{40}", reference):
                unpinned.append(f"{path.name}:{number} {reference}")
    assert total, "no `uses:` found in any workflow; this check would pass vacuously"
    assert unpinned == [], f"these action references are not SHA-pinned: {unpinned}"


# --- The Quality & Metrics row: what `make verify` actually runs -------------


def _ci_stages() -> set[str]:
    """Every ``make <target>`` step ``ci.yml`` runs."""
    stages = set(re.findall(r"^\s*run: make ([a-z0-9-]+)$", _read(CI_WORKFLOW), re.MULTILINE))
    assert stages, "no `run: make <target>` steps found in ci.yml"
    return stages


def test_readme_lists_the_verify_stages_the_makefile_runs() -> None:
    """The arrow list in the Standards table is the Makefile's prerequisite list.

    ``make verify`` is nothing but that list, so a stage dropped from it is a
    gate that stops running while both the Makefile and this README still say it
    does.
    """
    stated = re.search(r"`make verify` = ([^.|]+)", _read(README))
    assert stated, "the README no longer spells out the `make verify` stage list"
    listed = [part.strip().strip("`") for part in stated.group(1).split("→")]
    assert listed == makefile_prerequisites("verify"), (
        f"the README lists the verify stages as {listed}; the Makefile runs "
        f"{makefile_prerequisites('verify')}"
    )


def test_readme_names_every_ci_stage_that_verify_skips() -> None:
    """ "Identical locally and in CI" was contradicted by the Makefile's own header.

    ``ci.yml`` runs ``perf-load`` and ``lighthouse`` unconditionally and
    ``verify`` does not, because both need a booted server or a downloaded
    Chromium. The difference is real and documented in three other places; the
    README claimed there was none. Deriving the gap means a future stage added
    to CI but not to ``verify`` fails here until the README admits it.
    """
    skipped = _ci_stages() - set(makefile_prerequisites("verify"))
    readme = _read(README)
    unmentioned = sorted(stage for stage in skipped if f"`{stage}`" not in readme)
    assert unmentioned == [], (
        f"ci.yml runs {sorted(skipped)} that `make verify` does not, and the "
        f"README does not name {unmentioned}. A reader told the two are "
        "identical will not run the missing gate."
    )
    assert "identical locally and in CI" not in readme, (
        "the README claims local and CI runs are identical while ci.yml runs "
        f"{sorted(skipped)} that `make verify` does not"
    )


def test_readme_states_the_coverage_floor_that_pyproject_configures() -> None:
    """The floor is a combined line-and-branch total, and the README said branch.

    ``--cov-fail-under`` is compared against coverage.py's total, which with
    ``branch = true`` counts branch outcomes alongside statements. The floor is
    met on either reading, so this was imprecise rather than false — but a
    reader budgeting against "85% branch coverage" is reading a number that is
    measured nowhere.
    """
    ini = tomllib.loads(_read(PYPROJECT))["tool"]["pytest"]["ini_options"]
    floors = [opt for opt in ini["addopts"] if opt.startswith("--cov-fail-under=")]
    assert len(floors) == 1, f"expected exactly one coverage floor in addopts, found {floors}"
    readme = _read(README)
    assert f"`{floors[0]}`" in readme, (
        f"the README does not state the configured coverage floor {floors[0]!r}"
    )
    assert "branch coverage" not in readme, (
        "the README describes the floor as branch coverage; --cov-fail-under is "
        "compared against coverage.py's combined line-and-branch total"
    )


# --- The Security row: which scans actually block a merge --------------------


def _pull_request_trigger(source: str) -> str:
    """The ``pull_request:`` trigger block of a workflow, as written."""
    lines = source.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "pull_request:" or not line.startswith(" "):
            continue
        indent = len(line) - len(line.lstrip())
        block = [line]
        for following in lines[index + 1 :]:
            if not following.strip():
                continue
            if len(following) - len(following.lstrip()) <= indent:
                break
            block.append(following)
        return "\n".join(block)
    return ""


def test_the_container_scan_is_described_as_the_path_filtered_gate_it_is() -> None:
    """The Trivy scan was published as merge-blocking. It is not, twice over.

    It is not one of the ``protect-main`` ruleset's required status checks, and
    it is path-filtered to ``Dockerfile``, ``.dockerignore``, ``pyproject.toml``,
    ``uv.lock`` and its own file, so on a pull request touching none of those it
    never starts and has nothing to block with. The required-check list lives in
    GitHub's settings and this suite makes no network calls, so it is recorded
    in ``.github/rulesets/README.md`` instead; the half that *is* derivable is
    the path filter, asserted here. Removing the filter — which would make the
    scan run on every pull request — fails this test until the README is
    rewritten to match.
    """
    assert "paths:" in _pull_request_trigger(_read(CONTAINER_SCAN)), (
        "container-scan.yml's pull_request trigger is no longer path-filtered, "
        "but the README's Security row describes it as path-filtered"
    )
    row = _table_row(_read(README), "Security & Supply-Chain")
    assert "path-filtered" in row, (
        "the README's Security row does not say the container scan is "
        "path-filtered, so a reader will take it for a gate that runs"
    )
    assert "security" in makefile_prerequisites("verify"), (
        "`make security` is no longer a `verify` stage, so pip-audit, "
        "osv-scanner and gitleaks no longer block a merge through the required "
        "`verify` check, which the README's Security row says they do"
    )


# --- The Accessibility row: which pages the gate covers ----------------------

#: Where each document describes the accessibility gate's coverage. The prose
#: sits in three files, so keeping it in step by hand meant three edits nobody
#: made; the marker locates the sentence and the page list is derived.
A11Y_PROSE = (
    (README, r"^\|\s*Accessibility\s*\|.*$"),
    (CI_WORKFLOW, r"^\s*# 5\. accessibility.*(?:\n\s*#.*)*$"),
    (ROADMAP, r"^\| axe violations.*$"),
)


def test_every_document_describing_the_a11y_gate_names_every_page() -> None:
    """Three documents said "dashboard + login" after a third page was added.

    ``A11Y_PAGES`` is already tied to what ``build_all`` writes
    (``tests/test_a11y.py``), so the page list is derivable and the prose about
    it can be checked against the same source instead of being kept in step by
    hand in three files at once.
    """
    pages = [Path(entry).stem for entry in makefile_list("A11Y_PAGES")]
    assert len(pages) > 1, "A11Y_PAGES no longer names more than one page"
    for path, marker in A11Y_PROSE:
        found = re.search(marker, _read(path), re.MULTILINE)
        rel = path.relative_to(REPO_ROOT)
        assert found, f"{rel} no longer has the passage that describes the a11y gate ({marker})"
        missing = [page for page in pages if page not in found.group(0)]
        assert missing == [], (
            f"{rel} describes the accessibility gate without naming {missing}, "
            f"which A11Y_PAGES covers"
        )


# --- Counts and links across the authored docs -------------------------------


def test_stated_file_counts_match_the_tree() -> None:
    """Two docs from one pass gave 35 and 37 test files for the same tree.

    Neither matched, and they did not match each other, so the disagreement was
    committed already broken. Both figures are trivially derivable, so any doc
    stating one is now compared against the directory.
    """
    derived = {
        "test files": len(list((REPO_ROOT / "tests").glob("test_*.py"))),
        "workflow files": len(_workflows()),
    }
    wrong: list[str] = []
    for path in _authored_markdown():
        for number, line in enumerate(_read(path).splitlines(), 1):
            for noun, actual in derived.items():
                for stated in re.findall(rf"([0-9]+) {noun}", line):
                    if int(stated) != actual:
                        rel = path.relative_to(REPO_ROOT)
                        wrong.append(f"{rel}:{number} says {stated} {noun}, tree has {actual}")
    assert wrong == [], "stale counts in published docs: " + "; ".join(wrong)


def _relative_link_targets(text: str) -> list[tuple[int, str]]:
    """Every markdown link on each line that points inside this repository."""
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), 1):
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", line):
            stripped = target.strip()
            candidate = stripped.split()[0] if stripped else ""
            if not candidate or candidate.startswith(("http://", "https://", "mailto:", "#")):
                continue
            found.append((number, candidate))
    return found


def _resolves_case_sensitively(path: Path) -> bool:
    """``Path.exists`` answers the wrong question on a case-insensitive volume.

    ``docs/README.md`` linked ``roadmap.md`` beside ``ROADMAP.md``. On macOS
    that link opens; on Linux, and on github.com, it 404s, which is where the
    people reading this repository are. Walking the tree name by name gives the
    answer a Linux reader would get, from any host.
    """
    try:
        parts = path.resolve().relative_to(REPO_ROOT).parts
    except ValueError:
        return False
    current = REPO_ROOT
    for part in parts:
        if not current.is_dir() or part not in {child.name for child in current.iterdir()}:
            return False
        current = current / part
    return True


def test_every_relative_link_in_an_authored_doc_resolves() -> None:
    """Case-sensitively, so a link that only works on macOS still fails here.

    This replaces a hand-recorded "64 authored-doc links checked; 0 unresolved"
    in ``docs/DOCUMENTATION-AUDIT.md``, which went on reporting a clean result
    for a set of links that had since grown and acquired a broken one.
    """
    broken: list[str] = []
    checked = 0
    for doc in _authored_markdown():
        for number, target in _relative_link_targets(_read(doc)):
            checked += 1
            fragmentless = target.split("#", 1)[0]
            if not fragmentless:
                continue
            if not _resolves_case_sensitively(doc.parent / fragmentless):
                broken.append(f"{doc.relative_to(REPO_ROOT)}:{number} -> {target}")
    assert checked, "no relative links found; this check would pass vacuously"
    assert broken == [], f"unresolved links in authored docs: {broken}"


# --- Release claims ----------------------------------------------------------


def test_citation_and_changelog_agree_on_whether_anything_is_released() -> None:
    """``CITATION.cff`` carried ``date-released: 2026-06-30`` with nothing tagged.

    ``CHANGELOG.md`` says in the same tree that no release has been tagged, and
    ``DEFINITION_OF_DONE.md`` leaves the dated-changelog-section box unticked.
    The date is the one of the three a citation manager reads, so the repository
    published a release date for a release that does not exist. The equality
    below binds the two directions together: the date cannot reappear before a
    dated changelog section does, and cutting a real release without restoring
    the date fails here too.
    """
    dated_sections = re.findall(
        r"^## \[(?!Unreleased)[^\]]+\][^\n]*[0-9]{4}-[0-9]{2}-[0-9]{2}",
        _read(REPO_ROOT / "CHANGELOG.md"),
        re.MULTILINE,
    )
    citation = _read(REPO_ROOT / "CITATION.cff")
    has_date = any(line.startswith("date-released:") for line in citation.splitlines())
    assert has_date == bool(dated_sections), (
        f"CITATION.cff {'declares' if has_date else 'omits'} date-released while "
        f"CHANGELOG.md has {len(dated_sections)} dated release sections"
    )


def test_citation_version_matches_the_packaged_version() -> None:
    """One version string in two files, and only one of them is installed from."""
    packaged = tomllib.loads(_read(PYPROJECT))["project"]["version"]
    cited = re.search(r'^version:\s*"?([^"\n]+?)"?$', _read(REPO_ROOT / "CITATION.cff"), re.M)
    assert cited, "CITATION.cff no longer declares a version"
    assert cited.group(1) == packaged, (
        f"CITATION.cff cites {cited.group(1)}, pyproject.toml packages {packaged}"
    )


def test_the_responsible_tech_audit_describes_the_release_pipeline_that_exists() -> None:
    """It said "no release pipeline exists yet" for seven weeks after one shipped.

    ``release.yml`` landed 2026-07-09 carrying the CycloneDX SBOM, the cosign
    keyless signing and the build-provenance attestation that section says are
    waiting on a pipeline to be built — and the README's Release row said the
    opposite in the same tree. Two published documents disagreeing is worse than
    either being stale alone, because a reader who checks one has no reason to
    check the other.
    """
    release = WORKFLOW_DIR / "release.yml"
    text = _read(RESPONSIBLE_TECH)
    assert release.is_file() == ("release.yml" in text), (
        f"release.yml {'exists' if release.is_file() else 'does not exist'} but "
        f"RESPONSIBLE-TECH-AUDITS.md {'does not name' if release.is_file() else 'names'} it"
    )
    if release.is_file():
        assert "no release pipeline exists" not in text, (
            "RESPONSIBLE-TECH-AUDITS.md says no release pipeline exists while "
            ".github/workflows/release.yml is committed"
        )
