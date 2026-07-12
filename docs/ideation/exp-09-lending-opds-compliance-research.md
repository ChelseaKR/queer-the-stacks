# EXP-09 Compliance Research — Open Library Lending & Generic OPDS (2026-07-09)

> **Status: RESEARCH ONLY. Not an allowlist decision.** This document does the
> terms-of-service *research* piece of EXP-09 ("Borrowability on the TBR")
> that a human can delegate. It does **not** add `openlibrary.org`'s lending
> surface or any OPDS host to `recommender/sources.py::ETHICAL_SOURCES` or
> `recommender/catalogs.py::ALLOWED_HOSTS`, and no borrow/lending/OPDS client
> code is implemented here. The **legal/SME sign-off** EXP-09 names as its gate
> — "is this actually okay to ship, and to whom do we represent ourselves as a
> partner" — is Chelsea's call, informed by §5/§6 below, not this document's.

Card format follows the compliance-card pattern implemented on
`research-panel-and-roadmap` (item R5: expanded `EthicalSource` — kind,
license/terms, attribution, auth, cache/rate-limit/robots, contact, terms
URL, why) and rendered today for the three already-allowed sources in
`docs/ethical-book-data-sources.md`. Two fields are added here because
lending/OPDS sources don't fit that dataclass's "sign up for a key and go"
shape (see §5): **partnership required?** and **open questions**.

---

## 1. Scope & method

Two research targets, both real, both fetched/searched 2026-07-09 (sources
cited inline and listed again in §7):

1. **Open Library's actual API terms** (`openlibrary.org/developers/api`),
   plus specifically its **Lending API / borrow surface**, which is legally
   and operationally distinct from the bibliographic-metadata API this repo
   already calls today.
2. **OPDS as a protocol** — what it requires of a *consuming client* — plus
   two real public-library-facing OPDS catalog providers, to see how "OPDS
   compliance" actually differs per host.

## 2. The load-bearing distinction: Open Library has (at least) three different surfaces

`openlibrary.org` is **already** on `ALLOWED_HOSTS` and `ETHICAL_SOURCES` —
but only for the **bibliographic/subjects API** (`OpenLibraryClient` in
`recommender/catalogs.py` calls `/subjects/<s>.json`). EXP-09 asks about a
*different* surface with materially different terms:

| Surface | What it is | Terms posture |
|---|---|---|
| Bibliographic API (`/subjects/*.json`, search, works/editions) | Already allowed in this repo | CC0 data, no key, generic API ToS |
| **Read API / availability check** (`status`: `full access` / `lendable` / `checked out` / `restricted`) | Tells you *whether* a book is currently borrowable | Same generic API ToS + rate limits; **no account needed to check** |
| **Borrow/checkout action** | Actually starts a loan for a patron | Requires a **logged-in Open Library patron account**; no documented third-party delegation/OAuth |
| **"In Library" partner tier** | IP-authenticated *expanded* borrowable catalog for a physical library's patrons | Requires a **formal Internet Archive/Open Libraries partnership** — institutional, not an API key |

This three/four-way split is the single most important finding: **"is Open
Library lending open?" has no one answer.** Metadata: yes, already using it.
Checking if a book is borrowable: probably fine under the general API terms.
Actually lending it through this app, or getting the bigger "In Library"
catalog: no — those require steps a self-hosted single-reader tool doesn't
have going through them today.

## 3. Compliance card — Open Library (Read API / lending surfaces)

