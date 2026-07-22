#!/usr/bin/env python3
"""Assemble bounded static dashboard data from the generated private surfaces."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


POLICY_NAME = "dashboard-export-policy.json"


def load_policy(app: Path) -> dict[str, Any]:
    policy = json.loads((app / POLICY_NAME).read_text(encoding="utf-8"))
    if policy.get("schema_version") != "limen.dashboard-export-policy.v1":
        raise ValueError("dashboard export policy has an unsupported schema_version")
    max_logs = policy.get("max_dispatch_log_entries")
    max_bytes = policy.get("max_dashboard_bytes")
    done_statuses = policy.get("done_statuses")
    if not isinstance(max_logs, int) or isinstance(max_logs, bool) or max_logs < 0:
        raise ValueError("dashboard export policy max_dispatch_log_entries must be a non-negative integer")
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        raise ValueError("dashboard export policy max_dashboard_bytes must be a positive integer")
    if (
        not isinstance(done_statuses, list)
        or not done_statuses
        or not all(isinstance(item, str) for item in done_statuses)
    ):
        raise ValueError("dashboard export policy done_statuses must be a nonempty string list")
    return policy


def slim_task(task: dict[str, Any], *, max_logs: int) -> dict[str, Any]:
    projected = dict(task)
    logs = task.get("dispatch_log")
    if logs is None:
        return projected
    if not isinstance(logs, list):
        projected["dispatch_log"] = []
        return projected
    if len(logs) <= max_logs:
        return projected
    projected["dispatch_log"] = sorted(
        logs,
        key=lambda event: str(event.get("timestamp", "")) if isinstance(event, dict) else "",
        reverse=True,
    )[:max_logs]
    return projected


def payloads(
    *,
    internal: dict[str, Any],
    task_document: dict[str, Any] | list[Any],
    policy: dict[str, Any],
    integrity: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    tasks = task_document.get("tasks", task_document) if isinstance(task_document, dict) else task_document
    tasks = tasks if isinstance(tasks, list) else []
    normalized_tasks = [task for task in tasks if isinstance(task, dict)]
    summary = dict(internal.get("summary") or {})
    if integrity is not None:
        summary["integrity"] = {
            "counts": integrity.get("counts", {}),
            "chronic": integrity.get("chronic", []),
        }
    done_statuses = set(policy["done_statuses"])
    max_logs = policy["max_dispatch_log_entries"]
    active = [
        slim_task(task, max_logs=max_logs) for task in normalized_tasks if task.get("status") not in done_statuses
    ]
    done = [slim_task(task, max_logs=max_logs) for task in normalized_tasks if task.get("status") in done_statuses]
    dashboard = {
        "portal": internal.get("portal"),
        "summary": summary,
        "tasks": active,
        "storage": internal.get("storage"),
    }
    done_document = {
        "generated_at": summary.get("generated_at"),
        "total_done": len(done),
        "tasks": done,
    }
    return dashboard, done_document


def encoded(document: dict[str, Any]) -> bytes:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def assemble(app: Path, *, repo_root: Path, write_public: bool = False) -> dict[str, Any]:
    generated = app / ".generated" / "surfaces"
    policy = load_policy(app)
    internal = json.loads((generated / "internal-status.json").read_text(encoding="utf-8"))
    task_document = json.loads((generated / "tasks.json").read_text(encoding="utf-8"))
    try:
        integrity = json.loads((repo_root / "logs" / "dispatch-verify.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        integrity = None
    dashboard, done = payloads(
        internal=internal,
        task_document=task_document,
        policy=policy,
        integrity=integrity,
    )
    dashboard_bytes = encoded(dashboard)
    done_bytes = encoded(done)
    if len(dashboard_bytes) > policy["max_dashboard_bytes"]:
        maximum_kib = policy["max_dashboard_bytes"] // 1024
        raise ValueError(
            f"dashboard.json exceeds {maximum_kib}KB ratchet: "
            f"{len(dashboard_bytes) // 1024}KB > {maximum_kib}KB; slim the bounded projection"
        )
    destinations = [app / "out"]
    if write_public:
        destinations.append(app / "public")
    for destination in destinations:
        write_atomic(destination / "dashboard.json", dashboard_bytes)
        write_atomic(destination / "done-tasks.json", done_bytes)
    return {
        "active": len(dashboard["tasks"]),
        "done": done["total_done"],
        "dashboard_bytes": len(dashboard_bytes),
        "done_bytes": len(done_bytes),
        "max_dashboard_bytes": policy["max_dashboard_bytes"],
        "max_dispatch_log_entries": policy["max_dispatch_log_entries"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, default=Path("web/app"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--write-public", action="store_true")
    args = parser.parse_args(argv)
    result = assemble(args.app.resolve(), repo_root=args.repo_root.resolve(), write_public=args.write_public)
    print(
        f"dashboard.json: {result['dashboard_bytes'] // 1024}KB ({result['active']} active tasks) | "
        f"done-tasks.json: {result['done_bytes'] // 1024}KB ({result['done']} done/archived) | "
        f"dispatch_log<={result['max_dispatch_log_entries']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
