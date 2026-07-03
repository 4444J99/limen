#!/usr/bin/env python3
"""insight-route.py — close the insight report → owner → heal loop.

Consumes insight reports (logs/insight-cadence/<tier>-*.json) and routes each
to its proper owner. Gated behind LIMEN_INSIGHT_ROUTE_APPLY=1.
"""
import os
import json
import sys
from pathlib import Path
from datetime import date
import subprocess

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.io import load_limen_file, save_limen_file, queue_lock  # noqa: E402
from limen.models import Task  # noqa: E402

HIS_HAND_FILE = ROOT / "his-hand-levers.json"
TASKS_YAML = ROOT / "tasks.yaml"
LOGS_DIR = ROOT / "logs"

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

def route_repo_insight(insight, apply):
    repo = insight["owner"]
    tid = task_id_from_insight(insight["id"])

    if not apply:
        print(f"Would route to queue task {tid} for repo {repo}")
        return

    with queue_lock(TASKS_YAML) as got:
        if not got:
            # Lock timed out — honor the contract and skip this write (never dead-stop; a missed
            # route self-corrects next beat) rather than clobbering a concurrent board write.
            print(f"insight-route: queue busy — skipped {tid} this pass (self-corrects next beat)")
            return
        limen_file = load_limen_file(TASKS_YAML)

        # Check idempotency
        for t in limen_file.tasks:
            if t.id == tid:
                return

        task = Task(
            id=tid,
            title=f"Heal insight: {insight.get('title', '')}",
            description=insight.get("detail", ""),
            repo=repo,
            type="code",
            target_agent="jules",
            priority="medium",
            budget_cost=1,
            status="open",
            context=f"Suggested action: {insight.get('suggested_action', '')}\nSource: {insight.get('source', '')}\nSeverity: {insight.get('severity', '')}",
            created=date.today()
        )
        limen_file.tasks.append(task)
        save_limen_file(TASKS_YAML, limen_file)
        print(f"Routed {tid} to conductor queue for {repo}")

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

def process_report(report_path, apply):
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
            route_repo_insight(insight, apply)
        elif owner:
            route_organ_insight(insight, apply)

def main():
    apply = os.environ.get("LIMEN_INSIGHT_ROUTE_APPLY", "0") == "1"

    cadence_dir = LOGS_DIR / "insight-cadence"
    if not cadence_dir.exists():
        print(f"No insight reports found in {cadence_dir}")
        return 0

    paths = list(cadence_dir.glob("*.json"))

    for p in paths:
        process_report(p, apply)

    return 0

if __name__ == "__main__":
    sys.exit(main())
