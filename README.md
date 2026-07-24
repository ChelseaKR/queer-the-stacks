# Queer the Stacks

**A private, self-hosted reading dashboard and recommender for Calibre and
KOReader.** It combines library metadata, reading statistics, and cross-device
progress into one view with streaks, a local "Reading Wrapped," and explainable
recommendations sourced from ethical, non-gatekept catalogs. The service is
designed for a single reader and can run on a home server or seedbox beside
Calibre-Web.

**Status:** `Beta` · **Track:** Personal (self-hosted web app + recommender) · **License:** MIT · **Data:** self-hosted/private

> **Build:** M0–M6 **plus expansion phases N1–N6** implemented on **Python
> 3.14**. `make verify` runs lint, strict typing, tests with coverage,
> dependency and secret scans, accessibility checks, and the offline
> recommender evaluation. Beyond the core dashboard, the project includes a
> persisted app-state store with `stacks doctor`/`refresh`, ethical catalog
> adapters behind a hard allowlist, a hybrid recommender, series/TBR browsing,
> container support, backups, local goals, and export. The dashboard fails
> closed without authentication. Human accessibility and representation review
> remain release gates; see [`docs/audits/`](./docs/audits/) and the
> [expansion plan](./docs/ROADMAP-FUTURE.md).

## Why it matters
Reading activity often lives across Calibre, KOReader, Calibre-Web, and mobile
readers, with no private view that ties it together. Mainstream recommenders
also tend to rely on gatekept, surveillance-heavy catalogs. Queer the Stacks
unifies local data and recommends from better sources without sending reading
history to a hosted analytics or recommendation service.

## What it does
- **One reading view:** cross-device "currently reading," progress, and history, read from Calibre + KOReader.
- **Stats & Wrapped:** pages, time, streaks, genre/theme mix, and a self-hosted year-in-review.
- **Diverse-shelf analytics:** a "how diverse is my reading" view — coverage, representation lenses, and provenance — built *only* from sourced book descriptors, never inferred author identity, with accessible chart + table equivalents.
- **Goals & streaks:** set local reading goals (books / pages / hours / streak) and track progress on the dashboard; computed on-device, shared with no one.
- **Share cards:** generate Bookwyrm/Mastodon-ready cards ("my year in books", a finished book) — composed locally and posted only when *you* copy and share them (no auto-egress).
- **Recommender:** tuned to the local reader's library, sourced from OpenLibrary, Hardcover, and Bookwyrm plus curated community lists — not Goodreads.
- **Every pick explained:** why + which source, with diverse/small-press surfacing rather than bestseller bias.
- **Self-hosted & private:** runs on your seedbox; reading data never leaves it.

## Quickstart

Try it in demo mode first — no real library needed:

```sh
make dev    # installs, then serves a demo dashboard at http://127.0.0.1:8765
```

To run it on your library, point it at your real, read-only sources and ingest
into the local app-state store:

```sh
export STACKS_CALIBRE_DB=/path/to/Calibre/metadata.db
export STACKS_KOREADER_DB=/path/to/koreader/statistics.sqlite
# optional cross-device progress (key from the env, never a file):
export STACKS_KOSYNC_HOST=https://sync.koreader.rocks STACKS_KOSYNC_USER=you STACKS_KOSYNC_KEY=…
stacks doctor     # validate paths + confirm read-only access (mutates nothing)
stacks refresh    # snapshot-first ingest into data/app-state.sqlite
uvicorn app.server:app   # serve the dashboard behind auth (set STACKS_AUTH_TOKEN)
```

Config can also live in `stacks.toml` (`[calibre] path=…`); env vars win.
`make verify` runs every checkable gate (CI parity). See
[`docs/ROADMAP-FUTURE.md`](./docs/ROADMAP-FUTURE.md) for the expansion plan.

## Guardrails

- **Source libraries are opened strictly read-only.** Calibre's `metadata.db`
  and KOReader's `statistics.sqlite` are never written to or put at risk of
  corruption; ingest snapshots/copies before reading.
