# Deep Dive — Current State (2026-07-01)

Assessment from a full read of `main` (HEAD `a19142c`, working tree clean) plus
the unmerged `research-panel-and-roadmap` branch. No tests or builds were run;
claims below are grounded in the files cited.

## 1. Architecture as actually built

Three packages, cleanly layered, all Python 3.14 (`pyproject.toml` floor
`>=3.14`; the code uses 3.14-only unparenthesized `except TypeError, ValueError:`
syntax, e.g. `ingest/calibre.py:103`, `ingest/kosync.py:56` — the repo genuinely
cannot run on older interpreters).

**Ingest** (`ingest/`): `snapshot.py` is the library-safety layer — copy-first
(`shutil.copy2`) then `mode=ro&immutable=1` + `PRAGMA query_only=ON`, entered
via `open_snapshot()`. `calibre.py`/`koreader.py` parse the source DBs with
schema-drift tolerance (`table_exists`/`columns` probing). `kosync.py` holds
the only reading-data network path (a `ProgressSource` protocol: live client +
fixture). `unify.py` joins everything by a normalized `title|first-author` key
into `ReadingState`. `store.py` persists derived state as JSON documents in a
single-table SQLite KV store (`data/app-state.sqlite`) via `serde.py`.
`refresh.py` orchestrates `stacks refresh`/`doctor` with an mtime-unchanged
skip; `config.py` resolves TOML + `STACKS_*` env (secrets env-only); `cli.py`
adds eval/recommend/backup/restore/export subcommands.

**Recommender** (`recommender/`): `model.py` — content scoring (theme-vector
cosine + author bonus + list bonus) over a `TasteProfile`; `collaborative.py` —
the non-surveillance collaborative signal (curated-list co-membership anchors);
`embeddings.py` — a dependency-free hashing embedder behind an `Embedder`
protocol, off by default; `rerank.py` — the boost-only aperture lens;
`hybrid.py` blends all four; `explain.py` guarantees every pick a non-empty
`Explanation` with sources; `catalogs.py` — the single network choke point with
`assert_allowed()` default-deny over `ALLOWED_HOSTS`/`BLOCKED_HOSTS`, pure
fixture-tested parsers for OpenLibrary/Hardcover/Bookwyrm, and `pragma: no
cover` live clients; `sources.py` — the in-code ethical-sources registry that
generates `docs/ethical-book-data-sources.md`; `eval.py` — precision/recall/
MAP/nDCG vs a popularity baseline plus intra-list diversity.

**App** (`app/`): `server.py` — FastAPI with `require_auth` on every content
route, `/livez`/`/readyz` probes, request-logging middleware; `view.py`
assembles one `DashboardView` used identically by the server, the static a11y
build (`build_static.py`), and `stacks export`; `render.py` — the pure,
escape-everything HTML renderer (ADR-1) with data-table equivalents for every
chart; `diversity.py` — the diverse-shelf analytics with honest denominators;
`stats.py`/`wrapped.py`/`goals.py`/`shelf.py`/`browse.py`/`share.py` — pure
functions; `a11y_check.py` — the dependency-free static WCAG checker that is the
authoritative CI a11y gate; `logging_config.py` — JSON logging with a hard
field allowlist and no query strings.

**Enforcement:** the four guardrails live in the *type system*
(`ingest/models.py`: `ThemeTag` cannot exist without a `Source`; `SourceKind`
is a closed enum with no inference-shaped member; `Author` has no identity
fields) and in structural tests (`tests/test_sourced_tags.py`,
`test_no_egress.py` scans source text for network/telemetry tokens outside
`kosync.py`/`catalogs.py`, `test_source_allowlist.py`,
`test_snapshot_readonly.py`). CI (`.github/workflows/ci.yml`) mirrors
`make verify`: ruff (+bandit subset), `mypy --strict`, pytest with ≥85%
branch coverage, pip-audit + secret scan, static a11y, offline eval gate;
`standards.yml` fetches the pinned private standards repo; `container-scan.yml`
runs Trivy. The suite is 196 test functions (~199 collected with
parametrization) across 36 files.

## 2. What is genuinely strong

- **Invariants as construction rules, not conventions.** You cannot build an
  unsourced descriptor or label an author anywhere in this codebase; the
  guardrails would have to be deleted from `ingest/models.py` to be violated.
  This is the strongest version of "honesty as a feature" in the portfolio.
- **One render path** (`app/view.py` → `app/render.py`) serving the live app,
  the CI a11y artifact, and the offline export identically — the a11y gate
  audits exactly what users see.
- **Honest denominators** in `app/diversity.py`: undescribed books are
  "unknown", never "not diverse"; lenses are a published, auditable grouping
  over sourced tags with the matched labels shown.
- **Privacy-hard logging**: `JsonLogFormatter._ALLOWED_EXTRA` is a field
  allowlist, so a future caller cannot widen the log surface; the core packages
  are enforced log-free (`tests/test_log_safety.py`).
- **Determinism everywhere** (stable sorts, injected "today", no RNG) makes the
  reproducibility gate real rather than aspirational.

## 3. Structural debt and gaps actually observed

