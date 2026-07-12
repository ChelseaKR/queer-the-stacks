# Research-Backed Roadmap — Queer the Stacks

> **Companion to [`ROADMAP.md`](./ROADMAP.md) (shipped M0–M6) and
> [`ROADMAP-FUTURE.md`](./ROADMAP-FUTURE.md) (shipped N1–N6).** This document does
> **not** replace either; it triages the [synthetic persona panel](./USER-RESEARCH.md)
> and recent public research into a backlog and a sequence that *complement* the
> existing plans. Where an item restates an existing roadmap line it is tagged
> **[corroborates …]** (independent triangulation is signal, not noise); where it
> surfaced only from this exercise it is tagged **[NET-NEW]**.
> **Last assembled: 2026-06-30.**

Every item must hold the four hard guardrails or it does not ship (verbatim from
`ROADMAP-FUTURE.md`): **(1)** read-only / snapshot-first source access; **(2)**
reading data never leaves the instance; **(3)** no Goodreads / no gatekept catalogs;
**(4)** describe books via sourced tags, never auto-label authors.

---

## 1. Framing: what this adds to the existing roadmaps

The shipped roadmaps are feature- and phase-complete (N1–N6 green). The persona
panel doesn't find missing *features* so much as missing **proof and provenance**:

- The **auto-gated** guardrails are strong and tested. The **review-gated** human
  sign-offs the audits depend on (privacy, representation, screen-reader) are still
  *"pending first release"* — a gate with nothing committed behind it yet.
- The invariants are **enforced in code** (`assert_allowed` default-deny;
  `ThemeTag` requires a `Source`; `Author` has no identity field) but **not surfaced**
  to the people who care: the reader, the catalogs, the authors.
- The fairness win is **real but thinly evidenced** (Precision/Recall/MAP@5 on a small
  fixture) against a literature that demands diversity-aware, temporally honest evaluation.

So this roadmap is weighted toward **assurance, provenance, and the demo→real-library
transition** — and it slots the rest of the persona wishes onto the *existing* N-phase
sequence rather than inventing a parallel one.

## 2. Research basis / evidence (cited; accessed 2026-06-30)

