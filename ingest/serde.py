"""JSON (de)serialization for persisted derived state.

The unified :class:`~ingest.models.ReadingState` (with its nested book, sourced
theme tags, stats, and device progress) and :class:`~ingest.models.DailyActivity`
round-trip through plain JSON-able dicts so they can live in the SQLite app-state
store. Round-trip fidelity is asserted in the tests — what goes in comes back
identical, preserving every source citation.
"""

from __future__ import annotations

from typing import Any, Optional

from ingest.models import (
    Author,
    Book,
    DailyActivity,
    DeviceProgress,
    ReadingStat,
    ReadingState,
    ReadingStatus,
    Source,
    SourceKind,
    ThemeTag,
)


def _source_to_dict(s: Source) -> dict[str, Any]:
    return {
        "kind": s.kind.value,
        "citation": s.citation,
        "retrieved_at": s.retrieved_at,
        "detail": s.detail,
    }


def _source_from_dict(d: dict[str, Any]) -> Source:
    return Source(
        kind=SourceKind(d["kind"]),
        citation=d["citation"],
        retrieved_at=d["retrieved_at"],
        detail=d.get("detail", ""),
    )


def _book_to_dict(b: Book) -> dict[str, Any]:
    return {
        "book_id": b.book_id,
        "title": b.title,
        "authors": [{"name": a.name, "sort": a.sort} for a in b.authors],
        "series": b.series,
        "series_index": b.series_index,
        "identifiers": dict(b.identifiers),
        "theme_tags": [
            {"label": t.label, "source": _source_to_dict(t.source)} for t in b.theme_tags
        ],
        "pubdate": b.pubdate,
    }


def _book_from_dict(d: dict[str, Any]) -> Book:
    return Book(
        book_id=d["book_id"],
        title=d["title"],
        authors=tuple(Author(name=a["name"], sort=a.get("sort", "")) for a in d["authors"]),
        series=d.get("series"),
        series_index=d.get("series_index"),
        identifiers=dict(d.get("identifiers", {})),
        theme_tags=tuple(
            ThemeTag(label=t["label"], source=_source_from_dict(t["source"]))
            for t in d.get("theme_tags", [])
        ),
        pubdate=d.get("pubdate"),
    )


def _stat_to_dict(s: ReadingStat) -> dict[str, Any]:
    return {
        "key": s.key,
        "title": s.title,
        "authors": list(s.authors),
        "pages_read": s.pages_read,
        "total_pages": s.total_pages,
        "read_time_seconds": s.read_time_seconds,
        "last_read_ts": s.last_read_ts,
        "sessions": s.sessions,
        "highlights": s.highlights,
    }


def _stat_from_dict(d: dict[str, Any]) -> ReadingStat:
    return ReadingStat(
        key=d["key"],
        title=d["title"],
        authors=tuple(d["authors"]),
        pages_read=d["pages_read"],
        total_pages=d["total_pages"],
        read_time_seconds=d["read_time_seconds"],
        last_read_ts=d["last_read_ts"],
        sessions=d["sessions"],
        highlights=d.get("highlights", 0),
    )


def _progress_to_dict(p: DeviceProgress) -> dict[str, Any]:
    return {
        "document": p.document,
        "percentage": p.percentage,
        "device": p.device,
        "timestamp": p.timestamp,
    }


def _progress_from_dict(d: dict[str, Any]) -> DeviceProgress:
    return DeviceProgress(
        document=d["document"],
        percentage=d["percentage"],
        device=d["device"],
        timestamp=d["timestamp"],
    )


def state_to_dict(s: ReadingState) -> dict[str, Any]:
    book: Optional[dict[str, Any]] = _book_to_dict(s.book) if s.book else None
    stat: Optional[dict[str, Any]] = _stat_to_dict(s.stat) if s.stat else None
    return {
        "title": s.title,
        "authors": list(s.authors),
        "status": s.status.value,
        "book": book,
        "stat": stat,
        "progress": [_progress_to_dict(p) for p in s.progress],
    }


def state_from_dict(d: dict[str, Any]) -> ReadingState:
    return ReadingState(
        title=d["title"],
        authors=tuple(d["authors"]),
        status=ReadingStatus(d["status"]),
        book=_book_from_dict(d["book"]) if d.get("book") else None,
        stat=_stat_from_dict(d["stat"]) if d.get("stat") else None,
        progress=tuple(_progress_from_dict(p) for p in d.get("progress", [])),
    )


def activity_to_dict(a: DailyActivity) -> dict[str, Any]:
    return {"day_ordinal": a.day_ordinal, "seconds": a.seconds, "pages": a.pages}


def activity_from_dict(d: dict[str, Any]) -> DailyActivity:
    return DailyActivity(day_ordinal=d["day_ordinal"], seconds=d["seconds"], pages=d["pages"])
