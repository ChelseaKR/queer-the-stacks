"""Diverse-shelf analytics — sourced-only, honest coverage, no author labels."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.diversity import (
    BUILTIN_LENS_SOURCE,
    DEFAULT_DIMENSIONS,
    DIMENSIONS,
    SENSITIVE_DESCRIPTORS,
    SENSITIVE_DIMENSIONS,
    LensValidationError,
    compute_diversity,
    load_dimensions,
    load_lens_config,
    resolve_sensitive_descriptors,
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


# --- R4: per-descriptor provenance + the privacy (hide-sensitive) toggle -------


def test_descriptor_provenance_carries_source_and_retrieved_at() -> None:
    """Every diverse-shelf tag exposes its Source kind, citation, and fetch date."""
    states = [_state("A", ReadingStatus.FINISHED, (_tag("literary"), _tag("trans")))]
    report = compute_diversity(states)
    by_label = {d.label: d for d in report.descriptor_provenance}
    lit = by_label["literary"]
    assert lit.source_kinds == ("calibre-tag",)
    assert lit.latest_retrieved_at == "2026-06-05"
    assert lit.sources[0].citation == "calibre:local"
    assert lit.sensitive is False
    # "trans" is identity-adjacent and flagged sensitive (but still shown by default).
    assert by_label["trans"].sensitive is True
    assert report.hide_sensitive is False


def test_descriptor_provenance_unions_multiple_sources() -> None:
    states = [
        _state("A", ReadingStatus.FINISHED, (_tag("queer", SourceKind.CALIBRE_TAG),)),
        _state("B", ReadingStatus.FINISHED, (_tag("queer", SourceKind.OPENLIBRARY_SUBJECT),)),
    ]
    report = compute_diversity(states)
    queer = next(d for d in report.descriptor_provenance if d.label == "queer")
    assert queer.books == 2
    assert queer.source_kinds == ("calibre-tag", "openlibrary-subject")


def test_hide_sensitive_aggregates_identity_descriptors() -> None:
    states = [
        _state("A", ReadingStatus.FINISHED, (_tag("trans"), _tag("literary"))),
        _state("B", ReadingStatus.FINISHED, (_tag("queer"),)),
    ]
    report = compute_diversity(states, hide_sensitive=True)
    labels = {d.label for d in report.descriptor_provenance}
    # Granular identity labels are gone; the non-sensitive one stays.
    assert "trans" not in labels and "queer" not in labels
    assert "literary" in labels
    # Exactly one aggregated stand-in row, counting distinct books, keeping provenance.
    agg = [d for d in report.descriptor_provenance if d.aggregated]
    assert len(agg) == 1
    assert agg[0].sensitive and agg[0].books == 2
    assert agg[0].source_kinds == ("calibre-tag",)
    # Coarse lens counts remain, but their concrete labels are masked.
    by_name = {d.name: d for d in report.dimensions}
    assert by_name["Trans & nonbinary"].books == 1
    assert by_name["Trans & nonbinary"].matched_labels == ("(hidden for privacy)",)
    # The flat theme breakdown also redacts the granular sensitive labels.
    tb = dict(report.theme_breakdown)
    assert "trans" not in tb and "queer" not in tb
    assert report.hide_sensitive is True


def test_hide_sensitive_keeps_nonsensitive_detail() -> None:
    states = [_state("A", ReadingStatus.FINISHED, (_tag("speculative"), _tag("literary")))]
    report = compute_diversity(states, hide_sensitive=True)
    labels = {d.label for d in report.descriptor_provenance}
    assert {"speculative", "literary"} <= labels
    # No sensitive descriptors present, so no aggregated row is synthesised.
    assert not any(d.aggregated for d in report.descriptor_provenance)


def test_sensitive_descriptors_are_identity_adjacent() -> None:
    assert {"trans", "queer"} <= SENSITIVE_DESCRIPTORS
    # Descriptors of works (not outing identity labels) are never sensitive.
    assert "speculative" not in SENSITIVE_DESCRIPTORS
    assert "literary" not in SENSITIVE_DESCRIPTORS
    # The sensitive lenses are a subset of the published, auditable dimensions.
    dimension_names = {name for name, _ in DIMENSIONS}
    assert SENSITIVE_DIMENSIONS.issubset(dimension_names)


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
    """The shipped example must load cleanly to the built-in defaults."""
    repo_root = Path(__file__).resolve().parent.parent
    cfg = load_lens_config(repo_root / "examples" / "lenses.example.toml")
    assert cfg.warning is None
    assert cfg.dimensions == DEFAULT_DIMENSIONS


def test_all_unread_falls_back_to_the_whole_shelf_and_says_so() -> None:
    """A Calibre-only shelf has no reading status, so the reading filter empties it.

    Ingesting a real 1,907-book Calibre library produced `coverage_pct: 0.0` and
    `dimensions: ()` — a blank panel that reads as "your shelf isn't diverse"
    rather than "nothing here knows what you've read". The fallback reports the
    shelf instead, flagged, so the honesty this module applies to undescribed
    books also covers the no-reading-history case.
    """
    states = [
        _state("Owned queer", ReadingStatus.UNREAD, (_tag("queer"),)),
        _state("Owned trans", ReadingStatus.UNREAD, (_tag("trans"),)),
        _state("Owned untagged", ReadingStatus.UNREAD, ()),
    ]
    report = compute_diversity(states)
    assert report.shelf_fallback is True
    assert report.total_books == 3
    assert report.described_books == 2
    assert {d.name for d in report.dimensions} == {"Queer / LGBTQ+", "Trans & nonbinary"}


def test_any_reading_history_keeps_the_reading_view() -> None:
    """The fallback is strictly a last resort — one read book restores the filter."""
    states = [
        _state("Finished queer", ReadingStatus.FINISHED, (_tag("queer"),)),
        _state("Owned trans", ReadingStatus.UNREAD, (_tag("trans"),)),
    ]
    report = compute_diversity(states)
    assert report.shelf_fallback is False
    assert report.total_books == 1
    assert {d.name for d in report.dimensions} == {"Queer / LGBTQ+"}


def test_empty_shelf_does_not_claim_a_fallback() -> None:
    assert compute_diversity([]).shelf_fallback is False


# --- The privacy toggle against a reader's OWN lenses ------------------------
#
# The toggle exists for one situation, named in app/diversity.py: screen-sharing
# a queer or trans reading history. It used to redact a frozen list of twelve
# built-in strings while honouring the reader's configured lenses everywhere
# else, so on a personalized lens file it redacted less than it said, and on a
# fully personalized one it redacted nothing while the page still said it had.
#
# Every test below asserts the absence of the unsafe outcome — no
# reader-configured sensitive descriptor surviving anywhere in the report — not
# the presence of a flag.


def _assert_nowhere_in_report(report: object, labels: set[str]) -> None:
    """No label in ``labels`` appears in any granular part of ``report``."""
    breakdown = {lbl for lbl, _ in report.theme_breakdown}  # type: ignore[attr-defined]
    assert not (breakdown & labels), f"theme_breakdown leaked {sorted(breakdown & labels)}"

    provenance = {d.label for d in report.descriptor_provenance}  # type: ignore[attr-defined]
    assert not (provenance & labels), f"descriptor_provenance leaked {sorted(provenance & labels)}"

    for dim in report.dimensions:  # type: ignore[attr-defined]
        matched = set(dim.matched_labels)
        assert not (matched & labels), (
            f"{dim.name} matched_labels leaked {sorted(matched & labels)}"
        )


CUSTOM_VOCABULARY = {"transmasc", "two-spirit", "asexual", "intersex", "dyke", "genderfluid"}


def test_hide_sensitive_redacts_a_readers_own_vocabulary_under_a_shipped_lens_name() -> None:
    """Issue case 1: shipped lens names, the reader's own descriptors inside them.

    This was the worst version: the coarse lens masking *did* fire, so the
    reader saw "(hidden for privacy)" beside both identity lenses and had every
    reason to believe the toggle had worked — with the granular labels sitting in
    the table underneath.
    """
    dimensions = (
        ("Trans & nonbinary", frozenset({"trans", "transmasc", "two-spirit"})),
        ("Queer / LGBTQ+", frozenset({"queer", "asexual", "intersex"})),
        ("Literary", frozenset({"literary"})),
    )
    states = [
        _state("A", ReadingStatus.FINISHED, (_tag("transmasc"), _tag("literary"))),
        _state("B", ReadingStatus.FINISHED, (_tag("two-spirit"),)),
        _state("C", ReadingStatus.FINISHED, (_tag("asexual"),)),
        _state("D", ReadingStatus.FINISHED, (_tag("intersex"), _tag("trans"))),
    ]
    report = compute_diversity(
        states,
        dimensions,
        hide_sensitive=True,
        sensitive_lens_names=frozenset({"Trans & nonbinary", "Queer / LGBTQ+"}),
    )

    _assert_nowhere_in_report(report, CUSTOM_VOCABULARY)
    # The non-sensitive lens keeps its detail: this is redaction, not a blank page.
    assert "literary" in {lbl for lbl, _ in report.theme_breakdown}
    # And the aggregate still says how many books are behind the curtain.
    agg = [d for d in report.descriptor_provenance if d.aggregated]
    assert len(agg) == 1 and agg[0].books == 4


def test_hide_sensitive_fails_closed_on_renamed_lenses() -> None:
    """Issue case 2: renamed lenses, wholly the reader's own vocabulary.

    ``SENSITIVE_DIMENSIONS`` matches lens *names*, so a renamed lens fell outside
    it and nothing was redacted at all. An unmarked custom grouping now fails
    closed — over-redacting is the right direction for what this toggle is for.
    """
    dimensions = (
        ("Gender", frozenset({"genderfluid", "transmasc"})),
        ("Sexuality", frozenset({"dyke"})),
    )
    states = [
        _state("A", ReadingStatus.FINISHED, (_tag("genderfluid"),)),
        _state("B", ReadingStatus.FINISHED, (_tag("transmasc"),)),
        _state("C", ReadingStatus.FINISHED, (_tag("dyke"),)),
    ]
    report = compute_diversity(states, dimensions, hide_sensitive=True)

    _assert_nowhere_in_report(report, CUSTOM_VOCABULARY)
    assert report.redacted_descriptor_count == 3
    # The coarse picture survives: lens names and their counts are still there.
    assert {d.name for d in report.dimensions} == {"Gender", "Sexuality"}


def test_a_custom_lens_file_cannot_unredact_a_builtin_sensitive_descriptor() -> None:
    """Dropping ``queer`` from your own lists must not make ``queer`` visible."""
    dimensions = (("Shelf", frozenset({"literary"})),)
    states = [_state("A", ReadingStatus.FINISHED, (_tag("queer"), _tag("literary")))]

    report = compute_diversity(
        states,
        dimensions,
        hide_sensitive=True,
        sensitive_lens_names=frozenset(),  # the reader marked every lens safe
    )
    _assert_nowhere_in_report(report, {"queer"})
    assert "literary" in {lbl for lbl, _ in report.theme_breakdown}


def test_default_lenses_redact_exactly_what_they_always_did() -> None:
    """The built-in path is unchanged: same twelve descriptors, same behaviour."""
    assert resolve_sensitive_descriptors(DEFAULT_DIMENSIONS) == SENSITIVE_DESCRIPTORS


def test_redacted_count_records_what_was_removed_not_what_was_asked_for() -> None:
    """``hide_sensitive`` is a request; the count is the outcome.

    The rendered assurance keys off the count, so a report that redacted nothing
    must not be able to claim it did.
    """
    nothing_sensitive = [_state("A", ReadingStatus.FINISHED, (_tag("literary"),))]
    report = compute_diversity(nothing_sensitive, hide_sensitive=True)
    assert report.hide_sensitive is True
    assert report.redacted_descriptor_count == 0

    two_sensitive = [_state("A", ReadingStatus.FINISHED, (_tag("trans"), _tag("queer")))]
    report = compute_diversity(two_sensitive, hide_sensitive=True)
    assert report.redacted_descriptor_count == 2

    # Not requested -> nothing removed, whatever is on the shelf.
    assert compute_diversity(two_sensitive).redacted_descriptor_count == 0


def test_unmarked_lenses_in_a_config_file_default_to_sensitive(tmp_path: Path) -> None:
    """A lens you added without saying is treated as sensitive, not as safe."""
    toml = tmp_path / "lenses.toml"
    toml.write_text(
        """
        [[lenses]]
        name = "Gender"
        descriptors = ["genderfluid", "transmasc"]

        [[lenses]]
        name = "Sea stories"
        descriptors = ["nautical"]
        """
    )
    cfg = load_lens_config(toml)
    assert cfg.warning is None
    assert cfg.sensitive_lens_names == frozenset({"Gender", "Sea stories"})


def test_a_lens_marked_not_sensitive_is_shown_in_full(tmp_path: Path) -> None:
    """The escape hatch works: ``sensitive = false`` is the reader's own call."""
    toml = tmp_path / "lenses.toml"
    toml.write_text(
        """
        [[lenses]]
        name = "Gender"
        descriptors = ["genderfluid"]

        [[lenses]]
        name = "Sea stories"
        sensitive = false
        descriptors = ["nautical"]
        """
    )
    cfg = load_lens_config(toml)
    assert cfg.sensitive_lens_names == frozenset({"Gender"})

    states = [
        _state("A", ReadingStatus.FINISHED, (_tag("genderfluid"),)),
        _state("B", ReadingStatus.FINISHED, (_tag("nautical"),)),
    ]
    report = compute_diversity(
        states,
        cfg.dimensions,
        hide_sensitive=True,
        sensitive_lens_names=cfg.sensitive_lens_names,
    )
    labels = {lbl for lbl, _ in report.theme_breakdown}
    assert "genderfluid" not in labels
    assert "nautical" in labels


