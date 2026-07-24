# 0007. Internationalization applies pending fork reconciliation

* Status: accepted
* Date: 2026-07-23
* Supersedes: ADR 0006's internationalization decision only

## Context and Problem Statement

ADR 0006 declared internationalization N/A because the product was described
as a single-user English-only personal tool. The portfolio applicability
manifest later kept the standard applicable pending reconciliation with the
`queer-specfic-reader` fork/symlink and backlog #17. The repository therefore
claimed both N/A and Applies at once.

## Decision Outcome

Use the conservative disposition: internationalization applies, deferred to
backlog #17's repository/audience reconciliation. `docs/I18N.md` owns the
scope, fallback, and decision paths. No catalog or translation claim is made.

ADR 0006 remains accepted for AI Evaluation, which is still N/A because the
product uses no LLM/GenAI SDK and its classic recommender has a separate
merge-blocking evaluation.

## Consequences

- The README, applicability manifest, ADR log, and declaration no longer
  contradict one another.
- A broader audience cannot inherit an accidental single-user exemption.
- A future N/A decision requires a new ADR with evidence that the product and
  repository boundary remain strictly single-operator.
- A future localization implementation starts from the user-facing boundary
  in `docs/I18N.md`, not from ad hoc string replacement.
