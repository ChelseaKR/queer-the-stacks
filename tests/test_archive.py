"""Preservation-grade archive export/import — round-trip fidelity + schema honesty."""

from __future__ import annotations

import copy

import pytest
from ingest.archive import (
    ARCHIVE_SCHEMA_VERSION,
    ArchiveVersionError,
    build_archive,
    restore_archive,
)
from ingest.models import DailyActivity


def test_archive_round_trips_states_and_activity(states: list, daily_activity: list) -> None:
    bundle = build_archive(states, daily_activity, generated_at=1_700_000_000)
    restored_states, restored_activity = restore_archive(bundle)
    assert restored_states == states
    assert restored_activity == daily_activity


def test_archive_round_trips_with_empty_activity(states: list) -> None:
    bundle = build_archive(states, [], generated_at=1_700_000_000)
    restored_states, restored_activity = restore_archive(bundle)
    assert restored_states == states
    assert restored_activity == []


def test_archive_manifest_carries_schema_version(states: list, daily_activity: list) -> None:
    bundle = build_archive(states, daily_activity, generated_at=1_700_000_000)
    assert bundle["manifest"]["schema_version"] == ARCHIVE_SCHEMA_VERSION
    assert bundle["manifest"]["generated_at"] == 1_700_000_000
    assert "reimport" in bundle["manifest"]
    assert "stacks import --archive" in bundle["manifest"]["reimport"]
    # Members are documented, including the E11 (highlight-text) caveat.
    assert "E11" in bundle["manifest"]["members"]["annotations"]


def test_archive_annotations_are_valid_web_annotations(states: list, daily_activity: list) -> None:
    bundle = build_archive(states, daily_activity, generated_at=1_700_000_000)
    anno = bundle["annotations"]
    assert anno["@context"] == "http://www.w3.org/ns/anno.jsonld"
    assert anno["type"] == "AnnotationCollection"
    assert anno["total"] == len(anno["items"])

    expected = sum(1 for s in states if s.stat and s.stat.highlights > 0)
    assert anno["total"] == expected
    assert expected > 0, "demo fixture should have at least one highlighted book"

    for item in anno["items"]:
        assert item["type"] == "Annotation"
        assert item["motivation"] == "highlighting"
        assert item["target"]
        body = item["body"]
        assert body["type"] == "TextualBody"
        assert body["purpose"] == "highlighting"
        assert "highlight" in body["value"]


def test_archive_annotation_count_matches_stat_highlights(states: list) -> None:
    bundle = build_archive(states, [], generated_at=0)
    items = bundle["annotations"]["items"]
    counts = {item["target"]: item["body"]["value"] for item in items}
    for s in states:
        if s.stat and s.stat.highlights > 0 and s.book:
            assert s.book.book_id in counts
            assert str(s.stat.highlights) in counts[s.book.book_id]


def test_restore_archive_rejects_mismatched_schema_version(
    states: list, daily_activity: list
) -> None:
    bundle = build_archive(states, daily_activity, generated_at=1_700_000_000)
    tampered = copy.deepcopy(bundle)
    tampered["manifest"]["schema_version"] = ARCHIVE_SCHEMA_VERSION + 1
    with pytest.raises(ArchiveVersionError):
        restore_archive(tampered)


def test_restore_archive_rejects_missing_manifest() -> None:
    with pytest.raises(ArchiveVersionError):
        restore_archive({"states": [], "daily_activity": []})


def test_archive_is_json_serializable(states: list, daily_activity: list) -> None:
    import json

    bundle = build_archive(states, daily_activity, generated_at=1_700_000_000)
    text = json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=False)
    reloaded = json.loads(text)
    restored_states, restored_activity = restore_archive(reloaded)
    assert restored_states == states
    assert restored_activity == daily_activity


def test_archive_activity_dict_round_trip_ignores_ordering() -> None:
    # Sanity: DailyActivity survives archive round trip independent of order.
    activity = [
        DailyActivity(day_ordinal=19000, seconds=100, pages=5),
        DailyActivity(day_ordinal=19001, seconds=200, pages=10),
    ]
    bundle = build_archive([], activity, generated_at=1)
    _, restored = restore_archive(bundle)
    assert restored == activity
