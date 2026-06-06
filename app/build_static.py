"""Generate the static HTML artifact that the a11y gate audits.

``make a11y`` runs this to produce ``docs/audits/dashboard.html`` from the
offline demo world, then checks it with pa11y (if installed) or the built-in
:mod:`app.a11y_check`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.render import render_dashboard
from app.view import demo_view

DEFAULT_OUT = Path("docs/audits/dashboard.html")


def build(out: Path = DEFAULT_OUT) -> Path:
    with tempfile.TemporaryDirectory(prefix="qsr-demo-") as tmp:
        view = demo_view(Path(tmp))
    html = render_dashboard(
        view.currently_reading,
        view.finished,
        view.stats,
        view.wrapped,
        view.recommendations,
        user=view.user,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    path = build()
    print(f"wrote {path}")  # noqa: T201
