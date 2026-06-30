# Ethical Book-Data Sources

_Generated from `recommender/sources.py` — the single source of truth._

## Used (summary)

| Source | Host | Kind | License / terms | Why |
|--------|------|------|-----------------|-----|
| Open Library | `openlibrary.org` | open-data | Bibliographic data is CC0 (public-domain dedication); no key required, public JSON endpoints. | Non-profit (Internet Archive), open bibliographic data + subject headings. |
| Hardcover | `api.hardcover.app` | api | Token-gated GraphQL API; terms are explicitly in flux — treat the schema and policy as unstable and re-check before relying on a field. | Independent, reader-run alternative with community tags; not surveillance-funded. |
| Bookwyrm | `bookwyrm.social` | federated | Per-instance Terms of Service over ActivityPub; content licenses vary by instance and by user — there is no single global term. | Federated, community-run reading lists — no central gatekeeper or ad model. |

## Per-source compliance cards

The three sources impose **materially different** obligations — they are not interchangeable. Each card below states the headline license, the attribution posture, the auth/token handling, and the cache/rate-limit/robots policy we honour.

### Open Library (`openlibrary.org`)

_Non-profit (Internet Archive), open bibliographic data + subject headings._

| Obligation | Posture |
|------------|---------|
| Kind | open-data |
| License / terms | Bibliographic data is CC0 (public-domain dedication); no key required, public JSON endpoints. |
| Attribution | Attribution appreciated but not required — credit 'Open Library / Internet Archive' where practical. |
| Auth / token | No API key. Public, unauthenticated JSON (e.g. /subjects/<s>.json). |
| Cache · rate-limit · robots | Cache on disk; honour robots.txt; back off on 429/5xx; send a descriptive User-Agent; keep volume modest. |
| Contact | Internet Archive / Open Library — https://openlibrary.org/help |
| Terms / API docs | https://openlibrary.org/developers/api |

### Hardcover (`api.hardcover.app`)

_Independent, reader-run alternative with community tags; not surveillance-funded._

| Obligation | Posture |
|------------|---------|
| Kind | api |
| License / terms | Token-gated GraphQL API; terms are explicitly in flux — treat the schema and policy as unstable and re-check before relying on a field. |
| Attribution | Credit Hardcover for community tags; respect contributor data. |
| Auth / token | Requires a personal API token. Keep it in the environment and use it localhost/server-side only — never ship the token to a browser. |
| Cache · rate-limit · robots | Respect published GraphQL rate limits; cache; back off on 429/5xx; identify via User-Agent. |
| Contact | Hardcover — https://docs.hardcover.app (community support via their Discord) |
| Terms / API docs | https://docs.hardcover.app/api/getting-started/ |

### Bookwyrm (`bookwyrm.social`)

_Federated, community-run reading lists — no central gatekeeper or ad model._

| Obligation | Posture |
|------------|---------|
| Kind | federated |
| License / terms | Per-instance Terms of Service over ActivityPub; content licenses vary by instance and by user — there is no single global term. |
| Attribution | Attribute the specific instance and author; honour each instance's license. |
| Auth / token | Public ActivityPub / JSON; no central key. Each instance is an independent host with its own rules and admins. |
| Cache · rate-limit · robots | Honour a per-instance opt-out for reads; cache aggressively; respect robots.txt and rate limits; back off on 429/5xx; descriptive User-Agent. |
| Contact | The individual instance admin (e.g. bookwyrm.social admins) — ask before any bulk/automated read. |
| Terms / API docs | https://github.com/bookwyrm-social/bookwyrm/blob/main/FEDERATION.md |

## Federation & fetch etiquette

Every catalog/federation request follows this policy (enforced by `recommender.catalogs.etiquette_headers` + `ResponseCache`):

- Identify every request with a descriptive User-Agent (app + read-only intent).
- Fetch only public catalog metadata — the reader's reading history is never sent.
- Cache responses on disk (recommender.catalogs.ResponseCache) so we do not re-hit APIs.
- Honour robots.txt and any published rate limits; keep request volume low.
- Back off (exponentially) on HTTP 429 / 5xx instead of hammering a host.
- Treat each Bookwyrm instance as independent; honour a per-instance opt-out for reads.

## Excluded (on purpose)

| Source | Host | Reason |
|--------|------|--------|
| Goodreads | `goodreads.com` | Amazon-owned; ToS forbids scraping; gatekept + surveillance-funded catalog. |
| Amazon | `amazon.com` | Surveillance commerce; not a values-aligned source of book metadata. |
