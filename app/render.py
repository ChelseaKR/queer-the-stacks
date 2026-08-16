"""Render the unified reading dashboard to accessible, semantic HTML.

This pure renderer is the single source of truth for the dashboard's *content*:
currently-reading across devices, reading stats, a private Reading Wrapped, and
explained recommendations. The FastAPI app serves exactly this HTML, and the
a11y gate (:mod:`app.a11y_check` / pa11y) audits it, so the mechanical WCAG 2.2
AA checks run in CI without a live browser.

Accessibility decisions baked in here:

* every page has ``lang`` + a viewport meta (zoom/reflow at 320 px),
* a skip link to ``<main>`` and proper landmarks + heading order,
* theme tags and progress are conveyed as **text**, never colour alone,
* every "chart" (stats, Wrapped) ships with a real ``<table>`` data equivalent,
* every recommendation shows its why **and** its sources as visible links.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from html import escape
from typing import TYPE_CHECKING, Optional

from ingest.models import Explanation, ReadingState, Recommendation
from ingest.store import CatalogPoolStatus

if TYPE_CHECKING:
    from app.view import BookForecast
from recommender.explain import NearMiss
from recommender.lists import CuratedList

from app.diversity import REDACTED_LABEL, DiversityReport
from app.goals import Goal
from app.shelf import SeriesNext
from app.stats import ReadingStats
from app.wrapped import Wrapped

LIBRARY_PREVIEW_LIMIT = 100


def _pct(value: float) -> str:
    return f"{value:.0%}"


def _withheld_note(hidden_count: int) -> str:
    """The visible stand-in for descriptors the privacy toggle withheld.

    Shown as text (never colour or omission alone) so the reader can always tell
    the difference between "this book has no sourced descriptors" and "some are
    being held back right now".
    """
    if hidden_count == 1:
        return f"{REDACTED_LABEL} (1 descriptor)"
    return f"{REDACTED_LABEL} ({hidden_count} descriptors)"


def _split_labels(labels: Sequence[str], hidden: frozenset[str]) -> tuple[list[str], int]:
    """Split sourced labels into the ones to show and a count of the withheld."""
    if not hidden:
        return list(labels), 0
    shown = [label for label in labels if label.strip().lower() not in hidden]
    return shown, len(labels) - len(shown)


def _theme_chips(state: ReadingState, hidden: frozenset[str] = frozenset()) -> str:
    """Per-book theme chips, minus anything the privacy toggle is withholding.

    A per-book chip is *more* revealing than the aggregated diversity breakdown,
    not less: it ties the descriptor to a specific title. Redacting the summary
    while publishing the detail beside each book would defeat the toggle.
    """
    if not state.theme_tags:
        return '<p class="themes">Themes: none recorded.</p>'
    shown, withheld = _split_labels([t.label for t in state.theme_tags], hidden)
    chips = " ".join(f'<span class="tag">{escape(label)}</span>' for label in shown)
    if withheld:
        chips = f'{chips} <span class="tag">{escape(_withheld_note(withheld))}</span>'.strip()
    return f'<p class="themes">Themes: {chips}</p>'


def _reading_item(state: ReadingState, hidden: frozenset[str] = frozenset()) -> str:
    authors = escape(", ".join(state.authors) or "unknown author")
    device = escape(state.latest_device or "—")
    title = escape(state.title)
    progress = max(0, min(100, round(state.percent_complete * 100)))
    return (
        '<li class="reading">'
        '<div class="shelfmark" aria-hidden="true"><span>IN CIRCULATION</span></div>'
        '<div class="reading-copy">'
        f"<h3>{title}</h3>"
        f'<p class="byline">by {authors}</p>'
        f'<p class="progress-label"><strong>{progress}% complete</strong>'
        f" · last on {device}</p>"
        f'<progress max="100" value="{progress}" '
        f'aria-label="Reading progress for {title}">{progress}%</progress>'
        f"{_theme_chips(state, hidden)}</div>"
        "</li>"
    )


def _stats_table(stats: ReadingStats) -> str:
    rows = "".join(
        f'<tr><th scope="row">{escape(label)}</th><td>{escape(value)}</td></tr>'
        for label, value in (
            ("Books finished", str(stats.books_finished)),
            ("Currently reading", str(stats.books_reading)),
            ("Pages read", str(stats.pages_read)),
            ("Time read (hours)", str(stats.read_time_hours)),
            ("Current streak (days)", str(stats.current_streak_days)),
            ("Longest streak (days)", str(stats.longest_streak_days)),
            ("Active reading days", str(stats.active_days)),
            ("Highlights", str(stats.total_highlights)),
        )
    )
    return (
        "<table><caption>Reading totals (data-table equivalent of the stats panel)"
        '</caption><thead><tr><th scope="col">Metric</th>'
        f'<th scope="col">Value</th></tr></thead><tbody>{rows}</tbody></table>'
    )


def _theme_mix_table(stats: ReadingStats, hidden: frozenset[str] = frozenset()) -> str:
    """The theme/genre mix, minus anything the privacy toggle is withholding.

    Withheld rows are dropped rather than replaced by a stand-in count: this
    table counts books per theme, and there is no way to combine those counts
    into a distinct-book total without inventing a number. The aggregated,
    correct figure already lives in the Reading-diversity section, so the note
    points there instead of guessing.
    """
    if not stats.theme_mix:
        return "<p>No sourced themes recorded yet.</p>"
    visible = [(label, count) for label, count in stats.theme_mix if label.lower() not in hidden]
    withheld = len(stats.theme_mix) - len(visible)
    rows = "".join(
        f'<tr><th scope="row">{escape(label)}</th><td>{count}</td></tr>' for label, count in visible
    )
    note = (
        f"<p>{escape(_withheld_note(withheld))} — held back here by the privacy toggle. "
        "The aggregated count is in the reading-diversity section below.</p>"
        if withheld
        else ""
    )
    if not visible:
        return f"{note}<p>No further sourced themes to show.</p>"
    return (
        "<table><caption>Theme &amp; genre mix, from sourced tags only"
        '</caption><thead><tr><th scope="col">Theme</th>'
        f'<th scope="col">Books</th></tr></thead><tbody>{rows}</tbody></table>{note}'
    )


def _wrapped_table(wrapped: Wrapped) -> str:
    """The standout-reads table, with the scope of its hours stated in the caption.

    These hours are all-time per book, while the panel around them is scoped to
    one year (see :class:`app.wrapped.StandoutRead`). Rendered under a bare
    "Hours" heading inside a "Reading Wrapped {year}" panel they read as the
    year's hours, and their sum can exceed the year's total — a number a reader
    can check in five seconds, and then stop believing the rest of the page. So
    the column names its scope, and when the totals do exceed the year the
    caption says why before the reader has to work it out.
    """
    standouts = "".join(
        f'<tr><th scope="row">{escape(r.title)}</th>'
        f"<td>{escape(', '.join(r.authors) or 'unknown')}</td>"
        f"<td>{r.total_read_time_hours}</td></tr>"
        for r in wrapped.standout_reads
    )
    if not standouts:
        standouts = '<tr><td colspan="3">No finished books recorded this year.</td></tr>'
    reconciliation = (
        " These add up to more than the "
        f"{wrapped.read_time_hours} hours above because at least one of them was "
        f"started before {wrapped.year}; the two figures measure different things."
        if wrapped.standouts_exceed_the_year
        else ""
    )
    return (
        f"<table><caption>Standout reads of {wrapped.year} — the books you finished "
        f"in {wrapped.year}, ranked by their all-time read time. KOReader keeps one "
        "cumulative total per book and no per-year breakdown, so these hours count "
        f"every session ever, not only {wrapped.year}.{reconciliation}"
        '</caption><thead><tr><th scope="col">Title</th>'
        '<th scope="col">Author</th><th scope="col">Hours (all time)</th></tr></thead>'
        f"<tbody>{standouts}</tbody></table>"
    )


#: Applied to every external (http/https) citation link: ``noopener`` +
#: ``noreferrer`` stop the new-tab window-handle and Referer leaks respectively
#: (belt-and-suspenders alongside the app-wide ``Referrer-Policy: no-referrer``
#: header); ``external`` is a plain semantic hint, not a browser behavior.
_EXTERNAL_REL = "noopener noreferrer external"


def _source_item(kind: object, citation: str, retrieved_at: str) -> str:
    """Render a citation as a link only when it is one, and as text otherwise.

    Local ``curated-list:...`` citations used to point at in-page fragments that
    did not exist. They remain visible provenance, but are no longer presented
    as broken links.

    The link test used to be ``startswith("http://", "https://")``, which said
    yes to ``https://openlibrary.org/subjects/science fiction`` — a string with
    a space in it, which no browser can resolve. The demo dashboard shipped that
    href. So the test is now :func:`~recommender.catalogs.is_citable_url`: the
    same allowlist, HTTPS, credential and whitespace rules the *fetch* path
    enforces, applied to the *display* path, so a citation the app would refuse
    to request is also one it will not hand the reader as a link. Anything that
    fails stays fully visible as text — the provenance is never hidden, it just
    stops pretending to be clickable.
    """
    from recommender.catalogs import is_citable_url

    label = escape(citation)
    if is_citable_url(citation):
        source = f'<a href="{label}" rel="{_EXTERNAL_REL}">{label}</a>'
    else:
        source = f'<span class="local-citation">{label}</span>'
    return (
        f"<li>{escape(str(kind))}: {source} "
        f'<span class="retrieved">(retrieved {escape(retrieved_at)})</span></li>'
    )


def _sources_html(explanation: Explanation) -> str:
    items = "".join(_source_item(s.kind, s.citation, s.retrieved_at) for s in explanation.sources)
    return f"<h4>Sources</h4><ul>{items}</ul>"


def _signals_html(explanation: Explanation, *, heading: str = "Why recommended") -> str:
    items = "".join(f"<li>{escape(s.kind)}: {escape(s.detail)}</li>" for s in explanation.signals)
    return f"<h4>{escape(heading)}</h4><ul>{items}</ul>"


def _rec_card(rec: Recommendation) -> str:
    authors = escape(", ".join(rec.book.author_names) or "unknown author")
    rid = escape(rec.book.book_id.replace(":", "-"))
    return (
        f'<article class="card" aria-labelledby="rec-{rid}">'
        f'<h3 id="rec-{rid}">{rec.rank}. {escape(rec.book.title)}</h3>'
        f'<p class="byline">by {authors}</p>'
        f'<p class="score">Fit score: {rec.score:.3f}</p>'
        f"{_signals_html(rec.explanation)}"
        f"{_sources_html(rec.explanation)}"
        f'<p class="summary">{escape(rec.explanation.summary)}</p>'
        "</article>"
    )


def _near_miss_card(miss: NearMiss) -> str:
    authors = escape(", ".join(miss.book.author_names) or "unknown author")
    rid = escape(miss.book.book_id.replace(":", "-"))
    return (
        f'<article class="card" aria-labelledby="miss-{rid}">'
        f'<h3 id="miss-{rid}">{escape(miss.book.title)}</h3>'
        f'<p class="byline">by {authors}</p>'
        f"{_signals_html(miss.explanation, heading='Why not')}"
        f"{_sources_html(miss.explanation)}"
        f'<p class="summary">{escape(miss.explanation.summary)}</p>'
        "</article>"
    )


_STYLE = """
:root {
  color-scheme: light dark;
  --paper: #fdf6fb;
  --wash: #f2e5f0;
  --plum: #7a2e63;
  --plum-dark: #542044;
  --ink: #241c22;
  --muted: #665660;
  --line: #d8bfd1;
  --white: #fffafd;
  --display: Georgia, "Times New Roman", serif;
  --body: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --utility: ui-monospace, "SFMono-Regular", Consolas, monospace;
}
* { box-sizing: border-box; }
html { color: var(--ink); background: var(--paper); scroll-behavior: smooth; }
body {
  position: relative;
  margin: 0;
  color: var(--ink);
  background-color: var(--paper);
  font-family: var(--body);
  font-size: 1rem;
  line-height: 1.6;
}
body::before {
  position: fixed;
  z-index: 8;
  inset: 0 auto 0 0;
  width: .35rem;
  background: var(--plum);
  content: "";
  pointer-events: none;
}
body > header, body > nav, main { width: min(72rem, calc(100% - 2rem)); margin-inline: auto; }
body > header { padding: clamp(2.5rem, 7vw, 6rem) 0 1.75rem; }
.kicker, .eyebrow, .shelfmark, summary, caption {
  font-family: var(--utility);
  font-size: .78rem;
  letter-spacing: .08em;
  text-transform: uppercase;
}
.kicker { color: var(--plum); font-weight: 750; margin: 0 0 .75rem; }
h1, h2, h3, h4, p { margin-top: 0; }
h1 {
  max-width: 12ch;
  margin-bottom: .75rem;
  font: 700 clamp(2.7rem, 9vw, 6.6rem)/.92 var(--display);
  letter-spacing: -.055em;
  color: var(--plum-dark);
}
h2 { font: 700 clamp(1.65rem, 4vw, 2.5rem)/1.08 var(--display); color: var(--plum-dark); }
h3 { font: 700 1.22rem/1.25 var(--display); margin-bottom: .3rem; }
h4 { margin-bottom: .25rem; }
.intro { max-width: 62ch; font-size: 1.08rem; color: var(--muted); }
a { color: var(--plum-dark); text-underline-offset: .18em; }
a:hover { text-decoration-thickness: .16em; }
a:focus-visible, input:focus-visible, button:focus-visible, summary:focus-visible {
  outline: .2rem solid var(--plum);
  outline-offset: .2rem;
}
.skip { position: fixed; z-index: 10; left: 1rem; top: -6rem; padding: .75rem 1rem;
  background: var(--ink); color: var(--white); }
