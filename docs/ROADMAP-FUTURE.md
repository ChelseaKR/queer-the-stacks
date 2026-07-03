# Queer the Stacks — Improvement & Expansion Plan

> Forward-looking companion to `ROADMAP.md` (which covers the shipped M0–M6).
> **Last verified: 2026-06-06 · Recheck cadence: per phase kickoff.**
>
> **Status (2026-06-06): N1–N6 shipped.** All phases below are implemented with
> `make verify` green (167 tests @ ~96% coverage, `mypy --strict`, lint,
> `pip-audit` 0 vulns, a11y 0 violations, recommender beats popularity). Deeper
> follow-ups remain open and are noted inline: live-network contract cassettes, a
> real (still-local) embedding model, Lighthouse/k6 in CI, and sidecar
> highlight-*text* import.

**Guiding constraint.** Every item below must hold the four hard guardrails or it
does not ship:

1. **Read-only / snapshot-first** access to Calibre `metadata.db` + KOReader
   `statistics.sqlite` — never a write handle to a real library.
2. **Reading data never leaves the instance** — no third-party analytics, no
   reading history sent to any catalog; egress confined to the user's own kosync
   server and public-metadata GETs.
3. **No Goodreads / no gatekept catalogs** — sources stay on the ethical
   allowlist with provenance.
4. **Describe books via sourced tags; never auto-label authors.**

---

## 0. Foundations & honesty gaps (do first)

The shipped build is demo-driven. Close the gap between "demo works" and "runs on
your real library" before adding features.

- **Real-library config + first-run wizard** — paths for Calibre/KOReader, kosync
  host/user/key, storage dir; a `stacks doctor` that validates paths, confirms
  read-only access, and reports detected schema versions. *(Phase N1)*
- **Persisted derived state** — a `data/` SQLite app-state store with a `stacks
  refresh` job and an "ingest only if the source mtime changed" guard; surface a
  "data as of …" freshness stamp. *(Phase N1)*
- **Live-path contract tests** — the live `KosyncClient` / `OpenLibraryClient` are
  `pragma: no cover` today; add recorded-cassette tests so parsers are exercised
  against real response shapes without network in CI. *(N2)*
- **Coverage honesty** — add TestClient route tests so `app/server.py` wiring is
  covered, not just the auth path. *(N1)*

## Deferred merge-blocking gates the standard names

- **Performance (Quality §2)** — k6/Locust smoke (p95 < 500 ms dashboard route) +
  Lighthouse-CI on the rendered HTML; make merge-blocking. *(N5)*
- **Reliability (Quality §5)** — restart-recovery test (reads persisted state) and
  a chaos test for "kosync down → degrade to KOReader-only". *(N5)*
- **Manual a11y sign-off** — perform + commit the dated VoiceOver/NVDA walkthrough.
  *(N1–N6, before first release)*

---

## A. Ingest & data breadth

1. **More read-only sources, same guardrails** — Readest progress, Kobo's native
   `KoboReader.sqlite`, Calibre-Web read-state, sideloaded EPUB/PDF. Each is a new
   adapter behind the existing `unify` join. **Kobo native (`ingest/kobo.py`)
   done** — snapshot-first `KoboReader.sqlite` reader over the `content` table
   (`ContentType = 6`, chapter-row dedup, schema-drift tolerant), merged through
   the existing `unify` join with zero changes to `ingest/unify.py`; wired into
   `ingest/config.py` (`[kobo]` / `STACKS_KOBO_DB`) and `ingest/refresh.py`.
   Readest, Calibre-Web read-state, and sideloaded EPUB/PDF remain open.
2. **Annotations & highlights** — surface a private, searchable "commonplace book"
   from KOReader highlights; never synced anywhere.
3. **Series & TBR intelligence** — "next in a series you own," progress through a
   series, a prioritized to-read shelf.
4. **Robust matching** — ISBN/OLID resolution + a fuzzy-match review queue for
   ambiguous Calibre↔KOReader joins (translations/editions).

## B. Recommender depth (the most differentiated surface)

1. **Hybrid model** — add a non-surveillance collaborative signal: co-occurrence
   of books across **public curated lists**, blended with the content model.
2. **Local semantic embeddings — local-only, optional (decided 2026-06-05).** A
   small embedding model running on the seedbox over sourced theme tags +
   descriptions, for semantic similarity beyond exact-tag overlap. **Strictly no
   egress; feature-flagged off by default.** Parked until the list-co-occurrence
   hybrid proves itself. *(N3)*
3. **Diversity / aperture controls** — a boost-only "lean into small-press /
   own-voices / translated / underread" slider (mirrors the values-lens pattern;
   "unknown" stays first-class, never penalized).
4. **Gentle negative signals** — opt-in DNF / low-dwell down-weighting, explained.
5. **Richer eval** — nDCG, catalog coverage, intra-list diversity, plus a real
   temporal hold-out on actual finishes; track metric drift across runs.

## C. Catalog & sourcing

1. **Hardened live adapters** — OpenLibrary, Hardcover (GraphQL), Bookwyrm
   federation behind the allowlist, with caching, rate-limit respect, and
   provenance on every field. *(N2)*
2. **Reusable "ethical book-data sources" list** — ship the GTM-promised,
   versioned data file others can reuse. *(N2)*
3. **Curated-list ingestion pipeline** — import named community lists (citation +
   `retrieved_at`); a refresh job flags rotted links. *(N2)*

## D. Experience

1. **Progressive-enhancement UI** — keep the static-render a11y contract; layer
   unobtrusive JS for filter/sort that degrades to the existing data tables.
2. **Wrapped, expanded** — monthly timelines, pace, theme evolution across years,
   an opt-in local PNG/PDF export (nothing auto-published).
3. **Search & browse** by sourced theme/genre, author, series, status.
4. **Goal tracking** — pages/books/streak goals, computed locally.

## E. Hardening, ops, distribution

1. **Containerize** + one-command compose for the seedbox next to Calibre-Web;
   documented reverse-proxy + auth.
2. **Auth upgrade path** — bearer token → optional OIDC/forward-auth; rate-limit
   the auth endpoint.
3. **Backups** of `data/` app state + a restore drill.
4. **Observability without telemetry** — local structured logs with a hard
   "no reading-content in logs" lint (extend the no-egress test family).
5. **Schema-drift CI** — a matrix of recorded Calibre/KOReader schema versions the
   parsers must handle.

---

## Suggested sequencing

| Phase | Theme | Rationale |
|-------|-------|-----------|
| **N1** | Real-library config + persisted state + `stacks doctor` | Turns the demo into a tool you actually run |
| **N2** | Hardened live catalog adapters + curated-list pipeline | Real recs, real provenance |
| **N3** | Hybrid + (optional, local) embedding recommender + richer eval | The differentiated core |
| **N4** | Annotations, series/TBR, search/browse | Daily-driver depth |
| **N5** | Containerize, backups, perf + reliability gates | Production-ready on the seedbox |
| **N6** | Interactive UI, expanded Wrapped, goals | Polish |

Each phase ends with `make verify` green and any new responsible-tech artifact
committed under `docs/audits/`.
