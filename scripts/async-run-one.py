#!/usr/bin/env python3
"""async-run-one.py — detached worker for the ASYNC dispatch engine.

Runs ONE task's full isolated dispatch (worktree → agent → commit → push → PR) via the SAME
call_agent_dispatch the sync path uses, then writes the raw result to
logs/async-runs/<task-id>.result.json (atomically) and clears its running-marker. It deliberately
does NOT touch tasks.yaml — the orchestrator (dispatch-async.py) harvests result files under the
queue-lock. This is what decouples agent runtime from the beat: the orchestrator spawns these
detached and returns immediately; a slow/stuck agent can no longer gate the whole beat.

Usage (spawned detached by dispatch-async.py; rarely run by hand):
    async-run-one.py --agent codex --task-id CIFIX-foo --reservation-id NONCE --execution-contract-hash SHA256
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.execution_contract import execution_contract_hash  # noqa: E402
from limen.io import load_limen_file  # noqa: E402
from limen.dispatch import _REMOTE_SUBMISSION_RECEIPTS, _queue_lock, call_agent_dispatch  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
TASKS = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
RUNS = ROOT / "logs" / "async-runs"
_SAFE_STEM_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_ASYNC_RESERVATION_RE = re.compile(r"^async-reserve:[0-9a-f]{32}$")


def _run_stem(task_id: str) -> str:
    if _SAFE_STEM_RE.fullmatch(task_id):
        return task_id
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", task_id).strip("._-") or "task"
    digest = hashlib.sha1(task_id.encode("utf-8")).hexdigest()[:12]
    return f"{slug[:80]}--{digest}"


def _reservation_suffix(reservation_id: str) -> str:
    return hashlib.sha256(reservation_id.encode("utf-8")).hexdigest()[:16]


def _result_path(task_id: str, reservation_id: str = "async-reserve") -> Path:
    suffix = "" if reservation_id == "async-reserve" else f"--{_reservation_suffix(reservation_id)}"
    return RUNS / f"{_run_stem(task_id)}{suffix}.result.json"


def _running_marker_path(task_id: str, agent: str, reservation_id: str = "async-reserve") -> Path:
    suffix = "" if reservation_id == "async-reserve" else f"--{_reservation_suffix(reservation_id)}"
    return RUNS / f"{_run_stem(task_id)}__{agent}{suffix}.running"


def _contract_hash(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise argparse.ArgumentTypeError("execution contract hash must be 64 lowercase hexadecimal characters")
    return value


def _reservation_id(value: str) -> str:
    if value != "async-reserve" and not _ASYNC_RESERVATION_RE.fullmatch(value):
        raise argparse.ArgumentTypeError("reservation ID must be async-reserve plus 32 lowercase hex characters")
    return value


def _failure(blocker_id: str, reason: str, **evidence: object) -> dict[str, object]:
    return {"id": blocker_id, "reason": reason[:500], **evidence}


def _load_verified_task(
    task_id: str,
    agent: str,
    reservation_id: str,
    expected_hash: str,
) -> tuple[object | None, str | bool, dict[str, object] | None, str]:
    """Load one immutable execution snapshot under the queue lock.

    The returned task object is the exact snapshot passed to dispatch. Later
    board rewrites therefore cannot change the prompt after this verification.
    """

    with _queue_lock(TASKS) as got:
        if not got:
            return (
                None,
                "__notask__",
                _failure("async-execution-queue-lock-busy", "task queue lock was unavailable before execution"),
                "",
            )
        board = load_limen_file(TASKS)
        task = next((candidate for candidate in board.tasks if candidate.id == task_id), None)
        if task is None:
            return (
                None,
                "__notask__",
                _failure("async-execution-task-missing", "reserved task disappeared before execution"),
                "",
            )
        try:
            actual_hash = execution_contract_hash(task)
        except Exception as exc:
            return (
                task,
                False,
                _failure(
                    "async-execution-contract-invalid",
                    f"fresh task cannot be canonically fingerprinted: {exc}",
                ),
                "",
            )
        if task.status != "dispatched":
            return (
                task,
                "__notask__",
                _failure(
                    "async-execution-status-unsafe",
                    f"fresh task status is {task.status}; expected dispatched",
                    actual_status=task.status,
                ),
                actual_hash,
            )
        last = task.dispatch_log[-1] if task.dispatch_log else None
        if last is None or last.session_id != reservation_id or last.status != "dispatched" or last.agent != agent:
            return (
                task,
                False,
                _failure(
                    "async-execution-claim-owner-mismatch",
                    "fresh task is not owned by this async reservation",
                ),
                actual_hash,
            )
        if actual_hash != expected_hash:
            return (
                task,
                False,
                _failure(
                    "async-execution-contract-mismatch",
                    "task execution contract changed after reservation",
                    expected_hash=expected_hash,
                    actual_hash=actual_hash,
                ),
                actual_hash,
            )
        return task, False, None, actual_hash


def _publish_result(
    out: dict[str, object],
    *,
    task_id: str,
    agent: str,
    reservation_id: str,
    expected_hash: str,
    execution_started: bool,
) -> bool:
    """Publish under the same queue lock used by recovery.

    If exact recovery won the lock and reopened the task, fence the late result
    instead of applying it to a new claim. The counts-only receipt remains
    durable for diagnosis, but harvest will not mutate the reopened row.
    """

    with _queue_lock(TASKS) as got:
        if not got:
            return False
        board_error = None
        try:
            board = load_limen_file(TASKS)
            current = next((candidate for candidate in board.tasks if candidate.id == task_id), None)
        except Exception as exc:
            current = None
            current_hash = ""
            board_error = _failure(
                "async-result-board-unreadable",
                f"fresh board could not be verified before result publication: {exc}",
            )
        else:
            try:
                current_hash = execution_contract_hash(current) if current is not None else ""
            except Exception:
                current_hash = ""

        last = current.dispatch_log[-1] if current is not None and current.dispatch_log else None
        publication_safe = bool(
            board_error is None
            and current is not None
            and current.status == "dispatched"
            and current_hash == expected_hash
            and last is not None
            and last.session_id == reservation_id
            and last.status == "dispatched"
            and last.agent == agent
        )
        if not publication_safe:
            out["result"] = "__notask__"
            out["publication_failure"] = board_error or _failure(
                "async-result-publication-fenced",
                "task changed or was recovered before the worker could publish its result",
                expected_hash=expected_hash,
                actual_hash=current_hash,
                actual_status=getattr(current, "status", None),
            )
        elif not execution_started:
            # Validation failures are diagnostic receipts, never task outcomes.
            out["result"] = "__notask__"

        RUNS.mkdir(parents=True, exist_ok=True)
        tmp = _result_path(task_id, reservation_id).with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(out))
        tmp.replace(_result_path(task_id, reservation_id))  # atomic publish while recovery is excluded
        try:
            _running_marker_path(task_id, agent, reservation_id).unlink()
        except OSError:
            pass
        return True


def heal_outcome(task, result):
    """Mechanically derive a heal receipt's outcome — never trust agent prose.

    The gap (retro 06-24→07-08 finding 2): 59% of heal receipts produced no PR
    and nothing distinguished "already green" from "gave up silently", so heal
    convergence could be neither asserted nor falsified. For HEAL-* tasks this
    probes the TARGET PR's post-run state via gh and returns
    {outcome: already_green|fixed|gave_up, failing_checks: [...]}.
    Fail-open: any probe error returns None (receipt ships without the field,
    counted by heal-convergence.py as legacy/uncovered).
    """
    import re
    import subprocess

    blob = f"{task.context or ''} {' '.join(str(u) for u in (task.urls or []))}"
    m = re.search(r"github\.com/([^/\s]+/[^/\s]+)/pull/(\d+)", blob)
    if not m:
        return None
    repo, num = m.group(1), m.group(2)
    try:
        v = subprocess.run(
            ["gh", "pr", "view", num, "-R", repo, "--json", "statusCheckRollup,mergeable"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if v.returncode != 0:
            return None
        data = json.loads(v.stdout or "{}") or {}
        rollup = data.get("statusCheckRollup") or []
        failing = sorted(
            {
                c.get("name", "?")
                for c in rollup
                if (c.get("conclusion") or "").upper() in ("FAILURE", "TIMED_OUT", "CANCELLED")
            }
        )
        green = not failing and str(data.get("mergeable", "")).upper() != "CONFLICTING"
        if green:
            outcome = "already_green" if result in ("__noop__", False, None) else "fixed"
        else:
            outcome = "gave_up"
        return {"outcome": outcome, "failing_checks": failing}
    except Exception:  # noqa: BLE001 — outcome derivation must never sink the worker
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True)
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--reservation-id", default="async-reserve", type=_reservation_id)
    ap.add_argument("--execution-contract-hash", required=True, type=_contract_hash)
    a = ap.parse_args()
    err = None
    task = None
    execution_started = False
    actual_hash = ""
    validation_failure = None
    try:
        task, result, validation_failure, actual_hash = _load_verified_task(
            a.task_id,
            a.agent,
            a.reservation_id,
            a.execution_contract_hash,
        )
        if validation_failure is None and task is not None:
            execution_started = True
            result = call_agent_dispatch(a.agent, task, dry_run=False)
    except Exception as e:  # never crash without leaving a result the harvester can apply
        result = False
        err = str(e)[:300]
    out = {
        "task_id": a.task_id,
        "agent": a.agent,
        "reservation_id": a.reservation_id,
        "result": result,  # bool | str (PR url / __noop__ / __ratelimit__ / __timeout__)
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "err": err,
        "execution_contract_hash": a.execution_contract_hash,
        "actual_execution_contract_hash": actual_hash,
        "execution_started": execution_started,
        "remote_submission": dict(_REMOTE_SUBMISSION_RECEIPTS.get(a.task_id, {})),
    }
    if validation_failure is not None:
        out["validation_failure"] = validation_failure
    if execution_started and task is not None and a.task_id.startswith("HEAL-"):
        derived = heal_outcome(task, result)
        if derived:
            out.update(derived)
    published = _publish_result(
        out,
        task_id=a.task_id,
        agent=a.agent,
        reservation_id=a.reservation_id,
        expected_hash=a.execution_contract_hash,
        execution_started=execution_started,
    )
    if not published:
        print("async worker could not acquire the queue lock for result publication", file=sys.stderr)
        return 2
    return 0 if validation_failure is None else 10


if __name__ == "__main__":
    raise SystemExit(main())
