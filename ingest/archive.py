"""Preservation-grade export — a versioned, self-describing JSON archive.

``stacks export --archive`` writes the *whole* derived app state — unified
reading state (with every sourced theme tag's provenance), per-day activity,
and highlight annotations — as a single plain-JSON bundle meant to outlive this
codebase: no binary format, no SQLite file, no dependency on this project still
existing to read it back. ``stacks import --archive`` reverses it losslessly.

Design choices, in order of how much they matter for "readable in thirty years":

1. **Plain JSON, stdlib only.** No pickle, no proprietary binary layout.
2. **Self-describing.** The bundle carries its own manifest — schema version,
   what produced it, when, and what each member means — so a future reader
   (human or machine) does not need this repo's source to understand the file.
3. **Standards where they exist.** Highlights are emitted as W3C Web Annotations
   (https://www.w3.org/TR/annotation-model/), the closest fit even though today
   only a *count* per book is available (see the module docstring note below).
4. **Round-trips exactly.** The archive reuses :mod:`ingest.serde` verbatim for
   states and activity, so lossless re-import falls out of the same fidelity
   the app-state store already guarantees (tests/test_store_serde.py).

Schema versioning (FIX-06): ``ARCHIVE_SCHEMA_VERSION`` is bumped whenever the
bundle's shape changes in a way that would break an older reader;
:func:`restore_archive` refuses to load a bundle whose ``manifest.schema_version``
it does not recognize rather than silently guessing.
"""

from __future__ import annotations

from typing import Any

from ingest.models import DailyActivity, ReadingState
from ingest.serde import (
    activity_from_dict,
    activity_to_dict,
    state_from_dict,
    state_to_dict,
)

#: Bumped whenever the archive's on-disk shape changes incompatibly.
ARCHIVE_SCHEMA_VERSION = 1

#: The Web Annotation JSON-LD context (W3C). Every entry in ``annotations`` is
#: a valid Annotation under this context.
_ANNO_CONTEXT = "http://www.w3.org/ns/anno.jsonld"

#: A stable, hand-written description of the bundle shape — copied into every
#: archive's ``manifest`` (with ``generated_at`` filled in per-export) so the
#: file explains itself without this source tree.
MANIFEST: dict[str, Any] = {
    "schema_version": ARCHIVE_SCHEMA_VERSION,
    "generator": "queer-the-stacks stacks export --archive",
    "description": (
        "A preservation-grade, self-describing export of one reader's local "
        "reading state: unified books + reading stats + device progress "
        "('states'), per-day activity aggregates ('daily_activity'), and "
        "highlight annotations ('annotations'). Plain JSON, stdlib-only, no "
        "external format dependency. Re-import losslessly with "
        "`stacks import --archive <file>`."
    ),
    "members": {
        "states": (
            "List of unified ReadingState records (ingest.serde.state_to_dict "
            "shape): title/authors/status, the sourced Book (with theme_tags "
            "and their provenance — kind, citation, retrieved_at), the local "
            "ReadingStat, and per-device progress."
        ),
        "daily_activity": (
            "List of {day_ordinal, seconds, pages} — reading time and pages "
            "aggregated to a UTC calendar day (day_ordinal = unix day since "
            "epoch), for streaks and time-based views."
        ),
        "annotations": (
            "A W3C Web Annotation (https://www.w3.org/TR/annotation-model/) "
            "JSON-LD list, one Annotation per book with highlights > 0. NOTE: "
            "highlight *text* does not exist in this codebase yet (tracked as "
            "E11) — only a per-book highlight *count* "
            "(ReadingStat.highlights) is available, so each Annotation's body "
            "is count-only ({'type': 'TextualBody', 'purpose': 'highlighting', "
            "'value': '<n> highlight(s)'}) rather than the highlighted text "
            "itself. Once E11 ships, richer per-highlight Annotations (with "
            "TextQuoteSelector bodies) can be added without breaking this "
            "schema version — count-only annotations simply become redundant."
        ),
    },
    "reimport": "stacks import --archive <file>",
}


def _annotation_for_stat(state: ReadingState) -> dict[str, Any] | None:
    """A count-only Web Annotation for one book's highlights, or ``None``.

    Highlight *content* (E11) does not exist yet — only
    :attr:`~ingest.models.ReadingStat.highlights`, a count. Emitted only when
    that count is positive, so books with zero highlights carry no annotation.
    """
    stat = state.stat
    if stat is None or stat.highlights <= 0:
        return None
    target = state.book.book_id if state.book else stat.key
    n = stat.highlights
    return {
        "type": "Annotation",
        "motivation": "highlighting",
        "target": target,
        "body": {
            "type": "TextualBody",
            "purpose": "highlighting",
            "format": "text/plain",
            "value": f"{n} highlight{'s' if n != 1 else ''} (count-only pending E11)",
        },
    }


def build_archive(
    states: list[ReadingState],
    activity: list[DailyActivity],
    *,
    generated_at: int,
) -> dict[str, Any]:
    """Assemble the full self-describing archive bundle for ``states``/``activity``.

    ``generated_at`` (unix seconds) is passed in rather than read from the wall
    clock so the function — and its tests — stay deterministic.
    """
    manifest = dict(MANIFEST)
    manifest["generated_at"] = int(generated_at)

    annotations = [anno for anno in (_annotation_for_stat(s) for s in states) if anno is not None]

    return {
        "manifest": manifest,
        "states": [state_to_dict(s) for s in states],
        "daily_activity": [activity_to_dict(a) for a in activity],
        "annotations": {
            "@context": _ANNO_CONTEXT,
            "type": "AnnotationCollection",
            "total": len(annotations),
            "items": annotations,
        },
    }


class ArchiveVersionError(Exception):
    """Raised when a bundle's ``manifest.schema_version`` is not supported."""


def restore_archive(bundle: dict[str, Any]) -> tuple[list[ReadingState], list[DailyActivity]]:
    """Rebuild ``(states, daily_activity)`` from a bundle built by :func:`build_archive`.

    Validates the manifest's schema version before touching the payload — an
    archive from an incompatible future (or malformed) schema is rejected
    rather than partially, silently misread.
    """
    manifest = bundle.get("manifest")
    if not isinstance(manifest, dict) or "schema_version" not in manifest:
        raise ArchiveVersionError("archive is missing a manifest.schema_version")
    version = manifest["schema_version"]
    if version != ARCHIVE_SCHEMA_VERSION:
        raise ArchiveVersionError(
            f"unsupported archive schema_version {version!r}; "
            f"this build reads version {ARCHIVE_SCHEMA_VERSION}"
        )

    states = [state_from_dict(d) for d in bundle.get("states", [])]
    activity = [activity_from_dict(d) for d in bundle.get("daily_activity", [])]
    return states, activity
