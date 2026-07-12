# Large-Scale Fixes (2026-07-01)

Deep structural fixes, net-new relative to `ROADMAP.md`, `ROADMAP-FUTURE.md`,
and the branch's `RESEARCH-ROADMAP.md` (R1–R12). Where a fix extends an
existing item, the item is cited and the delta stated. Effort: S ≈ a day ·
M ≈ 2–4 days · L ≈ 1–2 weeks · XL ≈ multi-week.

> Known nit, deliberately **not** counted as a fix: the `security` gate's
> `pip-audit` currently errors on the editable local install because the
> `queer-specfic-reader → queer-the-stacks` symlink yields two editable
> distributions. Environment/tooling issue, not structural work.

---

### FIX-01 — Wire real candidate acquisition into the serving path
**Pitch:** make the recommender recommend from live ethical catalogs, not the
demo pool, when a real library is configured.
**Why / for whom:** `app/view.py::view_from_store` unconditionally uses
`ingest.demo.demo_candidates()` + `DEMO_LISTS`; the live clients in
`recommender/catalogs.py` are never constructed by any serving path. The
headline claim ("sourced from OpenLibrary, Hardcover, and Bookwyrm") is not
yet true outside demo mode — the largest honesty gap on `main`, hitting the
owner/reader directly.
**Shape:** a `CandidatePool` step in `ingest/refresh.py`: derive subject
queries from top sourced themes (`recommender/model.py::TasteProfile`), fetch
via `OpenLibraryClient`/`BookwyrmClient` plus a new Hardcover client, pass
through `merge_candidates()`, persist with provenance + `retrieved_at` in the
store; `view_from_store` reads the persisted pool, demo pool only in demo mode
with a visible banner in `render.py`. Fetching lives in refresh, never in a
request — serve time stays no-egress.
**Effort:** L. **Risks/deps:** Hardcover token (key gate); document in
`docs/audits/reading-privacy.md` that queries are public theme labels, not
reading history; depends on branch R7 cassettes + R5/R11 posture; storage via
FIX-06.
**Excellent:** with a real library, ≥95% of rendered recs cite a non-demo
source; a merge-blocking test forbids `ingest.demo` imports on the real path;
network-down refresh degrades to the last pool with a dated staleness notice.

### FIX-02 — Consistent, verified snapshots of live source databases
**Pitch:** make snapshots safe *from* a mid-write Calibre/KOReader, not just
safe *for* them.
**Why / for whom:** `ingest/snapshot.py::snapshot` copies only the main DB
file via `shutil.copy2`. A live writer with an active WAL/journal can produce
a torn copy; `immutable=1` then suppresses SQLite recovery, so the snapshot
can fail to open or silently read inconsistent state. The guardrail protects
the source; nothing protects the reader's correctness.
**Shape:** copy `-wal`/`-shm`/`-journal` sidecars, or better use
`sqlite3.Connection.backup()` from a read-only source handle; run
`PRAGMA integrity_check` on the snapshot before yielding; retry once; record
hash + check result for `stacks doctor`. Keep the source-hash-unchanged test
(`tests/test_snapshot_readonly.py`); add a torn-copy fixture test.
**Effort:** M. **Risks/deps:** validate the read-only-URI + backup combination
against a genuinely busy Calibre library (real-data gate).
**Excellent:** a fault-injection test proves ingest either succeeds on retry
or fails loudly with a doctor-visible reason — never a silent inconsistent
read.

### FIX-03 — First-class work/edition identity across ingest and catalogs
**Pitch:** replace string-key joins with a persisted identity layer (work /
edition / document) with user-visible match decisions.
**Why / for whom:** everything joins on `normalize_key(title, first_author)`
(`ingest/unify.py`, `catalogs.py::merge_candidates`, ownership exclusion in
`recommender/model.py`). Translations, subtitle drift, and re-editions
mis-join or wrongly merge; the md5 secondary join the `unify.py` docstring
promises is unimplemented; `Book.identifiers` (ISBN/OLID) is parsed but never
used. Goes beyond ROADMAP-FUTURE A4's "fuzzy-match review queue": identity as
a data-model layer, not a heuristic.
**Shape:** an `ingest/identity` module — resolution order (identifier → md5
document → normalized key → unmatched), each match recorded with method +
confidence; a persisted override table ("stat X *is* book Y" / "never merge")
surviving refreshes (FIX-06); `unify()` consumes resolved identities;
`merge_candidates()` gains identifier-aware merging. Unmatched/low-confidence
joins surfaced in doctor and later the dashboard.
**Effort:** L. **Risks/deps:** FIX-06; needs an ADR (revisits ADR-2); build
the layer first, A4's queue UI second.
**Excellent:** a hard-case fixture corpus (translated title, subtitle drift,
same title/different author, edition split) yields 100% correct or explicitly-
unmatched — never a silent wrong merge; overrides round-trip through refresh.

