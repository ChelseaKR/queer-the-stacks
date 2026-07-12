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

**Illustrative single fixture** (`ingest.demo`, one hand-built library — kept
for readability, no longer the gate):

| Model | Precision@5 | Recall@5 | MAP@5 |
|-------|-------------|----------|-------|
| content (themes + authors + curated lists) | 1.00 | 1.00 | 1.00 |
| popularity baseline | 0.40 | 0.40 | 0.13 |

(Regenerated into `docs/audits/eval-report.json` by `make eval`.) This one
fixture is trivially separable — every model scores a perfect 1.0 on every
metric, which cannot distinguish a healthy recommender from a broken one short
of catastrophe. It is not what merges block on (FIX-13).

**Merge-blocking gate: the synthetic-world battery.** `recommender/synth.py`
deterministically generates 10 seeded synthetic libraries (`random.Random(seed)`
only — no numpy, no real-world data), each with its own noisy, only-mostly-
separable canon-vs-distractor split, and `recommender/battery.py::run_battery`
runs the same content/hybrid/popularity eval on every one:

| Metric (MAP@5, seeds 0–9) | content | hybrid | popularity |
|---|---|---|---|
| median | 0.71 | 0.80 | 0.00 |

- **`median_uplift` = 0.68** (content − popularity), gated at **`MARGIN` = 0.5**
  — real headroom below a healthy run, real headroom above a broken one.
- **`no_losing_seed` = true** — content never loses to popularity on any of the
  10 seeds.
- **Falsifiability, proven, not asserted:** zeroing
  `recommender/model.py::AUTHOR_BONUS` (the "more by an author you love"
  signal) drops the median uplift to **~0.37** — below `MARGIN` — and the gate
  fails. `tests/test_synth_eval.py::test_author_bonus_zero_narrows_uplift`
  asserts exactly this every run.
- **Ablations, tracked per seed (not gating, but recorded):** dropping the
  synthetic curated lists costs content real MAP (median delta ≈ 0.35);
  shuffling ~20% of candidate tags never *improves* content MAP on any of the
  10 seeds (asserted in
  `tests/test_synth_eval.py::test_shuffling_tags_never_improves_content_map`)
  and measurably degrades it on several.

(Regenerated into `docs/audits/eval-battery.json` by `make eval` — that JSON is
the full per-seed distribution behind the summary above.)

## Enforcement (auto-gated, merge-blocking)

| Check | Test |
|-------|------|
| Goodreads/Amazon raise; unknown hosts default-denied | `tests/test_source_allowlist.py` |
| No inference-shaped source kind; `ThemeTag` requires a source | `tests/test_sourced_tags.py` |
| `Author` exposes no identity field | `tests/test_sourced_tags.py::test_author_has_no_identity_fields` |
| Content recommender beats popularity, with margin, across 10 synthetic seeds | `tests/test_synth_eval.py::test_run_battery_default_seeds_passes` |
| The eval gate is actually falsifiable (`AUTHOR_BONUS=0` fails it) | `tests/test_synth_eval.py::test_author_bonus_zero_narrows_uplift` |
| Illustrative single-fixture eval (informational, not merge-blocking) | `tests/test_eval.py::test_content_beats_popularity` |
| Every recommendation shows why + source | `tests/test_explanation.py` |

**Metrics:** Goodreads requests = **0**; "why + source" present = **100%** of
recs; recommendation reproducibility = **deterministic**. Status: ✅ green.
Review-gated: representation review (pending first release).