def test_a_non_boolean_sensitive_flag_degrades_visibly(tmp_path: Path) -> None:
    """A typo must not silently resolve to "not sensitive"."""
    toml = tmp_path / "lenses.toml"
    toml.write_text(
        """
        [[lenses]]
        name = "Gender"
        sensitive = "yes"
        descriptors = ["genderfluid"]
        """
    )
    cfg = load_lens_config(toml)
    assert cfg.dimensions == DEFAULT_DIMENSIONS
    assert cfg.warning is not None and "sensitive" in cfg.warning
    assert cfg.sensitive_lens_names == SENSITIVE_DIMENSIONS


def test_the_committed_template_reproduces_the_builtin_redaction() -> None:
    """Copying the shipped template must not change what the toggle hides.

    Unmarked lenses fail closed, so the template marks its four non-identity
    lenses ``sensitive = false`` on purpose — otherwise a reader who copied it
    unchanged would get a duller chart than the defaults for no reason.
    """
    repo_root = Path(__file__).resolve().parent.parent
    cfg = load_lens_config(repo_root / "examples" / "lenses.example.toml")
    assert cfg.warning is None
    assert cfg.dimensions == DEFAULT_DIMENSIONS
    assert cfg.sensitive_lens_names == SENSITIVE_DIMENSIONS
    assert (
        resolve_sensitive_descriptors(cfg.dimensions, cfg.sensitive_lens_names)
        == SENSITIVE_DESCRIPTORS
    )


