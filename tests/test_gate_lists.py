"""The gates' hand-maintained lists still match what exists, and still bite.

A merge-blocking gate driven by a literal list is only as complete as that
list. Nothing fails when a new directory is simply not added to it: the gate
runs, finds nothing in the places it was told about, and reports success. That
is the shape the accessibility gate's page list already guards against (see
``tests/test_a11y.py``); this file applies it to the other gates in
``make verify``.

Two kinds of check live here.

**Coverage of a list.** ``MARKER_ROOTS`` in the ``Makefile``, ``files`` under
``[tool.mypy]``, the ``--cov=`` entries in ``addopts``, and ``packages`` under
``[tool.setuptools]`` are four hand-written spellings of "the first-party code".
Each is compared against the packages that actually import, so adding a package
and forgetting one of the four is a test failure instead of a leg of the
pipeline that silently stops looking at it.

**Discipline inside a recipe.** ``marker-hygiene`` and ``scripts/secret-scan.sh``
were both, until this branch, structurally incapable of reporting what they
exist to report: each discarded a grep exit code that distinguishes "nothing
found" from "nothing read". Those recipes are read back here so that restoring
the discarded status is a failing test rather than a quiet return to a gate
that always passes.
"""

from __future__ import annotations

import json
import re
import shlex
import tomllib
from pathlib import Path

import app
import ingest
import recommender

from tests.makefilevars import makefile_list, makefile_prerequisites, makefile_recipe

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
SECRET_SCAN = REPO_ROOT / "scripts" / "secret-scan.sh"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
LIGHTHOUSERC = REPO_ROOT / ".lighthouserc.json"


def _pyproject() -> dict[str, object]:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _tool(*path: str) -> object:
    node: object = _pyproject()
    for key in path:
        assert isinstance(node, dict), f"pyproject.toml has no [{'.'.join(path)}]"
        assert key in node, f"pyproject.toml no longer defines {'.'.join(path)}"
        node = node[key]
    return node


def _first_party_packages() -> set[str]:
    """Every importable first-party package, derived from the packages themselves.

    Derived rather than listed, so this side of each comparison below cannot go
    stale in the same way the hand-written side can.
    """
    return {
        Path(pkg.__file__).parent.resolve().relative_to(REPO_ROOT).as_posix()
        for pkg in (ingest, recommender, app)
        if pkg.__file__
    }


def _first_party_roots() -> set[str]:
    """The packages, plus the test suite, which the marker scan also covers."""
    return _first_party_packages() | {"tests"}


# --- The marker-hygiene scan -------------------------------------------------


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


def test_marker_hygiene_keeps_its_exit_code_discipline() -> None:
    """The recipe still tells grep's "no match" apart from grep's "error".

    grep exits 0 on a match, 1 on no match and 2 on an error. The recipe used
    ``|| true``, which swallowed all three alike: renaming a scanned directory
    made every scan return empty and the target print "0 bare markers" and exit
    0, having read nothing. Reintroducing ``|| true`` on those greps restores a
    gate that cannot fail, so it fails here instead.
    """
    recipe = makefile_recipe("marker-hygiene")
    assert "|| true" not in recipe, (
        "marker-hygiene has a `|| true` again. That discards grep's exit 2 "
        "(error) along with its exit 1 (no match), so a scan that read nothing "
        "reports the same '0 bare markers' as a scan that found nothing."
    )
    assert recipe.count("-gt 1") == 3, (
        "each of the three marker scans must check for a grep exit code above "
        "1; without that check an errored scan is indistinguishable from a "
        "clean one"
    )
    assert "test -d" in recipe, (
        "marker-hygiene no longer verifies its scan roots exist, so a renamed "
        "directory would simply go unscanned"
    )
    assert "pass vacuously" in recipe, (
        "marker-hygiene no longer refuses to run when the roots hold no Python "
        "files; an empty scan would report success"
    )


# --- The type-check gate's file list -----------------------------------------


