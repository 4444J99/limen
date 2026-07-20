#!/usr/bin/env python3
"""self-heal.py — the SELF-HEAL rung of the self-* ladder.

merge-drain.py merges the PRs that are genuinely READY and correctly REFUSES the ones that
are CI-RED or CONFLICTING. But nothing fixes those refused PRs, so the open-PR floor never
falls — the stuck pile just sits. This organ closes that gap: every heal beat it assesses the
open PRs (exactly as merge-drain does), and for each CI-RED or CONFLICT PR it EMITS a targeted
heal task into the queue so the existing router+dispatcher picks it up and an agent fixes the
PR in a worktree → the PR turns mergeable → merge-drain lands it next beat → the floor drops.

This is alchemical progress toward ideal form (the fleet repairing its OWN work), NOT reduction.

Safety / shape (matches the sibling organs exactly):
  • SCAN side is identical to merge-drain.py (same OWNERS, same `gh search prs --author @me`,
    the same assess() classifier: READY / CI-RED / CI-PENDING / CONFLICT). Read-only `gh`.
  • EMIT side acquires the daemon's queue-lock (logs/.queue.lock.d, the heal-dispatch.py
    convention), RELOADS the read-only projection under the lock, constructs validated Limen Task
    objects, and submits the delta through TABVLARIVS. The remote keeper is the only lifecycle
    writer; this organ never rewrites tasks.yaml or pushes the default branch.
  • IDEMPOTENT: each heal task has a STABLE id derived from kind+owner+repo+num
    (HEAL-cifix-… / HEAL-rebase-…). If that id already exists in tasks.yaml (any status), no
    duplicate is emitted — re-running is a no-op until the PR's state changes.
  • FULL COVERAGE, BOUNDED COST: one cheap enumeration of EVERY open PR (shared _pr_scan), then a
    rotating --scan window is assessed per beat (default 30) so the whole backlog is covered over
    successive beats — not just the head-of-list 30 forever. --limit caps heal tasks emitted this
    run (default 10, lifted up to 3x when vendor capacity is idle). Never dispatches/merges/pushes.

  --scan N      assess WINDOW per run — PRs classified this beat, rotating (default 30)
  --scan-max N  cap on the cheap full-fleet enumeration the window draws from (default 500)
  --limit N     max heal tasks to EMIT this run, headroom-scaled (default 10)
  --dry-run     assess + report what WOULD be emitted; make ZERO writes (cursor + lock untouched)
"""

import argparse
import collections
import concurrent.futures as cf
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling scripts/ for _pr_scan
from limen.io import load_limen_file  # noqa: E402
from limen.intake import contract_fields, github_existing_pr_contract  # noqa: E402
from limen.models import Task  # noqa: E402
from limen.tabularius import apply_limen_file_sync  # noqa: E402
from _pr_scan import (  # noqa: E402
    enumerate_open_prs,
    merge_queue_capability,
    rotating_window,
    scaled_limit,
    stale_base_verdict,
)

# DERIVED from env so the conductor survives relocation; same defaults as merge-drain.py.
OWNERS = [o.strip() for o in os.environ.get("LIMEN_OWNERS", "organvm,4444J99").split(",") if o.strip()]
ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
LOCKD = ROOT / "logs" / ".queue.lock.d"
LOG = ROOT / "logs" / "self-heal.log"
HEAL_CONVERGENCE = ROOT / "logs" / "heal-convergence.json"
CHRONIC_MAX_AGE_SECONDS = 2 * 60 * 60