def test_no_configured_sensitive_descriptor_survives_into_the_rendered_page(
    tmp_path: Path,
) -> None:
    """End to end, at the surface that matters: the HTML on the shared screen.

    The same report feeds the exported static dashboard, so an export made with
    the toggle on is covered by this too — both go through ``build_view``.
    """
    from app.view import build_view, render_view

    toml = tmp_path / "lenses.toml"
    toml.write_text(
        """
        [[lenses]]
        name = "Gender"
        descriptors = ["genderfluid", "transmasc", "two-spirit"]

        [[lenses]]
        name = "Sea stories"
        sensitive = false
        descriptors = ["nautical"]
        """
    )
    cfg = load_lens_config(toml)
    states = [
        _state("A", ReadingStatus.FINISHED, (_tag("transmasc"),)),
        _state("B", ReadingStatus.FINISHED, (_tag("two-spirit"), _tag("nautical"))),
        _state("C", ReadingStatus.FINISHED, (_tag("genderfluid"),)),
    ]
    view = build_view(
        states,
        [],
        (),
        lens_dimensions=cfg.dimensions,
        lens_source=cfg.source,
        lens_warning=cfg.warning,
        lens_sensitive_names=cfg.sensitive_lens_names,
        hide_sensitive_descriptors=True,
    )
    html = render_view(view).lower()

    for label in ("genderfluid", "transmasc", "two-spirit"):
        assert label not in html, f"the rendered page still shows {label!r}"
    assert "nautical" in html  # the lens the reader marked safe is unaffected