def test_mypy_checks_every_first_party_package() -> None:
    """``files`` is the same shape of list as MARKER_ROOTS, with the same risk.

    mypy checks exactly what ``files`` names. A package absent from it is never
    type-checked, and ``make typecheck`` still exits 0 — the gate reports
    success having never looked.
    """
    files = _tool("tool", "mypy", "files")
    assert isinstance(files, list)
    assert set(files) == _first_party_packages(), (
        f"[tool.mypy] files is {sorted(str(f) for f in files)} but the "
        f"first-party packages are {sorted(_first_party_packages())}. A package "
        "missing here is never type-checked by `make typecheck`."
    )


def test_mypy_is_still_strict() -> None:
    """The gate's strength is configuration; nothing else asserts it."""
    mypy = _tool("tool", "mypy")
    assert isinstance(mypy, dict)
    assert mypy.get("strict") is True, "[tool.mypy] strict is no longer true"
    assert mypy.get("disallow_untyped_defs") is True
    assert mypy.get("warn_return_any") is True
    assert not mypy.get("ignore_errors", False), (
        "[tool.mypy] ignore_errors would make `make typecheck` pass on anything"
    )


# --- The coverage gate's package list and floor ------------------------------


def _addopts() -> list[str]:
    addopts = _tool("tool", "pytest", "ini_options", "addopts")
    assert isinstance(addopts, list)
    return [str(opt) for opt in addopts]


def test_coverage_measures_every_first_party_package() -> None:
    """A package with no ``--cov=`` entry is outside the denominator entirely.

    It is not reported as 0% — it is not reported at all, so the 85% floor is
    computed as though the package did not exist and cannot fail because of it.
    """
    measured = {opt.split("=", 1)[1] for opt in _addopts() if opt.startswith("--cov=")}
    assert measured == _first_party_packages(), (
        f"coverage measures {sorted(measured)} but the first-party packages are "
        f"{sorted(_first_party_packages())}. A package missing a --cov= entry is "
        "outside the coverage denominator, so the floor cannot fail on it."
    )


def test_coverage_floor_is_still_enforced() -> None:
    """``--cov-fail-under`` is what makes the coverage number a gate at all."""
    floors = [opt for opt in _addopts() if opt.startswith("--cov-fail-under=")]
    assert len(floors) == 1, f"expected exactly one --cov-fail-under, found {floors}"
    value = int(floors[0].split("=", 1)[1])
    assert value >= 85, (
        f"the coverage floor is {value}; the pipeline is documented as gating at "
        "85% and lowering it silently weakens stage 3"
    )


def test_setuptools_packages_match_the_first_party_packages() -> None:
    """The fourth spelling of the same list, kept in step with the other three."""
    packages = _tool("tool", "setuptools", "packages")
    assert isinstance(packages, list)
    assert set(packages) == _first_party_packages()


# --- The lint gate's rule selection ------------------------------------------

#: Rule families ``pyproject.toml`` documents and the Makefile advertises. ``S``
#: is flake8-bandit: `make lint`'s help text calls it "the bandit SAST subset",
#: so dropping it would make that claim false and remove the only SAST leg in
#: the pipeline without any gate going red.
ADVERTISED_RUFF_FAMILIES = frozenset({"E", "F", "I", "B", "C4", "UP", "SIM", "T20", "S", "C90"})


def test_ruff_still_selects_the_advertised_rule_families() -> None:
    select = _tool("tool", "ruff", "lint", "select")
    assert isinstance(select, list)
    missing = ADVERTISED_RUFF_FAMILIES - {str(rule) for rule in select}
    assert not missing, (
        f"[tool.ruff.lint] select no longer includes {sorted(missing)}. The "
        "Makefile advertises `make lint` as covering these; a family dropped "
        "here removes its checks with no gate going red."
    )