| Obligation | Posture |
|---|---|
| Kind | `api` (availability check) / `partnership` (borrow action, In-Library tier) — **not** `open-data` like the existing bib-API entry |
| License / terms | General API ToS at `openlibrary.org/developers/api`: prioritizes "open-source and mission-aligned projects," "library and education tools," "human-facing discovery and lookup," "real-time, low-volume, high-value use." Explicitly **not** intended as "a bulk data backend or high-traffic commercial infrastructure." No bibliographic-data license claim covers the *lending* transaction itself (loans are a service, not open data). |
| Attribution | Not contractually required for API use (CC0 covers the *data*, not the lending service); this repo's existing convention ("borrowable per openlibrary.org, checked \<date\>" per EXP-09's own pitch) already matches OL's spirit. |
| Auth / token | **Availability check:** none required — same unauthenticated JSON pattern as the bib API, IP + `User-Agent` identified. **Borrow action:** requires the *reader's own* Open Library account login; no documented server-to-server OAuth/delegation for third-party apps was found in `openlibrary.org/developers/api`, `openlibrary.org/dev/docs/api/read`, or `openlibrary.org/help/faq/borrow`. **In-Library tier:** IP-range registration tied to a library's EZproxy, granted only through the partnership process below. |
| Cache · rate-limit · robots | Unidentified: **1 req/s**. Identified (`User-Agent` + contact email, e.g. `QueerTheStacks (contact@example.org)`): **3 req/s**. "Do not... harvest data in bulk," "do not make hundreds of single-book requests" (batch via `search.json` instead); bulk needs monthly data dumps or `openlibrary@archive.org`, not the live API. No published rate limit specific to the Read API's `status` field was found beyond the general API limits; the same etiquette (`assert_allowed`'s already-live posture) applies. |
| Partnership required? | **Availability check: no.** **Borrow action: functionally yes** — no documented path for an app to initiate a loan on a patron's behalf without that patron's own OL session; treating it otherwise would collide with "not intended as a backend for third-party services." **In-Library expanded tier: yes, explicitly** — contact `info@archive.org` for a free ISBN-overlap assessment, then join via `openlibraries.online/join`; this is an *institutional library* partnership program (Internet Archive's "Open Libraries," launched 2017, uses Controlled Digital Lending), not something a personal self-hosted reading tool applies for as itself. |
| Contact | API: `openlibrary@archive.org`. Partnership: `info@archive.org`, `openlibrary.org/partner-with-us`. |
| Terms / API docs | `https://openlibrary.org/developers/api` · `https://openlibrary.org/dev/docs/api/read` · `https://openlibrary.org/dev/docs/inlibrary` · `https://openlibrary.org/partner-with-us` · `https://openlibrary.org/help/faq/borrow` |
| Why it's tempting | Matches this project's "libraries over storefronts" values register exactly — a non-profit, non-gatekept lending service is the ideal partner *in spirit*. |

### What EXP-09's "borrowability badge" idea maps to, concretely

- A **refresh-time availability check** using only the `status` field (no
  login, no borrow action, same IP/User-Agent/rate-limit discipline this
  repo already applies to the bib API) looks consistent with OL's "real-time,
  low-volume, human-facing… on behalf of human users" language — closest to
  something that *could* be added to the allowlist without a new partnership.
- Anything that **starts a loan** or claims the **In-Library** expanded
  catalog is a different, gated thing that needs either (a) the reader
  authenticating to Open Library directly (out of this app's control surface
  today — no FIX-04-style session exists for a third-party OL login) or
  (b) an actual institutional partnership this project isn't positioned to
  hold on a reader's behalf.

### Open legal/policy questions for Chelsea's sign-off (not answered here)

1. Does a **refresh-time, cached, batched availability check** (status only,
   no borrow) cross OL's "not intended as a backend for third-party
   services" line, or does it sit inside "human-facing discovery/lookup"?
   OL's own docs don't address this exact pattern (checking many books'
   status on a schedule for one household, as opposed to per-request live
   lookups for many users) — genuinely ambiguous, not resolved by this
   research.
2. Even if allowed under the letter of the terms, is it worth **emailing
   `openlibrary@archive.org` before shipping** anything that polls `status`
   for an entire TBR, given OL explicitly asks high-volume/programmatic-
   feeling users to identify themselves and given they're a mission-aligned
   non-profit this project wants to stay in good standing with?
3. EXP-09's own risk note says "a batch of borrowability queries could sketch
   a TBR" — worth flagging that this is a privacy consideration for the
   *reader's own request pattern reaching a third party*, distinct from and
   in addition to any of OL's terms; it needs the same pad/shuffle-batching
   treatment already named in the roadmap line, decided alongside the ToS
   question, not instead of it.
4. If a borrow-action feature were ever wanted, is asking the reader to
   authenticate directly to Open Library (their own credentials, handled the
   way a per-user OPDS credential would be — see §5) an acceptable shape, or
   is any credential-holding for a third-party lending service out of scope
   for this project's threat model?

## 4. Compliance card — Generic OPDS (protocol, not a single ToS)

OPDS is **not one source** the way `bookwyrm.social` is one (many
independent instances) or `api.hardcover.app` is one (one company). It's an
Atom-based *protocol* — "OPDS compliance" is actually **N separate
relationships**, one per catalog host a reader points the app at. That's
the single biggest structural difference from every source already in
`recommender/sources.py`.

| Obligation | Posture |
|---|---|
| Kind | `protocol` / `federated`-shaped, but per-**user-supplied** host rather than a fixed set of independent public instances (unlike Bookwyrm, where the *set* of instances is discoverable/bounded; any library could stand up an OPDS catalog). |
| License / terms | No global OPDS ToS exists. **What the protocol itself requires of a client** (from `drafts.opds.io/authentication-for-opds-1.0.html` and `specs.opds.io/opds-1.2.html`): parse Atom feeds (`atom:feed`/`atom:entry`, RFC 4287); recognize acquisition link relations — `.../acquisition` (generic), `.../acquisition/open-access` ("complete representation… without any requirement"), `.../acquisition/borrow`, `.../acquisition/buy`, `.../acquisition/sample`, `.../acquisition/subscribe`. The spec places attribution/rights fields (`atom:rights`, `dc:issued`) as **provider**-side obligations to *publish*, not client obligations to *enforce* — "the specification imposes no mandatory terms-of-use or attribution requirements on consuming clients themselves." |
| Attribution | Protocol-neutral; whatever the *specific catalog* asks for (e.g., Standard Ebooks credits its transcribers; a library OPDS feed may require displaying its name). Must be handled per-host, not once. |
| Auth / token | **Varies per catalog — this is the crux.** If a catalog requires auth, `Authentication for OPDS 1.0` defines an unauthenticated-to-fetch discovery document (`application/opds-authentication+json`) naming one of: HTTP Basic (RFC 2617), OAuth 2.0 Implicit Grant, or OAuth 2.0 Resource Owner Password Credentials Grant (both RFC 6749). **Every step must use TLS.** For password-grant flows, the client **must not** store the reader's password beyond the immediate flow. In practice this means the app would be handling a *per-reader, per-library* credential (their library card / OPDS account), not a service-level API key like Hardcover's. |
| Cache · rate-limit · robots | No protocol-level rule; entirely per-host, same "federated, honor whatever this instance asks" posture already documented for Bookwyrm — except the *set* of hosts is unbounded (reader-supplied) rather than a known list of public instances. |
| Partnership required? | **Depends entirely on the catalog** — see the two case studies below. Ranges from "none, fully open" to "formal library-content partnership plus per-library credentials." |
| Contact | Per-host; there is no single OPDS steward to contact. |
| Terms / API docs | `https://specs.opds.io/opds-1.2.html` · `https://drafts.opds.io/authentication-for-opds-1.0.html` · `https://opds.io/` |
| Why (as a category) it's tempting | It's the *right* protocol for "your library, your card" access — no central gatekeeper, purpose-built for exactly this project's "device-native, no new silo" ethos (same reasoning as EXP-01's own use of OPDS for outbound shelves). |

