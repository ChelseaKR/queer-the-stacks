"""The committed ruleset must not be a lockout waiting to be applied.

``.github/rulesets/main.proposed.json`` carried ``"bypass_actors": []`` from the day
it was written, and its own README walked a reader through posting it with
``gh api -X POST .../rulesets --input``. Following this repository's own
instructions was therefore enough to lock the owner out of it, which is not
hypothetical: applying a no-bypass ruleset elsewhere in this portfolio took a
manual recovery sweep across eighteen repositories. GitHub answers such a POST
with ``201 Created`` like any other, so nothing warns you at the moment you do it.

An empty bypass list is not a stricter gate. It changes none of the rules --
deletion, force-push and the required status checks are enforced identically
either way. The only thing it changes is whether anybody can recover when the
gate itself is wrong, which is the situation a bypass exists for.

Correcting the file once is not the fix, because the file can regress. This
module is the fix: the empty list, and the four other shapes that lose the
bypass just as completely, are now test failures.

Everything here fails closed, in the sense the rest of this suite already uses
(``tests/test_standards_pin.py``, ``Makefile``'s ``marker-hygiene``). The
predicate is a pure function of a parsed document and is run against documents
it must reject as well as against the committed one, and the loader refuses a
missing or unparseable file rather than returning something empty that the
assertions below would read as "nothing wrong". A guard that passes when its
subject is absent is the defect it exists to catch, and the parse is what
catches it: a truncated JSON file still contains the literal string
``bypass_actors``, so a grep would wave it through.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
RULESET_DIR = ROOT / ".github" / "rulesets"
RULESET_DOC = RULESET_DIR / "README.md"
WORKFLOWS = ROOT / ".github" / "workflows"

#: The ruleset for ``main``, under either name it is allowed to have. The README
#: tells the reader to drop the ``.proposed`` suffix once the file and the live
#: ruleset agree, so both names resolve here; exactly one of them may exist.
MAIN_RULESET_NAMES = ("main.proposed.json", "main.json")

OWNER_BYPASS = {
    "actor_id": 5,
    "actor_type": "RepositoryRole",
    "bypass_mode": "always",
}
"""The repository owner's standing bypass, and the only entry this file may carry.

