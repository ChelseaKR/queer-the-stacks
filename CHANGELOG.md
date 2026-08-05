# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/) once it ships a first
release (see `docs/ROADMAP.md` REL-01/REL-05: pre-1.0, current line `0.1.x`).

## [Unreleased]

No release has been tagged yet. `v0.1.0` is pending the pre-release
accessibility/responsible-tech sign-offs; the automated build, SBOM, GHCR,
keyless-signing/provenance, release, and verify-published lifecycle is in place.

### Added
- An explicitly opt-in public-metadata candidate pool for predeclared Open
  Library subjects and public BookWyrm lists, persisted per source with a
  visible last-good fallback, source age, and degraded-state reporting.
- A consent-based five-participant usability-study protocol and a dated
  real-library dogfood audit; no synthetic user findings are presented as
  research.
- Desktop and 320 px pa11y/axe gates for the daily dashboard.
- A "Time to finish" dashboard section: for each currently-reading book, an
  accessible table shows a ranged time-to-finish estimate from your recent
  reading pace (never a single number), computed locally by the existing
  `app.forecast` module; books without enough recent reading say so plainly
  rather than guess (EXP-04 dashboard wiring).
- Structured JSON request logging, `/livez`, and fail-closed `/readyz` (#13).
- `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (#12).
- Trivy container CVE scan, blocking on HIGH/CRITICAL (#11).
- `uv.lock` committed (#10).
- `CITATION.cff` (#9).
- Diverse-shelf analytics, reading time goals, and share cards (#6).
- Renovate dependency-update automation with GitHub Actions digest pinning (BL-8).
- Real-library config, persisted derived app state, `stacks doctor`/`refresh` (#1).
- Renamed project to Queer the Stacks; expansion phases N2–N6 (hybrid recommender,
  series/TBR, search/browse, container + backups, expanded Wrapped) (#2).
- Initial build: M0–M6, Python 3.14 (read-only Calibre/KOReader ingest, stats, Wrapped,
  ethical-catalog recommender with explanations, auth-gated self-hosted dashboard).

### Changed
- Reconciled the contradictory internationalization dispositions: the standard
  now applies, deferred to backlog #17's fork/audience decision; `docs/I18N.md`
  defines both decision paths and ADR 0007 supersedes only the i18n portion of
  ADR 0006. No catalog or translation is claimed.
- **Relicensed from MIT to AGPL-3.0-or-later** (sole-author relicense): keeps
  derivatives and network deployments open; prior released snapshots remain MIT.
- The daily homepage now follows a focused circulation-desk flow—continue,
  choose what is next, review recent returns, then browse—with detailed stats,
  provenance, lists, and source health in progressive disclosures.
- KOReader remote progress is refreshed on a bounded TTL even when the local
  statistics database mtime is unchanged; failed keys remain immediately
  retryable and retain last-good progress.
- The homepage previews at most 100 library rows while server-side search still
  covers the complete stored library.
- Dependency security refresh: raised `starlette`/`msgpack` floors above known advisories (#10).
- Pinned all GitHub Actions `uses:` to full commit SHAs (#5).
- CI quick wins: least-privilege `permissions:`, SHA-pinning, blocking security gates (#4).
- CI fetches the pinned `/STANDARDS` at build time instead of vendoring it (#3).
- Accessibility gate graduated: `pa11y`/axe (real browser engine, incl. color-contrast) is now
  merge-blocking alongside the structural checker, closing the A11Y-03 honesty gap (2026-07-05).
- CI's secret scan now installs a pinned, checksum-verified `gitleaks` binary instead of silently
  falling back to the weaker grep pattern set, closing the SEC-18 honesty gap (2026-07-05).

### Fixed
- `stacks recommend` reads the configured library through the app-state store
  instead of always printing demo fixtures. With sources configured it never
  falls back to the demo world: an unrefreshed store and an empty candidate
  pool are now distinct, actionable messages. Found by running the ingest
  against a real 1,907-book library, where three of the five fixture titles it
  printed were books already in that library.
- Sourced Calibre tags carry the date the library was actually read. The real
  ingest path never passed `retrieved_at`, so it silently took the
  `1970-01-01` default and stamped every citation with the epoch — 11,233 of
  them in the same real-library run.
- Author names restore the commas Calibre escapes as `|` in `authors.name`, so
  `Vine Deloria| Jr.` renders as `Vine Deloria, Jr.` (53 affected books in that
  library). The `authors.sort` column stores the same string already
  comma-formed, which confirms the convention rather than assuming it.
- Login form submission is now permitted by the CSP while its inline style
  remains hash-pinned. View-cache keys now include privacy mode, content
  fingerprints, catalog settings, and a monotonic store revision so
  sensitive/full or newly persisted catalog views cannot collide.
- Personalized runtime databases, SQLite sidecars, authored lists, catalog
  caches, active lens configuration, and `stacks.toml` are ignored; the tracked
  lens file is now a non-personalized example template.
- Dashboard/share-page CSS: elements now inherit an explicit, guaranteed-AA-contrast
  `color`/`background-color` pair instead of relying solely on the `color-scheme` hint, which had
  been failing `axe`'s color-contrast check (2026-07-05).
- `standards remediation`: `persist-credentials: false` on checkouts (#9).

### Security
- `pip-audit` clean (0 known vulnerabilities) on the Python 3.14 floor; empty accepted-advisory
  list (`docs/audits/residual-risk.md`).