### Case study A — Standard Ebooks (open, unauthenticated OPDS)

Public-domain ebook producer; its "New Releases" Atom/RSS/OPDS feed is
**open to everyone, no login**. Full access to its per-collection feeds
requires joining the paid "Patrons Circle" support tier — so **even the
"fully open" example has a gated tier**, just a donation-gated one rather
than a library-partnership one. Content itself is public domain / openly
licensed, formatted by Standard Ebooks. No borrow semantics — it's all
`open-access` acquisition (own the file, no return). *(Source:
`standardebooks.org/feeds`.)*

### Case study B — DPLA Exchange / Palace Project (OPDS + ODL, library-partnered)

DPLA Exchange delivers licensed and open ebook content to libraries via
OPDS plus the **ODL (Open Distribution to Libraries)** extension, built on
the Library Simplified / Palace Project circulation-manager stack
(LYRASIS + DPLA + NYPL). To even **shop or curate** content, a library must
become a **DPLA Cultural Services member** (no fee, but a formal join step —
`pro.dp.la/ebooks/join-dpla-exchange`). Once set up, the OPDS+ODL feed is
served **per library**, and access is granted via a **library contract**
issuing per-library credentials (username/password or an OAuth authorization-
code flow) — i.e., **a formal per-catalog partnership plus a per-library
credential handshake**, not something obtainable by a generic client hitting
a public endpoint. Licensed (non-public-domain) content additionally carries
DRM/license-return semantics under ODL (Readium LCP-family), a compliance
surface beyond base OPDS. *(Sources: DPLA press/help pages, Palace Project
OPDS tag page, LYRASIS wiki "Authenticated Feeds.")*

