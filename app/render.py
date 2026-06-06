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

from collections.abc import Sequence
from html import escape

from ingest.models import ReadingState, Recommendation

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
body { font-family: system-ui, sans-serif; max-width: 75ch; margin: 0 auto; padding: 1rem; }
.card, li.reading { border: 1px solid; border-radius: 8px; padding: 1rem; margin: 1rem 0;
  list-style: none; }
ul.books { padding: 0; }
.tag { border: 1px solid; border-radius: 999px; padding: 0.1rem 0.5rem; margin-right: 0.25rem;
  white-space: nowrap; }
.tag::before { content: "# "; }  /* glyph paired with text, never colour-only */
a:focus, .skip:focus { outline: 3px solid; }
.skip { position: absolute; left: -999px; }
.skip:focus { left: 1rem; top: 1rem; }
table { border-collapse: collapse; width: 100%; margin: 0.5rem 0; }
th, td { border: 1px solid; padding: 0.4rem; text-align: left; }
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
"""


def render_dashboard(
    currently_reading: Sequence[ReadingState],
    finished: Sequence[ReadingState],
    stats: ReadingStats,
    wrapped: Wrapped,
    recommendations: Sequence[Recommendation],
    *,
    user: str = "demo",
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
        "<h2>Currently reading</h2>"
        f'<ul class="books">{reading_items}</ul>'
        "<h2>Reading stats</h2>"
        f"{_stats_table(stats)}"
        f"{_theme_mix_table(stats)}"
        f"<h2>Reading Wrapped {wrapped.year}</h2>"
        f"<p>{wrapped.books_finished} books · {wrapped.read_time_hours} hours · "
        f"{wrapped.days_read} reading days — computed locally, shared with no one.</p>"
        f"{_wrapped_table(wrapped)}"
        "<h2>Recommended for you</h2>"
        "<p>Every pick shows why it surfaced and the source it came from.</p>"
        f"{_rec_table(recommendations)}"
        f"{rec_cards}"
        "<h2>Recently finished</h2>"
        f'<ul class="books">{finished_items}</ul>'
        "</main></body></html>"
    )