def test_ruff_does_not_blanket_ignore_the_sast_subset() -> None:
    """Selecting ``S`` means nothing if ``S`` is then ignored wholesale."""
    ignore = _tool("tool", "ruff", "lint", "ignore")
    assert isinstance(ignore, list)
    assert "S" not in {str(rule) for rule in ignore}, (
        "[tool.ruff.lint] ignore contains a blanket `S`, which disables the "
        "whole bandit SAST subset while leaving it listed in `select`"
    )
    per_file = _tool("tool", "ruff", "lint", "per-file-ignores")
    assert isinstance(per_file, dict)
    for glob, rules in per_file.items():
        assert "S" not in {str(rule) for rule in rules}, (
            f"per-file-ignores disables the whole SAST subset for {glob!r}"
        )


def test_ruff_excludes_no_first_party_code() -> None:
    """An excluded directory is a directory `ruff check .` reports nothing about."""
    ruff = _tool("tool", "ruff")
    assert isinstance(ruff, dict)
    excluded: set[str] = set()
    for key in ("exclude", "extend-exclude"):
        for entry in ruff.get(key, []) or []:
            excluded.add(str(entry).strip("./"))
    overlap = excluded & _first_party_roots()
    assert not overlap, f"ruff excludes first-party code: {sorted(overlap)}"


# --- The secret scan ---------------------------------------------------------
#
# `scripts/secret-scan.sh` falls back to grep when gitleaks is absent, and every
# defect it had was a way of reporting "0 findings" without having looked. The
# script now self-tests its patterns at run time; these tests cover the plumbing
# around them, which a run on a clean tree cannot demonstrate.


def _secret_scan_source() -> str:
    return SECRET_SCAN.read_text(encoding="utf-8")


def _secret_scan_code() -> str:
    """The script with whole-line comments removed.

    The header comment names each defect the script used to have, quoting the
    constructs that caused them — ``|| true``, ``2>/dev/null``, "no tracked
    files yet". An assertion that those strings are absent has to read the code
    alone, or the explanation of the fix reads as the defect itself.
    """
    return "\n".join(
        line
        for line in _secret_scan_source().splitlines()
        if not line.lstrip().startswith("#") or line.startswith("#!")
    )


def _secret_scan_patterns() -> list[str]:
    """The ``patterns=(...)`` array, unquoted the way the shell would unquote it."""
    source = _secret_scan_source()
    block = re.search(r"^patterns=\(\n(.*?)^\)$", source, re.MULTILINE | re.DOTALL)
    assert block, "scripts/secret-scan.sh no longer defines a patterns=(...) array"
    patterns: list[str] = []
    for line in block.group(1).splitlines():
        if line.strip():
            patterns.extend(shlex.split(line, comments=True))
    assert patterns, "the secret scan's pattern list is empty"
    return patterns


#: One known positive per pattern, in the same order as the script's array.
#: Assembled from fragments for the same reason the script assembles its own:
#: the scan reads every tracked file, this one included, and a literal sample
#: here would make the gate report itself forever.
KNOWN_POSITIVES: tuple[str, ...] = (
    "AKIA" + "A" * 16,
    "-----BEGIN RSA PRIVATE " + "KEY" + "-----",
    "xox" + "b-0123456789abcdef",
    "AIza" + "b" * 35,
    "password" + '="correcthorsebatterystaple"',
)


def _as_python_regex(pattern: str) -> str:
    """Translate the one POSIX class these ERE patterns use into Python's dialect."""
    translated = pattern.replace("[[:space:]]", "[ \t\r\n\f\v]")
    assert "[[:" not in translated, (
        f"{pattern!r} uses a POSIX character class this translation does not "
        "handle, so the assertion below would not be testing what it appears to"
    )
    return translated


def test_secret_scan_patterns_match_known_positives() -> None:
    """Every pattern still matches the shape it exists to catch.

    The script checks this itself before scanning, which is the check that
    matters at run time. Repeating it here with independently written samples
    means a pattern and its shell sample cannot be weakened together and still
    look green.
    """
    patterns = _secret_scan_patterns()
    assert len(patterns) == len(KNOWN_POSITIVES), (
        f"the scan has {len(patterns)} patterns but this test knows "
        f"{len(KNOWN_POSITIVES)} samples; add the missing sample rather than "
        "leaving a pattern unproven"
    )
    for pattern, sample in zip(patterns, KNOWN_POSITIVES, strict=True):
        assert re.search(_as_python_regex(pattern), sample), (
            f"secret-scan pattern {pattern!r} no longer matches {sample!r}; it "
            "would contribute nothing to the scan and report 0 findings "
            "whatever the tree holds"
        )


