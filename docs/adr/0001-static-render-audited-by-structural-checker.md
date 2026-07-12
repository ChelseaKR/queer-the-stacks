# 0001. Pure HTML renderer audited statically, served live by FastAPI

* Status: accepted
* Date: 2026-06-05
* Ported from: `docs/ROADMAP.md` §6 (2026-07-05, form only — content unchanged)

## Context and Problem Statement

The dashboard needs an accessibility gate that runs reliably in CI, without depending on a live
browser being available on the runner.

## Decision Outcome

`app/render.py` is the single source of truth for the dashboard's *content*. `make a11y` renders it
to a static artifact and gates it (pa11y/axe, plus the built-in `app/a11y_check.py` structural
checker as a second, dependency-free layer), so the mechanical WCAG checks run in CI without
depending on a live server. `app/server.py` serves exactly the same HTML the gate checked.

## Rejected Options

* Testing accessibility against a running server (flakier; needs a browser reachable over HTTP in
  CI, not just a local file).

## 2026-07-05 update

Both layers are now merge-blocking (previously pa11y ran advisory-only — see the 2026-07-05
remediation log and `docs/audits/accessibility-2026-06-05.md`). The two-layer design in this ADR is
unchanged; only the pa11y layer's enforcement level changed.
