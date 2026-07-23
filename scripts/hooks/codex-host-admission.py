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

from limen.action_admission import classify_action, path_within, target_paths  # noqa: E402
from limen.action_admission_runtime import admit_pre_tool_action  # noqa: E402
from limen.host_admission import (  # noqa: E402
    AdmissionController,
    AdmissionStateError,
    worktree_scope,
)

_EXECUTION_TTL_SECONDS = 24 * 60 * 60
_CAPABILITY_TIMEOUT_SECONDS = 1.0
_DELEGATE_TIMEOUT_SECONDS = 8.0


class ImmutableRuntimeError(RuntimeError):
    """The installed host policy cannot safely own this hook event."""


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


def _state_error_text(exc: AdmissionStateError) -> str:
    diagnostic = exc.diagnostic()
    pid = diagnostic.get("lease_pid") or "unknown"
    identity = diagnostic.get("lease_process_identity") or "unknown"
    return (
        "Limen host admission failed closed: "
        f"invalid_field={diagnostic['invalid_field']} "
        f"reader_protocol={diagnostic['reader_protocol']} "
        f"writer_protocol={diagnostic['writer_protocol']} "
        f"pid_identity={pid}/{identity}. "
        f"Safe next command: {diagnostic['safe_next_command']}"
    )


def _runtime_interpreter(target: Path) -> str:
    """Use the immutable runtime's own interpreter when its layout is present."""

    try:
        resolved = target.resolve(strict=True)
    except OSError:
        return sys.executable
    runtime_root = resolved.parents[2] if len(resolved.parents) >= 3 else None
    candidate = runtime_root / "venv" / "bin" / "python" if runtime_root is not None else None
    return str(candidate) if candidate is not None and candidate.is_file() else sys.executable


