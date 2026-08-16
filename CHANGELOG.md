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
- `stacks doctor` no longer reports a mid-write library's main table as missing
  (#60). `_check_source` was the one caller in the tree that passed a live path
  to `open_readonly`, whose `immutable=1` makes SQLite skip WAL recovery — so
  against a Calibre library that was open in Calibre-Web (the setup the README
  describes, and the moment a reader runs `doctor`) it read only the main file
  and announced `'books' table missing` for a healthy library. It now snapshots
  into a temporary directory and reads that, the same entry point `refresh`
  uses, so the diagnostic is no longer less accurate than the thing it
  diagnoses; it also reports when a sidecar shows the library is open elsewhere,
  rather than leaving a reader to interpret a surprising result. `open_readonly`
  now refuses a path with sidecars (`ReadOnlyViolation`, previously defined and
  unused), so the snapshot-first invariant is enforced rather than documented.
- The "Time to finish" basis line no longer overstates its sample (#61). The
  range is computed from days with pages turned, but the label counted every day
  in the record: with 30 days in the window of which 6 contributed, the
  dashboard said thirty. The basis line is the module's whole honesty mechanism,
  and `render.py` prints it verbatim, so a reader deciding whether to trust a
  range had been handed the wrong denominator.
- Removed `forecast_series`. It had no caller, and the number it needs —
  remaining pages across the *unread* books of a series — does not exist in the
  models: page counts arrive on `ReadingStat` (KOReader, so read books only) and
  `Book` carries none from Calibre. Its "up to ~N weeks at that pace" clause
  divided by an unstated 24-hours-a-day assumption while its own docstring said
  ~2 hours/day, a 12x discrepancy that sat under a green suite because the test
  covering the line asserted only that the word "weeks" appeared.
- The privacy toggle now redacts the lenses a reader configured, not only the
  twelve built-in descriptor strings (#59). `SENSITIVE_DESCRIPTORS` was computed
  once at import from the module defaults, so on a personalized
  `data/lenses.toml` the toggle redacted less than it said, and on a fully
  personalized one it redacted nothing while the page still said it had. What
  counts as sensitive is now resolved from the grouping actually in use: each
  `[[lenses]]` entry takes an optional `sensitive` flag that **defaults to
  true**, an unmarked or renamed custom lens fails closed, and the built-in
  identity descriptors are always unioned in so a custom file cannot un-redact
  them. The shipped template marks its four non-identity lenses `sensitive =
  false`, so copying it reproduces the built-in behaviour exactly.
- The privacy toggle now covers the whole page rather than one panel. It only
  ever reached the diverse-shelf section; the per-book theme chips, the library
  table's "Themes (sourced)" column, the stats theme mix, and the `/share` card
  all continued to publish the same descriptors. The first two are *more*
  revealing than the aggregated breakdown, not less, because they name the
  descriptor beside a specific title.
- The page no longer claims a redaction that did not happen.
  `DiversityReport.hide_sensitive` records only that the toggle was requested, so
  a new `redacted_descriptor_count` records what was actually removed and the
  rendered assurance keys off that. The copy now describes the mechanism
  ("descriptors on your sensitive list") rather than the outcome
  ("identity-adjacent"), since the code cannot know a label is identity-adjacent
  — only that it is on a list.
- Citation links are URLs a browser can resolve, and the dashboard says whose
  requests "outbound mode" governs. Subject citations interpolated the raw
  label, so a multi-word subject shipped as
  `href="https://openlibrary.org/subjects/science fiction"` — a href with a
  space in it, on the page that also reports "no public catalog requests are
  permitted". Subject URLs are now built with Open Library's own slug form, the
  renderer only presents a citation as a link if it passes the same allowlist,
  HTTPS, credential and whitespace checks the fetch path enforces (everything
  else stays visible as plain text), and the status row now reads "this
  instance makes no public catalog requests" with a note that following a
  citation is a request your browser makes, not one the instance makes (#70).
- Reading Wrapped no longer reports all-time hours under a year-scoped heading.
  "Standout reads of 2024 by time spent" listed each book's cumulative KOReader
  `total_read_time`, so the demo's top five summed to 78.0 hours inside a
  37.6-hour year — a number a reader checks in seconds and then stops trusting
  the rest of the page for. KOReader keeps no per-year total per book, so the
  figure stays what it is and the page now says what it is: the column reads
  "Hours (all time)", the caption explains the scope, and when the standouts do
  exceed the year it reconciles the two figures in place. `StandoutRead` carries
  the scope in its field name (`total_read_time_seconds`) so a future caller
  cannot re-make the assumption silently (#71).
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