def test_secret_scan_passes_every_pattern_after_dash_e() -> None:
    """The private-key pattern begins with ``-`` and is otherwise read as options.

    Without ``-e`` grep parsed it as an option bundle, printed "unrecognized
    option" to a discarded stderr and exited non-zero, which the caller read as
    "no match". That pattern had therefore never matched anything, and a PEM
    block committed to a tracked file scanned clean.
    """
    code = _secret_scan_code()
    invocations = re.findall(r"grep\s+(-[A-Za-z]+)\s+(?!-e\b)", code)
    assert not invocations, (
        f"a grep in secret-scan.sh takes its pattern positionally ({invocations}); "
        "a pattern beginning with `-` is then parsed as options and silently "
        "matches nothing"
    )
    assert code.count("grep -qIE -e") == 1, "the pattern self-check must survive"
    assert code.count("grep -InE -e") == 1, "the scanning grep must survive"


def test_secret_scan_refuses_a_tree_it_could_not_read() -> None:
    """A grep that could not read a file must not count as a file with no secret.

    grep exits non-zero both when it finds nothing and when it cannot read what
    it was pointed at, so the scanning grep's stderr is captured and any output
    on it fails the run.
    """
    code = _secret_scan_code()
    assert 'hits=$(xargs -0 grep -InE -e "$pat" <"$list" 2>"$errs" || true)' in code, (
        "the scanning grep no longer captures stderr to a file; a tracked file "
        "the scan could not read would count as a file with no secret in it"
    )
    assert '[ -s "$errs" ]' in code, (
        "nothing checks the captured stderr, so an unreadable tree still scans clean"
    )
    assert "2>/dev/null" not in code, (
        "secret-scan.sh discards a stream again; every defect this script had "
        "was an error being read as an absence of findings"
    )


def test_secret_scan_refuses_an_empty_or_unbuildable_file_list() -> None:
    """Both vacuous-pass doors the old script left open are shut."""
    code = _secret_scan_code()
    assert "no tracked files yet" not in code, (
        "the old `no tracked files yet — ok; exit 0` path is back; outside a git "
        "work tree it reported success having read nothing"
    )
    assert "refusing to report success" in code
    assert "refusing to report a clean scan of a tree it never read" in code


# --- The lockfile scan the local gate is allowed to skip ---------------------


def test_ci_runs_the_lockfile_scan_the_local_gate_may_skip() -> None:
    """``make security`` exits 0 without osv-scanner, so CI must be the backstop.

    This is the one leg of ``make verify`` that is deliberately allowed not to
    run locally: the Makefile prints a loud warning and continues. That is only
    defensible while CI installs the scanner and runs the same target blocking,
    which is what this asserts. If the CI install step goes away, the lockfile
    is scanned nowhere and nothing else would say so.
    """
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "osv-scanner" in workflow, (
        "ci.yml no longer installs osv-scanner, and `make security` skips it "
        "locally, so uv.lock would be scanned nowhere"
    )
    assert "run: make security" in workflow, "ci.yml no longer runs `make security`"

    recipe = makefile_recipe("security")
    assert "./scripts/secret-scan.sh" in recipe
    assert "osv-scanner --lockfile=uv.lock" in recipe
    assert "SKIPPED" in recipe and ">&2" in recipe, (
        "the local osv-scanner skip must stay loud and on stderr; a silent skip "
        "reads exactly like a scan that found nothing"
    )


# --- The accessibility gate's own non-vacuity guards -------------------------


