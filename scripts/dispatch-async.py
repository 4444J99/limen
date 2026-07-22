#!/usr/bin/env python3
"""dispatch-async.py — ASYNC dispatch: decouple the beat from agent runtime (the real throughput fix
for "the slowest of N agents gates the whole beat / 900s gates every beat").

Each beat this does TWO fast, non-blocking things:
  (1) HARVEST — apply any finished background runs (logs/async-runs/*.result.json) to tasks.yaml
      under the queue-lock (reload-fresh + _apply_result, same as the sync commit).
  (2) RESERVE + LAUNCH — pick open tasks per lane within live runway + a LOCAL host slot cap, mark
      them dispatched, then SPAWN detached async-run-one workers and RETURN IMMEDIATELY.

Agents run in the background; their results land on a later beat. Beats stay fast regardless of how
slow any single agent is. Opt-in: the heartbeat calls this instead of dispatch-parallel.py when
LIMEN_DISPATCH_ASYNC=1. The synchronous dispatch-parallel.py is left completely unchanged.

Concurrency: at most LIMEN_ASYNC_MAX LOCAL background runs at once (default: live host CPU count);
remote lanes such as Jules are bounded by provider runway, not host slots. Per-agent in-flight count is tracked via
<task-id>__<agent>.running markers so budgets aren't blown between reserve & harvest.

Usage: dispatch-async.py --lanes auto --per-lane 8 --local-per-lane 3 [--local-max N] [--dry-run]
       dispatch-async.py --task-id TASK --execution-contract-hash SHA256 --targeted-only
       dispatch-async.py --recover-task TASK --reservation-id NONCE --execution-contract-hash SHA256

For a control-plane caller that has already selected one typed task, ``--targeted-only`` keeps
the operation exact: no broad harvest/reap and no always-working producer pass, and success is
reported only when the requested task is the sole launch. ``--json-output`` emits a final
machine-readable counts-only receipt for that decision.
"""

import argparse
import datetime
import hashlib
import json
import math
import os
import re
import secrets
import signal
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.capacity import LOCAL_CHECKOUT_AGENTS, _weak_proxy_exhaustion, select_lanes  # noqa: E402
from limen.execution_contract import execution_contract_hash  # noqa: E402
from limen.intake import IntakeContractError, normalize_selected_legacy_task  # noqa: E402
from limen.io import load_limen_file  # noqa: E402
from limen.models import DispatchLogEntry, dispatch_agent, dispatch_session_id  # noqa: E402
from limen.provider_selection import execution_profile_for  # noqa: E402
from limen.remote_execution import (  # noqa: E402
    RemoteExecutionError,
    validate_remote_submission_harvest,
    verification_context_for_task,
)
from limen.remote_predicate import canonical_json, digest_bytes, digest_text  # noqa: E402
from limen.tabularius import apply_limen_file_sync  # noqa: E402
from limen.dispatch import (  # noqa: E402
    WORKSTREAM_SUCCESSOR_REQUIRED_LABEL,
    _apply_result,
    _REMOTE_SUBMISSION_RECEIPTS,
    _deps_met,
    _dispatchable,
    task_work_loan_readiness,
    _down_lanes,
    _effective_target_agent,
    _has_done_transition,
    _is_blocked_result,
    _queue_lock,
    _reset_budget_if_needed,
    _restore_done_status,
    _restore_pr_open_status,
    _routine_generated_buildout_allowed,
    _admission_lease_path,
    _active_admission_leases,
    _machine_admission_lock,
    _machine_admission_reserved_gib,
    _release_machine_admission,
    _snapshot_with_machine_reservations,
    _transfer_machine_admission_owner,
    _superseded_by_rebase_task,
    _worktree_admission_for_task,
    _worktree_admission_snapshot,
    _value_tier_repos,
    agent_can_run_task,
    chronic_dispatch_reason,
    dispatch_admission_check,
    print_dispatch_admission_block,
    run_always_working_before_dispatch,
    sort_value_gate_candidates,
)

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
TASKS = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
RUNS = ROOT / "logs" / "async-runs"
RECEIPT_ARCHIVE = ROOT / ".limen-private" / "async-runs" / "archive"
REMOTE_RECEIPT_ROOT = Path(
    os.environ.get("LIMEN_REMOTE_RECEIPT_ROOT", str(ROOT / "logs" / "remote-execution"))
).expanduser()
WORKER = ROOT / "scripts" / "async-run-one.py"
_TOKEN_RE = re.compile(r"(github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{12,})")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_SAFE_STEM_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_ASYNC_RESERVATION_RE = re.compile(r"^async-reserve:[0-9a-f]{32}$")


