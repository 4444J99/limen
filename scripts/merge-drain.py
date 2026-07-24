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

It also REFUSES stale-base PRs (the #111 guard) unless the target branch positively exposes an
active merge queue. The queue validates an exact-head merge group against current base; absent or
unknown queue capability keeps the rebase-to-current route. ([[pr111-daemon-regression-healed]])

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
from _pr_scan import (  # noqa: E402
    enumerate_open_prs,
    merge_queue_capability,
    rotating_window,
    stale_base_verdict,
)

# DERIVED from env (derive-not-pin) so the conductor survives relocation; same default + classifier
# as self-heal.py — the two organs are two halves of one verdict and must agree on the PR universe.
OWNERS = [o.strip() for o in os.environ.get("LIMEN_OWNERS", "organvm,4444J99").split(",") if o.strip()]
ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
LOG = ROOT / "logs" / "merge-drain.log"
POLICY = ROOT / "scripts" / "merge-policy.sh"
LIFECYCLE_LABELS = frozenset(
    {
        "lifecycle:delivery",
        "lifecycle:preservation",
        "lifecycle:active-human",
        "lifecycle:blocked",
        "lifecycle:superseded",
    }
)


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


def lifecycle_disposition(labels) -> str | None:
    names = {
        str(label.get("name") if isinstance(label, dict) else label).strip().lower()
        for label in (labels or [])
    }
    matches = names & LIFECYCLE_LABELS
    return next(iter(matches)) if len(matches) == 1 else None


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
                (
                    "mergeable,mergeStateStatus,state,statusCheckRollup,isDraft,files,"
                    "baseRefName,headRefOid,labels"
                ),
            ],
            timeout=40,
        )
        if r.returncode != 0:
            return (repo, num, "ERR")
        d = json.loads(r.stdout)
        if d.get("state") != "OPEN" or d.get("isDraft"):
            return (repo, num, "SKIP")
        disposition = lifecycle_disposition(d.get("labels"))
        if disposition is None:
            return (repo, num, "LIFECYCLE-UNKNOWN")
        if disposition != "lifecycle:delivery":
            return (repo, num, disposition.removeprefix("lifecycle:").upper())
        if d.get("mergeable") == "CONFLICTING":
            return (repo, num, "CONFLICT")
        states = [(c.get("conclusion") or c.get("state") or "") for c in (d.get("statusCheckRollup") or [])]
        if any(s in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED") for s in states):
            return (repo, num, "CI-RED")
        if any(s in ("PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", "") for s in states):
            return (repo, num, "CI-PENDING")
        if d.get("mergeable") == "MERGEABLE":
            # STALE-BASE GATE (kept identical to self-heal.assess — one verdict): only a positively
            # detected active queue can accept a stale exact head. GitHub then synthesizes and
            # validates the current-base merge group; absent/unknown preserves the rebase guard.
            paths = [f.get("path", "") for f in (d.get("files") or [])]
            sb = stale_base_verdict(repo, paths, d.get("baseRefName"), d.get("headRefOid"), gh)
            queue_capability = merge_queue_capability(repo, d.get("baseRefName"), gh)
            if sb and queue_capability != "active":
                return (repo, num, sb)  # STALE-CORE / STALE-BASE — do NOT auto-merge; rebase first
            if _is_trivial(repo, num):
                return (repo, num, "TRIVIAL")  # CI-green but no-op/reformat — value gate refuses it
            head = str(d.get("headRefOid") or "")
            if not head:
                return (repo, num, "ERR")
            mode_hint = "queue" if queue_capability == "active" else "direct"
            return (repo, num, "READY", head, mode_hint)
        return (repo, num, "BLOCKED")
    except Exception:
        return (repo, num, "ERR")


def _queue_state(repo, num):
    """Return exact live PR state before a queue effect; ``None`` fails closed."""
    r = gh(
        [
            "pr",
            "view",
            str(num),
            "-R",
            repo,
            "--json",
            "state,headRefOid,mergeStateStatus,autoMergeRequest",
        ],
        timeout=40,
    )
    if r.returncode != 0:
        return None
    try:
        d = json.loads(r.stdout)
    except (TypeError, ValueError):
        return None
    return {
        "state": str(d.get("state") or ""),
        "head": str(d.get("headRefOid") or ""),
        "queued": d.get("autoMergeRequest") is not None or d.get("mergeStateStatus") == "QUEUED",
    }


def _merge_policy(repo, num, expected_head):
    """Re-run the one authority immediately before mutation and return its exact mode."""
    r = subprocess.run(
        [
            str(POLICY),
            str(num),
            "--repo",
            repo,
            "--expected-head",
            expected_head,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if r.returncode != 0:
        return None
    out = r.stdout + r.stderr
    mode = ""
    head = ""
    for line in out.splitlines():
        if line.startswith("MERGE-MODE: "):
            mode = line.removeprefix("MERGE-MODE: ").strip()
        elif line.startswith("MERGE-HEAD: "):
            head = line.removeprefix("MERGE-HEAD: ").split(maxsplit=1)[0]
    if mode not in {"queue", "direct"} or head != expected_head:
        return None
    return mode


def merge(repo, num, expected_head, mode_hint):
    """Perform at most one exact-head effect; never fall back across merge methods.

    Queue mode is idempotent and returns ``QUEUED`` rather than manufacturing a merge receipt.
    The final policy invocation is adjacent to the effect, invalidating stale batch assessments.
    """
    if mode_hint == "queue":
        current = _queue_state(repo, num)
        if current is None or current["head"] != expected_head:
            return "FAILED"
        if current["state"] == "MERGED":
            return "MERGED"
        if current["state"] != "OPEN":
            return "FAILED"
        if current["queued"]:
            return "QUEUED"

    mode = _merge_policy(repo, num, expected_head)
    if mode is None or mode != mode_hint:
        return "FAILED"
    if mode == "queue":
        args = [
            "pr",
            "merge",
            str(num),
            "-R",
            repo,
            "--auto",
            "--match-head-commit",
            expected_head,
        ]
        success = "QUEUED"
    else:
        args = [
            "pr",
            "merge",
            str(num),
            "-R",
            repo,
            "--squash",
            "--match-head-commit",
            expected_head,
        ]
        success = "MERGED"
    r = gh(args, timeout=90)
    return success if r.returncode == 0 else "FAILED"


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
    ready = [(r[0], r[1], r[3], r[4]) for r in rows if r[2] == "READY"][: a.limit]
    merged = []
    queued = []
    if not a.dry_run:
        for repo, num, head, mode_hint in ready:
            outcome = merge(repo, num, head, mode_hint)
            if outcome == "MERGED":
                merged.append(f"{repo}#{num}")
            elif outcome == "QUEUED":
                queued.append(f"{repo}#{num}@{head[:12]}")
    ts = datetime.datetime.now().strftime("%F %T")
    summary = (
        f"[merge-drain] {ts} window={len(prs)}/{len(allprs)} ready={b['READY']} "
        f"merged={len(merged)} queued={len(queued)} trivial-skipped={b['TRIVIAL']} | "
        f"blocked: conflict={b['CONFLICT']} "
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
            effects = merged + [f"QUEUED:{item}" for item in queued]
            f.write(summary + (("  " + " ".join(effects)) if effects else "") + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    main()
