# Queer the Stacks — Implementation Roadmap

> Generic enforcement lives in `/STANDARDS`. This document carries the decisions and project-specific values.
> **Last verified: 2026-05-31 · Recheck cadence: per Calibre/KOReader schema + OpenLibrary/Hardcover/Bookwyrm API change.**

## 1. Snapshot
A self-hosted reading dashboard + recommender over your real ebook ecosystem: Calibre's `metadata.db` (SQLite), KOReader's `statistics.sqlite`, and `sync.koreader.rocks` progress. Unifies cross-device reading state, computes stats and a self-hosted Wrapped, and recommends queer/speculative work from ethical, non-gatekept catalogs. Runs on the Whatbox seedbox beside Calibre-Web; single-user; private.

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
- **ADR-1 — Pure HTML renderer audited statically, served live by FastAPI.** `app/render.py` is the single source of truth for dashboard *content*; `make a11y` renders it to a static artifact and gates it (pa11y/axe, or the built-in `app/a11y_check.py` fallback) so the mechanical WCAG checks run in CI without a live browser, and `app/server.py` serves the same HTML. *Rejected: testing a11y against a running server (flakier, needs a browser in CI).*
- **ADR-2 — Join Calibre ↔ KOReader by a normalized `title|first-author` key, with KOReader md5 as the progress key.** Robust to punctuation/case/spacing drift across the two stores; books read in KOReader but absent from Calibre are still surfaced so history is complete. *Rejected: ISBN-only joins (KOReader stats rarely carry ISBNs).*
- **ADR-3 — Auth fails closed; demo mode still requires a token.** Non-demo startup raises if `STACKS_AUTH_TOKEN` is unset (no accidental open instance); demo mode uses a fixed token so there is never an unauthenticated path. *Rejected: an "open in demo" bypass — a reading history is sensitive even in demos.*
- **ADR-4 — Python 3.14 floor; dependency audit clean.** The project targets **Python 3.14** (build + deployment interpreter 3.14.5). This lets every dependency install at a fixed release, so `pip-audit` reports **0 known vulnerabilities** and `make security` runs with no accepted advisories. (Superseded the interim 3.9 floor, under which fixes for `requests`/`urllib3`/`starlette` were not installable and had to be accepted as documented residual risk.) *Rejected: silently pinning vulnerable versions, or dropping the dep audit gate.*

## 7. Quality attributes & metrics
| Metric | Target | Measured by | Gate |
|--------|--------|-------------|------|
| Writes to Calibre/KOReader source DBs | 0 (read-only/snapshot) | DB-access test (asserts no write handle to source) | merge-blocking |
| Reading data leaving the instance | none | no-egress/no-telemetry test | merge-blocking |
| Goodreads requests | 0 | source-allowlist test | merge-blocking |
| "Why recommended" + source present | 100% of recs | explanation test | merge-blocking |
| Recommendation reproducibility (seeded) | deterministic | snapshot test | merge-blocking |
| axe violations (dashboard) | 0 | pa11y-ci | merge-blocking |
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

## 9. Go-to-market & community
- **Positioning.** "Your reading life, unified and private — with recs that respect your taste and values."
- **Marketing/comms.** A clean self-hosting + responsible-recommender story; pairs naturally with the music engine as a "values-aware discovery" theme.
- **Community.** Self-hosting guide; a documented, reusable "ethical book-data sources" list; contribution guide.

## 10. Legal & compliance
- **Catalog terms** (OpenLibrary, Hardcover, Bookwyrm) honored; **Goodreads excluded** on ToS + values grounds; attribution where required.
- **Privacy.** Reading data is sensitive (it can out a reader) → self-hosted, private, behind auth, never shared.

## 11. Operations & sustainability
- **Hosting/cost.** Runs on the existing Whatbox seedbox; negligible marginal cost.
- **Maintenance.** Re-snapshot on a schedule; resilient to Calibre/KOReader schema drift (versioned parsers).
- **Sustainability.** Single-user, self-hosted, no external dependencies for the core view.

## 12. Responsible-tech summary
Top risks: (1) corrupting your real Calibre/KOReader libraries → strictly read-only + snapshot-first (tested); (2) outing a reader by leaking sensitive reading data → self-hosted, private, no egress (tested); (3) recommendations that mirror gatekept, surveillance-heavy catalogs → ethical sources + diverse surfacing; (4) pigeonholing authors via auto-assigned identity labels → sourced theme tags only. Full treatment in [`RESPONSIBLE-TECH-AUDITS.md`](./RESPONSIBLE-TECH-AUDITS.md).
