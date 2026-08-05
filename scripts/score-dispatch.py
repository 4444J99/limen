#!/usr/bin/env python3
"""score-dispatch — the CREDIT side of the ledger. Every assignment is a debit; this weighs the RETURN.

`verify-dispatch.py` checks whether a PR *landed* (binary). This grades whether the spend was WORTH it:
every RESOLVED task gets `worth_it` / `marginal` / `wasted`, carrying its `budget_cost` as the debit and
(for wasted) the spent cost logged as SUNK — the money that bought nothing. Append-only to
`logs/ledger.jsonl`, idempotent via the ids already in that file — the daemon runs it each heal beat to
score newly-resolved tasks; `--backfill` scores the whole board once (the first honest verdict).

Grading is from LOCAL dispatch_log signals by default (no network, so the heal beat stays fast):
  worth_it : status=done AND a PR ref landed in dispatch_log               → work shipped
  marginal : status=done with no PR artifact, OR archived+superseded label → done, nothing shippable / folded in
  wasted   : archived+cancelled/noop label, OR chronic reopened w/o PR     → effort, zero output

Debit accounting: a dispatch is a debit of `budget_cost`. `attempts` = recorded dispatches; `spent` =
budget_cost x attempts. For `wasted` that whole spend is SUNK. ([[value-is-discovered-never-assumed]]
is the input side; this is the output side — every item measured: done right, or wasted money.)

READ-ONLY on tasks.yaml. Fail-open: any error scores nothing rather than crash the beat.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
TASKS = Path(os.environ.get("LIMEN_TASKS", str(ROOT / "tasks.yaml")))
LEDGER = ROOT / "logs" / "ledger.jsonl"
PR_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")

# A task is RESOLVED (its return can be weighed) once it reaches a terminal state.
_RESOLVED = {"done", "archived"}


def _logical_session(entry: dict) -> str:
    return str(entry.get("logical_session_id") or entry.get("session_id") or "")


def _positive_int(value, default: int = 1) -> int:
    try:
        if isinstance(value, bool):
            return default
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _pr_ref(t: dict) -> str | None:
    for e in t.get("dispatch_log") or []:
        m = PR_RE.search(_logical_session(e))
        if m:
            return f"{m.group(1)}/{m.group(2)}#{m.group(3)}"
    return None


def _attempts(t: dict) -> int:
    """How many times this task was actually dispatched (each a real debit)."""
    return sum(1 for e in (t.get("dispatch_log") or []) if str(e.get("status")) == "dispatched")


def _is_chronic(t: dict, min_reopens: int = 3) -> bool:
    log = t.get("dispatch_log") or []
    reopens = sum(1 for e in log if str(e.get("status")) == "open")
    ever_pr = any(PR_RE.search(_logical_session(e)) for e in log)
    return reopens >= min_reopens and not ever_pr


def _labels(t: dict) -> set[str]:
    return {str(label) for label in (t.get("labels") or [])}


def _archived_reason(t: dict) -> str:
    labels = _labels(t)
    if "superseded" in labels:
        return "superseded"
    if "cancelled" in labels or "noop" in labels:
        return "cancelled"
    return "closed"


def grade(t: dict) -> dict | None:
    """Weigh one task's return. None ⇒ not yet resolvable (still in flight / pending human)."""
    status = t.get("status")
    chronic = _is_chronic(t)
    if status not in _RESOLVED and not (status in ("needs_human", "failed_blocked") and chronic):
        return None  # open / dispatched / in_progress / non-chronic needs_human/failed_blocked → not yet weighable

    pr = _pr_ref(t)
    cost = _positive_int(t.get("budget_cost"), 1)
    attempts = _attempts(t)

    if status == "done" and pr:
        g, note = "worth_it", "shipped — PR landed"
    elif status == "done":
        g, note = "marginal", "done, no shippable PR artifact"
    elif status == "archived" and _archived_reason(t) == "superseded":
        g, note = "marginal", "folded into other work"
    elif status == "archived" and _archived_reason(t) == "cancelled":
        g, note = "wasted", "cancelled/no-op — effort produced nothing"
    elif status == "archived":
        g, note = "marginal", "archived without a shippable PR artifact"
    else:  # chronic needs_human / chronic failed_blocked (parked fleet-debt)
        g, note = "wasted", "chronic — reopened, never a PR (parked off the dispatch loop)"

    spent = cost * (attempts if _archived_reason(t) == "cancelled" else max(1, attempts))
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "task_id": t.get("id"),
        "repo": t.get("repo"),
        "lane": t.get("target_agent"),
        "status": status,
        "grade": g,
        "budget_cost": cost,
        "attempts": attempts,
        "spent": spent,
        "sunk": spent if g == "wasted" else 0,
        "pr": pr,
        "note": note,
        # class signals — what KIND of work this was, so routing can steer a lane away from the
        # classes it wastes on (not blanket-demote a lane that wins elsewhere).
        "type": t.get("type"),
        "labels": t.get("labels") or [],
    }


def _already_scored() -> set[str]:
    scored: set[str] = set()
    if LEDGER.exists():
        for ln in LEDGER.read_text().splitlines():
            try:
                scored.add(json.loads(ln)["task_id"])
            except Exception:
                continue
    return scored


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=str(TASKS), help="board to weigh (default: $LIMEN_TASKS / tasks.yaml)")
    ap.add_argument("--backfill", action="store_true", help="score every resolved task once (the first full verdict)")
    ap.add_argument("--limit", type=int, default=0, help="cap new records this run (0 = no cap)")
    ap.add_argument("--print", dest="print_only", action="store_true", help="print the new records; do not append")
    args = ap.parse_args()

    try:
        data = yaml.safe_load(Path(args.tasks).read_text()) or {}
        tasks = data.get("tasks", []) if isinstance(data, dict) else (data or [])
    except Exception as e:
        print(f"score-dispatch: cannot read board ({e}) — scored nothing (fail-open).")
        return 0

    scored = set() if args.backfill else _already_scored()
    new: list[dict] = []
    for t in tasks:
        if not isinstance(t, dict) or t.get("id") in scored:
            continue
        rec = grade(t)
        if rec is None:
            continue
        new.append(rec)
        scored.add(rec["task_id"])
        if args.limit and len(new) >= args.limit:
            break

    by_grade = {}
    for r in new:
        by_grade[r["grade"]] = by_grade.get(r["grade"], 0) + 1
    print(
        f"score-dispatch: {len(new)} newly-weighed tasks "
        f"({by_grade.get('worth_it', 0)} worth_it, {by_grade.get('marginal', 0)} marginal, "
        f"{by_grade.get('wasted', 0)} wasted)"
    )

    if args.print_only:
        for r in new:
            print(json.dumps(r))
        return 0
    if not new:
        return 0
    LEDGER.parent.mkdir(exist_ok=True)
    mode = "w" if args.backfill else "a"
    with LEDGER.open(mode) as fh:
        for r in new:
            fh.write(json.dumps(r) + "\n")
    print(
        f"score-dispatch: appended {len(new)} records -> {LEDGER}" + (" (backfill: rewrote)" if args.backfill else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