def test_a11y_recipe_keeps_its_layer_zero_guards() -> None:
    """Every loop in the a11y recipe is a no-op if the page list is empty.

    ``tests/test_a11y.py`` ties ``A11Y_PAGES`` to what ``build_all`` writes. The
    complementary risk is the list going empty or a page going missing, which
    would make each ``for`` loop below iterate zero times and exit 0.
    """
    recipe = makefile_recipe("a11y")
    assert 'test -n "$(A11Y_PAGES)"' in recipe, (
        "the a11y recipe no longer asserts its page list is non-empty; every "
        "loop in it would then be a no-op that exits 0"
    )
    assert 'test -s "$$page"' in recipe, (
        "the a11y recipe no longer asserts each page exists and is non-empty"
    )
    for leg in ("app.a11y_check", "pa11y --runner axe", "scripts/a11y-browser-check.js"):
        assert leg in recipe, f"the a11y gate lost its {leg} leg"


# --- The Lighthouse gate's URL list ------------------------------------------
#
# `.lighthouserc.json` carries the hardest numeric assertion in the pipeline:
# `categories:accessibility` at minScore 1.0, blocking and unconditional. It
# was pointed at `/dashboard.html` alone — 1 of the 4 documents in its own
# `staticDistDir`, and a quarter of the surface `A11Y_PAGES` covers. Nothing
# tied the two lists, so they drifted independently and only one was asserted.
#
# This is the same shape as MARKER_ROOTS and `[tool.mypy] files` above: a
# merge-blocking gate driven by a hand-written list, where the omission is
# invisible because the gate runs, examines what it was told about, and passes.


def _lighthouse_config() -> dict[str, object]:
    config = json.loads(LIGHTHOUSERC.read_text(encoding="utf-8"))
    assert isinstance(config, dict)
    ci = config.get("ci")
    assert isinstance(ci, dict), ".lighthouserc.json has no `ci` block"
    return ci


def _lighthouse_collect() -> dict[str, object]:
    collect = _lighthouse_config().get("collect")
    assert isinstance(collect, dict), ".lighthouserc.json has no `ci.collect` block"
    return collect


def _lighthouse_urls() -> list[str]:
    urls = _lighthouse_collect().get("url")
    assert isinstance(urls, list) and urls, (
        ".lighthouserc.json names no URLs. lhci audits nothing and every "
        "assertion in it passes over an empty set."
    )
    return [str(url) for url in urls]


def test_lighthouse_audits_every_document_the_other_a11y_layers_scan() -> None:
    """The strictest assertion in the pipeline must not cover a quarter of it.

    ``A11Y_PAGES`` is already tied to ``build_all`` and to
    ``HTML_ROUTE_COVERAGE`` by ``tests/test_a11y.py``. This ties the fourth
    spelling of the same list — the one Lighthouse reads — to those three, so
    a document can no longer be audited by the structural checker, pa11y and
    the browser check while the ``minScore: 1.0`` gate never opens it.
    """
    dist = _lighthouse_collect().get("staticDistDir")
    assert isinstance(dist, str) and dist, ".lighthouserc.json has no staticDistDir"

    audited = {f"/{Path(page).name}" for page in makefile_list("A11Y_PAGES")}
    assert set(_lighthouse_urls()) == audited, (
        f"Lighthouse audits {sorted(_lighthouse_urls())} but the a11y gate scans "
        f"{sorted(audited)}. A document missing here is a document the "
        "`categories:accessibility` minScore 1.0 assertion never opens, and "
        "nothing else in the pipeline asserts a Lighthouse score at all."
    )
    assert len(_lighthouse_urls()) == len(set(_lighthouse_urls())), (
        f"Lighthouse's url list repeats an entry: {_lighthouse_urls()}. A "
        "duplicate inflates the run count while hiding a missing document."
    )

    # Non-vacuity: each URL must name a document that `staticDistDir` holds.
    # A path that resolves to nothing is a 404 lhci scores, not a page it read.
    for url in _lighthouse_urls():
        served = REPO_ROOT / dist / url.lstrip("/")
        assert served.is_file(), (
            f"{url} is audited but {served.relative_to(REPO_ROOT)} does not exist; "
            "`make lighthouse` runs `app.build_static` first, so a URL with no "
            "document behind it is a list that has drifted from the generator"
        )


