# Project Scope

Last reviewed: 2026-07-08. Base branch: `main`.

This file is a plain-language map of the project as it exists on `main`. It does not replace the README, roadmap, audit docs, or source comments. It points to them so a reviewer can see the whole shape without reading every file first.

## What This Project Is

Queer the Stacks is a local-first reading-library tool. It ingests personal library sources, keeps adapters read-only, builds shareable views, and supports recommendation and diversity lenses with source ethics in mind.

Package metadata checked in this pass:

- Python package `queer-the-stacks` for Python `>=3.14`.

## Who It Serves

- Readers maintaining personal libraries in Calibre, KOReader, or related tools.
- Maintainers building privacy-aware book dashboards and recommendation surfaces.
- Reviewers checking source ethics, accessibility, and read-only ingest guarantees.

## What It Covers

- Read-only ingest adapters, snapshot logic, library unification, browse views, share cards, and wrapped-style summaries.
- Recommendation, diversity, shelf, stats, auth, and rendering code.
- Docs for roadmap, I18N, audits, ADRs, ethical sources, and responsible-tech review.
- Accessibility reports, scorecards, residual-risk notes, and data ethics docs.
- Tests covering ingest, rendering, privacy, a11y, and serving paths.

## How It Is Put Together

- ingest/ contains adapters and data-unification code.
- app/ contains browse, rendering, sharing, stats, server, and UI logic.
- docs/ holds ADRs, audits, roadmap, and source-ethics material.
- data/ is kept as a placeholder for local user data.
- tests/ exercises adapters and app outputs.

Observed source and operations surfaces:

- `Dockerfile`
- `Makefile`
- `app/`
- `docker-compose.yml`
- `ingest/`
- `pyproject.toml`
- `recommender/`
- `scripts/`

GitHub workflow files checked:

- `.github/workflows/ci.yml`
- `.github/workflows/codeql.yml`
- `.github/workflows/container-scan.yml`
- `.github/workflows/scorecard.yml`
- `.github/workflows/standards.yml`
- `.github/workflows/zizmor.yml`

## Trust Boundaries

- Adapters should read from library sources without modifying them.
- Book metadata and reading history can reveal identity and community, so privacy is part of the design.
- Recommendation lenses need sourced facts and should not infer identity from weak signals.

## Outside This Scope

- It is not a hosted social reading network.
- It cannot guarantee the ethics or license status of every external book-data source.
- The duplicate local symlink path should be handled carefully to avoid double-counting the repo.

## Docs And Evidence Checked

This pass checked 28 hand-authored doc or metadata files, 37 test files, and 6 workflow files on `main`. The count excludes vendored provider licenses, dependency folders, generated cache files, and large generated artifact history.

Primary docs checked:

- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/rulesets/README.md`
- `CHANGELOG.md`
- `CITATION.cff`
- `CODE_OF_CONDUCT.md`
- `CONTRIBUTING.md`
- `DEFINITION_OF_DONE.md`
- `LICENSE`
- `README.md`
- `SECURITY.md`
- `docs/I18N.md`
- `docs/RESPONSIBLE-TECH-AUDITS.md`
- `docs/ROADMAP-FUTURE.md`
- `docs/ROADMAP.md`
- `docs/adr/0000-record-architecture-decisions.md`
- `docs/adr/0001-static-render-audited-by-structural-checker.md`
- `docs/adr/0002-calibre-koreader-join-key.md`
- `docs/adr/0003-auth-fails-closed.md`
- `docs/adr/0004-python-314-floor.md`
- `docs/adr/0005-flat-non-src-layout.md`
- `docs/adr/0006-i18n-and-ai-evaluation-not-applicable.md`
- `docs/audits/accessibility-2026-06-05.md`
- `docs/audits/library-safety.md`
- `docs/audits/reading-privacy.md`
- `docs/audits/residual-risk.md`
- `docs/audits/scorecard-2026-07.md`
- `docs/audits/source-ethics.md`
- `docs/ethical-book-data-sources.md`

Representative test files checked:

- `tests/__init__.py`
- `tests/conftest.py`
- `tests/test_a11y.py`
- `tests/test_auth.py`
- `tests/test_backup.py`
- `tests/test_calibre.py`
- `tests/test_catalog_parsers.py`
- `tests/test_catalogs_lists.py`
- `tests/test_config.py`
- `tests/test_diversity.py`
- `tests/test_eval.py`
- `tests/test_explanation.py`
- `tests/test_goals_time.py`
- `tests/test_hybrid.py`
- `tests/test_koreader.py`
- `tests/test_kosync.py`
- `tests/test_log_safety.py`
- `tests/test_no_egress.py`
- `tests/test_observability.py`
- `tests/test_perf.py`
- `tests/test_polish.py`
- `tests/test_recommender.py`
- `tests/test_refresh_doctor.py`
- `tests/test_reliability.py`
- `tests/test_render_view.py`
- `tests/test_reproducibility.py`
- `tests/test_schema_drift.py`
- `tests/test_share.py`
- `tests/test_shelf_browse.py`
- `tests/test_snapshot_readonly.py`
- `tests/test_source_allowlist.py`
- `tests/test_sourced_tags.py`
- `tests/test_sources_registry.py`
- `tests/test_stats.py`
- `tests/test_store_serde.py`
- `tests/test_unify.py`
- `tests/test_wrapped.py`

## Validation Notes

For this docs PR, validation means the scope file was generated from the clean `origin/main` worktree, reviewed against repo metadata and docs inventory, and checked with `git diff --check`. Project test suites are still the authority for code behavior, because this PR changes documentation only.
