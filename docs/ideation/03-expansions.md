# Expansion roadmap items (EXP-*)

Tracked expansion items beyond the phases in `docs/ROADMAP-FUTURE.md`. Each item
gets a stable `EXP-N` id so it can be referenced from commits/PRs independent of
prose section numbering.

- [x] **EXP-13 — Preservation-grade export (open formats, decades-scale).**
  `stacks export --archive --out <path.json>` writes a versioned,
  self-describing JSON bundle: the manifest (schema version, generator,
  generation timestamp, member descriptions, and the `stacks import --archive`
  re-import instructions), the full unified reading `states` (with every
  sourced theme tag's provenance intact), `daily_activity`, and highlight
  `annotations` as a W3C Web Annotation JSON-LD collection. Highlight bodies
  are count-only today (highlight *text* is E11, not yet shipped) — the
  manifest documents this so the schema stays honest and forward-compatible.
  `stacks import --archive <file>` restores it losslessly via the same
  `ingest.serde` round-trip the app-state store already guarantees. No new
  dependencies (stdlib `json` only). See `ingest/archive.py`,
  `tests/test_archive.py`.
