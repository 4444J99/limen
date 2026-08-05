#!/usr/bin/env python3
"""Backlog-miner — rung 3 of the self-* ladder (self-feeding).

Keeps the conductor's queue full so idle multi-vendor capacity always has work.
Mines OPEN GitHub issues across the fleet's orgs, normalizes each into a limen
task (identity = owner/repo from the issue, never a folder name), dedups against
the existing tasks.yaml, and appends them as `open` tasks with target_agent=any
so the vendor-tiering router (scripts/route.py) decides the lane.

Bounded by design (the backlog is ~1600+ issues; the budget is 100/day):
  --limit N         cap total mined this run (default 25)
  --owners a,b,c    restrict to these owners (default: the known fleet owners)
  --label L         only issues carrying label L
  --exclude-label   skip these labels (default: park,blocked,wip,duplicate,
                    invalid,wontfix) — "park"/"blocked" are deferred by design
  --apply           append to tasks.yaml via the limen schema (validated);
                    without it, prints the plan and changes nothing.

Priority is read from labels: ship-now/critical -> high; ship-soon -> medium;
otherwise medium. Requires `gh` authenticated with repo + read:org.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

# Post-move: the per-aspect orgs (a-organvm, organvm-i..vii, meta-organvm) were
# consolidated into the single `organvm` org. Personal account stays separate
# (uses the user: qualifier). Override with --owners or $LIMEN_OWNERS.
DEFAULT_OWNERS = [o.strip() for o in os.environ.get(
    "LIMEN_OWNERS", "4444J99,organvm").split(",") if o.strip()]
DEFAULT_EXCLUDE = ["park", "blocked", "wip", "duplicate", "invalid", "wontfix"]
_PERSONAL = {"4444J99"}


def _allowed_repos() -> set[str]:
    """Value tier (revenue/conductor repos) — the ONLY repos worth mining a token for. Sourced from
    value-repos.json at LIMEN_ROOT (or LIMEN_VALUE_REPOS_FILE) + the LIMEN_VALUE_REPOS env. The
    single source of truth is the value-repos.json file (same as generate-backlog). Empty = unset."""
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


def _gh_issues(owner: str, per_owner: int, label: str | None) -> list[dict]:
    args = ["gh", "search", "issues", "--owner", owner, "--state", "open",
            "--limit", str(per_owner),
            "--json", "repository,number,title,labels,url,body"]
    if label:
        args += ["--label", label]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            print(f"  ! {owner}: gh error ({r.stderr.strip()[:80]})", file=sys.stderr)
            return []
        return json.loads(r.stdout or "[]")
    except Exception as e:
        print(f"  ! {owner}: {e}", file=sys.stderr)
        return []


_PRIO_HIGH = {"ship-now", "critical", "urgent", "p0", "p1"}
_PRIO_MED = {"ship-soon", "p2"}


def _priority(labels: list[str]) -> str:
    ls = {l.lower() for l in labels}
    if ls & _PRIO_HIGH:
        return "high"
    if ls & _PRIO_MED:
        return "medium"
    return "medium"


_PRIO_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "backlog": 4}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _to_task(issue: dict) -> dict:
    nwo = issue["repository"]["nameWithOwner"]  # owner/repo
    owner, _, repo = nwo.partition("/")
    num = issue["number"]
    labels = [l["name"] for l in issue.get("labels", [])]
    body = (issue.get("body") or "").strip().replace("\r", "")
    excerpt = re.sub(r"\s+", " ", body)[:400]
    return {
        "id": f"GH-{_slug(owner)}-{_slug(repo)}-{num}",
        "title": issue["title"][:140],
        "repo": nwo,
        "type": "code",
        "target_agent": "any",
        "priority": _priority(labels),
        "budget_cost": 1,
        # A needs-human-labeled issue is a human-gated lever, not fleet-dispatchable work:
        # mine it straight into the needs_human STATUS so label and status never contradict
        # (an `open` needs-human task fails the board validator + gets re-picked forever).
        "status": "needs_human" if "needs-human" in labels else "open",
        "origin": "obligation",
        "horizon": "present",
        "value_case": f"Close the source-owned GitHub obligation {nwo}#{num}",
        "labels": labels,
        "urls": [issue["url"]],
        "context": f"GitHub issue {nwo}#{num}. {excerpt}".strip(),
        "predicate": f'test "$(gh issue view {num} --repo {nwo} --json state --jq .state)" = CLOSED',
        "receipt_target": issue["url"],
        "created": date.today().isoformat(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", "tasks.yaml"))
    ap.add_argument("--owners", default=",".join(DEFAULT_OWNERS))
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--per-owner", type=int, default=40)
    ap.add_argument("--label", default=None)
    ap.add_argument("--exclude-label", default=",".join(DEFAULT_EXCLUDE))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    owners = [o.strip() for o in args.owners.split(",") if o.strip()]
    exclude = {x.strip().lower() for x in args.exclude_label.split(",") if x.strip()}
    tasks_path = Path(args.tasks)

    # existing ids + urls for dedup
    import yaml
    existing = yaml.safe_load(tasks_path.read_text()) if tasks_path.exists() else {"tasks": []}
    have_ids = {t["id"] for t in existing.get("tasks", [])}
    have_urls = {u for t in existing.get("tasks", []) for u in (t.get("urls") or [])}

    print(f"# Backlog-miner  (owners={len(owners)}, limit={args.limit}, "
          f"exclude={sorted(exclude)})\n")

    mined: list[dict] = []
    seen_ids: set[str] = set()
    for owner in owners:
        # gh's `user:` vs `org:` is auto-handled by --owner, but personal accounts
        # work with --owner too; keep a note for clarity.
        issues = _gh_issues(owner, args.per_owner, args.label)
        for iss in issues:
            labels = {l["name"].lower() for l in iss.get("labels", [])}
            if labels & exclude:
                continue
            t = _to_task(iss)
            if t["id"] in have_ids or t["id"] in seen_ids:
                continue
            if t["urls"] and t["urls"][0] in have_urls:
                continue
            seen_ids.add(t["id"])
            mined.append(t)

    # VALUE-TIER GATE: only mine issues for revenue/conductor repos (never the dead/zero-user estate).
    allowed = _allowed_repos()
    if allowed:
        before = len(mined)
        mined = [t for t in mined if t.get("repo") in allowed]
        print(f"  value-tier gate: {before} mined → {len(mined)} in tier")

    # prioritize, then cap
    mined.sort(key=lambda t: _PRIO_RANK.get(t["priority"], 9))
    capped = mined[: args.limit]

    print(f"discovered {len(mined)} new (deduped) issues; taking top {len(capped)} "
          f"by priority\n")
    print("| new task id | repo | prio | title |")
    print("|---|---|---|---|")
    for t in capped:
        print(f"| {t['id']} | {t['repo']} | {t['priority']} | {t['title'][:50]} |")

    if not args.apply:
        print(f"\ndry-run — no changes. re-run with --apply to append "
              f"{len(capped)} tasks, then route + dispatch.")
        return 0

    # Validated, append-only submission to the record keeper.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
    from limen.tabularius import submit_task_upsert

    session_id = os.environ.get("LIMEN_SESSION_ID", "mine-backlog")
    for t in capped:
        submit_task_upsert(tasks_path, t, agent="mine-backlog", session_id=session_id)
    print(
        f"\nsubmitted {len(capped)} upsert tickets to the keeper's inbox "
        f"(TABVLARIVS folds them onto {tasks_path} next beat)."
    )
    print("next: the record-keeper seals them, then   python3 scripts/route.py --apply")
    return 0


if __name__ == "__main__":
    rc = main()
    # SELF-FEED (live without a daemon restart): the heartbeat calls THIS script as a fresh
    # subprocess every FEED beat, so chaining the generator here activates the "queue never hits 0"
    # guarantee in the RUNNING daemon — no heartbeat-loop.sh restart, no in-flight dispatch lost.
    # Only on --apply (the daemon's mode); generate-backlog no-ops when the queue is above floor.
    if "--apply" in sys.argv:
        try:
            import subprocess
            gen = Path(__file__).resolve().parent / "generate-backlog.py"
            subprocess.run([sys.executable, str(gen), "--apply"], timeout=120)
        except Exception as e:  # never let self-feed break the feed beat
            print(f"(generate-backlog skipped: {e})")
    sys.exit(rc)
