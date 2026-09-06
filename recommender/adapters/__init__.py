"""Catalog source adapters, and the contract every one of them must satisfy.

See :mod:`recommender.adapters.contract` for the declaration and protocol,
:mod:`recommender.adapters.conformance` for the checks, and
``docs/adding-a-catalog-source.md`` for how to add one.
"""

from __future__ import annotations

from recommender.adapters.builtin import BookwyrmAdapter, OpenLibraryAdapter
from recommender.adapters.conformance import (
    ConformanceFailure,
    check_adapter,
    query_leaks,
)
from recommender.adapters.contract import AdapterSpec, CatalogAdapter, QueryGrammar
from recommender.adapters.registry import (
    REGISTERED_ADAPTERS,
    CardStatus,
    adapter_card_statuses,
    compliance_card_status,
)

__all__ = [
    "REGISTERED_ADAPTERS",
    "AdapterSpec",
    "BookwyrmAdapter",
    "CardStatus",
    "CatalogAdapter",
    "ConformanceFailure",
    "OpenLibraryAdapter",
    "QueryGrammar",
    "adapter_card_statuses",
    "check_adapter",
    "compliance_card_status",
    "query_leaks",
]