# the heal kinds this organ emits, keyed by the classifier verdict it reacts to.
KINDS = {
    "CI-RED": {
        "slug": "cifix",
        "priority": "high",
        "labels": ["cifix", "self-heal", "ci-red"],
        "title": "fix failing CI on {repo}#{num}",
        "context": (
            "PR {repo}#{num} has FAILING CI checks and merge-drain correctly refuses to merge "
            "it. Check out the PR branch, find the root cause of the red checks (lint / types / "
            "failing test / config), fix it, push to the SAME PR branch, and confirm every check "
            "goes green. If the branch ALSO rolls back base content its title/body never declared "
            "(a poisoned/stale generated tree), restore base's side of those paths rather than "
            "repairing on top of a rollback. Do not open a new PR — repair the existing one so "
            "merge-drain lands it. PR: {url}"
        ),
    },
    "CONFLICT": {
        "slug": "rebase",
        "priority": "high",
        "labels": ["rebase", "self-heal", "conflict"],
        "title": "rebase/resolve conflicts on {repo}#{num}",
        "context": (
            "PR {repo}#{num} is CONFLICTING with its base branch and merge-drain correctly "
            "refuses to merge it. FIRST check the PR's ORIGINAL diff (merge-base..head) against "
            "its declared title/body intent: a branch generated from a broken tree can carry mass "
            "deletions it never declared, and branch-side deletions the declaration does not name "
            "are POISON to restore from base, never intent to preserve (session-meta#148 ate "
            "ingest/ + 3 test suites this way). Then check out the PR branch, rebase it onto the "
            "current base (or merge base in), resolve every conflict preserving the PR's declared "
            "intent, push to the SAME PR branch, and confirm it reports MERGEABLE with green CI. "
            "After resolving, verify diff-vs-base matches the declared intent; if nothing genuine "
            "survives (all absorbed or superseded on base), close the PR as superseded instead of "
            "pushing. Do not open a new PR. PR: {url}"
        ),
    },
    # STALE-BASE family — the #111 guard. When queue capability is absent/unknown, a mergeable+green
    # PR off an OLD base can silently REVERT work that landed since, so these tasks rebase it onto
    # CURRENT base. An active queue instead validates a current-base merge group and must not spawn
    # rebase churn. ([[pr111-daemon-regression-healed]])
    "STALE-CORE": {
        "slug": "rebase-stale",
        "priority": "high",
        "labels": ["rebase", "self-heal", "stale-base", "core"],
        "title": "rebase {repo}#{num} onto current base — stale base touches the daemon body",
        "context": (
            "PR {repo}#{num} is MERGEABLE + green BUT its base is STALE and its diff touches CORE "
            "daemon files (cli/src/limen, scripts/*.py|sh, mcp/src, web/api, container). Merging "
            "as-is would silently REVERT newer code on the base — the #111 failure mode. Check out "
            "the PR branch and REBASE it onto the CURRENT base (git fetch origin && git rebase "
            "origin/<base>). During the rebase, KEEP every change that is genuinely this PR's own "
            "work and DROP any hunk that would revert a file the PR did not intend to change "
            "(especially core files it only carries because it branched old). Push --force-with-lease "
            "to the SAME PR branch; confirm it reports MERGEABLE, current with base, and green. Do "
            "NOT open a new PR and do NOT drop any unique work — absorb the branch toward current "
            "ideal form. PR: {url}"
        ),
    },
    "STALE-BASE": {
        "slug": "rebase-stale",
        "priority": "normal",
        "labels": ["rebase", "self-heal", "stale-base"],
        "title": "rebase {repo}#{num} onto current base — branched far behind",
        "context": (
            "PR {repo}#{num} is MERGEABLE + green but branched well behind its current base — the "
            "structural condition for a stale-base silent revert. Check out the branch, REBASE it "
            "onto the current base, KEEP all of the PR's genuine changes and DROP any hunk that "
            "merely reverts base files it didn't mean to touch, push --force-with-lease to the SAME "
            "branch, and confirm MERGEABLE + current + green. Do NOT open a new PR; preserve all "
            "unique work. PR: {url}"
        ),
    },
    # REVIEW-FEEDBACK — the ping-pong half of the multi-agent review engine (estate.yaml
    # integrations, category review). NOT an assess() verdict: assess stays verbatim-identical to
    # merge-drain.assess (one shared verdict), and this is a post-assess RECLASSIFICATION of READY
    # PRs that sit green+mergeable while review threads wait on our reply.
    "REVIEW-FEEDBACK": {
        "slug": "review",
        "priority": "normal",
        "labels": ["review", "self-heal", "review-feedback"],
        "title": "address review feedback on {repo}#{num}",
        "context": (
            "PR {repo}#{num} is green and mergeable BUT carries unresolved review threads (or a "
            "standing CHANGES_REQUESTED review) from the multi-agent review engine — the ping-pong "
            "is waiting on our half. Check out the PR branch and read EVERY unresolved thread. For "
            "each one: fix the code and push to the SAME branch, or reply with a short factual "
            "reason why not. Then reply on each thread and RESOLVE it; if a reviewer holds "
            "CHANGES_REQUESTED, re-request review (post '@claude' / '/gemini review' to re-summon "
            "those agents). Never resolve a thread without either a fix or a reply, and do NOT "
            "open a new PR — once threads are resolved and CI is green, merge-drain lands it. "
            "PR: {url}"
        ),
    },
}

