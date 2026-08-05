# 0006. INTERNATIONALIZATION and AI-EVALUATION standards are not applicable

* Status: accepted
* Date: 2026-07-05

> **Partially superseded:** ADR 0007 supersedes the internationalization
> decision. The AI Evaluation decision below remains accepted.

## Context and Problem Statement

`STANDARDS/CODE-QUALITY-STANDARD.md` (CQ-45) asks for an ADR-style record backing any
standard-level N/A declaration, not just a one-line note. Two standards are declared N/A for this
repo: INTERNATIONALIZATION and AI-EVALUATION.

## Decision Outcome

**INTERNATIONALIZATION: N/A.** Single-user, English-only personal tool; the standard explicitly
permits this opt-out. Full declaration: [`docs/I18N.md`](../I18N.md) (I18N-02). `<html lang="en">`
is still set and gate-enforced regardless, as an accessibility floor rather than an i18n feature.

**AI-EVALUATION: N/A.** No LLM/GenAI SDK is used anywhere in this repo (verified: no
anthropic/openai/transformers imports). The recommender (`recommender/`) is a classic
content/co-occurrence model plus optional local hash embeddings — not generative, not LLM-backed.
The standard's evaluation rigor is applied anyway, just not through that standard: `make eval` is a
merge-blocking gate that fails unless the recommender beats a popularity baseline (see
`ingest/cli.py`, `docs/audits/eval-report.json`).

## Considered Options

* Silently omit both standards from any declaration (status quo before 2026-07-05 — flagged by the
  audit as itself a defect: "silent omission is a defect").
* Declare both N/A with a one-line reason only.
* Declare both N/A with a one-line reason **and** this ADR, so the reasoning is durable and
  addressable, not just a passing mention.

Chosen: the third option, matching CQ-45's ask.

## Links

* [`README.md` §Standards Conformance](../../README.md#standards-conformance)
* [`docs/RESPONSIBLE-TECH-AUDITS.md` §Applicability](../RESPONSIBLE-TECH-AUDITS.md)
* [`docs/I18N.md`](../I18N.md)