def _probe_immutable_capabilities(target: Path) -> dict[str, Any]:
    """Require the exact project-declared protocol before delegating policy."""

    try:
        resolved = target.resolve(strict=True)
    except OSError as exc:
        raise ImmutableRuntimeError("runtime-entrypoint-missing") from exc
    if resolved == Path(__file__).resolve():
        raise ImmutableRuntimeError("runtime-entrypoint-is-mutable-project")
    try:
        completed = subprocess.run(
            [_runtime_interpreter(resolved), str(resolved), "--capabilities"],
            capture_output=True,
            text=True,
            timeout=_CAPABILITY_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ImmutableRuntimeError("runtime-capabilities-timeout") from exc
    except OSError as exc:
        raise ImmutableRuntimeError("runtime-capabilities-unavailable") from exc
    if completed.returncode != 0:
        raise ImmutableRuntimeError("runtime-capabilities-nonzero")
    try:
        observed = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ImmutableRuntimeError("runtime-capabilities-malformed") from exc
    if not isinstance(observed, dict):
        raise ImmutableRuntimeError("runtime-capabilities-not-an-object")
    expected = host_admission_capabilities()
    required = (
        "schema",
        "reader_protocol",
        "policy_revision",
        "state_schemas",
        "lease_kinds",
        "stable_action_denial",
        "single_rejection_channel",
        "migration",
    )
    mismatched = [field for field in required if observed.get(field) != expected.get(field)]
    if mismatched:
        raise ImmutableRuntimeError(f"runtime-capabilities-incompatible:{','.join(mismatched)}")
    return observed


def delegate_immutable(target: Path, raw: str) -> dict[str, Any] | None:
    """Run host-global policy only from the installed immutable runtime."""

    resolved = target.resolve(strict=False)
    _probe_immutable_capabilities(resolved)
    try:
        completed = subprocess.run(
            [_runtime_interpreter(resolved), str(resolved)],
            input=raw,
            capture_output=True,
            text=True,
            timeout=_DELEGATE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ImmutableRuntimeError("runtime-delegate-timeout") from exc
    except OSError as exc:
        raise ImmutableRuntimeError("runtime-delegate-unavailable") from exc
    if completed.returncode != 0:
        raise ImmutableRuntimeError("runtime-delegate-nonzero")
    if not completed.stdout.strip():
        return None
    try:
        output = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ImmutableRuntimeError("runtime-delegate-malformed-output") from exc
    if not isinstance(output, dict):
        raise ImmutableRuntimeError("runtime-delegate-output-not-an-object")
    return output


def _runtime_unavailable(
    payload: dict[str, Any],
    exc: ImmutableRuntimeError,
    *,
    controller: AdmissionController | None = None,
    owner_pid: int | None = None,
) -> dict[str, Any] | None:
    event = str(payload.get("hook_event_name") or "")
    text = (
        "Limen immutable host admission failed closed: "
        f"{exc}; reader_protocol={host_admission_capabilities()['reader_protocol']} "
        f"policy_revision={host_admission_capabilities()['policy_revision']}. "
        "Safe next command: domus-limen-runtime status"
    )
    if event == "UserPromptSubmit":
        # Session admission is never a global serialization boundary. Missing
        # immutable policy is handled at PreToolUse and inside guarded heavy
        # entrypoints; it must not prevent another Codex root from opening.
        return None
    if event == "Stop":
        owner = _turn_owner(payload)
        if owner is None:
            return _warning(text)
        try:
            _release_execution(
                controller or AdmissionController(),
                owner=owner,
                pid=owner_pid or codex_owner_pid(),
                cwd=str(payload.get("cwd") or ""),
            )
        except (AdmissionStateError, ValueError):
            return _warning(text)
        return None
    if event == "PreToolUse":
        action = classify_action(payload)
        if action.category == "observe":
            return None
        return _tool_deny(text)
    return _warning(text)


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
    # Older installed runtimes may have left an exact legacy execution record.
    # Releasing only the same owner/PID/start identity is safe migration cleanup;
    # current session start never creates or enforces this global lease.
    controller.release_owned("execution", owner=owner, pid=pid)


def handle(
    payload: dict[str, Any],
    *,
    controller: AdmissionController | None = None,
    owner_pid: int | None = None,
    closeout_probe: Callable[[str], bool] = _needs_bounded_closeout,
) -> dict[str, Any] | None:
    event = str(payload.get("hook_event_name") or "")

    # Starting or continuing a conversation is not work admission. Multiple
    # Codex roots are always allowed, including when structured action denial
    # is unavailable. Mutation and heavy-work boundaries are enforced below.
    if event == "UserPromptSubmit":
        return None

    controller = controller or AdmissionController()
    owner = _turn_owner(payload)
    pid = owner_pid or codex_owner_pid()

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
    if sys.argv[1:] == ["--capabilities"]:
        print(json.dumps(host_admission_capabilities(), separators=(",", ":"), sort_keys=True))
        return 0
    if len(sys.argv) == 3 and sys.argv[1] == "--delegate-immutable":
        raw = sys.stdin.read()
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("hook input must be a JSON object")
        except (json.JSONDecodeError, ValueError) as exc:
            output = _warning(f"Limen host admission hook failed closed: {exc}")
        else:
            try:
                output = delegate_immutable(Path(sys.argv[2]), raw)
            except ImmutableRuntimeError as exc:
                output = _runtime_unavailable(payload, exc)
        if output is not None:
            print(json.dumps(output, separators=(",", ":")))
        return 0
    event = ""
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be a JSON object")
        event = str(payload.get("hook_event_name") or "")
        output = handle(payload)
    except (AdmissionStateError, ValueError) as exc:
        text = (
            _state_error_text(exc)
            if isinstance(exc, AdmissionStateError)
            else (f"Limen host admission hook failed closed: {exc}")
        )
        if event == "PreToolUse":
            output = _tool_deny(text)
        else:
            output = _warning(text)
    if output is not None:
        print(json.dumps(output, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
