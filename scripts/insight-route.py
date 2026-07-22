#!/usr/bin/env python3
"""insight-route.py — close the insight report → owner → heal loop.

Routes each insight in the LATEST report per cadence tier (hourly/daily/weekly/
monthly, from logs/insight-cadence/) to its durable owner:

  owner "anthony"    → his-hand-levers.json (+ sync-hishand-issues)
  owner "org/repo"   → a board task, via the TABVLARIVS keeper. Insights whose source is the
                       board itself (source == "tasks.yaml", e.g. "Task failed:
                       <id>") are SKIPPED: the board already owns that failure —
                       a heal-twin task would just echo it back onto the board.
  owner "<organ>"    → logs/<organ>-residual.json (the organ's durable inbox)

Gated behind LIMEN_INSIGHT_ROUTE_APPLY=1 (dry-run prints otherwise). New board
tasks are capped per pass (LIMEN_INSIGHT_ROUTE_MAX, default 5); the overflow is
counted in the summary line and self-corrects next beat.
"""
import os
import json
import re
import sys
from pathlib import Path
from datetime import date
import subprocess

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.io import load_limen_file  # noqa: E402
from limen.intake import contract_fields, github_pr_contract  # noqa: E402
from limen.models import Task  # noqa: E402
from limen.tabularius import pending_task_ids, submit_task_upsert  # noqa: E402

HIS_HAND_FILE = ROOT / "his-hand-levers.json"
TASKS_YAML = ROOT / "tasks.yaml"
LOGS_DIR = ROOT / "logs"

TIERS = ("hourly", "daily", "weekly", "monthly")

def load_json(path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return default if default is not None else {}

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2))

def task_id_from_insight(insight_id):
    return f"TASK-{insight_id}"

def latest_reports(cadence_dir):
    """The latest report per tier — never the whole history (old reports are an
    aged-out lens; their insights either persist into the latest report or are
    resolved). Stamp formats changed over time (20260626T135356 vs
    2026-07-03T133909+0000), so order on the digit prefix (YYYYMMDDHHMMSS),
    never lexically on the raw filename."""
    latest = {}
    for p in cadence_dir.glob("*.json"):
        m = re.match(rf"({'|'.join(TIERS)})-(.+)$", p.stem)
        if not m:
            continue
        tier, stamp = m.groups()
        key = re.sub(r"\D", "", stamp)[:14]
        if tier not in latest or key > latest[tier][0]:
            latest[tier] = (key, p)
    return [p for _, p in sorted(latest.values())]

def _task_for(insight, tid, repo):
    contract = contract_fields(github_pr_contract(repo, tid))
    return Task(
        id=tid,
        title=f"Heal insight: {insight.get('title', '')}",
        description=insight.get("detail", ""),
        repo=repo,
        type="code",
        target_agent="jules",
        priority="medium",
        budget_cost=1,
        status="open",
        origin="system_debt",
        horizon="present",
        value_case=f"Remove the recurring insight failure owned by {repo}",
        context=f"Suggested action: {insight.get('suggested_action', '')}\nSource: {insight.get('source', '')}\nSeverity: {insight.get('severity', '')}",
        created=date.today(),
        **contract,
    )

def route_repo_insight(insight, apply, stats=None):
    repo = insight["owner"]
    tid = task_id_from_insight(insight["id"])

    if insight.get("source") == "tasks.yaml":
        # Board echo — the referenced task IS the durable record of this failure.
        if stats is not None:
            stats["echo"] += 1
        return

    if not apply:
        print(f"Would route to queue task {tid} for repo {repo}")
        return

    if stats is not None and stats["cap_left"] <= 0:
        stats["deferred"] += 1
        return

    # TABVLARIVS producer path: read-only dedup, then hand the keeper an upsert ticket — never a
    # direct board write. Pending tickets count as existing so repeated beats before a drain do not
    # submit duplicates.
    limen_file = load_limen_file(TASKS_YAML)
    if any(t.id == tid for t in limen_file.tasks) or tid in pending_task_ids(TASKS_YAML):
        return
    submit_task_upsert(
        TASKS_YAML,
        _task_for(insight, tid, repo),
        agent="insight-route",
        session_id=os.environ.get("LIMEN_SESSION_ID", "insight-route"),
    )
    if stats is not None:
        stats["cap_left"] -= 1
        stats["created"] += 1
    print(f"Submitted upsert ticket {tid} for {repo} (keeper folds next beat)")

def route_organ_insight(insight, apply):
    organ = insight["owner"]
    residual_file = LOGS_DIR / f"{organ}-residual.json"

    if not apply:
        print(f"Would route to organ residual {residual_file} for organ {organ}")
        return

    data = load_json(residual_file, [])
    if not isinstance(data, list):
        data = []

    # Check idempotency
    for item in data:
        if item.get("id") == insight["id"]:
            return

    data.append(insight)
    save_json(residual_file, data)
    print(f"Routed insight {insight['id']} to {organ} residual")

def route_anthony_insight(insight, apply):
    if not apply:
        print(f"Would route to his-hand-levers for anthony: {insight['id']}")
        return

    data = load_json(HIS_HAND_FILE, {"levers": []})
    levers = data.get("levers", [])

    # Check idempotency
    for lever in levers:
        if lever.get("id") == insight["id"]:
            return

    new_lever = {
        "id": insight["id"],
        "label": f"{insight.get('title', '')} — {insight.get('detail', '')}",
        "owner": "yours",
        "cost": "evaluate and heal",
        "unlocks": insight.get("suggested_action", ""),
        "source_task": f"insight-cadence ({insight.get('source', 'unknown')})",
        "gate": "insight-route"
    }
    levers.append(new_lever)
    data["levers"] = levers
    save_json(HIS_HAND_FILE, data)
    print(f"Routed insight {insight['id']} to his-hand-levers.json")

    # Sync his-hand issues
    subprocess.run([sys.executable, str(ROOT / "scripts" / "sync-hishand-issues.py"), "--apply"], check=False)

def process_report(report_path, apply, stats=None):
    try:
        report = json.loads(report_path.read_text())
    except Exception as e:
        print(f"Failed to load {report_path}: {e}")
        return

    insights = report.get("insights", [])
    for insight in insights:
        owner = insight.get("owner", "")
        if owner == "anthony":
            route_anthony_insight(insight, apply)
        elif "/" in owner:
            route_repo_insight(insight, apply, stats)
        elif owner:
            route_organ_insight(insight, apply)

def main():
    apply = os.environ.get("LIMEN_INSIGHT_ROUTE_APPLY", "0") == "1"
    try:
        cap = int(os.environ.get("LIMEN_INSIGHT_ROUTE_MAX", "5"))
    except ValueError:
        cap = 5
    stats = {"cap_left": cap, "created": 0, "echo": 0, "deferred": 0}

    cadence_dir = LOGS_DIR / "insight-cadence"
    if not cadence_dir.exists():
        print(f"No insight reports found in {cadence_dir}")
        return 0

    for p in latest_reports(cadence_dir):
        process_report(p, apply, stats)

    print(
        f"insight-route: {stats['created']} board tasks created, "
        f"{stats['echo']} board-echoes skipped, {stats['deferred']} deferred "
        f"(cap {cap}/pass){'' if apply else ' [dry-run]'}"
    )
    return 0

if __name__ == "__main__":
    sys.exit(main())
