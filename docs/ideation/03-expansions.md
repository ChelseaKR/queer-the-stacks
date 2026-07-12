# Expansions (2026-07-01)

Net-new expansion ideas in three horizons. Existing roadmap items are cited,
not repeated (ROADMAP-FUTURE A1–E5; branch RESEARCH-ROADMAP R/E items).
Effort tiers as in `02-large-scale-fixes.md`. Every idea inherits the four
hard guardrails; tensions are named.

---

## Horizon 1 — Deepen the core

### EXP-01 — OPDS feed of your own shelves (auth-gated, read-only)
**Pitch:** serve TBR, currently-reading, series-next, and recommendations as
an OPDS catalog so KOReader/Readest/Calibre-Web can browse them *from the
reading devices*.
**Impact:** closes the loop the tool exists for — a rec becomes visible where
books are opened. KOReader speaks OPDS natively; zero write-back (metadata
only; entries can link to Calibre-Web, which already hosts files).
**Shape:** an `/opds` route family in `app/server.py` rendering OPDS 1.2 from
the existing `DashboardView` shelves (`app/shelf.py`), explanation summaries
in `<content>`; same fail-closed auth (FIX-04; KOReader may need a
basic-auth adapter on this route family).
**Effort:** M. **Risks/deps:** FIX-04; OPDS conformance against real KOReader
(real-device gate).
**Excellent:** the Kobo lists "Recommended for you" with why-text over the
seedbox, reading data still never leaving the instance.

