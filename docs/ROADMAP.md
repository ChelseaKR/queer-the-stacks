# Queer the Stacks — Implementation Roadmap

> Generic enforcement lives in `/STANDARDS`. This document carries the decisions and project-specific values.
> **Last verified: 2026-07-05 · Recheck cadence: per Calibre/KOReader schema + OpenLibrary/Hardcover/Bookwyrm API change.**

## 1. Snapshot
A self-hosted reading dashboard + recommender over a reader's ebook ecosystem:
Calibre's `metadata.db` (SQLite), KOReader's `statistics.sqlite`, and optional
KOReader sync progress. It unifies cross-device reading state, computes stats
and a self-hosted Wrapped, and recommends queer/speculative work from ethical,
non-gatekept catalogs. It is designed for a single-user home server or seedbox
deployment beside Calibre-Web.

## 2. Problem & users
- **Problem.** Reading is fragmented across Calibre/KOReader/Readest with no unified view, and mainstream recommenders are bad at trans/queer/spec-fic and built on surveillance-heavy, gatekept catalogs.
- **Primary user.** You (single-user, self-hosted).
- **Jobs to be done.** "Show me what I'm reading everywhere, in one place." · "Give me good queer/spec-fic recs from sources I trust." · "Keep my reading life private."
- **Evidence basis.** Your Calibre library + KOReader stats are ground truth; recommender quality judged against your canon and held-out reads.

## 3. Product definition
- **Vision.** Your reading life, unified and private, with recommendations that actually fit your taste and values.
- **Scope (MoSCoW).**
  - *Must:* read-only Calibre + KOReader ingest; cross-device currently-reading + progress + history; reading stats; recommender from ethical sources with per-pick explanation; self-hosted behind auth.
  - *Should:* self-hosted Reading Wrapped; KOReader sync-server progress integration; theme/genre browsing; "to-read" shelf.
  - *Could:* federated Bookwyrm activity import; reading-goal tracking; export.
  - *Won't (v1):* writing back to Calibre/KOReader; Goodreads scraping; any public/social exposure of your reading.
- **Non-goals.** Not a public profile; not a Goodreads clone; not a library editor.

## 4. Research & evidence
- **Schema mapping.** Map Calibre `metadata.db` (books, authors, tags, series, identifiers) and KOReader `statistics.sqlite` (per-book read time, pages, sessions); confirm read-only access and a snapshot-before-read approach.
- **Ethical sourcing.** OpenLibrary + Hardcover (API) + Bookwyrm (federated) as primary catalogs; curated queer-lit community lists for canon grounding; document why Goodreads is excluded (ToS + gatekeeping + surveillance).
- **Representation method.** Use *sourced* theme/genre tags (own-voices, trans, queer, speculative) from catalogs/lists; never auto-assign identity labels to authors.

## 5. Experience & design
- **Dashboard.** A calm, legible reading home: currently-reading across devices, recent finishes, stats, and a recommendations rail with "why + source" on every card.
- **Wrapped.** A self-hosted year-in-review (counts, time, themes, standout reads) — private, no third-party service.
- **Accessibility.** Keyboard-complete, charts have data-table equivalents, theme tags not color-only. Release gate.

## 6. Architecture
- **Shape.** Python service (FastAPI) reading from read-only copies/snapshots of `metadata.db` and `statistics.sqlite`, plus the KOReader sync endpoint; SQLite for derived/app state; a light web UI; deployed on the seedbox behind auth, alongside Calibre-Web.
- **Recommender.** Content-based over your library's themes/tags/authors + ethical-catalog lookups + curated lists; explanation layer attaches reasons + source to each pick.
- **Key decisions (ADRs).** Read-only + snapshot of source DBs (rejected: live writes — risk of corrupting real libraries). FastAPI + light UI over Streamlit (slightly more polish for a self-hosted daily app). Ethical catalogs over Goodreads (ToS + values). Sourced theme tags over auto-labeling authors (avoids pigeonholing).

### ADRs recorded during the M0–M6 build (2026-06-05)
Ported to [`docs/adr/`](adr/) (MADR format, append-only) on 2026-07-05 — see
[0001](adr/0001-static-render-audited-by-structural-checker.md),
[0002](adr/0002-calibre-koreader-join-key.md),
[0003](adr/0003-auth-fails-closed.md),
[0004](adr/0004-python-314-floor.md), plus two new ones added directly there:
[0005](adr/0005-flat-non-src-layout.md) (flat layout rationale) and
[0006](adr/0006-i18n-and-ai-evaluation-not-applicable.md) (I18N/AI-EVAL N/A declarations). This
section is kept as a short pointer rather than a duplicate; the full text with rejected
alternatives lives at the links above.

## 7. Quality attributes & metrics
| Metric | Target | Measured by | Gate |
|--------|--------|-------------|------|
| Writes to Calibre/KOReader source DBs | 0 (read-only/snapshot) | DB-access test (asserts no write handle to source) | merge-blocking |
| Reading data leaving the instance | none | no-egress/no-telemetry test | merge-blocking |
| Goodreads requests | 0 | source-allowlist test | merge-blocking |
| "Why recommended" + source present | 100% of recs | explanation test | merge-blocking |
| Recommendation reproducibility (seeded) | deterministic | snapshot test | merge-blocking |
| axe violations (dashboard) | 0 | `app/a11y_check.py` (structural, blocking) **+** pa11y/axe (browser-engine, incl. contrast — graduated to blocking 2026-07-05) | merge-blocking |
| Auth on the self-hosted app | required | access test | merge-blocking |
| Coverage | ≥ 85% / ≥ 80% | coverage | merge-blocking |