**Together, these two cases bracket the real range:** a user-configured OPDS
endpoint could be Standard-Ebooks-shaped (open, no partnership, safe to treat
like a generic HTTP fetch once a host is trusted) or DPLA/Palace-shaped
(requires the *reader's own* library-issued credential, entered by them, used
on their behalf) — and the app has no way to know which, in general, without
per-host handling.

### What EXP-09's "user-configured library OPDS endpoints" idea maps to, concretely

- This is **structurally different** from the fixed-host allowlist model
  (`assert_allowed` / `ALLOWED_HOSTS`) this repo uses for the three sources
  it already contracts with as a service. A library OPDS endpoint is *the
  reader's own account at their own library* — closer in shape to "bring
  your own KOReader sync server" (already precedented: KOReader sync is a
  user-supplied host, not on `ALLOWED_HOSTS`) than to "a new host this repo
  vets once and everyone gets."
- If/when this ships, it likely needs a **different admission model**
  entirely — reader attests they have an account with that catalog, enters
  their own host + credential, and the app acts as *their* client — rather
  than trying to force per-library OPDS catalogs onto the same
  `assert_allowed` fixed-allowlist mechanism.

### Open legal/policy questions for Chelsea's sign-off (not answered here)

1. Does a **user-supplied arbitrary OPDS host** fit this repo's
   `assert_allowed` fixed-list model at all, or does it need the
   "bring-your-own-server" admission model already used for KOReader sync
   (out of `ALLOWED_HOSTS` scope, trusted because the *reader* configured
   it, not because this codebase vetted the host)? This is a security-model
   question as much as a legal one — worth a short ADR either way.
2. If a per-library credential (Basic Auth password, or an OAuth
   password/implicit grant per `drafts.opds.io`) is entered by the reader,
   what storage/handling bar applies? This is a **new credential-holding
   surface** — Hardcover's token today is an app-level env var the operator
   sets once, never a per-user secret the app stores on someone else's
   behalf. It should probably be held to at least FIX-04's session-auth
   security bar, and reviewed as such before it exists.
3. Should a narrow, **no-credential** OPDS allowlist addition (e.g.,
   Standard-Ebooks-shaped open catalogs, added the normal
   `EthicalSource`/`assert_allowed` way) ship separately from and ahead of a
   generic **BYO-host, credentialed** OPDS client (any library's Palace/DPLA-
   style catalog)? They have different risk shapes and don't need to land
   together.
4. Is representing a book as "borrowable via your library's OPDS catalog"
   accurate/safe to badge the same way as "borrowable per openlibrary.org,"
   given availability there depends on a contract between the *reader's*
   library and its vendor (DPLA/Palace/OverDrive-family) that this project
   has no visibility into and cannot itself verify beyond "the feed said so"?

## 5. What this means for the `EthicalSource` shape, if/when this is ever allowlisted

Every source in `recommender/sources.py` today (Open Library bib API,
Hardcover, Bookwyrm) is a "get a key or nothing, then it's yours" shape —
one app-level credential (or none), one ToS, one contact. Neither Open
Library lending nor generic OPDS fits that. Two fields the dataclass would
plausibly need before either could be represented honestly as a compliance
card, **not implemented here**:

- `partnership_required: str` — none / per-request account / institutional
  agreement — since "compliant" ranges from "call the API" (bib data) to
  "join a partnership program and pass a library contract" (In-Library tier,
  DPLA Exchange).
