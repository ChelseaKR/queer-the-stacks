"""Persisted public catalog refresh, consent, freshness, and last-good behavior."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from app.view import view_from_store
from ingest.config import load_config
from ingest.demo import build_demo_dbs
from ingest.models import Author, Book, Source, SourceKind, ThemeTag
from ingest.refresh import doctor, refresh
from ingest.store import Store
from recommender.catalog_pool import fetch_catalog_pool


def _catalog_book() -> Book:
    source = Source(
        SourceKind.OPENLIBRARY_SUBJECT,
        "https://openlibrary.org/subjects/queer_fiction",
        "2026-07-25",
        "queer fiction",
    )
    return Book(
        book_id="ol:/works/OL1W",
        title="Public Discovery",
        authors=(Author("Catalog Author"),),
        theme_tags=(ThemeTag("queer", source), ThemeTag("fiction", source)),
    )


def _config(tmp_path: Path, *, outbound: str = "public-metadata"):
    metadata_db, statistics_db = build_demo_dbs(tmp_path / "lib")
    return load_config(
        env={
            "STACKS_CALIBRE_DB": str(metadata_db),
            "STACKS_KOREADER_DB": str(statistics_db),
            "STACKS_DATA_DIR": str(tmp_path / "data"),
            "STACKS_CATALOG_OUTBOUND": outbound,
            "STACKS_CATALOG_TTL": "60",
            "STACKS_OPENLIBRARY_SUBJECTS": "queer_fiction",
        },
        config_path=tmp_path / "absent.toml",
    )


def test_catalog_refresh_is_opt_in_and_ttl_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def subject(_client: object, name: str, limit: int = 50) -> tuple[Book, ...]:
        calls.append(name)
        return (_catalog_book(),)

    monkeypatch.setattr("recommender.catalogs.OpenLibraryClient.subject", subject)
    cfg = _config(tmp_path)
    with Store(cfg.store_path) as store:
        first = refresh(cfg, store, now=100)
        assert first.catalog_attempted == 1
        assert first.catalog_succeeded == 1
        assert first.catalog_candidates == 1
        assert calls == ["queer_fiction"]

        # Neither local source nor catalog TTL changed: the whole refresh skips.
        second = refresh(cfg, store, now=159)
        assert second.refreshed is False
        assert calls == ["queer_fiction"]

        # Catalog TTL alone breaks the source-mtime skip and fetches broad,
        # predeclared public metadata again.
        third = refresh(cfg, store, now=160)
        assert third.refreshed is True
        assert third.catalog_attempted == 1
        assert calls == ["queer_fiction", "queer_fiction"]


def test_catalog_ttl_refresh_performs_a_new_network_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    class Response:
        status_code = 200
        text = (
            '{"works":[{"key":"/works/OL1W","title":"Public Discovery",'
            '"authors":[{"name":"Catalog Author"}]}]}'
        )

        def raise_for_status(self) -> None:
            return None

    def get(
        url: str,
        timeout: int,
        headers: dict[str, str],
        allow_redirects: bool,
    ) -> Response:
        del timeout, headers
        assert allow_redirects is False
        calls.append(url)
        return Response()

    monkeypatch.setattr("requests.get", get)
    cfg = _config(tmp_path)
    with Store(cfg.store_path) as store:
        refresh(cfg, store, now=100)
        refresh(cfg, store, now=160)

    assert calls == [
        "https://openlibrary.org/subjects/queer_fiction.json?limit=50",
        "https://openlibrary.org/subjects/queer_fiction.json?limit=50",
    ]


def test_catalog_failure_keeps_last_good_pool_and_exposes_degraded_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "recommender.catalogs.OpenLibraryClient.subject",
        lambda _client, _name, limit=50: (_catalog_book(),),
    )
    cfg = _config(tmp_path)
    with Store(cfg.store_path) as store:
        refresh(cfg, store, now=100)

        def fail(_client: object, _name: str, limit: int = 50) -> tuple[Book, ...]:
            raise TimeoutError("catalog unavailable")

        monkeypatch.setattr("recommender.catalogs.OpenLibraryClient.subject", fail)
        result = refresh(cfg, store, now=160)

        assert result.catalog_errors == 1
        assert store.load_catalog_candidates() == (_catalog_book(),)
        status = store.catalog_pool_status()
        assert status.state == "degraded"
        assert status.sources[0].fetched_at == 100
        assert status.sources[0].attempted_at == 160
        assert status.sources[0].error == "TimeoutError"
        catalog_check = next(
            check for check in doctor(cfg, store) if check.name.startswith("catalog openlibrary:")
        )
        assert catalog_check.ok is False
        assert "last-good" in catalog_check.detail


def test_catalog_outbound_off_never_calls_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> tuple[Book, ...]:
        raise AssertionError("catalog client must not run without explicit consent")

    monkeypatch.setattr("recommender.catalogs.OpenLibraryClient.subject", forbidden)
    cfg = _config(tmp_path, outbound="off")
    with Store(cfg.store_path) as store:
        result = refresh(cfg, store, now=100)
        assert result.catalog_attempted == 0
        assert store.catalog_pool_status().state == "off"
        assert store.load_catalog_candidates() == ()


def test_invalid_catalog_values_are_not_copied_into_persisted_source_ids(
    tmp_path: Path,
) -> None:
    cfg = dataclasses.replace(
        _config(tmp_path),
        openlibrary_subjects=("not a slug",),
        bookwyrm_lists=("https://reader:secret@bookwyrm.social/list/7#private",),
    )
    result = fetch_catalog_pool(cfg)
    source_ids = {update.source_id for update in result.updates}

    assert source_ids == {
        "openlibrary:subject:invalid-1",
        "bookwyrm:list:invalid-1",
    }
    assert all("secret" not in source_id and "private" not in source_id for source_id in source_ids)
    assert result.errors == 2


def test_refresh_removes_legacy_raw_response_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> tuple[Book, ...]:
        raise AssertionError("catalog client must remain off")

    monkeypatch.setattr("recommender.catalogs.OpenLibraryClient.subject", forbidden)
    cfg = _config(tmp_path, outbound="off")
    legacy = cfg.data_dir / "catalog-response-cache.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text('{"subject-interest":"raw response"}', encoding="utf-8")

    with Store(cfg.store_path) as store:
        refresh(cfg, store, now=100)

    assert not legacy.exists()


def test_view_uses_persisted_pool_and_demo_fallback_requires_demo_mode(
    tmp_path: Path, states: list, daily_activity: list
) -> None:
    with Store(tmp_path / "state.sqlite") as store:
        store.save(states, daily_activity, refreshed_at=100)

        real_view = view_from_store(store)
        assert real_view.recommendations == ()

        demo_view = view_from_store(store, demo_mode=True)
        assert demo_view.recommendations
