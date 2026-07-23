#!/usr/bin/env python3
"""Claude PreToolUse adapter for Limen's shared action-admission runtime."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.action_admission_runtime import admit_pre_tool_action  # noqa: E402
from limen.host_admission import AdmissionController, AdmissionStateError  # noqa: E402

_EXECUTION_TTL_SECONDS = 24 * 60 * 60


def _process_table() -> dict[int, tuple[int, str]]:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,comm="],
            capture_output=True,
            text=True,
            timeout=0.5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}
    table: dict[int, tuple[int, str]] = {}
    for line in result.stdout.splitlines():
        parts = line.strip().split(maxsplit=2)
        if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        table[int(parts[0])] = (int(parts[1]), parts[2] if len(parts) > 2 else "")
    return table


def claude_owner_pid() -> int:
    """Resolve the durable Claude ancestor instead of leasing to this short hook."""

    current = os.getppid()
    table = _process_table()
    if not table:
        raise ValueError("durable Claude owner process table is unavailable")
    seen: set[int] = set()
    oldest: int | None = None
    for _ in range(32):
        if current <= 1 or current in seen:
            break
        seen.add(current)
        row = table.get(current)
        if row is None:
            break
        parent, command = row
        oldest = current
        if "claude" in command.lower():
            return current
        current = parent
    if oldest is None:
        raise ValueError("durable Claude owner ancestor cannot be proven")
    return oldest


def _turn_owner(payload: dict[str, Any]) -> str | None:
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        return None
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]
    return f"claude-session-{digest}"


def _tool_deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def handle(
    payload: dict[str, Any],
    *,
    controller: AdmissionController | None = None,
    owner_pid: int | None = None,
) -> dict[str, Any] | None:
    if str(payload.get("hook_event_name") or "") != "PreToolUse":
        return None
    decision = admit_pre_tool_action(
        payload,
        controller=controller or AdmissionController(),
        owner=_turn_owner(payload),
        pid=owner_pid or claude_owner_pid(),
        surface="claude-worktree-write",
        ttl_seconds=_EXECUTION_TTL_SECONDS,
    )
    return None if decision.allowed else _tool_deny(decision.reason)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be a JSON object")
        output = handle(payload)
    except (AdmissionStateError, ValueError) as exc:
        output = _tool_deny(f"Limen host admission hook failed closed: {exc}")
    if output is not None:
        print(json.dumps(output, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
