"""The committed coverage report is what the test run just produced.

``pyproject.toml`` points pytest at ``--cov-report=xml:docs/audits/coverage.xml``,
so ``make test`` rewrites a committed artifact on every run and nothing compares
it. That is the shape ``make eval-check`` was added to close: a gate that
regenerates the artifact it is supposed to be checked against, discards the
comparison, and passes. A ``docs/audits/coverage.xml`` committed months ago can
sit in git describing a coverage profile nobody has, because every run that
could have noticed overwrote it first.

The fix cannot be byte equality. Three parts of the file move for reasons that
are not facts about the code:

* ``timestamp``, which changes on every run;
* the coverage.py ``version``, which changes when the tool is upgraded;
* the ``<source>`` elements, which are absolute paths. The committed copy's
  point at ``/private/tmp/.../scratchpad/wt/queer-the-stacks/app``, a directory
  that has never existed on any developer's machine, because the artifact was
  last written from a temporary worktree. Asserting those would only assert
  whose machine ran the tests last.

Everything else is a fact about the code, and all of it is compared: which
files were measured, and each one's line rate and branch rate, together with
the run totals. Those are exactly the numbers a reader of the committed report
would rely on.

This runs after ``make test``, so the file on disk is the run that just
finished and the committed bytes come from git. Nothing here writes to the
working tree.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

REPORT = Path("docs/audits/coverage.xml")

#: Attributes deliberately not compared, and why. Named here rather than
#: silently skipped, so that widening the exclusion is a visible edit.
EXCLUDED = {
    "timestamp": "changes on every run",
    "version": "changes when coverage.py is upgraded",
    "complexity": "always 0 in coverage.py's cobertura output",
}


def _totals(root: ElementTree.Element) -> dict[str, str]:
    return {key: value for key, value in root.attrib.items() if key not in EXCLUDED}


def _per_file(root: ElementTree.Element) -> dict[str, tuple[str, str]]:
    measured: dict[str, tuple[str, str]] = {}
    for element in root.iter("class"):
        filename = element.attrib.get("filename")
        if filename is None:
            continue
        measured[filename] = (
            element.attrib.get("line-rate", ""),
            element.attrib.get("branch-rate", ""),
        )
    return measured


def _committed_bytes(rev: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{rev}:{REPORT.as_posix()}"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise SystemExit(
            f"coverage-check: could not read {REPORT} at {rev}: {message}\n"
            "Refusing to report success for a check that did not happen."
        )
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rev",
        default="HEAD",
        help="the revision whose committed report is compared (default: HEAD)",
    )
    args = parser.parse_args(argv)

    if not REPORT.is_file():
        print(
            f"coverage-check: {REPORT} is not on disk. It is written by `make test`, "
            "which must run before this check.",
            file=sys.stderr,
        )
        return 1

    fresh = ElementTree.fromstring(REPORT.read_bytes())
    committed = ElementTree.fromstring(_committed_bytes(args.rev))

    problems: list[str] = []

    fresh_totals, committed_totals = _totals(fresh), _totals(committed)
    for key in sorted(set(fresh_totals) | set(committed_totals)):
        if fresh_totals.get(key) != committed_totals.get(key):
            problems.append(
                f"  run total {key}: committed {committed_totals.get(key)!r}, "
                f"this run {fresh_totals.get(key)!r}"
            )

    fresh_files, committed_files = _per_file(fresh), _per_file(committed)
    if not fresh_files:
        print(
            "coverage-check: this run measured no files at all, so the comparison "
            "would be vacuous.",
            file=sys.stderr,
        )
        return 1

    for name in sorted(set(fresh_files) - set(committed_files)):
        problems.append(f"  {name}: measured by this run, absent from the committed report")
    for name in sorted(set(committed_files) - set(fresh_files)):
        problems.append(f"  {name}: in the committed report, not measured by this run")
    for name in sorted(set(fresh_files) & set(committed_files)):
        if fresh_files[name] != committed_files[name]:
            was_line, was_branch = committed_files[name]
            now_line, now_branch = fresh_files[name]
            problems.append(
                f"  {name}: committed line-rate {was_line} branch-rate {was_branch}, "
                f"this run line-rate {now_line} branch-rate {now_branch}"
            )

    if problems:
        print(
            f"coverage-check: the committed {REPORT} is not what this test run produced.",
            file=sys.stderr,
        )
        print("\n".join(problems), file=sys.stderr)
        print(
            f"\nRun `make test` and commit the regenerated {REPORT}.\n"
            "Not compared, deliberately: "
            + "; ".join(f"{key} ({why})" for key, why in sorted(EXCLUDED.items()))
            + "; and the <source> absolute paths.",
            file=sys.stderr,
        )
        return 1

    print(
        f"coverage-check: the committed {REPORT} matches this run "
        f"({len(fresh_files)} files compared)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