def _truthy_env(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _int_or_default(raw: object, default: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    return _int_or_default(os.environ.get(name), default)


def _default_local_max() -> int:
    """Host-sized local ceiling; VITALS applies live memory backpressure separately."""
    return max(1, os.cpu_count() or 1)


def _disk_free_gib() -> float | None:
    path = Path(os.environ.get("LIMEN_DISK_PRESSURE_PATH", str(ROOT)))
    try:
        return shutil.disk_usage(path).free / (1024**3)
    except OSError:
        return None


def _disk_pressure_active() -> bool:
    if not _truthy_env("LIMEN_DISK_PRESSURE_VALUE_ONLY", True):
        return False
    floor = _env_int(
        "LIMEN_DISK_FLOOR_GIB",
        _env_int("LIMEN_ALWAYS_WORKING_MIN_FREE_GIB", 45),
    )
    free = _disk_free_gib()
    return free is not None and free < floor


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _run_stem(task_id: str) -> str:
    """Return a filename-safe stem while leaving legacy safe task ids unchanged."""
    if _SAFE_STEM_RE.fullmatch(task_id):
        return task_id
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", task_id).strip("._-") or "task"
    digest = hashlib.sha1(task_id.encode("utf-8")).hexdigest()[:12]
    return f"{slug[:80]}--{digest}"


def _run_log_path(task_id: str) -> Path:
    return RUNS / f"{_run_stem(task_id)}.log"


def _reservation_suffix(reservation_id: str) -> str:
    return hashlib.sha256(reservation_id.encode("utf-8")).hexdigest()[:16]


def _result_path(task_id: str, reservation_id: str | None = None) -> Path:
    suffix = f"--{_reservation_suffix(reservation_id)}" if reservation_id and reservation_id != "async-reserve" else ""
    return RUNS / f"{_run_stem(task_id)}{suffix}.result.json"


def _running_marker_path(task_id: str, agent: str, reservation_id: str | None = None) -> Path:
    suffix = f"--{_reservation_suffix(reservation_id)}" if reservation_id and reservation_id != "async-reserve" else ""
    return RUNS / f"{_run_stem(task_id)}__{agent}{suffix}.running"


def _new_async_reservation_id() -> str:
    return f"async-reserve:{secrets.token_hex(16)}"


def _is_async_reservation_id(value: str) -> bool:
    return value == "async-reserve" or bool(_ASYNC_RESERVATION_RE.fullmatch(value))


def _write_running_marker(
    task_id: str,
    agent: str,
    now: datetime.datetime,
    pid: int,
    reserved_gib: float,
    reservation_id: str | None = None,
) -> None:
    """Publish the marker atomically so slot readers never observe a partial JSON document."""
    marker = _running_marker_path(task_id, agent, reservation_id)
    tmp = marker.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(
        json.dumps(
            {
                "started_at": now.isoformat(),
                "agent": agent,
                "task_id": task_id,
                "pid": pid,
                "reserved_gib": reserved_gib,
                "reservation_id": reservation_id,
            }
        )
    )
    os.replace(tmp, marker)


def _rollback_unlaunched_reservation(
    agent: str,
    task_id: str,
    reservation_id: str,
    now: datetime.datetime,
    error: Exception,
) -> bool:
    """Reopen/refund an async reservation when no worker process was created."""
    with _queue_lock(TASKS) as got:
        if not got:
            return False
        lf = load_limen_file(TASKS)
        task = next((candidate for candidate in lf.tasks if candidate.id == task_id), None)
        if task is None or task.status != "dispatched":
            return True
        last = task.dispatch_log[-1] if task.dispatch_log else None
        if last is None or dispatch_session_id(last) != reservation_id or dispatch_agent(last) != agent:
            return True
        successor_required = WORKSTREAM_SUCCESSOR_REQUIRED_LABEL in (task.labels or [])
        task.status = "failed" if successor_required else "open"
        task.updated = now
        task.dispatch_log.append(
            DispatchLogEntry(
                timestamp=now,
                agent=agent,
                session_id="async-launch-failed",
                status=task.status,
                lifecycle_repair="stale-successor-hold" if successor_required else None,
                liveness_evidence="launch-failed" if successor_required else None,
                liveness_reservation_id=reservation_id if successor_required else None,
                liveness_age_seconds=0.0 if successor_required else None,
                output=(
                    "dispatch-async: detached worker did not launch; successor-required reservation "
                    f"released without reopening ({str(error)[:160]})"
                    if successor_required
                    else f"dispatch-async: detached worker did not launch; reservation reopened ({str(error)[:160]})"
                ),
            )
        )
        cost = max(0, int(task.budget_cost or 0))
        track = lf.portal.budget.track
        track.spent = max(0, track.spent - cost)
        track.per_agent[agent] = max(0, track.per_agent.get(agent, 0) - cost)
        apply_limen_file_sync(TASKS, lf, agent="dispatch-async", session_id="launch-failure")
        return True


def _marker_task_agent(marker: Path) -> tuple[str, str]:
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            task_id = str(data.get("task_id") or "")
            agent = str(data.get("agent") or "")
            if task_id and agent:
                return task_id, agent
    except (OSError, ValueError):
        pass
    task_id, agent = marker.name[: -len(".running")].rsplit("__", 1)
    return task_id, agent


def _result_task_id(result_file: Path) -> str:
    try:
        data = json.loads(result_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            task_id = str(data.get("task_id") or "")
            if task_id:
                return task_id
    except (OSError, ValueError):
        pass
    return result_file.name[: -len(".result.json")]


def _result_exists(task_id: str, reservation_id: str | None = None) -> bool:
    stem = _run_stem(task_id)
    expected_name = _result_path(task_id, reservation_id).name if reservation_id else None
    for path in RUNS.glob("*.result.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        if isinstance(data, dict) and str(data.get("task_id") or "") == task_id:
            if reservation_id is None or data.get("reservation_id") == reservation_id:
                return True
        if expected_name is not None and path.name == expected_name:
            return True
        if reservation_id is None and (
            path.name == f"{stem}.result.json"
            or (path.name.startswith(f"{stem}--") and path.name.endswith(".result.json"))
        ):
            return True
    return False


def _clear_running_markers(task_id: str, reservation_id: str | None = None) -> None:
    prefix = f"{task_id}__"
    for marker in RUNS.glob("*.running"):
        try:
            marker_task_id, _agent = _marker_task_agent(marker)
        except ValueError:
            marker_task_id = ""
        if marker_task_id != task_id and not marker.name.startswith(prefix):
            continue
        if reservation_id is not None:
            try:
                marker_reservation = _running_marker_info(marker).get("reservation_id")
            except (OSError, ValueError):
                marker_reservation = None
            if marker_reservation != reservation_id:
                continue
        marker.unlink(missing_ok=True)


def _running_marker_info(marker: Path) -> dict[str, object]:
    raw = marker.read_text().strip()
    try:
        data = json.loads(raw)
        started = datetime.datetime.fromisoformat(str(data.get("started_at") or ""))
        pid = data.get("pid")
        return {
            "started_at": started,
            "pid": int(pid) if pid is not None else None,
            "reservation_id": data.get("reservation_id"),
        }
    except Exception:
        return {
            "started_at": datetime.datetime.fromisoformat(raw),
            "pid": None,
            "reservation_id": None,
        }


def _marker_claim_matches(
    marker: Path,
    task_id: str,
    agent: str,
    reservation_id: str | None,
) -> bool:
    """Prove a scanned marker still names the same reservation.

    Reapers call this again while holding the queue lock.  A worker can publish
    its result and unlink its marker between the initial filesystem scan and
    that lock; neither a missing/replaced marker nor an unreadable marker is
    authority to reopen the board row.
    """

    if marker != _running_marker_path(task_id, agent, reservation_id) or not marker.is_file():
        return False
    try:
        marker_task_id, marker_agent = _marker_task_agent(marker)
        marker_reservation_id = _running_marker_info(marker).get("reservation_id")
    except Exception:
        return False
    return marker_task_id == task_id and marker_agent == agent and marker_reservation_id == reservation_id


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _worker_has_defunct_child(pid: int) -> bool:
    try:
        proc = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,stat="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    for line in proc.stdout.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            ppid = int(parts[1])
        except ValueError:
            continue
        if ppid == pid and "Z" in parts[2]:
            return True
    return False


def _kill_worker_group(pid: int | None) -> None:
    if pid is None:
        return
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def _redact_receipt_value(value: object) -> object:
    if isinstance(value, str):
        redacted = _TOKEN_RE.sub("[REDACTED_TOKEN]", value)
        redacted = _EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)
        if len(redacted) > 4000:
            redacted = f"{redacted[:4000]}...[TRUNCATED {len(redacted) - 4000} chars]"
        return redacted
    if isinstance(value, list):
        return [_redact_receipt_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_receipt_value(item) for key, item in value.items()}
    return value


def _archive_result_receipt(
    receipt_path: Path,
    raw: bytes,
    now: datetime.datetime,
    *,
    parsed: object | None,
    reason: str,
    parse_error: str | None = None,
    blocker: str | None = None,
) -> Path:
    day_dir = RECEIPT_ARCHIVE / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", receipt_path.name)
    out = day_dir / f"{stamp}-{safe_name}"
    counter = 1
    while out.exists():
        out = day_dir / f"{stamp}-{counter}-{safe_name}"
        counter += 1
    try:
        source = str(receipt_path.relative_to(ROOT))
    except ValueError:
        source = str(receipt_path)
    archive = {
        "archived_at": now.isoformat(),
        "source": source,
        "reason": reason,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_bytes": len(raw),
        "receipt": _redact_receipt_value(parsed) if parsed is not None else None,
    }
    if parse_error:
        archive["parse_error"] = _redact_receipt_value(parse_error)
        archive["raw_preview"] = _redact_receipt_value(raw.decode("utf-8", errors="replace"))
    if blocker:
        archive["blocker"] = _redact_receipt_value(blocker)
    out.write_text(json.dumps(archive, indent=2, sort_keys=True) + "\n")
    return out


def harvest() -> int:
    """Apply finished background runs to tasks.yaml under the lock. Returns count applied."""
    RUNS.mkdir(parents=True, exist_ok=True)
    files = sorted(RUNS.glob("*.result.json"))
    if not files:
        return 0
    now = _now()
    applied = 0
    with _queue_lock(TASKS) as got:
        if not got:
            # Lock timed out — skip this pass (honor the contract). The .result.json files are only
            # unlinked INSIDE the lock below, so returning here preserves them for the next beat.
            return applied
        lf = load_limen_file(TASKS)
        byid = {t.id: t for t in lf.tasks}
        track = lf.portal.budget.track
        for rf in files:
            raw = b""
            try:
                raw = rf.read_bytes()
                data = json.loads(raw.decode("utf-8"))
            except Exception as exc:
                _archive_result_receipt(
                    rf,
                    raw,
                    now,
                    parsed=None,
                    reason="malformed-result",
                    parse_error=str(exc),
                )
                rf.unlink(missing_ok=True)
                continue
            if not isinstance(data, dict):
                _archive_result_receipt(
                    rf,
                    raw,
                    now,
                    parsed=data,
                    reason="malformed-result",
                    parse_error="result receipt JSON root is not an object",
                )
                rf.unlink(missing_ok=True)
                continue
            task_id = data.get("task_id")
            remote_submission = data.get("remote_submission")
            remote_hint = data.get("agent") == "github_actions" or (
                remote_submission is not None and remote_submission != {}
            )
            if not isinstance(task_id, str) or not task_id:
                _archive_result_receipt(
                    rf,
                    raw,
                    now,
                    parsed=data,
                    reason="remote-metadata-blocked" if remote_hint else "harvest-fenced",
                    blocker="async result task ID is missing or non-string" if remote_hint else None,
                )
                rf.unlink(missing_ok=True)
                continue
            t = byid.get(task_id) if isinstance(task_id, str) else None
            expected_hash = data.get("execution_contract_hash")
            agent = data.get("agent")
            reservation_id = data.get("reservation_id")
            reservation_id_valid = reservation_id is None or (
                isinstance(reservation_id, str) and _is_async_reservation_id(reservation_id)
            )
            result_path_matches = bool(
                isinstance(task_id, str)
                and (
                    rf == _result_path(task_id, reservation_id)
                    if isinstance(reservation_id, str)
                    else rf == _result_path(task_id)
                )
            )
            custody_ok = (
                isinstance(task_id, str)
                and bool(task_id)
                and isinstance(agent, str)
                and bool(agent)
                and isinstance(expected_hash, str)
                and re.fullmatch(r"[0-9a-f]{64}", expected_hash) is not None
                and data.get("execution_started") is True
                and "result" in data
                and reservation_id_valid
                and result_path_matches
                and t is not None
                and t.status == "dispatched"
            )
            if custody_ok:
                try:
                    custody_ok = execution_contract_hash(t) == expected_hash
                except Exception:
                    custody_ok = False
            if custody_ok:
                last = t.dispatch_log[-1] if t.dispatch_log else None
                last_reservation_id = dispatch_session_id(last) if last is not None else ""
                reservation_matches = bool(
                    last is not None
                    and (
                        (reservation_id is None and last_reservation_id == "async-reserve")
                        or (isinstance(reservation_id, str) and last_reservation_id == reservation_id)
                    )
                )
                custody_ok = bool(
                    custody_ok
                    and reservation_matches
                    and last is not None
                    and last.status == "dispatched"
                    and dispatch_agent(last) == agent
                )

            authoritative_worker_receipt = custody_ok
            remote_blocker: str | None = None
            validated_remote: dict[str, object] | None = None
            last = t.dispatch_log[-1] if t is not None and t.dispatch_log else None
            requires_remote_identity = remote_hint or "github_actions" in {
                str(t.target_agent if t is not None else ""),
                dispatch_agent(last) if last is not None else "",
            }
            result_value = data.get("result")
            remote_preflight_blocked = bool(
                custody_ok
                and requires_remote_identity
                and isinstance(result_value, (bool, str))
                and _is_blocked_result(result_value)
                and (remote_submission is None or remote_submission == {})
            )
            if custody_ok and requires_remote_identity and not remote_preflight_blocked:
                try:
                    if (
                        last is None
                        or not isinstance(reservation_id, str)
                        or not _ASYNC_RESERVATION_RE.fullmatch(reservation_id)
                        or dispatch_session_id(last) != reservation_id
                        or dispatch_agent(last) != agent
                    ):
                        raise RemoteExecutionError(
                            "remote async result no longer matches the current authoritative reservation"
                        )
                    if t is None or not t.predicate or not t.receipt_target:
                        raise RemoteExecutionError("current remote task contract is incomplete")
                    current_context = verification_context_for_task(t, byid)
                    execution_profile = execution_profile_for(t).as_dict()
                    expected_request_contract = {
                        "predicate_digest": digest_text(t.predicate.strip()),
                        "instruction_digest": digest_text(
                            f"Verify completed implementation for task {t.id}; do not modify code: {t.title}"
                        ),
                        "receipt_target": t.receipt_target,
                        "custody_mode": "artifact",
                        "inputs": [],
                        "execution_profile": execution_profile,
                        "execution_profile_digest": digest_bytes(canonical_json(execution_profile)),
                        "verification_context_digest": digest_bytes(canonical_json(current_context)),
                    }
                    validated_remote = validate_remote_submission_harvest(
                        remote_submission,
                        result=data.get("result"),
                        agent=agent,
                        expected_agent=dispatch_agent(last),
                        expected_request_contract=expected_request_contract,
                        task_id=t.id,
                        task_repo=t.repo,
                        root=ROOT,
                        receipt_root=REMOTE_RECEIPT_ROOT,
                    )
                except (RemoteExecutionError, TypeError, ValueError) as exc:
                    custody_ok = False
                    remote_blocker = str(exc)

            if custody_ok:
                if data["result"] != "__notask__":
                    if validated_remote is not None:
                        _REMOTE_SUBMISSION_RECEIPTS[task_id] = validated_remote
                    try:
                        _apply_result(t, agent, data["result"], now, track, charge_budget=False)
                    finally:
                        _REMOTE_SUBMISSION_RECEIPTS.pop(task_id, None)
                    applied += 1
                _clear_running_markers(
                    task_id,
                    (reservation_id if isinstance(reservation_id, str) and reservation_id != "async-reserve" else None),
                )
                archive_reason = "harvested"
            else:
                _REMOTE_SUBMISSION_RECEIPTS.pop(task_id, None)
                # A receipt is untrusted input.  Task id alone is never custody: a stale worker or
                # forged/legacy receipt must not mutate (or clear the marker of) a changed claim.
                if requires_remote_identity:
                    if authoritative_worker_receipt and isinstance(reservation_id, str):
                        _clear_running_markers(task_id, reservation_id)
                    archive_reason = "remote-metadata-blocked"
                    remote_blocker = remote_blocker or "remote async result failed authoritative execution custody"
                else:
                    archive_reason = "harvest-fenced"
            _archive_result_receipt(
                rf,
                raw,
                now,
                parsed=data,
                reason=archive_reason,
                blocker=remote_blocker,
            )
            rf.unlink(missing_ok=True)
        if applied:
            apply_limen_file_sync(TASKS, lf, agent="dispatch-async", session_id="harvest")
    return applied


def inspect_harvest() -> int:
    """Count result files without applying or deleting them."""
    RUNS.mkdir(parents=True, exist_ok=True)
    return len(list(RUNS.glob("*.result.json")))


def reap_stale(max_age_s: int):
    """Free slots from DEAD workers. A .running marker older than max_age with no result file means
    the detached worker crashed/was-killed before finishing (OOM, host sleep, SIGKILL). Remove the
    marker and reopen the task so it's retried — otherwise it would leak a concurrency slot forever.
    Also reopen markerless async reservations after the same grace window: a worker that exits between
    board reservation and result publication can leave tasks.yaml stuck at dispatched with no .running
    marker for the normal reaper to see. A live slow worker is younger than max_age (call_agent_dispatch
    caps the agent at its timeout)."""
    RUNS.mkdir(parents=True, exist_ok=True)
    now = _now()
    defunct_grace_s = max(1, _env_int("LIMEN_ASYNC_DEFUNCT_GRACE", 120))
    reaped = []
    marker_claims: set[tuple[str, str | None]] = set()
    for m in RUNS.glob("*__*.running"):
        tid, agent = _marker_task_agent(m)
        try:
            info = _running_marker_info(m)
            age = (now - info["started_at"]).total_seconds()  # type: ignore[operator]
        except Exception:
            age = max_age_s + 1  # unreadable/empty marker → treat as stale
            info = {"pid": None, "reservation_id": None}
        pid = info.get("pid")
        reservation_id = info.get("reservation_id") if isinstance(info.get("reservation_id"), str) else None
        marker_claims.add((tid, reservation_id))
        dead_pid = isinstance(pid, int) and not _pid_alive(pid)
        zombie_stuck = isinstance(pid, int) and age > defunct_grace_s and _worker_has_defunct_child(pid)
        if age > max_age_s:
            # if the worker DID finish (result file present), let harvest handle it; don't reap
            if not _result_exists(tid, reservation_id):
                # Defer the marker unlink until the reopen is committed under the lock (below), so a
                # lock timeout can't leave the slot leaked (marker gone, task still 'dispatched').
                evidence = "dead-process" if dead_pid else "defunct-process" if zombie_stuck else "markerless-expired"
                # An old marker with a still-live exact PID remains protected.
                # Age alone can recover only a marker that has no process owner.
                if pid is None or dead_pid or zombie_stuck:
                    reaped.append(
                        (
                            tid,
                            agent,
                            m,
                            pid if isinstance(pid, int) else None,
                            reservation_id,
                            max(0.0, age),
                            evidence,
                        )
                    )
        elif dead_pid or zombie_stuck:
            if not _result_exists(tid, reservation_id):
                reaped.append(
                    (
                        tid,
                        agent,
                        m,
                        pid if isinstance(pid, int) else None,
                        reservation_id,
                        max(0.0, age),
                        "dead-process" if dead_pid else "defunct-process",
                    )
                )
    markerless = []
    try:
        lf_preview = load_limen_file(TASKS)
        for t in lf_preview.tasks:
            if t.status != "dispatched":
                continue
            if not t.dispatch_log:
                continue
            last = t.dispatch_log[-1]
            last_reservation_id = dispatch_session_id(last)
            if not _is_async_reservation_id(last_reservation_id) or last.status != "dispatched":
                continue
            reservation_id = last_reservation_id if _ASYNC_RESERVATION_RE.fullmatch(last_reservation_id) else None
            if (t.id, reservation_id) in marker_claims or _result_exists(t.id, reservation_id):
                continue
            stamp = t.updated or last.timestamp
            if stamp and (now - stamp).total_seconds() > max_age_s:
                markerless.append(
                    (
                        t.id,
                        dispatch_agent(last) or t.target_agent,
                        reservation_id,
                        max(0.0, (now - stamp).total_seconds()),
                    )
                )
    except Exception:
        markerless = []
    applied_reaped: list[str] = []
    applied_markerless = []
    if reaped or markerless:
        pids_to_kill: list[int | None] = []
        markers_to_remove: list[Path] = []
        with _queue_lock(TASKS) as got:
            if not got:
                # Lock busy — keep the markers (not yet unlinked) so a later beat retries the reap;
                # unlinking without reopening would leak the concurrency slot forever.
                return []
            lf = load_limen_file(TASKS)
            byid = {t.id: t for t in lf.tasks}
            changed = False
            for (
                tid,
                agent,
                marker,
                _pid,
                marker_reservation_id,
                marker_age,
                liveness_evidence,
            ) in reaped:
                # Revalidate the exact artifact and pending-result state under the
                # publication lock.  A result that won the race keeps custody and
                # must be harvested; it must never be converted into a retry.
                if not _marker_claim_matches(marker, tid, agent, marker_reservation_id):
                    continue
                t = byid.get(tid)
                last = t.dispatch_log[-1] if t is not None and t.dispatch_log else None
                last_reservation_id = dispatch_session_id(last) if last is not None else ""
                reservation_matches = bool(
                    last is not None
                    and last.status == "dispatched"
                    and dispatch_agent(last) == agent
                    and (
                        (marker_reservation_id is None and last_reservation_id == "async-reserve")
                        or last_reservation_id == marker_reservation_id
                    )
                )
                if t is not None and t.status == "dispatched" and reservation_matches:
                    if _result_exists(tid, marker_reservation_id):
                        continue
                    pids_to_kill.append(_pid)
                    markers_to_remove.append(marker)
                    applied_reaped.append(tid)
                    if _has_done_transition(t):
                        _restore_done_status(
                            t,
                            now,
                            agent=agent,
                            session_id="async-reap-stale",
                            output=(
                                "dispatch-async: stale worker marker reaped after prior done; restored terminal status"
                            ),
                        )
                        changed = True
                    elif _restore_pr_open_status(
                        t,
                        now,
                        agent=agent,
                        session_id="async-reap-stale",
                        output="dispatch-async: stale worker marker reaped after prior open PR; restored PR-open status",
                    ):
                        changed = True
                    else:
                        successor_required = WORKSTREAM_SUCCESSOR_REQUIRED_LABEL in (t.labels or [])
                        t.status = "failed" if successor_required else "open"
                        t.updated = now
                        t.dispatch_log.append(
                            DispatchLogEntry(
                                timestamp=now,
                                agent=agent,
                                session_id="async-reap-stale",
                                status=t.status,
                                lifecycle_repair=("stale-successor-hold" if successor_required else None),
                                liveness_evidence=(liveness_evidence if successor_required else None),
                                liveness_reservation_id=(last_reservation_id if successor_required else None),
                                liveness_pid=_pid if successor_required else None,
                                liveness_age_seconds=(marker_age if successor_required else None),
                                output=(
                                    f"dispatch-async: stale worker marker older than {max_age_s}s reaped; "
                                    "successor-required task held failed"
                                    if successor_required
                                    else (
                                        f"dispatch-async: stale worker marker older than {max_age_s}s "
                                        "reaped; task reopened"
                                    )
                                ),
                            )
                        )
                        changed = True
                else:
                    # This is a proven stale artifact for an older reservation.
                    # Its nonce-specific path can be retired without touching the
                    # current row, worker, marker, or result.
                    markers_to_remove.append(marker)
            if markerless:
                fresh_marker_claims: set[tuple[str, str | None]] = set()
                for marker in RUNS.glob("*__*.running"):
                    marker_tid, _marker_agent = _marker_task_agent(marker)
                    try:
                        marker_info = _running_marker_info(marker)
                    except Exception:
                        marker_info = {"reservation_id": None}
                    marker_reservation_id = (
                        marker_info.get("reservation_id")
                        if isinstance(marker_info.get("reservation_id"), str)
                        else None
                    )
                    fresh_marker_claims.add((marker_tid, marker_reservation_id))
                for tid, agent, reservation_id, marker_age in markerless:
                    t = byid.get(tid)
                    if (
                        t is None
                        or t.status != "dispatched"
                        or (tid, reservation_id) in fresh_marker_claims
                        or _result_exists(tid, reservation_id)
                        or not t.dispatch_log
                    ):
                        continue
                    last = t.dispatch_log[-1]
                    last_reservation_id = dispatch_session_id(last)
                    stamp = t.updated or last.timestamp
                    if (
                        not _is_async_reservation_id(last_reservation_id)
                        or (reservation_id is not None and last_reservation_id != reservation_id)
                        or (reservation_id is None and last_reservation_id != "async-reserve")
                        or last.status != "dispatched"
                        or not stamp
                        or (now - stamp).total_seconds() <= max_age_s
                    ):
                        continue
                    if _has_done_transition(t):
                        _restore_done_status(
                            t,
                            now,
                            agent=agent,
                            session_id="async-reap-stale",
                            output="dispatch-async: markerless stale async reservation restored terminal status",
                        )
                        applied_markerless.append(tid)
                        changed = True
                    elif _restore_pr_open_status(
                        t,
                        now,
                        agent=agent,
                        session_id="async-reap-stale",
                        output="dispatch-async: markerless stale async reservation restored PR-open status",
                    ):
                        applied_markerless.append(tid)
                        changed = True
                    else:
                        successor_required = WORKSTREAM_SUCCESSOR_REQUIRED_LABEL in (t.labels or [])
                        t.status = "failed" if successor_required else "open"
                        t.updated = now
                        t.dispatch_log.append(
                            DispatchLogEntry(
                                timestamp=now,
                                agent=agent,
                                session_id="async-reap-stale",
                                status=t.status,
                                lifecycle_repair=("stale-successor-hold" if successor_required else None),
                                liveness_evidence=("markerless-expired" if successor_required else None),
                                liveness_reservation_id=(last_reservation_id if successor_required else None),
                                liveness_age_seconds=(marker_age if successor_required else None),
                                output=(
                                    f"dispatch-async: markerless async reservation older than {max_age_s}s reaped; "
                                    + ("successor-required task held failed" if successor_required else "task reopened")
                                ),
                            )
                        )
                        applied_markerless.append(tid)
                        changed = True
            if changed:
                apply_limen_file_sync(TASKS, lf, agent="dispatch-async", session_id="reap-stale")
        for pid in pids_to_kill:
            _kill_worker_group(pid)
        # reopen is committed → now safe to remove the markers that freed these slots
        for marker in markers_to_remove:
            marker.unlink(missing_ok=True)
    return applied_reaped + applied_markerless


def inspect_stale(max_age_s: int) -> list[str]:
    """Return stale marker task ids without deleting markers or reopening tasks."""
    RUNS.mkdir(parents=True, exist_ok=True)
    now = _now()
    stale = []
    for m in RUNS.glob("*__*.running"):
        try:
            info = _running_marker_info(m)
            age = (now - info["started_at"]).total_seconds()  # type: ignore[operator]
        except Exception:
            age = max_age_s + 1
            info = {"reservation_id": None}
        if age > max_age_s:
            tid, _agent = _marker_task_agent(m)
            reservation_id = info.get("reservation_id") if isinstance(info.get("reservation_id"), str) else None
            if not _result_exists(tid, reservation_id):
                stale.append(tid)
    return stale


def default_max_age_s() -> int:
    """Keep stale reaping above the local lane timeout so live bounded workers are not reopened."""
    env = os.environ.get("LIMEN_ASYNC_MAX_AGE")
    if env is not None:
        return max(1, _int_or_default(env, 2100))
    lane_timeout = max(1, _env_int("LIMEN_LANE_TIMEOUT", 1800))
    return max(1200, lane_timeout + 300)


def _running_total() -> int:
    return len(list(RUNS.glob("*.running")))


def _nonce_artifact_reservation(path: Path, task_id: str) -> str | None:
    if path.is_symlink():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or str(payload.get("task_id") or "") != task_id:
        return None
    reservation_id = payload.get("reservation_id")
    if not isinstance(reservation_id, str) or not _ASYNC_RESERVATION_RE.fullmatch(reservation_id):
        return None
    if path.name.endswith(".running"):
        agent = payload.get("agent")
        if not isinstance(agent, str) or path != _running_marker_path(task_id, agent, reservation_id):
            return None
    elif path.name.endswith(".result.json"):
        if path != _result_path(task_id, reservation_id):
            return None
    else:
        return None
    return reservation_id


def _running_local(*, exclude_task_id: str | None = None) -> int:
    """In-flight LOCAL-lane runs only. The concurrency cap bounds LOCAL host pressure (each local run
    holds a worktree + a ThreadPoolExecutor slot). An async/remote run (jules, github_actions, ...)
    executes OFF-BOX — a `jules remote new` session runs on Google's VM — so it must NOT consume a
    local slot, or a backlog of local work starves the remote lanes out of the cap entirely (the root
    cause of 'zero jules remote sessions launched'). Remote lanes stay bounded by their per-agent
    budget, not this local cap."""
    total = 0
    for m in RUNS.glob("*__*.running"):
        marker_task_id, agent = _marker_task_agent(m)
        if (
            exclude_task_id is not None
            and marker_task_id == exclude_task_id
            and _nonce_artifact_reservation(m, exclude_task_id) is not None
        ):
            continue
        if agent in LOCAL_CHECKOUT_AGENTS:  # census local_checkout authority, not a hand-kept lane set
            total += 1
    return total


def _running_for(agent: str, *, exclude_task_id: str | None = None) -> int:
    total = 0
    for marker in RUNS.glob("*__*.running"):
        marker_task_id, marker_agent = _marker_task_agent(marker)
        if marker_agent != agent:
            continue
        if (
            exclude_task_id is not None
            and marker_task_id == exclude_task_id
            and _nonce_artifact_reservation(marker, exclude_task_id) is not None
        ):
            continue
        total += 1
    return total


def _nonce_local_marker_reservations(task_id: str) -> tuple[int, float]:
    """Return only finite, nonce-fenced local promises for one exact task.

    These may be subtracted from an exact open-task admission snapshot because
    the new board nonce fences the old worker.  Legacy, malformed, remote, and
    unknown-size markers remain fail-closed and continue consuming capacity.
    """

    slots = 0
    reserved_gib = 0.0
    for marker in RUNS.glob("*__*.running"):
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                continue
            marker_task_id, marker_agent = _marker_task_agent(marker)
            raw_reserved_gib = payload.get("reserved_gib")
            if (
                marker_task_id != task_id
                or marker_agent not in LOCAL_CHECKOUT_AGENTS
                or _nonce_artifact_reservation(marker, task_id) is None
                or isinstance(raw_reserved_gib, bool)
                or not isinstance(raw_reserved_gib, (int, float))
            ):
                continue
            marker_reserved_gib = float(raw_reserved_gib)
            if not math.isfinite(marker_reserved_gib) or marker_reserved_gib < 0:
                continue
        except (OSError, ValueError, TypeError):
            continue
        slots += 1
        reserved_gib += marker_reserved_gib
    return slots, reserved_gib


def _running_task_ids() -> set[str]:
    ids: set[str] = set()
    for marker in RUNS.glob("*__*.running"):
        task_part = _marker_task_agent(marker)[0]
        if task_part:
            ids.add(task_part)
    return ids


def _result_task_ids() -> set[str]:
    return {_result_task_id(rf) for rf in RUNS.glob("*.result.json")}


def _claimed_task_ids() -> set[str]:
    return _running_task_ids() | _result_task_ids()


def _task_claim_artifacts_are_nonce_fenced(task_id: str) -> bool:
    artifacts = [
        path
        for path in [*RUNS.glob("*__*.running"), *RUNS.glob("*.result.json")]
        if (_marker_task_agent(path)[0] if path.name.endswith(".running") else _result_task_id(path)) == task_id
    ]
    return bool(artifacts) and all(_nonce_artifact_reservation(path, task_id) is not None for path in artifacts)


def _usage_by_agent() -> dict[str, dict[str, object]]:
    path = ROOT / "logs" / "usage.json"
    try:
        vendors = (json.loads(path.read_text(encoding="utf-8")) or {}).get("vendors", {})
    except (OSError, ValueError):
        return {}
    if not isinstance(vendors, dict):
        return {}
    return {str(agent): info for agent, info in vendors.items() if isinstance(info, dict)}


def _usage_remaining_by_agent(usage: dict[str, dict[str, object]]) -> dict[str, int]:
    """Live usage runway from logs/usage.json.

    The task board budget is a reservation ledger; usage telemetry is the live provider/run
    meter. Remote lanes such as Jules must satisfy both. Without this cap, a reserve override can
    make a lane selectable and then reserve every board-budget slot even when the rolling provider
    window only has a few runs left.
    """
    remaining: dict[str, int] = {}
    for agent, info in usage.items():
        if info.get("health") == "rate-limited" or info.get("recent_rate_limit"):
            remaining[str(agent)] = 0
            continue
        if "remaining" not in info:
            continue
        try:
            value = int(float(info["remaining"]))
        except (TypeError, ValueError):
            continue
        remaining[str(agent)] = max(0, value)
    return remaining


def _weak_proxy_agents(usage: dict[str, dict[str, object]]) -> set[str]:
    return {agent for agent, info in usage.items() if _weak_proxy_exhaustion(agent, info)}


def _effectively_unbounded_remaining(lf) -> int:
    """Enough budget units to let scheduler knobs, not the stale board cap, bound this beat."""
    total = 0
    for task in getattr(lf, "tasks", []) or []:
        if _dispatchable(task):
            total += int(getattr(task, "budget_cost", 1) or 1)
    return max(total, 1)


def _execution_contract_blocker(lf, task_id: str, expected_hash: str) -> dict[str, object] | None:
    """Compare the selected contract with fresh board state before any reservation mutation."""

    task = next((candidate for candidate in lf.tasks if candidate.id == task_id), None)
    actual_hash = execution_contract_hash(task) if task is not None else ""
    if task is not None and actual_hash == expected_hash:
        return None
    return {
        "id": "targeted-execution-contract-mismatch",
        "reason": (
            f"exact task {task_id} changed between owner selection and queue-locked reservation"
            if task is not None
            else f"exact task {task_id} disappeared before queue-locked reservation"
        ),
        "task_id": task_id,
        "expected_hash": expected_hash,
        "actual_hash": actual_hash,
    }


def _targeted_zero_launch_blocker(task_id: str, lanes: list[str]) -> dict[str, object]:
    """Name the gate that refused an exact-task launch so a targeted zero-launch is never silent.

    The overnight lane switch (and any exact-task conductor) needs the true refusing predicate to
    route around an unlaunchable packet.  A bare ``launched 0`` wedged the 2026-07-16 overnight
    lane in a WATCH_ALERT loop on a packet the capability contract can never launch (local lane +
    self-modifying repo + non-narrow predicate) because the receipt carried no blocker.  This is
    read-only: it re-walks the deterministic reservation filters and names the first refusal; the
    runtime-only gates (usage remaining, lane slots, worktree admission) stay attributed as such.
    """

    try:
        lf = load_limen_file(TASKS)
    except Exception as exc:
        return {
            "id": "targeted-zero-launch-board-unreadable",
            "task_id": task_id,
            "reason": str(exc)[:300],
        }
    task = next((candidate for candidate in lf.tasks if candidate.id == task_id), None)
    if task is None:
        return {
            "id": "targeted-task-missing",
            "task_id": task_id,
            "reason": f"exact task {task_id} is not on the board",
        }
    if not _dispatchable(task):
        return {
            "id": "targeted-task-not-dispatchable",
            "task_id": task_id,
            "reason": f"exact task {task_id} status is {task.status}; not in a dispatchable state",
        }
    effective_target = _effective_target_agent(task)
    if effective_target not in lanes and effective_target != "any":
        return {
            "id": "targeted-lane-mismatch",
            "task_id": task_id,
            "reason": f"exact task routes to {effective_target}; requested lanes {lanes}",
        }
    agent = effective_target if effective_target != "any" else (lanes[0] if lanes else "")
    if agent and not agent_can_run_task(agent, task):
        return {
            "id": "targeted-agent-capability-refused",
            "task_id": task_id,
            "reason": (
                f"lane {agent} cannot run exact task {task_id} under the dispatch capability "
                "contract (agent_can_run_task); a local lane requires an isolated "
                "narrow-verification predicate for a self-modifying repo task"
            ),
        }
    id2 = {candidate.id: candidate for candidate in lf.tasks}
    if not _deps_met(task, id2):
        return {
            "id": "targeted-deps-unmet",
            "task_id": task_id,
            "reason": f"exact task {task_id} has unmet dependencies {list(task.depends_on or [])}",
        }
    if not _routine_generated_buildout_allowed(task):
        return {
            "id": "targeted-buildout-gated",
            "task_id": task_id,
            "reason": f"exact task {task_id} is a routine generated buildout the value tier gates",
        }
    if task_id in _claimed_task_ids() and not _task_claim_artifacts_are_nonce_fenced(task_id):
        return {
            "id": "targeted-already-claimed",
            "task_id": task_id,
            "reason": f"exact task {task_id} already has a live claim artifact",
        }
    return {
        "id": "targeted-zero-launch-unattributed",
        "task_id": task_id,
        "reason": (
            f"exact task {task_id} passes the deterministic filters; a runtime gate "
            "(usage remaining, lane slots, or worktree admission) refused this beat"
        ),
    }


def _targeted_recovery_blocker(blocker_id: str, task_id: str, reason: str) -> dict[str, object]:
    return {"id": blocker_id, "task_id": task_id, "reason": reason[:500]}


def recover_exact_task(
    task_id: str,
    expected_contract_hash: str,
    *,
    reservation_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """Safely reopen one proven orphaned async reservation, never a broad claim set."""

    RUNS.mkdir(parents=True, exist_ok=True)
    now = _now()
    markers_to_remove: list[Path] = []
    with _queue_lock(TASKS) as got:
        if not got:
            return {
                "status": "blocked",
                "recovered_count": 0,
                "blocker": _targeted_recovery_blocker(
                    "targeted-recovery-queue-lock-busy", task_id, "task queue lock is busy"
                ),
            }
        lf = load_limen_file(TASKS)
        contract_blocker = _execution_contract_blocker(lf, task_id, expected_contract_hash)
        if contract_blocker:
            return {"status": "blocked", "recovered_count": 0, "blocker": contract_blocker}
        task = next(candidate for candidate in lf.tasks if candidate.id == task_id)
        if WORKSTREAM_SUCCESSOR_REQUIRED_LABEL in (task.labels or []):
            return {"status": "successor_required_held", "recovered_count": 0}
        if task.status == "open":
            return {"status": "already_open", "recovered_count": 0}
        if task.status != "dispatched":
            return {
                "status": "blocked",
                "recovered_count": 0,
                "blocker": _targeted_recovery_blocker(
                    "targeted-recovery-status-unsafe",
                    task_id,
                    f"exact task status is {task.status}; only an async dispatched claim can be recovered",
                ),
            }
        last = task.dispatch_log[-1] if task.dispatch_log else None
        last_reservation_id = dispatch_session_id(last) if last is not None else ""
        if last is None or not _is_async_reservation_id(last_reservation_id) or last.status != "dispatched":
            return {
                "status": "blocked",
                "recovered_count": 0,
                "blocker": _targeted_recovery_blocker(
                    "targeted-recovery-owner-unsafe",
                    task_id,
                    "exact claim is not owned by async-reserve",
                ),
            }
        active_reservation_id = last_reservation_id if _ASYNC_RESERVATION_RE.fullmatch(last_reservation_id) else None
        if active_reservation_id != reservation_id:
            return {
                "status": "blocked",
                "recovered_count": 0,
                "blocker": _targeted_recovery_blocker(
                    "targeted-recovery-reservation-mismatch",
                    task_id,
                    "exact recovery nonce does not match the current async reservation",
                ),
            }
        if _result_exists(task_id, active_reservation_id):
            return {"status": "result_pending_harvest", "recovered_count": 0}

        matching_markers: list[tuple[Path, int, float]] = []
        if active_reservation_id is not None:
            # A nonce-bound claim owns one deterministic marker path.  Do not
            # parse same-task artifacts from older reservations: malformed A
            # must not be able to block recovery of current reservation B.
            expected_marker = _running_marker_path(
                task_id,
                dispatch_agent(last) or task.target_agent,
                active_reservation_id,
            )
            marker_paths = [expected_marker] if expected_marker.is_file() else []
        else:
            marker_paths = list(RUNS.glob("*.running"))
        for marker in marker_paths:
            marker_task_id, marker_agent = _marker_task_agent(marker)
            if marker_task_id != task_id:
                continue
            try:
                marker_data = json.loads(marker.read_text(encoding="utf-8"))
                if not isinstance(marker_data, dict):
                    raise ValueError("marker JSON root is not an object")
                started_raw = marker_data.get("started_at")
                if not isinstance(started_raw, str):
                    raise ValueError("marker started_at is not a string")
                started_at = datetime.datetime.fromisoformat(started_raw)
                if started_at.tzinfo is None or started_at.utcoffset() is None:
                    raise ValueError("marker started_at is not timezone-aware")
                age_s = (now - started_at).total_seconds()
            except Exception as exc:
                return {
                    "status": "blocked",
                    "recovered_count": 0,
                    "blocker": _targeted_recovery_blocker(
                        "targeted-recovery-marker-unreadable",
                        task_id,
                        f"exact task marker cannot prove worker age or pid: {exc}",
                    ),
                }
            if marker_data.get("reservation_id") != active_reservation_id:
                continue
            if marker_agent != dispatch_agent(last):
                return {
                    "status": "blocked",
                    "recovered_count": 0,
                    "blocker": _targeted_recovery_blocker(
                        "targeted-recovery-marker-owner-mismatch",
                        task_id,
                        "exact task marker agent does not match the async reservation owner",
                    ),
                }
            pid = marker_data.get("pid")
            if type(pid) is not int or pid <= 0:
                return {
                    "status": "blocked",
                    "recovered_count": 0,
                    "blocker": _targeted_recovery_blocker(
                        "targeted-recovery-marker-pid-invalid",
                        task_id,
                        "exact task marker does not contain an explicit positive integer pid",
                    ),
                }
            matching_markers.append((marker, pid, age_s))

        if not matching_markers:
            return {
                "status": "blocked",
                "recovered_count": 0,
                "blocker": _targeted_recovery_blocker(
                    "targeted-recovery-marker-required",
                    task_id,
                    "exact recovery requires a readable stale marker with an explicit dead pid",
                ),
            }
        if len(matching_markers) != 1:
            return {
                "status": "blocked",
                "recovered_count": 0,
                "blocker": _targeted_recovery_blocker(
                    "targeted-recovery-marker-ambiguous",
                    task_id,
                    "exact task has multiple running markers; worker custody is ambiguous",
                ),
            }

        marker, pid, marker_age_s = matching_markers[0]
        try:
            pid_alive = _pid_alive(pid)
        except Exception as exc:
            return {
                "status": "blocked",
                "recovered_count": 0,
                "blocker": _targeted_recovery_blocker(
                    "targeted-recovery-pid-proof-unavailable",
                    task_id,
                    f"exact task pid liveness could not be proven: {exc}",
                ),
            }
        if pid_alive:
            return {"status": "already_running", "recovered_count": 0, "pid": pid}

        grace_s = max(1, _env_int("LIMEN_TARGETED_RECOVERY_GRACE", default_max_age_s()))
        if marker_age_s <= grace_s:
            return {
                "status": "blocked",
                "recovered_count": 0,
                "blocker": _targeted_recovery_blocker(
                    "targeted-recovery-marker-grace-active",
                    task_id,
                    "exact task marker is not stale enough for safe orphan recovery",
                ),
            }
        markers_to_remove = [marker]

        with _machine_admission_lock():
            live_leases = [lease for lease in _active_admission_leases() if lease.get("task_id") == task_id]
        if live_leases:
            return {
                "status": "blocked",
                "recovered_count": 0,
                "blocker": _targeted_recovery_blocker(
                    "targeted-recovery-live-lease",
                    task_id,
                    "exact claim still has a live machine-admission lease",
                ),
            }

        # Close the PID-reuse window after lease inspection.  A PID that is live now is not
        # recoverable even if the first probe observed it absent.
        try:
            pid_alive = _pid_alive(pid)
        except Exception as exc:
            return {
                "status": "blocked",
                "recovered_count": 0,
                "blocker": _targeted_recovery_blocker(
                    "targeted-recovery-pid-proof-unavailable",
                    task_id,
                    f"exact task pid liveness could not be revalidated: {exc}",
                ),
            }
        if pid_alive:
            return {"status": "already_running", "recovered_count": 0, "pid": pid}

        # Result publishers take this same queue lock. Recheck immediately before mutation so a
        # result that won the lock is harvested, while a late publisher sees the reopened status
        # and fences its receipt instead of applying it to a new claim.
        if _result_exists(task_id, active_reservation_id):
            return {"status": "result_pending_harvest", "recovered_count": 0}

        if dry_run:
            return {"status": "would_recover", "recovered_count": 0}
        task.status = "open"
        task.updated = now
        task.dispatch_log.append(
            DispatchLogEntry(
                timestamp=now,
                agent=task.target_agent,
                session_id="async-recover-exact",
                status="open",
                output="dispatch-async: exact orphaned async claim reopened after custody proof",
            )
        )
        apply_limen_file_sync(TASKS, lf, agent="dispatch-async", session_id="recover-exact")
    for marker in markers_to_remove:
        marker.unlink(missing_ok=True)
    return {"status": "recovered", "recovered_count": 1}


def _pick_reservations(
    lf,
    agents,
    per_agent,
    cap,
    dry,
    now,
    usage_remaining,
    weak_proxy_agents,
    task_id=None,
    local_per_agent=None,
    admission_snapshot=None,
    running_local=None,
    machine_lease=False,
):
    picked = []
    picked_ids = set(_claimed_task_ids())
    if task_id is not None and _task_claim_artifacts_are_nonce_fenced(task_id):
        # Exact selection is governed by the queue-locked board row.  Residue
        # from a recovered nonce A must not self-deadlock launch B; B's distinct
        # nonce fences A at worker preflight/publication.  Other tasks' markers
        # still count against host and lane limits below.
        picked_ids.discard(task_id)
    reset_changed = _reset_budget_if_needed(lf, now)
    track = lf.portal.budget.track
    unbounded_remaining = _effectively_unbounded_remaining(lf)
    value_repos = _value_tier_repos()
    disk_pressure = _disk_pressure_active()
    # Loud-not-silent (PR #1329): the WorkLoan admission gate inside _dispatchable now filters
    # un-underwritten candidates BEFORE they reach normalization, where the "INTAKE BLOCKED"
    # notice used to surface.  Report each agent-relevant rejection here, once, so a legacy
    # un-underwritten task is visibly blocked rather than silently dropped.
    for _t in lf.tasks:
        if task_id is not None and _t.id != task_id:
            continue
        if _t.target_agent != "any" and _t.target_agent not in agents:
            continue
        _readiness = task_work_loan_readiness(_t)
        if not _readiness.ready:
            print(f"  INTAKE BLOCKED {_t.id}: {_readiness.reason_code}")
    # Worktree admission is ALWAYS evaluated — an explicit --task does NOT bypass resource/VITALS/
    # reaper custody (a task-id run still creates a local worktree). The only override is the
    # documented LIMEN_WORKTREE_DEBT_GATE=0 lever (snapshot → inactive → gate returns False).
    admission_snapshot = admission_snapshot or _worktree_admission_snapshot()
    if admission_snapshot.get("reason") and not dry:
        print(f"── async: {admission_snapshot['reason']}")
    # The cap counts only LOCAL in-flight runs; remote/async lanes run off-box and are budgeted
    # separately below (see _running_local).
    slots = max(
        0,
        cap - (_running_local(exclude_task_id=task_id) if running_local is None else running_local),
    )
    id2 = {t.id: t for t in lf.tasks}  # for dependency resolution
    states = []
    for agent in agents:
        # Locality is the census authority (LOCAL_CHECKOUT_AGENTS); a non-local lane runs off-box.
        is_async = agent not in LOCAL_CHECKOUT_AGENTS  # remote lane — off-box, not gated by the local cap
        running_for_agent = _running_for(agent, exclude_task_id=task_id)
        lane_per_agent = per_agent if is_async else min(per_agent, local_per_agent or per_agent)
        launch_room = max(0, lane_per_agent - running_for_agent)
        if launch_room <= 0:
            continue
        # Board counters are a reservation ledger, not the physical provider ceiling. The only hard
        # launch ceiling here is live usage headroom when a real meter exists. Weak proxy rows such
        # as Agy's dispatch-count estimate are pacing signals only, so they must not cap work.
        if agent in weak_proxy_agents:
            agent_rem = None
        else:
            agent_rem = usage_remaining.get(agent)
        rem = unbounded_remaining if agent_rem is None else max(0, agent_rem)
        if rem <= 0:
            continue
        cands = [
            t
            for t in lf.tasks
            if _dispatchable(t)
            and (task_id is None or t.id == task_id)
            and _effective_target_agent(t) in {agent, "any"}
            and agent_can_run_task(agent, t)
            and t.budget_cost <= rem
            and _deps_met(t, id2)
            and (task_id is not None or not _superseded_by_rebase_task(t, id2))
            and _routine_generated_buildout_allowed(t)
        ]
        cands = sort_value_gate_candidates(cands, value_repos, disk_pressure=disk_pressure)
        states.append(
            {
                "agent": agent,
                "is_async": is_async,
                "agent_rem": agent_rem,
                "launch_room": launch_room,
                "cands": cands,
                "index": 0,
                "taken": 0,
            }
        )
    while states:
        progressed = False
        for state in states:
            if state["taken"] >= state["launch_room"]:
                continue
            if not state["is_async"] and slots <= 0:
                continue  # local slot budget spent — but a later async lane may still launch off-box

            agent_rem = state["agent_rem"]
            rem = unbounded_remaining if agent_rem is None else max(0, agent_rem)
            if rem <= 0:
                continue

            cands = state["cands"]
            t = None
            agent = state["agent"]
            while state["index"] < len(cands):
                cand = cands[state["index"]]
                state["index"] += 1
                if cand.id in picked_ids or cand.budget_cost > rem:
                    continue
                if task_id is None and chronic_dispatch_reason(cand):
                    continue
                try:
                    normalize_selected_legacy_task(cand)
                except IntakeContractError as exc:
                    print(f"  INTAKE BLOCKED {cand.id}: {exc}")
                    continue
                blocked, msg = _worktree_admission_for_task(
                    cand,
                    agent,
                    admission_snapshot,
                    reserve=True,
                    machine_lease=machine_lease,
                )
                if blocked:
                    print(f"  Worktree admission blocked {cand.id}: {msg}")
                    continue
                t = cand
                break
            if t is None:
                continue

            picked.append((agent, t.id))
            picked_ids.add(t.id)
            if agent_rem is not None:
                state["agent_rem"] = max(0, agent_rem - t.budget_cost)
            if not dry:
                track.spent += t.budget_cost
                track.per_agent[agent] = track.per_agent.get(agent, 0) + t.budget_cost
                selected_contract_hash = execution_contract_hash(t)
                t.status = "dispatched"
                t.updated = now
                t.dispatch_log.append(
                    DispatchLogEntry(
                        timestamp=now,
                        agent=agent,
                        session_id=_new_async_reservation_id(),
                        status="dispatched",
                        execution_contract_hash=selected_contract_hash,
                        output="dispatch-async: reserved before detached worker launch",
                    )
                )
            if not state["is_async"]:
                slots -= 1  # only local runs consume a local concurrency slot
            state["taken"] += 1
            progressed = True
        if not progressed:
            break
    return picked, reset_changed


def reserve_and_launch(
    agents,
    per_agent,
    cap,
    dry,
    task_id=None,
    *,
    admission_checked: bool = False,
    local_per_agent=None,
    expected_contract_hash: str | None = None,
    reservation_blocker: dict[str, object] | None = None,
):
    """Reserve open tasks (under lock) up to the concurrency cap + per-agent budget, then spawn
    detached workers. Returns the list of (agent, task_id) launched/would-launch."""
    if should_reserve(per_agent, cap) and not admission_checked:
        admission = dispatch_admission_check(TASKS, task_id=task_id, refresh_handoff=not dry)
        if not admission.get("allow", False):
            print_dispatch_admission_block("async", admission)
            return []
    # An explicit task has already passed typed intake and owner selection. Running the broad
    # always-working producer here could enqueue unrelated packets immediately before an exact-one
    # launch, so keep that producer exclusive to generic reservation passes.
    if task_id is None and not run_always_working_before_dispatch(TASKS, dry_run=dry):
        print("── async: always-working gate blocked reservation")
        return []
    now = _now()
    usage = _usage_by_agent()
    usage_remaining = _usage_remaining_by_agent(usage)
    weak_proxy_agents = _weak_proxy_agents(usage)
    reserved_contract_hashes: dict[str, str] = {}
    reserved_ids: dict[str, str] = {}
    if dry:
        lf = load_limen_file(TASKS)
        if task_id and expected_contract_hash:
            blocker = _execution_contract_blocker(lf, task_id, expected_contract_hash)
            if blocker:
                if reservation_blocker is not None:
                    reservation_blocker.update(blocker)
                return []
        picked, _reset_changed = _pick_reservations(
            lf,
            agents,
            per_agent,
            cap,
            dry,
            now,
            usage_remaining,
            weak_proxy_agents,
            task_id=task_id,
            local_per_agent=local_per_agent,
        )
        return picked
    with _queue_lock(TASKS) as got:
        if not got:
            # Lock busy — reserve nothing this round. Returning BEFORE `picked` is used to spawn
            # detached workers (below) prevents launching workers for tasks never persisted as
            # 'dispatched', which would double-dispatch. Self-corrects next beat.
            return []
        # Load and fingerprint under the queue lock.  This is the last read before reservation;
        # a changed predicate/receipt/context/route can never spend budget under the old selection.
        lf = load_limen_file(TASKS)
        if task_id and expected_contract_hash:
            blocker = _execution_contract_blocker(lf, task_id, expected_contract_hash)
            if blocker:
                if reservation_blocker is not None:
                    reservation_blocker.update(blocker)
                return []
        with _machine_admission_lock():
            base_snapshot = _worktree_admission_snapshot()
            live_snapshot, used_slots = _snapshot_with_machine_reservations(dict(base_snapshot))
            if task_id is not None:
                stale_slots, stale_reserved_gib = _nonce_local_marker_reservations(task_id)
                if stale_slots:
                    base_reserved = base_snapshot.get("reserved_gib")
                    snapshot_reserved = live_snapshot.get("reserved_gib")
                    base_room = base_snapshot.get("room_gib")
                    finite_admission_truth = all(
                        isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
                        for value in (base_reserved, snapshot_reserved, base_room)
                    )
                    if finite_admission_truth:
                        promised_gib = max(0.0, float(snapshot_reserved) - float(base_reserved))
                        adjusted_promised_gib = max(0.0, promised_gib - stale_reserved_gib)
                        live_snapshot["reserved_gib"] = float(base_reserved) + adjusted_promised_gib
                        live_snapshot["room_gib"] = max(0.0, float(base_room) - adjusted_promised_gib)
                    used_slots = max(0, used_slots - stale_slots)
            picked, reset_changed = _pick_reservations(
                lf,
                agents,
                per_agent,
                cap,
                dry,
                now,
                usage_remaining,
                weak_proxy_agents,
                task_id=task_id,
                local_per_agent=local_per_agent,
                admission_snapshot=live_snapshot,
                running_local=used_slots,
                machine_lease=True,
            )
            by_id = {task.id: task for task in lf.tasks}
            reserved_contract_hashes = {tid: execution_contract_hash(by_id[tid]) for _agent, tid in picked}
            reserved_ids = {tid: dispatch_session_id(by_id[tid].dispatch_log[-1]) for _agent, tid in picked}
            if not dry and (picked or reset_changed):
                try:
                    apply_limen_file_sync(TASKS, lf, agent="dispatch-async", session_id="reserve")
                except Exception:
                    for agent, tid in picked:
                        if agent in LOCAL_CHECKOUT_AGENTS:
                            _admission_lease_path(tid).unlink(missing_ok=True)
                    raise
    # Outside the board lock: spawn + atomically publish markers (fast; never wait on workers).
    # The machine lease remains authoritative throughout this gap.
    launched = []
    for agent, tid in picked:
        reservation_id = reserved_ids[tid]
        try:
            logf = open(_run_log_path(tid), "a")
            proc = subprocess.Popen(
                [
                    sys.executable,
                    str(WORKER),
                    "--agent",
                    agent,
                    "--task-id",
                    tid,
                    "--reservation-id",
                    reservation_id,
                    "--execution-contract-hash",
                    reserved_contract_hashes[tid],
                ],
                stdout=logf,
                stderr=logf,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env={**os.environ, "PYTHONPATH": str(ROOT / "cli" / "src")},
            )
        except Exception as exc:
            if _rollback_unlaunched_reservation(agent, tid, reservation_id, now, exc):
                _release_machine_admission(tid)
            else:
                _transfer_machine_admission_owner(tid, os.getpid(), "launch-failed-unreconciled")
            print(f"── async: failed to launch {agent} {tid}: {str(exc)[:160]}")
            continue
        try:
            _write_running_marker(
                tid,
                agent,
                now,
                proc.pid,
                _machine_admission_reserved_gib(tid),
                reservation_id,
            )
        except Exception as exc:
            # The child is live but invisible to marker accounting. Transfer the durable lease to
            # that child and keep it fail-closed until the child exits; its result receipt/harvest
            # still reconciles the board.
            _transfer_machine_admission_owner(tid, proc.pid, "worker-live-marker-failed")
            print(f"── async: marker publish failed for live {agent} {tid}: {str(exc)[:160]}")
            launched.append((agent, tid))
        else:
            # Only a successfully durable marker supersedes the selection lease.
            _release_machine_admission(tid)
            launched.append((agent, tid))
    return launched


def should_reserve(per_agent: int, cap: int) -> bool:
    """Whether this invocation may reserve new async work after harvest/reap.

    Closeout and harvest-only probes deliberately call ``--per-lane 0 --max 0``. Those passes must
    not run pre-dispatch writers such as always-working; otherwise a read-mostly harvest check
    dirties the live root without launching anything. ``--max 0`` alone means "no local host slots";
    it must not suppress remote-only lanes such as Jules.
    """
    return per_agent > 0


def resolve_lanes(selector: str, down: set[str]) -> list[str]:
    try:
        board = load_limen_file(TASKS)
        _reset_budget_if_needed(board, _now())
    except Exception:
        board = None
    lanes = select_lanes(selector, board, down_lanes=down)
    if lanes:
        return lanes
    if selector.strip().lower() == "auto":
        return [agent for agent in ("codex",) if agent not in down]
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lanes", default="auto")
    ap.add_argument("--per-lane", type=int, default=max(1, _env_int("LIMEN_LOCAL_LIMIT", 8)))
    ap.add_argument(
        "--local-per-lane",
        type=int,
        default=max(0, _env_int("LIMEN_ASYNC_LOCAL_PER_LANE", _env_int("LIMEN_LOCAL_LIMIT", 8))),
        help="Per-lane launch room for local host lanes; remote lanes use --per-lane.",
    )
    ap.add_argument(
        "--max",
        "--local-max",
        dest="max",
        type=int,
        default=max(0, _env_int("LIMEN_ASYNC_MAX", _default_local_max())),
        help="Local host slot ceiling. Remote lanes such as Jules do not consume it.",
    )
    ap.add_argument("--task-id", help="Reserve and launch only this task id")
    ap.add_argument(
        "--recover-task",
        help="safely reopen only this proven orphaned async claim, then exit",
    )
    ap.add_argument(
        "--execution-contract-hash",
        help="expected canonical execution hash for an exact task",
    )
    ap.add_argument(
        "--reservation-id",
        help="exact async reservation nonce required to recover a nonce-bound claim",
    )
    ap.add_argument(
        "--targeted-only",
        action="store_true",
        help="require --task-id, skip broad reap/harvest, and fail unless exactly that task launches",
    )
    ap.add_argument(
        "--json-output",
        action="store_true",
        help="emit a final counts-only JSON dispatch receipt",
    )
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.recover_task and a.task_id:
        ap.error("--recover-task and --task-id are mutually exclusive")
    if a.recover_task and a.targeted_only:
        ap.error("--recover-task and --targeted-only are mutually exclusive")
    if a.targeted_only and not a.task_id:
        ap.error("--targeted-only requires --task-id")
    if (a.targeted_only or a.recover_task) and not re.fullmatch(r"[0-9a-f]{64}", str(a.execution_contract_hash or "")):
        ap.error("exact dispatch/recovery requires a 64-character --execution-contract-hash")
    if a.reservation_id and not _ASYNC_RESERVATION_RE.fullmatch(str(a.reservation_id)):
        ap.error("--reservation-id must be an async-reserve nonce")
    if a.recover_task:
        recovery = recover_exact_task(
            a.recover_task,
            str(a.execution_contract_hash),
            reservation_id=a.reservation_id,
            dry_run=a.dry_run,
        )
        receipt = {
            "schema_version": "limen-targeted-recovery.v1",
            "task_id": a.recover_task,
            "execution_contract_hash": a.execution_contract_hash,
            "reservation_id": a.reservation_id,
            **recovery,
        }
        if a.json_output:
            print(json.dumps(receipt, sort_keys=True))
        else:
            print(
                f"── async exact recovery: {recovery.get('status')} "
                f"task={a.recover_task} recovered={recovery.get('recovered_count', 0)}"
            )
        return (
            0
            if recovery.get("status")
            in {
                "recovered",
                "would_recover",
                "already_open",
                "already_running",
                "result_pending_harvest",
            }
            else 10
        )
    down = _down_lanes()
    lanes = resolve_lanes(a.lanes, down)
    if down:
        print(f"── skipping down lanes: {sorted(down)}")
    max_age = default_max_age_s()
    if a.targeted_only:
        # The overnight lane switch owns one exact task. Broad recovery/harvest belongs to the
        # heartbeat and could mutate or free unrelated lanes, so this path deliberately does
        # neither. Launch failures still use _rollback_unlaunched_reservation for the exact task.
        reaped = []
        applied = 0
    elif a.dry_run:
        reaped = inspect_stale(max_age)
        applied = inspect_harvest()
    else:
        reaped = reap_stale(max_age)
        applied = harvest()
    running = _running_total()
    reserve_allowed = True
    admission = {"allow": True}
    if should_reserve(a.per_lane, a.max):
        admission = dispatch_admission_check(TASKS, task_id=a.task_id, refresh_handoff=not a.dry_run)
        if not admission.get("allow", False):
            reserve_allowed = False
            print_dispatch_admission_block("async", admission)
    if should_reserve(a.per_lane, a.max) and reserve_allowed:
        reservation_blocker: dict[str, object] = {}
        launched = (
            reserve_and_launch(
                lanes,
                a.per_lane,
                a.max,
                a.dry_run,
                task_id=a.task_id,
                admission_checked=True,
                local_per_agent=a.local_per_lane,
                expected_contract_hash=a.execution_contract_hash,
                reservation_blocker=reservation_blocker,
            )
            if should_reserve(a.per_lane, a.max)
            else []
        )
    else:
        reservation_blocker = {}
        launched = []
    verb = "would launch" if a.dry_run else "launched"
    print(
        f"── async: reaped {len(reaped)} dead · harvested {applied} · {running} still running · "
        f"{verb} {len(launched)} (local cap {a.max}, local per-lane {a.local_per_lane}) → "
        f"{[t for _, t in launched]}"
    )
    exact_launch = len(launched) == 1 and launched[0][1] == a.task_id
    if a.targeted_only and a.task_id and reserve_allowed and not launched and not reservation_blocker:
        # A silent targeted zero-launch is a defect (sensor without a named effector): attribute it.
        reservation_blocker.update(_targeted_zero_launch_blocker(a.task_id, lanes))
    launched_reservation_id = None
    if exact_launch and not a.dry_run and a.task_id:
        try:
            current = next(task for task in load_limen_file(TASKS).tasks if task.id == a.task_id)
            last = current.dispatch_log[-1] if current.dispatch_log else None
            last_reservation_id = dispatch_session_id(last) if last is not None else ""
            if last is not None and _ASYNC_RESERVATION_RE.fullmatch(last_reservation_id):
                launched_reservation_id = last_reservation_id
        except Exception:
            launched_reservation_id = None
    targeted_status = (
        "contract_mismatch"
        if reservation_blocker.get("id") == "targeted-execution-contract-mismatch"
        else (
            ("would_launch" if a.dry_run else "launched")
            if exact_launch
            else ("zero_launch" if not launched else "launch_mismatch")
        )
    )
    if a.json_output:
        print(
            json.dumps(
                {
                    "schema_version": "limen-targeted-dispatch.v1",
                    "targeted_only": bool(a.targeted_only),
                    "task_id": a.task_id,
                    "execution_contract_hash": a.execution_contract_hash,
                    "reservation_id": launched_reservation_id,
                    "lanes": lanes,
                    "admission_allow": bool(admission.get("allow", False)),
                    "reaped_count": len(reaped),
                    "harvested_count": applied,
                    "launched": [[agent, task] for agent, task in launched],
                    "launched_count": len(launched),
                    "status": targeted_status if a.targeted_only else "complete",
                    "blocker": reservation_blocker or None,
                },
                sort_keys=True,
            )
        )
    return 0 if not a.targeted_only or exact_launch else 10


if __name__ == "__main__":
    raise SystemExit(main())
