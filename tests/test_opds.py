"""OPDS catalog — auth-gated, read-only, well-formed, sourced content only."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from app.opds import (
    ATOM_NS,
    build_root_navigation,
    build_shelf_acquisition,
    currently_reading_entries,
    entries_for_shelf,
    recommendation_entries,
    series_next_entries,
    to_read_entries,
)
from app.view import demo_view

ATOM = f"{{{ATOM_NS}}}"


def _feed_entries(xml_text: str) -> list[ET.Element]:
    root = ET.fromstring(xml_text)  # raises if not well-formed
    assert root.tag == f"{ATOM}feed"
    return root.findall(f"{ATOM}entry")


# --- root navigation feed ----------------------------------------------------


def test_root_navigation_is_well_formed_xml(workdir: Path) -> None:
    view = demo_view(workdir)
    xml_text = build_root_navigation(view)
    ET.fromstring(xml_text)  # raises ElementTree.ParseError if malformed


def test_root_navigation_lists_all_shelf_feeds(workdir: Path) -> None:
    view = demo_view(workdir)
    xml_text = build_root_navigation(view)
    assert "profile=opds-catalog;kind=navigation" in xml_text
    for path in (
        "/opds/to-read",
        "/opds/currently-reading",
        "/opds/series-next",
        "/opds/recommendations",
    ):
        assert path in xml_text
    root = ET.fromstring(xml_text)
    self_links = [
        link
        for link in root.findall(f"{ATOM}link")
        if link.get("rel") == "self" and link.get("href") == "/opds"
    ]
    start_links = [
        link
        for link in root.findall(f"{ATOM}link")
        if link.get("rel") == "start" and link.get("href") == "/opds"
    ]
    assert self_links, "root feed must carry a rel=self link"
    assert start_links, "root feed must carry a rel=start link"
    entries = root.findall(f"{ATOM}entry")
    assert len(entries) == 4


# --- acquisition feeds: one entry per shelf item -----------------------------


def test_to_read_acquisition_has_one_entry_per_book(workdir: Path) -> None:
    view = demo_view(workdir)
    entries = to_read_entries("to-read", view.to_read)
    xml_text = build_shelf_acquisition("to-read", "To read", entries)
    assert "profile=opds-catalog;kind=acquisition" in xml_text
    parsed = _feed_entries(xml_text)
    assert len(parsed) == len(view.to_read) > 0
    for state, entry in zip(view.to_read, parsed, strict=True):
        assert entry.find(f"{ATOM}title").text == state.title
        assert entry.find(f"{ATOM}id").text.startswith("urn:qts:to-read:")
        author_names = {a.find(f"{ATOM}name").text for a in entry.findall(f"{ATOM}author")}
        assert author_names == set(state.authors) or (
            not state.authors and "Unknown" in author_names
        )


def test_currently_reading_acquisition_has_one_entry_per_book(workdir: Path) -> None:
    view = demo_view(workdir)
    entries = currently_reading_entries("currently-reading", view.currently_reading)
    xml_text = build_shelf_acquisition("currently-reading", "Currently reading", entries)
    parsed = _feed_entries(xml_text)
    assert len(parsed) == len(view.currently_reading) > 0
    titles = {e.find(f"{ATOM}title").text for e in parsed}
    assert titles == {s.title for s in view.currently_reading}


def test_series_next_acquisition_has_one_entry_per_book(workdir: Path) -> None:
    view = demo_view(workdir)
    entries = series_next_entries("series-next", view.series_next)
    xml_text = build_shelf_acquisition("series-next", "Series next", entries)
    parsed = _feed_entries(xml_text)
    assert len(parsed) == len(view.series_next)


def test_entries_for_shelf_matches_direct_mappers(workdir: Path) -> None:
    view = demo_view(workdir)
    assert entries_for_shelf("to-read", view) == to_read_entries("to-read", view.to_read)
    assert entries_for_shelf("recommendations", view) == recommendation_entries(
        "recommendations", view.recommendations
    )
    with pytest.raises(ValueError):
        entries_for_shelf("no-such-shelf", view)


# --- recommendation feed: sourced explanation only ---------------------------


def test_recommendation_entry_ids_titles_authors(workdir: Path) -> None:
    view = demo_view(workdir)
    entries = recommendation_entries("recommendations", view.recommendations)
    xml_text = build_shelf_acquisition("recommendations", "Recommendations", entries)
    parsed = _feed_entries(xml_text)
    assert len(parsed) == len(view.recommendations) > 0
    for rec, entry in zip(view.recommendations, parsed, strict=True):
        assert entry.find(f"{ATOM}title").text == rec.book.title
        assert entry.find(f"{ATOM}id").text.startswith("urn:qts:recommendations:")
        author_names = tuple(a.find(f"{ATOM}name").text for a in entry.findall(f"{ATOM}author"))
        assert author_names == rec.book.author_names


def test_recommendation_content_carries_sourced_explanation(workdir: Path) -> None:
    view = demo_view(workdir)
    entries = recommendation_entries("recommendations", view.recommendations)
    xml_text = build_shelf_acquisition("recommendations", "Recommendations", entries)
    parsed = _feed_entries(xml_text)
    for rec, entry in zip(view.recommendations, parsed, strict=True):
        content = entry.find(f"{ATOM}content").text
        # The explanation summary is present verbatim.
        assert rec.explanation.summary in content
        # Every signal's sourced detail is present...
        for signal in rec.explanation.signals:
            assert signal.detail in content
        # ...and nothing else is fabricated: content is built only from the
        # summary + the signal kind/detail pairs, never additional text.
        expected_why = "; ".join(f"{s.kind}: {s.detail}" for s in rec.explanation.signals)
        expected = (
            f"{rec.explanation.summary} Why: {expected_why}"
            if expected_why
            else rec.explanation.summary
        )
        assert content == expected


def test_recommendation_feed_content_type_text(workdir: Path) -> None:
    view = demo_view(workdir)
    entries = recommendation_entries("recommendations", view.recommendations)
    xml_text = build_shelf_acquisition("recommendations", "Recommendations", entries)
    root = ET.fromstring(xml_text)
    for entry in root.findall(f"{ATOM}entry"):
        content_el = entry.find(f"{ATOM}content")
        assert content_el.get("type") == "text"


# --- calibre-web link: config-driven, omitted if unset -----------------------


def test_calibre_web_link_omitted_when_unset(workdir: Path) -> None:
    view = demo_view(workdir)
    entries = to_read_entries("to-read", view.to_read)
    xml_text = build_shelf_acquisition("to-read", "To read", entries)
    assert 'rel="alternate"' not in xml_text


def test_calibre_web_link_present_when_configured(workdir: Path) -> None:
    view = demo_view(workdir)
    entries = to_read_entries("to-read", view.to_read)
    xml_text = build_shelf_acquisition(
        "to-read", "To read", entries, calibre_web_url="https://books.example.org/"
    )
    assert 'rel="alternate"' in xml_text
    assert "https://books.example.org/search" in xml_text


# --- determinism: matches the reproducibility gate on the HTML renderer -----


def test_feeds_are_byte_identical_across_builds(tmp_path: Path) -> None:
    view_a = demo_view(tmp_path / "a")
    view_b = demo_view(tmp_path / "b")
    assert build_root_navigation(view_a) == build_root_navigation(view_b)
    entries_a = recommendation_entries("recommendations", view_a.recommendations)
    entries_b = recommendation_entries("recommendations", view_b.recommendations)
    feed_a = build_shelf_acquisition("recommendations", "Recommendations", entries_a)
    feed_b = build_shelf_acquisition("recommendations", "Recommendations", entries_b)
    assert feed_a == feed_b


# --- XML escaping -------------------------------------------------------------


def test_entry_content_is_xml_escaped() -> None:
    from ingest.models import Author, Book, ReadingState, ReadingStatus

    book = Book(book_id="b1", title="<script>&", authors=(Author("A & B"),))
    state = ReadingState(
        title=book.title, authors=("A & B",), status=ReadingStatus.UNREAD, book=book
    )
    entries = to_read_entries("to-read", [state])
    xml_text = build_shelf_acquisition("to-read", "To read", entries)
    assert "<script>" not in xml_text
    assert "&lt;script&gt;" in xml_text
    assert "A &amp; B" in xml_text
    ET.fromstring(xml_text)  # still well-formed


def test_entry_with_no_authors_falls_back_to_unknown() -> None:
    from ingest.models import ReadingState, ReadingStatus

    state = ReadingState(title="Anonymous Work", authors=(), status=ReadingStatus.UNREAD, book=None)
    entries = to_read_entries("to-read", [state])
    xml_text = build_shelf_acquisition("to-read", "To read", entries)
    parsed = _feed_entries(xml_text)
    assert len(parsed) == 1
    author_names = {a.find(f"{ATOM}name").text for a in parsed[0].findall(f"{ATOM}author")}
    assert author_names == {"Unknown"}


# --- auth gate + wiring, via the FastAPI app (mirrors tests/test_auth.py) ---


def test_opds_requires_auth_and_serves_atom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("STACKS_DEMO", "1")
    monkeypatch.setenv("STACKS_DATA_DIR", str(tmp_path))
    from tests.conftest import seed_store_from_env

    seed_store_from_env()
    from app.server import create_app

    client = TestClient(create_app())

    assert client.get("/opds").status_code == 401
    assert client.get("/opds", headers={"Authorization": "Bearer wrong"}).status_code == 401

    ok = client.get("/opds", headers={"Authorization": "Bearer demo-token"})
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("application/atom+xml")

    for path in (
        "/opds/to-read",
        "/opds/currently-reading",
        "/opds/series-next",
        "/opds/recommendations",
    ):
        assert client.get(path).status_code == 401
        shelf_ok = client.get(path, headers={"Authorization": "Bearer demo-token"})
        assert shelf_ok.status_code == 200
        assert shelf_ok.headers["content-type"].startswith("application/atom+xml")
        ET.fromstring(shelf_ok.text)
