#!/usr/bin/env python3
"""merge-drain.py — the MISSING merge organ of the heartbeat.

The loop lands PRs every beat (dispatch + jules-land) but nothing ever MERGED them, so
open PRs piled up until a human ran a manual drain. This makes merge autonomic: every
drain beat it merges the PRs that are genuinely READY (mergeable + CI-green), surfaces
the blocked ones, and NEVER force-merges. Bounded per run so it never dominates a beat.
Idempotent and concurrency-safe: if another agent already merged a PR, gh reports it and
we count it, no error. It preserves source branches; branch cleanup is a separate accepted reap.
Touches only GitHub — not tasks.yaml ownership or agent worktrees — so it cannot race the
dispatcher.

It also REFUSES stale-base PRs (the #111 guard): a mergeable+green PR that branched from an old
base can silently REVERT work that landed since — self-heal reroutes those to a rebase-onto-current
task instead of letting them clobber the body. ([[pr111-daemon-regression-healed]])

  --scan N      assess WINDOW per run — PRs classified this beat, rotating over the full backlog
  --scan-max N  cap on the cheap full-fleet enumeration the window draws from (default 500)
  --limit N     max PRs to merge this run   (default 10)
  --dry-run     assess + report only (cursor untouched)
"""

import argparse
import concurrent.futures as cf
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling scripts/ for _pr_scan, _notify
import _notify  # noqa: E402
from _pr_scan import enumerate_open_prs, rotating_window, stale_base_verdict  # noqa: E402

# DERIVED from env (derive-not-pin) so the conductor survives relocation; same default + classifier
# as self-heal.py — the two organs are two halves of one verdict and must agree on the PR universe.
OWNERS = [o.strip() for o in os.environ.get("LIMEN_OWNERS", "organvm,4444J99").split(",") if o.strip()]
ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
LOG = ROOT / "logs" / "merge-drain.log"


def gh(args, timeout=60):
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)


def _is_trivial(repo, num):
    """True if the PR diff is a no-op / pure reformat (whitespace or line-ending only) or empty — the
    'green-checkmark noise' class (e.g. a CIFIX that only normalized CRLF->LF, showing 436/436 lines).
    A VALUE gate ON TOP of the CI gate: refuse to auto-merge these. Conservative + fail-open: any real
    content change, or any error fetching the diff, -> NOT trivial (defer to the existing CI gate)."""
    r = gh(["pr", "diff", str(num), "-R", repo], timeout=60)
    if r.returncode != 0:
        return False
    added, removed = [], []
    for ln in r.stdout.splitlines():
        if ln.startswith(
            (
                "+++",
                "---",
                "diff ",
                "index ",
                "@@",
                "old mode",
                "new mode",
                "similarity",
                "rename",
                "deleted file",
                "new file",
                "Binary",
            )
        ):
            continue
        if ln.startswith("+"):
            added.append(ln[1:].strip())
        elif ln.startswith("-"):
            removed.append(ln[1:].strip())
    if not added and not removed:
        return True  # empty diff
    # added==removed after stripping whitespace/EOL -> no net content change -> pure reformat no-op
    return sorted(x for x in added if x) == sorted(x for x in removed if x)


