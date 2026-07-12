"""Persistence for authored curated lists — local-only, no network.

:mod:`recommender.lists` defines the format (``CuratedList``, ``load_lists``,
``validate_lists``) but has no serializer or file store; this module adds
both, so a reader can *author* cited lists (not just consume the built-in
``DEMO_LISTS``) and persist them to ``data_dir / "lists.json"``.

Posture mirrors :mod:`app.share`: pure, local, no network access anywhere in
this module. Nothing here sends a list anywhere — ``export_lists`` only
returns a string; the CLI decides whether that goes to stdout or a local file
(manual-only, matching the share-card guardrail).

Every write path calls :func:`~recommender.lists.validate_lists` first, so an
invalid list (missing citation, no books) can never reach disk.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from recommender.lists import CuratedList, ListValidationError, load_lists, validate_lists

if TYPE_CHECKING:
    from ingest.config import Config


def list_to_record(lst: CuratedList) -> dict[str, object]:
    """A :class:`CuratedList` as a plain, JSON-safe record."""
    return {
        "name": lst.name,
        "citation": lst.citation,
        "book_ids": list(lst.book_ids),
        "retrieved_at": lst.retrieved_at,
    }


def records_from_lists(lists: tuple[CuratedList, ...]) -> list[dict[str, object]]:
    """The inverse of :func:`~recommender.lists.load_lists`."""
    return [list_to_record(lst) for lst in lists]


def list_store_path(config: Config) -> Path:
    """Where authored lists persist: ``<data_dir>/lists.json``."""
    return config.data_dir / "lists.json"


def load_stored_lists(path: Path) -> tuple[CuratedList, ...]:
    """Load + validate authored lists from ``path``. Missing file → no lists."""
    path = Path(path)
    if not path.is_file():
        return ()
    raw = json.loads(path.read_text(encoding="utf-8"))
    records = raw if isinstance(raw, list) else []
    return load_lists(records)


def save_lists(path: Path, lists: tuple[CuratedList, ...]) -> None:
    """Validate, then persist ``lists`` as sorted-key JSON with a trailing newline.

    Validation runs before any byte is written, so a partially-authored or
    invalid list is never the thing that ends up on disk.
    """
    validate_lists(lists)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(records_from_lists(lists), indent=2, sort_keys=True)
    path.write_text(body + "\n", encoding="utf-8")


def export_lists(lists: tuple[CuratedList, ...]) -> str:
    """The validated JSON string used by ``stacks lists export``."""
    validate_lists(lists)
    return json.dumps(records_from_lists(lists), indent=2, sort_keys=True) + "\n"


def new_list(
    lists: tuple[CuratedList, ...],
    name: str,
    citation: str,
    book_ids: tuple[str, ...] = (),
) -> tuple[CuratedList, ...]:
    """Add a brand-new list named ``name``. Raises on a duplicate name.

    Immutable: returns a new tuple, does not mutate ``lists``.
    """
    name = name.strip()
    if not name:
        raise ListValidationError("a curated list must have a name")
    if any(lst.name == name for lst in lists):
        raise ListValidationError(f"a list named {name!r} already exists")
    candidate = CuratedList(name=name, citation=citation, book_ids=tuple(book_ids))
    validate_lists((candidate,))
    return (*lists, candidate)


def add_book_to_list(
    lists: tuple[CuratedList, ...], name: str, book_id: str
) -> tuple[CuratedList, ...]:
    """Append ``book_id`` to the named list. Raises if the list does not exist.

    Immutable: returns a new tuple with the one list replaced; adding a book
    id already on the list is a no-op (idempotent).
    """
    if not any(lst.name == name for lst in lists):
        raise ListValidationError(f"no list named {name!r} — create it with 'lists new' first")
    out = []
    for lst in lists:
        if lst.name == name and book_id not in lst.book_ids:
            lst = CuratedList(
                name=lst.name,
                citation=lst.citation,
                book_ids=(*lst.book_ids, book_id),
                retrieved_at=lst.retrieved_at,
            )
        out.append(lst)
    result = tuple(out)
    validate_lists(result)
    return result