# Active states for a HEAL-mainred task — mirrors dispatch._ACTIVE_SUPERSEDER_STATUSES
# and check-main-green._ACTIVE_STATES. When trunk repair is in one of these, individual
# PR CI-fix tasks are redundant (limen#895).
_MAINRED_ACTIVE_STATUSES = frozenset({"open", "dispatched", "in_progress", "needs_human", "failed_blocked"})


def gh(args, timeout=60):
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)


def review_feedback(repo, num):
    """True ⟺ the PR carries unresolved review threads or a standing CHANGES_REQUESTED review —
    the ping-pong signal from the multi-agent review engine. One GraphQL read; fail-OPEN (False)
    so a hiccup never spawns phantom heal tasks. Kept OUTSIDE assess(): that block stays
    verbatim-identical to merge-drain.assess, and REVIEW-FEEDBACK is a post-assess
    reclassification only self-heal performs."""
    try:
        owner, name = repo.split("/", 1)
        q = (
            "query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){"
            "reviewThreads(first:100){nodes{isResolved}}"
            "reviews(last:20){nodes{state}}}}}"
        )
        r = gh(["api", "graphql", "-f", f"query={q}", "-F", f"o={owner}", "-F", f"r={name}", "-F", f"n={num}"])
        if r.returncode != 0:
            return False
        d = json.loads(r.stdout or "{}")["data"]["repository"]["pullRequest"]
        unresolved = sum(1 for t in (d.get("reviewThreads") or {}).get("nodes") or [] if not t.get("isResolved"))
        states = [s.get("state") for s in (d.get("reviews") or {}).get("nodes") or []]
        changes_requested = bool(states) and states[-1] == "CHANGES_REQUESTED"
        return unresolved > 0 or changes_requested
    except Exception:
        return False


def assess(pr):
    # identical classification logic to merge-drain.py.assess (kept verbatim so the two organs
    # always agree on what is READY vs CI-RED vs CONFLICT — they are two halves of one verdict).
    repo, num, url = pr
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
            return (repo, num, url, "ERR", [])
        d = json.loads(r.stdout)
        if d.get("state") != "OPEN" or d.get("isDraft"):
            return (repo, num, url, "SKIP", [])
        if d.get("mergeable") == "CONFLICTING":
            return (repo, num, url, "CONFLICT", [])
        rollup = d.get("statusCheckRollup") or []
        states = [(c.get("conclusion") or c.get("state") or "") for c in rollup]
        if any(s in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED") for s in states):
            failing_checks = sorted(
                {
                    str(check.get("name") or "?")
                    for check in rollup
                    if (check.get("conclusion") or check.get("state") or "")
                    in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED")
                }
            )
            return (repo, num, url, "CI-RED", failing_checks)
        if any(s in ("PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", "") for s in states):
            return (repo, num, url, "CI-PENDING", [])
        if d.get("mergeable") == "MERGEABLE":
            # STALE-BASE GATE (identical to merge-drain.assess — one verdict): only a positively
            # detected active queue makes a stale exact head queueable. Absent/unknown preserves
            # the rebase-to-current heal route.
            paths = [f.get("path", "") for f in (d.get("files") or [])]
            sb = stale_base_verdict(repo, paths, d.get("baseRefName"), d.get("headRefOid"), gh)
            queue_capability = merge_queue_capability(repo, d.get("baseRefName"), gh)
            if sb and queue_capability != "active":
                return (repo, num, url, sb, [])  # STALE-CORE / STALE-BASE → rebase task below
            return (repo, num, url, "READY", [])
        return (repo, num, url, "BLOCKED", [])
    except Exception:
        return (repo, num, url, "ERR", [])


def live_chronic_groups(path=HEAL_CONVERGENCE, *, now=None):
    """Fresh ``(repo, failing-check)`` groups from the convergence sensor's live receipt.

    A stale or malformed receipt cannot freeze new work indefinitely. The next metabolize/heartbeat
    refresh repairs the gap; until then self-heal falls back to its existing idempotent behavior.
    """

    now = now or datetime.datetime.now(datetime.timezone.utc)
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        generated = datetime.datetime.fromisoformat(str(payload["timestamp"]).replace("Z", "+00:00"))
    except (OSError, ValueError, KeyError, TypeError):
        return set()
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=datetime.timezone.utc)
    age_seconds = (now - generated.astimezone(datetime.timezone.utc)).total_seconds()
    if age_seconds < 0 or age_seconds > CHRONIC_MAX_AGE_SECONDS:
        return set()
    return {
        (str(group.get("repo") or ""), str(group.get("check") or ""))
        for group in payload.get("chronic") or []
        if isinstance(group, dict) and group.get("repo") and group.get("check")
    }


