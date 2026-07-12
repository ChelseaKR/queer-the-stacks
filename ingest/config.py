"""Runtime configuration — where the real Calibre/KOReader libraries live.

Resolution order (later overrides earlier):

1. built-in defaults (demo off, ``data/`` for app state + snapshots),
2. a TOML config file (``stacks.toml`` by default, or ``$STACKS_CONFIG``),
3. ``STACKS_*`` environment variables.

Secrets (the kosync key) come from the environment only, never a committed file.
Nothing here opens a database or the network — it only resolves paths and flags,
so it is safe to import everywhere and trivial to test.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_CONFIG_FILE = "stacks.toml"
DEFAULT_DATA_DIR = Path("data")
#: Personalized diversity-lens grouping, auto-loaded when present (see
#: app/diversity.py::load_lens_config). Overridable via [lenses].path in
#: stacks.toml or $STACKS_LENS_CONFIG; ships as a committed template with the
#: current defaults so editing it "just works" with zero code changes.
DEFAULT_LENS_CONFIG = Path("data/lenses.toml")

# Every ``STACKS_*`` environment variable this app actually reads. Exported so
# ``ingest.refresh.doctor`` can flag typos (e.g. ``STACKS_CALIBER_DB``) without
# hardcoding a second copy of this list that can drift out of sync.
KNOWN_STACKS_ENV = frozenset(
    {
        "STACKS_CONFIG",
        "STACKS_DATA_DIR",
        "STACKS_DEMO",
        "STACKS_CALIBRE_DB",
        "STACKS_KOREADER_DB",
        "STACKS_KOSYNC_HOST",
        "STACKS_KOSYNC_USER",
        "STACKS_KOSYNC_KEY",
        "STACKS_APERTURE",
        "STACKS_EMBEDDINGS",
        "STACKS_DNF_SIGNALS",
        "STACKS_GOAL_BOOKS",
        "STACKS_GOAL_PAGES",
        "STACKS_GOAL_HOURS",
        "STACKS_GOAL_STREAK",
        "STACKS_AUTH_TOKEN",
        "STACKS_HIDE_SENSITIVE",
        "STACKS_CALIBRE_WEB_URL",
        "STACKS_LENS_CONFIG",
    }
)


@dataclass(frozen=True)
class Config:
    """Resolved runtime configuration. All paths are absolute-or-relative as given."""

    calibre_db: Optional[Path]
    koreader_db: Optional[Path]
    data_dir: Path
    kosync_host: Optional[str]
    kosync_user: Optional[str]
    kosync_key: Optional[str]  # md5 key, from the environment only
    demo: bool
    aperture_strength: float = 0.0  # boost-only discovery-widening lens (0 = off)
    embeddings_enabled: bool = False  # optional, strictly-local semantic signal
    dnf_signals: bool = False  # opt-in soft down-weighting of stalled themes
    goal_books: int = 0  # yearly book goal (0 = unset)
    goal_pages: int = 0  # yearly page goal (0 = unset)
    goal_hours: int = 0  # yearly reading-time goal in hours (0 = unset)
    goal_streak_days: int = 0  # streak goal in days (0 = unset)
    lens_config: Optional[Path] = None  # diversity-lens TOML override, if any
    hide_sensitive_descriptors: bool = False  # privacy: aggregate identity-adjacent tags

    @property
    def store_path(self) -> Path:
        """Where the persisted derived-state SQLite store lives."""
        return self.data_dir / "app-state.sqlite"

    @property
    def snapshot_dir(self) -> Path:
        """Where read-only snapshots of the source libraries are written."""
        return self.data_dir / "snapshots"

    @property
    def kosync_configured(self) -> bool:
        return bool(self.kosync_host and self.kosync_user and self.kosync_key)

    @property
    def has_real_sources(self) -> bool:
        return self.calibre_db is not None or self.koreader_db is not None


def _read_toml(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return data if isinstance(data, dict) else {}


def _section(data: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = data.get(name)
    return value if isinstance(value, Mapping) else {}


def _opt_path(value: Optional[str]) -> Optional[Path]:
    return Path(value) if value else None


def load_config(
    env: Optional[Mapping[str, str]] = None,
    config_path: Optional[Path] = None,
) -> Config:
    """Resolve configuration from a TOML file overlaid with ``STACKS_*`` env vars."""
    resolved_env: Mapping[str, str] = os.environ if env is None else env

    path = config_path or Path(resolved_env.get("STACKS_CONFIG", DEFAULT_CONFIG_FILE))
    toml = _read_toml(path)
    calibre = _section(toml, "calibre")
    koreader = _section(toml, "koreader")
    kosync = _section(toml, "kosync")
    storage = _section(toml, "storage")

    def pick(env_key: str, section: Mapping[str, object], key: str) -> Optional[str]:
        if env_key in resolved_env and resolved_env[env_key]:
            return resolved_env[env_key]
        raw = section.get(key)
        return str(raw) if isinstance(raw, (str, int)) else None

    data_dir = _opt_path(pick("STACKS_DATA_DIR", storage, "data_dir")) or DEFAULT_DATA_DIR
    rec = _section(toml, "recommender")

    aperture_raw = pick("STACKS_APERTURE", rec, "aperture_strength")
    try:
        aperture = max(0.0, min(1.0, float(aperture_raw))) if aperture_raw else 0.0
    except ValueError:
        aperture = 0.0

    goals = _section(toml, "goals")

    def pick_int(env_key: str, key: str) -> int:
        raw = pick(env_key, goals, key)
        try:
            return max(0, int(raw)) if raw else 0
        except ValueError:
            return 0

    lenses = _section(toml, "lenses")
    lens_config_raw = pick("STACKS_LENS_CONFIG", lenses, "path")
    if lens_config_raw:
        lens_config = Path(lens_config_raw)
    elif DEFAULT_LENS_CONFIG.is_file():
        lens_config = DEFAULT_LENS_CONFIG
    else:
        lens_config = None

    return Config(
        calibre_db=_opt_path(pick("STACKS_CALIBRE_DB", calibre, "path")),
        koreader_db=_opt_path(pick("STACKS_KOREADER_DB", koreader, "path")),
        data_dir=data_dir,
        kosync_host=pick("STACKS_KOSYNC_HOST", kosync, "host"),
        kosync_user=pick("STACKS_KOSYNC_USER", kosync, "user"),
        kosync_key=resolved_env.get("STACKS_KOSYNC_KEY") or None,  # secret: env only
        demo=resolved_env.get("STACKS_DEMO") == "1",
        aperture_strength=aperture,
        embeddings_enabled=resolved_env.get("STACKS_EMBEDDINGS") == "1",
        dnf_signals=resolved_env.get("STACKS_DNF_SIGNALS") == "1",
        goal_books=pick_int("STACKS_GOAL_BOOKS", "books"),
        goal_pages=pick_int("STACKS_GOAL_PAGES", "pages"),
        goal_hours=pick_int("STACKS_GOAL_HOURS", "hours"),
        goal_streak_days=pick_int("STACKS_GOAL_STREAK", "streak_days"),
        lens_config=lens_config,
        hide_sensitive_descriptors=resolved_env.get("STACKS_HIDE_SENSITIVE") == "1",
    )