### FIX-04 — Browser-native session auth (login → HttpOnly cookie)
**Pitch:** let a phone browser reach the dashboard without weakening
fail-closed auth.
**Why / for whom:** every content route requires an `Authorization: Bearer`
header (`app/server.py::require_auth`); browsers can't send one on navigation,
so the dashboard is reachable only via curl or a header-injecting proxy. A
structural usability hole in the primary daily surface. (ROADMAP-FUTURE E2's
OIDC path and R12's rate limiting are adjacent; the missing login flow itself
is unstated.)
**Shape:** a minimal `/login` page (same escaping + a11y discipline)
exchanging `STACKS_AUTH_TOKEN` for a signed HttpOnly `SameSite=Strict`
`Secure` cookie; `require_auth` accepts header or valid cookie; `/logout`;
constant-time checks stay in `app/auth.py`; failed-login rate limiting lands
here (subsumes that slice of E2/R12). All routes stay GET-only, asserted by
test, so CSRF exposure stays nil.
**Effort:** M. **Risks/deps:** expiry/tamper tests at `tests/test_auth.py`
grade; document the TLS assumption behind `Secure`.
**Excellent:** browser → login → dashboard, keyboard-only, 0 a11y violations;
401 on tampered/expired cookies; lockout test after N failures.

### FIX-05 — Defense-in-depth response headers (CSP, Referrer-Policy) — DONE
**Status:** implemented on `roadmap/fix-05-defense-in-depth-response-headers`:
`app/security_headers.py` derives the CSP's inline-script/style hashes from
`_FILTER_JS`/`_COPY_JS`/`_STYLE`/`_SHARE_STYLE` at import time; a
`SecurityHeadersMiddleware` in `app/server.py` (registered after
`RequestLoggingMiddleware`) sets the full header set on every response,
including 401s; citation links in `_sources_html` carry
`rel="noopener noreferrer external"` when external; `tests/test_security_headers.py`
covers every route plus a hash-drift test.
**Pitch:** make "reading data never leaves" hold against markup injection and
link-away leaks, not just intentional egress.
**Why / for whom:** the dashboard renders text from external catalogs —
escaped consistently in `app/render.py`, but one future escaping miss becomes
XSS inside an authenticated, deeply sensitive page. Citation links
(`_sources_html`) leak a `Referer` from the private dashboard to catalog
hosts. No CSP, `Referrer-Policy`, `X-Content-Type-Options`, or frame
protections exist today.
**Shape:** middleware in `app/server.py`: CSP (`default-src 'none'`, hashes
for the two inline scripts `_FILTER_JS`/`_COPY_JS` + inline style),
`Referrer-Policy: no-referrer`, `nosniff`, `frame-ancestors 'none'`, COOP;
`rel="noopener noreferrer external"` on outbound citation links; route tests
assert the header set everywhere, and a test computes the CSP hashes from
source so drift fails CI.
**Effort:** S–M. **Risks/deps:** inline-script edits must regenerate hashes —
the test makes that automatic.
**Excellent:** an injected `<script>` in a fixture catalog payload is inert
under CSP even with escaping deliberately disabled in a harness; zero referrer
leakage verified.

### FIX-06 — Store v2: schema-versioned, normalized derived state
**Pitch:** replace the single-JSON-blob KV store with versioned, queryable
tables and migrations.
**Why / for whom:** `ingest/store.py` keeps the whole library as one JSON
document; `ingest/serde.py` has no schema-version field, so model changes
break old stores with a raw `KeyError`; every read deserializes everything;
nothing is queryable. FIX-03 overrides, FIX-07 ledger, FIX-01 pool, EXP-06/07
all need real tables.
**Shape:** v2 schema — `meta(schema_version)`, `books`, `states`,
`daily_activity`, `candidate_pool`, `match_overrides`; `serde.py` retargeted
to rows; `migrations.py` upgrades v1 blobs in place; doctor reports store
version; public `Store` API (`load_states`, `save`, `refreshed_at`) kept
stable to minimize churn in `view.py`/`refresh.py`.
**Effort:** L. **Risks/deps:** migration tested against a committed v1 fixture
store; `ingest/backup.py` runs before migrate.
**Excellent:** lossless v1→v2 round-trip test; an old binary refuses a newer
store loudly with both version numbers; per-section loads stop deserializing
the whole library.

