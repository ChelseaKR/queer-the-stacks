"""Share cards — local-only composition, privacy-safe content, accessible page."""

from __future__ import annotations

from pathlib import Path

from app.a11y_check import check_html
from app.share import (
    MAX_POST_CHARS,
    build_share_cards,
    finished_book_card,
    render_share_page,
    render_share_svg,
    year_in_books_card,
)
from app.view import demo_view
from app.wrapped import Wrapped
from ingest.models import (
    Author,
    Book,
    ReadingStat,
    ReadingState,
    ReadingStatus,
    Source,
    SourceKind,
    ThemeTag,
)


def _wrapped() -> Wrapped:
    return Wrapped(
        year=2024,
        books_finished=12,
        pages_read=3400,
        read_time_seconds=180_000,
        days_read=140,
        theme_breakdown=(("trans", 5), ("speculative", 4), ("queer", 3)),
        standout_reads=(),
    )


def _finished_state() -> ReadingState:
    src = Source(SourceKind.OPENLIBRARY_SUBJECT, "https://openlibrary.org/subjects/trans", "x", "t")
    book = Book(
        book_id="b",
        title="Nevada",
        authors=(Author("Imogen Binnie"),),
        theme_tags=(ThemeTag("trans", src), ThemeTag("queer", src)),
    )
    stat = ReadingStat("b", "Nevada", ("Imogen Binnie",), 250, 250, 36000, 1_700_000_000, 6)
    return ReadingState(
        title="Nevada",
        authors=("Imogen Binnie",),
        status=ReadingStatus.FINISHED,
        book=book,
        stat=stat,
    )


def test_year_card_exposes_only_aggregates() -> None:
    card = year_in_books_card(_wrapped())
    text = card.post_text()
    assert "12 books" in text
    assert "2024" in card.title
    assert "Top themes: trans, speculative, queer" in text
    # Hashtags suitable for the fediverse.
    assert "#bookwyrm" in text
    # No device names, timestamps, or per-day history leak into the card.
    assert "Kobo" not in text and "last_read" not in text


def test_finished_card_uses_sourced_themes_only() -> None:
    card = finished_book_card(_finished_state())
    text = card.post_text()
    assert "Nevada" in text
    assert "Imogen Binnie" in text
    assert "Themes (sourced): trans, queer" in text


def test_post_text_capped_to_post_limit() -> None:
    w = _wrapped()
    huge = Wrapped(
        year=w.year,
        books_finished=w.books_finished,
        pages_read=w.pages_read,
        read_time_seconds=w.read_time_seconds,
        days_read=w.days_read,
        theme_breakdown=tuple((f"theme-with-a-long-name-{i}", 1) for i in range(50)),
        standout_reads=(),
    )
    card = year_in_books_card(huge)
    assert len(card.post_text()) <= MAX_POST_CHARS


def test_svg_is_self_contained_and_labelled() -> None:
    svg = render_share_svg(year_in_books_card(_wrapped()))
    assert svg.startswith("<svg")
    assert 'role="img"' in svg
    assert "<title>" in svg
    # Self-contained: no external fetch, so no egress when a client renders it.
    assert "http://www.w3.org/2000/svg" in svg  # the xmlns is the only http token
    assert "<image" not in svg and "xlink:href" not in svg


def test_share_page_is_accessible_and_says_nothing_auto_posts() -> None:
    cards = (year_in_books_card(_wrapped()), finished_book_card(_finished_state()))
    html = render_share_page(cards, user="demo")
    assert check_html(html) == []
    assert "Nothing is posted automatically" in html
    # The postable text sits in a labelled control the reader copies by hand.
    assert "Postable text" in html
    assert "<textarea" in html


def test_copy_js_has_no_angle_brackets_inside() -> None:
    from app.share import _COPY_JS

    inner = _COPY_JS.replace("<script>", "").replace("</script>", "")
    assert "<" not in inner  # keeps the static a11y parser happy


def test_share_page_escapes_user_content() -> None:
    src = Source(SourceKind.CALIBRE_TAG, "calibre:local", "2026-06-05", "x")
    book = Book(
        book_id="b",
        title="<script>alert(1)</script>",
        authors=(Author("A & B"),),
        theme_tags=(ThemeTag("queer", src),),
    )
    state = ReadingState(
        title=book.title, authors=("A & B",), status=ReadingStatus.FINISHED, book=book
    )
    html = render_share_page((finished_book_card(state),))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_build_share_cards_from_demo_view(tmp_path: Path) -> None:
    cards = build_share_cards(demo_view(tmp_path))
    kinds = {c.kind for c in cards}
    assert "year" in kinds and "finished" in kinds


def test_no_empty_cards_page_is_accessible() -> None:
    html = render_share_page(())
    assert check_html(html) == []
    assert "No share cards yet" in html
