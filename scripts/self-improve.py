#!/usr/bin/env python3
"""self-improve.py — the LAST rung of the conductor's self-* ladder.

sustain -> route -> feed -> merge -> converge -> heal -> **self-IMPROVE**.

Every other organ acts on the world (assign a lane, merge a PR, close a gap).
This one acts on the CONDUCTOR ITSELF: it reads the loop's own track record —
the `dispatch_log` the dispatcher writes into every task, plus the live status
ledger — and EMITS a re-plan proposal so the next cycle is wiser than the last.
Without it the loop repeats its mistakes forever: re-dispatching task patterns
that always fail, piling work on a lane that's 0%, chasing chronic-reopen tasks
that have been thrown at every vendor a dozen times and still won't land.

This is alchemical evolution toward ideal form, not janitorial reduction: each
beat the conductor distills what worked from what didn't and adjusts its own
priors. It learns three things and proposes three moves:

  1. LANE PRODUCTIVITY  — per-lane success rate + throughput from dispatch_log.
     "lane X is 0% over its last N tries -> down-weight"; "lane Y idle while Z
     saturated -> rebalance toward Y". Expressed as a target_weight per lane that
     route.py's budget-split could honour.
  2. TASK-PATTERN LEARNING — task-ID prefixes (LIMEN/GH/BLD/REV/CIFIX/GEN/...)
     and types that chronically FAIL or get re-dispatched 3..7..19x. Recommends
     RETIRE (stop feeding) or RE-ROUTE (try a different lane) for each.
  3. BACKLOG RE-RANK — boost patterns that actually SHIP (high done-rate, tied to
     merged/open work), de-prioritise chronic dead-ends.

PROPOSAL-FIRST + READ-ONLY by design. It never writes tasks.yaml and never
touches route config. It writes ONE structured, timestamped, evidence-backed
proposal to logs/self-improve-proposal.json. `--dry-run` prints it instead of
writing. `--apply` is a documented STUB: there is no safe-append / route-update
mechanism wired yet, so it refuses and explains, leaving the human (or a future
organ) to act on the proposal. Bounded, idempotent, never crashes its caller.

Everything is DERIVED or env-tunable — lanes come from capacity.PAID_AGENT_ORDER,
prefixes/types are read off the board, thresholds are env knobs. No hardcodes;
names are outputs.

Usage:
  python3 self-improve.py [--tasks tasks.yaml] [--out logs/self-improve-proposal.json]
                          [--dry-run] [--apply]

Env knobs (all optional, all have derived/sane defaults):
  LIMEN_ROOT, LIMEN_TASKS
  LIMEN_SI_FAIL_RATE        lane/pattern fail-rate above which we flag       (0.6)
  LIMEN_SI_MIN_SAMPLES      min dispatches before a lane verdict is trusted  (5)
  LIMEN_SI_CHRONIC_REDISP   dispatch_log length at/above which a task is
                            "chronic" (re-thrown too many times)             (5)
  LIMEN_SI_MIN_PATTERN      min tasks in a prefix/type before a verdict      (3)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

try:
    import yaml
except ImportError:  # pragma: no cover - environment guard
    print("pyyaml required", file=sys.stderr)
    sys.exit(1)

from limen.capacity import PAID_AGENT_ORDER, canonical_agent  # noqa: E402


# --- env knobs (derived defaults, never pinned literals at the call site) -----
def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


FAIL_RATE = _env_float("LIMEN_SI_FAIL_RATE", 0.6)
MIN_SAMPLES = _env_int("LIMEN_SI_MIN_SAMPLES", 5)
CHRONIC_REDISP = _env_int("LIMEN_SI_CHRONIC_REDISP", 5)
MIN_PATTERN = _env_int("LIMEN_SI_MIN_PATTERN", 3)

# `limen` appears as an "agent" in dispatch_log but it is the conductor's own
# status-ledger voice (it records open/done/archived transitions), NOT a vendor
# lane that does work. The real lanes are exactly PAID_AGENT_ORDER. Deriving the
# real-lane set this way means a new vendor added to capacity.py is learned about
# automatically — names are outputs.
_REAL_LANES = set(PAID_AGENT_ORDER)

# Terminal success markers a dispatch_log entry can carry. A lane "shipped" a try
# only when its entry reads `done`. Everything else is non-success: an outright
# `failed`/`noop`, or a hand-off arrow (`timeout->jules`, `ratelimited->opencode`,
# `failed->claude`) which means THIS lane could not do it and punted. `dispatched`
# / `in_progress` are in-flight (not yet a verdict) and excluded from rates.
_SUCCESS = {"done"}
_INFLIGHT = {"dispatched", "in_progress"}


def _status_class(raw: str) -> str:
    """done | inflight | fail — the alchemical verdict of one dispatch attempt."""
    s = (raw or "").strip().lower()
    if s in _SUCCESS:
        return "done"
    if s in _INFLIGHT:
        return "inflight"
    return "fail"  # failed / noop / *->fallback handoffs all = this lane didn't land it


def _prefix(task_id: str) -> str:
    """Derive a task's PATTERN from its id (LIMEN-064 -> LIMEN). Names are outputs."""
    return str(task_id or "").split("-", 1)[0].upper() or "?"