def test_lighthouse_keeps_the_assertions_that_make_it_a_gate() -> None:
    """Widening the URL list must not be paid for by lowering the bar.

    Both figures are what make this stage blocking rather than a report. The
    accessibility floor is 1.0 and is documented as such; the performance floor
    is 0.9. ``"warn"`` in place of ``"error"`` would leave the whole stage
    green whatever it measured.
    """
    assertions = _lighthouse_config().get("assert")
    assert isinstance(assertions, dict), ".lighthouserc.json has no `ci.assert` block"
    rules = assertions.get("assertions")
    assert isinstance(rules, dict) and rules, "`ci.assert.assertions` is empty"

    for name, floor in (("categories:accessibility", 1.0), ("categories:performance", 0.9)):
        rule = rules.get(name)
        assert isinstance(rule, list) and len(rule) == 2, (
            f"{name} is no longer asserted in .lighthouserc.json; the stage would "
            "run Lighthouse and gate on nothing"
        )
        level, options = rule
        assert level == "error", (
            f"{name} is asserted at {level!r}, not 'error'. A warning does not "
            "fail `lhci autorun`, so the stage would pass at any score."
        )
        assert isinstance(options, dict)
        assert float(options.get("minScore", 0)) >= floor, (
            f"{name} minScore is {options.get('minScore')!r}; this gate is "
            f"documented as blocking at {floor}"
        )


def test_the_lighthouse_stage_still_builds_before_it_audits() -> None:
    """``staticDistDir`` holds committed files, so an audit of them is only
    current if the recipe regenerates them first.

    Without the build step lhci would score whatever bytes are committed —
    which is the same defect ``test_build_all_writes_every_audited_document``
    guards one layer down, reached from the other side.
    """
    recipe = makefile_recipe("lighthouse")
    assert "app.build_static" in recipe, (
        "`make lighthouse` no longer regenerates the audited documents, so it "
        "would score the committed copies rather than what the app renders"
    )
    assert "--config=.lighthouserc.json" in recipe, (
        "`make lighthouse` no longer reads .lighthouserc.json, so every "
        "assertion asserted above governs nothing"
    )


# --- The pipeline's own stage list -------------------------------------------

#: Stages ``ci.yml`` runs that ``verify`` deliberately does not. The Makefile
#: header documents both: each needs a booted server or a downloaded Chromium,
#: and ``make perf-gates`` runs them.
VERIFY_EXCLUDED_STAGES = frozenset({"perf-load", "lighthouse"})


def test_verify_runs_every_stage_ci_runs() -> None:
    """``verify`` is only its prerequisite list, and nothing else checks it.

    Drop ``security`` from that line and ``make verify`` still runs to
    completion and still prints "all checkable gates green" — it just never
    scans anything. That is the same defect as a scan root going unlisted, one
    level up, and it would take the whole stage with it rather than one
    directory. The list is tied to the stages CI runs so that neither can lose
    a gate alone.
    """
    stages = set(makefile_prerequisites("verify"))
    ci_stages = set(
        re.findall(
            r"^\s*run: make ([a-z0-9-]+)$", CI_WORKFLOW.read_text(encoding="utf-8"), re.MULTILINE
        )
    )
    assert ci_stages, "no `run: make <target>` steps found in ci.yml"
    expected = ci_stages - VERIFY_EXCLUDED_STAGES
    assert stages == expected, (
        f"`make verify` runs {sorted(stages)} but CI runs {sorted(ci_stages)}, of "
        f"which {sorted(VERIFY_EXCLUDED_STAGES)} are documented as excluded. A "
        "stage missing from verify is a gate that never runs locally; a CI "
        "stage missing from both is a gate that runs nowhere."
    )


