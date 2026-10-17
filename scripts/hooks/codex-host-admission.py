#!/usr/bin/env python3
"""Action-level Codex admission for concurrent isolated worktrees."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import signal
import subprocess
import sys
import time
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

from limen.action_admission import classify_action  # noqa: E402
from limen.action_admission_runtime import admit_pre_tool_action  # noqa: E402
from limen.bounded_subprocess import (  # noqa: E402
    BoundedSubprocessError,
    run_bounded_subprocess,
)
from limen.host_admission import (  # noqa: E402
    AdmissionController,
    AdmissionStateError,
    worktree_scope,
)

_EXECUTION_TTL_SECONDS = 24 * 60 * 60
_CAPABILITY_TIMEOUT_SECONDS = 1.0
_DELEGATE_TIMEOUT_SECONDS = 8.0
_INPUT_LIMIT_BYTES = 1024 * 1024
_HOOK_BUDGET_SECONDS = 8.0
_EVENTS = {"PreToolUse", "UserPromptSubmit", "Stop", "SubagentStart"}


class ImmutableRuntimeError(RuntimeError):
    """The installed host policy cannot safely own this hook event."""


class OwnerIdentityError(ValueError):
    """Fixed internal owner diagnostics, never text copied from hook input."""


class HookDeadlineExceeded(BaseException):
    """Cancellation must cross lower-level OSError/Exception recovery blocks."""


def _deadline_expired(_signum: int, _frame: Any) -> None:
    raise HookDeadlineExceeded("hook-evaluation-deadline")


def _read_input() -> str:
    source = getattr(sys.stdin, "buffer", sys.stdin)
    raw = source.read(_INPUT_LIMIT_BYTES + 1)
    encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
    if len(encoded) > _INPUT_LIMIT_BYTES:
        raise ValueError("hook-input-size-limit")
    return encoded.decode("utf-8")


def _parse_payload(raw: str, registered_event: str) -> dict[str, Any]:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("hook-input-not-object")
    event = payload.get("hook_event_name")
    if not isinstance(event, str) or event not in _EVENTS:
        raise ValueError("hook-input-event-invalid")
    if registered_event and event != registered_event:
        raise ValueError("hook-input-event-mismatch")
    if event == "PreToolUse" and (
        not isinstance(payload.get("tool_name"), str)
        or not payload["tool_name"]
        or not isinstance(payload.get("tool_input"), dict)
    ):
        raise ValueError("hook-input-tool-invalid")
    return payload


def _valid_delegate_verdict(output: dict[str, Any], event: str) -> bool:
    if event == "PreToolUse":
        verdict = output.get("hookSpecificOutput")
        return (
            set(output) == {"hookSpecificOutput"}
            and isinstance(verdict, dict)
            and verdict.get("hookEventName") == event
            and isinstance(verdict.get("permissionDecision"), str)
            and verdict.get("permissionDecision") in {"allow", "deny", "ask"}
            and isinstance(verdict.get("permissionDecisionReason"), str)
            and bool(verdict["permissionDecisionReason"])
        )
    if not output or not set(output) <= {"systemMessage", "continue", "stopReason", "hookSpecificOutput"}:
        return False
    if "continue" in output and not isinstance(output["continue"], bool):
        return False
    if output.get("continue") is False and not isinstance(output.get("stopReason"), str):
        return False
    if "systemMessage" in output and not isinstance(output["systemMessage"], str):
        return False
    return "hookSpecificOutput" not in output or (
        isinstance(output["hookSpecificOutput"], dict) and output["hookSpecificOutput"].get("hookEventName") == event
    )


def _hash_label(prefix: str, raw: str) -> str:
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"


def _process_table() -> dict[int, tuple[int, str]]:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,command="],
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


def _is_codex_process(command: str) -> bool:
    """Return true only for an evidence-bearing Codex or ChatGPT process."""

    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if not tokens:
        return False
    executable_path = tokens[0].casefold()
    executable = Path(executable_path).name
    if executable.startswith("codex") or executable == "chatgpt":
        return True
    if "/applications/chatgpt.app/contents/" in executable_path:
        return True
    if executable not in {"node", "nodejs"}:
        return False
    for token in tokens[1:]:
        candidate = token.casefold().rstrip("/")
        if "/@openai/codex/" in candidate:
            return True
        if Path(candidate).name.startswith("codex"):
            return True
    return False


def codex_owner_pid() -> int:
    """Resolve a proven durable Codex ancestor; never lease a terminal fallback."""

    current = os.getppid()
    table = _process_table()
    if not table:
        raise OwnerIdentityError("durable Codex owner process table is unavailable")
    seen: set[int] = set()
    for _ in range(32):
        if current <= 1 or current in seen:
            break
        seen.add(current)
        row = table.get(current)
        if row is None:
            break
        parent, command = row
        if _is_codex_process(command):
            return current
        current = parent
    raise OwnerIdentityError("durable Codex owner ancestor cannot be proven")


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
        completed = run_bounded_subprocess(
            [_runtime_interpreter(resolved), str(resolved), "--capabilities"],
            cwd=ROOT,
            timeout_seconds=_CAPABILITY_TIMEOUT_SECONDS,
            stdout_ceiling=65536,
            stderr_ceiling=8192,
        )
    except subprocess.TimeoutExpired as exc:
        raise ImmutableRuntimeError("runtime-capabilities-timeout") from exc
    except OSError as exc:
        raise ImmutableRuntimeError("runtime-capabilities-unavailable") from exc
    except BoundedSubprocessError as exc:
        raise ImmutableRuntimeError(f"runtime-capabilities-{exc.kind}") from exc
    if completed.returncode != 0:
        raise ImmutableRuntimeError("runtime-capabilities-nonzero")
    try:
        observed = json.loads(completed.stdout)
    except (json.JSONDecodeError, UnicodeError) as exc:
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
        completed = run_bounded_subprocess(
            [_runtime_interpreter(resolved), str(resolved)],
            input_bytes=raw.encode("utf-8"),
            cwd=ROOT,
            timeout_seconds=_DELEGATE_TIMEOUT_SECONDS,
            stdout_ceiling=65536,
            stderr_ceiling=8192,
        )
    except subprocess.TimeoutExpired as exc:
        raise ImmutableRuntimeError("runtime-delegate-timeout") from exc
    except OSError as exc:
        raise ImmutableRuntimeError("runtime-delegate-unavailable") from exc
    except BoundedSubprocessError as exc:
        raise ImmutableRuntimeError(f"runtime-delegate-{exc.kind}") from exc
    if completed.returncode != 0:
        raise ImmutableRuntimeError("runtime-delegate-nonzero")
    if not completed.stdout.strip():
        return None
    try:
        output = json.loads(completed.stdout)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ImmutableRuntimeError("runtime-delegate-malformed-output") from exc
    if not isinstance(output, dict):
        raise ImmutableRuntimeError("runtime-delegate-output-not-an-object")
    if not _valid_delegate_verdict(output, json.loads(raw).get("hook_event_name", "")):
        raise ImmutableRuntimeError("runtime-delegate-invalid-verdict")
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

    if event == "PreToolUse":
        # Observation and sanctioned self-gated controls do not need a durable
        # writer owner. Return before walking process ancestry so read-only
        # operation remains available when that ancestry cannot be proven.
        action = classify_action(payload)
        if action.category in {"observe", "sanctioned_control"}:
            return None
        controller = controller or AdmissionController()
        owner = _turn_owner(payload)
        if owner is None:
            return _tool_deny("Limen host admission denied mutation: durable Codex session identity is missing")
        pid = owner_pid or codex_owner_pid()
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

    controller = controller or AdmissionController()
    owner = _turn_owner(payload)
    pid = owner_pid or codex_owner_pid()

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


def _main(args: list[str], registered_event: str) -> int:
    if args == ["--capabilities"]:
        print(json.dumps(host_admission_capabilities(), separators=(",", ":"), sort_keys=True))
        return 0
    if len(args) == 2 and args[0] == "--delegate-immutable":
        try:
            raw = _read_input()
            payload = _parse_payload(raw, registered_event)
        except (json.JSONDecodeError, ValueError) as exc:
            output = _boundary_failure(registered_event, exc)
        else:
            try:
                output = delegate_immutable(Path(args[1]), raw)
            except ImmutableRuntimeError as exc:
                output = _runtime_unavailable(payload, exc)
        if output is not None:
            print(json.dumps(output, separators=(",", ":")))
        return 0
    event = registered_event
    try:
        payload = _parse_payload(_read_input(), registered_event)
        event = str(payload.get("hook_event_name") or "")
        output = handle(payload)
    except (AdmissionStateError, ValueError) as exc:
        if isinstance(exc, AdmissionStateError):
            text = _state_error_text(exc)
        elif isinstance(exc, OwnerIdentityError):
            text = f"Limen host admission failed closed: {exc}"
        else:
            text = f"Limen host admission hook evaluation unavailable: {type(exc).__name__}"
        if event == "PreToolUse" or not event:
            output = _tool_deny(text)
        else:
            output = _warning(text)
    if output is not None:
        print(json.dumps(output, separators=(",", ":")))
    return 0


def _boundary_failure(event: str, exc: BaseException) -> dict[str, Any]:
    # Error class is enough to diagnose the boundary without copying input or
    # private paths from exception messages into audit logs.
    text = f"Limen host admission evaluation unavailable: {type(exc).__name__}"
    return _warning(text) if event in _EVENTS - {"PreToolUse"} else _tool_deny(text)


def main() -> int:
    args = list(sys.argv[1:])
    event = ""
    started = time.monotonic()
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    try:
        if "--event" in args:
            index = args.index("--event")
            event = args[index + 1]
            del args[index : index + 2]
            if event not in _EVENTS or "--event" in args:
                event = ""
                raise ValueError("hook-registration-event-invalid")
        signal.signal(signal.SIGALRM, _deadline_expired)
        budget = min(_HOOK_BUDGET_SECONDS, previous_timer[0] or _HOOK_BUDGET_SECONDS)
        signal.setitimer(signal.ITIMER_REAL, budget)
        return _main(args, event)
    except (Exception, HookDeadlineExceeded) as exc:
        print(json.dumps(_boundary_failure(event, exc), separators=(",", ":")))
        return 0
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0]:
            remaining = max(0.000001, previous_timer[0] - (time.monotonic() - started))
            signal.setitimer(signal.ITIMER_REAL, remaining, previous_timer[1])


if __name__ == "__main__":
    raise SystemExit(main())
