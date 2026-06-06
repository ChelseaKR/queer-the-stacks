# Source-Ethics Audit — ethical catalogs, Goodreads exclusion, diverse surfacing

**Last verified: 2026-06-05 · Recheck cadence: per OpenLibrary/Hardcover/Bookwyrm API change.**

Instantiates `RESPONSIBLE-TECH-FRAMEWORK.md` §A (ethics) and §B (bias & fairness).
Two commitments: recommend only from ethical, non-gatekept catalogs (never
Goodreads), and describe books via *sourced* theme tags rather than labelling
authors.

## Goodreads / Amazon exclusion

Goodreads is excluded on ToS + gatekeeping + surveillance grounds. The exclusion
is a **build-time impossibility**, not a guideline: `recommender.catalogs` is the
single network choke point, and `assert_allowed()` is default-deny —

- **Allowed:** `openlibrary.org`, `covers.openlibrary.org`, `api.hardcover.app`,
  `bookwyrm.social`.
- **Blocked (explicit):** `goodreads.com`, `www.goodreads.com`, `amazon.com`,
  `www.amazon.com`.
- **Everything else:** denied by default.

## Representation: describe books, never label authors

- Theme/genre tags are modelled as `ThemeTag`, which **cannot be constructed
  without a `Source`** (a Calibre tag, OpenLibrary subject, Hardcover/Bookwyrm
  tag, or curated list). There is no inference-shaped `SourceKind` — no NLP, no
  classifier, no name/cover guess.
- `Author` carries only a name + sort key. There is **no** gender/sexuality/
  identity field — nowhere to put a reductive auto-assigned label on a person.

## Diverse surfacing vs bestseller bias

The eval encodes the commitment to widen the aperture: the on-canon discoveries
are deliberately *less popular* than the distractor bestsellers, and the content
model recovers them while a popularity baseline misses them.

| Model | Precision@5 | Recall@5 | MAP@5 |
|-------|-------------|----------|-------|
| content (themes + authors + curated lists) | 1.00 | 1.00 | 1.00 |
| popularity baseline | 0.40 | 0.40 | 0.13 |

(Regenerated into `docs/audits/eval-report.json` by `make eval`.)

## Enforcement (auto-gated, merge-blocking)

| Check | Test |
|-------|------|
| Goodreads/Amazon raise; unknown hosts default-denied | `tests/test_source_allowlist.py` |
| No inference-shaped source kind; `ThemeTag` requires a source | `tests/test_sourced_tags.py` |
| `Author` exposes no identity field | `tests/test_sourced_tags.py::test_author_has_no_identity_fields` |
| Content recommender beats popularity | `tests/test_eval.py::test_content_beats_popularity` |
| Every recommendation shows why + source | `tests/test_explanation.py` |

**Metrics:** Goodreads requests = **0**; "why + source" present = **100%** of
recs; recommendation reproducibility = **deterministic**. Status: ✅ green.
Review-gated: representation review (pending first release).
