"""A dependency-free, offline checker for the mechanical WCAG 2.2 AA subset.

This is the fallback a11y gate when a browser-based runner (pa11y/axe) is not
available. It is intentionally conservative — it only asserts what is
unambiguously checkable from static HTML — and ``make a11y`` prefers pa11y when
it is installed. Run as ``python -m app.a11y_check FILE``; exits non-zero on any
violation.
"""

from __future__ import annotations

import sys
from html.parser import HTMLParser
from pathlib import Path


class _A11yParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.violations: list[str] = []
        self.html_lang = False
        self.has_viewport = False
        self.h1_count = 0
        self.heading_levels: list[int] = []
        self.has_main = False
        self.has_skip = False
        self._table_has_caption = False
        self._open_a = False
        self._a_text = ""

    # Split into per-concern helpers (mccabe/C90 gate, QW-10): handle_starttag
    # itself just dispatches, so each independent tag check stays separately
    # readable and under the complexity ceiling. Behavior is unchanged — every
    # check below ran unconditionally in the original flat `if` chain too.
    def _check_landmarks(self, tag: str, attrs: dict[str, str | None]) -> None:
        if tag == "html" and attrs.get("lang"):
            self.html_lang = True
        if tag == "meta" and attrs.get("name") == "viewport":
            self.has_viewport = True
        if tag == "main" or attrs.get("role") == "main":
            self.has_main = True

    def _check_heading(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(tag[1])
            self.heading_levels.append(level)
            if level == 1:
                self.h1_count += 1

    def _check_anchor_open(self, tag: str, attrs: dict[str, str | None]) -> None:
        if tag != "a":
            return
        href = attrs.get("href") or ""
        if href.startswith("#") and ("skip" in (attrs.get("class") or "")):
            self.has_skip = True
        self._open_a = True
        self._a_text = ""
        if not href.strip():
            self.violations.append("anchor with empty href")

    def _check_img(self, tag: str, attrs: dict[str, str | None]) -> None:
        if tag == "img" and not attrs.get("alt") and attrs.get("alt") != "":
            self.violations.append("img without alt attribute")

    def _check_table_open(self, tag: str, attrs: dict[str, str | None]) -> None:
        if tag == "table":
            self._table_has_caption = False
        if tag == "caption":
            self._table_has_caption = True
        if tag == "th" and not attrs.get("scope"):
            self.violations.append("th without scope attribute")

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = dict(attrs_list)
        self._check_landmarks(tag, attrs)
        self._check_heading(tag)
        self._check_anchor_open(tag, attrs)
        self._check_img(tag, attrs)
        self._check_table_open(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            if self._open_a and not self._a_text.strip():
                self.violations.append("link with no accessible text")
            self._open_a = False
        if tag == "table" and not self._table_has_caption:
            self.violations.append("table without caption")

    def handle_data(self, data: str) -> None:
        if self._open_a:
            self._a_text += data


def check_html(html: str) -> list[str]:
    """Return a list of accessibility violations (empty == passing)."""
    parser = _A11yParser()
    parser.feed(html)
    v = list(parser.violations)
    if not parser.html_lang:
        v.append("<html> missing lang attribute")
    if not parser.has_viewport:
        v.append("missing viewport meta (zoom/reflow)")
    if parser.h1_count != 1:
        v.append(f"expected exactly one <h1>, found {parser.h1_count}")
    if not parser.has_main:
        v.append("no <main> landmark")
    if not parser.has_skip:
        v.append("no skip link to main content")
    prev = 0
    for level in parser.heading_levels:
        if prev and level > prev + 1:
            v.append(f"heading level jumps from h{prev} to h{level}")
        prev = level
    return v


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python -m app.a11y_check FILE.html", file=sys.stderr)  # noqa: T201
        return 2
    html = Path(args[0]).read_text(encoding="utf-8")
    violations = check_html(html)
    if violations:
        print(f"{len(violations)} accessibility violation(s):", file=sys.stderr)  # noqa: T201
        for v in violations:
            print(f"  - {v}", file=sys.stderr)  # noqa: T201
        return 1
    print("a11y: 0 violations")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
