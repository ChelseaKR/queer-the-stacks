"""Config resolution: defaults, TOML file, env overrides, secret handling."""

from __future__ import annotations

from pathlib import Path

import pytest
from ingest.config import DEFAULT_DATA_DIR, load_config


def test_defaults_when_nothing_set(tmp_path: Path) -> None:
    cfg = load_config(env={}, config_path=tmp_path / "absent.toml")
    assert cfg.calibre_db is None
    assert cfg.koreader_db is None
    assert cfg.kobo_db is None
    assert cfg.data_dir == DEFAULT_DATA_DIR
    assert cfg.demo is False
    assert cfg.kosync_configured is False
    assert cfg.has_real_sources is False


def test_env_overrides(tmp_path: Path) -> None:
    env = {
        "STACKS_CALIBRE_DB": "/lib/metadata.db",
        "STACKS_KOREADER_DB": "/lib/statistics.sqlite",
        "STACKS_KOBO_DB": "/lib/KoboReader.sqlite",
        "STACKS_DATA_DIR": str(tmp_path / "state"),
        "STACKS_KOSYNC_HOST": "https://sync.example",
        "STACKS_KOSYNC_USER": "reader",
        "STACKS_KOSYNC_KEY": "deadbeef",
        "STACKS_DEMO": "1",
    }
    cfg = load_config(env=env, config_path=tmp_path / "absent.toml")
    assert cfg.calibre_db == Path("/lib/metadata.db")
    assert cfg.koreader_db == Path("/lib/statistics.sqlite")
    assert cfg.kobo_db == Path("/lib/KoboReader.sqlite")
    assert cfg.data_dir == tmp_path / "state"
    assert cfg.demo is True
    assert cfg.kosync_configured is True
    assert cfg.has_real_sources is True
    assert cfg.store_path == tmp_path / "state" / "app-state.sqlite"
    assert cfg.snapshot_dir == tmp_path / "state" / "snapshots"


def test_kobo_only_counts_as_a_real_source(tmp_path: Path) -> None:
    cfg = load_config(
        env={"STACKS_KOBO_DB": "/lib/KoboReader.sqlite"}, config_path=tmp_path / "absent.toml"
    )
    assert cfg.calibre_db is None
    assert cfg.koreader_db is None
    assert cfg.kobo_db == Path("/lib/KoboReader.sqlite")
    assert cfg.has_real_sources is True


def test_toml_file_is_read(tmp_path: Path) -> None:
    toml = tmp_path / "stacks.toml"
    toml.write_text(
        """
        [calibre]
        path = "/books/metadata.db"
        [koreader]
        path = "/books/statistics.sqlite"
        [kobo]
        path = "/books/KoboReader.sqlite"
        [kosync]
        host = "https://sync.example"
        user = "me"
        [storage]
        data_dir = "/srv/stacks-data"
        """,
        encoding="utf-8",
    )
    cfg = load_config(env={}, config_path=toml)
    assert cfg.calibre_db == Path("/books/metadata.db")
    assert cfg.koreader_db == Path("/books/statistics.sqlite")
    assert cfg.kobo_db == Path("/books/KoboReader.sqlite")
    assert cfg.kosync_host == "https://sync.example"
    assert cfg.kosync_user == "me"
    assert cfg.data_dir == Path("/srv/stacks-data")
    # No key in the file -> kosync not fully configured (secret comes from env).
    assert cfg.kosync_configured is False


def test_env_beats_toml(tmp_path: Path) -> None:
    toml = tmp_path / "stacks.toml"
    toml.write_text('[calibre]\npath = "/from/toml.db"\n', encoding="utf-8")
    cfg = load_config(env={"STACKS_CALIBRE_DB": "/from/env.db"}, config_path=toml)
    assert cfg.calibre_db == Path("/from/env.db")


def test_hide_sensitive_descriptors_flag(tmp_path: Path) -> None:
    absent = tmp_path / "absent.toml"
    assert load_config(env={}, config_path=absent).hide_sensitive_descriptors is False
    cfg = load_config(env={"STACKS_HIDE_SENSITIVE": "1"}, config_path=absent)
    assert cfg.hide_sensitive_descriptors is True


def test_key_only_from_env_never_file(tmp_path: Path) -> None:
    toml = tmp_path / "stacks.toml"
    # Even if someone puts a key in the file, it is ignored — secrets are env-only.
    toml.write_text('[kosync]\nhost="h"\nuser="u"\nkey="should-be-ignored"\n', encoding="utf-8")
    cfg = load_config(env={}, config_path=toml)
    assert cfg.kosync_key is None
    cfg2 = load_config(env={"STACKS_KOSYNC_KEY": "realkey"}, config_path=toml)
    assert cfg2.kosync_key == "realkey"


def test_lens_config_defaults_to_none_without_committed_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no data/lenses.toml on disk, lens_config resolves to None (built-in)."""
    monkeypatch.chdir(tmp_path)
    cfg = load_config(env={}, config_path=tmp_path / "absent.toml")
    assert cfg.lens_config is None


def test_lens_config_env_override(tmp_path: Path) -> None:
    lens_path = tmp_path / "custom-lenses.toml"
    lens_path.write_text('[[lenses]]\nname = "X"\ndescriptors = ["y"]\n', encoding="utf-8")
    cfg = load_config(
        env={"STACKS_LENS_CONFIG": str(lens_path)}, config_path=tmp_path / "absent.toml"
    )
    assert cfg.lens_config == lens_path


def test_lens_config_toml_section(tmp_path: Path) -> None:
    lens_path = tmp_path / "custom-lenses.toml"
    lens_path.write_text('[[lenses]]\nname = "X"\ndescriptors = ["y"]\n', encoding="utf-8")
    toml = tmp_path / "stacks.toml"
    toml.write_text(f'[lenses]\npath = "{lens_path}"\n', encoding="utf-8")
    cfg = load_config(env={}, config_path=toml)
    assert cfg.lens_config == lens_path
