"""Refresh the persisted public catalog candidate pool.

Catalog egress is deliberately separate from recommendation scoring. Sources
are broad, predeclared configuration (Open Library subjects and explicit public
BookWyrm list URLs), never queries derived from reading history, theme weights,
authors, or other sensitive local signals. Egress is off unless the operator
explicitly selects ``public-metadata`` mode.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ingest.config import Config
from ingest.models import Book
from ingest.store import CatalogSourceUpdate

from recommender.catalogs import BookwyrmClient, OpenLibraryClient, SourceNotAllowed, assert_allowed

_OL_SUBJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")


@dataclass(frozen=True)
class CatalogRefreshResult:
    updates: tuple[CatalogSourceUpdate, ...] = ()
    active_source_ids: frozenset[str] = frozenset()
    attempted: int = 0
    succeeded: int = 0
    errors: int = 0

    @property
    def candidates_fetched(self) -> int:
        return sum(len(update.books) for update in self.updates if update.ok)


def _openlibrary_source_id(subject: str, index: int) -> str:
    if _OL_SUBJECT.fullmatch(subject):
        return f"openlibrary:subject:{subject}"
    return f"openlibrary:subject:invalid-{index + 1}"


def _bookwyrm_source_id(url: str, index: int) -> str:
    try:
        assert_allowed(url)
    except SourceNotAllowed:
        # Do not persist a malformed URL: it could contain credentials or a
        # private fragment. The ordinal remains stable for this configuration
        # and is enough to expose a per-source error.
        return f"bookwyrm:list:invalid-{index + 1}"
    return f"bookwyrm:list:{url}"


def configured_source_ids(config: Config) -> frozenset[str]:
    ids = {
        _openlibrary_source_id(subject, index)
        for index, subject in enumerate(config.openlibrary_subjects)
    }
    ids.update(_bookwyrm_source_id(url, index) for index, url in enumerate(config.bookwyrm_lists))
    return frozenset(ids)


def _error_update(source_id: str, exc: Exception) -> CatalogSourceUpdate:
    # Persist only the exception class. Response bodies, tokens, paths, and
    # configured URLs do not need to be copied into operational error text.
    return CatalogSourceUpdate(source_id=source_id, ok=False, error=type(exc).__name__)


def fetch_catalog_pool(config: Config) -> CatalogRefreshResult:
    """Fetch all explicitly configured public sources once.

    The caller persists results and supplies last-good fallback. This function
    has no access to reading state by construction.
    """
    active = configured_source_ids(config)
    if not config.catalog_egress_enabled or not active:
        return CatalogRefreshResult(active_source_ids=active)

    updates: list[CatalogSourceUpdate] = []
    # The persisted, per-source candidate pool is the refresh cache. Do not put
    # raw URL-keyed responses on disk: their age can diverge from the pool TTL,
    # overstate freshness, and retain removed subject interests indefinitely.
    ol = OpenLibraryClient()
    bw = BookwyrmClient()

    for index, subject in enumerate(config.openlibrary_subjects):
        source_id = _openlibrary_source_id(subject, index)
        if not _OL_SUBJECT.fullmatch(subject):
            updates.append(
                CatalogSourceUpdate(
                    source_id=source_id,
                    ok=False,
                    error="invalid broad subject slug",
                )
            )
            continue
        try:
            books: tuple[Book, ...] = ol.subject(subject)
            updates.append(CatalogSourceUpdate(source_id=source_id, books=books))
        except Exception as exc:  # noqa: BLE001 - surfaced as per-source status
            updates.append(_error_update(source_id, exc))

    for index, url in enumerate(config.bookwyrm_lists):
        source_id = _bookwyrm_source_id(url, index)
        try:
            books = bw.fetch_list(url)
            updates.append(CatalogSourceUpdate(source_id=source_id, books=books))
        except Exception as exc:  # noqa: BLE001 - surfaced as per-source status
            updates.append(_error_update(source_id, exc))

    succeeded = sum(update.ok for update in updates)
    return CatalogRefreshResult(
        updates=tuple(updates),
        active_source_ids=active,
        attempted=len(updates),
        succeeded=succeeded,
        errors=len(updates) - succeeded,
    )


def clear_legacy_response_cache(config: Config) -> None:
    """Remove the obsolete raw-response cache from earlier working builds.

    The parsed candidate pool already provides bounded, per-source caching and
    is pruned when configuration changes. Raw responses add no offline
    availability but can retain removed subject URLs, so refresh migrates them
    away in every outbound mode.
    """
    (config.data_dir / "catalog-response-cache.json").unlink(missing_ok=True)
