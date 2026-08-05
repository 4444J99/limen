#!/usr/bin/env python3
"""Static guard for non-bypassable dispatch admission wiring."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def require(rel: str, needle: str, errors: list[str]) -> None:
    if needle not in read(rel):
        errors.append(f"{rel}: missing {needle!r}")


def main() -> int:
    errors: list[str] = []
    async_py = read("scripts/dispatch-async.py")
    heartbeat = read("scripts/heartbeat-loop.sh")

    require("cli/src/limen/dispatch.py", "def dispatch_admission_check(", errors)
    require("cli/src/limen/dispatch.py", "admission = dispatch_admission_check(tasks_path, task_id=task_id)", errors)
    require("cli/src/limen/dispatch.py", "admission = dispatch_admission_check(tasks_path)", errors)
    require("scripts/dispatch-async.py", "dispatch_admission_check", errors)
    require("scripts/dispatch-admission.py", "dispatch_admission_check", errors)

    if "def _session_value_dispatch_gate" in async_py or "SESSION_VALUE_SCRIPT =" in async_py:
        errors.append("scripts/dispatch-async.py: carries private session-value admission logic")
    if "def _next_action_sources" in async_py or "PROMPT_BATCH_REVIEW_INDEX" in async_py:
        errors.append("scripts/dispatch-async.py: carries private next-action source logic")

    worked_patterns = [
        line
        for line in heartbeat.splitlines()
        if "worked=1" in line and "grep -qE" in line
    ]
    if any("harvested" in line for line in worked_patterns):
        errors.append("scripts/heartbeat-loop.sh: harvest-only output still counts as worked")
    if any("launched" in line and "launched [1-9][0-9]*" not in line for line in worked_patterns):
        errors.append("scripts/heartbeat-loop.sh: launched output must require a positive count")

    raw_launchers = ("async-run-one.py", "agent-dispatch")
    for rel in ("scripts/heartbeat-loop.sh", "scripts/overnight-watch.py"):
        text = read(rel)
        for raw in raw_launchers:
            if raw in text:
                errors.append(f"{rel}: raw launcher {raw!r} bypasses shared admission")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("dispatch-admission static guard: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
