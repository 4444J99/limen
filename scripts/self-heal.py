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
  • EMIT side uses the ONE safe shared-append path every tasks.yaml writer uses: acquire the
    daemon's queue-lock (logs/.queue.lock.d, the heal-dispatch.py convention), RELOAD fresh
    under the lock, append validated limen Task objects, save via the atomic writer
    (limen.io.save_limen_file → temp file + fsync + os.replace). Never a naive open()/dump,
    so it can NEVER race the daemon or torn-read tasks.yaml.
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
from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.intake import contract_fields, github_existing_pr_contract  # noqa: E402
from limen.models import Task  # noqa: E402
from _pr_scan import enumerate_open_prs, rotating_window, scaled_limit, stale_base_verdict  # noqa: E402

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
    # STALE-BASE family — the #111 guard. A mergeable+green PR off an OLD base would silently REVERT
    # work that landed since. merge-drain refuses it; these tasks rebase it onto the CURRENT base,
    # keeping the PR's own work and dropping only the reverting hunks. ([[pr111-daemon-regression-healed]])
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
}


def gh(args, timeout=60):
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)


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
            # STALE-BASE GATE (identical to merge-drain.assess — one verdict): refuse a green+mergeable
            # PR off an old base that would silently revert work, and emit a rebase-to-current heal task.
            paths = [f.get("path", "") for f in (d.get("files") or [])]
            sb = stale_base_verdict(repo, paths, d.get("baseRefName"), d.get("headRefOid"), gh)
            if sb:
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
    for repo, num, url, verdict, failing_checks in rows:
        chronic_hits = sorted(check for check in failing_checks if (repo, check) in chronic)
        if verdict == "CI-RED" and failing_checks and len(chronic_hits) == len(failing_checks):
            frozen.append((repo, num, chronic_hits))
            continue
        if verdict in KINDS:
            sick.append((verdict, repo, num, url))
    sick = sick[:limit]
    stamp = datetime.date.today().isoformat()

    tasks_path = Path(a.tasks)

    # DRY-RUN: assess + report only. Zero writes; the queue-lock is never even touched.
    if a.dry_run:
        existing = {t.id for t in load_limen_file(tasks_path).tasks} if tasks_path.exists() else set()
        would, dup = [], 0
        for verdict, repo, num, url in sick:
            tid = task_id(KINDS[verdict]["slug"], repo, num)
            if tid in existing:
                dup += 1
            else:
                would.append((tid, verdict, repo, num))
        print(
            f"[self-heal] DRY-RUN window={len(prs)}/{len(allprs)} ready={b['READY']} "
            f"ci-red={b['CI-RED']} conflict={b['CONFLICT']} ci-pending={b['CI-PENDING']} "
            f"stale-core={b['STALE-CORE']} stale-base={b['STALE-BASE']} "
            f"chronic-frozen={len(frozen)} | would-emit={len(would)} already-queued={dup}"
        )
        print("| heal task id (would emit) | kind | repo | pr |")
        print("|---|---|---|---|")
        for tid, verdict, repo, num in would:
            print(f"| {tid} | {KINDS[verdict]['slug']} | {repo} | #{num} |")
        if not would:
            print("| (none — every sick PR already has an open heal task) |  |  |  |")
        return 0

    # LIVE: acquire the daemon's queue-lock, RELOAD fresh under it, dedupe by stable id, append
    # validated Task objects, save atomically. This is the ONLY safe shared-append path.
    if not acquire_lock():
        print("[self-heal] queue lock held by daemon — skipping this pass (retry next tick)")
        return 0
    try:
        lf = load_limen_file(tasks_path)
        existing = {t.id for t in lf.tasks}
        emitted = []
        for verdict, repo, num, url in sick:
            tid = task_id(KINDS[verdict]["slug"], repo, num)
            if tid in existing:
                continue
            existing.add(tid)
            lf.tasks.append(build_task(verdict, repo, num, url, stamp))
            emitted.append(tid)
        if emitted:
            save_limen_file(tasks_path, lf)
    finally:
        try:
            LOCKD.rmdir()
        except OSError:
            pass

    ts = datetime.datetime.now().strftime("%F %T")
    summary = (
        f"[self-heal] {ts} window={len(prs)}/{len(allprs)} ready={b['READY']} ci-red={b['CI-RED']} "
        f"conflict={b['CONFLICT']} ci-pending={b['CI-PENDING']} stale-core={b['STALE-CORE']} "
        f"stale-base={b['STALE-BASE']} chronic-frozen={len(frozen)} "
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