### EXP-02 — Counterfactual explanations ("why not?" and rank deltas)
**Pitch:** explain why a book ranked low or was excluded, and what would
change its rank.
**Impact:** `recommender/explain.py` only justifies winners. Counterfactuals
("no sourced tags overlap"; "excluded: already on your shelf"; "would rise if
on a cited list") make the ranking auditable by its user — the deepest form
of "every pick explained" and a showcase for the portfolio's values-lens
pattern.
**Shape:** a pure `explain_absence(taste, book, lists)` beside
`build_explanation()`; a near-miss section per shelf; reuses the already-
decomposed `score_candidate` (`recommender/model.py`).
**Effort:** S–M. **Risks/deps:** wording must reference only sourced tags,
lists, authorship — asserted by test.
**Excellent:** any candidate in the pool has a complete sourced accounting of
its rank; a test pins permitted signal kinds in absence-explanations.
**Status: Shipped (2026-07-02).** `explain_absence(taste, book, lists)` added
beside `build_explanation()` in `recommender/explain.py`, reusing
`recommender.model.score_candidate` via a lazy import. Emits sourced-only
counterfactual signals (`excluded: already on your shelf`; `no sourced tags
overlap your taste`; `would rise if on a cited list`; `no finished-author
match`), always non-empty with >=1 cited source. Covered by
`tests/test_explain_absence.py`, including a pinned-kinds guardrail test.
Deferred: the per-shelf near-miss surface in `recommend()` (out of scope for
this pass; the pure function is the core deliverable).

### EXP-03 — Explicit, reversible taste feedback (local "more/less like this")
**Pitch:** let the reader adjust the taste profile directly — stored locally,
displayed, undoable.
**Impact:** taste is currently inferred only from completion
(`recommender/model.py::build_taste_profile`); ROADMAP-FUTURE B4 adds
*implicit* negatives (DNF/dwell). Explicit feedback is a different mechanism —
agency — and covers cold-spot themes the shelf can't express ("more translated
work" before owning any).
**Shape:** a `taste_adjustments` table (FIX-06) of bounded weight records; a
"your taste, as the recommender sees it" panel with per-row delete (profile
visibility is half the feature); POST routes gated by FIX-04 sessions + CSRF
token — the first non-GET surface, a deliberate security-model change.
**Effort:** M. **Risks/deps:** FIX-04, FIX-06; boost-bounded so feedback tunes
rather than overrides sourced signals.
**Excellent:** naming a wanted theme changes rankings with the adjustment
cited in each affected explanation; deleting it restores prior ranks
deterministically.

### EXP-04 — Reading-pace forecasts on TBR and series — ✅ shipped (2026-07-03)
**Status:** done. `app/forecast.py` is a pure module (no I/O, deterministic)
that derives per-page pace from the most-recent active `DailyActivity` days
and returns a `Forecast(low_hours, high_hours, basis, estimable)` — always a
range (p25–p75 of recent per-page seconds), never a single point. Fewer than
`MIN_DAYS_FOR_ESTIMATE` valid days, or a non-positive remaining-pages count,
returns the honest `Forecast.unknown()` ("not enough recent reading to
estimate") instead of guessing. `forecast_series` reuses the same math over a
combined remaining-pages total and adds a weeks-ish gloss to the basis when
the high end is large. `tests/test_forecast.py` pins the p25/p75 math against
a hand-computable fixture and covers the thin-data and zero/negative-pages
fallbacks. Not wired into `render.py`/`app/server.py` — the spec scoped this
item to the pure module + fixture test; wiring into the dashboard view is a
natural, still-open follow-up.
**Pitch:** "at your recent pace, this 384-page book ≈ 8–10 hours; this series
≈ 6 weeks" — locally, from KOReader page timing.
**Impact:** turns data the system already has
(`app/wrapped.py::pace_pages_per_day`, per-book stats) into a daily decision
aid; no new data, no inference beyond the reader's own arithmetic.
**Shape:** a pure `forecast.py` beside `app/stats.py`: trailing-window pace
with honest ranges (p25–p75 of recent per-page times), the window disclosed;
thin data renders "not enough recent reading to estimate" (unknown stays
first-class).
**Effort:** S. **Risks/deps:** resist false precision — ranges, never points.
**Excellent:** forecasts carry their basis ("from your last 30 reading days");
a fixture test pins the math; thin-data fallback verified.

### EXP-05 — Curated-list authoring studio (create, cite, export) — DONE
**Status:** implemented on `roadmap/exp-05-curated-list-authoring-studio` —
`recommender/lists_store.py` (serializer + validated JSON file store atop
`recommender/lists.py`'s `load_lists`/`validate_lists`), `stacks lists
new/add/export/ls` in `ingest/cli.py`, and a read-only "Your lists" dashboard
section (`app/render.py`, wired through `app/view.py::DashboardView
.authored_lists`). Export remains CLI-only/manual, no auto-egress. The
"import of others' exports" half of the shape stays open for a follow-up.
**Pitch:** first-class tooling to *make* cited lists from your shelf and
export them as validated JSON others can import.
**Impact:** ROADMAP-FUTURE C3 / branch E4 cover *importing*. Authoring is the
other half: the reader contributes to the ecosystem the recommender depends
on; exports carry citation, `retrieved_at`, and descriptor provenance — the
portfolio's values made portable. Also feeds FIX-11's cited press list.
**Shape:** `stacks lists new/add/export` over `recommender/lists.py` (whose
`load_lists`/`validate_lists` already define the format); a dashboard section
listing your lists; import of others' exports through existing validation.
**Effort:** M. **Risks/deps:** a list of books can itself be sensitive —
export stays manual-only (the `app/share.py` posture).
**Excellent:** author → export → re-import on a clean instance → the list
drives a cited co-occurrence anchor in an explanation.

### EXP-06 — Multi-year analytics on the refresh ledger
**Pitch:** year-over-year Wrapped, theme-drift timelines, streak seasons —
computed from FIX-07's ledger.
**Impact:** delivers ROADMAP-FUTURE D2's "theme evolution across years" for
real (the current data layer cannot); the tool's value compounds with time.
**Shape:** pure functions over `refresh_log` (windowed theme mixes,
first-seen/finished spans); a "Years" section in `render.py` with table
equivalents; every figure labeled with its source (ledger vs KOReader) per
FIX-09.
**Effort:** M. **Risks/deps:** FIX-06 + FIX-07; graceful first-year emptiness.
**Excellent:** two synthetic fixture years produce a drift view a test pins;
every figure names its window and source.

### EXP-07 — Instant search over library + highlights (FTS5)
**Pitch:** sub-100ms full-text search across titles, authors, sourced tags,
and (once branch E11 lands) highlight text.
**Impact:** `app/browse.py::filter_states` linearly scans every state per
request — fine at 100 books, wrong at 5,000; highlights (already counted in
`ingest/models.py::ReadingStat.highlights`) become useful only when
searchable. Supplies the retrieval layer E11 will need.
**Shape:** an FTS5 virtual table maintained at refresh in the v2 store
(FIX-06); `filter_states` gains an FTS path with the pure fallback kept;
highlight text is local-only and excluded from exports by default (quotation
+ marginalia — the most intimate data in the system).
**Effort:** S–M (after FIX-06). **Risks/deps:** FIX-06; privacy note in
`docs/audits/reading-privacy.md`.
**Excellent:** search stays under budget on a 5,000-book fixture
(`tests/test_perf.py` extension); highlights provably absent from exports.

## Horizon 2 — Adjacent capabilities, audiences, integrations

### EXP-08 — Migration bridges: import your own StoryGraph/Bookwyrm exports
**Pitch:** parse the reader's *own* export files from local disk into history
and shelves; compose (never send) files for the reverse direction.
**Impact:** the adjacent audience is people leaving Goodreads via
StoryGraph/Bookwyrm (the branch's EV-ETHICAL-ALT base). Carrying history in —
from files they downloaded themselves — extends "your reading life, unified"
with zero new network surface. Distinct from branch E9 (live ActivityPub
import): offline files, no federation code.
**Shape:** `ingest/imports.py` parsers, fixture-tested like the
`catalogs.py` parsers, feeding `unify()` via FIX-03 identity resolution;
imported records carry a new file-provenance `SourceKind` (human-curated, so
the enum stays non-inference-shaped); export composition mirrors
`app/share.py`'s "composed locally, you upload it".
**Effort:** M. **Risks/deps:** needs *real sample exports* (real-data gate —
formats are undocumented and shift); FIX-03 to avoid duplicate books.
**Excellent:** a real StoryGraph export round-trips into unified history with
per-record provenance; zero network calls in the path.

### EXP-09 — Borrowability on the TBR (Open Library lending, library OPDS)
**Pitch:** show per TBR/recommended book whether it's borrowable — IA/Open
Library lending plus user-configured library OPDS endpoints — with per-source
compliance first-class.
**Impact:** connects discovery to access; libraries over storefronts is
exactly this project's values register.
**Shape:** refresh-time lookups (never serve-time) through `assert_allowed`,
with archive.org/user hosts added *only* after a per-source compliance card
(branch R5's mechanism) exists; results cached with `retrieved_at`; rendered
as a sourced fact ("borrowable per openlibrary.org, checked <date>");
FIX-03's ISBN/OLID resolution does the matching.
**Effort:** M–L. **Risks/deps:** **legal/SME gate** — lending-API and library-
endpoint terms reviewed per source before allowlisting; a batch of
borrowability queries could sketch a TBR — document, and pad/shuffle batching
if needed. Defer honestly if terms are unclear.
**Excellent:** every badge carries source + date; each allowlist addition is
paired with a committed compliance card.

### EXP-10 — Household profiles (2–5 readers, isolated by construction)
**Pitch:** optional multi-profile mode: separate stores, auth, and taste —
sharing only the candidate-pool cache.
**Impact:** the single-user premise (ROADMAP §2) excludes the most common
adjacent deployment: a household seedbox, where a shared Calibre library
currently means shared reading history — the exact thing the tool protects.
Structural isolation *strengthens* the privacy story.
**Shape:** per-profile `data/<profile>/app-state.sqlite` (the `Store` API
already takes a path); per-profile tokens/sessions (FIX-04); profile chosen at
login, never per-request parameters; the shared non-sensitive candidate pool
(FIX-01) is the only common state; per-profile KOReader sources.
**Effort:** L. **Risks/deps:** FIX-04, FIX-01; a threat-model addendum
(cross-profile inference via timing/cache) answered in `docs/audits/` first;
revisits a ROADMAP non-goal → needs an ADR.
**Excellent:** a test proves profile A's routes can never read profile B's
store; the privacy audit gains a household section.

### EXP-11 — Homelab distribution: published image + app-store packaging
**Pitch:** a versioned GHCR image plus Umbrel/CasaOS/YunoHost app definitions
and a first-run wizard, so a stranger deploys in minutes.
**Impact:** ROADMAP-FUTURE E1 / branch E6 containerize for *this* seedbox;
this reaches *other people's* boxes — the difference between a personal tool
and a self-hosting community project, and it makes the branch §8 "watch a
homelabber stand it up cold" validation possible.
**Shape:** a release workflow publishing a signed image (the STANDARDS
SBOM/Sigstore machinery applies); per-platform manifests; a first-run wizard
route that is open *only* until a token is set, then locks (fail-closed,
consistent with `app/auth.py`); reverse-proxy docs.
**Effort:** L. **Risks/deps:** **human gate — publishing means deciding the
repo/image goes public** (portfolio default: private until Chelsea says
otherwise); app-store listings create support expectations; FIX-04
prerequisite.
**Excellent:** cold deploy on a clean Umbrel to first render in under 10
minutes, observed with a real third-party homelabber.

### EXP-12 — Extract the values-lens discovery kernel (shared with women-artist-discovery)
**Pitch:** factor the pattern both repos implement — sourced-descriptor
provenance, boost-only aperture, unknown-is-first-class,
explanation-with-sources — into one small library both consume.
**Impact:** the portfolio maintains two hand-rolled implementations of its
signature pattern. One kernel means improvements (FIX-11's dimension-aware
boosts, EXP-02's counterfactuals) land once — and the pattern becomes a
citable artifact, arguably the portfolio's most distinctive contribution.
**Shape:** extract from `ingest/models.py` (Source/ThemeTag/Explanation
invariants), `recommender/rerank.py`, `recommender/explain.py` into a
`values-lens` package (new repo, private by default); domain enums stay
per-repo via a protocol; both repos' existing guardrail tests become the
conformance suite. Distinct from branch E5 (adapter contract *within* this
repo's catalog layer).
**Effort:** L. **Risks/deps:** cross-repo release discipline (SemVer per
STANDARDS); extract only after FIX-11/EXP-02 stabilize the surface, or the
kernel fossilizes early.
**Excellent:** both repos pass unchanged guardrail suites against the shared
kernel; one pattern doc replaces two divergent explanations.

### EXP-13 — Preservation-grade export (open formats, decades-scale)
**Pitch:** `stacks export --archive`: a documented, self-describing bundle —
history, sourced tags with provenance, highlights as W3C Web Annotations,
lists as EXP-05 JSON — designed to outlive the app.
**Impact:** a reading life is a life record; the only export today is
rendered HTML (`ingest/cli.py::_cmd_export`). Open formats are the honest
complement to "your data never leaves": *and it's yours to take*.
**Shape:** an export module writing JSON per committed schemas + a `MANIFEST`
(FIX-06 versioning reused); highlights (post E11) as Web Annotation JSON-LD;
a restore path sharing EXP-08 machinery; local-only, manual-only.
**Effort:** M. **Risks/deps:** E11 for highlight content; the schema is a
maintenance promise — version it from day one.
**Excellent:** today's archive re-imports losslessly on a fresh instance; the
manifest alone lets a stranger parse the bundle without this codebase.

**Status: shipped.** `stacks export --archive --out <path.json>` writes a
versioned, self-describing JSON bundle containing the manifest, unified states
with sourced-tag provenance, daily activity, and count-only highlight Web
Annotations. `stacks import --archive <file>` restores it losslessly through
the existing serde/store contract. Highlight text remains explicitly out of
scope until E11. See `ingest/archive.py` and `tests/test_archive.py`.

## Horizon 3 — Transformative bets

### EXP-14 — A local, citation-constrained librarian voice
**Pitch:** an optional, off-by-default, strictly on-device language model
writing short "librarian notes" — where every generated claim must trace to a
`Source` already in the data, or is dropped.
**Impact:** the leap from structured explanations to prose that feels like a
knowledgeable friend — *if* it can hold sourced-not-inferred. The constraint
mechanism (claim→citation matching over the provenance graph) would itself be
a novel responsible-AI artifact, more interesting than the prose.
**Shape:** behind a flag like `embeddings_enabled` (`ingest/config.py`);
llama.cpp-class local runtime, no runtime weight downloads; generation
constrained to template slots filled from `Explanation` signals/sources, then
a verifier rejecting any sentence with a proper noun or descriptor absent
from the pick's sourced data; per-sentence source footnotes; the no-egress
test family extends to the model runtime.
**Effort:** XL. **Risks/deps:** **SME/human gates — representation review
(generated prose about queer/trans books is where subtle harm hides) and a
published hallucination-eval bar before anything is user-visible;** seedbox
CPU budget; may honestly conclude structured explanations are better — a
written negative result is an acceptable outcome.
**Excellent:** a red-team set where every hallucinated or identity-implying
sentence is mechanically rejected; a dated representation-review artifact in
`docs/audits/`; ships dark until both gates pass.

### EXP-15 — Consensual list exchange between trusted instances
**Pitch:** friends running their own instances exchange *curated lists*
(cited, validated, explicitly chosen) — never reading history — via signed
payloads.
**Impact:** `recommender/collaborative.py` is strictly public-list-based;
what mainstream systems get from surveillance, this gets from friendship — an
architecturally honest social layer and the first bridge between instances.
**Shape:** EXP-05 list JSON + Ed25519 signature + author note; import
verifies against a locally-pinned friend key (TOFU, documented); imported
lists join the co-occurrence machinery with the friend named in the source
citation. Transport starts as "send the file yourself" (share-card posture);
ActivityPub delivery is a later, separately-gated step (branch E9 covers
reading *your own* Bookwyrm activity; this is peer exchange).
**Effort:** L (file-based) → XL (federated). **Risks/deps:** **human/privacy
gate** — even a curated list reveals taste: per-list, explicit, revocable;
key-management UX is the hard part; representation note for "friend says"
explanations.
**Excellent:** an explanation reading "on '…', a list signed by Sam (imported
2026-07-01)" with a verifiable signature; a privacy-review artifact covering
the exchange model.

### EXP-16 — The Stacks Atlas: a public, governed dataset of the ethics layer
**Pitch:** grow the in-code registry (`recommender/sources.py`), branch R5's
compliance cards, and the list-validation rules into a maintained *public*
dataset — source compliance cards, cited-list registry, descriptor-lens
vocabulary — with governance and branch E8's author-correction path as its
intake.
**Impact:** every values-aligned reading tool needs exactly this and each
rebuilds it badly; it is ROADMAP §9's GTM promise at full size. Contains zero
reading data by construction — ethics metadata, not anyone's shelf.
**Shape:** a separate repo (private until decided otherwise) generated
from/feeding this repo's registry; JSON + rendered docs; a governance file
(source add/remove process, author dispute process); versioned releases this
repo pins the way it pins standards (`.github/workflows/standards.yml`
pattern).
**Effort:** XL (mostly ongoing stewardship). **Risks/deps:** **legal/SME/
steward gates** — per-source terms summaries are legal characterizations and
must be reviewed before publication; the branch §8 warning applies: confirm
with real Open Library / Bookwyrm stewards that the posture is welcome; needs
a named maintenance owner or it rots into misinformation — defer honestly
otherwise.
**Excellent:** two external projects consume the Atlas; at least one real
steward and one real author have reviewed their entries (dated artifacts);
`docs/ethical-book-data-sources.md` becomes a pinned render of it.
