"""KOReader sync: response parsing, the offline fixture source, and key derivation."""

from __future__ import annotations

import pytest
from ingest.kosync import FixtureKosync, parse_progress, userkey
from ingest.models import DeviceProgress


def test_parse_progress_valid() -> None:
    dp = parse_progress(
        {"document": "md5abc", "percentage": 0.42, "device": "Kobo", "timestamp": 1700000000}
    )
    assert dp is not None
    assert dp.document == "md5abc"
    assert dp.percentage == 0.42
    assert dp.device == "Kobo"


def test_parse_progress_empty_returns_none() -> None:
    assert parse_progress({}) is None
    assert parse_progress({"document": ""}) is None


def test_parse_progress_clamps_and_defaults() -> None:
    dp = parse_progress({"document": "d", "percentage": 5.0, "timestamp": "oops"})
    assert dp is not None
    assert dp.percentage == 1.0  # clamped
    assert dp.timestamp == 0  # bad timestamp -> 0
    assert dp.device == "unknown"


def test_parse_progress_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="must be an object"):
        parse_progress(["not", "an", "object"])


def test_fixture_source_round_trips() -> None:
    dp = DeviceProgress(document="md5x", percentage=0.5, device="Readest", timestamp=1)
    src = FixtureKosync({"md5x": dp})
    assert src.progress_for("md5x") == dp
    assert src.progress_for("missing") is None


def test_userkey_is_deterministic_md5() -> None:
    assert userkey("hunter2") == userkey("hunter2")
    assert len(userkey("hunter2")) == 32
