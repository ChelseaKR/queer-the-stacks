# User Research — Synthetic Personas & Simulated Interviews

> [!WARNING]
> **These personas and interviews are synthetic.** They were generated as a
> structured brainstorming device — *not* conducted with real people. No real
> reader, contributor, data steward, or author said any of this. The panel exists
> to pressure-test the product from many angles at once; it is **not** evidence of
> demand and does **not** substitute for real discovery. Treat every "quote" as a
> hypothesis to validate, not a finding. (Consistent with how this project labels
> its synthetic eval fixtures — see [`audits/source-ethics.md`](./audits/source-ethics.md).)
>
> The honest next step is real conversations with people in ≥5 of these roles —
> especially the **data stewards** (Open Library / Bookwyrm) whose terms this tool
> depends on, and the **review-gated sign-offs** (privacy, representation, screen
> reader) the audits list as *pending first release*.
> **Last assembled: 2026-06-30.**

## Why do this at all
Queer the Stacks is a single-user, self-hosted app, so the "user" is mostly one
person (Chelsea). But the *stakeholders* are not: the tool reads from other
people's catalogs (Open Library, Bookwyrm, Hardcover), surfaces other people's
books (small-press and indie authors), and would be deployed and audited by people
who are not Chelsea. Role-playing the full cast surfaces obligations a single
author misses — especially the ones that are ethical or legal, not just features.
Findings at the end are tagged so this doesn't become a wishlist:

- **[shipped]** — already exists in the M0–M6 + N1–N6 build.
- **[pending]** — a review-gated sign-off the audits already name but haven't signed.
- **[roadmap]** — already in [`ROADMAP.md`](./ROADMAP.md) / [`ROADMAP-FUTURE.md`](./ROADMAP-FUTURE.md).
- **[NET-NEW]** — genuinely surfaced here.

## How to read a persona
Each card is the simulated interview compressed to five lines — **Goal · What
they'd value today** (mapped to *real, shipped* features) **· Where they'd get
stuck · What they'd want next · The one thing that makes them adopt (or walk).**

---

## Method

