# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/) once it ships a first
release (see `docs/ROADMAP.md` REL-01/REL-05: pre-1.0, current line `0.1.x`).

## [Unreleased]

No release has been tagged yet. `v0.1.0` is pending: the release-lifecycle pipeline
(build/sign/SBOM/publish) and the pre-release accessibility/responsible-tech sign-offs are
tracked gaps — see README §Standards and `docs/audits/accessibility-2026-06-05.md`.

### Added
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
- Dependency security refresh: raised `starlette`/`msgpack` floors above known advisories (#10).
- Pinned all GitHub Actions `uses:` to full commit SHAs (#5).
- CI quick wins: least-privilege `permissions:`, SHA-pinning, blocking security gates (#4).
- CI fetches the pinned `/STANDARDS` at build time instead of vendoring it (#3).
- Accessibility gate graduated: `pa11y`/axe (real browser engine, incl. color-contrast) is now
  merge-blocking alongside the structural checker, closing the A11Y-03 honesty gap (2026-07-05).
- CI's secret scan now installs a pinned, checksum-verified `gitleaks` binary instead of silently
  falling back to the weaker grep pattern set, closing the SEC-18 honesty gap (2026-07-05).

### Fixed
- Dashboard/share-page CSS: elements now inherit an explicit, guaranteed-AA-contrast
  `color`/`background-color` pair instead of relying solely on the `color-scheme` hint, which had
  been failing `axe`'s color-contrast check (2026-07-05).
- `standards remediation`: `persist-credentials: false` on checkouts (#9).

### Security
- `pip-audit` clean (0 known vulnerabilities) on the Python 3.14 floor; empty accepted-advisory
  list (`docs/audits/residual-risk.md`).
