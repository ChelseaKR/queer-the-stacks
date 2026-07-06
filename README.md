# Queer the Stacks

**A reading dashboard and recommender built on top of your actual ebook stack** — Calibre's library plus KOReader's reading stats and cross-device progress — that gives you one place to see what you're reading everywhere, your reading stats and streaks, a self-hosted "Reading Wrapped," and recommendations tuned to your canon (Plett, Peters, Thom, Butler, Atwood) sourced from ethical, non-gatekept catalogs. Self-hosted on your Whatbox seedbox next to Calibre-Web, single-user, private by design.

**Status:** `Beta` · **Track:** Personal (self-hosted web app + recommender) · **License:** MIT · **Data:** self-hosted/private

> **Build:** M0–M6 **plus expansion phases N1–N6** implemented on **Python 3.14**; all *checkable* `/STANDARDS` gates green via `make verify` (lint, `mypy --strict`, 167 tests @ ~96% coverage, dep-audit = **0 known vulnerabilities**, secret scan, a11y = 0 violations, recommender beats the popularity baseline). Beyond the core dashboard: a persisted app-state store with `stacks doctor`/`refresh`, ethical catalog adapters (OpenLibrary/Hardcover/Bookwyrm) behind a hard allowlist, a hybrid recommender (curated-list co-occurrence + optional **local-only** embeddings + a boost-only aperture lens), series/TBR + search/browse, container + backups, and an expanded private Wrapped with local goals + export. The dashboard serves only behind auth (401 without a valid token). Review-gated sign-offs (manual screen-reader walkthrough, privacy/representation review) pending first release — see [`docs/audits/`](./docs/audits/) and the [expansion plan](./docs/ROADMAP-FUTURE.md). Quickstart: `make install && make dev` (demo mode, no real library, no API key) · `make verify`.

## Why it matters
Your reading lives across Calibre (Mac), a Kobo running KOReader, Calibre-Web on the seedbox, and Readest on your phone, with KOReader progress syncing through `sync.koreader.rocks`. Nothing ties that together, and mainstream recommenders are both bad at trans/queer/speculative work and built on gatekept, surveillance-heavy catalogs. This unifies your own data and recommends from better sources — without ever leaving your control.

## What it does
- **One reading view:** cross-device "currently reading," progress, and history, read from Calibre + KOReader.
- **Stats & Wrapped:** pages, time, streaks, genre/theme mix, and a self-hosted year-in-review.
- **Diverse-shelf analytics:** a "how diverse is my reading" view — coverage, representation lenses, and provenance — built *only* from sourced book descriptors, never inferred author identity, with accessible chart + table equivalents.
- **Goals & streaks:** set local reading goals (books / pages / hours / streak) and track progress on the dashboard; computed on-device, shared with no one.
- **Share cards:** generate Bookwyrm/Mastodon-ready cards ("my year in books", a finished book) — composed locally and posted only when *you* copy and share them (no auto-egress).
- **Recommender:** tuned to your canon and tastes, sourced from OpenLibrary, Hardcover, and Bookwyrm plus curated community lists — not Goodreads.
- **Every pick explained:** why + which source, with diverse/small-press surfacing rather than bestseller bias.
- **Self-hosted & private:** runs on your seedbox; reading data never leaves it.

## For Claude Code
- **Build entrypoint:** [`docs/ROADMAP.md`](./docs/ROADMAP.md) → *Implementation Plan*.
- **Hard guardrails:** **open Calibre's `metadata.db` and KOReader's `statistics.sqlite` strictly read-only** (never write to or risk corrupting the real libraries — copy/snapshot before reading); **reading data is sensitive and never leaves the self-hosted instance** (no third-party analytics, no telemetry, behind auth on the seedbox); **do not scrape Goodreads** (Amazon ToS + gatekeeping) — source recommendations from OpenLibrary/Hardcover/Bookwyrm/curated lists with provenance; books and authors are described via *sourced* theme/genre tags, never reductive auto-assigned identity labels; every recommendation shows why + source.
- **Commands:** `make dev` · `make verify` · `make a11y` · `make eval`.
- **Run it on your library:** point it at your real, read-only sources and ingest into the local app-state store —
  ```sh
  export STACKS_CALIBRE_DB=/path/to/Calibre/metadata.db
  export STACKS_KOREADER_DB=/path/to/koreader/statistics.sqlite
  # optional cross-device progress (key from the env, never a file):
  export STACKS_KOSYNC_HOST=https://sync.koreader.rocks STACKS_KOSYNC_USER=you STACKS_KOSYNC_KEY=…
  stacks doctor     # validate paths + confirm read-only access (mutates nothing)
  stacks refresh    # snapshot-first ingest into data/app-state.sqlite
  uvicorn app.server:app   # serve the dashboard behind auth (set STACKS_AUTH_TOKEN)
  ```
  Config can also live in `stacks.toml` (`[calibre] path=…`); env vars win. See [`docs/ROADMAP-FUTURE.md`](./docs/ROADMAP-FUTURE.md) for the expansion plan.
