# 0005. Flat (non-src) package layout

* Status: accepted
* Date: 2026-07-05

## Context and Problem Statement

`STANDARDS/CODE-QUALITY-STANDARD.md` (CQ-23) expects either a `src/`-layout package or an explicit,
recorded rationale for deviating from it. This repo has kept `ingest/`, `recommender/`, and `app/`
at the repository root since the initial commit, without a recorded rationale — flagged by the
2026-07-05 conformance audit.

## Decision Drivers

* The project has always been installed editable (`pip install -e .` / `uv sync`) in CI, in the
  Docker build, and for local dev — the classic "flat layout accidentally imports the wrong thing
  because the repo root is on `sys.path`" failure mode that `src/`-layout guards against mainly
  bites non-editable, ad-hoc `python -m` invocations from the repo root without an install step,
  which this project doesn't do.
* Three top-level packages (`ingest`, `recommender`, `app`) plus `tests/`, `docs/`, `data/` are
  already a small, unambiguous top-level namespace — there's no `test_*.py`-shaped or
  same-named-as-a-dependency collision risk in practice.
* A `src/`-layout migration is a pure mechanical move (imports, `pyproject.toml` package-dir config,
  `Dockerfile` COPY lines, CI paths) with no functional benefit for a single-package personal
  project at this size — real but low-value churn.

## Considered Options

* Migrate now to `src/ingest`, `src/recommender`, `src/app`.
* Keep the flat layout, record the rationale here (this ADR), revisit if/when the project grows a
  second installable package or contributors report an accidental-import problem.

## Decision Outcome

Keep the flat layout. This ADR is the CQ-23/CQ-45 declaration the audit asked for. Revisit if this
project ever ships a second distributable package, adds a `src`-layout-dependent tool, or an
accidental same-name-import bug is actually observed — none of which apply today.
