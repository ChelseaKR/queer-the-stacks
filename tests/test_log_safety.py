"""No-reading-content-in-logs guarantee.

Reading data is sensitive, so the **core** is kept log-free: no module in
ingest/recommender/app reaches the logging machinery — except the deliberately
audited web-request boundary. With the core log-free, a reading title or
progress value can never reach a log line.

The request boundary (``app/logging_config.py`` + its wiring in
``app/server.py``) does emit structured JSON access logs, but only request
*metadata* — method, path (never the query string), status, latency, request id.
That PII-safety is asserted separately in ``tests/test_observability.py``. The
CLI prints to stdout by design (the user ran it); that is not logging.

**How this is checked, and why it changed.** This file used to scan the source
*text* for four tokens (``import logging``, ``getLogger``,
``logging.basicConfig``, ``logging.getLogger``) and exempt files by
:attr:`~pathlib.Path.name`. Both halves were unfalsifiable in the same way
``tests/test_no_egress.py``'s original four-token network scan was, and that
file's docstring already records why the shape was abandoned there:

* ``from logging import warning`` at the top of ``app/render.py``, then
  ``warning("rendering %s", state.book.title)``, contains none of the four
  tokens. Reading titles reach stdout and both tests stay green.
* The exemption keyed on the bare filename, so a new ``ingest/server.py`` or
  ``recommender/server.py`` inherited ``app/server.py``'s exemption by
  basename collision.
* The confinement assertion was ``users <= LOG_ALLOWED``, a subset. Both audited
  files could stop logging entirely and it would still pass, leaving
  ``tests/test_observability.py``'s PII assertions guarding nothing.

All three are closed below: imports are resolved with :mod:`ast` through
``tests/importscan.py`` — the same scanner the no-egress guardrail uses — the
allowlist is keyed on the repository-relative path, and the confinement
assertion is an equality. The scanner is measured against the forms it must
catch in :func:`test_import_scan_detects_every_logging_form`, so a green run
here means the scan works rather than merely that it found nothing.
"""

from __future__ import annotations

from pathlib import Path

import app
import ingest
import pytest
import recommender

from tests.importscan import denied_imports, imported_modules, module_prefixes

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Namespaces that write log records. ``logging`` is the stdlib machinery;
#: ``structlog`` and ``loguru`` are the two obvious ways to log without
#: importing it, and are listed for the same fail-closed reason
#: ``tests/test_no_egress.py`` lists ``httpx`` and ``aiohttp`` despite neither
#: being a dependency: the guardrail should fail when someone adds one, not
#: after.
LOGGING_MODULE_PREFIXES: frozenset[str] = frozenset({"logging", "loguru", "structlog"})

#: Nothing inside the denied namespaces is exempt: ``logging.config`` and
#: ``logging.handlers`` are logging machinery too.
LOGGING_MODULE_EXCEPTIONS: frozenset[str] = frozenset()

#: The only file permitted to reach the logging machinery itself. Exactly one:
#: ``app/server.py`` never imports :mod:`logging`, it calls ``get_logger()`` and
#: ``configure_logging()`` from the audited module below. Repository-relative,
#: so a new module cannot inherit the exemption by sharing a basename.
#:
#: The previous version of this file listed ``server.py`` here as well and
#: asserted ``users <= LOG_ALLOWED``, a *subset*. That is what hid the
#: distinction: an allowlist entry for a file that does not actually import
#: logging costs nothing under a subset test, and so does both audited files
#: quietly ceasing to log at all.
LOGGING_MACHINERY_ALLOWED: frozenset[str] = frozenset({"app/logging_config.py"})

#: The first-party module every log record must be emitted through. Anything
#: that can write a log line does it by importing from here.
LOGGING_BOUNDARY_MODULE = "app.logging_config"

#: The only modules permitted to emit log records, i.e. to import the audited
#: boundary. ``app/server.py`` is the request-logging wiring plus two explicit
#: operational warnings (``startup_store_unpopulated``, ``readyz_unavailable``);
#: ``app/logging_config.py`` is the boundary itself.
LOG_EMITTERS_ALLOWED: frozenset[str] = frozenset({"app/logging_config.py", "app/server.py"})


def _source_files() -> list[Path]:
    roots = [Path(pkg.__file__).parent for pkg in (ingest, recommender, app)]
    return sorted(p for root in roots for p in root.rglob("*.py"))


