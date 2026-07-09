## What & why

<!-- One or two sentences: what changed, and why. -->

## Definition of Done

See [`DEFINITION_OF_DONE.md`](../DEFINITION_OF_DONE.md) for the full checklist. At minimum:

- [ ] `make verify` is green locally.
- [ ] Tests added/updated for the behavior that changed.
- [ ] Docs updated (incl. `docs/audits/*` if a responsible-tech control changed).
- [ ] No secrets, tokens, or real library data in the diff.
- [ ] The four hard guardrails are intact (read-only source access; no reading data leaves the
      instance; no Goodreads/gatekept catalogs; sourced tags, never inferred author identity) —
      see `CONTRIBUTING.md` §Invariants.
- [ ] Commits are signed off (`git commit -s`) and follow Conventional Commits.

## If this touches a workflow or a dependency

- [ ] New/changed `uses:` are SHA-pinned with a version comment.
- [ ] No gate is muted (no `continue-on-error`, no `|| true`/`|| echo`).
- [ ] `uv.lock` updated in the same commit; `pip-audit`/`osv-scanner` clean or the exception is
      recorded in `docs/audits/residual-risk.md`.
