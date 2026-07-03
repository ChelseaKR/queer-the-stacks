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
from typing import Optional

from ingest.models import ReadingState, Recommendation

from app.diversity import DiversityReport
from app.goals import Goal
from app.shelf import SeriesNext
from app.stats import ReadingStats
from app.wrapped import Wrapped


def _pct(value: float) -> str:
    return f"{value:.0%}"


def _theme_chips(state: ReadingState) -> str:
    if not state.theme_tags:
        return '<p class="themes">Themes: none recorded.</p>'
    chips = " ".join(f'<span class="tag">{escape(t.label)}</span>' for t in state.theme_tags)
    return f'<p class="themes">Themes: {chips}</p>'


def _reading_item(state: ReadingState) -> str:
    authors = escape(", ".join(state.authors) or "unknown author")
    device = escape(state.latest_device or "—")
    return (
        '<li class="reading">'
        f"<h3>{escape(state.title)}</h3>"
        f'<p class="byline">by {authors}</p>'
        f'<p class="progress">Progress: {_pct(state.percent_complete)} '
        f"· last on {device}</p>"
        f"{_theme_chips(state)}"
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


def _theme_mix_table(stats: ReadingStats) -> str:
    if not stats.theme_mix:
        return "<p>No sourced themes recorded yet.</p>"
    rows = "".join(
        f'<tr><th scope="row">{escape(label)}</th><td>{count}</td></tr>'
        for label, count in stats.theme_mix
    )
    return (
        "<table><caption>Theme &amp; genre mix, from sourced tags only"
        '</caption><thead><tr><th scope="col">Theme</th>'
        f'<th scope="col">Books</th></tr></thead><tbody>{rows}</tbody></table>'
    )


def _wrapped_table(wrapped: Wrapped) -> str:
    standouts = "".join(
        f'<tr><th scope="row">{escape(r.title)}</th>'
        f"<td>{escape(', '.join(r.authors) or 'unknown')}</td>"
        f"<td>{r.read_time_hours}</td></tr>"
        for r in wrapped.standout_reads
    )
    if not standouts:
        standouts = '<tr><td colspan="3">No finished books recorded this year.</td></tr>'
    return (
        f"<table><caption>Standout reads of {wrapped.year} by time spent"
        '</caption><thead><tr><th scope="col">Title</th>'
        '<th scope="col">Author</th><th scope="col">Hours</th></tr></thead>'
        f"<tbody>{standouts}</tbody></table>"
    )


def _sources_html(rec: Recommendation) -> str:
    items = "".join(
        f"<li>{escape(str(s.kind))}: "
        f'<a href="{escape(_as_url(s.citation))}">{escape(s.citation)}</a> '
        f'<span class="retrieved">(retrieved {escape(s.retrieved_at)})</span></li>'
        for s in rec.explanation.sources
    )
    return f"<h4>Sources</h4><ul>{items}</ul>"


def _as_url(citation: str) -> str:
    """Make a non-URL citation (e.g. ``curated-list:…``) a safe in-page anchor."""
    if citation.startswith(("http://", "https://")):
        return citation
    return f"#source-{citation.replace(':', '-').replace(' ', '-')}"


def _signals_html(rec: Recommendation) -> str:
    items = "".join(
        f"<li>{escape(s.kind)}: {escape(s.detail)}</li>" for s in rec.explanation.signals
    )
    return f"<h4>Why recommended</h4><ul>{items}</ul>"


def _rec_card(rec: Recommendation) -> str:
    authors = escape(", ".join(rec.book.author_names) or "unknown author")
    rid = escape(rec.book.book_id.replace(":", "-"))
    return (
        f'<article class="card" aria-labelledby="rec-{rid}">'
        f'<h3 id="rec-{rid}">{rec.rank}. {escape(rec.book.title)}</h3>'
        f'<p class="byline">by {authors}</p>'
        f'<p class="score">Fit score: {rec.score:.3f}</p>'
        f"{_signals_html(rec)}"
        f"{_sources_html(rec)}"
        f'<p class="summary">{escape(rec.explanation.summary)}</p>'
        "</article>"
    )


def _rec_table(recs: Sequence[Recommendation]) -> str:
    rows = "".join(
        f"<tr><td>{r.rank}</td>"
        f'<th scope="row">{escape(r.book.title)}</th>'
        f"<td>{escape(', '.join(r.book.author_names) or 'unknown')}</td>"
        f"<td>{r.score:.3f}</td></tr>"
        for r in recs
    )
    return (
        "<table><caption>Recommendation fit scores (data-table equivalent of the cards)"
        '</caption><thead><tr><th scope="col">Rank</th>'
        '<th scope="col">Title</th><th scope="col">Author</th>'
        f'<th scope="col">Fit</th></tr></thead><tbody>{rows}</tbody></table>'
    )


_STYLE = """
:root { color-scheme: light dark; }
/* Explicit fg/bg (system Canvas/CanvasText, not just the color-scheme hint) so
   every element inherits a guaranteed-AA-contrast pair in both light and dark —
   without this, unstyled table cells can inherit mismatched UA default colors
   in some browsers/OSes and fail the axe color-contrast check (FIX 2026-07-05,
   closes the pa11y-graduation blocker — see docs/ROADMAP.md §7). */
html { color: CanvasText; background-color: Canvas; }
body { font-family: system-ui, sans-serif; max-width: 75ch; margin: 0 auto; padding: 1rem;
  color: inherit; background-color: inherit; }
.card, li.reading { border: 1px solid; border-radius: 8px; padding: 1rem; margin: 1rem 0;
  list-style: none; }
ul.books { padding: 0; }
.tag { border: 1px solid; border-radius: 999px; padding: 0.1rem 0.5rem; margin-right: 0.25rem;
  white-space: nowrap; }
.tag::before { content: "# "; }  /* glyph paired with text, never colour-only */
a:focus, .skip:focus { outline: 3px solid; }
.skip { position: absolute; left: -999px; }
.skip:focus { left: 1rem; top: 1rem; }
table { border-collapse: collapse; width: 100%; margin: 0.5rem 0; color: inherit;
  background-color: inherit; }
th, td { border: 1px solid; padding: 0.4rem; text-align: left; color: inherit;
  background-color: inherit; }
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
"""


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
        "<h2>Goals</h2>"
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

    coverage_rows = "".join(
        f'<tr><th scope="row">{escape(label)}</th><td>{value}</td></tr>'
        for label, value in (
            ("Books considered (reading + finished)", str(report.total_books)),
            ("With a sourced descriptor", str(report.described_books)),
            ("No sourced descriptor (unknown — not 'none')", str(report.undescribed_books)),
            ("Descriptor coverage", _pct(report.coverage_pct)),
        )
    )
    coverage = (
        "<table><caption>Coverage — how much of the shelf carries a sourced "
        'descriptor</caption><thead><tr><th scope="col">Measure</th>'
        f'<th scope="col">Value</th></tr></thead><tbody>{coverage_rows}</tbody></table>'
    )

    if report.dimensions:
        dim_rows = "".join(
            f'<tr><th scope="row">{escape(d.name)}</th>'
            f"<td>{d.books}</td><td>{_pct(d.pct)}</td>"
            f"<td>{escape(', '.join(d.matched_labels))}</td></tr>"
            for d in report.dimensions
        )
        dimensions = (
            "<table><caption>Representation lenses, as a share of your described "
            "books (a grouping of sourced descriptors — never an author's identity)"
            '</caption><thead><tr><th scope="col">Lens</th>'
            '<th scope="col">Books</th><th scope="col">% of described</th>'
            '<th scope="col">Sourced descriptors seen</th></tr></thead>'
            f"<tbody>{dim_rows}</tbody></table>"
        )
    else:
        dimensions = "<p>No grouped representation lenses populated yet.</p>"

    prov_rows = "".join(
        f'<tr><th scope="row">{escape(kind)}</th><td>{count}</td></tr>'
        for kind, count in report.source_provenance
    )
    provenance = (
        "<table><caption>Where these descriptors came from (provenance of every "
        'sourced tag)</caption><thead><tr><th scope="col">Source</th>'
        f'<th scope="col">Descriptors</th></tr></thead><tbody>{prov_rows}</tbody></table>'
        if prov_rows
        else "<p>No descriptor provenance recorded yet.</p>"
    )

    return (
        "<h2>Reading diversity</h2>"
        "<p>Built <strong>only</strong> from sourced descriptors of the books "
        "themselves — Calibre tags, OpenLibrary subjects, and curated lists. We "
        "never infer an author's identity and never auto-label a person; a book "
        "with no sourced descriptor is reported as unknown, not as &ldquo;not "
        "diverse&rdquo;.</p>"
        f"{coverage}{dimensions}{provenance}"
    )


def _library_table(library: Sequence[ReadingState]) -> str:
    if not library:
        return "<p>Your library is empty.</p>"
    rows = "".join(
        f'<tr><th scope="row">{escape(s.title)}</th>'
        f"<td>{escape(', '.join(s.authors) or 'unknown')}</td>"
        f"<td>{escape(str(s.status))}</td>"
        f"<td>{escape(', '.join(t.label for t in s.theme_tags) or '—')}</td></tr>"
        for s in library
    )
    return (
        '<table id="lib-table"><caption>Your library — browse by reading the rows, or '
        "filter via the box above (or the /browse route)</caption><thead><tr>"
        '<th scope="col">Title</th><th scope="col">Author</th>'
        '<th scope="col">Status</th><th scope="col">Themes (sourced)</th>'
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )


# Progressive enhancement: filters the library table client-side. The page is
# fully usable without it (every row is server-rendered; /browse filters too).
# Deliberately contains no "<" so the static a11y parser reads it cleanly.
_FILTER_JS = (
    "<script>"
    "(function(){"
    "var i=document.getElementById('lib-filter');"
    "var t=document.getElementById('lib-table');"
    "if(!i||!t||!t.tBodies.length){return;}"
    "i.addEventListener('input',function(){"
    "var q=i.value.toLowerCase();var rows=t.tBodies[0].rows;"
    "for(var r=0;r!==rows.length;r++){"
    "var hay=rows[r].textContent.toLowerCase();"
    "rows[r].hidden=(q!==''&&hay.indexOf(q)===-1);"
    "}});"
    "})();"
    "</script>"
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
        # datetime.utcfromtimestamp is deprecated; fromtimestamp(..., UTC) is the
        # non-deprecated equivalent and yields the identical ISO-8601 UTC string.
        as_of = datetime.datetime.fromtimestamp(refreshed_at, datetime.UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    banner = (
        '<p role="status">Stale: this data is more than the freshness threshold old — '
        "run <code>stacks refresh</code> to update it.</p>"
        if stale
        else ""
    )
    rows = f'<tr><th scope="row">Data as of</th><td>{escape(as_of)}</td></tr>'
    return (
        f"{banner}"
        "<h2>Data status</h2>"
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
    series_next: Sequence[SeriesNext] = (),
    to_read: Sequence[ReadingState] = (),
    library: Sequence[ReadingState] = (),
    goals: Sequence[Goal] = (),
    diversity: Optional[DiversityReport] = None,
    user: str = "demo",
    refreshed_at: Optional[int] = None,
    stale: bool = False,
) -> str:
    """Render the complete, accessible dashboard document."""
    reading_items = "".join(_reading_item(s) for s in currently_reading) or (
        "<li>Nothing in progress right now.</li>"
    )
    finished_items = "".join(_reading_item(s) for s in finished[:10]) or (
        "<li>No finished books recorded yet.</li>"
    )
    rec_cards = "".join(_rec_card(r) for r in recommendations) or (
        "<p>No recommendations yet — read a few books to seed your taste.</p>"
    )
    tbr_items = "".join(_reading_item(s) for s in to_read[:10]) or (
        "<li>Nothing on your to-read shelf.</li>"
    )
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Queer the Stacks — your reading dashboard</title>"
        f"<style>{_STYLE}</style></head><body>"
        '<a class="skip" href="#main">Skip to your reading dashboard</a>'
        "<header><h1>Queer the Stacks</h1>"
        f"<p>Your private reading dashboard, {escape(user)} — unified read-only from "
        "Calibre and KOReader, with recommendations from ethical, non-gatekept "
        "catalogs. Reading data never leaves this instance.</p></header>"
        '<main id="main">'
        f"{_data_status_section(refreshed_at, stale)}"
        "<h2>Currently reading</h2>"
        f'<ul class="books">{reading_items}</ul>'
        "<h2>Reading stats</h2>"
        f"{_stats_table(stats)}"
        f"{_theme_mix_table(stats)}"
        f"{_diversity_section(diversity)}"
        f"<h2>Reading Wrapped {wrapped.year}</h2>"
        f"<p>{wrapped.books_finished} books · {wrapped.read_time_hours} hours · "
        f"{wrapped.days_read} reading days — computed locally, shared with no one.</p>"
        f"{_wrapped_table(wrapped)}"
        f"{_monthly_table(wrapped)}"
        f"{_goals_section(goals)}"
        '<p><a href="/share">Make a share card for Bookwyrm or Mastodon</a> — '
        "composed locally; nothing is posted until you copy and share it yourself.</p>"
        "<h2>Up next in your series</h2>"
        f"{_series_table(series_next)}"
        "<h2>To-read shelf</h2>"
        f'<ul class="books">{tbr_items}</ul>'
        "<h2>Recommended for you</h2>"
        "<p>Every pick shows why it surfaced and the source it came from.</p>"
        f"{_rec_table(recommendations)}"
        f"{rec_cards}"
        "<h2>Recently finished</h2>"
        f'<ul class="books">{finished_items}</ul>'
        "<h2>Browse your library</h2>"
        '<p><label for="lib-filter">Filter the table below '
        "(works without JavaScript via the /browse route):</label> "
        '<input id="lib-filter" type="text" autocomplete="off" '
        'placeholder="type a title, author, or theme"></p>'
        f"{_library_table(library)}"
        f"{_FILTER_JS}"
        "</main></body></html>"
    )