def test_every_verify_stage_has_a_recipe_that_runs_something() -> None:
    """Each stage names a real target with a real body.

    Guards the comparison above against a stage that exists only as a name: a
    target with an empty recipe, or one reduced to an ``echo``, would satisfy
    the prerequisite list and run no checks.
    """
    for stage in makefile_prerequisites("verify"):
        recipe = makefile_recipe(stage)
        commands = [
            line
            for line in recipe.splitlines()
            if line.strip() and not line.lstrip().startswith(("#", "@echo", "echo"))
        ]
        assert commands, (
            f"the {stage} stage has no command in its recipe, so `make verify` "
            "would run it and check nothing"
        )


# --- The gate that runs, versus the gate that is cancelled --------------------

#: The interpolation that gives a branch push one concurrency group per commit
#: while keeping one group per pull request.
PER_COMMIT_KEY = "github.event_name == 'pull_request' && 'pr' || github.sha"

WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

#: Workflows that trigger on a push to a branch and cancel runs sharing their
#: group. Named rather than discovered so that a workflow dropping off the list
#: is a failing test rather than one fewer thing checked.
BRANCH_PUSH_WORKFLOWS = ("ci.yml", "standards.yml", "container-scan.yml")


def _concurrency_block(name: str) -> tuple[str, str]:
    """``(group, cancel-in-progress)`` for one workflow, read as text."""
    text = (WORKFLOW_DIR / name).read_text(encoding="utf-8")
    match = re.search(r"^concurrency:\n((?:[ \t]+.*\n)+)", text, re.MULTILINE)
    assert match is not None, f"{name} declares no top-level `concurrency:` block"
    body = match.group(1)
    group = re.search(r"^\s*group:\s*(.+)$", body, re.MULTILINE)
    cancel = re.search(r"^\s*cancel-in-progress:\s*(\S+)", body, re.MULTILINE)
    assert group is not None, f"{name}: concurrency block has no `group:`"
    return group.group(1).strip(), (cancel.group(1) if cancel else "false")


def test_the_branch_push_workflow_list_still_describes_the_workflows() -> None:
    """A floor. Every assertion below iterates this list, so an empty or stale
    list would check nothing and pass — the failure mode this whole file is
    about, applied to itself."""
    present = {path.name for path in WORKFLOW_DIR.glob("*.yml")}
    assert set(BRANCH_PUSH_WORKFLOWS) <= present, sorted(present)
    for name in BRANCH_PUSH_WORKFLOWS:
        text = (WORKFLOW_DIR / name).read_text(encoding="utf-8")
        assert re.search(r"^  push:\n(?:    .*\n)*    branches:", text, re.MULTILINE), (
            f"{name} no longer triggers on a push to a branch; either the list "
            "above is stale or the workflow stopped gating main"
        )


def test_a_push_to_main_cannot_cancel_the_commit_before_it() -> None:
    """A concurrency group keyed on ``github.ref`` alone puts every commit on
    ``main`` in one group, so the second push cancels the first commit's run.

    That is not a red build. A cancelled run's conclusion is neither success nor
    failure: no check goes red, nobody is told, and the commit is on ``main``
    having been examined by nothing. It is the same shape as the silent skips
    the rest of this file guards — a signal identical whether the work happened
    — except that here the gate does not even start.
    """
    offenders: list[str] = []
    for name in BRANCH_PUSH_WORKFLOWS:
        group, cancel = _concurrency_block(name)
        if cancel == "false":
            # Queues instead of cancelling; the earlier commit's run survives.
            continue
        if "github.sha" not in group:
            offenders.append(f"{name}: group: {group}")
    assert not offenders, (
        "these workflows run on a branch push and cancel in-progress runs in "
        "their own group, but the group does not name the commit, so a push to "
        f"main discards the previous commit's only verdict: {offenders}. "
        f"Append -${{{{ {PER_COMMIT_KEY} }}}} to the group."
    )


def test_the_three_fixed_workflows_use_the_agreed_key() -> None:
    """The scan above says "nothing is wrong"; this says "these three were wrong
    and are fixed", so a workflow leaving the scan's reach fails here instead of
    passing there."""
    for name in BRANCH_PUSH_WORKFLOWS:
        group, _ = _concurrency_block(name)
        assert PER_COMMIT_KEY in group, f"{name} does not use the agreed key: {group}"