- `open_questions: tuple[str, ...]` — the unresolved items in §3/§4 above,
  so a future `to_markdown()` render doesn't imply false completeness the
  way a finished card does for Hardcover/Bookwyrm today.

## 6. Recommendation (research finding, not a sign-off)

Nothing here should be read as "go ahead and allowlist X." The honest
summary this research supports:

- **Open Library availability-check-only, cached at refresh time** is the
  closest thing to "probably fine under existing terms" — but "probably" is
  doing real work, and a pre-emptive email to `openlibrary@archive.org`
  before shipping anything that polls a whole TBR seems like the
  responsible move given their own request to be contacted about
  regular/frequent use.
- **Open Library borrow-action and In-Library tier** are not close —
  they need either a documented delegation flow that doesn't currently
  appear to exist, or an institutional partnership this project doesn't fit.
  Defer, per EXP-09's own instruction to "defer honestly if terms are
  unclear."
- **Generic OPDS** has no single answer by construction — it needs a
  per-catalog handling decision, and probably a different admission
  mechanism (BYO-host + reader's own credential) than the fixed allowlist
  this repo uses today, before any code is written.

The **legal/SME gate stays exactly where the roadmap put it.** This document
narrows what needs to be decided; it does not decide it.

## 7. Sources (fetched/searched 2026-07-09)

- [APIs | Open Library](https://openlibrary.org/developers/api) — interface
  conditions, discouraged usage, rate limits, and User-Agent guidance
- [Open Library Read API](https://openlibrary.org/dev/docs/api/read) —
  `status` field values, IP-based In-Library detection
- [Resources for In Library Lending Partners](https://openlibrary.org/dev/docs/inlibrary) —
  EZproxy setup for existing partners
- [Partner With Open Library](https://openlibrary.org/partner-with-us) —
  overlap-assessment / `info@archive.org` partnership process
- [Borrowing Books Through Open Library FAQ](https://openlibrary.org/help/faq/borrow) —
  account requirement, loan periods, waitlist behavior
- [Open Libraries partnership program background](https://help.archive.org/help/borrowing-from-the-lending-library/) —
  Controlled Digital Lending, 2017 program launch
- [Case Studies/Open Library — Creative Commons wiki](https://wiki.creativecommons.org/wiki/Case_Studies/Open_Library) —
  CC0 data dedication, attribution norms
- [OPDS Catalog 1.2 spec](https://specs.opds.io/opds-1.2.html) — Atom
  structure, acquisition link relations, client vs. provider obligations
- [Authentication for OPDS 1.0 (drafts)](https://drafts.opds.io/authentication-for-opds-1.0.html) —
  Authentication Document, TLS requirement, Basic/OAuth flows, credential
  non-persistence
- [OPDS — A standard for digital content distribution](https://opds.io/) —
  protocol overview
- [Ebook Feeds — Standard Ebooks](https://standardebooks.org/feeds) — open
  unauthenticated feed vs. Patrons Circle gated feeds
- [DPLA Exchange offers library-centered ebook marketplace](https://dp.la/news/dpla-exchange-offers-library-centered-ebook-marketplace) —
  OPDS + ODL delivery model
- [Join DPLA Exchange](https://pro.dp.la/ebooks/join-dpla-exchange) — DPLA
  Cultural Services membership requirement
- [Authenticated Feeds — SimplyE / LYRASIS wiki](https://wiki.lyrasis.org/display/SIM/Authenticated+Feeds) —
  per-library credential handshake for Library Simplified/Palace Project OPDS
- [The Palace Project — OPDS](https://thepalaceproject.org/tag/opds/) —
  library contract + OAuth posture

## 8. Explicit non-actions taken by this document

- No changes to `recommender/catalogs.py` (`ALLOWED_HOSTS`, `assert_allowed`)
  or `recommender/sources.py` (`ETHICAL_SOURCES`).
- No borrow, lending, or OPDS client code of any kind.
- No claim of legal sign-off — §3 and §4's "open questions" are exactly
  that: open, for Chelsea to close.
- EXP-09 remains deferred in `docs/ideation/03-expansions.md` and
  `docs/ideation/04-impact-and-sequencing.md`; this document is cited input
  to that eventual decision, not a substitute for it.
