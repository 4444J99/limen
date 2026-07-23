#!/usr/bin/env python3
"""Action-level Codex admission for concurrent isolated worktrees."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.host_admission_capabilities import (  # noqa: E402
    host_admission_capabilities,
)

if sys.argv[1:] == ["--capabilities"]:
    print(json.dumps(host_admission_capabilities(), separators=(",", ":")))
    raise SystemExit(0)

from limen.action_admission import action_denial_supported  # noqa: E402
from limen.action_admission_runtime import admit_pre_tool_action  # noqa: E402
from limen.host_admission import (  # noqa: E402
    AdmissionController,
    AdmissionStateError,
    worktree_scope,
)

_EXECUTION_TTL_SECONDS = 24 * 60 * 60


def _hash_label(prefix: str, raw: str) -> str:
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"


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


def codex_owner_pid() -> int:
    """Resolve the durable Codex ancestor instead of leasing to this short hook."""

    current = os.getppid()
    table = _process_table()
    if not table:
        raise ValueError("durable Codex owner process table is unavailable")
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
        lowered = command.lower()
        if any(marker in lowered for marker in ("codex", "chatgpt", "openai")):
            return current
        current = parent
    if oldest is None:
        raise ValueError("durable Codex owner ancestor cannot be proven")
    return oldest


def _turn_owner(payload: dict[str, Any]) -> str | None:
    session_id = str(payload.get("session_id") or "").strip()
    return _hash_label("codex-session", session_id) if session_id else None


def _warning(text: str) -> dict[str, Any]:
    return {"systemMessage": text}


def _stop(text: str) -> dict[str, Any]:
    return {"continue": False, "stopReason": text}


def _tool_deny(text: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": text,
        }
    }


def _needs_bounded_closeout(cwd: str) -> bool:
    """Cheap evidence only; never scan worktrees, transcripts, or remote state."""

    if not cwd:
        return False
    try:
        branch = subprocess.run(
            ["git", "-C", cwd, "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=0.5,
            check=False,
        ).stdout.strip()
        if not branch or branch in {"main", "master"}:
            return False
        dirty = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain=v1", "--untracked-files=no"],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        )
        ahead = subprocess.run(
            ["git", "-C", cwd, "rev-list", "--count", "@{upstream}..HEAD"],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(dirty.returncode == 0 and dirty.stdout.strip()) or bool(
        ahead.returncode == 0 and ahead.stdout.strip().isdigit() and int(ahead.stdout) > 0
    )


def _release_execution(
    controller: AdmissionController,
    *,
    owner: str,
    pid: int,
    cwd: str,
) -> None:
    try:
        scope = worktree_scope(cwd)
    except ValueError:
        scope = None
    if scope is not None and scope.linked:
        controller.release_owned(scope.lease_kind, owner=owner, pid=pid)
    # A client that failed the startup feature probe still owns the legacy
    # machine-wide record. Exact owner/PID/start identity keeps this release safe.
    controller.release_owned("execution", owner=owner, pid=pid)


def handle(
    payload: dict[str, Any],
    *,
    controller: AdmissionController | None = None,
    owner_pid: int | None = None,
    closeout_probe: Callable[[str], bool] = _needs_bounded_closeout,
    feature_probe: Callable[[], bool] = action_denial_supported,
) -> dict[str, Any] | None:
    controller = controller or AdmissionController()
    event = str(payload.get("hook_event_name") or "")
    permission_mode = str(payload.get("permission_mode") or "default")
    owner = _turn_owner(payload)
    pid = owner_pid or codex_owner_pid()

    if event == "UserPromptSubmit":
        if permission_mode == "plan":
            return None
        if owner is None:
            return _stop("Limen denied a non-plan Codex turn without a stable session identity.")
        if feature_probe():
            return None
        decision = controller.acquire(
            "execution",
            owner=owner,
            surface="codex-user-prompt",
            pid=pid,
            ttl_seconds=_EXECUTION_TTL_SECONDS,
        )
        if not decision["allowed"]:
            reasons = ",".join(decision.get("reasons") or ["execution-lease-held"])
            return _stop(
                f"Limen denied this Codex turn: {reasons}. Finish or stop the current root first.",
            )
        return None

    if event == "PreToolUse":
        decision = admit_pre_tool_action(
            payload,
            controller=controller,
            owner=owner,
            surface="codex-worktree-write",
            pid=pid,
            ttl_seconds=_EXECUTION_TTL_SECONDS,
        )
        return None if decision.allowed else _tool_deny(decision.reason)

    if event == "SubagentStart":
        return {
            "systemMessage": (
                "Limen subagent bounds: max_threads=3, max_depth=1; source writes require the "
                "parent's linked-worktree writer scope and heavy entrypoints require the shared host lease."
            ),
            "hookSpecificOutput": {
                "hookEventName": "SubagentStart",
                "additionalContext": (
                    "Do not start a nested subagent. Keep this child bounded and use guarded "
                    "entrypoints for heavy verification."
                ),
            },
        }

    if event == "Stop" and owner is not None:
        # Codex may expose the compatibility flag used by Stop hooks. Only that
        # explicit first-pass signal may request one continuation; otherwise Stop
        # releases immediately and can never become an unbounded loop.
        first_stop = payload.get("stop_hook_active") is False
        if first_stop and closeout_probe(str(payload.get("cwd") or "")):
            try:
                scope = worktree_scope(str(payload.get("cwd") or ""))
                owned = next(
                    (
                        lease
                        for lease in controller.status(probe=False).get("leases") or []
                        if lease.get("kind") == scope.lease_kind
                        and lease.get("owner") == owner
                        and int(lease.get("pid") or 0) == pid
                    ),
                    None,
                )
            except AdmissionStateError:
                owned = None
            except ValueError:
                owned = None
            if owned is not None:
                return _stop(
                    "One bounded closeout pass remains: preserve named changes and leave a durable "
                    "owner receipt. Do not launch broad scans or full verification.",
                )
        _release_execution(
            controller,
            owner=owner,
            pid=pid,
            cwd=str(payload.get("cwd") or ""),
        )
        return None

    return None


def main() -> int:
    event = ""
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be a JSON object")
        event = str(payload.get("hook_event_name") or "")
        output = handle(payload)
    except (AdmissionStateError, ValueError) as exc:
        text = f"Limen host admission hook failed closed: {exc}"
        if event == "UserPromptSubmit":
            output = _stop(text)
        elif event == "PreToolUse":
            output = _tool_deny(text)
        else:
            output = _warning(text)
    if output is not None:
        print(json.dumps(output, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
