# Accessibility Audit — 2026-06-05

**Last verified: 2026-06-05 · Recheck cadence: per WCAG revision / UI change.**

Instantiates `RESPONSIBLE-TECH-FRAMEWORK.md` §E. Target: WCAG 2.2 AA as the
floor. The primary task — reading your unified dashboard and recommendations —
must be completable with a keyboard, a screen reader, magnification, and reduced
motion.

## Automated pass (auto-gated, merge-blocking)

`make a11y` renders the demo dashboard to `docs/audits/dashboard.html` and runs
**two blocking layers**: the dependency-free structural checker (`app.a11y_check`)
and pa11y (real headless-Chrome axe runtime, including color-contrast). Both must
report zero violations to pass; neither is advisory. **Result: 0 violations on
both** (graduated from pa11y-advisory to pa11y-blocking on 2026-07-05, after
fixing a real color-contrast gap — see "2026-07-05 update" below).

Mechanically verified properties:

- `<html lang>` + viewport meta (zoom + 320 px reflow),
- exactly one `<h1>`, no skipped heading levels,
- a `<main>` landmark and a skip link to it,
- every data table has a `<caption>` and `<th scope>`,
- every link has discernible text,
- theme tags and progress are conveyed as **text** (a `#` glyph + label), never
  colour alone,
- every "chart" (stats, Wrapped, recommendation scores) ships a real `<table>`
  data-equivalent,
- `prefers-reduced-motion` disables animation/transition.

Tests: `tests/test_a11y.py` (zero-violation gate + checker unit tests).

## Manual pass (review-gated)

The following manual walkthroughs are required before the first release and are
**not yet signed off**:

- [ ] Keyboard-only walkthrough of the dashboard (tab order, visible focus, skip link).
- [ ] Screen-reader walkthrough (VoiceOver/NVDA) of currently-reading, stats,
      Wrapped, and a recommendation card.
- [ ] 200% zoom and 320 px reflow visual check.
- [ ] Contrast check in both light and dark `color-scheme`.

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
