# Accessibility Audit — 2026-06-05

**Last verified: 2026-08-15 · Recheck cadence: per WCAG revision / UI change.**

Instantiates `RESPONSIBLE-TECH-FRAMEWORK.md` §E. Target: WCAG 2.2 AA as the
floor. The primary task — reading your unified dashboard and recommendations —
must be completable with a keyboard, a screen reader, magnification, and reduced
motion.

## Automated pass (auto-gated, merge-blocking)

`make a11y` renders every HTML document the app serves to a person — the demo
dashboard, the login entry point, and the share-card page — then runs two
blocking layers: the dependency-free structural checker (`app.a11y_check`) and a
real Chromium/axe layer. Pa11y scans each document at desktop and 320 × 800
mobile viewports; the browser contract additionally forces light and dark
preferences and asserts that document width never exceeds 320 CSS pixels. All
checks must pass; none is advisory. **Result: 0 violations.**

The page list is itself asserted. `tests/test_a11y.py` enumerates the app's
`HTMLResponse` routes and fails if one is not mapped to an audited document, so
a new template cannot join the app without joining the gate. `/browse` is
covered by `dashboard.html`: it renders the same `app.view.render_view` output
with a filtered library. A gate cannot fail on a page it never loads, and until
2026-08-15 the share page was such a page — its structural check ran in a unit
test, but the browser/axe, light/dark, and 320 px reflow layers never saw it.
It was clean when first put through them.

Mechanically verified properties:

- `<html lang>` + viewport meta on dashboard, login, and share,
- page-level reflow at 320 CSS pixels, enforced with a browser width assertion,
- exactly one `<h1>`, no skipped heading levels,
- a `<main>` landmark and a skip link to it,
- every data table has a `<caption>` and `<th scope>`,
- every link has discernible text,
- theme tags include a visible `#` glyph and label; progress has visible text
  plus a named native `<progress>` element, so neither relies on colour,
- chart-like stats, Wrapped, and diversity summaries ship real `<table>`
  equivalents; recommendations are semantic articles with visible fit,
  explanation, and source text rather than a duplicate table,
- light and dark preference modes both pass axe color-contrast checks,
- `prefers-reduced-motion` disables animation/transition.

Tests: `tests/test_a11y.py` (structural contracts + checker unit tests) and
`scripts/a11y-browser-check.js` (explicit light/dark axe + 320 px reflow).

## Manual pass (review-gated)

Completed engineering evidence (useful, but not a substitute for a human
assistive-technology sign-off):

- [x] Technical keyboard walkthrough of sign-in and the dashboard in a real
      browser (focus order, skip link, same-origin login submission).
- [x] Dashboard and login reflow at 320 px, with a blocking browser assertion.
- [x] Automated contrast check for the explicit light and dark palettes.

The following human walkthroughs remain required before the first release and
are **not yet signed off**:

- [ ] Keyboard-only walkthrough of the dashboard (tab order, visible focus,
      skip link).
- [ ] Screen-reader walkthrough (VoiceOver/NVDA) of currently-reading, stats,
      Wrapped, and a recommendation card.
- [ ] Human 200% zoom walkthrough using the participant's normal browser.

## Accessibility statement

This dashboard targets WCAG 2.2 AA. Charts have data-table equivalents; theme
tags are never colour-only; the interface respects reduced-motion. Report issues
via the project tracker.

## 2026-07-05 update

pa11y previously ran advisory-only (`|| echo`, `Makefile:59-63`) while the
committed ledger (`docs/ROADMAP.md` §7) claimed it was merge-blocking — an
honesty defect flagged by the 2026-07-05 conformance audit (A11Y-03). Running
pa11y locally to graduate it surfaced a real, previously-undetected
color-contrast defect (384 `color-contrast` findings): the dashboard set no
explicit `color`/`background-color` anywhere, relying only on
`color-scheme: light dark`, which left some elements without a guaranteed
AA-contrast pair. Fixed in `app/render.py`/`app/share.py` (explicit
`CanvasText`/`Canvas` fg/bg, inherited down through tables) and re-verified:
pa11y now reports **0 issues** on three consecutive local runs. The `||` swallow
was removed from `Makefile:52-58`; pa11y is now genuinely merge-blocking
alongside the structural checker, closing A11Y-03.

## 2026-07-25 update

The redesigned daily homepage and login entry point are checked at desktop and
320 × 800 viewports with the structural checker and pa11y/axe. A separate
browser contract makes light/dark preference deterministic and tests real
document width because axe alone does not implement WCAG 1.4.10 reflow. The
review caught and fixed low-contrast text, horizontal overflow, unnamed
progress elements, unassociated login errors, broken local-source anchors, and
a table presentation that could have damaged native table semantics. The final
automated result is zero violations for both documents in all gated modes.

Technical dogfood against 1,907 real Calibre states also passed the structural,
desktop pa11y, and mobile pa11y checks; see
[`real-library-dogfood-2026-07-25.md`](real-library-dogfood-2026-07-25.md).
This evidence does **not** sign off the remaining human screen-reader or
magnification walkthroughs. Those stay release-blocking and are included in the
consent-based study protocol at
[`../research/real-user-study-plan.md`](../research/real-user-study-plan.md).