def assess(rn):
    repo, num = rn
    try:
        r = gh(
            [
                "pr",
                "view",
                str(num),
                "-R",
                repo,
                "--json",
                "mergeable,mergeStateStatus,state,statusCheckRollup,isDraft,files,baseRefName,headRefOid",
            ],
            timeout=40,
        )
        if r.returncode != 0:
            return (repo, num, "ERR")
        d = json.loads(r.stdout)
        if d.get("state") != "OPEN" or d.get("isDraft"):
            return (repo, num, "SKIP")
        if d.get("mergeable") == "CONFLICTING":
            return (repo, num, "CONFLICT")
        states = [(c.get("conclusion") or c.get("state") or "") for c in (d.get("statusCheckRollup") or [])]
        if any(s in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED") for s in states):
            return (repo, num, "CI-RED")
        if any(s in ("PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", "") for s in states):
            return (repo, num, "CI-PENDING")
        if d.get("mergeable") == "MERGEABLE":
            # STALE-BASE GATE (kept identical to self-heal.assess — one verdict): a green+mergeable
            # PR off an OLD base can silently revert work it never meant to touch (#111). Refuse it
            # here; self-heal reroutes it to a rebase-onto-current task. One bounded compare call.
            paths = [f.get("path", "") for f in (d.get("files") or [])]
            sb = stale_base_verdict(repo, paths, d.get("baseRefName"), d.get("headRefOid"), gh)
            if sb:
                return (repo, num, sb)  # STALE-CORE / STALE-BASE — do NOT auto-merge; rebase first
            if _is_trivial(repo, num):
                return (repo, num, "TRIVIAL")  # CI-green but no-op/reformat — value gate refuses it
            return (repo, num, "READY")
        return (repo, num, "BLOCKED")
    except Exception:
        return (repo, num, "ERR")


def merge(repo, num):
    for m in ("--squash", "--merge", "--rebase"):
        r = gh(["pr", "merge", str(num), "-R", repo, m], timeout=90)
        out = (r.stdout + r.stderr).lower()
        if r.returncode == 0 or "merged" in out:
            return True
        if "not allowed" in out or "not enabled" in out:
            continue
        return False
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--scan",
        type=int,
        default=int(os.environ.get("LIMEN_MERGE_SCAN", "30")),
        help="assess WINDOW per run — PRs classified this beat, rotating",
    )
    ap.add_argument(
        "--scan-max",
        type=int,
        default=int(os.environ.get("LIMEN_MERGE_SCAN_MAX", "500")),
        help="cap on the cheap full-fleet enumeration the window draws from",
    )
    ap.add_argument("--limit", type=int, default=int(os.environ.get("LIMEN_MERGE_LIMIT", "10")))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    # FULL-FLEET coverage (shared with self-heal): enumerate every open PR once, assess a rotating
    # --scan window this beat so a READY PR below the old head-of-list 30 finally gets landed
    # instead of sitting forever. Own cursor so MERGE and HEAL rotate independently.
    allprs = enumerate_open_prs(OWNERS, gh, max_total=a.scan_max, want_url=False)
    if not allprs:
        print("[merge-drain] no open PRs (or gh unavailable)")
        return
    prs = rotating_window(allprs, a.scan, str(ROOT / "logs" / ".pr-scan-cursor.merge"), persist=not a.dry_run)
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        rows = list(ex.map(assess, prs))
    import collections

    b = collections.Counter(r[2] for r in rows)
    ready = [(r[0], r[1]) for r in rows if r[2] == "READY"][: a.limit]
    merged = []
    if not a.dry_run:
        for repo, num in ready:
            if merge(repo, num):
                merged.append(f"{repo}#{num}")
    ts = datetime.datetime.now().strftime("%F %T")
    summary = (
        f"[merge-drain] {ts} window={len(prs)}/{len(allprs)} ready={b['READY']} "
        f"merged={len(merged)} trivial-skipped={b['TRIVIAL']} | blocked: conflict={b['CONFLICT']} "
        f"ci-red={b['CI-RED']} ci-pending={b['CI-PENDING']} "
        f"stale-core={b['STALE-CORE']} stale-base={b['STALE-BASE']}"
    )
    print(summary)
    # LOUD trunk state (IF-HOST-PRESSURE form-4 sibling): a green-blocked PR skipped as CI-RED was a
    # silent log line only — announce the condition once per onset, clear when the window shows none,
    # so a fleet-wide CI jam (e.g. the 2026-07-17 billing outage) is felt without reading beat logs.
    if b["CI-RED"]:
        _notify.notify_once(
            ROOT,
            "merge-drain-ci-red",
            f"{b['CI-RED']} open PR(s) skipped green-blocked (CI-RED) this drain beat",
            title="LIMEN merge drain",
        )
    else:
        _notify.clear_condition(ROOT, "merge-drain-ci-red")
    try:
        with open(LOG, "a") as f:
            f.write(summary + (("  " + " ".join(merged)) if merged else "") + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    main()