def load_board(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


# ---------------------------------------------------------------------------
# 1. LANE PRODUCTIVITY
# ---------------------------------------------------------------------------
def _labels(t: dict) -> set[str]:
    return {str(label) for label in (t.get("labels") or [])}


def _is_cancel_archived(t: dict) -> bool:
    labels = _labels(t)
    return t.get("status") == "archived" and ("cancelled" in labels or "noop" in labels)


def _is_success_status(t: dict) -> bool:
    return t.get("status") == "done" or (t.get("status") == "archived" and not _is_cancel_archived(t))


def _is_failure_status(t: dict) -> bool:
    return t.get("status") in {"failed", "failed_blocked"} or _is_cancel_archived(t)


def lane_stats(tasks: list[dict]) -> dict[str, Counter]:
    """Per real-lane Counter of done/inflight/fail, attributed PER TASK to the lane
    that actually last worked it.

    Why per-task, not per-dispatch-row: the local lanes (codex/opencode/agy) run in a
    throwaway worktree and open a PR, leaving their OWN dispatch_log row at `dispatched`;
    the terminal `done` is written later by the `limen` reconcile voice on a SEPARATE
    row. Counting rows therefore credits those lanes' wins to `limen` (which we exclude)
    and scores them ~0% — a pure measurement artifact (it made codex read 0%/92 while it
    was in fact carrying load). Instead we credit each task's terminal verdict to its
    RESPONSIBLE lane = the last real-lane agent in its dispatch_log (the one that
    produced the final state). jules self-reports `done`, so both views agree for it;
    this repair only corrects the local lanes whose success the ledger had hidden.
    """
    stats: dict[str, Counter] = defaultdict(Counter)
    for t in tasks:
        real_entries = [
            e for e in (t.get("dispatch_log") or [])
            if canonical_agent(e.get("agent")) in _REAL_LANES
        ]
        if not real_entries:
            continue  # no real lane ever took it (limen-only ledger / never dispatched)
        lane = canonical_agent(real_entries[-1].get("agent"))
        if _is_success_status(t):
            verdict = "done"
        elif _is_failure_status(t):
            verdict = "fail"
        else:
            verdict = "inflight"  # open / dispatched / in_progress / needs_human / ...
        stats[lane][verdict] += 1
    return stats


def lane_adjustments(stats: dict[str, Counter]) -> list[dict]:
    """Recommend per-lane weight shifts from success rate + throughput.

    target_weight is a 0..1 prior route.py's budget-split could multiply a lane's
    headroom by: 1.0 = trust as-is, <1 = down-weight a failing lane, slight boost
    for proven-but-underused lanes so an idle high-success lane gets fed."""
    # decided lanes = those with a verdict (done or fail); inflight doesn't count.
    decided = {l: (c["done"] + c["fail"]) for l, c in stats.items()}
    throughput = {l: c["done"] for l, c in stats.items()}
    max_done = max(throughput.values(), default=0)

    rows: list[dict] = []
    for lane in sorted(stats, key=lambda l: -decided.get(l, 0)):
        c = stats[lane]
        n = decided[lane]
        rate = (c["done"] / n) if n else None
        fail_rate = (c["fail"] / n) if n else None
        trusted = n >= MIN_SAMPLES

        if rate is None:
            verdict, weight = "no-verdict-yet", 1.0
            reason = f"only in-flight tries ({c['inflight']}); no done/fail to judge"
        elif not trusted:
            verdict, weight = "low-sample", 1.0
            reason = f"{n} decided tries (<{MIN_SAMPLES}); keep as-is until more signal"
        elif fail_rate >= FAIL_RATE:
            verdict = "down-weight"
            # weight scales with how much it DID land: a 0%-lane drops hard.
            weight = round(max(0.1, rate), 3)
            reason = (f"success {rate:.0%} over {n} decided tries "
                      f"(fail {fail_rate:.0%} >= {FAIL_RATE:.0%}) -> shed new work")
        elif max_done and throughput[lane] <= 0.25 * max_done and rate >= 0.5:
            verdict = "boost-underused"
            weight = 1.25
            reason = (f"success {rate:.0%} but throughput {throughput[lane]} is "
                      f"<=25% of top lane ({max_done}); feed it more")
        else:
            verdict, weight = "keep", 1.0
            reason = f"healthy: success {rate:.0%} over {n} decided tries"

        rows.append({
            "lane": lane,
            "verdict": verdict,
            "target_weight": weight,
            "success_rate": None if rate is None else round(rate, 3),
            "throughput_done": c["done"],
            "decided_tries": n,
            "inflight": c["inflight"],
            "fail": c["fail"],
            "reason": reason,
        })
    return rows


# ---------------------------------------------------------------------------
# 2. TASK-PATTERN LEARNING
# ---------------------------------------------------------------------------
def pattern_stats(tasks: list[dict]) -> dict[str, dict]:
    """Per task-ID-prefix: outcome tally + chronic-redispatch evidence."""
    by: dict[str, dict] = defaultdict(lambda: {
        "total": 0,
        "status": Counter(),       # current task.status (done/archived/open/...)
        "success_status": 0,
        "failure_status": 0,
        "dispatch": Counter(),     # done/fail/inflight summed over dispatch_log
        "chronic": [],             # task ids re-thrown >= CHRONIC_REDISP times
        "max_redispatch": 0,
    })
    for t in tasks:
        p = _prefix(t.get("id"))
        b = by[p]
        b["total"] += 1
        b["status"][t.get("status", "?")] += 1
        if _is_success_status(t):
            b["success_status"] += 1
        elif _is_failure_status(t):
            b["failure_status"] += 1
        log = t.get("dispatch_log") or []
        # count only real-lane attempts toward "chronic" (ignore limen ledger rows)
        real_tries = [e for e in log if canonical_agent(e.get("agent")) in _REAL_LANES]
        for e in real_tries:
            b["dispatch"][_status_class(e.get("status"))] += 1
        if len(real_tries) >= CHRONIC_REDISP:
            b["chronic"].append({"id": t.get("id"), "tries": len(real_tries),
                                 "status": t.get("status")})
        b["max_redispatch"] = max(b["max_redispatch"], len(real_tries))
    return by


def retire_patterns(by: dict[str, dict]) -> list[dict]:
    """Recommend RETIRE / RE-ROUTE for chronically-failing or chronic-reopen patterns."""
    rows: list[dict] = []
    for p, b in sorted(by.items(), key=lambda kv: -kv[1]["total"]):
        if b["total"] < MIN_PATTERN:
            continue
        d = b["dispatch"]
        decided = d["done"] + d["fail"]
        dispatch_fail_rate = (d["fail"] / decided) if decided else None
        st = b["status"]
        # current-status ship rate: shipped vs terminal/parked outcomes — the
        # patterns that never reach done are the dead-ends.
        terminal = b["success_status"] + b["failure_status"] + st["needs_human"]
        ship_rate = (b["success_status"] / terminal) if terminal else None
        chronic_n = len(b["chronic"])

        flags = []
        if dispatch_fail_rate is not None and decided >= MIN_SAMPLES and dispatch_fail_rate >= FAIL_RATE:
            flags.append(f"dispatch fail {dispatch_fail_rate:.0%} over {decided} tries")
        if ship_rate is not None and terminal >= MIN_PATTERN and ship_rate < (1 - FAIL_RATE):
            flags.append(f"ship rate {ship_rate:.0%} (mostly archived-noop/needs_human)")
        if chronic_n:
            flags.append(f"{chronic_n} chronic tasks re-thrown >= {CHRONIC_REDISP}x "
                         f"(max {b['max_redispatch']}x)")

        if not flags:
            continue

        # RETIRE if it almost never ships; otherwise RE-ROUTE the chronic stragglers.
        action = "retire" if (ship_rate is not None and ship_rate < (1 - FAIL_RATE)) else "re-route"
        rows.append({
            "pattern": p,
            "action": action,
            "total_tasks": b["total"],
            "ship_rate": None if ship_rate is None else round(ship_rate, 3),
            "dispatch_fail_rate": None if dispatch_fail_rate is None else round(dispatch_fail_rate, 3),
            "chronic_count": chronic_n,
            "max_redispatch": b["max_redispatch"],
            "status_breakdown": dict(st),
            "evidence": flags,
            # cap the named examples so the proposal stays bounded
            "chronic_examples": sorted(b["chronic"], key=lambda c: -c["tries"])[:5],
        })
    return rows


# ---------------------------------------------------------------------------
# 3. BACKLOG RE-RANK
# ---------------------------------------------------------------------------
def rerank(by: dict[str, dict]) -> list[dict]:
    """Score each pattern by how much it SHIPS; propose boost / hold / deprioritise.

    Tie to real outcomes: a pattern with many `done` and few cancellations earns a
    boost (feed it first); a pattern that mostly cancels / never lands gets pushed
    down so the loop stops spending beats on dead-ends."""
    rows: list[dict] = []
    for p, b in by.items():
        if b["total"] < MIN_PATTERN:
            continue
        st = b["status"]
        terminal = b["success_status"] + b["failure_status"] + st["needs_human"]
        ship_rate = (b["success_status"] / terminal) if terminal else None
        open_n = st.get("open", 0) + st.get("dispatched", 0)
        if ship_rate is None:
            continue
        if ship_rate >= 0.75 and b["success_status"] >= MIN_PATTERN:
            move, delta = "boost", "+1"
        elif ship_rate < (1 - FAIL_RATE):
            move, delta = "deprioritise", "-1"
        else:
            move, delta = "hold", "0"
        rows.append({
            "pattern": p,
            "move": move,
            "priority_delta": delta,
            "ship_rate": round(ship_rate, 3),
            "done": b["success_status"],
            "open_remaining": open_n,
            "reason": f"ship rate {ship_rate:.0%} ({b['success_status']} shipped / {terminal} terminal); "
                      f"{open_n} still open",
        })
    # most-shipping first; ties broken by volume shipped
    rows.sort(key=lambda r: (-r["ship_rate"], -r["done"]))
    return rows


def build_proposal(board: dict, tasks_path: Path) -> dict:
    tasks = board.get("tasks") or []
    ls = lane_stats(tasks)
    ps = pattern_stats(tasks)
    statuses = Counter(t.get("status", "?") for t in tasks)
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": str(tasks_path),
        "organ": "self-improve",
        "ladder_rung": "self-improve (final)",
        "thresholds": {
            "fail_rate": FAIL_RATE,
            "min_samples": MIN_SAMPLES,
            "chronic_redispatch": CHRONIC_REDISP,
            "min_pattern": MIN_PATTERN,
        },
        "board_summary": {
            "total_tasks": len(tasks),
            "status_breakdown": dict(statuses),
            "real_lanes_observed": sorted(l for l in ls),
        },
        "lane_adjustments": lane_adjustments(ls),
        "retire_patterns": retire_patterns(ps),
        "rerank": rerank(ps),
        "apply": {
            "wired": True,
            "note": "--apply now closes the loop: lane weights are consumed by route.py "
                    "(_learned_weights, gated LIMEN_SI_APPLY=1); rerank boost/deprioritise "
                    "set OPEN tasks' priority (idempotent targets); retire→archived/superseded is gated "
                    "behind LIMEN_SI_RETIRE=1 (destructive, default OFF). All under the canonical "
                    "queue lock, reversible.",
        },
    }


