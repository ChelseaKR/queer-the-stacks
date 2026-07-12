"""Command-line entry point: ``stacks eval`` and ``stacks recommend`` (demo mode).

Thin argparse glue over the library; excluded from coverage. Demo mode runs the
full offline pipeline with no real library and no network. Real mode would point
at configured Calibre/KOReader paths.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from recommender.lists import CuratedList

    from ingest.demo import Candidate
    from ingest.models import ReadingState


def _demo_states_and_candidates() -> tuple[
    list[ReadingState], tuple[Candidate, ...], tuple[CuratedList, ...]
]:
    from recommender.lists import DEMO_LISTS

    from ingest.demo import demo_candidates, demo_reading_states

    with tempfile.TemporaryDirectory(prefix="stacks-demo-") as tmp:
        states = demo_reading_states(Path(tmp))
    return states, demo_candidates(), DEMO_LISTS


def _cmd_eval(args: argparse.Namespace) -> int:
    from recommender.eval import evaluate, to_report
    from recommender.hybrid import recommend_hybrid

    states, candidates, lists = _demo_states_and_candidates()
    results = evaluate(states, list(candidates), lists=lists, k=args.k)
    top = recommend_hybrid(states, tuple(c.book for c in candidates), lists=lists, k=args.k)
    report = to_report(results, top_books=[r.book for r in top], k=args.k)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["content_beats_popularity"]:
        print("FAIL: the recommender did not beat the popularity baseline", file=sys.stderr)
        return 1
    return 0


def _cmd_recommend(args: argparse.Namespace) -> int:
    from recommender.model import recommend

    states, candidates, lists = _demo_states_and_candidates()
    recs = recommend(states, tuple(c.book for c in candidates), lists=lists, k=args.k)
    for rec in recs:
        authors = ", ".join(rec.book.author_names) or "unknown"
        print(f"{rec.rank:>2}. {rec.book.title} — {authors}  (fit {rec.score:.3f})")
        print(f"    {rec.explanation.summary}")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    from ingest.config import load_config
    from ingest.refresh import doctor
    from ingest.store import Store

    config = load_config()
    store = Store(config.store_path)
    try:
        checks = doctor(config, store)
    finally:
        store.close()
    failed = sum(1 for c in checks if not c.ok)
    for c in checks:
        print(f"  {'✓' if c.ok else '✗'} {c.name}: {c.detail}")
    if failed:
        print(f"\n{failed} check(s) failed.", file=sys.stderr)
        return 1
    print("\nall checks passed")
    return 0


def _cmd_refresh(args: argparse.Namespace) -> int:
    import time

    from ingest.config import load_config
    from ingest.refresh import refresh
    from ingest.store import Store

    config = load_config()
    store = Store(config.store_path)
    try:
        result = refresh(config, store, now=int(time.time()), force=args.force)
    finally:
        store.close()
    verb = "refreshed" if result.refreshed else "skipped"
    print(f"{verb}: {result.reason} — {result.n_states} books in state")
    if result.progress_fetched or result.progress_errors:
        print(
            f"kosync progress: {result.progress_fetched} resolved, "
            f"{result.progress_errors} error(s)"
        )
    return 0


def _cmd_backup(args: argparse.Namespace) -> int:
    import time

    from ingest.backup import backup_store
    from ingest.config import load_config

    config = load_config()
    stamp = time.strftime("%Y%m%dT%H%M%S")
    dest = backup_store(config.store_path, config.data_dir / "backups", stamp)
    print(f"backed up to {dest}")
    return 0


def _cmd_restore(args: argparse.Namespace) -> int:
    from ingest.backup import restore_store
    from ingest.config import load_config

    config = load_config()
    restore_store(Path(args.backup), config.store_path)
    print(f"restored {config.store_path} from {args.backup}")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    """Write the dashboard (incl. Wrapped) to a self-contained local HTML file.

    With ``--archive``, instead writes a preservation-grade JSON bundle (see
    :mod:`ingest.archive`) — the same "local only" contract, different format.
    """
    if args.archive:
        return _cmd_export_archive(args)

    import time

    from app.view import render_view, view_from_store

    from ingest.config import load_config
    from ingest.refresh import refresh
    from ingest.store import Store

    config = load_config()
    store = Store(config.store_path)
    try:
        if not store.is_populated:
            refresh(config, store, now=int(time.time()))
        from recommender.lists_store import list_store_path, load_stored_lists

        view = view_from_store(
            store,
            user="demo" if config.demo else "you",
            aperture_strength=config.aperture_strength,
            goal_books=config.goal_books,
            goal_pages=config.goal_pages,
            goal_streak_days=config.goal_streak_days,
            lens_config=config.lens_config,
            authored_lists=load_stored_lists(list_store_path(config)),
        )
    finally:
        store.close()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_view(view), encoding="utf-8")
    print(f"exported dashboard to {out} (local only — nothing was published)")
    return 0


def _cmd_export_archive(args: argparse.Namespace) -> int:
    """Write the full derived app state as a self-describing JSON archive."""
    import time

    from ingest.archive import build_archive
    from ingest.config import load_config
    from ingest.refresh import refresh
    from ingest.store import Store

    config = load_config()
    store = Store(config.store_path)
    try:
        now = int(time.time())
        if not store.is_populated:
            refresh(config, store, now=now)
        states = store.load_states()
        activity = store.load_daily_activity()
        bundle = build_archive(states, activity, generated_at=now)
    finally:
        store.close()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
    print(f"exported archive to {out} (local only — nothing was published)")
    return 0


def _cmd_import_archive(args: argparse.Namespace) -> int:
    """Restore derived app state from a preservation-grade JSON archive."""
    from ingest.archive import restore_archive
    from ingest.config import load_config
    from ingest.store import Store

    src = Path(args.archive)
    bundle = json.loads(src.read_text(encoding="utf-8"))
    states, activity = restore_archive(bundle)

    config = load_config()
    store = Store(config.store_path)
    try:
        store.save(states, activity, refreshed_at=int(bundle["manifest"]["generated_at"]))
    finally:
        store.close()
    print(
        f"imported {len(states)} book(s) from {src} into {config.store_path} "
        "(local only — nothing was published)"
    )
    return 0


def _cmd_lists_new(args: argparse.Namespace) -> int:
    """Create a new authored curated list and persist it to ``data_dir/lists.json``."""
    from recommender.lists_store import list_store_path, load_stored_lists, new_list, save_lists

    from ingest.config import load_config

    config = load_config()
    path = list_store_path(config)
    lists = load_stored_lists(path)
    lists = new_list(lists, args.name, args.citation, tuple(args.book or ()))
    save_lists(path, lists)
    added = next(lst for lst in lists if lst.name == args.name)
    print(f"created list {added.name!r} ({len(added.book_ids)} book(s)) — saved to {path}")
    return 0


def _cmd_lists_add(args: argparse.Namespace) -> int:
    """Add a book to an existing authored list."""
    from recommender.lists_store import (
        add_book_to_list,
        list_store_path,
        load_stored_lists,
        save_lists,
    )

    from ingest.config import load_config

    config = load_config()
    path = list_store_path(config)
    lists = load_stored_lists(path)
    lists = add_book_to_list(lists, args.name, args.book)
    save_lists(path, lists)
    updated = next(lst for lst in lists if lst.name == args.name)
    print(f"list {updated.name!r} now has {len(updated.book_ids)} book(s) — saved to {path}")
    return 0


def _cmd_lists_export(args: argparse.Namespace) -> int:
    """Export authored lists as validated JSON — manual-only, no network.

    Writes to stdout by default, or a local file with ``--out``. Nothing here
    ever transmits the export; the reader shares it themselves if they choose.
    """
    from recommender.lists_store import export_lists, list_store_path, load_stored_lists

    from ingest.config import load_config

    config = load_config()
    lists = load_stored_lists(list_store_path(config))
    body = export_lists(lists)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
        print(f"exported {len(lists)} list(s) to {out} (local only — nothing was sent)")
    else:
        print(body, end="")
    return 0


def _cmd_lists_ls(args: argparse.Namespace) -> int:
    """List authored lists with their citation and book count."""
    from recommender.lists_store import list_store_path, load_stored_lists

    from ingest.config import load_config

    config = load_config()
    lists = load_stored_lists(list_store_path(config))
    if not lists:
        print("no authored lists yet — create one with 'stacks lists new'")
        return 0
    for lst in lists:
        print(
            f"{lst.name} — {lst.citation} — {len(lst.book_ids)} book(s), as of {lst.retrieved_at}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stacks", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_eval = sub.add_parser("eval", help="offline eval vs the popularity baseline")
    p_eval.add_argument("--k", type=int, default=5)
    p_eval.add_argument("--out", default="docs/audits/eval-report.json")
    p_eval.set_defaults(func=_cmd_eval)

    p_rec = sub.add_parser("recommend", help="print demo recommendations")
    p_rec.add_argument("--k", type=int, default=10)
    p_rec.set_defaults(func=_cmd_recommend)

    p_doc = sub.add_parser("doctor", help="validate config + read-only access")
    p_doc.set_defaults(func=_cmd_doctor)

    p_ref = sub.add_parser("refresh", help="ingest sources into the app-state store")
    p_ref.add_argument("--force", action="store_true", help="re-ingest even if unchanged")
    p_ref.set_defaults(func=_cmd_refresh)

    p_bak = sub.add_parser("backup", help="back up the app-state store (timestamped)")
    p_bak.set_defaults(func=_cmd_backup)

    p_res = sub.add_parser("restore", help="restore the app-state store from a backup")
    p_res.add_argument("backup", help="path to a backup .sqlite file")
    p_res.set_defaults(func=_cmd_restore)

    p_exp = sub.add_parser(
        "export", help="export the dashboard (or, with --archive, a preservation JSON bundle)"
    )
    p_exp.add_argument("--out", default="stacks-dashboard.html")
    p_exp.add_argument(
        "--archive",
        action="store_true",
        help="write a versioned, self-describing JSON archive instead of HTML "
        "(see ingest.archive); pair with --out to name the .json file",
    )
    p_exp.set_defaults(func=_cmd_export)

    p_imp = sub.add_parser(
        "import", help="restore app state from a preservation-grade JSON archive"
    )
    p_imp.add_argument(
        "--archive",
        dest="archive",
        required=True,
        help="path to a JSON archive produced by `stacks export --archive`",
    )
    p_imp.set_defaults(func=_cmd_import_archive)

    p_lists = sub.add_parser("lists", help="author cited curated lists")
    lists_sub = p_lists.add_subparsers(dest="lists_command", required=True)

    p_lists_new = lists_sub.add_parser("new", help="create a new curated list")
    p_lists_new.add_argument("name", help="list name (must be unique)")
    p_lists_new.add_argument("--citation", required=True, help="where this list came from")
    p_lists_new.add_argument(
        "--book", action="append", default=[], help="a book id to seed the list with (repeatable)"
    )
    p_lists_new.set_defaults(func=_cmd_lists_new)

    p_lists_add = lists_sub.add_parser("add", help="add a book to an existing list")
    p_lists_add.add_argument("name", help="list name")
    p_lists_add.add_argument("--book", required=True, help="book id to add")
    p_lists_add.set_defaults(func=_cmd_lists_add)

    p_lists_export = lists_sub.add_parser(
        "export", help="export authored lists as validated JSON (manual-only, no network)"
    )
    p_lists_export.add_argument("--out", default=None, help="write to this file instead of stdout")
    p_lists_export.set_defaults(func=_cmd_lists_export)

    p_lists_ls = lists_sub.add_parser("ls", help="list your authored curated lists")
    p_lists_ls.set_defaults(func=_cmd_lists_ls)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
