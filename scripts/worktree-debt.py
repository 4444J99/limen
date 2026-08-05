#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))

from limen.worktree_debt import worktree_debt_report  # noqa: E402
from limen.worktree_roots import WorktreeInventoryError  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", str(Path(__file__).resolve().parents[1])))
LOGS = ROOT / "logs"
DEBT_TREND = LOGS / "debt-trend.jsonl"

# Default window for the rising-trend check (number of trailing samples).
_TREND_WINDOW_DEFAULT = 10


def int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _append_trend(debt: int, stamp: str | None, trend_path: Path) -> list[dict]:
    """Append one {stamp, debt} record to the trend JSONL and return the full ledger."""
    ts = stamp or datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = {"stamp": ts, "debt": debt}
    trend_path.parent.mkdir(parents=True, exist_ok=True)
    with trend_path.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")
    # Re-read the full ledger so the caller can window it.
    ledger: list[dict] = []
    for line in trend_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec.get("debt"), int):
            ledger.append(rec)
    return ledger


def _trend_rising(ledger: list[dict], window: int) -> bool:
    """Return True when the trailing `window` debt values are strictly rising."""
    tail = ledger[-window:]
    if len(tail) < 2:
        return False
    return all(tail[i]["debt"] < tail[i + 1]["debt"] for i in range(len(tail) - 1))


def main() -> int:
    parser = argparse.ArgumentParser(description="Report preserved worktree lifecycle debt.")
    parser.add_argument("--json", action="store_true", help="emit the raw debt report as JSON")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail when any configured lifecycle scope cannot be inventoried completely",
    )
    parser.add_argument(
        "--fail-on-debt",
        action="store_true",
        help="exit non-zero unless debt is EXACTLY zero (completion = every root has a terminal receipt)",
    )
    parser.add_argument(
        "--fail-over-cap",
        action="store_true",
        help="DEPRECATED alias of --fail-on-debt (exact-zero); no count cap remains",
    )
    parser.add_argument(
        "--fail-reapable-over-cap",
        action="store_true",
        help="exit non-zero when reapable roots exceed LIMEN_WORKTREE_REAPABLE_MAX",
    )
    parser.add_argument(
        "--trend",
        action="store_true",
        help=(
            "append the debt scalar (+ timestamp) to logs/debt-trend.jsonl and exit nonzero "
            "when the trailing window of samples is strictly rising (IF-AMALGAMATION distance_metric)"
        ),
    )
    parser.add_argument(
        "--stamp",
        default=None,
        help="ISO-8601 UTC timestamp to record with --trend (default: current time)",
    )
    parser.add_argument(
        "--trend-window",
        type=int,
        default=_TREND_WINDOW_DEFAULT,
        metavar="N",
        help=f"trailing sample count for rising-trend check (default: {_TREND_WINDOW_DEFAULT})",
    )
    args = parser.parse_args()

    try:
        report = worktree_debt_report(strict=args.strict)
    except WorktreeInventoryError as exc:
        print(f"worktree lifecycle inventory incomplete: {exc}", file=sys.stderr)
        return 2
    reapable_limit = int_env("LIMEN_WORKTREE_REAPABLE_MAX", 0)
    # Completion is exact zero debt — there is no tolerated count. --fail-over-cap is kept only as a
    # deprecated exact-zero alias so existing callers/gates do not break; it carries no cap authority.
    fail_on_debt = args.fail_on_debt or args.fail_over_cap
    if args.json:
        print(
            json.dumps(
                {
                    **report,
                    "debt_target": 0,
                    "complete": report["debt"] == 0,
                    "reapable_limit": reapable_limit,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"worktree lifecycle debt: {report['debt']} debt roots / {report['total']} scanned (target 0)")
        print(f"worktree reapable roots: {report['reapable']} roots (cap {reapable_limit})")
        for reason, count in sorted(report["by_reason"].items()):
            print(f"  {reason}: {count}")
        if report["debt"] > 0:
            print("  action: each debt root needs a terminal receipt (land / reassign / preserve) — debt must reach 0")
        if report["reapable"] > reapable_limit:
            print("  gate: run scripts/reclaim-worktrees.py --apply --force or record a blocker per retained root")
    if fail_on_debt and report["debt"] > 0:
        return 1
    if args.fail_reapable_over_cap and report["reapable"] > reapable_limit:
        return 1

    if args.trend:
        ledger = _append_trend(report["debt"], args.stamp, DEBT_TREND)
        rising = _trend_rising(ledger, args.trend_window)
        window_tail = ledger[-args.trend_window :]
        tail_vals = [r["debt"] for r in window_tail]
        status = "RISING" if rising else "stable"
        print(
            f"debt-trend: appended debt={report['debt']} to {DEBT_TREND} "
            f"({len(ledger)} samples) | window={args.trend_window} tail={tail_vals} | {status}"
        )
        if rising:
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