.skip:focus { top: 1rem; }
.section-nav {
  position: sticky;
  z-index: 5;
  top: 0;
  padding: .5rem 0;
  background-color: var(--paper);
  border-block: 1px solid var(--line);
}
.section-nav ul {
  display: flex; gap: .35rem; margin: 0; padding: 0; list-style: none; overflow-x: auto;
}
.section-nav a {
  display: inline-flex; align-items: center; min-height: 44px; padding: .45rem .8rem;
  border-radius: 999px; white-space: nowrap; font-weight: 700; text-decoration: none;
}
.section-nav a:hover { background: var(--wash); }
main { padding: 2.5rem 0 5rem; }
.home-section { padding: clamp(2.5rem, 7vw, 5.5rem) 0; border-bottom: 1px solid var(--line); }
.section-heading { display: grid; grid-template-columns: minmax(0, 1fr) minmax(14rem, 28rem);
  gap: 1rem 3rem; align-items: end; margin-bottom: 1.5rem; }
.section-heading > * { margin-bottom: 0; }
.section-heading p { color: var(--muted); }
ul.books { display: grid; gap: 1rem; padding: 0; list-style: none; }
.reading {
  display: grid;
  grid-template-columns: 3.25rem minmax(0, 1fr);
  min-height: 10rem;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: .7rem;
  background: var(--white);
  box-shadow: 0 .3rem 1.2rem rgb(84 32 68 / .07);
}
.shelfmark {
  display: flex; justify-content: center; padding: 1rem .3rem;
  color: var(--white); background: var(--plum);
}
.shelfmark span { writing-mode: vertical-rl; transform: rotate(180deg); }
.reading-copy { min-width: 0; padding: 1.15rem clamp(1rem, 3vw, 1.6rem); }
.byline, .progress-label, .themes, .summary { color: var(--muted); }
.byline, .progress-label { margin-bottom: .45rem; }
progress {
  display: block; width: 100%; height: .55rem; margin: .85rem 0 1rem;
  border: 0; border-radius: 999px; overflow: hidden; background: var(--wash);
}
progress::-webkit-progress-bar { background: var(--wash); }
progress::-webkit-progress-value { background: var(--plum); }
progress::-moz-progress-bar { background: var(--plum); }
.tag { display: inline-block; margin: .2rem .15rem .2rem 0; padding: .08rem .5rem;
  border: 1px solid var(--line); border-radius: 999px; color: var(--plum-dark);
  background: var(--paper); white-space: nowrap; }
