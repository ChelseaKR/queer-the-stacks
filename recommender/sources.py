"""The reusable, cited registry of ethical book-data sources.

This is the GTM-promised "ethical book-data sources" list, in code so it stays
versioned and testable. Each entry documents a catalog the recommender is allowed
to draw from, its access kind, license/terms note, and why it qualifies — and the
deliberate exclusions (Goodreads/Amazon) with the reason.

Every allowed host here must also be on :data:`recommender.catalogs.ALLOWED_HOSTS`
(asserted by the source-ethics test), so this human-readable registry and the
machine-enforced allowlist can never drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EthicalSource:
    """One vetted book-data source, with provenance and rationale."""

    name: str
    host: str
    kind: str  # "open-data" | "api" | "federated"
    license_note: str
    why: str


@dataclass(frozen=True)
class ExcludedSource:
    """A source deliberately not used, with the reason recorded."""

    name: str
    host: str
    reason: str


ETHICAL_SOURCES: tuple[EthicalSource, ...] = (
    EthicalSource(
        name="Open Library",
        host="openlibrary.org",
        kind="open-data",
        license_note="Open data (CC0 for data); attribution appreciated.",
        why="Non-profit (Internet Archive), open bibliographic data + subject headings.",
    ),
    EthicalSource(
        name="Hardcover",
        host="api.hardcover.app",
        kind="api",
        license_note="Public GraphQL API; respect rate limits + ToS.",
        why="Independent, reader-run alternative with community tags; not surveillance-funded.",
    ),
    EthicalSource(
        name="Bookwyrm",
        host="bookwyrm.social",
        kind="federated",
        license_note="ActivityPub; per-instance terms; honor robots + rate limits.",
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


def to_markdown() -> str:
    """Render the registry as a committable Markdown document."""
    lines = [
        "# Ethical Book-Data Sources",
        "",
        "_Generated from `recommender/sources.py` — the single source of truth._",
        "",
        "## Used",
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
        "## Excluded (on purpose)",
        "",
        "| Source | Host | Reason |",
        "|--------|------|--------|",
    ]
    lines += [f"| {s.name} | `{s.host}` | {s.reason} |" for s in EXCLUDED_SOURCES]
    lines.append("")
    return "\n".join(lines)
