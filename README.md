# Queer the Stacks

**A private, self-hosted reading dashboard and recommender for Calibre and
KOReader.** It combines library metadata, reading statistics, and cross-device
progress into one view with streaks, a local "Reading Wrapped," and explainable
recommendations sourced from ethical, non-gatekept catalogs. The service is
designed for a single reader and can run on a home server or seedbox beside
Calibre-Web.

**Status:** `Beta` · **Track:** Personal (self-hosted web app + recommender) · **License:** AGPL-3.0-or-later · **Data:** self-hosted/private

> **Build:** M0–M6 **plus expansion phases N1–N6** implemented on **Python
> 3.14**. `make verify` runs lint, strict typing, tests with coverage,
> dependency and secret scans, accessibility checks, and the offline
> recommender evaluation. Beyond the core dashboard, the project includes a
> persisted app-state store with `stacks doctor`/`refresh`, ethical catalog
> adapters behind a hard allowlist, an opt-in persisted candidate pool, a hybrid
> recommender, series/TBR browsing,
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
- **Recommender:** tuned locally to the reader's library, using a persisted
  candidate pool from opt-in broad Open Library subjects and explicit public
  Bookwyrm lists — not Goodreads. Hardcover parsing is tested, but a live
  Hardcover refresh client is not yet wired.
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
stacks doctor     # validate paths + confirm snapshot-first read-only access (mutates nothing)
stacks refresh    # snapshot-first ingest into data/app-state.sqlite
uvicorn app.server:app   # serve the dashboard behind auth (set STACKS_AUTH_TOKEN)
```

Public catalog networking is fail-closed. It remains off unless you explicitly
enable public metadata and predeclare broad sources; queries are never generated
from your reading history, authors, or recommender weights:

```sh
export STACKS_CATALOG_OUTBOUND=public-metadata
export STACKS_OPENLIBRARY_SUBJECTS=speculative_fiction,queer_fiction
# Optional: explicit public list URLs on the allowlisted BookWyrm instance.
export STACKS_BOOKWYRM_LISTS=https://bookwyrm.social/list/1234/s/example-list
stacks refresh
```

The dashboard and `stacks doctor` show whether catalog egress is off, fresh, or
degraded, including last-success timestamps and last-good fallback counts.
Config can also live in the ignored runtime file `stacks.toml`
(`[calibre] path=…`; `[catalogs] outbound_mode="public-metadata"`); env vars
win. Copy [`examples/lenses.example.toml`](examples/lenses.example.toml) to the
ignored `data/lenses.toml` before personalizing diversity lenses.
`make verify` runs every checkable gate (CI parity). See
[`docs/ROADMAP-FUTURE.md`](./docs/ROADMAP-FUTURE.md) for the expansion plan.

## Guardrails

- **Source libraries are opened strictly read-only.** Calibre's `metadata.db`
  and KOReader's `statistics.sqlite` are never written to or put at risk of
  corruption; ingest snapshots/copies before reading.
- **Reading data is sensitive and never leaves the self-hosted instance:** no
  third-party analytics or telemetry, and the dashboard sits behind auth.
  Opt-in catalog requests contain only operator-predeclared public subjects or
  list URLs—never titles, authors, reading history, or learned taste signals.
- **No Goodreads scraping** (Amazon ToS + gatekeeping). Recommendations are
  drawn from allowlisted ethical sources and local curated lists, with
  provenance. The currently wired live sources are Open Library and explicit
  public Bookwyrm lists.
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
| Accessibility | **Applies** | Two blocking layers cover dashboard + login: structural checks and Chromium/axe at desktop/mobile, explicit light/dark preferences, and asserted 320px reflow. Human screen-reader and magnification sign-offs remain pending first release — see [`docs/audits/accessibility-2026-06-05.md`](docs/audits/accessibility-2026-06-05.md). |
| Observability | **Applies — Tier C** | Local-only, single-user, no network surface. Structured JSON logs, `/livez`, fail-closed `/readyz`, `/version` — see [`docs/ROADMAP.md` §Observability](docs/ROADMAP.md#observability) for the full per-signal N/A-with-reason declaration. |
| Internationalization | **Applies — deferred to backlog #17** | [`docs/I18N.md`](docs/I18N.md) now reconciles the manifest and prior single-user assumption; ADR 0007 defines the audience/fork decision paths and the first localization boundary. |
| AI Evaluation | N/A — no LLM/GenAI SDK anywhere; the recommender is a classic content/co-occurrence model | Has its own merge-blocking offline eval regardless (`make eval` — beats the popularity baseline); see [`docs/RESPONSIBLE-TECH-AUDITS.md`](docs/RESPONSIBLE-TECH-AUDITS.md#applicability--ai-evaluation-and-internationalization). |
| Documentation | **Applies** | This table, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CITATION.cff`, `CHANGELOG.md`, currency stamps throughout `docs/`. |
| Responsible-Tech Framework | **Applies** | Full A–F treatment, including an ASVS level declaration, in [`docs/RESPONSIBLE-TECH-AUDITS.md`](docs/RESPONSIBLE-TECH-AUDITS.md). |

## Support

This is independent, unpaid work. If it has been useful to you, you can
<a href='https://ko-fi.com/T6T6GMYTU' target='_blank'><img height='36' style='border:0px;height:36px;' src='https://storage.ko-fi.com/cdn/kofi6.png?v=6' border='0' alt='Buy Me a Coffee at ko-fi.com' /></a>