1. **Real mode recommends from the demo catalog.** `app/view.py::view_from_store`
   (lines ~147–155) imports `ingest.demo.demo_candidates()` and
   `recommender.lists.DEMO_LISTS` unconditionally — even when the store holds a
   real library. The live `OpenLibraryClient`/`BookwyrmClient` in
   `recommender/catalogs.py` are never constructed by any serving path (only
   `refresh.py` constructs `KosyncClient`). The docstring admits it ("live
   catalog candidate pools land when configured"). The recommender — the
   differentiated surface — is not yet wired to real candidates.
2. **The 2026-06-30 research pass is stranded on an unmerged branch.**
   `docs/USER-RESEARCH.md`, `docs/RESEARCH-ROADMAP.md`, and the implemented
   R4/R5/R11 code (provenance UI in `app/diversity.py`/`render.py`, expanded
   `EthicalSource` compliance cards, etiquette headers) exist only on
   `research-panel-and-roadmap` (commit `d00224e`), which is now 6 commits
   behind `main` and overlaps files `main` has since changed
   (`docs/audits/coverage.xml`, `dashboard.html`, `recommender/sources.py`).
   `/Users/chelsea/portfolio/PORTFOLIO-RESEARCH-INDEX.md` links to
   `queer-the-stacks/docs/USER-RESEARCH.md` as if it were on `main`.
3. **Documented behavior that does not exist:** `ingest/unify.py`'s module
   docstring promises "KOReader md5 used as a secondary join when a stat
   carries one and a book records the same identifier" — the code joins only by
   `normalize_key`; `Book.identifiers` is never consulted. Similarly, N1's
   promised "data as of …" freshness stamp is persisted
   (`Store.refreshed_at()`) but never rendered — `app/render.py` has no
   freshness output at all.
4. **Snapshot consistency under a live writer.** `ingest/snapshot.py::snapshot`
   copies only the main DB file. If Calibre is mid-transaction (WAL/journal
   active), the copy can be torn — it cannot corrupt the source, but the
   snapshot may fail to open or silently reflect an inconsistent state, and
   `immutable=1` suppresses recovery. There is no integrity check after copy.
5. **The store is a JSON blob, unversioned.** `ingest/store.py` serializes the
   whole state under one key; `serde.py` has no schema-version field, so any
   model change breaks old stores with a raw `KeyError`, and each refresh
   overwrites history — nothing longitudinal survives a KOReader device reset.
6. **kosync is N+1 and silent.** `unify._progress_for` makes one synchronous
   HTTP GET per stat-carrying book during refresh (hundreds of sequential
   requests for a real library) and swallows every exception (`except
   Exception: return ()`), so a down sync server is indistinguishable from "no
   progress" on the dashboard.
7. **Browser reality of auth.** Every content route requires an
   `Authorization: Bearer` header (`app/server.py::require_auth`); a plain
   browser cannot send one on navigation. As shipped, the dashboard is only
   reachable via curl or a header-injecting reverse proxy — there is no login
   page, cookie session, or logout. (ROADMAP-FUTURE E2 names OIDC/forward-auth
   as the upgrade path; the day-one browser gap itself is unstated.)
8. **Gate honesty drift on a11y.** `ROADMAP.md` §7 lists "axe violations = 0,
   measured by pa11y-ci, merge-blocking", but the `Makefile` `a11y` target runs
   pa11y best-effort (`|| echo … built-in checker is authoritative`). The
   deterministic static checker is real and good; the *claimed* gate is axe.
9. **The data model cannot support promised lenses.** ROADMAP-FUTURE B3 / the
   branch's E3 want "small-press / own-voices / translated / underread"
   aperture dimensions, but `Book` (`ingest/models.py`) has no language or
   publisher field, and `ingest/calibre.py` never reads Calibre's `languages`
   or `publishers` tables. `rerank.py::aperture_boost` today boosts any
   new-to-you theme label equally — it cannot distinguish "translated" from
   "horror".
10. **Serving-path lifecycle.** `server.py::_load_view` re-reads config, opens
    the store, and (first run) performs a full ingest inside a request; there
    is no view cache keyed on `refreshed_at`, no staleness check on subsequent
    requests, and coverage still omits `app/server.py` (`pyproject.toml`
    `[tool.coverage.run] omit`) despite ROADMAP-FUTURE §0's "coverage honesty"
    line.
11. **Known operational nit:** the portfolio-level symlink
    (`queer-specfic-reader → queer-the-stacks`) makes `pip-audit` see two
    editable distributions and error in the `security` gate (recorded in
    `PORTFOLIO-RESEARCH-INDEX.md`). An environment problem, not an
    architecture problem — noted, not counted as a fix below.

## 4. Strategic position in the portfolio

This is the portfolio's cleanest demonstration of **"recommendation with an
explicit values lens"** — the same pattern as `women-artist-discovery`
(boost-only lens, unknown-is-first-class, sourced-not-inferred descriptors,
explanation on every pick), applied to the highest-privacy domain in the
portfolio (a reading history that can out someone). Its type-system-enforced
provenance is a reusable idea the other discovery repo could import rather than
re-implement. Its weaknesses are the mirror image: everything demo-path is
superb and gate-covered; everything real-world (live candidates, live library,
browser access, real eval data, merged research docs) is one step short of
proven. The highest-leverage work is closing the demo→real seam — which is also
exactly what the branch's R1 assurance sprint concluded, from the stakeholder
direction rather than the code direction. The two analyses converge, which is
itself a signal.