### FIX-07 — Append-only refresh ledger (longitudinal history)
**Pitch:** retain dated refresh events so the reading record survives device
resets and becomes analyzable across years — under explicit local retention
control.
**Why / for whom:** each refresh overwrites state (`Store.save`); KOReader's
`statistics.sqlite` is the only history and dies with the device.
ROADMAP-FUTURE D2 promises "theme evolution across years"; the data layer
can't answer it. A ledger is also *more* sensitive — retention must be a
first-class control.
**Shape:** post-FIX-06, append per-book status/progress deltas + activity
windows to `refresh_log`; `stacks history prune --keep <duration>` + config
default; update `docs/audits/reading-privacy.md` (ledger never leaves the
instance; export only via local `stacks export`). Multi-year views read the
ledger when present, KOReader when not, and say which.
**Effort:** M (after FIX-06). **Risks/deps:** FIX-06; privacy-review artifact
update (human gate); growth bounded by pruning.
**Excellent:** simulated device reset in a fixture — prior years' Wrapped
still renders, labeled "from local ledger"; prune verifiably deletes.

### FIX-08 — Batch + persist kosync progress (kill the N+1)
**Pitch:** refresh should cost O(changed books), not one sequential HTTP call
per book with silent failure.
**Why / for whom:** `ingest/unify.py::_progress_for` issues a synchronous GET
per stat during `unify()` (`KosyncClient.progress_for`) — a 500-book history
means 500 sequential requests per refresh — and swallows every exception
(`except Exception: return ()`), making outages invisible.
**Shape:** decouple fetching from `unify()`: a `fetch_progress(keys)` step in
`ingest/refresh.py` with bounded concurrency; per-key results cached in the
store with timestamps; re-fetch only keys whose stats changed; per-source
outcomes recorded in `RefreshResult` and surfaced via FIX-09. `unify()`
becomes pure again (takes a progress dict, not a live client).
**Effort:** M. **Risks/deps:** be polite to the user's sync server (R11's
spirit applied to kosync, which R11 doesn't cover); modest configurable
concurrency.
**Excellent:** 500-book fixture refresh performs ≤ changed-key fetches;
kosync-down degrades in one bounded timeout with a visible "progress stale
since <date>", not silence.

### FIX-09 — Degradation and freshness made legible on the dashboard
**Pitch:** the dashboard should say what it knows, how old it is, and what is
broken.
**Why / for whom:** `Store.refreshed_at()` exists but `app/render.py` never
renders it — N1's "data as of …" stamp is persisted, not shown. kosync
failures, missing sources, and stale stores are invisible at the surface the
user lives on. For a tool whose brand is honesty, silent staleness is
off-brand. (R1 covers the first real run; this is the permanent status
surface.)
**Shape:** a "Data status" section in `render.py` (with table equivalent):
refreshed-at, per-source state from the last `RefreshResult`
(calibre/koreader/kosync via FIX-08), candidate-pool age (FIX-01), store
version (FIX-06); a staleness banner past a configurable age; `stacks doctor`
warns on unknown `STACKS_*` env vars (today `STACKS_CALIBER_DB` is silently
ignored by `ingest/config.py`).
**Effort:** S–M. **Risks/deps:** full value needs FIX-08 outcomes, but the
stamp + env linting are standalone and cheap.
**Excellent:** every degraded state observable in demo mode is visible in
rendered HTML; a view test asserts stamp + per-source rows; zero new a11y
violations.
**Status (2026-07-03):** the standalone, non-FIX-08-dependent slice is done —
`render.py`'s new `_data_status_section` renders a "Data status" table with
the store's `refreshed_at` stamp as an ISO-8601 UTC string (or "never
refreshed — run `stacks refresh`" when absent), plus a text
`<p role="status">` staleness banner past a configurable threshold
(`app/view.py::STALE_AFTER_SECONDS`, default 7 days); `view.py` threads the
stamp + staleness through `DashboardView`/`build_view`/`view_from_store`; and
`ingest/refresh.py::doctor` now flags unrecognized `STACKS_*` env vars against
the exported `KNOWN_STACKS_ENV` set. Covered by `tests/test_render_view.py` and
`tests/test_refresh_doctor.py`; zero new a11y violations (`make a11y`).

