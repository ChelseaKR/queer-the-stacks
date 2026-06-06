# Queer & Spec-Fic Reader

**A reading dashboard and recommender built on top of your actual ebook stack** — Calibre's library plus KOReader's reading stats and cross-device progress — that gives you one place to see what you're reading everywhere, your reading stats and streaks, a self-hosted "Reading Wrapped," and recommendations tuned to your canon (Plett, Peters, Thom, Butler, Atwood) sourced from ethical, non-gatekept catalogs. Self-hosted on your Whatbox seedbox next to Calibre-Web, single-user, private by design.

**Status:** `Beta` · **Track:** Personal (self-hosted web app + recommender) · **License:** MIT · **Data:** self-hosted/private

> **Build:** M0–M6 implemented on **Python 3.14**; all *checkable* `/STANDARDS` gates green via `make verify` (lint, `mypy --strict`, 91 tests @ 95% coverage, dep-audit = **0 known vulnerabilities**, secret scan, a11y = 0 violations, recommender beats the popularity baseline). The dashboard serves only behind auth (401 without a valid token). Review-gated sign-offs (manual screen-reader walkthrough, privacy/representation review) pending first release — see [`docs/audits/`](./docs/audits/). Quickstart: `make install && make dev` (demo mode, no real library, no API key) · `make verify`.

## Why it matters
Your reading lives across Calibre (Mac), a Kobo running KOReader, Calibre-Web on the seedbox, and Readest on your phone, with KOReader progress syncing through `sync.koreader.rocks`. Nothing ties that together, and mainstream recommenders are both bad at trans/queer/speculative work and built on gatekept, surveillance-heavy catalogs. This unifies your own data and recommends from better sources — without ever leaving your control.

## What it does
- **One reading view:** cross-device "currently reading," progress, and history, read from Calibre + KOReader.
- **Stats & Wrapped:** pages, time, streaks, genre/theme mix, and a self-hosted year-in-review.
- **Recommender:** tuned to your canon and tastes, sourced from OpenLibrary, Hardcover, and Bookwyrm plus curated community lists — not Goodreads.
- **Every pick explained:** why + which source, with diverse/small-press surfacing rather than bestseller bias.
- **Self-hosted & private:** runs on your seedbox; reading data never leaves it.

## For Claude Code
- **Build entrypoint:** [`docs/ROADMAP.md`](./docs/ROADMAP.md) → *Implementation Plan*.
- **Hard guardrails:** **open Calibre's `metadata.db` and KOReader's `statistics.sqlite` strictly read-only** (never write to or risk corrupting the real libraries — copy/snapshot before reading); **reading data is sensitive and never leaves the self-hosted instance** (no third-party analytics, no telemetry, behind auth on the seedbox); **do not scrape Goodreads** (Amazon ToS + gatekeeping) — source recommendations from OpenLibrary/Hardcover/Bookwyrm/curated lists with provenance; books and authors are described via *sourced* theme/genre tags, never reductive auto-assigned identity labels; every recommendation shows why + source.
- **Commands:** `make dev` · `make verify` · `make a11y` · `make eval`.
- **Definition of done:** a single self-hosted dashboard shows your real cross-device reading state and stats from Calibre + KOReader, plus explainable recommendations from ethical sources — read-only against your libraries, private to your seedbox, all `/STANDARDS` gates green.

## Standards
Inherits [`/STANDARDS`](../STANDARDS/).
