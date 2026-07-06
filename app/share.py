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
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from ingest.models import ReadingState

from app.wrapped import Wrapped

#: Mastodon's default per-post limit; Bookwyrm is comparable. The composed text
#: is kept well under this so it posts cleanly without truncation.
MAX_POST_CHARS = 500


@dataclass(frozen=True)
class ShareCard:
    """A self-contained, postable card. Pure data — rendered, never transmitted."""

    kind: str  # "year" | "finished"
    title: str
    lines: tuple[str, ...]  # body lines, already human-readable
    hashtags: tuple[str, ...]

    @property
    def alt_text(self) -> str:
        """A complete text equivalent of the card image (for the image's alt)."""
        return f"{self.title}. " + " ".join(self.lines)

    def post_text(self) -> str:
        """The plain-text post the reader copies into Bookwyrm / Mastodon.

        Tags are appended on their own line. The result is capped at
        :data:`MAX_POST_CHARS` so it always fits a single post.
        """
        body = "\n".join((self.title, *self.lines))
        if self.hashtags:
            body = f"{body}\n\n" + " ".join(f"#{t}" for t in self.hashtags)
        if len(body) > MAX_POST_CHARS:
            body = body[: MAX_POST_CHARS - 1].rstrip() + "…"
        return body


def year_in_books_card(wrapped: Wrapped) -> ShareCard:
    """A "my year in books" card from the private Wrapped (aggregates only)."""
    lines = [
        f"{wrapped.books_finished} books · {wrapped.pages_read} pages · "
        f"{wrapped.read_time_hours} hours",
        f"across {wrapped.days_read} reading days",
    ]
    top = [label for label, _ in wrapped.theme_breakdown[:3]]
    if top:
        lines.append("Top themes: " + ", ".join(top))
    return ShareCard(
        kind="year",
        title=f"My {wrapped.year} in books",
        lines=tuple(lines),
        hashtags=("amreading", "yearinbooks", "bookwyrm"),
    )


def finished_book_card(state: ReadingState) -> ShareCard:
    """A "just finished" card for one book, using only its sourced descriptors."""
    author = ", ".join(state.authors) or "unknown author"
    lines = [f"by {author}"]
    if state.stat and state.stat.read_time_seconds > 0:
        lines.append(f"{round(state.stat.read_time_seconds / 3600, 1)} hours well spent")
    themes = [t.label for t in state.theme_tags]
    if themes:
        lines.append("Themes (sourced): " + ", ".join(themes))
    return ShareCard(
        kind="finished",
        title=f"Just finished: {state.title}",
        lines=tuple(lines),
        hashtags=("amreading", "bookwyrm", "queerlit"),
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
    body = "".join(
        f'<text x="60" y="{180 + i * 52}" font-size="32" fill="#222">{escape(line)}</text>'
        for i, line in enumerate(card.lines)
    )
    tags = " ".join(f"#{t}" for t in card.hashtags)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(card.alt_text)}">'
        f"<title>{escape(card.alt_text)}</title>"
        f'<rect width="{width}" height="{height}" fill="#fdf6fb" stroke="#7a2e63" '
        'stroke-width="6"/>'
        f'<text x="60" y="110" font-size="44" font-weight="bold" fill="#7a2e63">'
        f"{escape(card.title)}</text>"
        f"{body}"
        f'<text x="60" y="{height - 40}" font-size="26" fill="#7a2e63">{escape(tags)}</text>'
        "</svg>"
    )


def _card_figure(card: ShareCard, index: int) -> str:
    """One card: an accessible figure + a labelled, copyable post box."""
    tid = f"post-{card.kind}-{index}"
    body_lines = "".join(f"<p>{escape(line)}</p>" for line in card.lines)
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
textarea.post { width: 100%; font: inherit; color: inherit; background-color: inherit; }
.skip { position: absolute; left: -999px; }
.skip:focus { left: 1rem; top: 1rem; }
a:focus, button:focus, .skip:focus { outline: 3px solid; }
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
"""


def render_share_page(cards: tuple[ShareCard, ...], *, user: str = "demo") -> str:
    """Render the full, accessible /share page. Nothing here is auto-posted."""
    figures = "".join(_card_figure(c, i) for i, c in enumerate(cards)) or (
        "<p>No share cards yet — finish a book or build up a year of reading first.</p>"
    )
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
        "or Mastodon yourself.</p></header>"
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
    :class:`~app.view.DashboardView`'s stable shape.
    """
    wrapped: Wrapped = view.wrapped  # type: ignore[attr-defined]
    finished: tuple[ReadingState, ...] = view.finished  # type: ignore[attr-defined]
    cards: list[ShareCard] = [year_in_books_card(wrapped)]
    if finished:
        cards.append(finished_book_card(finished[0]))
    return tuple(cards)
