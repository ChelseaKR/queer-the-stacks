# Real-library dogfood — 2026-07-25

**Scope:** Local technical dogfood against the maintainer’s actual Calibre
`metadata.db` with catalog networking explicitly off. This is not a user
interview, usability finding, or human assistive-technology sign-off.

## Setup

- Real source: Calibre only; no KOReader statistics database was available in
  this environment.
- Source access: snapshot-first ingest into a temporary data directory.
- Catalog outbound mode: `off`.
- Stored reading states: 1,907.
- Public recommendation candidates: 0, as expected with networking off and no
  prior persisted pool.

No book titles, authors, tags, source paths, or derived state were sent to a
catalog or analytics service.

## Results

| Check | Result |
|---|---|
| Forced real-library refresh | Passed; 1,907 states ingested |
| Source database integrity | Passed; SHA-256 before and after forced ingest matched |
| Local dashboard export | Passed |
| Structural accessibility checker | 0 violations |
| Desktop pa11y/axe | 0 violations |
| 320px mobile pa11y/axe | 0 violations |
| Browser login form | POST `/login` → 303 → authenticated GET `/`; CSP permitted same-origin form action |
| Catalog status | Clearly reported `off`, 0 candidates, no outbound request |
| Full-library search | Server-side `q` searched all 1,907 states and preserved the submitted query |
| Sensitive-descriptor cache regression | Full → hidden → full returned the correct distinct/restored views in the isolated demo dataset |

## Dogfood issue found and fixed

The first real render put all 1,907 library rows on the daily homepage, producing
a 443,969-byte HTML document. The homepage now renders at most 100 preview rows
and sends searches to the full server-side library. The same real-library
dashboard fell to 41,806 bytes—a 90.6% reduction—while `/browse?q=...` continued
to search every stored state.

## Remaining human and environment-dependent checks

- A real KOReader database and remote sync account are still needed for an
  end-to-end cross-device progress dogfood. TTL and remote-only-change behavior
  are covered by deterministic integration tests.
- No human screen-reader participant took part. Browser accessibility-tree,
  keyboard, contrast, desktop, dark-preference, and 320px automated checks are
  useful evidence but do not replace a VoiceOver/NVDA session.
- Live public-catalog fetching was deliberately not enabled during real-library
  dogfood. Recorded client fixtures and persistence/fallback tests cover the
  implementation without disclosing catalog interests from the maintainer’s
  network.
