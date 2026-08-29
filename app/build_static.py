"""Generate the static HTML artifacts that the accessibility gate audits.

``make a11y`` runs this to produce every HTML document the app serves to a
person, then checks each with the built-in structural checker and a real
browser/axe runtime at desktop, mobile, and dark-preference settings.

The set is the point. A gate cannot fail on a page it never loads, and the
share page went unaudited by the browser layer for exactly that reason: it was
not written to disk here, so it was not in the list the Makefile scans. Any new
user-facing template belongs in :func:`build_all`.

``/browse`` is deliberately absent: it renders the same
:func:`app.view.render_view` document as ``/`` with a filtered library, so
``dashboard.html`` already covers its template.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from app.view import demo_view, render_view

DEFAULT_OUT = Path("docs/audits/dashboard.html")
DEFAULT_LOGIN_OUT = Path("docs/audits/login.html")
DEFAULT_SHARE_OUT = Path("docs/audits/share.html")


def build(out: Path = DEFAULT_OUT) -> Path:
    with tempfile.TemporaryDirectory(prefix="stacks-demo-") as tmp:
        view = demo_view(Path(tmp))
    html = render_view(view)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def build_login(out: Path = DEFAULT_LOGIN_OUT) -> Path:
    """Write the same login document served at ``GET /login``."""
    from app.server import _render_login_page

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_render_login_page(), encoding="utf-8")
    return out


def build_share(out: Path = DEFAULT_SHARE_OUT) -> Path:
    """Write the same share-card document served at ``GET /share``."""
    from app.share import build_share_cards, render_share_page

    with tempfile.TemporaryDirectory(prefix="stacks-demo-") as tmp:
        view = demo_view(Path(tmp))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render_share_page(
            build_share_cards(view), user=view.user, fixture_states=view.fixture_states
        ),
        encoding="utf-8",
    )
    return out


#: Where the committed audit artifacts live. Every default output below sits
#: here, and ``Makefile``'s ``A11Y_PAGES`` names the same three files.
DEFAULT_OUT_DIR = DEFAULT_OUT.parent


def build_all(out_dir: Optional[Path] = None) -> tuple[Path, ...]:
    """Write every HTML document covered by the blocking accessibility gate.

    ``out_dir`` exists so a test can call *this function* rather than
    reimplementing it by calling the three builders in turn. That distinction
    is the whole point of the function: a test that hand-calls the builders
    stays green when ``build_all`` stops calling one of them, and the page it
    dropped then goes unaudited while its stale committed copy keeps
    satisfying the Makefile's existence check.
    """
    base = DEFAULT_OUT_DIR if out_dir is None else Path(out_dir)
    return (
        build(base / DEFAULT_OUT.name),
        build_login(base / DEFAULT_LOGIN_OUT.name),
        build_share(base / DEFAULT_SHARE_OUT.name),
    )


if __name__ == "__main__":
    for path in build_all():
        print(f"wrote {path}")  # noqa: T201
