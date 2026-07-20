# CLAUDE.md — queer-the-stacks

Agent contract for this repository (moved here from the README's "For Claude
Code" section per DOCUMENTATION-STANDARD §9 [DOC-18] — the README is the
visitor's front door).

- **Build entrypoint:** [`docs/ROADMAP.md`](./docs/ROADMAP.md) → *Implementation Plan*.
- **Hard guardrails:** **open Calibre's `metadata.db` and KOReader's `statistics.sqlite` strictly read-only** (never write to or risk corrupting the real libraries — copy/snapshot before reading); **reading data is sensitive and never leaves the self-hosted instance** (no third-party analytics, no telemetry, behind auth on the seedbox); **do not scrape Goodreads** (Amazon ToS + gatekeeping) — source recommendations from OpenLibrary/Hardcover/Bookwyrm/curated lists with provenance; books and authors are described via *sourced* theme/genre tags, never reductive auto-assigned identity labels; every recommendation shows why + source.
- **Commands:** `make dev` · `make verify` · `make a11y` · `make eval`.
- **Running against a real library:** see the README's [Quickstart](./README.md#quickstart) — real, read-only sources are ingested into the local app-state store via `stacks doctor` / `stacks refresh`; config can also live in `stacks.toml` (`[calibre] path=…`), env vars win. See [`docs/ROADMAP-FUTURE.md`](./docs/ROADMAP-FUTURE.md) for the expansion plan.
- **Definition of done:** a single self-hosted dashboard shows cross-device reading state and stats from Calibre + KOReader, plus explainable recommendations from ethical sources — read-only against source libraries, private to its host, with every repository gate green.
