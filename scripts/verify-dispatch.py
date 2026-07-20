#!/usr/bin/env python3
"""verify-dispatch.py — babysit every dispatch. NO SILENT FAILURES.

For every task in status=dispatched, verify its claimed outcome actually exists on
GitHub instead of trusting the dispatch_log. Catches the silent-failure classes:
  - DISPATCHED_NO_PR : local lane recorded dispatched but produced no PR URL (the
                       "no-op that looked like success" — should have been failed/noop)
  - PR_MISSING       : recorded a PR URL but the PR no longer exists (deleted/wrong)
  - PR_MERGED        : PR is merged but task still 'dispatched' → harvest should close it
  - PR_CLOSED        : PR closed unmerged → recover should reopen the task
  - PR_OPEN          : healthy, awaiting review/merge
  - JULES_ASYNC      : jules session (no PR yet) → drain/harvest tracks it

READ-ONLY: never writes tasks.yaml. Emits a loud report + logs/dispatch-verify.json so
the board and the supervisor see failures immediately (they don't get aggregated into a
misleading zero). Healing stays in recover.py / harvest.

Usage:  python3 scripts/verify-dispatch.py [--limit N] [--quiet]
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.dispatch_ownership import active_typed_pr_owner_id  # noqa: E402
from limen.workstream_contract import WORKSTREAM_SUCCESSOR_REQUIRED_LABEL  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
PR_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")
# A dispatch is RESERVED (status=dispatched, updated stamped, reserve log appended) before its
# slow run. A freshly reserved local task still has no PR/session result, so only treat it as
# STRANDED once it has sat longer than any run could take: lane_timeout (900s) +
# fetch/worktree/push/PR overhead.


def _int_or_default(raw, default):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


GRACE = _int_or_default(os.environ.get("LIMEN_LANE_TIMEOUT"), 900) + 600


def _parse_ts(v):
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def _logical_session(entry):
    return str(entry.get("logical_session_id") or entry.get("session_id") or "")


def chronic_tasks(all_tasks, min_reopens=3, eligible_dispatched_ids=None):
    """Unowned tasks reopened by heal/recover >= min_reopens times without producing a PR.

    These churn across lanes (fail/orphan → reopen → fail again) burning capacity with zero
    output. Per 'stale = opportunity, not delete': SURFACE them for escalation (route to the
    one capable lane / human eyes), don't silently re-loop and don't cancel real work. A terminal
    failed attempt with an active typed owner for the same exact PR receipt is historical, not
    chronic; the owner task remains accountable for the leaf."""
    eligible_dispatched_ids = set(eligible_dispatched_ids or [])
    out = []
    for t in all_tasks:
        status = t.get("status", "open")
        tid = t.get("id")
        if status not in {"open", "failed"} and not (status == "dispatched" and tid in eligible_dispatched_ids):
            continue
        if WORKSTREAM_SUCCESSOR_REQUIRED_LABEL in (t.get("labels") or []):
            continue
        log = t.get("dispatch_log") or []
        # every reopen mechanism (release-stale / recover / heal-dispatch) appends a
        # status=="open" entry — count those, robust across all three.
        reopens = sum(1 for e in log if str(e.get("status")) == "open")
        ever_pr = any(PR_RE.search(_logical_session(e)) for e in log)
        if reopens < min_reopens or ever_pr:
            continue
        if active_typed_pr_owner_id(t, all_tasks) is not None:
            continue
        out.append((tid, t.get("target_agent"), reopens, t.get("repo")))
    return out


def gh_pr_state(owner, repo, num):
    """Return (exists, state) where state in MERGED/OPEN/CLOSED, or (False, None)."""
    try:
        out = subprocess.run(
            ["gh", "pr", "view", num, "--repo", f"{owner}/{repo}", "--json", "state,mergedAt"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if out.returncode != 0:
            return False, None  # PR not found / repo gone
        d = json.loads(out.stdout)
        if d.get("mergedAt"):
            return True, "MERGED"
        return True, d.get("state", "OPEN")  # OPEN or CLOSED
    except Exception:
        return False, None


def main():
    limit = None
    quiet = "--quiet" in sys.argv
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])

    d = yaml.safe_load((ROOT / "tasks.yaml").read_text()) or {}
    dispatched = [t for t in d.get("tasks", []) if t.get("status") == "dispatched"]
    if limit:
        dispatched = dispatched[:limit]

    cats = {
        k: []
        for k in (
            "PR_OPEN",
            "PR_MERGED",
            "PR_CLOSED",
            "PR_MISSING",
            "DISPATCHED_NO_PR",
            "DISPATCHED_RUNNING",
            "JULES_ASYNC",
        )
    }
    now = datetime.now(timezone.utc)

    for t in dispatched:
        tid = t.get("id")
        agent = t.get("target_agent")
        log = t.get("dispatch_log") or []
        sid = _logical_session(log[-1]) if log else ""
        m = PR_RE.search(str(sid))
        if m:
            owner, repo, num = m.group(1), m.group(2), m.group(3)
            exists, state = gh_pr_state(owner, repo, num)
            if not exists:
                cats["PR_MISSING"].append((tid, sid))
            elif state == "MERGED":
                cats["PR_MERGED"].append((tid, f"{owner}/{repo}#{num}"))
            elif state == "CLOSED":
                cats["PR_CLOSED"].append((tid, f"{owner}/{repo}#{num}"))
            else:
                cats["PR_OPEN"].append((tid, f"{owner}/{repo}#{num}"))
        elif agent == "jules":
            cats["JULES_ASYNC"].append((tid, str(sid)[:40]))
        else:
            # local lane, no PR URL: in-flight (reserved recently, still running) vs.
            # genuinely STRANDED (reserve never committed — crash/kill/timeout left it stuck)
            upd = _parse_ts(t.get("updated"))
            # ASYNC engine: a live .running marker means a detached worker is still on it — never
            # reopen those (would dup). No-op in sync mode (no markers exist). See dispatch-async.py.
            async_running = (ROOT / "logs" / "async-runs").exists() and any(
                (ROOT / "logs" / "async-runs").glob(f"{tid}__*.running")
            )
            if async_running or (upd and (now - upd).total_seconds() < GRACE):
                cats["DISPATCHED_RUNNING"].append((tid, agent))
            else:
                cats["DISPATCHED_NO_PR"].append((tid, agent))

    report = {k: [{"id": a, "ref": b} for a, b in v] for k, v in cats.items()}
    counts = {k: len(v) for k, v in cats.items()}
    no_pr_ids = {tid for tid, _ in cats["DISPATCHED_NO_PR"]}
    chronic = chronic_tasks(d.get("tasks", []), eligible_dispatched_ids=no_pr_ids)
    counts["CHRONIC"] = len(chronic)
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs" / "dispatch-verify.json").write_text(
        json.dumps(
            {
                "counts": counts,
                "detail": report,
                "chronic": [{"id": i, "agent": a, "reopens": r, "repo": rp} for i, a, r, rp in chronic],
            },
            indent=2,
        )
    )

    if not quiet:
        print(f"=== DISPATCH VERIFICATION ({len(dispatched)} dispatched tasks) ===")
        healthy = ("PR_OPEN", "JULES_ASYNC", "DISPATCHED_RUNNING")
        for k in (
            "PR_OPEN",
            "JULES_ASYNC",
            "DISPATCHED_RUNNING",
            "PR_MERGED",
            "PR_CLOSED",
            "PR_MISSING",
            "DISPATCHED_NO_PR",
        ):
            n = counts[k]
            flag = "  " if k in healthy else "⚠ "
            print(f"{flag}{k:18} {n}")
        # loud detail on the actionable failure classes
        for k in ("PR_MERGED", "PR_CLOSED", "PR_MISSING", "DISPATCHED_NO_PR"):
            for it in cats[k]:
                print(f"    {k}: {it[0]}  {it[1]}")
        actionable = sum(counts[k] for k in ("PR_MERGED", "PR_CLOSED", "PR_MISSING", "DISPATCHED_NO_PR"))
        print(f"--- {actionable} actionable (merged→harvest, closed/missing→recover) ---")
        if chronic:
            print(
                f"\n⚑ CHRONIC ({len(chronic)}) — reopened ≥3×, never a PR, "
                "no active typed owner (escalate, don't re-loop):"
            )
            for i, a, r, rp in chronic:
                print(f"    {i}  {a}  {r} reopens  {rp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