| Tag | Claim used | Sources |
|---|---|---|
| **EV-GOODREADS** | Goodreads (Amazon-owned) stopped issuing API keys 2020-12-08 and retired developer access, breaking OSS apps → justifies the "no Goodreads" guardrail | [Slashdot](https://developers.slashdot.org/story/20/12/17/1522242/goodreads-is-retiring-its-current-api-and-book-loving-developers-arent-happy) · [Goodreads help](https://help.goodreads.com/s/article/Why-did-my-API-key-stop-working) · [dev post-mortem](https://stephanieawilkinson.com/2020/12/10/yonderbook-and-goodreads/) |
| **EV-ETHICAL-ALT** | StoryGraph (independent, Black-owned), Hardcover (no-VC, reader-funded), Bookwyrm (federated) are the recognized non-gatekept options | [The Nod Mag](https://thenodmag.com/content/storygraph-reading-app-goodreads-alternative-woman-founded) · [Bookwise/Hardcover](https://bookwiseapp.com/blog/hardcover-app) · [joinbookwyrm](https://joinbookwyrm.com/) · [Good Good Good](https://www.goodgoodgood.co/articles/goodreads-alternatives) |
| **EV-LICENSE** | Three different obligations: OL = CC0 (attribution appreciated); Hardcover = token-gated GraphQL, "in flux," localhost/server-only; Bookwyrm = per-instance ToS, federation | [CC / Open Library](https://wiki.creativecommons.org/wiki/Case_Studies/Open_Library) · [Hardcover API docs](https://docs.hardcover.app/api/getting-started/) · [Bookwyrm FEDERATION.md](https://github.com/bookwyrm-social/bookwyrm/blob/main/FEDERATION.md) |
| **EV-SELFHOST** | Calibre-Web (GPL, OPDS) is the standard self-host frontend; KOReader sync keys progress by per-doc MD5; server-side **stats** sync is still a developing upstream feature | [Calibre-Web](https://github.com/janeczku/calibre-web) · [koreader-sync-server](https://github.com/koreader/koreader-sync-server) · [stats-sync FR #15182](https://github.com/koreader/koreader/issues/15182) |
| **EV-POPBIAS** | Book recommenders measurably under-serve niche/diverse tastes (popularity bias); thematic/genre bias specifically disadvantages long-tail interests | [Naghiaei et al. 2022](https://arxiv.org/abs/2202.13446) · [MDPI 2025](https://www.mdpi.com/2078-2489/16/2/151) · [Kalra & Daniil, RecSys 2025](https://arxiv.org/abs/2508.15643) |
| **EV-QUEER-ALGO** | Algorithmic systems under-surface / mis-handle LGBTQ+ cultural content; discoverability privileges large-corp, English content | [GLAAD 2026](https://glaad.org/2026-ai-report-build-for-everyone/lgbtq-impacts/) · [Paquette 2025](https://journals.sagepub.com/doi/10.1177/27018466251366274) |
| **EV-LABELS** | Identity labels on books harm authors; WNDB retired #OwnVoices (2021) for invading privacy / outing pressure → "describe books, not authors" | [Book Riot](https://bookriot.com/what-happened-to-the-own-voices-label/) · [Bitch Media](https://www.bitchmedia.org/article/own-voices-forcing-lgbtq-authors-out-of-closet) |
| **EV-PRIVACY** | A queer/trans reading history is sensitive: ALA logged 4,235 titles challenged in 2025 (~40% LGBTQIA+/PoC; 92% by pressure groups) → local-only/no-egress threat model | [ALA 2026](https://www.ala.org/news/2026/04/american-library-association-releases-2025-most-challenged-books-list-national-library) · [ALA data](https://www.ala.org/bbooks/book-ban-data) · [NYPL](https://www.nypl.org/blog/2024/05/28/stand-against-book-banning-lgbtq-titles-targeted-censorship) |
| **EV-A11Y** | Complex charts need a text summary + structured data-table equivalent; color must not be the only channel | [TPGi](https://www.tpgi.com/making-data-visualizations-accessible/) · [USWDS](https://designsystem.digital.gov/components/data-visualizations/) |

## 3. Remediation backlog (close gaps in what exists)

Priority: **P0** now · **P1** next · **P2** soon · **P3** opportunistic. Effort: S/M/L.

| ID | Remediation | Personas | Pri | Effort | Evidence / notes |
|---|---|---|---|---|---|
| R1 | **First real-library run** — point `stacks doctor`/`refresh` at the actual Calibre `metadata.db` + KOReader `statistics.sqlite`; verify read-only, surface "data as of …" freshness | A1, B2, B3 | P0 | M | EV-SELFHOST · **[corroborates ROADMAP-FUTURE §0 N1]** (built; first run is the untrodden path) |
| R2 | **Commit the manual a11y / screen-reader sign-off** — dated VoiceOver+NVDA walkthrough, 320px reflow, forced-colors; publish the live a11y report | A3, D2 | P0 | M | EV-A11Y · **[corroborates ROADMAP-FUTURE §0 + `accessibility-2026-06-05.md` pending items]** |
| R3 | **Commit privacy + representation review sign-offs** as dated artifacts under `docs/audits/`, each with a "what wasn't reviewed" note | D2, A2, B1 | P0 | S | EV-PRIVACY, EV-LABELS · **[NET-NEW packaging; corroborates RESPONSIBLE-TECH-AUDITS review-gated rows]** |
| R4 | **Surface descriptor provenance in the UI** — every diverse-shelf tag shows its `Source` + `retrieved_at`; option to aggregate/hide sensitive descriptors | A2, C3, D2 | P1 | S | EV-LABELS · **[NET-NEW UI; corroborates source-ethics `ThemeTag`-requires-`Source`]** · ✅ Implemented 2026-06-30 (working tree, uncommitted) — per-descriptor provenance table (kind + citation + retrieved date) in the diversity section; `STACKS_HIDE_SENSITIVE` / `?hide_sensitive=1` aggregates identity-adjacent descriptors while keeping coarse lens counts |
| R5 | **Per-source compliance card** — expand `ethical-book-data-sources.md`: CC0 vs per-instance ToS vs Hardcover token/localhost/"in-flux"; attribution posture; cache + rate-limit + robots policy; contact | C1, C2 | P1 | S | EV-LICENSE · **[corroborates ROADMAP-FUTURE C2; NET-NEW licensing nuance]** · ✅ Implemented 2026-06-30 (working tree, uncommitted) — `EthicalSource` carries license/attribution/auth/rate-limit/contact/terms; `to_markdown()` renders per-source compliance cards; doc regenerated |
| R6 | **Richer, diversity-aware eval** — add nDCG, catalog coverage, intra-list diversity, a temporal hold-out on real finishes; track metric drift; publish a fairness/diversity card | D1 | P1 | M | EV-POPBIAS · **[corroborates ROADMAP-FUTURE B5]** |
| R7 | **Live-path contract cassettes** — recorded-response tests for `KosyncClient` / `OpenLibraryClient` / Hardcover / Bookwyrm so parsers are exercised vs real shapes (today `pragma: no cover`); add TestClient route coverage | B3, D1, E1 | P1 | M | EV-SELFHOST · **[corroborates ROADMAP-FUTURE N2 + coverage-honesty]** |
| R8 | **Real (still-local) embedding model** behind the existing off-by-default flag, replacing the placeholder; strictly no egress | A1, D1 | P2 | M | **[corroborates ROADMAP-FUTURE B2]** |
| R9 | **Accessible share cards** — bake alt text + a text/plain-text equivalent into every generated Wrapped/finish card so it survives leaving the app | A3, E2 | P2 | S | EV-A11Y · **[NET-NEW]** |
| R10 | **Promote perf + reliability to merge-blocking** — k6/Locust (p95 < 500 ms), Lighthouse-CI, restart-recovery, kosync-down degrade | B2, B3 | P2 | M | **[corroborates ROADMAP-FUTURE §deferred gates / N5]** |
| R11 | **Federation etiquette, documented + enforced** — User-Agent, robots respect, backoff, aggressive caching, per-instance opt-out for Bookwyrm reads | C2, B1 | P2 | S | EV-LICENSE · **[NET-NEW; corroborates source-ethics allowlist]** · ✅ Implemented 2026-06-30 (working tree, uncommitted) — policy documented in the compliance card (`FETCH_ETIQUETTE`); descriptive User-Agent enforced on the live OpenLibrary/Bookwyrm clients via `catalogs.etiquette_headers`. Backoff/robots remain documented (live clients are `pragma: no cover` pending R7 cassettes) |
| R12 | **Egress legibility** — a one-page data-flow/egress diagram + `security.txt` + auth rate-limiting, so the no-egress property is readable outside the test suite | B1 | P3 | S | EV-PRIVACY · **[NET-NEW]** |

## 4. Expansion backlog (new capability)

| ID | Expansion | Personas | Pri | Effort | Evidence / notes |
|---|---|---|---|---|---|
| E1 | **More read-only sources, same join** — Readest progress, Kobo `KoboReader.sqlite`, Calibre-Web read-state, sideloaded EPUB/PDF | A1, B2 | P1 | M | **[corroborates ROADMAP-FUTURE A1]** |
| E2 | **Series/TBR intelligence + search/browse** by sourced theme/genre/series/status | A1 | P1 | M | **[corroborates ROADMAP-FUTURE A3, D3]** |
| E3 | **Aperture/diversity boost-only slider** — lean into small-press/own-voices/translated/underread; "unknown" stays first-class, never penalized | A2, C3, D1 | P1 | S | EV-POPBIAS, EV-QUEER-ALGO · **[corroborates ROADMAP-FUTURE B3]** |
| E4 | **Curated-list ingestion pipeline** — import named community/queer-canon lists with citation + `retrieved_at`; refresh job flags rotted links | C1, A2 | P1 | M | EV-ETHICAL-ALT · **[corroborates ROADMAP-FUTURE C3]** |
| E5 | **Adapter/plugin contract + conformance suite** — so a contributor can add an ethical catalog that *cannot* break the allowlist/provenance/sourced-tags/no-egress invariants | E1, C1 | P2 | M | **[NET-NEW]** |
| E6 | **Container one-command compose + auth upgrade + backups drill + schema-drift CI matrix** | B2, B3 | P1 | M | **[corroborates ROADMAP-FUTURE E1, E2, E3, E5]** |
| E7 | **Expanded Wrapped** — monthly timelines, pace, theme evolution across years, opt-in local PNG/PDF export (nothing auto-published) | A1, E2 | P2 | S | **[corroborates ROADMAP-FUTURE D2]** |
| E8 | **Author feedback / correction path** — a lightweight channel for a surfaced author to confirm provenance, correct a tag, or opt out; never auto-assigns identity | C3 | P2 | S | EV-LABELS · **[NET-NEW]** |
| E9 | **Bookwyrm activity import** — your own shelves/reviews over ActivityPub, read-only, behind the allowlist, cached | E2, A1 | P2 | M | EV-LICENSE · **[corroborates ROADMAP.md §3 "Could: federated Bookwyrm activity import"]** |
| E10 | **KOReader server-side statistics sync** — ingest stats sync when upstream ships it, still read-only/local | A1, B2 | P3 | M | EV-SELFHOST (tracks upstream FR #15182) · **[NET-NEW]** |
| E11 | **Private annotations / commonplace book** + sidecar highlight-*text* import from KOReader; never synced anywhere | A1 | P3 | M | **[corroborates ROADMAP-FUTURE A2]** |
| E12 | **Gentle negative signals** — opt-in DNF / low-dwell down-weighting, explained | A1, D1 | P3 | S | **[corroborates ROADMAP-FUTURE B4]** |

## 5. Sequenced roadmap (slots onto the existing N-phases)

| Window | Theme | Items | Why now |
|---|---|---|---|
| **Now (assurance sprint)** | Close the review-gated gap + go real | R1, R2, R3 | The audits already gate the release on these; they're the highest-trust, lowest-effort work and unblock "first real run" |
| **Next (provenance & sourcing)** | Make invariants visible; serve the stewards | R4, R5, R7, R11, E4 | Provenance serves River/Tomás/Lior/Petra at once; cassettes make sourcing honest in CI |
| **Then (fairness & depth)** | Prove the recommender fairly; daily-driver depth | R6, R8, E1, E2, E3 | Diversity-aware eval answers EV-POPBIAS; more sources + browse make it a daily tool |
| **Later (production & polish)** | Ship-on-a-stranger's-box; expand | R9, R10, E5, E6, E7, E9 | Perf/reliability gates + accessible share cards + contributor on-ramp |
| **Opportunistic** | Nice-to-have | R12, E8, E10, E11, E12 | Bounded by upstream (E10) or low demand-signal |

## 6. Recommended first sprint (highest-leverage, mostly already-built infra)

The triage and the existing roadmaps converge on the same starting line: **the
features are built; the *assurance* isn't.** Ship these five:

1. **R1 — first real-library run.** Turns the demo into the tool it's meant to be;
   unblocks Chelsea (A1) and de-risks every downstream item. (`stacks doctor`/`refresh`
   already exist — this is the first run + freshness stamp.)
2. **R2 — commit the screen-reader / manual a11y sign-off.** The audit lists it
   "pending"; a real VoiceOver+NVDA walkthrough + published live report converts
   "0 axe violations" into lived-experience proof (A3, D2).
3. **R3 — commit the privacy + representation sign-offs.** Same shape: dated artifacts
   behind gates that currently have nothing behind them (D2, A2, B1). EV-PRIVACY,
   EV-LABELS make these the most consequential reviews in the project.
4. **R4 — surface descriptor provenance in the UI.** One change that serves four
   personas (River, Tomás, Lior, Petra): show each tag's `Source` + `retrieved_at`,
   and let sensitive descriptors be aggregated/hidden. Leans entirely on the existing
   `ThemeTag`→`Source` invariant.
5. **R5 — per-source compliance card.** Expand `ethical-book-data-sources.md` into the
   three real obligations (CC0 / per-instance ToS / Hardcover token-localhost). Cheap,
   and it's what the stewards the tool depends on actually want.

Bundle the afternoon-sized wins alongside: **R9** (accessible share cards) and the
first half of **R11** (documented federation etiquette).

## 7. Traceability matrix (persona → findings)

| Persona | Remediations | Expansions |
|---|---|---|
| A1 Chelsea (reader/owner) | R1, R8 | E1, E2, E7, E9, E10, E11, E12 |
| A2 River (queer/trans reader) | R3, R4 | E3, E4 |
| A3 Mara (a11y user) | R2, R9 | — |
| B1 Sam (privacy self-hoster) | R3, R11, R12 | — |
| B2 Devon (tinkerer/deployer) | R1, R7, R10 | E1, E6, E10 |
| B3 Chelsea (ops/maintainer) | R1, R7, R10 | E6 |
| C1 Lior (Open Library steward) | R5, R7 | E4, E5 |
| C2 Petra (Bookwyrm admin) | R5, R11 | E9 |
| C3 Tomás (indie author) | R4 | E3, E8 |
| D1 Dr. Ada (ML reviewer) | R6, R7, R8 | E3, E12 |
| D2 Noor (responsible-tech reviewer) | R2, R3, R4 | — |
| E1 Robin (OSS contributor) | R7 | E5 |
| E2 Jules (Fediverse mutual) | R9 | E7, E9 |

## 8. Validate with real users / risks

Because the product is single-user, "validation" means talking to the **stakeholders
the tool depends on**, not running a usability lab:

- **Data stewards (highest stakes).** Before any wider sourcing, confirm with an Open
  Library / Internet Archive contact and a representative Bookwyrm instance admin that
  the cache/rate-limit/robots posture (R5, R11) is genuinely welcome. *Risk:* a
  well-meaning federated reader can still be an unwelcome load — verify EV-LICENSE
  assumptions with a real admin, not docs alone.
- **Assistive-tech walkthrough (R2).** The manual SR pass must be done by — or with —
  an actual screen-reader user; "0 axe violations" is necessary, not sufficient (EV-A11Y).
- **An indie/small-press author (R4, E8).** Show one real surfaced author their
  provenance view and ask whether anything reads as a mislabel. *Risk:* the worst
  failure (EV-LABELS) is invisible to the author who can't see what's attached to them.
- **Recommender fairness (R6).** *Risk:* a perfect 1.00 on a tiny synthetic fixture is
  not evidence the model beats popularity on real, temporally-split reads — the
  literature (EV-POPBIAS) predicts the hard case is exactly the niche/diverse tail this
  tool targets. Treat R6 as falsification, not confirmation.
- **A stranger's deploy (R10, E6).** Watch one homelabber stand it up cold; the
  demo→real and reverse-proxy/auth paths are where it'll break.

## 9. Honest limits

This roadmap is derived from a **synthetic** panel plus public research, not from real
discovery. It can sequence work and flag obligations, but it cannot tell you which
matter most to the real people behind the catalogs, whether anyone but Chelsea would
deploy it, or how a steward/author/SR-user would actually react. It over-weights what
is legible from the repo (the guardrails, the audits) and under-weights what only a
real conversation would surface. The **[corroborates …]** tags show most of this isn't
new — it's the existing N-phase plan re-prioritized toward *assurance and provenance*;
the genuinely **[NET-NEW]** items (R3 packaging, R4 UI provenance, R9 accessible cards,
R11 federation etiquette, E5 adapter contract, E8 author feedback, E10 stats sync) are
the parts most in need of real-world validation before they're treated as commitments.
Re-run against `ROADMAP.md` / `ROADMAP-FUTURE.md` whenever those change, and per
Calibre/KOReader schema or Open Library / Hardcover / Bookwyrm API change.
