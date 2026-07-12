# Impact × Effort & Sequencing (2026-07-01)

Covers FIX-01…FIX-14 and EXP-01…EXP-16. Impact is judged for the primary
reader/owner first, then portfolio-strategic value; these are judgment calls
from one code-reading pass, stated as such.

## 1. Impact × effort matrix

| | **Effort S–M** | **Effort L–XL** |
|---|---|---|
| **High impact** | FIX-02 (snapshot integrity) · FIX-08 (kosync batch) · FIX-09 (freshness/degradation surface) · FIX-05 (CSP/headers) · FIX-13 (falsifiable eval) · FIX-14 (serving lifecycle) · EXP-02 (counterfactuals) · EXP-07 (FTS5 search) | FIX-01 (real candidate pipeline) · FIX-03 (work/edition identity) · FIX-04 (browser session auth)¹ · FIX-06 (store v2) · EXP-01 (OPDS)¹ · EXP-11 (homelab distribution) · EXP-12 (values-lens kernel) |
| **Medium impact** | FIX-10 (a11y gate honesty) · FIX-11 (language/publisher facts) · FIX-12 (lens config) · EXP-04 (pace forecasts) · EXP-05 (list authoring) · EXP-06 (multi-year analytics) · EXP-13 (preservation export) · EXP-08 (migration bridges) | FIX-07 (refresh ledger)² · EXP-03 (taste feedback) · EXP-09 (borrowability) · EXP-10 (household profiles) · EXP-16 (Stacks Atlas) |
| **Speculative / option-value** | — | EXP-14 (local librarian voice) · EXP-15 (list exchange) |

¹ FIX-04 and EXP-01 are M-effort individually but graded L here because they
change the auth surface, which demands extra test/review weight.
² FIX-07 is M after FIX-06; its impact compounds with years of use, so its
matrix position undersells it long-term.

**Best value-per-effort:** FIX-09, FIX-02, FIX-05, EXP-02, EXP-04 — all S–M,
all either close honesty gaps or harden correctness with no new surface area.
**Biggest single unlock:** FIX-01 — until it lands, the recommender's headline
claim is only true of demo mode.

## 2. Dependency notes

- **FIX-06 (store v2) is the keystone**: FIX-03 (overrides), FIX-07 (ledger),
  FIX-01 (persisted candidate pool), EXP-03 (adjustments), EXP-06, EXP-07 all
  want real tables. Do it early or every dependent pays a migration tax twice.
- **FIX-04 (session auth) gates the interactive tier**: EXP-01 (device auth),
  EXP-03 (first POST routes), EXP-10 (profiles), EXP-11 (first-run wizard).
- **FIX-01 chains from** the branch's R7 cassettes (CI honesty for live
  clients) and R5/R11 compliance posture; it in turn feeds EXP-09 and makes
  FIX-13's eval meaningful on real candidate pools.
- **FIX-03 (identity)** underpins EXP-08 (imports without dupes) and EXP-09
  (ISBN/OLID matching).
- **FIX-07 → EXP-06** strictly. **EXP-05 → EXP-15 and FIX-11** (cited-list
  machinery reuse). **EXP-02/FIX-11 should stabilize before EXP-12** extracts
  the kernel, or the kernel freezes an immature pattern.
- **Branch merge precedes everything**: the `research-panel-and-roadmap`
  branch (R4/R5/R11 implementations + both research docs) must be rebased onto
  `main` and merged first — otherwise this folder and the R-items reference
  work that `main` doesn't have, and the regenerated artifacts
  (`coverage.xml`, `dashboard.html`) will conflict harder with every commit.

## 3. Suggested sequence (beyond the existing roadmaps)

The branch's RESEARCH-ROADMAP already sequences the assurance sprint (R1–R3)
first; this sequence assumes it and adds the net-new layer.

