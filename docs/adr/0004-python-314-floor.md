# 0004. Python 3.14 floor; dependency audit clean

* Status: accepted
* Date: 2026-06-05
* Ported from: `docs/ROADMAP.md` §6 (2026-07-05, form only — content unchanged)

## Context and Problem Statement

Under an earlier Python 3.9 floor, fixes for known `requests`/`urllib3`/`starlette` advisories were
not installable, and had to be accepted as documented residual risk instead of actually fixed.

## Decision Outcome

The project targets **Python 3.14** (build + deployment interpreter 3.14.5). Every dependency
installs at a fixed, non-vulnerable release, so `pip-audit` reports **0 known vulnerabilities** and
`make security` runs with an empty accepted-advisory list.

## Rejected Options

* Silently pinning known-vulnerable dependency versions.
* Dropping the dependency-audit gate to avoid the failures.

Both rejected as a materially weaker security posture than raising the floor.