- **Reading data is sensitive and never leaves the self-hosted instance:** no
  third-party analytics, no telemetry, and the dashboard sits behind auth on
  its host.
- **No Goodreads scraping** (Amazon ToS + gatekeeping). Recommendations are
  sourced from OpenLibrary, Hardcover, Bookwyrm, and curated community lists,
  with provenance.
- **Books and authors are described via *sourced* theme/genre tags,** never
  reductive auto-assigned identity labels.
- **Every recommendation shows why it was picked and which source it came
  from.**

Agent-facing build instructions (entrypoint, commands, definition of done) live
in [`CLAUDE.md`](./CLAUDE.md).

## Standards Conformance

`make verify` is the public, self-contained definition of the checkable merge
gate. Maintainer branches also check the pinned portfolio policy version in
[`.standards-version`](./.standards-version). Forked pull requests cannot
receive credentials for that private policy repository, so they run the full
local verification gate instead. Every policy area is declared below. *Last
verified: 2026-07-16.*

| Standard | Status | Notes |
|---|---|---|
| Quality & Metrics | **Applies** | `make verify` = lint → typecheck → test (≥85% branch coverage) → security → a11y → eval, identical locally and in CI (`ci.yml`). |
| Code Quality | **Applies** | ruff (incl. bandit `S` + mccabe `C90` complexity) + `mypy --strict`, both blocking; `.pre-commit-config.yaml` mirrors the fast checks locally. |
| Security & Supply-Chain | **Applies** | `pip-audit` (empty ignore list) + gitleaks (pinned binary in CI, `scripts/secret-scan.sh`) + Trivy container CVE scan, all merge-blocking; see `docs/audits/residual-risk.md`. |
| CI/CD | **Applies** | 3 workflows, all least-privilege (`permissions: contents: read`), all `uses:` SHA-pinned. |
| Release & Versioning | **Applies — automated lifecycle shipped; first release pending** | Pre-1.0 (`0.1.x` is the current, unreleased line per `SECURITY.md`). Signed annotated `v*` tags trigger exact-commit verification, package/SBOM and GHCR builds, keyless signing/provenance, GitHub Release publication, and post-publication verification. |
| Accessibility | **Applies** | Zero-violation gate from **two** blocking layers — a structural checker and pa11y/axe (browser-engine, incl. color-contrast; graduated from advisory 2026-07-05). Manual review-gate walkthroughs (keyboard, screen-reader, zoom/reflow, contrast) are still pending first release — see [`docs/audits/accessibility-2026-06-05.md`](docs/audits/accessibility-2026-06-05.md). |
| Observability | **Applies — Tier C** | Local-only, single-user, no network surface. Structured JSON logs, `/livez`, fail-closed `/readyz`, `/version` — see [`docs/ROADMAP.md` §Observability](docs/ROADMAP.md#observability) for the full per-signal N/A-with-reason declaration. |
| Internationalization | **Applies — deferred to backlog #17** | [`docs/I18N.md`](docs/I18N.md) now reconciles the manifest and prior single-user assumption; ADR 0007 defines the audience/fork decision paths and the first localization boundary. |
| AI Evaluation | N/A — no LLM/GenAI SDK anywhere; the recommender is a classic content/co-occurrence model | Has its own merge-blocking offline eval regardless (`make eval` — beats the popularity baseline); see [`docs/RESPONSIBLE-TECH-AUDITS.md`](docs/RESPONSIBLE-TECH-AUDITS.md#applicability--ai-evaluation-and-internationalization). |
| Documentation | **Applies** | This table, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CITATION.cff`, `CHANGELOG.md`, currency stamps throughout `docs/`. |
| Responsible-Tech Framework | **Applies** | Full A–F treatment, including an ASVS level declaration, in [`docs/RESPONSIBLE-TECH-AUDITS.md`](docs/RESPONSIBLE-TECH-AUDITS.md). |
