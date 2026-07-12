# OpenSSF Scorecard — 2026-07 (first dated report)

**Run:** 2026-07-05 · `scorecard --repo=github.com/ChelseaKR/queer-the-stacks` (CLI v5.5.0, local
run against the pushed `main` branch — this predates the uncommitted remediation work in this
audit pass, including `.github/workflows/codeql.yml`, `zizmor.yml`, and `scorecard.yml` themselves,
so several scores below should improve once those are pushed and re-scanned).

**Aggregate score: 5.5 / 10.**

This satisfies SEC-38 (a monthly-dated report committed) and converts four controls that were
UNVERIFIED from the working tree in the 2026-07-05 conformance audit into measured data:

| Control | Was | Now (measured) |
|---|---|---|
| Token-Permissions (CQ-37, CICD-03) | UNVERIFIED | **10/10** — least-privilege `permissions:` confirmed on all workflow tokens |
| Dangerous-Workflow (CQ-40) | UNVERIFIED | **10/10** — no dangerous trigger/injection patterns detected |
| Branch-Protection (CQ-38/43, CICD-11/13-16) | UNVERIFIED (`ci.yml` asserts it's enabled) | **0/10 — NOT enabled.** This directly contradicts the comment in `ci.yml:3-5` ("branch protection, no admin bypass"). See the BLOCKED item in the remediation log — enabling it is a live GitHub-settings change outside this pass's authority. |
| Pinned-Dependencies (SEC-25/26) | Believed strong (9/9 Actions SHA-pinned) | **3/10** — Actions are pinned, but this check also covers Docker base images and other ecosystems; the Dockerfile's `python:3.14-slim` base was unpinned before this pass (now pinned by digest — see `Dockerfile`) and CI still installs via `pip install -e` rather than a hash-locked set for some steps. Re-scan after these fixes land. |

## Full check table

| Score | Check | Reason |
|---|---|---|
| 10/10 | Binary-Artifacts | no binaries found in the repo |
| **0/10** | **Branch-Protection** | **branch protection not enabled on development/release branches** |
| 7/10 | CI-Tests | 8 out of 11 merged PRs checked by a CI test |
| 0/10 | CII-Best-Practices | no effort to earn an OpenSSF best-practices badge (expected — solo personal project) |
| 0/10 | Code-Review | 0/13 approved changesets (expected — single maintainer, no reviewers) |
| 0/10 | Contributors | 0 contributing companies/orgs (expected — personal project) |
| 10/10 | Dangerous-Workflow | no dangerous workflow patterns detected |
| 10/10 | Dependency-Update-Tool | Renovate detected |
| 0/10 | Fuzzing | project is not fuzzed (not applicable to this app's surface today) |
| 9/10 | License | license file detected |
| 0/10 | Maintained | project created within the last 90 days (expected — young repo; will rise over time) |
| ✓ | Packaging | tag-triggered package, SBOM, and GHCR release workflow is present |
| 3/10 | Pinned-Dependencies | dependency not pinned by hash detected — see note above |
| 0/10 | SAST | not run on all commits *(this pass adds `codeql.yml` + `zizmor.yml` — should rise once pushed)* |
| 10/10 | Security-Policy | `SECURITY.md` detected |
| ? | Signed-Releases | no releases found yet (tracked — issue #33) |
| **10/10** | **Token-Permissions** | **workflow tokens follow least privilege** |
| 10/10 | Vulnerabilities | 0 existing vulnerabilities detected |

## Reading the low scores honestly

Several 0-scores are expected and not concerning for a single-maintainer personal project
(Contributors, Code-Review, CII-Best-Practices, Fuzzing, Maintained-by-age) — Scorecard is tuned
for OSS projects with multiple contributors, and this repo declares itself single-user/personal in
`README.md` and `SECURITY.md`. The two that matter and are actionable:

- **Branch-Protection = 0** — real gap, not a scoring artifact. `ci.yml`'s header comment claims
  branch protection with no admin bypass; Scorecard confirms it is not actually configured on
  GitHub. ⛔ **BLOCKED (manual action needed)** — see the remediation log for the exact settings.
- **Pinned-Dependencies = 3** — partially addressed this pass (Docker base image now pinned by
  digest); re-run Scorecard after pushing to confirm the improved score.

## Next report

Due next: **2026-08** (or sooner, on demand — `scorecard.yml` also runs weekly and on every
`branch_protection_rule` change).
