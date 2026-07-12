# 0002. Join Calibre ↔ KOReader by normalized title|first-author, KOReader md5 for progress

* Status: accepted
* Date: 2026-06-05
* Ported from: `docs/ROADMAP.md` §6 (2026-07-05, form only — content unchanged)

## Context and Problem Statement

Calibre's `metadata.db` and KOReader's `statistics.sqlite` need to be joined into one unified
reading state per book, across two independent schemas with no shared primary key in practice.

## Decision Outcome

Join by a normalized `title|first-author` key, with KOReader's own md5 as the progress key on the
KOReader side. This is robust to punctuation/case/spacing drift across the two stores, and books
read in KOReader but absent from Calibre are still surfaced so history is complete.

## Rejected Options

* ISBN-only joins — KOReader stats rarely carry ISBNs, which would silently drop most books.
