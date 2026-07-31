"""Generate the static HTML artifacts that the accessibility gate audits.

``make a11y`` runs this to produce the offline demo dashboard and the login
document, then checks both with the built-in structural checker and a real
browser/axe runtime at desktop, mobile, and dark-preference settings.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.view import demo_view, render_view

DEFAULT_OUT = Path("docs/audits/dashboard.html")
DEFAULT_LOGIN_OUT = Path("docs/audits/login.html")


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


def build_all() -> tuple[Path, Path]:
    """Write every HTML document covered by the blocking accessibility gate."""
    return build(), build_login()


if __name__ == "__main__":
    for path in build_all():
        print(f"wrote {path}")  # noqa: T201
