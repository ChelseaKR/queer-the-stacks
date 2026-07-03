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


def _parse_seeds(spec: str) -> list[int]:
    """Parse ``--seeds``: either ``start:stop`` (a range) or a comma list."""
    if ":" in spec:
        start_s, stop_s = spec.split(":", 1)
        return list(range(int(start_s), int(stop_s)))
    return [int(s) for s in spec.split(",") if s.strip()]


def _cmd_eval(args: argparse.Namespace) -> int:
    from recommender.eval import evaluate, to_report
    from recommender.hybrid import recommend_hybrid

    # The demo single-fixture report stays available (informational — it was
    # the whole gate before FIX-13, now it is one saturated illustrative
    # datapoint) alongside the merge-blocking synthetic battery below.
    states, candidates, lists = _demo_states_and_candidates()
    results = evaluate(states, list(candidates), lists=lists, k=args.k)
    top = recommend_hybrid(states, tuple(c.book for c in candidates), lists=lists, k=args.k)
    demo_report = to_report(results, top_books=[r.book for r in top], k=args.k)
    demo_out = Path(args.out)
    demo_out.parent.mkdir(parents=True, exist_ok=True)
    demo_out.write_text(json.dumps(demo_report, indent=2), encoding="utf-8")

    if not args.synthetic:
        print(json.dumps(demo_report, indent=2))
        if not demo_report["content_beats_popularity"]:
            print("FAIL: the recommender did not beat the popularity baseline", file=sys.stderr)
            return 1
        return 0

    from recommender.battery import DEFAULT_SEEDS, run_battery

    seeds = _parse_seeds(args.seeds) if args.seeds else list(DEFAULT_SEEDS)
    battery_report = run_battery(seeds, k=args.k)
    battery_out = Path(args.battery_out)
    battery_out.parent.mkdir(parents=True, exist_ok=True)
    battery_out.write_text(json.dumps(battery_report, indent=2), encoding="utf-8")
    print(json.dumps(battery_report, indent=2))
    if not battery_report["passed"]:
        print(
            "FAIL: synthetic-world battery — median content-vs-popularity MAP uplift "
            f"{battery_report['median_uplift']} < margin {battery_report['margin']}, "
            f"or a losing seed (no_losing_seed={battery_report['no_losing_seed']})",
            file=sys.stderr,
        )
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
    """Write the dashboard (incl. Wrapped) to a self-contained local HTML file."""
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
        view = view_from_store(
            store,
            user="demo" if config.demo else "you",
            aperture_strength=config.aperture_strength,
            goal_books=config.goal_books,
            goal_pages=config.goal_pages,
            goal_streak_days=config.goal_streak_days,
        )
    finally:
        store.close()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_view(view), encoding="utf-8")
    print(f"exported dashboard to {out} (local only — nothing was published)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stacks", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_eval = sub.add_parser("eval", help="offline eval vs the popularity baseline")
    p_eval.add_argument("--k", type=int, default=5)
    p_eval.add_argument(
        "--out", default="docs/audits/eval-report.json", help="demo single-fixture report path"
    )
    p_eval.add_argument(
        "--battery-out",
        default="docs/audits/eval-battery.json",
        help="synthetic-world battery distribution report path",
    )
    p_eval.add_argument(
        "--synthetic",
        dest="synthetic",
        action="store_true",
        default=True,
        help="gate on the seeded synthetic-world battery (default; the merge-blocking gate)",
    )
    p_eval.add_argument(
        "--no-synthetic",
        dest="synthetic",
        action="store_false",
        help="gate on the single demo fixture instead (legacy, always-saturated)",
    )
    p_eval.add_argument(
        "--seeds",
        default=None,
        help="battery seeds: 'start:stop' (a range) or a comma list; default range(0, 10)",
    )
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

    p_exp = sub.add_parser("export", help="export the dashboard to a local HTML file")
    p_exp.add_argument("--out", default="stacks-dashboard.html")
    p_exp.set_defaults(func=_cmd_export)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
