# Real-library dogfood — 2026-08-18

**Scope:** Local technical dogfood against the maintainer's actual Calibre
`metadata.db`, catalog networking off, repeating the
[2026-07-25 run](./real-library-dogfood-2026-07-25.md) and auditing every output
surface for content that does not derive from the real ingest. Not a user
interview, usability finding, or human assistive-technology sign-off.

No book titles, authors, descriptors, per-lens counts, or source paths are
recorded here. The reading-privacy threat model (EV-PRIVACY) treats a
queer/trans reading profile as sensitive, so only whole-library aggregates that
were already published in the previous dogfood appear below.

## Setup

- Real source: Calibre only. There is still no KOReader `statistics.sqlite` in
  this environment.
- Catalog outbound mode: `off`; 0 public candidates stored, as expected.
- Stored reading states: 1,907 (unchanged from 2026-07-25).

## Source-library integrity

| Check | Result |
|---|---|
| `metadata.db` mtime before/after forced refresh | Unchanged |
| `metadata.db` SHA-256 before/after forced refresh | Unchanged |
| WAL / SHM / journal files created beside the source | None |
| Forced real refresh wall time | ~0.3 s for 1,907 books |

## Output-surface provenance audit

Every surface was exercised against the real store and checked for content that
did not derive from it.

| Surface | Derives from the real ingest? |
|---|---|
| `stacks doctor` | Yes — reports the missing KOReader source as a failed check |
| `stacks refresh` | Yes |
| `stacks recommend` | Yes — refuses with an actionable message rather than printing fixtures |
| `stacks export` (HTML) | Yes |
| `stacks export --archive` | Yes — 1,907 states, empty `daily_activity`, count-only annotations |
| `stacks lists ls` | Yes — says there are none rather than showing demo lists |
| `/` dashboard, `/browse` | Yes |
| `/share`, `/share/card.svg` | Yes, but see "absence rendered as a value" below |
| `/opds` and all four shelf feeds | Yes |
| Diversity & descriptor provenance panel | Yes — whole-shelf fallback is labelled, and every descriptor carries the current retrieval date |

Two defects in the *demo* direction were found and fixed in this change; both
were reproduced against the real library:

1. A demo refresh stamped its fixture books with the real sources' mtimes, so a
   subsequent real `stacks refresh` reported `sources unchanged since last
   refresh` and served nine fixture books as the reader's library.
2. `make dev` (`STACKS_DEMO=1`, no `STACKS_DATA_DIR` override) rendered the real
   1,907-book library alongside demo-fixture recommendations and near-misses
   with no label, directly above a "Candidates stored locally: 0" row.

## Absence rendered as a value (open, not fixed here)

With no KOReader source, every book is `UNREAD`, `daily_activity` is empty, and
`kosync_progress` is empty. Several surfaces render that absence as measurement:

- `app/view.py::_infer_today_and_year` falls back to year **1970** when there is
  no activity to infer a year from. The dashboard therefore renders "Reading
  Wrapped 1970", "0.0 hours read in 1970", "Standout reads of 1970", and — with
  goals configured — "Books in 1970: 0 / 52 — 0%".
- The same 1970 reaches `/share`, the one surface designed to be posted
  publicly: `year_in_books_card` composes "My 1970 in books · 0 books · 0 pages
  · 0.0 hours across 0 reading days" plus hashtags, and `build_share_cards`
  emits it unconditionally — so `render_share_page`'s "No share cards yet"
  message is unreachable.
- The reading-stats table renders eight confident zeros with no indication that
  no reading-data source is connected.
- `series_continuations` seeds only from finished books, so the page states "No
  series to continue right now" while the shelf holds unread sequels.
- `app/shelf.py::to_read` is documented as "best taste-fit first" but degrades
  to alphabetical order when no book carries a reading status; the OPDS blurb
  repeats the taste claim.

`app/forecast.py` (`Forecast.estimable` / `Forecast.unknown()`) and
`app/diversity.py` (`shelf_fallback`) already model unmeasured data honestly.
The vocabulary exists; `ReadingStats`, `Wrapped`, and `Goal` do not yet carry it.

## Corrections to the 2026-07-25 dogfood

That run recorded the real-library dashboard at **41,806 bytes** after the
library table was capped at 100 preview rows. Measured again today, the same
page is **188,219 bytes**. The cap still holds; the growth is the diversity
panel's per-descriptor provenance table, which is rendered uncapped (one row per
distinct sourced descriptor) and now accounts for the bulk of the document —
`docs/audits/real-library-dogfood-2026-07-25.md`'s "90.6% reduction" figure
should be read as a measurement of that date, not a standing property.

## Remaining human and environment-dependent checks

Unchanged from 2026-07-25: a real KOReader database and remote sync account are
still needed for a cross-device progress dogfood, no human screen-reader
participant has taken part, and live public-catalog fetching was again
deliberately not enabled.
