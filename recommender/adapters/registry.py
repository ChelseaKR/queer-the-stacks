"""The adapters this build ships, and their compliance-card status.

Registration is a tuple in this module rather than an entry-point scan. Plugin
loading from outside the package is deliberately out of scope until the contract
has two external users: an entry point is an arbitrary import, and an arbitrary
import inside a process that holds the reader's library is exactly the thing the
no-egress guarantee cannot survive.
"""

from __future__ import annotations

from dataclasses import dataclass

from recommender.adapters.builtin import BookwyrmAdapter, OpenLibraryAdapter
from recommender.adapters.contract import AdapterSpec, CatalogAdapter
from recommender.sources import ETHICAL_SOURCES

#: Every adapter wired into this build.
REGISTERED_ADAPTERS: tuple[CatalogAdapter, ...] = (OpenLibraryAdapter(), BookwyrmAdapter())


@dataclass(frozen=True)
class CardStatus:
    """Whether an adapter's obligations are written down, and where."""

    adapter: str
    host: str
    ok: bool
    detail: str


def compliance_card_status(spec: AdapterSpec) -> CardStatus:
    """Resolve ``spec`` against the committed ethical-sources registry."""
    card = next((s for s in ETHICAL_SOURCES if s.host == spec.compliance_card_host), None)
    if card is None:
        return CardStatus(
            adapter=spec.name,
            host=spec.compliance_card_host,
            ok=False,
            detail=(
                f"no compliance card for {spec.compliance_card_host} in recommender.sources "
                "(licence, attribution, auth and rate-limit obligations unrecorded)"
            ),
        )
    return CardStatus(
        adapter=spec.name,
        host=spec.compliance_card_host,
        ok=True,
        detail=f"{card.kind}; {card.license_note}",
    )


def adapter_card_statuses(
    adapters: tuple[CatalogAdapter, ...] | None = None,
) -> tuple[CardStatus, ...]:
    """The card status of every registered adapter, for ``stacks doctor``."""
    chosen = REGISTERED_ADAPTERS if adapters is None else adapters
    return tuple(compliance_card_status(adapter.spec) for adapter in chosen)