- **Definition of done:** a single self-hosted dashboard shows your real cross-device reading state and stats from Calibre + KOReader, plus explainable recommendations from ethical sources — read-only against your libraries, private to your seedbox, all `/STANDARDS` gates green.

## Standards
Inherits [`/STANDARDS`](../STANDARDS/). Per `/STANDARDS/README.md` §"How a repo declares
conformance," every standard is declared below — silent omission is itself a defect, so nothing
here is left unstated. *Last verified: 2026-07-05.*

| Standard | Status | Notes |
|---|---|---|
| QUALITY-AND-METRICS | **Applies** | `make verify` = lint → typecheck → test (≥85% branch coverage) → security → a11y → eval, identical locally and in CI (`ci.yml`). |
| CODE-QUALITY | **Applies** | ruff (incl. bandit `S` + mccabe `C90` complexity) + `mypy --strict`, both blocking; `.pre-commit-config.yaml` mirrors the fast checks locally. |
| SECURITY-AND-SUPPLY-CHAIN | **Applies** | `pip-audit` (empty ignore list) + gitleaks (pinned binary in CI, `scripts/secret-scan.sh`) + Trivy container CVE scan, all merge-blocking; see `docs/audits/residual-risk.md`. |
| CI-CD | **Applies** | 3 workflows, all least-privilege (`permissions: contents: read`), all `uses:` SHA-pinned. |
| RELEASE-AND-VERSIONING | **Applies — first release pending, gap tracked in [#33](https://github.com/ChelseaKR/queer-the-stacks/issues/33)** | Pre-1.0 (`0.1.x` is the current, unreleased line per `SECURITY.md`). `CHANGELOG.md` exists; the tag-triggered build/SBOM/signing pipeline does not yet — tracked, not silently missing. |
| ACCESSIBILITY | **Applies** | Zero-violation gate from **two** blocking layers — a structural checker and pa11y/axe (browser-engine, incl. color-contrast; graduated from advisory 2026-07-05). Manual review-gate walkthroughs (keyboard, screen-reader, zoom/reflow, contrast) are still pending first release — see [`docs/audits/accessibility-2026-06-05.md`](docs/audits/accessibility-2026-06-05.md). |
| OBSERVABILITY | **Applies — Tier C** | Local-only, single-user, no network surface. Structured JSON logs, `/livez`, fail-closed `/readyz`, `/version` — see [`docs/ROADMAP.md` §Observability](docs/ROADMAP.md#observability) for the full per-signal N/A-with-reason declaration. |
| INTERNATIONALIZATION | **N/A** — single-user, English-only personal tool (explicit opt-out permitted by the standard) | See [`docs/I18N.md`](docs/I18N.md). |
| AI-EVALUATION | **N/A** — no LLM/GenAI SDK anywhere; the recommender is a classic content/co-occurrence model | Has its own merge-blocking offline eval regardless (`make eval` — beats the popularity baseline); see [`docs/RESPONSIBLE-TECH-AUDITS.md`](docs/RESPONSIBLE-TECH-AUDITS.md#applicability--ai-evaluation-and-internationalization). |
| DOCUMENTATION | **Applies** | This table, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CITATION.cff`, `CHANGELOG.md`, currency stamps throughout `docs/`. |
| RESPONSIBLE-TECH | **Applies** | Full A–F treatment, including an ASVS level declaration, in [`docs/RESPONSIBLE-TECH-AUDITS.md`](docs/RESPONSIBLE-TECH-AUDITS.md). |
