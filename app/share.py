"""Shareable cards for Bookwyrm / Mastodon — generated locally, never auto-sent.

Privacy posture (hard guardrail): **nothing leaves this instance without an
explicit human action.** This module only *composes* postable text + an
accessible card and (optionally) a self-contained SVG image. It performs **no
network access at all** — there is no posting client, no fediverse API call, no
egress (the no-egress test pins this: network may only live in the kosync and
catalog clients). The reader copies the text or saves the image and posts it
themselves, on their own instance, by hand.

What a card exposes is deliberately minimal and already on the reader's own
auth-gated dashboard: aggregate counts (books / pages / hours), a year, and —
for a finished-book card — a title, author, and the book's *sourced* theme
descriptors (never an inferred identity, never an author label). No device
names, no timestamps, no reading history, no streak calendar.

The privacy toggle reaches here too. A card is composed to be copied and posted
by hand, which makes its descriptors the ones most likely to end up published,
so a card assembled while the toggle is on omits the descriptors the toggle is
holding back. Nothing is hidden from the reader by this: the card on screen is
exactly the card they would post, and unsetting the toggle restores the full set.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from ingest.models import ReadingState

from app.wrapped import Wrapped

#: Mastodon's default per-post limit; Bookwyrm is comparable. The composed text
#: is kept well under this so it posts cleanly without truncation.
MAX_POST_CHARS = 500

# --- Share-card SVG palette ---------------------------------------------------
# Named (not inline-literal) so a test can assert WCAG AA contrast against the
# background — see tests/test_share.py::test_share_svg_palette_meets_aa and
# app/color_contrast.py. Body text is normal-size (>=4.5:1 required); the
# heading/border color is only ever used at large text sizes (>=18pt / 44px
# and 26px here), so it only needs the large-text AA threshold (>=3.0:1).
SVG_BG = "#fdf6fb"
SVG_BORDER = "#7a2e63"
SVG_HEADING = "#7a2e63"
SVG_BODY = "#222"

#: Longest a card title is rendered before truncation, so the heading never
#: overflows the fixed-width SVG canvas.
MAX_SVG_TITLE_CHARS = 60

#: The disclosure carried *inside* a fixture-sourced card — into its body, its
#: alt text, its SVG, and the post text the reader pastes into Bookwyrm.
#:
#: Short on purpose. The dashboard's banner (``app.render.FIXTURE_STATES_NOTICE``)
#: can afford four sentences because it stays on the page; this line has to
#: survive being copied into a 500-character post, so it says the one thing that
#: stops a fixture card being read as a real year. Per-surface wording, like
#: ``app.opds.FIXTURE_STATES_SUBTITLE``.
FIXTURE_CARD_LINE = "Demo world: fixture books, not a real library."

#: The page-level banner on ``/share``. Rendered assertively (``role="alert"``)
#: like the dashboard's, because the page's own header otherwise tells the reader
#: these cards were composed "from your own dashboard" — true of the composition,
#: false of the numbers, and this is the one surface built to be posted publicly.
#: No apostrophes or angle brackets, so the constant survives ``html.escape``
#: unchanged and a test can assert it appears verbatim in the page — the same
#: idiom the dashboard notices use.
FIXTURE_PAGE_NOTICE = (
    "These cards describe the built-in demo world, not your reading. The books, "
    "counts, and hours below came from fixture data, so posting one would publish "
    "demo numbers as your own reading. Run stacks refresh without STACKS_DEMO=1 "
    "to compose cards from your own libraries."
)

#: Stated positively on a real page, so "no banner" is a claim the page makes
#: rather than an absence the reader has to infer. Same vocabulary as the
#: dashboard's data-status rows.
CARD_SOURCE_REAL = "your configured libraries"
CARD_SOURCE_FIXTURE = "built-in demo world (fixture books)"


@dataclass(frozen=True)
class ShareCard:
    """A self-contained, postable card. Pure data — rendered, never transmitted."""

    kind: str  # "year" | "finished"
    title: str
    lines: tuple[str, ...]  # body lines, already human-readable
    hashtags: tuple[str, ...]
    #: This card's numbers came from the built-in demo world. A card is composed
    #: to be *posted*, so the disclosure has to travel with it: a reader who
    #: saves the SVG or copies the post text has left the page and its banner
    #: behind. Rendered from this flag at every emission point below rather than
    #: baked into ``lines``, so the flag and the disclosure cannot disagree.
    fixture: bool = False

    @property
    def body_lines(self) -> tuple[str, ...]:
        """The body as rendered — fixture disclosure first, when it applies."""
        return (FIXTURE_CARD_LINE, *self.lines) if self.fixture else self.lines

    @property
    def alt_text(self) -> str:
        """A complete text equivalent of the card image (for the image's alt)."""
        return f"{self.title}. " + " ".join(self.body_lines)

    def post_text(self) -> str:
        """The plain-text post the reader copies into Bookwyrm / Mastodon.

        Tags are appended on their own line. The result is capped at
        :data:`MAX_POST_CHARS` so it always fits a single post.
        """
        body = "\n".join((self.title, *self.body_lines))
        if self.hashtags:
            body = f"{body}\n\n" + " ".join(f"#{t}" for t in self.hashtags)
        if len(body) > MAX_POST_CHARS:
            body = body[: MAX_POST_CHARS - 1].rstrip() + "…"
        return body


def year_in_books_card(
    wrapped: Wrapped,
    hidden: frozenset[str] = frozenset(),
    *,
    fixture: bool = False,
) -> ShareCard:
    """A "my year in books" card from the private Wrapped (aggregates only).

    ``fixture`` marks a card built from the built-in demo world; see
    :attr:`ShareCard.fixture`.
    """
    lines = [
        f"{wrapped.books_finished} books · {wrapped.pages_read} pages · "
        f"{wrapped.read_time_hours} hours",
        f"across {wrapped.days_read} reading days",
    ]
    top = [label for label, _ in wrapped.theme_breakdown if label.lower() not in hidden][:3]
    if top:
        lines.append("Top themes: " + ", ".join(top))
    return ShareCard(
        kind="year",
        title=f"My {wrapped.year} in books",
        lines=tuple(lines),
        hashtags=("amreading", "yearinbooks", "bookwyrm"),
        fixture=fixture,
    )


def finished_book_card(
    state: ReadingState,
    hidden: frozenset[str] = frozenset(),
    *,
    fixture: bool = False,
) -> ShareCard:
    """A "just finished" card for one book, using only its sourced descriptors.

    ``hidden`` is the sensitive descriptor set when the privacy toggle is on. A
    card is composed for a reader to copy and post by hand, so the descriptors it
    carries are the ones most likely to be published — a card assembled while the
    toggle is on must not carry the descriptors the toggle exists to hold back.
    The omission is visible on the page, and unsetting the toggle restores them.

    ``fixture`` marks a card built from the built-in demo world; see
    :attr:`ShareCard.fixture`.
    """
    author = ", ".join(state.authors) or "unknown author"
    lines = [f"by {author}"]
    if state.stat and state.stat.read_time_seconds > 0:
        lines.append(f"{round(state.stat.read_time_seconds / 3600, 1)} hours well spent")
    themes = [t.label for t in state.theme_tags if t.label.strip().lower() not in hidden]
    if themes:
        lines.append("Themes (sourced): " + ", ".join(themes))
    return ShareCard(
        kind="finished",
        title=f"Just finished: {state.title}",
        lines=tuple(lines),
        hashtags=("amreading", "bookwyrm", "queerlit"),
        fixture=fixture,
    )


# --- Rendering: an accessible card + a copyable post, no network -------------

# Copy-to-clipboard, client-side only (no network). Mirrors the dashboard's
# filter script: contains no "<" so the static a11y parser reads the page
# cleanly, and the page is fully usable without it (the text sits in a readable,
# selectable region for manual copy).
_COPY_JS = (
    "<script>"
    "(function(){"
    "var bs=document.querySelectorAll('button.copy');"
    "for(var i=0;i!==bs.length;i++){"
    "(function(b){"
    "b.addEventListener('click',function(){"
    "var t=document.getElementById(b.getAttribute('data-target'));"
    "if(!t){return;}"
    "if(navigator.clipboard){navigator.clipboard.writeText(t.value);}"
    "b.textContent='Copied';"
    "});"
    "})(bs[i]);"
    "}"
    "})();"
    "</script>"
)


def render_share_svg(card: ShareCard) -> str:
    """A self-contained SVG card image (no external fonts/images → no egress).

    The SVG carries a ``<title>`` and ``role="img"`` so assistive tech reads its
    text equivalent; it is offered for download so the reader can attach it to a
    post by hand.
    """
    width, height = 1000, 420
    title = card.title
    if len(title) > MAX_SVG_TITLE_CHARS:
        title = title[: MAX_SVG_TITLE_CHARS - 1].rstrip() + "…"
    body = "".join(
        f'<text x="60" y="{180 + i * 52}" font-size="32" fill="{SVG_BODY}">{escape(line)}</text>'
        for i, line in enumerate(card.body_lines)
    )
    tags = " ".join(f"#{t}" for t in card.hashtags)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(card.alt_text)}">'
        f"<title>{escape(card.alt_text)}</title>"
        f'<rect width="{width}" height="{height}" fill="{SVG_BG}" stroke="{SVG_BORDER}" '
        'stroke-width="6"/>'
        f'<text x="60" y="110" font-size="44" font-weight="bold" fill="{SVG_HEADING}">'
        f"{escape(title)}</text>"
        f"{body}"
        f'<text x="60" y="{height - 40}" font-size="26" fill="{SVG_HEADING}">{escape(tags)}</text>'
        "</svg>"
    )


