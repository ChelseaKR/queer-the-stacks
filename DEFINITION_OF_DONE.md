# Definition of Done

A change (PR, or a direct commit for solo maintenance work) is done when **all** of the following
are true. This mostly transcludes [`CONTRIBUTING.md`](CONTRIBUTING.md)'s checklist and
[`docs/ROADMAP.md`](docs/ROADMAP.md) §7's gate table rather than restating them — see those for the
authoritative detail.

## Every change

- [ ] `make verify` is green locally (lint → typecheck → test ≥85% coverage → security → a11y →
      eval — [`Makefile`](Makefile), [`CONTRIBUTING.md`](CONTRIBUTING.md)).
- [ ] CI (`ci.yml`) is green on the PR.
- [ ] Tests are added or updated for the behavior that changed; no drop in coverage.
- [ ] Docs are updated when behavior, an interface, or a responsible-tech control changed — refresh
      the relevant note under [`docs/audits/`](docs/audits/) in the same PR
      ([`CONTRIBUTING.md`](CONTRIBUTING.md) §Invariants).
- [ ] No secrets, tokens, or real library data in the diff.
- [ ] The four hard guardrails are intact (read-only/snapshot source access; no reading data leaves
      the instance; no Goodreads/gatekept catalogs; sourced tags, never inferred author identity) —
      see [`CONTRIBUTING.md`](CONTRIBUTING.md) §Invariants. A PR that weakens one needs an explicit
      rationale and will usually be declined.
- [ ] Commit messages follow Conventional Commits and are signed off (`git commit -s`).

## If the change touches a workflow (`.github/workflows/**`)

- [ ] New/changed `uses:` are pinned to a full commit SHA with a version comment.
- [ ] No gate is muted (no `continue-on-error`, no `|| true`/`|| echo` swallowing a real failure).
- [ ] zizmor (`zizmor.yml`) has no new High/Critical findings.

## If the change touches a dependency

- [ ] `uv.lock` is updated in the same commit (CI's `uv sync --frozen` fails otherwise).
- [ ] `pip-audit` and `osv-scanner` are clean, or a new finding is recorded in
      [`docs/audits/residual-risk.md`](docs/audits/residual-risk.md) with a justification and owner
      *before* anything is ignored.

## Before the first tagged release (`v0.1.0`)

Tracked in [issue #33](https://github.com/ChelseaKR/queer-the-stacks/issues/33) and
[`docs/audits/accessibility-2026-06-05.md`](docs/audits/accessibility-2026-06-05.md):

- [ ] The tag-triggered release pipeline exists (build, re-run `make verify` at the tag, SBOM,
      cosign signing, verify-published).
- [ ] Manual accessibility walkthroughs (keyboard, screen reader, 200%/320px reflow, contrast) are
      signed off.
- [ ] Responsible-tech sign-offs (privacy, representation, framing, threat-model) are dated and
      current.
- [ ] `CHANGELOG.md` has a dated `## [0.1.0]` section (not just `[Unreleased]`).
