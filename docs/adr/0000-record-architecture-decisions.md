# 0000. Record architecture decisions

* Status: accepted
* Date: 2026-07-05

## Context and Problem Statement

Four architecture decisions were already made and recorded during the M0–M6 build (2026-06-05),
but as an inline list in `docs/ROADMAP.md` §6 rather than as individually dated, append-only
records. `STANDARDS/DOCUMENTATION-STANDARD.md` (DOC-04/05) asks for a `docs/adr/` directory using
the MADR format instead, so decisions are individually addressable, and — once written — a
published ADR is append-only (superseded by a new ADR, never edited in place).

## Decision Drivers

* Existing ADR content in `docs/ROADMAP.md` is good but includes rejected alternatives inline,
  isn't individually linkable, and could be edited in place (no append-only guarantee).
* The portfolio standard specifies MADR-style numbered files.

## Considered Options

* Keep ADRs inline in `docs/ROADMAP.md` (status quo).
* Port to `docs/adr/NNNN-*.md`, MADR template, append-only from here on.

## Decision Outcome

Chosen option: port to `docs/adr/`. `0001`–`0004` port the four ADRs recorded inline in
`docs/ROADMAP.md:39-43` verbatim (content unchanged, form changed); `docs/ROADMAP.md` §6 now
points here instead of duplicating the text. `0005` and `0006` are new, addressing gaps the
2026-07-05 conformance audit found (CQ-23 flat layout undocumented; CQ-45 no ADR for the I18N/AIEV
N/A declarations). Future architecture decisions are recorded as new numbered files here, never by
editing an existing one.

## Template

New ADRs in this directory should follow
[MADR](https://adr.github.io/madr/) shape: Status, Context, Decision Drivers, Considered Options,
Decision Outcome (and Rejected Options, where useful).