def _card_figure(card: ShareCard, index: int) -> str:
    """One card: an accessible figure + a labelled, copyable post box."""
    tid = f"post-{card.kind}-{index}"
    body_lines = "".join(f"<p>{escape(line)}</p>" for line in card.body_lines)
    tags = " ".join(f"#{escape(t)}" for t in card.hashtags)
    post = escape(card.post_text())
    return (
        '<figure class="card">'
        f"<figcaption><strong>{escape(card.title)}</strong></figcaption>"
        f"{body_lines}"
        f'<p class="tags">{tags}</p>'
        f'<p><label for="{tid}">Postable text (copy and share it yourself):</label></p>'
        f'<textarea id="{tid}" class="post" rows="6" readonly>{post}</textarea>'
        f'<p><button type="button" class="copy" data-target="{tid}">Copy post text</button></p>'
        "</figure>"
    )


_SHARE_STYLE = """
:root { color-scheme: light dark; }
/* Explicit fg/bg, same rationale as app/render.py's _STYLE: guarantees an
   AA-contrast pair in both light and dark instead of relying on unstyled UA
   defaults (FIX 2026-07-05). */
html { color: CanvasText; background-color: Canvas; }
body { font-family: system-ui, sans-serif; max-width: 75ch; margin: 0 auto; padding: 1rem;
  color: inherit; background-color: inherit; }
.card { border: 1px solid; border-radius: 8px; padding: 1rem; margin: 1rem 0; }
/* Borders in currentColor, no background swap: the banner has to stay AA in
   both light and dark without introducing a second colour pair to verify. */
.fixture-note { border: 1px solid; border-left-width: .3rem; border-radius: 4px;
  padding: .75rem 1rem; margin: 1rem 0; color: inherit; background-color: inherit; }
.card-source { color: inherit; background-color: inherit; }
textarea.post { width: 100%; font: inherit; color: inherit; background-color: inherit; }
.skip { position: absolute; left: -999px; }
.skip:focus { left: 1rem; top: 1rem; }
a:focus, button:focus, .skip:focus { outline: 3px solid; }
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
"""