**Now — truth and foundations (order matters):**
1. Rebase + merge `research-panel-and-roadmap` (unblocks everything; fixes the
   portfolio index's dangling link).
2. FIX-09 (freshness/degradation surface) + the small honesty patches it
   carries (render the stored `refreshed_at`; doctor env-var linting; fix the
   `ingest/unify.py` docstring that promises an unimplemented md5 join).
3. FIX-02 (snapshot integrity) — correctness before any real-library daily
   driving (pairs with R1's first real run).
4. FIX-05 (headers/CSP) and FIX-10 (a11y gate honesty) — cheap, close
   claim/reality gaps.
5. FIX-06 (store v2) — the keystone, while dependent surface area is small.

**Next — make the headline true:**
6. FIX-08 (kosync batching) and FIX-14 (serving lifecycle) — refresh and
   serve become boring.
7. FIX-01 (real candidate pipeline) with FIX-13 (falsifiable eval) landing in
   the same window, so real candidates arrive with an eval that can catch
   regressions.
8. FIX-03 (identity layer), then FIX-04 (session auth).
9. Quick H1 wins as capacity allows: EXP-02, EXP-04, EXP-07.

**Later — compounding and outward:**
10. FIX-07 → EXP-06 (ledger, multi-year analytics); FIX-11 + FIX-12 (richer,
    configurable lenses); EXP-03 (taste feedback); EXP-05 → EXP-13
    (authoring, preservation).
11. EXP-01 (OPDS) once FIX-04 settles device auth; EXP-08 when real export
    samples are in hand.
12. Outward bets in gate order (below): EXP-11, EXP-09, EXP-10, EXP-12,
    EXP-16, EXP-15, EXP-14.

## 4. Items gated on humans, legal review, SMEs, or real data

Portfolio ethos: these do not proceed on synthetic substitutes; they defer and
say so.

| Item | Gate | What must actually happen |
|---|---|---|
| FIX-02 | Real-data | Validate snapshot/backup behavior against a *live, busy* Calibre library before trusting it (fixtures can't reproduce mid-write timing). |
| FIX-01 | Key + real-data | Hardcover personal API token; live contract validation of all three catalog APIs (cassettes only prove yesterday's shapes). |
| FIX-11 | SME + human review | The cited small-press list is an editorial artifact needing an accountable curator; new lenses need a representation-review note (extends the branch's R3 artifact). |
| FIX-13 (R6 half) | Real-data | Temporal holdout on real finishes requires the real library; synthetic worlds are labeled synthetic and never claimed as demand/quality evidence. |
| EXP-01 | Real-device | OPDS conformance against actual KOReader/Readest on the actual seedbox. |
| EXP-08 | Real-data | Genuine StoryGraph/Bookwyrm export files (formats are undocumented); do not guess formats. |
| EXP-09 | **Legal/SME** | Per-source terms review (IA lending, library endpoints) with a committed compliance card *before* any host joins the allowlist; defer if terms are unclear. |
| EXP-10 | Human (privacy review) | Household threat-model addendum reviewed and committed before shipping; ADR for revisiting the single-user non-goal. |
| EXP-11 | **Human (owner decision)** | Publishing an image/app listing makes the project public — repos stay private until Chelsea decides otherwise; plus one real third-party cold deploy observed. |
| EXP-12 | Human (owner/architecture) | Cross-repo kernel is a portfolio-level commitment (release discipline for two consumers); needs owner sign-off, not just code. |
| EXP-14 | **SME + human (representation review)** | Dated representation-review artifact and a published hallucination-eval bar *before* any generated prose is user-visible; a written negative result is an acceptable exit. |
| EXP-15 | Human (privacy review) | Exchange model (revocability, key trust) privacy-reviewed; pilot only with consenting real friends. |
| EXP-16 | **Legal + stewards + authors** | Terms summaries are legal characterizations → review before publication; real Open Library/Bookwyrm steward and at least one real author consulted (the branch §8 risks apply in full); requires a named maintenance owner or it doesn't ship. |
| (Standing, from the branch) | Human | R2 screen-reader walkthrough with a real SR user and R3 privacy/representation sign-offs remain the release gates this folder builds on top of — nothing here substitutes for them. |