- **Sampling frame.** Not "users" but *stakeholders around a private reading tool*:
  people who **read & discover** (the owner; a queer/trans reader; an
  assistive-tech user), people who **self-host & operate** (a privacy-conscious
  self-hoster; a homelab tinkerer who'd deploy it; the maintainer), people whose
  catalogs the tool **sources from** and whose terms it must respect (an Open Library /
  open-data steward; a Bookwyrm instance admin; a small-press author whose book gets
  surfaced), people who **assure & audit** (an ML/recommender-fairness reviewer; a
  responsible-tech reviewer doing the human sign-offs), and people who'd **extend or
  share** it (an OSS contributor; a Fediverse/Bookwyrm mutual on the receiving end of
  a share card).
- **Protocol.** For each: a goal, a walkthrough of the surfaces or guarantees they'd
  touch, what holds up against the *current* build, where they'd stall, and an open
  "what would make this a 10/10" prompt. Frictions become **R**emediations; wishes
  become **E**xpansions in [`RESEARCH-ROADMAP.md`](./RESEARCH-ROADMAP.md).
- **Effort scale (used in the roadmap).** S ≈ an afternoon · M ≈ a day or two ·
  L ≈ a week+.

### Research basis

The panel is grounded in the public record on the ebook self-hosting ecosystem,
the Goodreads-alternative landscape, book-data licensing, recommender bias, and
reading privacy. High-stakes claims are cross-checked against ≥2 sources.
Accessed **2026-06-30**.

- **Goodreads' enclosure is real, not rhetoric.** Goodreads (Amazon-owned since
  2013) stopped issuing new API keys on **2020-12-08** and disabled many existing
  ones, retiring developer access entirely and breaking open-source apps built on
  it — corroborated by [Slashdot](https://developers.slashdot.org/story/20/12/17/1522242/goodreads-is-retiring-its-current-api-and-book-loving-developers-arent-happy),
  Goodreads' own [help article](https://help.goodreads.com/s/article/Why-did-my-API-key-stop-working),
  and a [developer post-mortem](https://stephanieawilkinson.com/2020/12/10/yonderbook-and-goodreads/).
  This is the factual backbone of the project's "no Goodreads" guardrail.
- **The ethical-alternative landscape exists and is values-aligned.**
  [The StoryGraph](https://thenodmag.com/content/storygraph-reading-app-goodreads-alternative-woman-founded)
  (independent, Black-owned, Amazon-free), [Hardcover](https://bookwiseapp.com/blog/hardcover-app)
  (small team, no venture capital, ad-free, reader-funded), and
  [Bookwyrm](https://joinbookwyrm.com/) (federated, community-run) are the
  recognized non-gatekept options; see also a [survey of ethical trackers](https://www.goodgoodgood.co/articles/goodreads-alternatives).
  This tool sources from Open Library / Hardcover / Bookwyrm — not from these as
  competitors, but as the same values commitment.
- **Licensing differs by source and must be honored per source.** Open Library data
  is dedicated to the public domain under **CC0** (attribution appreciated, not
  required) per [Creative Commons](https://wiki.creativecommons.org/wiki/Case_Studies/Open_Library);
  [Hardcover's API](https://docs.hardcover.app/api/getting-started/) is a free
  GraphQL endpoint that is "heavily in flux," gated by a personal token, and
  restricted to localhost/server use; [Bookwyrm](https://github.com/bookwyrm-social/bookwyrm/blob/main/FEDERATION.md)
  is ActivityPub-federated with **per-instance** terms. A single "ethical sources"
  line under-describes three different obligations.
- **The self-hosting stack is real and read-only-friendly.**
  [Calibre-Web](https://github.com/janeczku/calibre-web) (GPL-3.0, OPDS) is the
  established self-hosted Calibre frontend; the
  [KOReader sync server](https://github.com/koreader/koreader-sync-server) is
  self-hostable and keys progress by a per-document MD5 — matching ADR-2's md5
  progress key. Server-side **statistics** sync is still a
  [developing upstream feature](https://github.com/koreader/koreader/issues/15182),
  which bounds what cross-device stats can promise today.
- **Mainstream book recommenders are measurably biased against the long tail.**
  Naghiaei et al. find most state-of-the-art algorithms "suffer from popularity
  bias in the book domain, and fail to meet users' expectations with Niche and
  Diverse tastes" while "Bestseller-focused users… receive high-quality
  recommendations" ([arXiv 2202.13446](https://arxiv.org/abs/2202.13446)); a 2025
  survey reaches the same conclusion about long-tail fairness
  ([MDPI Information](https://www.mdpi.com/2078-2489/16/2/151)); and a RecSys-2025
  study shows *thematic/genre* bias specifically disadvantages "users with niche and
  long-tail interests" ([arXiv 2508.15643](https://arxiv.org/abs/2508.15643)). This
  is exactly the gap the content-beats-popularity eval targets.
- **Algorithmic systems under-surface and mis-handle LGBTQ+ cultural content.** GLAAD
  documents recommendation/moderation harms to LGBTQ+ content
  ([2026 AI report](https://glaad.org/2026-ai-report-build-for-everyone/lgbtq-impacts/));
  scholarship on discoverability finds algorithms privilege "English-language…
  content produced by large global corporations"
  ([Paquette, 2025](https://journals.sagepub.com/doi/10.1177/27018466251366274)).
- **Identity labels on books can harm the people behind them.** We Need Diverse
  Books retired **#OwnVoices** in June 2021 because it was "vague and has been
  misused to gate-keep identities and invade authors' privacy," and now uses "the
  specific descriptions that authors use for themselves"
  ([Book Riot](https://bookriot.com/what-happened-to-the-own-voices-label/)); the
  label was warped into pressure to out authors
  ([Bitch Media](https://www.bitchmedia.org/article/own-voices-forcing-lgbtq-authors-out-of-closet)).
  This is the evidence behind "describe books via *sourced* tags; never auto-label
  authors."
- **A queer/trans reading history is genuinely sensitive.** In 2025 the ALA logged
  4,235 unique titles challenged (its second-highest ever), ~40% representing the
  lived experiences of LGBTQIA+ people and people of color, with 92% of challenges
  driven by pressure groups and officials — *Gender Queer* and *Last Night at the
  Telegraph Club* among the most targeted
  ([ALA, 2026](https://www.ala.org/news/2026/04/american-library-association-releases-2025-most-challenged-books-list-national-library);
  [ALA data](https://www.ala.org/bbooks/book-ban-data);
  [NYPL](https://www.nypl.org/blog/2024/05/28/stand-against-book-banning-lgbtq-titles-targeted-censorship)).
  This is why local-only, no-egress, behind-auth isn't paranoia — it's the threat model.
- **Charts must ship table equivalents to be accessible.** Complex visualizations
  need a text summary plus a structured data table; color must never be the only
  channel ([TPGi](https://www.tpgi.com/making-data-visualizations-accessible/);
  [USWDS](https://designsystem.digital.gov/components/data-visualizations/)) —
  exactly the contract `make a11y` already enforces.

---

## Persona roster

| # | Persona | Group | Primary goal | Top friction |
|---|---|---|---|---|
| A1 | **Chelsea** — primary reader & owner | Read & Discover | See all my reading in one private place; get recs that fit my canon | Build is demo-driven; not yet pointed at her real library |
| A2 | **River** — queer/trans reader, anti-essentialist | Read & Discover | Representation analytics that describe *books*, never label *me* or authors | Wants to see *where* each descriptor came from, and hide sensitive ones |
| A3 | **Mara** — low-vision dashboard user (magnifier + screen reader) | Read & Discover | Read the dashboard, stats, and Wrapped non-visually | Automated a11y passes, but no *human* SR walkthrough is signed off |
| B1 | **Sam** — privacy-conscious self-hoster | Self-Host & Operate | Prove reading data never leaves the box | Wants the no-egress claim demonstrable, not just asserted |
| B2 | **Devon** — homelab tinkerer / would-be deployer | Self-Host & Operate | Stand it up next to Calibre-Web on a seedbox in an evening | First-run is demo-shaped; real-library config path is new (N1) |
| B3 | **Chelsea (ops hat)** — owner / maintainer | Self-Host & Operate | Keep it running, backed up, and resilient to schema drift | Perf/reliability gates are deferred, not yet merge-blocking |
| C1 | **Lior** — Open Library / open-data steward | Source Ethically | See the project honor CC0 + rate limits + provenance | One "ethical sources" line flattens three different obligations |
| C2 | **Petra** — Bookwyrm instance admin | Source Ethically | Confirm federation etiquette: robots, rate limits, per-instance ToS | No public statement of how the tool treats her instance's terms |
| C3 | **Tomás** — small-press / indie author | Source Ethically | Be surfaced fairly, with no misattributed identity label | No path to confirm provenance or correct/opt-out |
| D1 | **Dr. Ada** — recommender / ML-fairness reviewer | Assure & Audit | Verify it beats popularity *fairly*, not just on one metric | Eval is Precision/Recall@5 only; no nDCG/diversity/temporal split |
| D2 | **Noor** — responsible-tech reviewer (human sign-off) | Assure & Audit | Sign the privacy + representation + SR reviews honestly | Those sign-offs are listed "pending," with no committed artifact |
| E1 | **Robin** — OSS contributor | Community / Expand | Add a new ethical catalog adapter and get it merged | No documented adapter contract / conformance test |
| E2 | **Jules** — Fediverse / Bookwyrm mutual | Community / Expand | Enjoy Chelsea's shared Wrapped/finish cards without surveillance | Share cards may lack alt text; wants the "no auto-egress" guarantee visible |

---

## Group A — Read & Discover (the reader at the dashboard)

### A1. Chelsea — primary reader & owner
- **Goal:** one private place that shows what she's reading across Calibre, KOReader,
  Calibre-Web, and Readest — plus recs that fit Plett/Peters/Thom/Butler/Atwood.
- **Values today:** the unified cross-device "currently reading" + history; reading
  stats, streaks, and the self-hosted **Wrapped**; the hybrid recommender with
  **why + source** on every card; **diverse-shelf analytics built only from sourced
  descriptors**; local **goals**; locally-composed **share cards** that egress
  nothing until she copies them. *(this is the whole product thesis)*
- **Gets stuck:** the shipped build is demo-driven — it proves the gates but isn't
  yet pointed at her real `metadata.db` / `statistics.sqlite`; `stacks doctor`/
  `refresh` (N1) exist but the real-library first run hasn't happened.
- **Wants next:** point it at the real library with a "data as of …" freshness stamp;
  a real (still-local) embedding model behind the existing flag; more read-only
  sources (Readest, Kobo, Calibre-Web read-state); series/TBR depth.
- **Adopts if:** the real library lights up the dashboard without touching the
  sources. **Walks if:** it stays a demo she has to babysit.

### A2. River — queer/trans reader seeking representation without essentialism
- **Goal:** understand the shape of their reading ("how queer/trans/spec-fic is my
  shelf?") **without** the tool putting an identity label on them or on any author.
- **Values today:** diverse-shelf analytics that are, by construction, **sourced**:
  `ThemeTag` cannot be built without a `Source` (a Calibre tag, OL subject, or
  curated list), and `Author` has **no** gender/sexuality/identity field — so there
  is literally nowhere to auto-assign one. Chart + **table** equivalents; tags shown
  as text, never color-only. *(directly answers the #OwnVoices outing harm)*
- **Gets stuck:** can see *that* a book is tagged "trans" but not *where the tag came
  from* or how confident it is; worries a sensitive descriptor could be visible on a
  shared card.
- **Wants next:** provenance on every descriptor ("from Open Library subject / curated
  list X, retrieved 2026-…"); the option to aggregate or hide sensitive descriptors;
  an aperture lens that boosts (never penalizes) underread/own-voices/translated work
  with "unknown" staying first-class.
- **Adopts if:** the analytics describe books, cite sources, and never essentialize.
  **Walks if:** it ever infers a person's identity from a name, cover, or model.

### A3. Mara — low-vision reader using magnification + a screen reader
- **Goal:** read the dashboard, stats, and Wrapped entirely non-visually / at 200% zoom.
- **Values today:** the *mechanically verified* a11y contract — one `<h1>`, landmarks
  + skip link, every chart shipped with a real `<table>` equivalent, theme/progress
  conveyed as text (a `#` glyph + label) not color, `prefers-reduced-motion`
  respected, 0 axe violations via `make a11y`. *(matches WCAG complex-image guidance)*
- **Gets stuck:** the audit itself flags that the **manual** passes are *not yet
  signed off* — no real VoiceOver/NVDA walkthrough, no 320px-reflow or
  forced-colors check, and streamed/interactive updates aren't SR-audited.
- **Wants next:** a committed, dated SR-walkthrough artifact; a published live a11y
  report; and — when share cards exist — **alt text baked into the card image** so
  it's accessible after it leaves the app.
- **Adopts if:** a human like her has actually driven it end-to-end and signed it.
  **Walks if:** "0 violations" is the *only* evidence and the lived path breaks.

---

## Group B — Self-Host & Operate

### B1. Sam — privacy-conscious self-hoster
- **Goal:** be convinced a queer/trans reading history can't leak off the box.
- **Values today:** auth fails closed (401 without a valid token; even demo needs
  one); network is confined to two clients (the user's own kosync server + GET-only
  public catalog metadata) and **never POSTs reading history**; no analytics/telemetry
  SDK in core; a log-safety lint keeps reading content out of logs — all
  *merge-blocking tests*, not promises. *(the threat model the book-ban data justifies)*
- **Gets stuck:** wants the guarantee legible from outside the test suite — a plain
  data-flow he can read, and assurance the *catalog* lookups can't fingerprint him.
- **Wants next:** a committed dated **privacy review** sign-off (the audit lists it
  "pending"); a one-page egress diagram; per-source notes on what each catalog call
  reveals; `security.txt` + auth rate-limiting.
- **Adopts if:** "nothing sensitive leaves" is demonstrable. **Walks if:** any
  reading data, even derived, touches a third party.

### B2. Devon — homelab tinkerer who'd actually deploy it
- **Goal:** run it next to Calibre-Web on a seedbox in one evening, read-only against
  the real libraries.
- **Values today:** the container + `docker-compose.yml` that mounts the real
  libraries **`:ro`** (kernel-level belt-and-braces over the in-code snapshot);
  `stacks doctor` to validate paths and confirm read-only access; config via env or
  `stacks.toml`; the documented quickstart. *(mirrors the established Calibre-Web/
  KOReader-sync self-hosting pattern)*
- **Gets stuck:** the build is demo-shaped, so the real first run (paths, kosync key
  from env, storage dir, detected schema versions) is the newest, least-trodden path;
  reverse-proxy/auth wiring is documented but unverified by a stranger.
- **Wants next:** a one-command compose + reverse-proxy/auth recipe; OIDC/forward-auth
  upgrade path; backups/restore drill; a schema-drift CI matrix so a different
  Calibre/KOReader version still ingests.
- **Adopts if:** a clean box reaches a working, authed dashboard in <30 min.
  **Walks if:** first-run requires reverse-engineering env vars.

### B3. Chelsea (ops hat) — owner / maintainer / operator
- **Goal:** keep it running, backed up, and resilient as Calibre/KOReader schemas drift.
- **Values today:** persisted derived state with `stacks refresh` (ingest only if
  source mtime changed) + freshness stamp; `stacks backup`/`restore`; restart-recovery
  and "kosync down → degrade to KOReader-only" reliability tests; versioned,
  fixture-tested parsers; `pip-audit` = 0 vulns on the Python 3.14 floor.
- **Gets stuck:** performance (k6/Lighthouse p95) and some reliability gates are
  **deferred**, not yet merge-blocking; live-path clients (`KosyncClient`,
  `OpenLibraryClient`) are `pragma: no cover`, so real response-shape drift isn't
  caught in CI.
- **Wants next:** promote perf + reliability to merge-blocking; recorded-cassette
  contract tests for the live clients; TestClient route coverage; a dated schema-drift
  matrix.
- **Adopts if:** an unattended seedbox stays correct across restarts and upgrades.
  **Walks if:** a silent schema change corrupts ingest.

---

## Group C — Source Ethically (whose terms this tool depends on)

### C1. Lior — Open Library / open-data steward
- **Goal:** see a downstream project use Open Library data *respectfully* — within
  CC0, with rate-limit discipline and provenance.
- **Values today:** Open Library is on the hard allowlist; `assert_allowed()` is
  default-deny; the recommender's single network choke point only GETs public
  metadata; `docs/ethical-book-data-sources.md` is generated from
  `recommender/sources.py` (one source of truth) and documents *why* each catalog is
  used. *(CC0 = public-domain dedication, attribution appreciated)*
- **Gets stuck:** the sources doc is terse — it doesn't spell out CC0 vs ODbL nuance,
  caching/rate-limit behavior, or robots respect, so a steward can't tell at a glance
  that the project is a *good* consumer.
- **Wants next:** a per-source **compliance card**: license (CC0 here), attribution
  posture, cache + rate-limit policy, `retrieved_at` provenance on every field, and
  a contact. Credit Open Library/Internet Archive even though CC0 doesn't require it.
- **Adopts (endorses) if:** the project is visibly a careful, low-impact consumer.
  **Walks if:** it hammers the API or strips provenance.

### C2. Petra — Bookwyrm instance admin / Fediverse data steward
- **Goal:** make sure federated reads honor **her instance's** terms, robots, and rate
  limits — Bookwyrm terms are per-instance, not global.
- **Values today:** Bookwyrm is allowlisted as *federated* with "per-instance terms;
  honor robots + rate limits" already written into the sources table; the tool is
  read-only and posts nothing back; share cards are composed locally and only posted
  when Chelsea manually copies them (no auto-federation). *(matches ActivityPub
  federation norms)*
- **Gets stuck:** there's no explicit, public statement of *how* the tool decides an
  instance is fair game, how it backs off, or how it caches — so an admin has to take
  it on faith.
- **Wants next:** documented federation etiquette (User-Agent, robots, backoff,
  per-instance opt-out); pull only public list/metadata, never private activity;
  cache aggressively to minimize hits.
- **Adopts if:** her instance is treated as a guest treats a host. **Walks if:** it
  scrapes federated data as if it were a central API.

### C3. Tomás — small-press / indie author whose book gets surfaced
- **Goal:** have his work discovered fairly, with **no** identity label pinned on him
  that he didn't choose.
- **Values today:** the whole design is built so recommendations *widen* past
  bestseller bias toward small-press/own-voices/translated work (the eval deliberately
  hides on-canon picks among more-popular distractors and recovers them); books are
  described by **sourced** tags, and `Author` carries only a name + sort key — so the
  tool *cannot* auto-assign him a gender/sexuality. *(directly answers the #OwnVoices
  outing harm and long-tail under-surfacing)*
- **Gets stuck:** he has no way to see *what* provenance/tags attach to his book, or to
  correct a wrong tag or ask not to be surfaced.
- **Wants next:** a lightweight author feedback/correction path; visible provenance per
  book; a guarantee that any descriptor traces to a source he or a catalog set, never
  an inference.
- **Adopts if:** he's surfaced accurately and never mislabeled. **Walks if:** a model
  ever guesses his identity from his name or cover.

---

## Group D — Assure & Audit

### D1. Dr. Ada — recommender / ML-fairness reviewer
- **Goal:** confirm the recommender beats the popularity baseline **fairly**, not by
  cherry-picked metrics or leakage.
- **Values today:** a deterministic, seeded recommender; an eval that shows the content
  model (themes + authors + curated lists) at Precision@5 / Recall@5 / MAP@5 = 1.00 vs
  a popularity baseline at 0.40 / 0.40 / 0.13, regenerated into `eval-report.json`;
  100% of recs carry why + source; the aperture lens is **boost-only** and "unknown"
  is never penalized. *(targets the documented popularity/thematic bias)*
- **Gets stuck:** the eval is small and Precision/Recall/MAP@5-only — no nDCG, catalog
  coverage, intra-list diversity, or *temporal* hold-out on real finishes; a perfect
  1.00 on a tiny fixture invites "it's a toy benchmark."
- **Wants next:** richer ranking + diversity metrics, a temporal split on actual reads,
  metric-drift tracking across runs, and a published fairness/diversity card so the
  "beats popularity *fairly*" claim is legible.
- **Adopts if:** the win survives diversity-aware, temporally honest evaluation.
  **Walks if:** the headline is one inflated number on synthetic data.

### D2. Noor — responsible-tech reviewer doing the human sign-offs
- **Goal:** honestly sign the **privacy**, **representation**, and **screen-reader**
  reviews that the audits gate the first release on.
- **Values today:** the auto-gated half is genuinely strong — no-egress, sourced-tags,
  auth, and axe checks are all merge-blocking with named tests; the responsible-tech
  framework cleanly separates *auto-gated* from *review-gated*.
- **Gets stuck:** all three human sign-offs are explicitly **"pending first release"**
  with no committed artifact — so right now there's a gate with nothing behind it.
- **Wants next:** dated, committed sign-off artifacts under `docs/audits/` for the
  privacy review, the representation review, and the SR walkthrough; a short
  "what wasn't reviewed" note in each.
- **Adopts if:** every review-gated claim has a signed, dated artifact. **Walks if:**
  "pending" silently becomes "done" at release without the walkthroughs.

---

## Group E — Community / Expand

### E1. Robin — OSS contributor
- **Goal:** add a new ethical catalog adapter (or a curated-list importer) and get it
  merged without weakening the guardrails.
- **Values today:** clear architecture (`ingest/` · `recommender/` · `app/`); a single
  network choke point with a default-deny allowlist; a generated sources doc; green
  `make verify` (lint, `mypy --strict`, ~167 tests @ ~96%, a11y, eval) as a contract.
- **Gets stuck:** there's no documented *adapter contract* or conformance test, so a
  new source could drift from the provenance/allowlist/sourced-tags invariants; unsure
  how to add a source without tripping the no-egress test.
- **Wants next:** a published adapter/plugin contract + conformance suite (allowlist
  honored, provenance attached, `ThemeTag` sourced, no egress of reading data); a
  "add an ethical source" guide; good-first-issues.
- **Adopts if:** their first adapter PR is mergeable in a day and *can't* violate an
  invariant. **Walks if:** contributing risks silently breaking a guardrail.

### E2. Jules — Fediverse / Bookwyrm mutual (the sharing community)
- **Goal:** enjoy Chelsea's shared "year in books" / finished-book cards on Bookwyrm or
  Mastodon — without being surveilled or fed an ad.
- **Values today:** share cards are **composed locally** and posted **only when Chelsea
  copies and shares them** — no auto-egress, no tracking pixel, no follower-graph
  scraping; nothing about Jules is ingested. *(values-aligned with federated, no-ad
  Bookwyrm norms)*
- **Gets stuck:** a card posted as an image may lack alt text (excludes blind mutuals);
  and the "this didn't phone home" guarantee isn't visible to the *recipient*.
- **Wants next:** alt text + a text equivalent baked into every generated card; an
  optional plain-text version; a one-line "composed locally, shared manually" footer so
  the no-surveillance property is legible to followers.
- **Adopts (engages) if:** the cards are accessible and demonstrably egress-free.
  **Walks if:** a "share" quietly turns into auto-posting or tracking.

---

## Cross-cutting themes (what the cast agrees on)

1. **The guardrails are the product, and they hold — but the *human* sign-offs are
   empty.** Sam (privacy), Mara (SR), Noor (all three), and River (representation) all
   independently land on the same thing: the auto-gated tests are excellent, yet the
   three **review-gated sign-offs the audits themselves name are still "pending."**
   That's the single highest-trust, lowest-effort gap. **[pending]**
2. **"Demo works" ≠ "runs on the real library."** Chelsea, Devon, and Chelsea-ops all
   hit the demo→real gap. N1 (`stacks doctor`/`refresh`, freshness stamp) is built but
   the first real run, and a stranger's first deploy, are the least-trodden paths.
   **[roadmap N1]**
3. **Provenance wants to be *visible*, not just *enforced*.** River, Tomás, Lior, and
   Petra each ask the same question from a different seat: *where did this come from?*
   The invariant exists in code (`ThemeTag` needs a `Source`; `assert_allowed` is
   default-deny) — but it isn't surfaced in the UI or to the catalogs/authors involved.
   Surfacing provenance is cheap and serves four personas at once. **[NET-NEW UI;
   corroborates source-ethics]**
4. **Sources are three obligations, not one.** Lior (CC0, attribution-appreciated),
   Petra (per-instance ToS + federation etiquette), and the Hardcover constraint
   (token-gated, localhost-only, "in flux") mean the single "ethical sources" line
   under-serves the stewards the tool depends on. A per-source compliance card fixes it.
   **[NET-NEW; corroborates ROADMAP-FUTURE C2]**
5. **The fairness claim is real but thinly evidenced.** Ada wants the popularity-beating
   result shown *fairly* — nDCG, diversity, a temporal split — which is exactly the
   "richer eval" already on the future roadmap. The research backs the need: book
   recommenders measurably under-serve niche/diverse/thematic tastes. **[roadmap B5]**
6. **Accessibility has to survive leaving the app.** Mara and Jules note the dashboard's
   a11y contract is strong *inside* the app, but a shared card is an image that escapes
   it — alt text must travel with the card. **[NET-NEW]**

## Honest limits of this exercise
This is simulated. It can generate plausible obligations and obvious gaps, but it
cannot tell you **which** matter most to the real people behind the catalogs, which
self-hosters would actually deploy it, or how an Open Library / Bookwyrm steward would
*really* feel about being consumed. Because the product is single-user, the panel
leans heavily on the author's own mental model and on stakeholders who would never
file an issue — so it over-weights what is *legible from the repo* and under-weights
what only a real steward, author, or assistive-tech user would surprise you with.
**Do not prioritize off this alone.** Use it to design the questions for — and lower
the cost of — real conversations, especially with the data stewards and the
review-gated sign-offs.

The triaged remediation/expansion backlog, sequencing, first sprint, and traceability
matrix live in **[`RESEARCH-ROADMAP.md`](./RESEARCH-ROADMAP.md)**.