.tag::before { content: "# "; }
.recommendation-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
.card {
  min-width: 0;
  padding: clamp(1.2rem, 3vw, 1.8rem);
  border: 1px solid var(--line);
  border-radius: .7rem;
  background: var(--white);
}
.card a, .card li, .local-citation { overflow-wrap: anywhere; }
.card h3 { padding-right: 2rem; }
.score { display: inline-block; padding: .15rem .55rem; border-radius: .25rem;
  color: var(--white); background: var(--plum); font-family: var(--utility); font-size: .82rem; }
.card ul { padding-left: 1.2rem; }
.next-shelves { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1.5rem; }
.shelf-block { min-width: 0; padding: 1rem; overflow-x: auto; border: 1px solid var(--line);
  border-radius: .7rem; }
.disclosures { display: grid; gap: .75rem; }
details { border: 1px solid var(--line); border-radius: .7rem; background: var(--white); }
summary {
  min-height: 44px; padding: 1rem 1.2rem; color: var(--plum-dark);
  cursor: pointer; font-weight: 750;
}
.details-inner { padding: .4rem 1.2rem 1.5rem; overflow-x: auto; }
.details-inner > :first-child { margin-top: .5rem; }
.browse-form {
  display: flex; align-items: end; gap: .65rem; max-width: 45rem; margin-bottom: 1.5rem;
  padding: 1rem; border-radius: .7rem; background: var(--wash);
}
.browse-form label { display: grid; flex: 1; gap: .25rem; font-weight: 700; }
input, button {
  min-height: 44px; border: 1px solid var(--plum); border-radius: .4rem;
  font: inherit;
}
input { width: 100%; padding: .55rem .7rem; color: var(--ink); background: var(--white); }
button { padding: .55rem 1rem; color: var(--white); background: var(--plum); font-weight: 750; }
.table-wrap { width: 100%; overflow-x: auto; margin: .75rem 0 1.5rem; }
table {
  width: 100%; max-width: 100%; border-collapse: collapse; color: var(--ink);
  background-color: var(--white);
}
caption {
  padding: .5rem 0; color: var(--muted); text-align: left;
  text-transform: none; letter-spacing: 0;
}
th, td {
  padding: .65rem .75rem; border-bottom: 1px solid var(--line);
  text-align: left; vertical-align: top; overflow-wrap: anywhere;
}
thead th { color: var(--plum-dark); background: var(--wash); }
.lens-warning, .status-note { padding: .75rem 1rem; border-left: .3rem solid var(--plum);
  background: var(--wash); }