### FIX-10 — Close the a11y gate-claim gap (real axe, reflow, keyboard) — DONE (deterministic slice)
**Status:** the deterministic, no-browser-needed slice is landed: `app/color_contrast.py`
(dependency-free WCAG 2.x contrast-ratio helper) + `app/share.py`'s SVG palette
hoisted into named, introspectable constants (`SVG_BG`/`SVG_BORDER`/
`SVG_HEADING`/`SVG_BODY`) + a merge-blocking `pytest` gate
(`tests/test_share.py::test_share_svg_palette_meets_aa`,
`::test_contrast_helper_flags_violation`) that fails CI on an injected
contrast violation — verified by flipping `SVG_BODY` to `#cccccc` and
confirming the test fails. Long share-card titles are now truncated in the
rendered SVG heading (`MAX_SVG_TITLE_CHARS`) so the fixed-width canvas can't
overflow; the accessible `<title>`/`aria-label` keep the untruncated text.
The browser-in-CI piece (Playwright + `@axe-core/playwright` against
`docs/audits/dashboard.html`/the share page, plus 320px-reflow and keyboard-
operability assertions) is **deferred**, per this item's own escape hatch
("if CI proves infeasible, amend §7 to name the static checker") — it is the
flaky/heavy piece requiring a headless browser in CI, tracked separately
rather than landed speculatively. `Makefile`'s `a11y` target still runs pa11y
best-effort (`|| echo …`) with the built-in `app/a11y_check.py` as the
authoritative, deterministic gate; that split is unchanged by this pass.
**Pitch:** make the merge-blocking a11y gate match what `ROADMAP.md` §7
claims; extend the mechanical floor.
**Why / for whom:** §7 declares "axe violations = 0 · pa11y-ci ·
merge-blocking", but the `Makefile` runs pa11y best-effort (`|| echo …`);
`app/a11y_check.py` is genuinely good but narrower than axe (no contrast, no
ARIA validity, no focus order). Also `app/share.py::render_share_svg`
hard-codes colors and doesn't wrap long titles — unverified contrast/overflow
on the one artifact designed to leave the instance.
**Shape:** run axe deterministically in CI via Playwright +
`@axe-core/playwright` against `docs/audits/dashboard.html` *and* the share
page (static input → no flakiness), blocking; keep the static checker as the
local fallback; add a 320px-reflow assertion and keyboard operability tests
for the filter input and copy buttons; contrast-check the SVG palette. If CI
proves infeasible, amend §7 to name the static checker — either way claim and
gate converge. Complements (never replaces) the branch's R2 human SR
walkthrough.
**Effort:** M. **Risks/deps:** headless-browser weight in CI (cacheable);
Lighthouse-CI stays separately deferred (ROADMAP-FUTURE §deferred gates).
**Excellent:** CI fails on an injected contrast violation; §7's row is
literally true; share cards verified AA with a long-title truncation test.

### FIX-11 — Sourced language & publisher facts in the data model
**Pitch:** give `Book` the fields the promised values-lenses require — sourced
facts with provenance, never guesses.
**Why / for whom:** ROADMAP-FUTURE B3 / branch E3 promise "small-press /
own-voices / translated / underread" widening, but `Book`
(`ingest/models.py`) has no language or publisher field and
`ingest/calibre.py` never reads Calibre's `languages`/`publishers` tables —
"translated" and "small-press" are unrepresentable, and
`rerank.py::aperture_boost` treats every novel theme label identically.
**Shape:** add `languages` (BCP-47, Calibre `languages` table) and
`publisher` to `Book`, populated only from library/catalog facts (OL edition
fields in the `catalogs.py` parsers) — facts about *books*, so the `Author`
guardrail is untouched; "small-press" derives from a *cited* press list
(a publisher `CuratedList` with citation + `retrieved_at`, reusing
`recommender/lists.py` validation), never a size heuristic; unknown stays
first-class. Extend `serde.py` (with FIX-06), `diversity.py` lenses, and
`aperture_boost` for dimension-aware boosts.
**Effort:** M. **Risks/deps:** FIX-06; the press list needs a cited editorial
owner (SME-adjacent); representation-review note for new lenses (human gate).
**Excellent:** a translated-fiction lens where every counted book carries a
sourced language fact with visible provenance; "publisher unknown" rendered
honestly; aperture can boost "translated" specifically, still boost-only.

