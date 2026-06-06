# Accessibility Audit — 2026-06-05

**Last verified: 2026-06-05 · Recheck cadence: per WCAG revision / UI change.**

Instantiates `RESPONSIBLE-TECH-FRAMEWORK.md` §E. Target: WCAG 2.2 AA as the
floor. The primary task — reading your unified dashboard and recommendations —
must be completable with a keyboard, a screen reader, magnification, and reduced
motion.

## Automated pass (auto-gated, merge-blocking)

`make a11y` renders the demo dashboard to `docs/audits/dashboard.html` and checks
it with pa11y (axe runtime) when installed, falling back to the dependency-free
`app.a11y_check`. **Result: 0 violations.**

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
