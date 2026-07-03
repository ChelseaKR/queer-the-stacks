"""Diverse-shelf analytics — sourced-only, honest coverage, no author labels."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.diversity import (
    BUILTIN_LENS_SOURCE,
    DEFAULT_DIMENSIONS,
    DIMENSIONS,
    LensValidationError,
    compute_diversity,
    load_dimensions,
    load_lens_config,
    validate_dimensions,
)
from ingest.models import (
    Author,
    Book,
    ReadingStat,
    ReadingState,
    ReadingStatus,
    Source,
    SourceKind,
    ThemeTag,
)


def _tag(label: str, kind: SourceKind = SourceKind.CALIBRE_TAG) -> ThemeTag:
    return ThemeTag(label, Source(kind, "calibre:local", "2026-06-05", label))


def _state(
    title: str,
    status: ReadingStatus,
    tags: tuple[ThemeTag, ...],
) -> ReadingState:
    book = Book(book_id=title, title=title, authors=(Author("A"),), theme_tags=tags)
    stat = ReadingStat(title, title, ("A",), 100, 100, 3600, 1_700_000_000, 3)
    return ReadingState(title=title, authors=("A",), status=status, book=book, stat=stat)


def test_excludes_unread_and_counts_described() -> None:
    states = [
        _state("Read trans", ReadingStatus.FINISHED, (_tag("trans"), _tag("literary"))),
        _state("Reading queer", ReadingStatus.READING, (_tag("queer"),)),
        _state("No tags", ReadingStatus.FINISHED, ()),
        _state("Unread queer", ReadingStatus.UNREAD, (_tag("queer"),)),  # excluded
    ]
    report = compute_diversity(states)
    assert report.total_books == 3  # the unread one is not considered
    assert report.described_books == 2  # "No tags" carries no sourced descriptor
    assert report.undescribed_books == 1
    assert round(report.coverage_pct, 3) == round(2 / 3, 3)


def test_dimensions_group_sourced_descriptors_only() -> None:
    states = [
        _state("A", ReadingStatus.FINISHED, (_tag("trans"),)),
        _state("B", ReadingStatus.FINISHED, (_tag("queer"),)),
        _state("C", ReadingStatus.FINISHED, (_tag("speculative"),)),
    ]
    report = compute_diversity(states)
    by_name = {d.name: d for d in report.dimensions}
    assert by_name["Trans & nonbinary"].books == 1
    assert by_name["Queer / LGBTQ+"].books == 1
    assert by_name["Speculative / SFF"].books == 1
    # % is a share of *described* books, never the whole shelf.
    assert round(by_name["Trans & nonbinary"].pct, 3) == round(1 / 3, 3)
    # The concrete sourced labels are surfaced for transparency.
    assert by_name["Trans & nonbinary"].matched_labels == ("trans",)


def test_empty_lenses_are_omitted() -> None:
    report = compute_diversity([_state("A", ReadingStatus.FINISHED, (_tag("trans"),))])
    names = {d.name for d in report.dimensions}
    assert names == {"Trans & nonbinary"}  # only populated lenses surface


def test_provenance_counts_by_source_kind() -> None:
    states = [
        _state("A", ReadingStatus.FINISHED, (_tag("trans", SourceKind.CALIBRE_TAG),)),
        _state(
            "B",
            ReadingStatus.FINISHED,
            (_tag("queer", SourceKind.OPENLIBRARY_SUBJECT),),
        ),
    ]
    report = compute_diversity(states)
    prov = dict(report.source_provenance)
    assert prov["calibre-tag"] == 1
    assert prov["openlibrary-subject"] == 1


def test_empty_shelf_is_safe() -> None:
    report = compute_diversity([])
    assert report.total_books == 0
    assert report.coverage_pct == 0.0
    assert report.dimensions == ()


def test_dimensions_constant_has_no_author_identity_intent() -> None:
    """The lens grouping describes books; its names must not label a person."""
    for name, labels in DIMENSIONS:
        assert name and labels
        # Lenses are descriptors of works, never claims about an author.
        assert "author" not in name.lower()


def test_demo_diversity_reflects_the_canon(states: list) -> None:
    report = compute_diversity(states)
    assert report.described_books >= 7
    by_name = {d.name: d for d in report.dimensions}
    assert by_name["Trans & nonbinary"].books >= 3
    assert by_name["Speculative / SFF"].books >= 3


def test_dimensions_alias_matches_default() -> None:
    assert DIMENSIONS is DEFAULT_DIMENSIONS


def test_default_lens_source_is_builtin() -> None:
    report = compute_diversity([_state("A", ReadingStatus.FINISHED, (_tag("trans"),))])
    assert report.lens_source == BUILTIN_LENS_SOURCE
    assert report.lens_warning is None


def test_custom_dimensions_reflect_renamed_lens_labels() -> None:
    """A caller-supplied lens grouping is used verbatim — a renamed label shows up."""
    custom = (("Trans Futures", frozenset({"trans"})),)
    states = [_state("A", ReadingStatus.FINISHED, (_tag("trans"),))]
    report = compute_diversity(states, custom, lens_source="data/lenses.toml")
    names = {d.name for d in report.dimensions}
    assert names == {"Trans Futures"}
    assert report.lens_source == "data/lenses.toml"


def test_validate_dimensions_rejects_duplicate_labels() -> None:
    dims = (
        ("Queer", frozenset({"queer"})),
        ("queer", frozenset({"lgbtq"})),  # case-insensitive duplicate
    )
    with pytest.raises(LensValidationError, match="duplicate"):
        validate_dimensions(dims)


def test_validate_dimensions_rejects_empty_descriptors() -> None:
    dims = (("Empty Lens", frozenset()),)
    with pytest.raises(LensValidationError, match="no descriptors"):
        validate_dimensions(dims)


def test_validate_dimensions_rejects_empty_name() -> None:
    dims = ((" ", frozenset({"trans"})),)
    with pytest.raises(LensValidationError, match="name"):
        validate_dimensions(dims)


def test_load_dimensions_from_records() -> None:
    records: list[dict[str, object]] = [
        {"name": "Trans & nonbinary", "descriptors": ["Trans", "NONBINARY"]},
        {"name": "Queer / LGBTQ+", "descriptors": ["queer", "lesbian"]},
    ]
    dims = load_dimensions(records)
    by_name = dict(dims)
    # Descriptors are normalized to lowercase to match ThemeTag.normalized.
    assert by_name["Trans & nonbinary"] == frozenset({"trans", "nonbinary"})


def test_load_dimensions_rejects_duplicate_labels() -> None:
    records: list[dict[str, object]] = [
        {"name": "Queer", "descriptors": ["queer"]},
        {"name": "queer", "descriptors": ["lgbtq"]},
    ]
    with pytest.raises(LensValidationError, match="duplicate"):
        load_dimensions(records)


def test_load_dimensions_rejects_empty_descriptors() -> None:
    with pytest.raises(LensValidationError, match="no descriptors"):
        load_dimensions([{"name": "Empty", "descriptors": []}])


def test_load_lens_config_none_uses_defaults_with_no_warning() -> None:
    cfg = load_lens_config(None)
    assert cfg.dimensions == DEFAULT_DIMENSIONS
    assert cfg.source == BUILTIN_LENS_SOURCE
    assert cfg.warning is None


def test_load_lens_config_valid_file(tmp_path: Path) -> None:
    toml = tmp_path / "lenses.toml"
    toml.write_text(
        """
        [[lenses]]
        name = "Trans Futures"
        descriptors = ["trans", "nonbinary"]
        """
    )
    cfg = load_lens_config(toml)
    assert cfg.warning is None
    assert cfg.source == str(toml)
    assert dict(cfg.dimensions)["Trans Futures"] == frozenset({"trans", "nonbinary"})


def test_load_lens_config_missing_file_degrades(tmp_path: Path) -> None:
    cfg = load_lens_config(tmp_path / "absent.toml")
    assert cfg.dimensions == DEFAULT_DIMENSIONS
    assert cfg.source == BUILTIN_LENS_SOURCE
    assert cfg.warning is not None  # visible, never a silent fallback


def test_load_lens_config_malformed_toml_degrades(tmp_path: Path) -> None:
    toml = tmp_path / "lenses.toml"
    toml.write_text("this is not [valid toml")
    cfg = load_lens_config(toml)
    assert cfg.dimensions == DEFAULT_DIMENSIONS
    assert cfg.warning is not None


def test_load_lens_config_duplicate_labels_degrade_with_warning(tmp_path: Path) -> None:
    toml = tmp_path / "lenses.toml"
    toml.write_text(
        """
        [[lenses]]
        name = "Queer"
        descriptors = ["queer"]
        [[lenses]]
        name = "queer"
        descriptors = ["lgbtq"]
        """
    )
    cfg = load_lens_config(toml)
    # Invalid config never blocks the view: it degrades to defaults, named.
    assert cfg.dimensions == DEFAULT_DIMENSIONS
    assert cfg.source == BUILTIN_LENS_SOURCE
    assert cfg.warning is not None
    assert "duplicate" in cfg.warning.lower()


def test_load_lens_config_empty_lenses_array_degrades(tmp_path: Path) -> None:
    toml = tmp_path / "lenses.toml"
    toml.write_text("lenses = []\n")
    cfg = load_lens_config(toml)
    assert cfg.dimensions == DEFAULT_DIMENSIONS
    assert cfg.warning is not None


def test_the_committed_lenses_toml_template_is_valid() -> None:
    """The shipped data/lenses.toml must load cleanly to defaults' equivalent."""
    repo_root = Path(__file__).resolve().parent.parent
    cfg = load_lens_config(repo_root / "data" / "lenses.toml")
    assert cfg.warning is None
    assert cfg.dimensions == DEFAULT_DIMENSIONS
