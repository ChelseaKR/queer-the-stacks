"""Command-line entry point: ``qsr eval`` and ``qsr recommend`` (demo mode).

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

    with tempfile.TemporaryDirectory(prefix="qsr-demo-") as tmp:
        states = demo_reading_states(Path(tmp))
    return states, demo_candidates(), DEMO_LISTS


def _cmd_eval(args: argparse.Namespace) -> int:
    from recommender.eval import evaluate, to_report

    states, candidates, lists = _demo_states_and_candidates()
    results = evaluate(states, list(candidates), lists=lists, k=args.k)
    report = to_report(results)
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
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qsr", description=__doc__)
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

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