def _relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def _logging_imports(source: str) -> set[str]:
    return denied_imports(source, LOGGING_MODULE_PREFIXES, LOGGING_MODULE_EXCEPTIONS)


def _can_emit_log_records(source: str) -> bool:
    """True if the module can write a log line, by either available route.

    Reaching :mod:`logging` directly is one route. Importing the audited
    boundary (``app.logging_config``) and calling ``get_logger()`` is the other,
    and it is the one ``app/server.py`` actually takes: no ``import logging``
    appears anywhere in that file.
    """
    if _logging_imports(source):
        return True
    reachable = {prefix for name in imported_modules(source) for prefix in module_prefixes(name)}
    return LOGGING_BOUNDARY_MODULE in reachable


def test_logging_machinery_is_reached_by_exactly_one_module() -> None:
    """Equality in both directions, so neither side can drift unnoticed.

    A new module reaching ``logging`` (or ``structlog``/``loguru``) fails here.
    So does ``app/logging_config.py`` quietly *stopping* being a logging module,
    because then ``tests/test_observability.py``'s PII assertions would be
    guarding a boundary that no longer exists.
    """
    users = {
        _relative(path)
        for path in _source_files()
        if _logging_imports(path.read_text(encoding="utf-8"))
    }
    assert users == set(LOGGING_MACHINERY_ALLOWED), (
        f"the set of modules reaching the logging machinery changed: "
        f"{sorted(users)} != {sorted(LOGGING_MACHINERY_ALLOWED)}"
    )


def test_log_emitters_are_exactly_the_audited_boundary() -> None:
    """Which modules can write a log line at all, asserted as an equality.

    Reaching :mod:`logging` is not the only way to log: a module that imports
    ``get_logger`` from the audited boundary emits records without importing
    the machinery, which is exactly what ``app/server.py`` does — that file
    contains no ``import logging`` at all. That second route was invisible to
    the old text scan, and it is the one a reading title would realistically
    travel: ``get_logger().info(f"rendering {state.book.title}")`` added to
    ``app/render.py`` reaches stdout with no ``import logging`` in the file.
    """
    emitters = {
        _relative(path)
        for path in _source_files()
        if _can_emit_log_records(path.read_text(encoding="utf-8"))
    }
    assert emitters == set(LOG_EMITTERS_ALLOWED), (
        f"the set of modules that can emit a log record changed: "
        f"{sorted(emitters)} != {sorted(LOG_EMITTERS_ALLOWED)}. Keep the core "
        "log-free so reading content has no path into a log line."
    )


def test_allowlisted_paths_all_exist() -> None:
    """An allowlist entry naming a file that is gone would exempt nothing, quietly."""
    for relative in sorted(LOGGING_MACHINERY_ALLOWED | LOG_EMITTERS_ALLOWED):
        assert (REPO_ROOT / relative).is_file(), (
            f"the log allowlists name {relative}, which does not exist; a stale "
            "entry hides that the boundary it describes has moved"
        )


@pytest.mark.parametrize(
    "snippet",
    [
        "import logging",
        "import logging.config",
        "import logging.handlers",
        "from logging import getLogger",
        "from logging import warning",
        "from logging.handlers import SysLogHandler",
        "from logging.config import dictConfig",
        "import structlog",
        "import loguru",
        "from loguru import logger",
        "from importlib import import_module\nlog = import_module('logging')",
        "m = __import__('logging')",
    ],
)
def test_import_scan_detects_every_logging_form(snippet: str) -> None:
    """The scanner is measured against the forms that must not slip past it.

    Most entries below are real bypasses of the four-token substring scan this
    file used to run: ``from logging import warning``, every
    ``from logging.<sub> import <name>`` form, both third-party loggers, and
    both dynamic-import forms contained none of the four tokens.
    """
    assert _logging_imports(snippet), f"logging scan missed a form: {snippet!r}"


@pytest.mark.parametrize(
    "snippet",
    [
        "import json",
        "import sqlite3",
        "from dataclasses import dataclass",
        "from pathlib import Path",
        "print('the CLI prints to stdout by design')",
    ],
)
def test_import_scan_does_not_flag_log_free_code(snippet: str) -> None:
    """The scan must stay usable: no false positive on ordinary offline code."""
    assert _logging_imports(snippet) == set(), f"logging scan false-positived on {snippet!r}"