def render_share_page(
    cards: tuple[ShareCard, ...],
    *,
    user: str = "demo",
    fixture_states: bool = False,
) -> str:
    """Render the full, accessible /share page. Nothing here is auto-posted.

    ``fixture_states`` is :attr:`~app.view.DashboardView.fixture_states`: the
    cards below describe the built-in demo world. Every other surface gained a
    provenance label with the fixture-provenance fix; this page — the only one
    designed to be posted publicly — must not be the exception.
    """
    figures = "".join(_card_figure(c, i) for i, c in enumerate(cards)) or (
        "<p>No share cards yet — finish a book or build up a year of reading first.</p>"
    )
    banner = (
        f'<p class="fixture-note" role="alert">{escape(FIXTURE_PAGE_NOTICE)}</p>'
        if fixture_states
        else ""
    )
    source = CARD_SOURCE_FIXTURE if fixture_states else CARD_SOURCE_REAL
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Queer the Stacks — share cards</title>"
        f"<style>{_SHARE_STYLE}</style></head><body>"
        '<a class="skip" href="#main">Skip to your share cards</a>'
        "<header><h1>Share cards</h1>"
        f"<p>Cards for {escape(user)}, composed locally from your own dashboard. "
        "<strong>Nothing is posted automatically.</strong> Copy a card's text (or "
        "save its image from <code>/share/card.svg</code>) and post it to Bookwyrm "
        "or Mastodon yourself.</p>"
        f"{banner}"
        f'<p class="card-source">Composed from: {escape(source)}.</p></header>'
        '<main id="main">'
        "<h2>Your cards</h2>"
        f"{figures}"
        f"{_COPY_JS}"
        "</main></body></html>"
    )


def build_share_cards(view: object) -> tuple[ShareCard, ...]:
    """Build the default card set from a dashboard view (year + latest finished).

    Pure: reads only the already-assembled view. Typed ``object`` to avoid an
    import cycle with :mod:`app.view`; the attributes used are part of
    :class:`~app.view.DashboardView`'s stable shape — including
    ``fixture_states``, which every card carries so the disclosure survives being
    copied or saved away from the page.
    """
    wrapped: Wrapped = view.wrapped  # type: ignore[attr-defined]
    finished: tuple[ReadingState, ...] = view.finished  # type: ignore[attr-defined]
    fixture: bool = bool(getattr(view, "fixture_states", False))
    diversity = getattr(view, "diversity", None)
    hidden: frozenset[str] = (
        diversity.sensitive_descriptors
        if diversity is not None and diversity.hide_sensitive
        else frozenset()
    )
    cards: list[ShareCard] = [year_in_books_card(wrapped, hidden, fixture=fixture)]
    if finished:
        cards.append(finished_book_card(finished[0], hidden, fixture=fixture))
    return tuple(cards)
