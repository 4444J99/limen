#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.doctor import qa_report  # noqa: E402
from limen.io import load_limen_file  # noqa: E402


def fail(message: str) -> None:
    print(f"lifecycle adapter validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        fail(f"missing {path}")


def mechanism_map(report: dict) -> dict:
    return {mechanism["id"]: mechanism for mechanism in report.get("mechanisms", [])}


def main() -> None:
    tasks_path = ROOT / "tasks.yaml"
    static_qa = read_json(ROOT / "web" / "app" / ".generated" / "surfaces" / "qa-status.json")
    cli_qa = qa_report(load_limen_file(tasks_path), tasks_path, agent="jules")

    if static_qa.get("surface") != "qa":
        fail("static qa-status surface is not qa")
    if static_qa.get("lifecycle") != cli_qa.get("lifecycle"):
        fail(f"static lifecycle {static_qa.get('lifecycle')} != cli lifecycle {cli_qa.get('lifecycle')}")

    for queue in ("next_batch", "qa_queue", "recovery_queue", "assignment_queue", "archive_queue"):
        static_ids = [item["id"] for item in static_qa.get("steering", {}).get(queue, [])]
        cli_ids = [item["id"] for item in cli_qa.get("steering", {}).get(queue, [])]
        if static_ids != cli_ids:
            fail(f"{queue} ids drifted: static {static_ids} != cli {cli_ids}")

    static_mechanisms = mechanism_map(static_qa)
    cli_mechanisms = mechanism_map(cli_qa)
    expected_commands = {
        "release-stale": "POST /api/release-stale?hours=24&dry_run=false",
        "qa-verify": "POST /api/tasks/{task_id}/verify",
        "assign-next": "POST /api/tasks/{task_id}/assign",
        "archive-done": "POST /api/tasks/{task_id}/archive",
    }
    for mechanism_id, command in expected_commands.items():
        if static_mechanisms.get(mechanism_id, {}).get("command") != command:
            fail(f"static mechanism {mechanism_id} command drifted")
        if cli_mechanisms.get(mechanism_id, {}).get("command") != command:
            fail(f"cli mechanism {mechanism_id} command drifted")
        if static_mechanisms.get(mechanism_id, {}).get("count") != cli_mechanisms.get(mechanism_id, {}).get("count"):
            fail(f"mechanism {mechanism_id} count drifted")

    print("Lifecycle adapter contracts verified")


if __name__ == "__main__":
    main()
