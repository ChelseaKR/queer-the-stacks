"""The reusable, cited registry of ethical book-data sources.

This is the GTM-promised "ethical book-data sources" list, in code so it stays
versioned and testable. Each entry documents a catalog the recommender is allowed
to draw from, its access kind, the **three distinct license/compliance
obligations** (CC0 vs per-instance ToS vs token-gated/"in-flux" API), its
attribution posture, its cache/rate-limit/robots policy, and a contact — plus the
deliberate exclusions (Goodreads/Amazon) with the reason.

Every allowed host here must also be on :data:`recommender.catalogs.ALLOWED_HOSTS`
(asserted by the source-ethics test), so this human-readable registry and the
machine-enforced allowlist can never drift apart. :func:`to_markdown` renders the
committed per-source *compliance card* in ``docs/ethical-book-data-sources.md``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EthicalSource:
    """One vetted book-data source, with provenance, obligations, and rationale.

    The fields capture the three *different* obligations the EV-LICENSE research
    surfaced — they are deliberately not collapsed into a single "terms" blob,
    because Open Library (CC0), Hardcover (token-gated, "in flux"), and Bookwyrm
    (per-instance ToS, federated) impose materially different duties on us.
    """

    name: str
    host: str
    kind: str  # "open-data" | "api" | "federated"
    license_note: str  # the headline license / terms obligation
    attribution: str  # how we credit the source
    auth: str  # key/token posture (e.g. token-gated, localhost/server-only)
    rate_limit: str  # cache + rate-limit + robots + backoff policy we honour
    contact: str  # who to talk to before bulk/automated access
    terms_url: str  # canonical link to the source's API/terms documentation
    why: str  # why this source qualifies as ethical / non-gatekept


@dataclass(frozen=True)
class ExcludedSource:
    """A source deliberately not used, with the reason recorded."""

    name: str
    host: str
    reason: str


#: A descriptive, identifying User-Agent string and the federation/fetch etiquette
#: policy we hold ourselves to. Honesty note on enforcement: the User-Agent,
#: no-reading-data, caching, and allowlist rules are enforced *in code*
#: (:func:`recommender.catalogs.etiquette_headers`, ``ResponseCache``,
#: ``assert_allowed``); robots.txt honouring and 429/5xx backoff are committed
#: policy the live clients must implement when the real candidate pipeline
#: lands (ideation FIX-01, cassette tests PR #27) — until then they are
#: enforced by review, not by code.
FETCH_ETIQUETTE: tuple[str, ...] = (
    "Identify every request with a descriptive User-Agent (app + read-only intent).",
    "Fetch only public catalog metadata — the reader's reading history is never sent.",
    "Cache responses on disk (recommender.catalogs.ResponseCache) so we do not re-hit APIs.",
    "Honour robots.txt and any published rate limits; keep request volume low.",
    "Back off (exponentially) on HTTP 429 / 5xx instead of hammering a host.",
    "Treat each Bookwyrm instance as independent; honour a per-instance opt-out for reads.",
)


ETHICAL_SOURCES: tuple[EthicalSource, ...] = (
    EthicalSource(
        name="Open Library",
        host="openlibrary.org",
        kind="open-data",
        license_note=(
            "Bibliographic data is CC0 (public-domain dedication); no key required, "
            "public JSON endpoints."
        ),
        attribution=(
            "Attribution appreciated but not required — credit "
            "'Open Library / Internet Archive' where practical."
        ),
        auth="No API key. Public, unauthenticated JSON (e.g. /subjects/<s>.json).",
        rate_limit=(
            "Cache on disk; honour robots.txt; back off on 429/5xx; send a descriptive "
            "User-Agent; keep volume modest."
        ),
        contact="Internet Archive / Open Library — https://openlibrary.org/help",
        terms_url="https://openlibrary.org/developers/api",
        why="Non-profit (Internet Archive), open bibliographic data + subject headings.",
    ),
    EthicalSource(
        name="Hardcover",
        host="api.hardcover.app",
        kind="api",
        license_note=(
            "Token-gated GraphQL API; terms are explicitly in flux — treat the schema "
            "and policy as unstable and re-check before relying on a field."
        ),
        attribution="Credit Hardcover for community tags; respect contributor data.",
        auth=(
            "Requires a personal API token. Keep it in the environment and use it "
            "localhost/server-side only — never ship the token to a browser."
        ),
        rate_limit=(
            "Respect published GraphQL rate limits; cache; back off on 429/5xx; identify "
            "via User-Agent."
        ),
        contact="Hardcover — https://docs.hardcover.app (community support via their Discord)",
        terms_url="https://docs.hardcover.app/api/getting-started/",
        why="Independent, reader-run alternative with community tags; not surveillance-funded.",
    ),
    EthicalSource(
        name="Bookwyrm",
        host="bookwyrm.social",
        kind="federated",
        license_note=(
            "Per-instance Terms of Service over ActivityPub; content licenses vary by "
            "instance and by user — there is no single global term."
        ),
        attribution="Attribute the specific instance and author; honour each instance's license.",
        auth=(
            "Public ActivityPub / JSON; no central key. Each instance is an independent "
            "host with its own rules and admins."
        ),
        rate_limit=(
            "Honour a per-instance opt-out for reads; cache aggressively; respect robots.txt "
            "and rate limits; back off on 429/5xx; descriptive User-Agent."
        ),
        contact=(
            "The individual instance admin (e.g. bookwyrm.social admins) — ask before "
            "any bulk/automated read."
        ),
        terms_url="https://github.com/bookwyrm-social/bookwyrm/blob/main/FEDERATION.md",
        why="Federated, community-run reading lists — no central gatekeeper or ad model.",
    ),
)

EXCLUDED_SOURCES: tuple[ExcludedSource, ...] = (
    ExcludedSource(
        name="Goodreads",
        host="goodreads.com",
        reason="Amazon-owned; ToS forbids scraping; gatekept + surveillance-funded catalog.",
    ),
    ExcludedSource(
        name="Amazon",
        host="amazon.com",
        reason="Surveillance commerce; not a values-aligned source of book metadata.",
    ),
)


def allowed_hosts() -> frozenset[str]:
    """Hosts the registry sanctions — must be a subset of the catalog allowlist."""
    return frozenset(s.host for s in ETHICAL_SOURCES)


def _compliance_card(s: EthicalSource) -> list[str]:
    """Render one source as a per-source compliance card (heading + obligations)."""
    return [
        f"### {s.name} (`{s.host}`)",
        "",
        f"_{s.why}_",
        "",
        "| Obligation | Posture |",
        "|------------|---------|",
        f"| Kind | {s.kind} |",
        f"| License / terms | {s.license_note} |",
        f"| Attribution | {s.attribution} |",
        f"| Auth / token | {s.auth} |",
        f"| Cache · rate-limit · robots | {s.rate_limit} |",
        f"| Contact | {s.contact} |",
        f"| Terms / API docs | {s.terms_url} |",
        "",
    ]


def to_markdown() -> str:
    """Render the registry as a committable Markdown document.

    Emits a quick "Used" summary table, then a per-source **compliance card**
    spelling out the three distinct obligations (CC0 / per-instance ToS /
    token-gated, "in-flux" API), the federation/fetch etiquette we enforce, and
    the deliberate exclusions.
    """
    lines = [
        "# Ethical Book-Data Sources",
        "",
        "_Generated from `recommender/sources.py` — the single source of truth._",
        "",
        "## Used (summary)",
        "",
        "| Source | Host | Kind | License / terms | Why |",
        "|--------|------|------|-----------------|-----|",
    ]
    lines += [
        f"| {s.name} | `{s.host}` | {s.kind} | {s.license_note} | {s.why} |"
        for s in ETHICAL_SOURCES
    ]
    lines += [
        "",
        "## Per-source compliance cards",
        "",
        "The three sources impose **materially different** obligations — they are not "
        "interchangeable. Each card below states the headline license, the attribution "
        "posture, the auth/token handling, and the cache/rate-limit/robots policy we honour.",
        "",
    ]
    for s in ETHICAL_SOURCES:
        lines += _compliance_card(s)

    lines += [
        "## Federation & fetch etiquette",
        "",
        "Every catalog/federation request follows this policy. The User-Agent, "
        "public-metadata-only, caching, and host-allowlist rules are enforced in code "
        "(`recommender.catalogs.etiquette_headers`, `ResponseCache`, `assert_allowed`); "
        "robots.txt honouring and 429/5xx backoff are committed policy, enforced by "
        "review until the live candidate pipeline lands (FIX-01 / cassette tests):",
        "",
    ]
    lines += [f"- {rule}" for rule in FETCH_ETIQUETTE]

    lines += [
        "",
        "## Excluded (on purpose)",
        "",
        "| Source | Host | Reason |",
        "|--------|------|--------|",
    ]
    lines += [f"| {s.name} | `{s.host}` | {s.reason} |" for s in EXCLUDED_SOURCES]
    lines.append("")
    return "\n".join(lines)
