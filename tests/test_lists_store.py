"""Persistence for authored curated lists — round-trip, validation, export."""

from __future__ import annotations

from pathlib import Path

import pytest
from ingest.config import Config
from recommender.lists import CuratedList, ListValidationError
from recommender.lists_store import (
    add_book_to_list,
    export_lists,
    list_store_path,
    list_to_record,
    load_stored_lists,
    new_list,
    records_from_lists,
    save_lists,
)


def _config(tmp_path: Path) -> Config:
    return Config(
        calibre_db=None,
        koreader_db=None,
        data_dir=tmp_path,
        kosync_host=None,
        kosync_user=None,
        kosync_key=None,
        demo=False,
    )


def test_list_store_path_is_under_data_dir(tmp_path: Path) -> None:
    assert list_store_path(_config(tmp_path)) == tmp_path / "lists.json"


def test_list_to_record_roundtrips_via_records_from_lists() -> None:
    lst = CuratedList(
        name="My Canon",
        citation="curated-list:my-canon",
        book_ids=("ol:nevada", "ol:fifth-season"),
        retrieved_at="2026-07-02",
    )
    record = list_to_record(lst)
    assert record == {
        "name": "My Canon",
        "citation": "curated-list:my-canon",
        "book_ids": ["ol:nevada", "ol:fifth-season"],
        "retrieved_at": "2026-07-02",
    }
    assert records_from_lists((lst,)) == [record]


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "lists.json"
    lists = (
        CuratedList(name="A", citation="curated-list:a", book_ids=("ol:1",)),
        CuratedList(name="B", citation="curated-list:b", book_ids=("ol:2", "ol:3")),
    )
    save_lists(path, lists)
    loaded = load_stored_lists(path)
    assert loaded == lists


def test_save_writes_sorted_keys_json_with_trailing_newline(tmp_path: Path) -> None:
    path = tmp_path / "lists.json"
    save_lists(path, (CuratedList(name="A", citation="c", book_ids=("ol:1",)),))
    body = path.read_text(encoding="utf-8")
    assert body.endswith("\n")
    # sort_keys means "book_ids" sorts before "citation" before "name" before "retrieved_at"
    first_obj = body[body.index("{") : body.index("}") + 1]
    assert first_obj.index('"book_ids"') < first_obj.index('"citation"')
    assert first_obj.index('"citation"') < first_obj.index('"name"')
    assert first_obj.index('"name"') < first_obj.index('"retrieved_at"')


def test_load_stored_lists_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_stored_lists(tmp_path / "does-not-exist.json") == ()


def test_save_rejects_list_with_no_citation(tmp_path: Path) -> None:
    path = tmp_path / "lists.json"
    bad = (CuratedList(name="X", citation="", book_ids=("ol:1",)),)
    with pytest.raises(ListValidationError, match="citation"):
        save_lists(path, bad)
    assert not path.exists()  # invalid list is never persisted


def test_save_rejects_list_with_no_books(tmp_path: Path) -> None:
    path = tmp_path / "lists.json"
    bad = (CuratedList(name="X", citation="curated-list:x", book_ids=()),)
    with pytest.raises(ListValidationError, match="no books"):
        save_lists(path, bad)
    assert not path.exists()


def test_new_list_adds_and_is_immutable() -> None:
    lists: tuple[CuratedList, ...] = ()
    updated = new_list(lists, "My Canon", "curated-list:my-canon", ("ol:nevada",))
    assert lists == ()  # original untouched
    assert len(updated) == 1
    assert updated[0].name == "My Canon"
    assert updated[0].book_ids == ("ol:nevada",)


def test_new_list_rejects_duplicate_name() -> None:
    lists = (CuratedList(name="My Canon", citation="curated-list:x", book_ids=("ol:1",)),)
    with pytest.raises(ListValidationError, match="already exists"):
        new_list(lists, "My Canon", "curated-list:y", ("ol:2",))


def test_new_list_rejects_blank_name() -> None:
    with pytest.raises(ListValidationError, match="must have a name"):
        new_list((), "   ", "curated-list:x", ("ol:1",))


def test_new_list_rejects_missing_citation() -> None:
    with pytest.raises(ListValidationError, match="citation"):
        new_list((), "My Canon", "", ("ol:1",))


def test_add_book_to_list_appends_and_is_immutable() -> None:
    lists = (CuratedList(name="My Canon", citation="curated-list:my-canon", book_ids=("ol:1",)),)
    updated = add_book_to_list(lists, "My Canon", "ol:2")
    assert lists[0].book_ids == ("ol:1",)  # original untouched
    assert updated[0].book_ids == ("ol:1", "ol:2")


def test_add_book_to_list_is_idempotent_for_duplicate_book() -> None:
    lists = (CuratedList(name="My Canon", citation="curated-list:my-canon", book_ids=("ol:1",)),)
    updated = add_book_to_list(lists, "My Canon", "ol:1")
    assert updated[0].book_ids == ("ol:1",)


def test_add_book_to_list_missing_list_raises() -> None:
    with pytest.raises(ListValidationError, match="no list named"):
        add_book_to_list((), "Does Not Exist", "ol:1")


def test_export_lists_returns_validated_json_string() -> None:
    lists = (CuratedList(name="A", citation="curated-list:a", book_ids=("ol:1",)),)
    body = export_lists(lists)
    assert body.endswith("\n")
    assert '"name": "A"' in body


def test_export_lists_rejects_invalid_list() -> None:
    bad = (CuratedList(name="X", citation="", book_ids=("ol:1",)),)
    with pytest.raises(ListValidationError):
        export_lists(bad)


def test_author_export_reimport_on_clean_dir(tmp_path: Path) -> None:
    """The EXP-05 acceptance flow: author -> export -> re-import on a clean instance."""
    lists = new_list((), "My Canon", "curated-list:my-canon", ("ol:nevada",))
    lists = add_book_to_list(lists, "My Canon", "ol:fifth-season")
    exported = export_lists(lists)

    clean_dir = tmp_path / "clean-instance"
    clean_dir.mkdir()
    out_path = clean_dir / "lists.json"
    out_path.write_text(exported, encoding="utf-8")

    reimported = load_stored_lists(out_path)
    assert reimported == lists