# ---------------------------------------------------------------------------
# 4. APPLY — the writer that closes the IMPROVE loop (safe, idempotent, reversible)
# ---------------------------------------------------------------------------
def apply_proposal(proposal: dict, tasks_path: Path) -> int:
    """Consume the proposal and SAFELY re-plan tasks.yaml under the canonical queue lock (cannot
    race the daemon; fresh-reload + atomic save). Bounded + idempotent + reversible:
      • rerank boost        -> raise the pattern's OPEN tasks to 'high'  (idempotent TARGET, never a
                               runaway +1-every-beat delta; 'critical' stays reserved for humans)
      • rerank deprioritise -> lower the pattern's OPEN tasks to 'low'
      • retire (supersede)  -> mark OPEN tasks 'archived' with a superseded label ONLY if LIMEN_SI_RETIRE=1 (destructive,
                               default OFF — never silently cancels real work [[no-never-happens-again]])
    Lane weights + 're-route' are consumed by route.py's weighting (NOT rewritten here — clearing
    target_agent would just thrash the router every beat)."""
    sys.path.insert(0, str(ROOT / "cli" / "src"))
    from limen.io import load_limen_file, queue_lock  # noqa: E402
    from limen.tabularius import apply_limen_file_sync  # noqa: E402

    boost = {r["pattern"] for r in proposal.get("rerank", []) if r.get("move") == "boost"}
    deprio = {r["pattern"] for r in proposal.get("rerank", []) if r.get("move") == "deprioritise"}
    retire = {r["pattern"] for r in proposal.get("retire_patterns", []) if r.get("action") == "retire"}
    allow_retire = os.environ.get("LIMEN_SI_RETIRE") == "1"

    with queue_lock(tasks_path) as got:
        if not got:
            print("[self-improve] queue busy — skipped apply this pass (self-corrects next beat)")
            return 0
        try:
            lf = load_limen_file(tasks_path)
        except Exception as exc:  # never crash the heartbeat — skip apply, proposal already written
            print(f"[self-improve] could not load {tasks_path} for apply ({exc}); proposal-only this pass")
            return 0
        ch = {"boost": 0, "deprio": 0, "retire": 0}
        for t in lf.tasks:
            if t.status not in ("open", "failed"):
                continue
            p = _prefix(t.id)
            if p in boost and t.priority not in ("critical", "high"):
                t.priority = "high"; ch["boost"] += 1
            elif p in deprio and t.priority not in ("low", "backlog"):
                t.priority = "low"; ch["deprio"] += 1
            if p in retire and allow_retire and t.status != "archived":
                t.status = "archived"
                if "superseded" not in t.labels:
                    t.labels.append("superseded")
                ch["retire"] += 1
        apply_limen_file_sync(tasks_path, lf, agent="self-improve", session_id="apply")
    held = "" if allow_retire else f" ({len(retire)} retire patterns HELD — set LIMEN_SI_RETIRE=1)"
    print(f"[self-improve] applied: {ch['boost']} boosted→high, {ch['deprio']} →low, "
          f"{ch['retire']} retired→archived/superseded{held}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="self-improve organ — read the loop's "
                                             "track record, emit a re-plan proposal")
    ap.add_argument("--tasks", default=os.environ.get(
        "LIMEN_TASKS", str(ROOT / "tasks.yaml")))
    ap.add_argument("--out", default=os.environ.get(
        "LIMEN_SI_OUT", str(ROOT / "logs" / "self-improve-proposal.json")))
    ap.add_argument("--dry-run", action="store_true",
                    help="print the proposal to stdout; write nothing")
    ap.add_argument("--apply", action="store_true",
                    help="write the proposal AND apply task-level re-plan (rerank priorities; "
                         "retire→archived/superseded gated by LIMEN_SI_RETIRE=1). Lane weights via route.py.")
    args = ap.parse_args()

    tasks_path = Path(args.tasks)
    if not tasks_path.exists():
        print(f"[self-improve] tasks file not found: {tasks_path}", file=sys.stderr)
        return 1

    try:
        board = load_board(tasks_path)
    except Exception as exc:  # never crash the heartbeat
        print(f"[self-improve] could not parse {tasks_path}: {exc}", file=sys.stderr)
        return 1

    proposal = build_proposal(board, tasks_path)
    blob = json.dumps(proposal, indent=2, ensure_ascii=False)

    if args.apply:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(blob + "\n")  # write proposal first so route.py picks up fresh weights
        print(f"[self-improve] wrote {out}")
        return apply_proposal(proposal, tasks_path)

    if args.dry_run:
        print(blob)
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(blob + "\n")

    la = proposal["lane_adjustments"]
    flagged = [r for r in la if r["verdict"] in ("down-weight", "boost-underused")]
    print(f"[self-improve] wrote {out}")
    print(f"  board: {proposal['board_summary']['total_tasks']} tasks; "
          f"lanes judged: {len(la)} ({len(flagged)} flagged for adjustment)")
    print(f"  retire/re-route patterns: {len(proposal['retire_patterns'])}; "
          f"rerank moves: {sum(1 for r in proposal['rerank'] if r['move'] != 'hold')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
