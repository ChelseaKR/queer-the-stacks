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
- The accessibility gate now audits every HTML document the app serves, not two
  of the three. The share-card page reached the structural checker only through
  a unit test; the pa11y/axe, light/dark, and 320 px reflow layers never loaded
  it, because `app.build_static` never wrote it and `make a11y` scans what that
  writes. It is now built, audited in all gated modes (0 violations on first
  run), and `tests/test_a11y.py` asserts that every `HTMLResponse` route maps to
  an audited document, so the list cannot silently fall behind the app. The gate
  also refuses an empty page list instead of looping zero times and exiting 0.
- The coverage gate measures `ingest/cli.py`. It was omitted as "thin argparse
  glue"; it is 503 lines of refresh/doctor/import/export/list-authoring
  behaviour with three dedicated test files, and at 57% it was the
  least-covered module in the project while sitting outside the denominator the
  85% floor is computed from. Reported total moves from ~96.9% to ~94.1%.
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
- The no-egress guardrail now detects egress instead of grepping for four
  substrings while exempting the two modules that make every request (#62). It
  parses each first-party module's imports and asserts that the set of
  network-capable modules is *exactly* the KOReader sync client and the catalog
  client — equality, not an exemption list — and it runs ingest, view build,
  render, and every dashboard route with the socket layer trapped, so those
  paths cannot reach the network without failing the suite. The two permitted
  paths are asserted request-by-request below `requests.get`: exact outbound URL
  set, no request body, redirects off, and no library-derived string anywhere in
  the request. The old check for the literal string `.post(` is gone; a GET
  carries its payload in the URL, so it never tested its own name. The limits of
  what the guardrail can see are now written down in
  `docs/audits/reading-privacy.md` rather than implied by a test name.
- The KOReader sync client no longer follows redirects. `requests` drops an
  `Authorization` header when a redirect changes host but keeps arbitrary ones,
  so a hostile or compromised sync endpoint could have bounced `x-auth-user`,
  `x-auth-key` (the derived credential) and the document key to any host. The
  first hop is now the last one, and the document key is percent-encoded into a
  single path segment so it cannot reshape the URL.
- `/openapi.json` is no longer served (#63). `docs_url=None, redoc_url=None`
  closed two of FastAPI's three documentation surfaces; `openapi_url` was not
  set alongside them, so the schema — every private path, each route's
  query-parameter names, and the session cookie name — answered any anonymous
  request. No reading content was exposed, but on a host whose contents can out
  its owner, publishing what the application is and what its private routes are
  called is itself the disclosure.
- The auth test enumerates the route table instead of checking two paths. It
  verified 2 routes of 17, and the one route that had slipped through was not
  one of the two — it was registered by FastAPI rather than by this project's
  own code, which is exactly what a hand-written list of paths cannot cover.
  Every registered route must now answer 401 without credentials or appear in an
  explicit public list with the reason it is safe, so a new ungated route fails
  the build rather than being found later. Public routes are separately asserted
  to carry no reading content and to name no private route.
- Diverse-shelf analytics no longer render blank on a Calibre-only shelf. The
  reading filter excludes unread books by design, but without KOReader every
  book is unread, so a real 1,907-book library reported 0% coverage and no
  lenses — a blank panel that reads as "your shelf isn't diverse" rather than
  "nothing here knows what you have read". With no reading history at all the
  report now covers the whole shelf and labels itself as doing so; one read
  book restores the reading view.
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