### FIX-12 — Diversity lenses as validated user config
**Pitch:** move `DIMENSIONS` out of `app/diversity.py` into a validated,
documented config file.
**Why / for whom:** the lens grouping is meant to be personalized ("Edit it to
match your own shelf's vocabulary") but the only way is patching source —
breaking on update and quietly invalidating the "published in code" audit
claim. Config-with-validation keeps auditability *and* adaptability.
**Shape:** a `[lenses]` structure in `stacks.toml` (or `data/lenses.toml`)
parsed in `ingest/config.py`, validated like
`recommender/lists.py::validate_lists` (non-empty sets, no duplicate labels,
warn on zero-match descriptors); `compute_diversity()` takes lenses as a
parameter (already pure); the *active* definition rendered in the diversity
section so the view stays self-describing (extends branch R4's tag-provenance
UI with lens provenance); defaults = current constants.
**Effort:** S–M. **Risks/deps:** config errors degrade to defaults with a
visible warning (FIX-09 surface), never a blank section.
**Excellent:** rename a lens in TOML → dashboard reflects it, zero code
changes; invalid config yields a doctor error naming the line; the page states
exactly which grouping produced its numbers.

### FIX-13 — Eval that can fail: synthetic-world battery + margins
**Pitch:** replace one saturated fixture with seeded synthetic libraries and
require robust margins, so "beats popularity" is falsifiable.
**Why / for whom:** `docs/audits/eval-report.json` shows content and hybrid at
a perfect 1.0 on every metric over 5 positives — the demo fixture
(`ingest/demo.py`) is trivially separable, so the merge-blocking eval gate
can't catch a real regression short of catastrophe. Branch R6 adds better
*metrics* (temporal holdout, drift); this fixes the *test data and pass
criteria* — a different axis.
**Shape:** a seeded generator (library size, tag-vocabulary overlap,
popularity-vs-canon correlation, tag noise) beside `recommender/eval.py`; run
content/hybrid/popularity across N seeds; gate on median MAP@5 uplift with no
losing seed, replacing the single boolean; ablations (drop lists, shuffle 20%
of tags) with expected-ordering assertions; commit the protocol next to the
report. Offline, deterministic-by-seed, clearly labeled synthetic.
**Effort:** M. **Risks/deps:** thresholds need calibration to avoid flakes;
real-finish temporal holdout stays R6 and stays real-data-gated.
**Excellent:** setting `recommender/model.py::AUTHOR_BONUS = 0` fails the
gate; the saturated-1.0 report becomes a distribution the eval doc explains.

### FIX-14 — Serving-path lifecycle: startup checks, view cache, coverage
**Pitch:** requests become boring — validated at startup, cached between
refreshes, measured by coverage.
**Why / for whom:** `app/server.py::_load_view` re-resolves config, opens the
store, and can run a *full first-run ingest inside a request*; every request
rebuilds stats/wrapped/diversity/recommendations; no invalidation concept.
And `pyproject.toml` still omits `app/server.py` from coverage despite
existing TestClient tests — ROADMAP-FUTURE §0 "coverage honesty" declared,
not fully landed.
**Shape:** config + store validation in FastAPI lifespan, failing closed like
`app/auth.py::AuthNotConfigured`; cache the built `DashboardView` keyed on
`Store.refreshed_at()` + config hash (one cheap SELECT per request — the same
probe `/readyz` already does), invalidated when the stamp changes; first-run
ingest becomes an explicit startup step or a 503-until-refreshed state;
remove `app/server.py` from the coverage omit list.
**Effort:** M. **Risks/deps:** must respect `stacks refresh` running in
another process (the stamp check handles it); interacts with FIX-01/FIX-06.
**Excellent:** p95 dashboard latency flat as library size grows (extend
`tests/test_perf.py` with a large fixture); zero ingest work inside requests;
coverage includes server wiring with the ≥85% gate intact.