**Testing.** Unit (schema parsers, stats math, recommender, explanation), integration (read-only DB access, OpenLibrary/Hardcover/Bookwyrm adapters with fixtures), eval (recommender fit vs your canon/held-out reads), a11y.

## 8. Implementation plan for Claude Code
```
ingest/      (calibre + koreader read-only readers, kosync client)
recommender/ (content model, catalog adapters, lists, explain)
app/         (fastapi + web ui: dashboard, stats, wrapped)
data/        (derived app state, sqlite)
docs/
```
- **M0 — Scaffold & gates.** Repo + CI (`/STANDARDS` gates + axe + read-only + no-egress tests). *Done when `make verify` is green and the read-only/no-egress tests exist and pass.*
- **M1 — Ingest (read-only).** Snapshot + parse Calibre + KOReader; KOReader sync progress. *Done when cross-device currently-reading + history render from real data without touching source DBs.*
- **M2 — Stats + Wrapped.** Reading stats and a self-hosted year-in-review. *Done when stats reconcile with KOReader and Wrapped renders.*
- **M3 — Recommender.** Content model + ethical-catalog adapters + curated lists. *Done when recs fit your canon better than a popularity baseline.*
- **M4 — Explanations + browse.** Why + source on every pick; theme/genre browsing. *Done when 100% of recs are explained with sources.*
- **M5 — Self-host hardening.** Auth, deploy beside Calibre-Web, backups of app state. *Done when the app is reachable only behind auth and survives a restart.*
- **M6 — Polish.** To-read shelf, goals, export. *Done when all §7 gates pass.*
- **Claude Code approach.** Treat the real libraries as sacred (read-only, snapshot first); allowlist outbound hosts (no Goodreads, no analytics); explain and source every recommendation.

## 9. Community
- **Community.** Self-hosting guide; a documented, reusable "ethical book-data sources" list; contribution guide.

## 10. Legal & compliance
- **Catalog terms** (OpenLibrary, Hardcover, Bookwyrm) honored; **Goodreads excluded** on ToS + values grounds; attribution where required.
- **Privacy.** Reading data is sensitive (it can out a reader) → self-hosted, private, behind auth, never shared.

## 11. Operations & sustainability
- **Hosting/cost.** Runs on an existing home server or seedbox; negligible marginal cost.
- **Maintenance.** Re-snapshot on a schedule; resilient to Calibre/KOReader schema drift (versioned parsers).
- **Sustainability.** Single-user, self-hosted, no external dependencies for the core view.

## 12. Responsible-tech summary
Top risks: (1) corrupting your real Calibre/KOReader libraries → strictly read-only + snapshot-first (tested); (2) outing a reader by leaking sensitive reading data → self-hosted, private, no egress (tested); (3) recommendations that mirror gatekept, surveillance-heavy catalogs → ethical sources + diverse surfacing; (4) pigeonholing authors via auto-assigned identity labels → sourced theme tags only. Full treatment in [`RESPONSIBLE-TECH-AUDITS.md`](./RESPONSIBLE-TECH-AUDITS.md).

## Observability
The checkable gates are implemented by this repository's `Makefile` and CI
workflows; this section records this project's observability values and its
N/A-with-reason declarations.

**Tier — C (local-only, single-user, no network surface).** The app is self-hosted beside Calibre-Web, binds to localhost, and never egresses (§/no-egress test). Per §0/§10 the OTel signals are **out-of-scope, N/A-with-reason**:
- **OTel traces (§1) — N/A:** no cross-service surface; a single local process with no collector to export to.
- **OTel metrics / RED·USE (§2) — N/A:** no metrics backend; single-user local service.
- **SLOs / error budgets (§4) & burn-rate alerting (§5) — N/A:** not a shared/hosted service; no on-call.
- **Core Web Vitals / Lighthouse (§8) — N/A:** server-rendered HTML audited statically by the a11y gate; no SPA RUM surface.
- **Continuous profiling (§9) — N/A:** local single-user process.

What this repo **does** ship on its self-hosted service surface (for the seedbox deployment's probe contract and local debuggability):

| Metric | Target | Measured by | Gate | Owner |
|--------|--------|-------------|------|-------|
| No secrets/PII/reading-data in logs (§3, non-tiered) | zero — logs carry only method, path (no query string), status, latency, request id | `tests/test_observability.py` + `tests/test_log_safety.py` (core stays log-free) | merge-blocking | Maintainer |
| Structured JSON logs (§3) | one valid JSON object per line; fields `ts, level, msg, request_id, method, path, status, latency_ms` | `tests/test_observability.py` (parse + field-set assertion) | merge-blocking | Maintainer |
| Logs never egress (§3/§10) | stdout only; no network log handler; `propagate=False` | `tests/test_observability.py` + `tests/test_no_egress.py` | merge-blocking | Maintainer |
| `/livez` (§6) | 200 `{"status":"ok"}`, no dependency calls, unauthenticated | `tests/test_observability.py` | merge-blocking | Maintainer |
| `/readyz` (§6) | 200 when the app-state store is reachable; **fail-closed 503** otherwise, leaking no internal detail | `tests/test_observability.py` (ready + stubbed-down cases) | merge-blocking | Maintainer |
| Probes excluded from access logs (§6) | `/livez`,`/readyz`,`/healthz` produce no request log line | `tests/test_observability.py` | merge-blocking | Maintainer |

Logging is confined to `app/logging_config.py` + its wiring in `app/server.py`; the core (`ingest`/`recommender` + pure `app` modules) stays log-free so reading content has no path into the log stream.
