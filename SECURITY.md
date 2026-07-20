# Security Policy

Queer the Stacks is a **single-user, self-hosted** reading dashboard and recommender (AGPL-3.0-or-later). By
design it runs **private and local-only**: your Calibre and KOReader data are read **read-only**,
reading data never leaves the instance, there is no telemetry, and the dashboard serves **only
behind auth** (`401` without a valid `STACKS_AUTH_TOKEN`). That posture is the first line of
defense; this policy covers what to do when something slips past it.

## Supported versions

Queer the Stacks is pre-1.0, so **only the latest minor on the latest major receives security
fixes**. Fixes ship *forward* in a new patch release (a published version is never re-published).

| Version | Supported | Notes                                                    |
|---------|-----------|----------------------------------------------------------|
| 0.1.x   | ✅ Yes    | Current release line; receives security patches.         |
| < 0.1.0 | ❌ No     | Pre-release / unreleased; upgrade to 0.1.x.              |

When `0.2.0` ships, `0.1.x` security support ends and this table is updated in the same release.

## Reporting a vulnerability

**Please do not open a public GitHub issue, pull request, or discussion for a security report.**

Report privately, by either:

1. **GitHub Security Advisory** — open a draft advisory via *Security → Report a vulnerability* on
   the repository (preferred; keeps the report, fix, and GHSA linked), **or**
2. **Email** — `ckellyreif@gmail.com` with subject `SECURITY: queer-the-stacks`.

Please include, as far as you can:

- the affected version or commit and the mode (CLI ingest, served dashboard, or recommender),
- a minimal reproduction or proof-of-concept,
- the impact you believe it has, and
- any suggested remediation.

If you want an encrypted channel, say so in a first low-detail email and we will arrange one.

## Our commitments

| Stage                    | Target                                                                       |
|--------------------------|------------------------------------------------------------------------------|
| Acknowledgement & triage | **≤ 72 hours** from receipt                                                  |
| Severity assessment      | shared with you in the triage reply                                          |
| Fix or mitigation plan   | communicated after triage, prioritized by severity                           |
| Coordinated disclosure   | by mutual agreement; default embargo up to 90 days                           |
| Credit                   | named in the advisory unless you prefer to remain anonymous                  |

A fix ships forward in a new patch release, and the release notes reference the advisory (GHSA).

## Scope

In scope: the `queer-the-stacks` package and the `stacks` CLI, the ingest pipeline, the FastAPI
dashboard/app server, the recommender, the CI workflows, and the dependency supply chain (installs
resolve above known-vulnerable floors and are scanned in CI — `pip-audit`, a secret scan, a Trivy
container CVE scan, and SHA-pinned Actions).

Especially in scope, given the local-only design:

- any path that **writes to or could corrupt** the real Calibre `metadata.db` or KOReader
  `statistics.sqlite` (they must be opened strictly read-only; see
  [`docs/audits/library-safety.md`](docs/audits/library-safety.md)),
- any path that **exfiltrates reading data** off the instance (unexpected network egress,
  telemetry, or a leak in a generated share card), and
- any way to reach the dashboard or its data **without a valid auth token**.

Out of scope: **recommendation quality** and **representation correctness** are product/eval
concerns, not vulnerabilities — file those as normal issues. Accessibility regressions are a
merge-blocking quality gate, not a security report. There is no bundled corpus of secrets or PII;
the repository ships no credentials (secrets come from the environment only and are blocked in CI).

## Hardening notes for self-hosters

- Keep the deployment **single-user and behind auth**; set a strong `STACKS_AUTH_TOKEN` and never
  commit it. The dashboard returns `401` without it — keep it that way.
- Point ingest at **copies/snapshots** of your libraries where possible; the tool snapshots first
  and opens sources read-only, but least privilege on the files is still worth having.
- Provide the optional KOReader sync key via the environment (`STACKS_KOSYNC_KEY`), never a
  committed file.
- Run `make security` (dependency + secret scan) before deploying and stay on the pinned lockfile.
