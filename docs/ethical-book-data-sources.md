# Ethical Book-Data Sources

_Generated from `recommender/sources.py` — the single source of truth._

## Used

| Source | Host | Kind | License / terms | Why |
|--------|------|------|-----------------|-----|
| Open Library | `openlibrary.org` | open-data | Open data (CC0 for data); attribution appreciated. | Non-profit (Internet Archive), open bibliographic data + subject headings. |
| Hardcover | `api.hardcover.app` | api | Public GraphQL API; respect rate limits + ToS. | Independent, reader-run alternative with community tags; not surveillance-funded. |
| Bookwyrm | `bookwyrm.social` | federated | ActivityPub; per-instance terms; honor robots + rate limits. | Federated, community-run reading lists — no central gatekeeper or ad model. |

## Excluded (on purpose)

| Source | Host | Reason |
|--------|------|--------|
| Goodreads | `goodreads.com` | Amazon-owned; ToS forbids scraping; gatekept + surveillance-funded catalog. |
| Amazon | `amazon.com` | Surveillance commerce; not a values-aligned source of book metadata. |
