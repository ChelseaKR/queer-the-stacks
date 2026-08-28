"""Static import resolution, shared by the guardrails that scan first-party code.

Two merge-blocking guardrails ask the same question of every module under
``app/``, ``ingest/`` and ``recommender/``: *can this file reach a namespace it
is not allowed to reach?* ``tests/test_no_egress.py`` asks it about network and
telemetry namespaces; ``tests/test_log_safety.py`` asks it about the logging
machinery.

Both used to be answered by a substring scan over the source text. The no-egress
one was rewritten as an :mod:`ast` scan after ``from requests import post``,
``import httpx``, ``from http import client`` and ``import aiohttp`` were all
shown to slip past a four-token list. The log-safety one still ran the original
four-token shape, and ``from logging import warning`` slipped past it in exactly
the same way.

So the scanner lives here once, is proved once (see
``test_no_egress.py::test_import_scan_detects_every_egress_form`` and
``test_log_safety.py::test_import_scan_detects_every_logging_form``), and is
used by both.

**What this establishes, and what it does not.** Names are resolved statically.
A dynamic import built from a computed string is invisible here, which is why
the no-egress guardrail also measures at the socket. A denied namespace reached
indirectly, through a module that is itself allowed, is likewise out of scope
for this layer.
"""

from __future__ import annotations

import ast


def module_prefixes(name: str) -> list[str]:
    """``a.b.c`` -> ``['a.b.c', 'a.b', 'a']`` (longest first)."""
    parts = name.split(".")
    return [".".join(parts[: len(parts) - i]) for i in range(len(parts))]


def classify(name: str, denied: frozenset[str], exceptions: frozenset[str]) -> bool:
    """True if ``name`` resolves to a denied namespace, most-specific rule wins."""
    for prefix in module_prefixes(name):
        if prefix in exceptions:
            return False
        if prefix in denied:
            return True
    return False


def imported_modules(source: str) -> set[str]:
    """Every module name a source file can pull in, resolved statically.

    Covers ``import x.y``, ``from x.y import z`` (recording ``x.y`` and
    ``x.y.z``, since the imported name may itself be a submodule), and a literal
    ``importlib.import_module("x")`` / ``__import__("x")``. Relative imports are
    first-party and skipped.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call):
            func = node.func
            called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if called in {"__import__", "import_module"} and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    found.add(first.value)
    return found


def denied_imports(source: str, denied: frozenset[str], exceptions: frozenset[str]) -> set[str]:
    """The imports in ``source`` that resolve into a denied namespace."""
    return {name for name in imported_modules(source) if classify(name, denied, exceptions)}