def task_id(kind_slug, repo, num):
    # stable id → idempotency. repo is owner/name; slugify both halves like generate-backlog.
    slug = repo.replace("/", "-").lower()
    return f"HEAL-{kind_slug}-{slug}-{num}"


def build_task(verdict, repo, num, url, stamp):
    spec = KINDS[verdict]
    contract = contract_fields(github_existing_pr_contract(repo, num))
    return Task(
        id=task_id(spec["slug"], repo, num),
        title=spec["title"].format(repo=repo, num=num),
        repo=repo,
        type="code",
        target_agent="any",
        priority=spec["priority"],
        budget_cost=1,
        status="open",
        labels=list(spec["labels"]),
        urls=[url] if url else [],
        context=spec["context"].format(repo=repo, num=num, url=url or f"{repo}#{num}")
        + f" [auto-emitted {stamp} by self-heal so merge-drain can land it]",
        **contract,
        depends_on=[],
        created=stamp,
        dispatch_log=[],
    )


def acquire_lock(timeout=15):
    for _ in range(timeout):
        try:
            LOCKD.mkdir()
            return True
        except FileExistsError:
            time.sleep(1)
    return False


def env_int(name, default):
    try:
        value = int(os.environ.get(name, str(default)) or str(default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def parse_pr_spec(raw):
    value = str(raw or "").strip()
    if not value:
        raise argparse.ArgumentTypeError("empty PR spec")
    if "github.com/" in value:
        tail = value.split("github.com/", 1)[1].strip("/")
        parts = tail.split("/")
        if len(parts) >= 4 and parts[2] in {"pull", "pulls"} and parts[3].isdigit():
            repo = f"{parts[0]}/{parts[1]}"
            num = int(parts[3])
            return repo, num, f"https://github.com/{repo}/pull/{num}"
    if "#" in value:
        repo, num = value.rsplit("#", 1)
        repo = repo.strip().strip("/")
        if "/" in repo and num.strip().isdigit():
            return repo, int(num), f"https://github.com/{repo}/pull/{int(num)}"
    raise argparse.ArgumentTypeError(f"expected owner/repo#number or GitHub PR URL, got {raw!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--scan",
        type=int,
        default=env_int("LIMEN_HEAL_SCAN", 30),
        help="assess WINDOW per run — how many PRs to classify this beat (rotates)",
    )
    ap.add_argument(
        "--scan-max",
        type=int,
        default=env_int("LIMEN_HEAL_SCAN_MAX", 500),
        help="cap on the cheap full-fleet enumeration the rotating window draws from",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=env_int("LIMEN_HEAL_LIMIT", 10),
        help="max heal tasks to EMIT this run (headroom-scaled up to 3x on a full tank)",
    )
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", str(ROOT / "tasks.yaml")))
    ap.add_argument(
        "--pr",
        action="append",
        type=parse_pr_spec,
        default=[],
        help="assess an explicit PR owner/repo#number or GitHub PR URL instead of the rotating search window",
    )
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    # FULL-FLEET coverage: one cheap enumeration of EVERY open PR (not just the first 30), then
    # assess a rotating window of --scan PRs this beat. Over a full rotation every red/conflict PR
    # gets seen → a heal task → merge-drain lands it. The cursor is per-organ so HEAL and MERGE
    # rotate independently. ([[self-star-ladder-shipped-live]])
    allprs = list(a.pr) if a.pr else enumerate_open_prs(OWNERS, gh, max_total=a.scan_max, want_url=True)
    if not allprs:
        print("[self-heal] no open PRs (or gh unavailable)")
        return 0
    if a.pr:
        prs = allprs
    else:
        cursor = ROOT / "logs" / ".pr-scan-cursor.heal"
        prs = rotating_window(allprs, a.scan, str(cursor), persist=not a.dry_run)
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        rows = list(ex.map(assess, prs))
    b = collections.Counter(r[3] for r in rows)

    # the stuck PRs this organ exists to heal, capped per run (the cap lifts when vendor capacity
    # is idle, so a full tank drains the red pile faster instead of trickling 10/beat).
    limit = scaled_limit(a.limit, ROOT)
    chronic = live_chronic_groups()
    frozen = []
    sick = []
    review_fb = 0
    for repo, num, url, verdict, failing_checks in rows:
        chronic_hits = sorted(check for check in failing_checks if (repo, check) in chronic)
        if verdict == "CI-RED" and failing_checks and len(chronic_hits) == len(failing_checks):
            frozen.append((repo, num, chronic_hits))
            continue
        # The ping-pong reclassification: a READY PR (green+mergeable) sitting on unresolved review
        # threads is waiting on OUR reply — one extra GraphQL read, READY PRs only (bounded by the
        # scan window), post-assess so the shared verdict block stays verbatim.
        if verdict == "READY" and review_feedback(repo, num):
            verdict = "REVIEW-FEEDBACK"
            review_fb += 1
        if verdict in KINDS:
            sick.append((verdict, repo, num, url))
    sick = sick[:limit]
    stamp = datetime.date.today().isoformat()

    tasks_path = Path(a.tasks)

    # DRY-RUN: assess + report only. Zero writes; the queue-lock is never even touched.
    if a.dry_run:
        tasks = load_limen_file(tasks_path).tasks if tasks_path.exists() else []
        tasks_by_id = {t.id: t for t in tasks}
        would, dup = [], 0
        for verdict, repo, num, url in sick:
            tid = task_id(KINDS[verdict]["slug"], repo, num)
            if tid in tasks_by_id:
                dup += 1
                continue
            # When main trunk is red, individual PR CI-fix tasks are redundant —
            # the HEAL-mainred task will fix the root cause, healing all PRs at once.
            if verdict == "CI-RED":
                mainred_tid = f"HEAL-mainred-{repo.replace('/', '-').lower()}"
                mt = tasks_by_id.get(mainred_tid)
                if mt is not None and mt.status in _MAINRED_ACTIVE_STATUSES:
                    dup += 1
                    continue
            would.append((tid, verdict, repo, num))
        print(
            f"[self-heal] DRY-RUN window={len(prs)}/{len(allprs)} ready={b['READY']} "
            f"ci-red={b['CI-RED']} conflict={b['CONFLICT']} ci-pending={b['CI-PENDING']} "
            f"stale-core={b['STALE-CORE']} stale-base={b['STALE-BASE']} "
            f"review-feedback={review_fb} "
            f"chronic-frozen={len(frozen)} | would-emit={len(would)} already-queued={dup}"
        )
        print("| heal task id (would emit) | kind | repo | pr |")
        print("|---|---|---|---|")
        for tid, verdict, repo, num in would:
            print(f"| {tid} | {KINDS[verdict]['slug']} | {repo} | #{num} |")
        if not would:
            print("| (none — every sick PR already has an open heal task) |  |  |  |")
        return 0

    # LIVE: acquire the daemon's queue-lock, RELOAD the hot projection under it, dedupe by stable
    # id, and submit the desired delta to TABVLARIVS. Only the remote keeper mutates lifecycle
    # state; this process never writes the canonical board.
    if not acquire_lock():
        print("[self-heal] queue lock held by daemon — skipping this pass (retry next tick)")
        return 0
    try:
        lf = load_limen_file(tasks_path)
        tasks_by_id = {t.id: t for t in lf.tasks}
        emitted = []
        for verdict, repo, num, url in sick:
            tid = task_id(KINDS[verdict]["slug"], repo, num)
            if tid in tasks_by_id:
                continue
            # When main trunk is red, individual PR CI-fix tasks are redundant —
            # the HEAL-mainred task will fix the root cause, healing all PRs at once.
            if verdict == "CI-RED":
                mainred_tid = f"HEAL-mainred-{repo.replace('/', '-').lower()}"
                mt = tasks_by_id.get(mainred_tid)
                if mt is not None and mt.status in _MAINRED_ACTIVE_STATUSES:
                    continue
            lf.tasks.append(build_task(verdict, repo, num, url, stamp))
            emitted.append(tid)
        if emitted:
            apply_limen_file_sync(tasks_path, lf, agent="self-heal", session_id="emit")
    finally:
        try:
            LOCKD.rmdir()
        except OSError:
            pass

    ts = datetime.datetime.now().strftime("%F %T")
    summary = (
        f"[self-heal] {ts} window={len(prs)}/{len(allprs)} ready={b['READY']} ci-red={b['CI-RED']} "
        f"conflict={b['CONFLICT']} ci-pending={b['CI-PENDING']} stale-core={b['STALE-CORE']} "
        f"stale-base={b['STALE-BASE']} review-feedback={review_fb} chronic-frozen={len(frozen)} "
        f"| emitted={len(emitted)} (limit={limit})"
    )
    print(summary)
    for tid in emitted:
        print(f"    emit: {tid}")
    try:
        with open(LOG, "a") as f:
            f.write(summary + (("  " + " ".join(emitted)) if emitted else "") + "\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