@media (max-width: 48rem) {
  .section-heading, .recommendation-grid, .next-shelves {
    grid-template-columns: minmax(0, 1fr);
  }
  .section-nav ul { flex-wrap: wrap; overflow-x: visible; }
  .browse-form { align-items: stretch; flex-direction: column; }
  .browse-form button { width: 100%; }
}
@media (max-width: 24rem) {
  body > header, body > nav, main { width: min(100% - 1rem, 72rem); }
  .reading { grid-template-columns: 2.5rem minmax(0, 1fr); }
  .reading-copy, .card, .details-inner { padding-inline: .8rem; }
  th, td { padding: .55rem; }
}
@media (prefers-color-scheme: dark) {
  :root {
    --paper: #18121a;
    --wash: #2b1d29;
    --plum: #dfa0c8;
    --plum-dark: #f4cce5;
    --ink: #fff7fc;
    --muted: #dfcbd8;
    --line: #69475f;
    --white: #211821;
  }
}
@media (forced-colors: active) {
  body::before { background: Highlight; }
  a:focus-visible, input:focus-visible, button:focus-visible, summary:focus-visible {
    outline-color: Highlight;
  }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
"""


def _forecast_table(forecasts: Sequence[BookForecast]) -> str:
    if not forecasts:
        return "<p>Nothing in progress to forecast right now.</p>"
    rows = ""
    for f in forecasts:
        fc = f.forecast
        # Estimable books show an hour range (never a single number); the rest
        # honestly show no estimate, with the reason in the "Based on" column.
        estimate = f"{fc.low_hours:g}–{fc.high_hours:g} hours" if fc.estimable else "—"
        rows += (
            f'<tr><th scope="row">{escape(f.title)}</th>'
            f"<td>{escape(', '.join(f.authors) or 'unknown')}</td>"
            f"<td>{escape(estimate)}</td>"
            f"<td>{escape(fc.basis)}</td></tr>"
        )
    return (
        '<div class="table-wrap"><table><caption>Time to finish, at your recent '
        "reading pace — a range, "
        "never a single number, computed locally from your own page timing</caption>"
        '<thead><tr><th scope="col">Title</th><th scope="col">Author</th>'
        '<th scope="col">Estimate</th><th scope="col">Based on</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>"
    )


def _series_table(series_next: Sequence[SeriesNext]) -> str:
    if not series_next:
        return "<p>No series to continue right now.</p>"
    rows = "".join(
        f'<tr><th scope="row">{escape(s.title)}</th>'
        f"<td>{escape(s.series)}</td>"
        f"<td>{escape(', '.join(s.authors) or 'unknown')}</td></tr>"
        for s in series_next
    )
    return (
        "<table><caption>Unread books in series you've started</caption>"
        '<thead><tr><th scope="col">Title</th><th scope="col">Series</th>'
        f'<th scope="col">Author</th></tr></thead><tbody>{rows}</tbody></table>'
    )


def _monthly_table(wrapped: Wrapped) -> str:
    if not wrapped.monthly:
        return ""
    names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    rows = "".join(
        f'<tr><th scope="row">{names[m.month]}</th>'
        f"<td>{m.pages}</td><td>{m.hours}</td><td>{m.days_read}</td></tr>"
        for m in wrapped.monthly
    )
    return (
        f"<table><caption>Monthly reading in {wrapped.year} "
        f"(pace: {wrapped.pace_pages_per_day} pages per reading day)</caption>"
        '<thead><tr><th scope="col">Month</th><th scope="col">Pages</th>'
        '<th scope="col">Hours</th><th scope="col">Days</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )


def _goals_section(goals: Sequence[Goal]) -> str:
    if not goals:
        return ""
    rows = "".join(
        f'<tr><th scope="row">{escape(g.name)}</th>'
        f"<td>{g.current} / {g.target}</td>"
        f"<td>{g.pct:.0%}{' ✓ met' if g.met else ''}</td></tr>"
        for g in goals
    )
    return (
        "<h3>Goals</h3>"
        "<table><caption>Your reading goals (set locally, shared with no one)</caption>"
        '<thead><tr><th scope="col">Goal</th><th scope="col">Progress</th>'
        f'<th scope="col">%</th></tr></thead><tbody>{rows}</tbody></table>'
    )


def _diversity_section(report: Optional[DiversityReport]) -> str:
    """The diverse-shelf analytics: honest coverage, lenses, and provenance.

    Every figure is built only from *sourced book descriptors*; the section opens
    by saying so, and surfaces undescribed books rather than hiding them. Each
    chart ships as a real data ``<table>`` (no colour-only meaning).
    """
    if report is None or report.total_books == 0:
        return ""

    considered_label = (
        "Books considered (whole shelf — no reading history)"
        if report.shelf_fallback
        else "Books considered (reading + finished)"
    )
    coverage_rows = "".join(
        f'<tr><th scope="row">{escape(label)}</th><td>{value}</td></tr>'
        for label, value in (
            (considered_label, str(report.total_books)),
            ("With a sourced descriptor", str(report.described_books)),
            ("No sourced descriptor (unknown — not 'none')", str(report.undescribed_books)),
            ("Descriptor coverage", _pct(report.coverage_pct)),
        )
    )
    shelf_note = (
        '<p class="shelf-fallback" role="note">Nothing on this shelf carries a reading '
        "status, so these counts describe <strong>everything you own</strong>, not what "
        "you have read. Connect KOReader to see the reading view.</p>"
        if report.shelf_fallback
        else ""
    )
    coverage = (
        "<table><caption>Coverage — how much of the shelf carries a sourced "
        'descriptor</caption><thead><tr><th scope="col">Measure</th>'
        f'<th scope="col">Value</th></tr></thead><tbody>{coverage_rows}</tbody></table>'
    )

    # Lens provenance: which grouping produced the numbers below, so a renamed
    # lens in a local lenses.toml appears verbatim and a degraded config is never
    # silent (extends the tag-provenance UI to the *grouping* itself).
    lens_provenance = f"<p>Lens grouping: <strong>{escape(report.lens_source)}</strong>.</p>"
    lens_warning = (
        f'<p class="lens-warning" role="alert">Warning: {escape(report.lens_warning)}</p>'
        if report.lens_warning
        else ""
    )

    if report.dimensions:
        dim_rows = "".join(
            f'<tr><th scope="row">{escape(d.name)}</th>'
            f"<td>{d.books}</td><td>{_pct(d.pct)}</td>"
            f"<td>{escape(', '.join(d.matched_labels))}</td></tr>"
            for d in report.dimensions
        )
        dimensions = (
            f"{lens_provenance}{lens_warning}"
            "<table><caption>Representation lenses, as a share of your described "
            "books (a grouping of sourced descriptors — never an author's identity)"
            '</caption><thead><tr><th scope="col">Lens</th>'
            '<th scope="col">Books</th><th scope="col">% of described</th>'
            '<th scope="col">Sourced descriptors seen</th></tr></thead>'
            f"<tbody>{dim_rows}</tbody></table>"
        )
    else:
        dimensions = (
            f"{lens_provenance}{lens_warning}<p>No grouped representation lenses populated yet.</p>"
        )

    prov_rows = "".join(
        f'<tr><th scope="row">{escape(kind)}</th><td>{count}</td></tr>'
        for kind, count in report.source_provenance
    )
    provenance = (
        "<table><caption>Where these descriptors came from (count of sourced tags "
        'by source)</caption><thead><tr><th scope="col">Source</th>'
        f'<th scope="col">Descriptors</th></tr></thead><tbody>{prov_rows}</tbody></table>'
        if prov_rows
        else "<p>No descriptor provenance recorded yet.</p>"
    )

    # R4: every diverse-shelf descriptor with the source that asserted it + when.
    # The sensitive marker is text (never colour-only) for the a11y contract.
    if report.descriptor_provenance:
        desc_rows = "".join(
            f'<tr><th scope="row">{escape(d.label)}'
            f"{' (sensitive)' if d.sensitive else ''}</th>"
            f"<td>{d.books}</td>"
            f"<td>{escape(', '.join(d.source_kinds) or '—')}</td>"
            f"<td>{escape(d.latest_retrieved_at or '—')}</td></tr>"
            for d in report.descriptor_provenance
        )
        descriptor_table = (
            "<table><caption>Per-descriptor provenance — every diverse-shelf tag, the "
            "source that asserted it, and when it was fetched (sourced, never inferred)"
            '</caption><thead><tr><th scope="col">Descriptor</th>'
            '<th scope="col">Books</th><th scope="col">Source(s)</th>'
            '<th scope="col">Retrieved</th></tr></thead>'
            f"<tbody>{desc_rows}</tbody></table>"
        )
    else:
        descriptor_table = "<p>No per-descriptor provenance recorded yet.</p>"

    # `hide_sensitive` records that the toggle was *asked for*; only
    # `redacted_descriptor_count` records that anything was actually removed.
    # Claiming descriptors are hidden while listing them is worse than saying
    # nothing, so the assurance is keyed off the count. The wording describes the
    # mechanism ("on your sensitive list") rather than the outcome
    # ("identity-adjacent"): the code cannot know a label is identity-adjacent,
    # only that it is on a list.
    if report.hide_sensitive and report.redacted_descriptor_count:
        count = report.redacted_descriptor_count
        plural = "descriptor" if count == 1 else "descriptors"
        privacy_note = (
            f"<p><strong>Privacy:</strong> {count} sourced {plural} on your sensitive "
            "list are aggregated into a single row here, and held back everywhere else "
            "on this page — the per-book theme chips, the library table, and the theme "
            "mix. Lens names and their counts stay visible, and share cards composed "
            "while this is on leave them out too. Unset the privacy toggle to see every "
            "sourced descriptor individually.</p>"
        )
    elif report.hide_sensitive:
        privacy_note = (
            "<p><strong>Privacy:</strong> the privacy toggle is on, and nothing on this "
            "shelf matched your sensitive list, so nothing has been aggregated — every "
            "descriptor below is shown individually.</p>"
        )
    else:
        privacy_note = (
            "<p>Every sourced descriptor is shown individually below. To aggregate the "
            "identity-adjacent ones (handy when screen-sharing a queer/trans reading "
            "history), set <code>STACKS_HIDE_SENSITIVE=1</code> or load "
            "<code>?hide_sensitive=1</code>.</p>"
        )

    return (
        "<h3>Reading diversity</h3>"
        "<p>Built <strong>only</strong> from sourced descriptors of the books "
        "themselves — Calibre tags, OpenLibrary subjects, and curated lists. We "
        "never infer an author's identity and never auto-label a person; a book "
        "with no sourced descriptor is reported as unknown, not as &ldquo;not "
        "diverse&rdquo;.</p>"
        f"{shelf_note}{privacy_note}{coverage}{dimensions}{provenance}{descriptor_table}"
    )


def _authored_lists_section(lists: Sequence[CuratedList]) -> str:
    """Read-only "Your lists" section: name, citation, retrieved date, book count.

    Authoring itself is CLI-only (``stacks lists new/add/export``, manual
    export, no network) — this section only ever displays what is already on
    disk; it never edits, imports, or sends anything.
    """
    if not lists:
        return (
            "<h3>Your lists</h3>"
            "<p>No authored lists yet — create one with "
            "<code>stacks lists new</code> and it will show up here.</p>"
        )
    rows = "".join(
        f'<tr><th scope="row">{escape(lst.name)}</th>'
        f"<td>{escape(lst.citation)}</td>"
        f"<td>{len(lst.book_ids)}</td>"
        f"<td>{escape(lst.retrieved_at)}</td></tr>"
        for lst in lists
    )
    return (
        "<h3>Your lists</h3>"
        "<p>Cited lists you've authored with <code>stacks lists</code> — "
        "read-only here. Export stays a manual, local step "
        "(<code>stacks lists export</code>); nothing here is sent anywhere.</p>"
        "<table><caption>Your authored curated lists</caption>"
        '<thead><tr><th scope="col">Name</th><th scope="col">Citation</th>'
        '<th scope="col">Books</th><th scope="col">Retrieved</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )


def _library_row_themes(state: ReadingState, hidden: frozenset[str]) -> str:
    """The library table's themes cell, minus anything being withheld."""
    shown, withheld = _split_labels([t.label for t in state.theme_tags], hidden)
    if withheld:
        shown = [*shown, _withheld_note(withheld)]
    return ", ".join(shown) or "—"


def _library_table(library: Sequence[ReadingState], hidden: frozenset[str] = frozenset()) -> str:
    if not library:
        return "<p>Your library is empty.</p>"
    rows = "".join(
        f'<tr><th scope="row">{escape(s.title)}</th>'
        f"<td>{escape(', '.join(s.authors) or 'unknown')}</td>"
        f"<td>{escape(str(s.status))}</td>"
        f"<td>{escape(_library_row_themes(s, hidden))}</td></tr>"
        for s in library
    )
    return (
        '<div class="table-wrap"><table id="lib-table"><caption>Your library — browse by '
        "reading the rows, or filter with the form above</caption><thead><tr>"
        '<th scope="col">Title</th><th scope="col">Author</th>'
        '<th scope="col">Status</th><th scope="col">Themes (sourced)</th>'
        f"</tr></thead><tbody>{rows}</tbody></table></div>"
    )


# Progressive enhancement: filters the library table client-side. The page is
# fully usable without it (every row is server-rendered; /browse filters too).
# Deliberately contains no "<" so the static a11y parser reads it cleanly.
_FILTER_JS = (
    "<script>"
    "(function(){"
    "var i=document.getElementById('lib-filter');"
    "var t=document.getElementById('lib-table');"
    "var s=document.getElementById('lib-filter-status');"
    "if(!i||!t||!s||!t.tBodies.length){return;}"
    "if(s.dataset.complete!=='true'){return;}"
    "i.addEventListener('input',function(){"
    "var q=i.value.toLowerCase();var rows=t.tBodies[0].rows;var shown=0;"
    "for(var r=0;r!==rows.length;r++){"
    "var hay=rows[r].textContent.toLowerCase();"
    "rows[r].hidden=(q!==''&&hay.indexOf(q)===-1);"
    "if(!rows[r].hidden){shown++;}"
    "}"
    "s.textContent='Showing '+shown+' of '+rows.length+' books.';"
    "});"
    "})();"
    "</script>"
)


def _utc_timestamp(value: Optional[int], *, empty: str = "never") -> str:
    if value is None or value <= 0:
        return empty
    return datetime.datetime.fromtimestamp(value, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _catalog_status_section(status: CatalogPoolStatus) -> str:
    """Explain catalog consent, freshness, and last-good fallback in plain text."""
    # Name the subject of the sentence. "No public catalog requests are
    # permitted" sat on the same page as live openlibrary.org citation links,
    # which reads as a contradiction until you work out that the row is about
    # requests *this instance* makes, not links you may choose to follow.
    mode = (
        "Off — this instance makes no public catalog requests"
        if status.outbound_mode != "public-metadata"
        else "Public metadata — explicitly enabled"
    )
    state = {
        "off": "Networking off; any candidates shown are already stored locally.",
        "unconfigured": "Enabled, but no broad subjects or public lists are configured.",
        "fresh": "The most recent configured-source refresh succeeded.",
        "degraded": "A source failed; last-good candidates are retained where available.",
    }.get(status.state, status.state)
    rows = (
        f'<tr><th scope="row">Outbound mode</th><td>{escape(mode)}</td></tr>'
        f'<tr><th scope="row">Pool state</th><td>{escape(state)}</td></tr>'
        f'<tr><th scope="row">Candidates stored locally</th>'
        f"<td>{status.candidate_count}</td></tr>"
        f'<tr><th scope="row">Last attempted</th>'
        f"<td>{escape(_utc_timestamp(status.attempted_at))}</td></tr>"
    )
    source_table = ""
    if status.sources:
        source_rows = []
        for source in status.sources:
            if source.status == "error":
                fallback = (
                    "Last attempt failed; using last-good candidates."
                    if source.candidate_count
                    else "Last attempt failed; no candidates are available."
                )
                note = f"{fallback} {source.error}".strip()
            else:
                note = "Last attempt succeeded."
            source_rows.append(
                f'<tr><th scope="row">{escape(source.source_id)}</th>'
                f"<td>{escape(source.status)}</td>"
                f"<td>{escape(_utc_timestamp(source.fetched_at))}</td>"
                f"<td>{source.candidate_count}</td><td>{escape(note)}</td></tr>"
            )
        source_table = (
            "<table><caption>Configured public catalog sources and their last-good "
            'state</caption><thead><tr><th scope="col">Source</th>'
            '<th scope="col">Latest attempt</th><th scope="col">Last success</th>'
            '<th scope="col">Candidates</th><th scope="col">Note</th></tr></thead>'
            f"<tbody>{''.join(source_rows)}</tbody></table>"
        )
    return (
        "<h3>Recommendation sources</h3>"
        "<p>Catalog requests use only broad subjects or explicit public lists. "
        "They are never generated from reading history, authors, or taste weights.</p>"
        "<table><caption>Catalog networking and candidate-pool status</caption>"
        '<thead><tr><th scope="col">Measure</th><th scope="col">Value</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>{source_table}"
    )


def _data_status_section(refreshed_at: Optional[int] = None, stale: bool = False) -> str:
    """Say what the dashboard knows and how old it is — never silently stale.

    Degrades gracefully: per-source ``RefreshResult`` rows land with FIX-08;
    until then this shows the one honest thing the store already persists —
    the ``refreshed_at`` stamp — plus a text (not colour-only) staleness banner.
    """
    if refreshed_at is None:
        as_of = "never refreshed — run `stacks refresh`"
    else:
        as_of = _utc_timestamp(refreshed_at)
    banner = (
        '<p class="status-note" role="status">Stale: this data is more than the '
        "freshness threshold old — run <code>stacks refresh</code> to update it.</p>"
        if stale
        else ""
    )
    rows = f'<tr><th scope="row">Data as of</th><td>{escape(as_of)}</td></tr>'
    return (
        f"{banner}"
        "<h3>Data status</h3>"
        "<table><caption>How current the data on this page is</caption>"
        '<thead><tr><th scope="col">Measure</th><th scope="col">Value</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )


def render_dashboard(
    currently_reading: Sequence[ReadingState],
    finished: Sequence[ReadingState],
    stats: ReadingStats,
    wrapped: Wrapped,
    recommendations: Sequence[Recommendation],
    *,
    near_misses: Sequence[NearMiss] = (),
    forecasts: Sequence[BookForecast] = (),
    series_next: Sequence[SeriesNext] = (),
    to_read: Sequence[ReadingState] = (),
    library: Sequence[ReadingState] = (),
    goals: Sequence[Goal] = (),
    diversity: Optional[DiversityReport] = None,
    authored_lists: Sequence[CuratedList] = (),
    user: str = "demo",
    refreshed_at: Optional[int] = None,
    stale: bool = False,
    catalog_status: Optional[CatalogPoolStatus] = None,
    browse_query: str = "",
    browse_theme: str = "",
    browse_author: str = "",
    browse_series: str = "",
    browse_status: str = "",
) -> str:
    """Render the complete, accessible dashboard document."""
    catalog = catalog_status or CatalogPoolStatus()
    # The privacy toggle governs the whole document, not only the diversity
    # panel. Per-book chips and the library table are *more* revealing than the
    # aggregated breakdown, because they name the title alongside the
    # descriptor; the theme mix restates the same vocabulary a second time.
    # Redacting one section while three others publish it is not a toggle.
    hidden_descriptors: frozenset[str] = (
        diversity.sensitive_descriptors
        if diversity is not None and diversity.hide_sensitive
        else frozenset()
    )
    reading_items = "".join(_reading_item(s, hidden_descriptors) for s in currently_reading) or (
        "<li>Nothing in progress right now.</li>"
    )
    finished_items = "".join(_reading_item(s, hidden_descriptors) for s in finished[:10]) or (
        "<li>No finished books recorded yet.</li>"
    )
    if recommendations:
        rec_cards = "".join(_rec_card(r) for r in recommendations)
    elif catalog.state == "off" and catalog.candidate_count == 0:
        rec_cards = (
            '<p class="empty-state">No recommendation candidates are stored yet. '
            "Catalog networking is off; explicitly configure broad public-metadata "
            "sources and run <code>stacks refresh</code> to populate this shelf.</p>"
        )
    else:
        rec_cards = (
            '<p class="empty-state">No recommendations fit yet. Check source status '
            "below, then read or tag a few books to provide local matching signals.</p>"
        )
    near_miss_cards = "".join(_near_miss_card(m) for m in near_misses)
    near_miss_section = (
        '<details class="near-misses"><summary>Why not others?</summary>'
        '<div class="details-inner">'
        "<p>Close candidates that didn't make the shelf, ranked and explained — "
        "the same sourced accounting the picks above get, applied to what "
        "fell short.</p>"
        f'<div class="recommendation-grid">{near_miss_cards}</div></div></details>'
        if near_miss_cards
        else ""
    )
    tbr_items = "".join(_reading_item(s, hidden_descriptors) for s in to_read[:10]) or (
        "<li>Nothing on your to-read shelf.</li>"
    )
    library_preview = library[:LIBRARY_PREVIEW_LIMIT]
    library_complete = len(library_preview) == len(library)
    library_status = (
        f"Showing {len(library)} books."
        if library_complete
        else f"Showing the first {len(library_preview)} of {len(library)} books. "
        "Submit the search form to filter the full library."
    )
    structured_filters = "".join(
        f'<input type="hidden" name="{name}" value="{escape(value)}">'
        for name, value in (
            ("theme", browse_theme),
            ("author", browse_author),
            ("series", browse_series),
            ("status", browse_status),
        )
        if value
    )
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Queer the Stacks — your reading dashboard</title>"
        f"<style>{_STYLE}</style></head><body>"
        '<a class="skip" href="#main">Skip to your reading dashboard</a>'
        '<header><p class="kicker">Private circulation desk · '
        f"{escape(user)}</p><h1>Queer the Stacks</h1>"
        f'<p class="intro">Your private reading dashboard, {escape(user)} — unified read-only from '
        "Calibre and KOReader, with recommendations from ethical, non-gatekept "
        "catalogs. Reading data never leaves this instance.</p></header>"
        '<nav class="section-nav" aria-label="Dashboard sections"><ul>'
        '<li><a href="#continue">Continue</a></li>'
        '<li><a href="#next">Next</a></li>'
        '<li><a href="#finished">Finished</a></li>'
        '<li><a href="#browse">Browse</a></li>'
        '<li><a href="#record">Reading record</a></li>'
        "</ul></nav>"
        '<main id="main">'
        '<section id="continue" class="home-section">'
        '<div class="section-heading"><h2>Continue reading</h2>'
        "<p>Books checked out to you now, joined across Calibre and KOReader.</p></div>"
        '<p class="eyebrow">Currently reading</p>'
        f'<ul class="books">{reading_items}</ul>'
        "<h3>Time to finish</h3>"
        f"{_forecast_table(forecasts)}"
        "</section>"
        '<section id="next" class="home-section">'
        '<div class="section-heading"><h2>What next</h2>'
        "<p>Explained possibilities for the next open slot on your reading shelf.</p></div>"
        "<h3>Recommended for you</h3>"
        "<p>Every pick shows why it surfaced and the source it came from. A "
        "citation that links out is a page you can open yourself; following one "
        "is a request your browser makes to that catalog, never one this "
        "instance makes on your behalf, and it carries no referrer.</p>"
        f'<div class="recommendation-grid">{rec_cards}</div>'
        f"{near_miss_section}"
        '<div class="next-shelves"><div class="shelf-block"><h3>Up next in your series</h3>'
        f"{_series_table(series_next)}</div>"
        '<div class="shelf-block"><h3>To-read shelf</h3>'
        f'<ul class="books">{tbr_items}</ul></div></div>'
        "</section>"
        '<section id="finished" class="home-section">'
        '<div class="section-heading"><h2>Recently finished</h2>'
        "<p>Your latest returns, kept close enough to revisit.</p></div>"
        f'<ul class="books">{finished_items}</ul>'
        "</section>"
        '<section id="browse" class="home-section">'
        '<div class="section-heading"><h2>Browse your library</h2>'
        "<p>Search the full catalogue by title, author, status, or sourced theme.</p></div>"
        '<form class="browse-form" action="/browse" method="get" role="search">'
        f"{structured_filters}"
        '<label for="lib-filter">Find a book'
        '<input id="lib-filter" name="q" type="search" autocomplete="off" '
        f'placeholder="Title, author, status, or theme" value="{escape(browse_query)}"></label>'
        '<button type="submit">Search library</button></form>'
        f'<p id="lib-filter-status" role="status" aria-live="polite" '
        f'data-complete="{str(library_complete).lower()}">{escape(library_status)}</p>'
        f"{_library_table(library_preview, hidden_descriptors)}"
        f"{_FILTER_JS}"
        "</section>"
        '<section id="record" class="home-section">'
        '<div class="section-heading"><h2>Reading record</h2>'
        "<p>Your patterns, provenance, lists, and data health—available when you need them.</p>"
        '</div><div class="disclosures">'
        '<details><summary>Stats, goals &amp; yearly history</summary><div class="details-inner">'
        "<h3>Reading stats</h3>"
        f"{_stats_table(stats)}{_theme_mix_table(stats, hidden_descriptors)}"
        f"<h3>Reading Wrapped {wrapped.year}</h3>"
        f"<p>{wrapped.books_finished} books finished · {wrapped.read_time_hours} hours "
        f"read in {wrapped.year} · {wrapped.days_read} reading days — computed "
        "locally, shared with no one.</p>"
        f"{_wrapped_table(wrapped)}{_monthly_table(wrapped)}{_goals_section(goals)}"
        '<p><a href="/share">Make a share card for Bookwyrm or Mastodon</a> — '
        "composed locally; nothing is posted until you copy and share it yourself.</p>"
        "</div></details>"
        f"<details{' open' if diversity and diversity.lens_warning else ''}>"
        "<summary>Diversity &amp; descriptor provenance"
        f"{' — attention needed' if diversity and diversity.lens_warning else ''}</summary>"
        f'<div class="details-inner">{_diversity_section(diversity)}</div></details>'
        '<details><summary>Your curated lists</summary><div class="details-inner">'
        f"{_authored_lists_section(authored_lists)}"
        "</div></details>"
        f'<details class="source-status"'
        f"{' open' if stale or catalog.state == 'degraded' else ''}>"
        "<summary>Data &amp; source status"
        f"{' — attention needed' if stale or catalog.state == 'degraded' else ''}</summary>"
        '<div class="details-inner">'
        f"{_data_status_section(refreshed_at, stale)}"
        f"{_catalog_status_section(catalog)}"
        "</div></details></div></section>"
        "</main></body></html>"
    )