``RepositoryRole`` 5 is the repository admin role. ``bypass_mode`` is ``always``
rather than the ``pull_request`` CICD-15 asks for, deliberately: a bypass scoped
to pull requests only acts inside a pull request, which is no use in precisely
the situation a bypass exists for, when the pull request is the thing that is
wedged. Narrowing this entry to ``pull_request`` reintroduces the lockout.
"""

#: Status-check contexts this repository may require on ``main``. Each one is
#: produced by a workflow job that runs on *every* pull request into ``main``
#: with no path filter, so each one actually reports and can actually go green.
#: A required check that files no check run does not fail a pull request, it
#: suspends one, at "Expected -- waiting for status to be reported", forever.
REVIEWED_CONTEXTS = {
    "verify",  # ci.yml, job `verify`
    "standards",  # standards.yml, job `standards`
    "Analyze (python)",  # codeql.yml, job `analyze`, matrix language `python`
    "Analyze (actions)",  # codeql.yml, job `analyze`, matrix language `actions`
}

#: Contexts that must never be required, mapped to the workflow whose trigger
#: makes requiring them a wedge. ``trivy`` and ``zizmor`` are path-filtered, so
#: they file no check run on a pull request that touches none of their paths;
#: ``scorecard`` has no ``pull_request`` trigger at all. ``trivy`` was required
#: by the first version of this file, and PR #79 -- which touched none of
#: `container-scan.yml`'s paths and produced no ``trivy`` check run -- could
#: never have merged under it.
UNREQUIRABLE_CONTEXTS = {
    "trivy": "container-scan.yml",
    "zizmor": "zizmor.yml",
    "scorecard": "scorecard.yml",
}


def main_ruleset_path() -> Path:
    """The committed ruleset for ``main``, or a failure. Never a silent skip."""
    present = [RULESET_DIR / name for name in MAIN_RULESET_NAMES]
    present = [path for path in present if path.is_file()]
    if not present:
        pytest.fail(
            f"none of {MAIN_RULESET_NAMES} exists under {RULESET_DIR.relative_to(ROOT)}; "
            "the committed ruleset is the thing this module checks, and its absence "
            "is a failure rather than nothing to do"
        )
    if len(present) > 1:
        pytest.fail(
            "both a proposed and a promoted ruleset exist "
            f"({[p.name for p in present]}); exactly one may, or a reader cannot tell "
            "which of them the apply instructions mean"
        )
    return present[0]


def load_ruleset(path: Path) -> dict[str, Any]:
    """A parsed ruleset document, or a failure. Never a silent empty document.

    The two ways a check like this passes vacuously are a missing file and an
    unparseable one, so both are failures here rather than defaults.
    """
    if not path.is_file():
        pytest.fail(f"{path.relative_to(ROOT)} is missing")
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        pytest.fail(
            f"{path.relative_to(ROOT)} is not parseable JSON, so nothing can vouch "
            f"for what applying it would do: {exc}"
        )
    if not isinstance(loaded, dict):
        pytest.fail(f"{path.relative_to(ROOT)} is not a JSON object")
    return loaded


def lockout_risk(document: dict[str, Any]) -> str | None:
    """Why applying this ruleset would lock the owner out, or ``None`` if it would not.

    A pure function of a parsed document, so it can be run against the documents
    it must reject and not only against the one that happens to be committed.
    """
    if "bypass_actors" not in document:
        return "no bypass_actors key at all, which GitHub reads as an empty list"
    actors = document["bypass_actors"]
    if not isinstance(actors, list):
        return f"bypass_actors is {type(actors).__name__}, not a list"
    if not actors:
        return (
            "bypass_actors is empty, so applying this leaves no break-glass path: "
            "the owner cannot push to main, cannot merge, and a required check that "
            "never reports blocks every pull request until the ruleset is edited by hand"
        )
    if OWNER_BYPASS in actors:
        return None
    narrowed = [
        actor
        for actor in actors
        if isinstance(actor, dict)
        and actor.get("actor_id") == OWNER_BYPASS["actor_id"]
        and actor.get("actor_type") == OWNER_BYPASS["actor_type"]
    ]
    if narrowed:
        return (
            "the owner's bypass is narrowed to bypass_mode "
            f"{narrowed[0].get('bypass_mode')!r}; CICD-15 asks for 'pull_request' and "
            "that is the mandate not to follow, because a bypass that only acts inside "
            "a pull request is no use when the pull request is what is wedged"
        )
    return (
        f"bypass_actors does not carry the owner's standing bypass {OWNER_BYPASS}; "
        f"it carries {actors}"
    )


def test_applying_the_committed_ruleset_would_not_lock_the_owner_out() -> None:
    """The whole point. This is the assertion the empty list has to fail."""
    path = main_ruleset_path()
    risk = lockout_risk(load_ruleset(path))
    assert risk is None, (
        f"applying {path.relative_to(ROOT)} as committed would lock the repository "
        f"owner out: {risk}. See .github/rulesets/README.md, 'bypass_actors: the "
        "repository owner, and nobody else'."
    )


def test_the_owner_is_the_only_bypass_actor_in_the_file() -> None:
    """One actor. A second entry is a widening of who may skip every rule.

    The live ruleset carries a second entry (``User:3114598``, scoped
    ``pull_request``) that no commit accounts for. Whatever is done about that
    on the server, this file stays auditable at one line.
    """
    path = main_ruleset_path()
    actors = load_ruleset(path)["bypass_actors"]
    assert actors == [OWNER_BYPASS], (
        "the owner's standing bypass is the only entry this file may carry, and a "
        f"second one is a widening of who can skip every rule: {actors}"
    )


def test_every_committed_ruleset_carries_the_bypass() -> None:
    """Not just the one for ``main``. A new ruleset file is a new way to lock her out."""
    assert RULESET_DIR.is_dir(), f"{RULESET_DIR.relative_to(ROOT)} is missing"
    documents = sorted(RULESET_DIR.glob("*.json"))
    assert documents, (
        f"no ruleset documents under {RULESET_DIR.relative_to(ROOT)}; this test would "
        "otherwise pass by having nothing to look at"
    )
    for path in documents:
        risk = lockout_risk(load_ruleset(path))
        assert risk is None, f"applying {path.relative_to(ROOT)} would lock the owner out: {risk}"


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ({"bypass_actors": []}, "is empty"),
        ({}, "no bypass_actors key"),
        ({"bypass_actors": {}}, "not a list"),
        (
            {
                "bypass_actors": [
                    {"actor_id": 1, "actor_type": "Integration", "bypass_mode": "always"}
                ]
            },
            "does not carry the owner",
        ),
        (
            {"bypass_actors": [dict(OWNER_BYPASS, bypass_mode="pull_request")]},
            "narrowed to bypass_mode",
        ),
    ],
    ids=["empty", "absent", "wrong-type", "foreign-actor", "pull-request-mode"],
)
def test_the_lockout_check_rejects_the_documents_it_must_reject(
    document: dict[str, Any], expected: str
) -> None:
    """Five ways to lose the bypass, each of which GitHub accepts with a 201.

    The empty list is the one that was committed. The rest are the shapes an
    edit meant to fix it could plausibly land in, and ``pull-request-mode`` is
    the one that looks correct.
    """
    risk = lockout_risk(document)
    assert risk is not None, f"{document} should be refused"
    assert expected in risk, f"{document} was refused, but for the wrong reason: {risk}"


def test_the_lockout_check_accepts_the_shape_it_should() -> None:
    """A positive control, so the check above cannot pass by refusing everything."""
    assert lockout_risk({"bypass_actors": [OWNER_BYPASS]}) is None


def test_the_documentation_names_the_bypass_the_file_carries() -> None:
    """The README talks a reader through checking this before posting, so it must agree.

    The apply procedure is prose, and prose drifts. If the file and the
    instructions for reading it disagree, the instructions are the ones a person
    follows.
    """
    doc = RULESET_DOC.read_text(encoding="utf-8")
    for fragment in ('"actor_id": 5', "RepositoryRole", "always"):
        assert fragment in doc, f"{RULESET_DOC.relative_to(ROOT)} does not name {fragment!r}"


def test_the_readme_does_not_claim_nothing_is_applied() -> None:
    """A ruleset *is* applied. The README said otherwise, and that was load-bearing.

    It justified the whole artifact on the claim that nothing was live, so a
    reader had no reason to expect a POST to collide with anything.
    """
    doc = RULESET_DOC.read_text(encoding="utf-8")
    assert "18752854" in doc, (
        "the README must name the live ruleset id, because a reader following its "
        "apply instructions needs to know a ruleset already exists"
    )
    assert "does not replace" in doc, (
        "the README must warn that POST adds a ruleset rather than replacing one; "
        "without that, applying this file leaves two rulesets over main"
    )


def test_only_reviewed_contexts_are_required() -> None:
    """Required checks are pinned to the set that reports on every pull request."""
    document = load_ruleset(main_ruleset_path())
    required = {
        check["context"]
        for rule in document["rules"]
        if rule["type"] == "required_status_checks"
        for check in rule["parameters"]["required_status_checks"]
    }
    assert required == REVIEWED_CONTEXTS, (
        f"required contexts are {sorted(required)}, reviewed set is "
        f"{sorted(REVIEWED_CONTEXTS)}. Every entry must be produced by a job that "
        "runs on every pull request into main; see .github/rulesets/README.md, "
        "'Required contexts: only checks that report on every pull request'."
    )
    for context, workflow in UNREQUIRABLE_CONTEXTS.items():
        assert context not in required, (
            f"{context!r} cannot be required: {workflow} does not report on every "
            "pull request, so requiring it suspends the ones it skips"
        )


def test_the_conditionally_triggered_workflows_still_are() -> None:
    """The reason those three contexts are excluded, checked rather than remembered.

    If a path filter is dropped or a ``pull_request`` trigger is added, the
    exclusion above stops being justified and should be revisited on purpose
    rather than left standing because nobody looked again.
    """
    for name in ("container-scan.yml", "zizmor.yml"):
        workflow = WORKFLOWS / name
        assert workflow.is_file(), f"{name} is gone; revisit the required-context list"
        assert "paths:" in workflow.read_text(encoding="utf-8"), (
            f"{name} is no longer path-filtered, so it now reports on every pull "
            "request. Revisit whether its check belongs in REVIEWED_CONTEXTS."
        )
    scorecard = WORKFLOWS / "scorecard.yml"
    assert scorecard.is_file(), "scorecard.yml is gone; revisit the required-context list"
    assert "pull_request" not in scorecard.read_text(encoding="utf-8"), (
        "scorecard.yml now has a pull_request trigger. Revisit whether its check "
        "belongs in REVIEWED_CONTEXTS."
    )
