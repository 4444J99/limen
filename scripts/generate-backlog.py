#!/usr/bin/env python3
"""generate-backlog — the SELF-FEEDING half of the metabolism.

mine-backlog.py pulls EXISTING open GitHub issues; when that backlog is exhausted the queue
drains to 0 and the autonomous loop idles (the one thing that forces a stop). This generator
closes that gap: when `open` falls below a floor, it synthesizes genuinely-useful build-out
tasks per active product so the stream is endless ("run out of tasks -> make more tasks").

NOT mindless filler: each task names a real engineering lever (coverage, CI, docs, security,
complexity, typing) and demands SPECIFIC work + a green check — the lane agent does the real
discovery. Every repo always has headroom in each lever, so the supply is effectively infinite.

Identity from metadata: the product set is DERIVED from the repos already referenced in
tasks.yaml (the active surfaces), never a pinned list.

Read-only by default (prints a plan). With --apply it appends `open` tasks via the limen
schema (validated, atomic write). Never dispatches.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.intake import contract_fields, github_pr_contract  # noqa: E402
from limen.models import Task  # noqa: E402
from limen.tabularius import submit_task_upsert  # noqa: E402
from limen.capacity import select_lanes  # noqa: E402
from limen.worktree_debt import worktree_debt_report  # noqa: E402

# Useful, repo-agnostic but ACTIONABLE levers. The agent resolves the specifics in-repo.
# (key, priority, title, context-template). {repo} is filled per product.
TEMPLATES = [
    (
        "test-coverage",
        "medium",
        "Raise test coverage in {repo}",
        "Find the largest source module in {repo} with little or no test coverage and add a focused, "
        "PASSING test suite for it. Run the repo's own test command and confirm green. No placeholder tests.",
    ),
    (
        "ci-green",
        "high",
        "Make {repo} CI green",
        "Inspect the latest FAILING checks on {repo}'s default branch, fix the root cause (lint / types / "
        "failing test / config), and confirm the checks pass. If CI is already green, add the single most "
        "valuable missing check (e.g. typecheck or test-matrix) instead.",
    ),
    (
        "docs",
        "low",
        "Real usage docs for {repo}",
        "Derive an accurate Usage section in {repo}'s README from the ACTUAL entrypoints/exports (install, "
        "run, key commands + flags). No invented features, no TODOs — only what the code actually does.",
    ),
    (
        "security",
        "high",
        "Security hardening pass on {repo}",
        "Run the ecosystem audit for {repo} (npm audit / pip-audit / equivalent), upgrade or pin "
        "high-severity advisories, and add input validation at the main untrusted-input entrypoints. "
        "Open a PR; keep the build green.",
    ),
    (
        "simplify",
        "medium",
        "Reduce complexity in {repo}",
        "Identify the most complex or most-duplicated module in {repo} and refactor it for clarity, with "
        "tests proving behavior is unchanged. Net lines should not grow without cause.",
    ),
    (
        "typing",
        "medium",
        "Tighten types in {repo}",
        "Eliminate the worst untyped hotspots in {repo}'s most-imported module (remove `any` / add type "
        "hints / fix loose signatures). Keep the build and tests green.",
    ),
]

# statuses that count as "this (repo,lever) is already being worked" — don't duplicate those.
_ACTIVE = {"open", "dispatched", "in_progress", "needs_human"}


def _org_repos() -> list[str]:
    """The full candidate set = EVERY non-fork, non-archived repo in the org(s) — so the generator
    covers every owner, not just the ~60 already in tasks.yaml (the organvm consolidation left ~160
    real repos dark). Org list DERIVED from LIMEN_ORGS (default organvm), core API (no search quota).
    Excludes infra/meta/site/example/contrib-fork names. Returns [] on any error so main() can fall
    back to the tasks.yaml set (the generator must never break the feed beat)."""
    import subprocess

    orgs = [o.strip() for o in os.environ.get("LIMEN_ORGS", "organvm").split(",") if o.strip()]
    out: list[str] = []
    for org in orgs:
        try:
            r = subprocess.run(
                [
                    "gh",
                    "api",
                    f"/orgs/{org}/repos",
                    "--paginate",
                    "--jq",
                    ".[] | select(.fork==false and .archived==false) | .full_name",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if r.returncode == 0:
                out += [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
        except Exception:
            pass

    def is_product(full: str) -> bool:
        n = full.split("/")[-1]
        if n.startswith("_") or n == ".github" or n.endswith("--superproject") or n.endswith(".github.io"):
            return False
        if n.startswith(("example-", "art-from--", "contrib--")):
            return False
        return True

    return [r for r in out if is_product(r)]


def _allowed_repos() -> set[str]:
    """THE VALUE TIER — the ONLY repos worth a generated token (revenue products + conductor-core),
    ranked by time-to-dollar. Sourced from value-repos.json at LIMEN_ROOT (or LIMEN_VALUE_REPOS_FILE)
    and/or the LIMEN_VALUE_REPOS env (comma-sep). Supports both ["owner/repo", …] and
    [{"repo": "owner/repo"}, …]. Returns the union as a set; empty = no tier configured (caller
    fail-closes). Derive-not-pin: the tier is data, never hardcoded here."""
    repos: set[str] = {r.strip() for r in os.environ.get("LIMEN_VALUE_REPOS", "").split(",") if r.strip()}
    fpath = os.environ.get(
        "LIMEN_VALUE_REPOS_FILE",
        str(Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent)) / "value-repos.json"),
    )
    try:
        data = json.loads(Path(fpath).read_text())
        for r in data.get("repos", []):
            repos.add(r if isinstance(r, str) else (r.get("repo") or ""))
    except Exception:
        pass
    repos.discard("")
    return repos


def _avg_headroom_pct() -> float | None:
    """Average live per-vendor headroom (0–100) from logs/usage.json, or None if unreadable. A full
    tank ⇒ lift the backlog floor so the routable queue can't cap out while capacity sits idle — the
    SAME accelerator discover-value.py uses, applied here too (the asymmetry was: discovery scaled with
    headroom but the larger backlog generator did not, so a full tank still hit the flat floor and the
    queue starved the daemon mid-window)."""
    fpath = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent)) / "logs" / "usage.json"
    try:
        vendors = (json.loads(fpath.read_text()) or {}).get("vendors", {})
        hs = [
            v["headroom_pct"]
            for v in vendors.values()
            if isinstance(v, dict) and isinstance(v.get("headroom_pct"), (int, float))
        ]
        return sum(hs) / len(hs) if hs else None
    except Exception:
        return None


def _dispatch_lanes(board: object, dead: set[str]) -> set[str]:
    selector = os.environ.get("LIMEN_DISPATCH_LANES", "auto")
    return set(select_lanes(selector, board, down_lanes=dead)) | {"any"}


def _headroom_bucket(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value >= 90:
        return "very_high"
    if value >= 75:
        return "high"
    if value >= 50:
        return "medium"
    if value >= 25:
        return "low"
    return "very_low"


def census(tasks_path: Path) -> dict:
    """Redacted feed census: aggregate queue/gate shape only, never task text or repo names."""
    report = {
        "tasks_present": tasks_path.exists(),
        "tasks_readable": False,
        "task_count": 0,
        "status_counts": {},
        "routable_open_count": 0,
        "active_buildout_count": 0,
        "generated_buildout_count": 0,
        "value_tier_count": len(_allowed_repos()),
        "template_count": len(TEMPLATES),
        "headroom_bucket": _headroom_bucket(_avg_headroom_pct()),
        "worktree_debt_gate_enabled": os.environ.get("LIMEN_WORKTREE_DEBT_GATE", "1") == "1",
        "worktree_debt_readable": False,
        "worktree_debt_count": 0,
        "worktree_debt_complete": False,
    }
    try:
        lf = load_limen_file(tasks_path)
    except Exception:
        return report
    tasks = lf.tasks
    report["tasks_readable"] = True
    report["task_count"] = len(tasks)
    report["status_counts"] = dict(sorted(Counter(str(t.status) for t in tasks).items()))

    try:
        from limen.dispatch import _down_lanes, _routine_generated_buildout_allowed

        dead = _down_lanes()
    except Exception:
        dead = set()

        def _routine_generated_buildout_allowed(_task):
            return True

    dispatch_lanes = _dispatch_lanes(lf, dead)
    template_keys = {k for k, *_ in TEMPLATES}
    report["routable_open_count"] = sum(
        1
        for t in tasks
        if t.status == "open"
        and (t.target_agent or "any") in dispatch_lanes
        and (t.target_agent or "any") not in dead
        and _routine_generated_buildout_allowed(t)
    )
    report["active_buildout_count"] = sum(
        1
        for t in tasks
        if t.status in _ACTIVE and t.labels and t.labels[0] in template_keys
    )
    report["generated_buildout_count"] = sum(
        1
        for t in tasks
        if t.labels and "generated" in t.labels and "build-out" in t.labels
    )
    try:
        debt_report = worktree_debt_report()
        report["worktree_debt_readable"] = True
        report["worktree_debt_count"] = int(debt_report.get("debt", 0))
        report["worktree_debt_complete"] = report["worktree_debt_count"] == 0
    except Exception:
        pass
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", "tasks.yaml"))
    ap.add_argument(
        "--floor",
        type=int,
        default=int(os.environ.get("LIMEN_BACKLOG_FLOOR", "60")),
        help="top the OPEN queue up to this depth; generate nothing if already at/above",
    )
    ap.add_argument(
        "--max-new",
        type=int,
        default=int(os.environ.get("LIMEN_GEN_MAX", "40")),
        help="hard cap on tasks generated in one run (anti-flood)",
    )
    ap.add_argument("--apply", action="store_true", help="append to tasks.yaml (validated, atomic)")
    ap.add_argument("--census", action="store_true", help="print redacted feed queue/gate counts and exit")
    args = ap.parse_args()

    path = Path(args.tasks)
    if args.census:
        print(json.dumps(census(path), indent=2, sort_keys=True))
        return 0

    lf = load_limen_file(path)
    tasks = lf.tasks

    # NO normal-path estate scan and NO global stop on debt. The preserved-root count is available
    # explicitly through ``--census``; classifying hundreds of roots here used to add ~51 seconds to
    # every feed voice before it even checked whether the queue was already healthy. Per-task
    # marginal admission owns launch safety, while this producer only keeps the routable queue fed.

    # Floor on ROUTABLE-BY-THE-FLEET open work, not total open. The dispatchable set is the same
    # selector heartbeat passes to dispatch; "any" is routable because route.py picks a live lane.
    try:
        from limen.dispatch import _down_lanes, _routine_generated_buildout_allowed

        _dead = _down_lanes()
    except Exception:
        _dead = set()

        def _routine_generated_buildout_allowed(_task):
            return True

    dispatch_lanes = _dispatch_lanes(lf, _dead)
    open_now = sum(
        1
        for t in tasks
        if t.status == "open"
        and (t.target_agent or "any") in dispatch_lanes
        and (t.target_agent or "any") not in _dead
        and _routine_generated_buildout_allowed(t)
    )
    # Headroom accelerator (symmetric with discover-value.py): a full tank lifts the floor up to 3x so
    # the routable queue stays deep enough to feed the accelerated dispatch toward each reset cliff;
    # a near-empty tank keeps the base floor (don't pile on). 50%→1x … 100%→3x.
    floor = args.floor
    avg_hr = _avg_headroom_pct()
    if avg_hr is not None and avg_hr >= 50:
        floor = int(round(args.floor * (1 + min(2.0, (avg_hr - 50) / 25))))
    if open_now >= floor:
        print(
            f"queue healthy: routable-open={open_now} >= floor={floor} "
            f"(avg headroom {avg_hr if avg_hr is None else round(avg_hr)}%) — nothing to generate."
        )
        return 0
    need = min(floor - open_now, args.max_new)

    # candidate repos = EVERY real repo in the org (so every owner gets covered, not just the ~60
    # already in tasks.yaml) ∪ any repo already referenced in the queue. Falls back to the tasks.yaml
    # set if the org API is unreachable. This is the permanent fix for the post-consolidation blind
    # spots: the generator now sources the live organvm estate, not just repos it already knew.
    in_queue = [r for r in dict.fromkeys(t.repo for t in tasks if t.repo) if r]
    org = _org_repos()
    repos = list(dict.fromkeys(org + in_queue)) if org else in_queue
    if not repos:
        print("no candidate repos (org API unreachable + tasks.yaml empty) — nothing to generate.")
        return 0

    # RANKED-TIER GATE (anti-flood, NOT starvation): build-out levers go ONLY to repos whose value is
    # already DISCOVERED + ranked (value-repos.json) — so we don't dump 6 busywork levers × 174 repos.
    # This is NOT "non-value repos get ignored": a repo with no discovered value isn't starved, it gets
    # a DISCOVERY task from discover-value.py (the value is an OUTPUT of the fleet, not a precondition).
    # value-repos.json is the OUTPUT of discovery, continuously re-ranked — never a hand-pinned allowlist.
    allowed = _allowed_repos()
    if not allowed:
        print("ranked tier empty — no build-out yet; discover-value.py will surface + rank value first.")
        return 0
    before = len(repos)
    repos = [r for r in repos if r in allowed]
    print(f"  value-tier gate: {before} candidates → {len(repos)} in tier")
    if not repos:
        print("no candidate repos in the value tier — nothing to generate.")
        return 0
    if org:
        print(f"  candidate repos: {len(repos)} ({len(org)} from org, +{len(set(in_queue) - set(org))} queue-only)")

    # how loaded is each repo right now (fewest-loaded get fed first → spread the work).
    load = Counter(t.repo for t in tasks if t.status in _ACTIVE and t.repo)
    repos.sort(key=lambda r: load.get(r, 0))

    # what (repo, lever) pairs are already active → skip them.
    existing = {t.id for t in tasks}
    active_pairs = {
        (t.repo, t.labels[0])
        for t in tasks
        if t.status in _ACTIVE and t.repo and t.labels and t.labels[0] in {k for k, *_ in TEMPLATES}
    }

    stamp = date.today().isoformat()
    mmdd = date.today().strftime("%m%d")
    new: list[Task] = []
    # round-robin levers across repos so we never dump six tasks on one repo.
    for lever_idx in range(len(TEMPLATES)):
        if len(new) >= need:
            break
        key, prio, title, ctx = TEMPLATES[lever_idx]
        for repo in repos:
            if len(new) >= need:
                break
            if (repo, key) in active_pairs:
                continue
            slug = repo.replace("/", "-").lower()
            tid = f"GEN-{slug}-{key}-{mmdd}"
            if tid in existing:
                continue
            existing.add(tid)
            active_pairs.add((repo, key))
            new.append(
                Task(
                    id=tid,
                    title=title.format(repo=repo),
                    repo=repo,
                    type="code",
                    target_agent="any",
                    priority=prio,
                    budget_cost=1,
                    status="open",
                    labels=[key, "generated", "build-out"],
                    urls=[],
                    context=ctx.format(repo=repo) + f" [auto-generated {stamp} to keep the stream endless]",
                    **contract_fields(github_pr_contract(repo, tid)),
                    depends_on=[],
                    created=stamp,
                    dispatch_log=[],
                )
            )

    print(
        f"# generate-backlog: open={open_now} floor={args.floor} -> generating {len(new)} "
        f"(cap {args.max_new}) across {len(set(t.repo for t in new))} repos\n"
    )
    print("| new task id | repo | prio | lever |")
    print("|---|---|---|---|")
    for t in new:
        print(f"| {t.id} | {t.repo} | {t.priority} | {t.labels[0]} |")

    if not new:
        print("\n(nothing new to generate — every (repo,lever) is already active)")
        return 0
    if args.apply:
        # TABVLARIVS producer path (Step 2.1). LIMEN_TICKETS_PRODUCE=1 → stop writing tasks.yaml
        # directly; hand each NEW task to the record-keeper as an upsert ticket. `new` is already
        # deduped against the board above, so every id is brand-new (an upsert never clobbers a live
        # id). The keeper folds them next beat. Default OFF preserves the legacy validated append.
        if os.environ.get("LIMEN_TICKETS_PRODUCE") == "1":
            session_id = os.environ.get("LIMEN_SESSION_ID", "generate-backlog")
            for t in new:
                submit_task_upsert(path, t, agent="generate-backlog", session_id=session_id)
            print(f"\nsubmitted {len(new)} upsert tickets to the keeper's inbox (folds onto {path} next beat).")
            return 0
        lf.tasks.extend(new)
        save_limen_file(path, lf)
        print(f"\napplied: appended {len(new)} generated tasks -> {path} (route+dispatch separately)")
    else:
        print(f"\ndry-run — re-run with --apply to append {len(new)} tasks.")
    return 0


def _stamp_health() -> None:
    """Proprioception: record that the FEED organ fired this beat (generate-backlog runs every feed
    beat, ungated), so organ-health.py reads it as a fresh artifact (mtime). Fail-open."""
    try:
        logs = Path(__file__).resolve().parent.parent / "logs"
        logs.mkdir(exist_ok=True)
        (logs / "feed-health.json").write_text(
            json.dumps({"timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}) + "\n"
        )
    except OSError:
        pass


if __name__ == "__main__":
    rc = main()
    _stamp_health()
    raise SystemExit(rc)
