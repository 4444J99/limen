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

Usage: dispatch-async.py --lanes auto --per-lane 8 --local-per-lane 3 [--local-max N] [--task-id TASK] [--dry-run]
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.capacity import LOCAL_CHECKOUT_AGENTS, _weak_proxy_exhaustion, select_lanes  # noqa: E402
from limen.intake import IntakeContractError, normalize_selected_legacy_task  # noqa: E402
from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.models import DispatchLogEntry  # noqa: E402
from limen.dispatch import (  # noqa: E402
    _apply_result,
    _deps_met,
    _dispatchable,
    _down_lanes,
    _has_done_transition,
    _queue_lock,
    _reset_budget_if_needed,
    _restore_done_status,
    _restore_pr_open_status,
    _routine_generated_buildout_allowed,
    _admission_lease_path,
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
WORKER = ROOT / "scripts" / "async-run-one.py"
_TOKEN_RE = re.compile(r"(github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{12,})")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_SAFE_STEM_RE = re.compile(r"^[A-Za-z0-9._-]+$")


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


def _result_path(task_id: str) -> Path:
    return RUNS / f"{_run_stem(task_id)}.result.json"


def _running_marker_path(task_id: str, agent: str) -> Path:
    return RUNS / f"{_run_stem(task_id)}__{agent}.running"


def _write_running_marker(
    task_id: str,
    agent: str,
    now: datetime.datetime,
    pid: int,
    reserved_gib: float,
) -> None:
    """Publish the marker atomically so slot readers never observe a partial JSON document."""
    marker = _running_marker_path(task_id, agent)
    tmp = marker.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(
        json.dumps(
            {
                "started_at": now.isoformat(),
                "agent": agent,
                "task_id": task_id,
                "pid": pid,
                "reserved_gib": reserved_gib,
            }
        )
    )
    os.replace(tmp, marker)


def _rollback_unlaunched_reservation(agent: str, task_id: str, now: datetime.datetime, error: Exception) -> bool:
    """Reopen/refund an async reservation when no worker process was created."""
    with _queue_lock(TASKS) as got:
        if not got:
            return False
        lf = load_limen_file(TASKS)
        task = next((candidate for candidate in lf.tasks if candidate.id == task_id), None)
        if task is None or task.status != "dispatched":
            return True
        last = task.dispatch_log[-1] if task.dispatch_log else None
        if last is None or last.session_id != "async-reserve" or last.agent != agent:
            return True
        task.status = "open"
        task.updated = now
        task.dispatch_log.append(
            DispatchLogEntry(
                timestamp=now,
                agent=agent,
                session_id="async-launch-failed",
                status="open",
                output=f"dispatch-async: detached worker did not launch; reservation reopened ({str(error)[:160]})",
            )
        )
        cost = max(0, int(task.budget_cost or 0))
        track = lf.portal.budget.track
        track.spent = max(0, track.spent - cost)
        track.per_agent[agent] = max(0, track.per_agent.get(agent, 0) - cost)
        save_limen_file(TASKS, lf)
        return True


def _marker_task_agent(marker: Path) -> tuple[str, str]:
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        task_id = str(data.get("task_id") or "")
        agent = str(data.get("agent") or "")
        if task_id and agent:
            return task_id, agent
    except (OSError, ValueError):
        pass
    return marker.name[: -len(".running")].rsplit("__", 1)


def _result_task_id(result_file: Path) -> str:
    try:
        data = json.loads(result_file.read_text(encoding="utf-8"))
        task_id = str(data.get("task_id") or "")
        if task_id:
            return task_id
    except (OSError, ValueError):
        pass
    return result_file.name[: -len(".result.json")]


def _clear_running_markers(task_id: str) -> None:
    prefix = f"{task_id}__"
    for marker in RUNS.glob("*.running"):
        try:
            marker_task_id, _agent = _marker_task_agent(marker)
        except ValueError:
            marker_task_id = ""
        if marker_task_id == task_id or marker.name.startswith(prefix):
            marker.unlink(missing_ok=True)


def _running_marker_info(marker: Path) -> dict[str, object]:
    raw = marker.read_text().strip()
    try:
        data = json.loads(raw)
        started = datetime.datetime.fromisoformat(str(data.get("started_at") or ""))
        pid = data.get("pid")
        return {"started_at": started, "pid": int(pid) if pid is not None else None}
    except Exception:
        return {"started_at": datetime.datetime.fromisoformat(raw), "pid": None}


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
            t = byid.get(data.get("task_id"))
            if t is not None and data.get("result") != "__notask__":
                _apply_result(t, data.get("agent"), data.get("result"), now, track, charge_budget=False)
                applied += 1
            if data.get("task_id"):
                _clear_running_markers(str(data.get("task_id")))
            _archive_result_receipt(rf, raw, now, parsed=data, reason="harvested")
            rf.unlink(missing_ok=True)
        if applied:
            save_limen_file(TASKS, lf)
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
    marker_task_ids = set()
    result_task_ids = {_result_task_id(rf) for rf in RUNS.glob("*.result.json")}
    for m in RUNS.glob("*__*.running"):
        tid, agent = _marker_task_agent(m)
        marker_task_ids.add(tid)
        try:
            info = _running_marker_info(m)
            age = (now - info["started_at"]).total_seconds()  # type: ignore[operator]
        except Exception:
            age = max_age_s + 1  # unreadable/empty marker → treat as stale
            info = {"pid": None}
        pid = info.get("pid")
        dead_pid = isinstance(pid, int) and not _pid_alive(pid)
        zombie_stuck = isinstance(pid, int) and age > defunct_grace_s and _worker_has_defunct_child(pid)
        if age > max_age_s:
            # if the worker DID finish (result file present), let harvest handle it; don't reap
            if not _result_path(tid).exists():
                # Defer the marker unlink until the reopen is committed under the lock (below), so a
                # lock timeout can't leave the slot leaked (marker gone, task still 'dispatched').
                reaped.append((tid, agent, m, pid if isinstance(pid, int) else None))
        elif dead_pid or zombie_stuck:
            if not _result_path(tid).exists():
                reaped.append((tid, agent, m, pid if isinstance(pid, int) else None))
    markerless = []
    try:
        lf_preview = load_limen_file(TASKS)
        for t in lf_preview.tasks:
            if t.status != "dispatched" or t.id in marker_task_ids or t.id in result_task_ids:
                continue
            if not t.dispatch_log:
                continue
            last = t.dispatch_log[-1]
            if last.session_id != "async-reserve" or last.status != "dispatched":
                continue
            stamp = t.updated or last.timestamp
            if stamp and (now - stamp).total_seconds() > max_age_s:
                markerless.append((t.id, last.agent or t.target_agent))
    except Exception:
        markerless = []
    applied_markerless = []
    if reaped or markerless:
        for _tid, _agent, _m, pid in reaped:
            _kill_worker_group(pid)
        with _queue_lock(TASKS) as got:
            if not got:
                # Lock busy — keep the markers (not yet unlinked) so a later beat retries the reap;
                # unlinking without reopening would leak the concurrency slot forever.
                return []
            lf = load_limen_file(TASKS)
            byid = {t.id: t for t in lf.tasks}
            changed = False
            for tid, agent, _m, _pid in reaped:
                t = byid.get(tid)
                if t is not None and t.status == "dispatched":
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
                        t.status = "open"  # dead worker left no result → retry on a later beat
                        t.updated = now
                        t.dispatch_log.append(
                            DispatchLogEntry(
                                timestamp=now,
                                agent=agent,
                                session_id="async-reap-stale",
                                status="open",
                                output=f"dispatch-async: stale worker marker older than {max_age_s}s reaped; task reopened",
                            )
                        )
                        changed = True
            if markerless:
                fresh_marker_task_ids = {_marker_task_agent(m)[0] for m in RUNS.glob("*__*.running")}
                fresh_result_task_ids = {_result_task_id(rf) for rf in RUNS.glob("*.result.json")}
                for tid, agent in markerless:
                    t = byid.get(tid)
                    if (
                        t is None
                        or t.status != "dispatched"
                        or tid in fresh_marker_task_ids
                        or tid in fresh_result_task_ids
                        or not t.dispatch_log
                    ):
                        continue
                    last = t.dispatch_log[-1]
                    stamp = t.updated or last.timestamp
                    if (
                        last.session_id != "async-reserve"
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
                        t.status = "open"
                        t.updated = now
                        t.dispatch_log.append(
                            DispatchLogEntry(
                                timestamp=now,
                                agent=agent,
                                session_id="async-reap-stale",
                                status="open",
                                output=(
                                    f"dispatch-async: markerless async reservation older than {max_age_s}s "
                                    "reaped; task reopened"
                                ),
                            )
                        )
                        applied_markerless.append(tid)
                        changed = True
            if changed:
                save_limen_file(TASKS, lf)
        # reopen is committed → now safe to remove the markers that freed these slots
        for _tid, _agent, m, _pid in reaped:
            m.unlink(missing_ok=True)
    return [tid for tid, _agent, _m, _pid in reaped] + applied_markerless


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
        if age > max_age_s:
            tid, _agent = _marker_task_agent(m)
            if not _result_path(tid).exists():
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


def _running_local() -> int:
    """In-flight LOCAL-lane runs only. The concurrency cap bounds LOCAL host pressure (each local run
    holds a worktree + a ThreadPoolExecutor slot). An async/remote run (jules, github_actions, ...)
    executes OFF-BOX — a `jules remote new` session runs on Google's VM — so it must NOT consume a
    local slot, or a backlog of local work starves the remote lanes out of the cap entirely (the root
    cause of 'zero jules remote sessions launched'). Remote lanes stay bounded by their per-agent
    budget, not this local cap."""
    total = 0
    for m in RUNS.glob("*__*.running"):
        _task_id, agent = _marker_task_agent(m)
        if agent in LOCAL_CHECKOUT_AGENTS:  # census local_checkout authority, not a hand-kept lane set
            total += 1
    return total


def _running_for(agent: str) -> int:
    return sum(1 for marker in RUNS.glob("*__*.running") if _marker_task_agent(marker)[1] == agent)


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
    reset_changed = _reset_budget_if_needed(lf, now)
    track = lf.portal.budget.track
    unbounded_remaining = _effectively_unbounded_remaining(lf)
    value_repos = _value_tier_repos()
    disk_pressure = _disk_pressure_active()
    # Worktree admission is ALWAYS evaluated — an explicit --task does NOT bypass resource/VITALS/
    # reaper custody (a task-id run still creates a local worktree). The only override is the
    # documented LIMEN_WORKTREE_DEBT_GATE=0 lever (snapshot → inactive → gate returns False).
    admission_snapshot = admission_snapshot or _worktree_admission_snapshot()
    if admission_snapshot.get("reason") and not dry:
        print(f"── async: {admission_snapshot['reason']}")
    # The cap counts only LOCAL in-flight runs; remote/async lanes run off-box and are budgeted
    # separately below (see _running_local).
    slots = max(0, cap - (_running_local() if running_local is None else running_local))
    id2 = {t.id: t for t in lf.tasks}  # for dependency resolution
    states = []
    for agent in agents:
        # Locality is the census authority (LOCAL_CHECKOUT_AGENTS); a non-local lane runs off-box.
        is_async = agent not in LOCAL_CHECKOUT_AGENTS  # remote lane — off-box, not gated by the local cap
        running_for_agent = _running_for(agent)
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
            and (t.target_agent == agent or t.target_agent == "any")
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
                t.status = "dispatched"
                t.updated = now
                t.dispatch_log.append(
                    DispatchLogEntry(
                        timestamp=now,
                        agent=agent,
                        session_id="async-reserve",
                        status="dispatched",
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
):
    """Reserve open tasks (under lock) up to the concurrency cap + per-agent budget, then spawn
    detached workers. Returns the list of (agent, task_id) launched/would-launch."""
    if should_reserve(per_agent, cap) and not admission_checked:
        admission = dispatch_admission_check(TASKS, task_id=task_id)
        if not admission.get("allow", False):
            print_dispatch_admission_block("async", admission)
            return []
    if not run_always_working_before_dispatch(TASKS, dry_run=dry):
        print("── async: always-working gate blocked reservation")
        return []
    now = _now()
    usage = _usage_by_agent()
    usage_remaining = _usage_remaining_by_agent(usage)
    weak_proxy_agents = _weak_proxy_agents(usage)
    if dry:
        lf = load_limen_file(TASKS)
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
        with _machine_admission_lock():
            lf = load_limen_file(TASKS)
            live_snapshot, used_slots = _snapshot_with_machine_reservations()
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
            if not dry and (picked or reset_changed):
                try:
                    save_limen_file(TASKS, lf)
                except Exception:
                    for agent, tid in picked:
                        if agent in LOCAL_CHECKOUT_AGENTS:
                            _admission_lease_path(tid).unlink(missing_ok=True)
                    raise
    # Outside the board lock: spawn + atomically publish markers (fast; never wait on workers).
    # The machine lease remains authoritative throughout this gap.
    launched = []
    for agent, tid in picked:
        try:
            logf = open(_run_log_path(tid), "a")
            proc = subprocess.Popen(
                [sys.executable, str(WORKER), "--agent", agent, "--task-id", tid],
                stdout=logf,
                stderr=logf,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env={**os.environ, "PYTHONPATH": str(ROOT / "cli" / "src")},
            )
        except Exception as exc:
            if _rollback_unlaunched_reservation(agent, tid, now, exc):
                _release_machine_admission(tid)
            else:
                _transfer_machine_admission_owner(tid, os.getpid(), "launch-failed-unreconciled")
            print(f"── async: failed to launch {agent} {tid}: {str(exc)[:160]}")
            continue
        try:
            _write_running_marker(tid, agent, now, proc.pid, _machine_admission_reserved_gib(tid))
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
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    down = _down_lanes()
    lanes = resolve_lanes(a.lanes, down)
    if down:
        print(f"── skipping down lanes: {sorted(down)}")
    max_age = default_max_age_s()
    if a.dry_run:
        reaped = inspect_stale(max_age)
        applied = inspect_harvest()
    else:
        reaped = reap_stale(max_age)
        applied = harvest()
    running = _running_total()
    reserve_allowed = True
    admission = {"allow": True}
    if should_reserve(a.per_lane, a.max):
        admission = dispatch_admission_check(TASKS, task_id=a.task_id)
        if not admission.get("allow", False):
            reserve_allowed = False
            print_dispatch_admission_block("async", admission)
    if should_reserve(a.per_lane, a.max) and reserve_allowed:
        launched = (
            reserve_and_launch(
                lanes,
                a.per_lane,
                a.max,
                a.dry_run,
                task_id=a.task_id,
                admission_checked=True,
                local_per_agent=a.local_per_lane,
            )
            if should_reserve(a.per_lane, a.max)
            else []
        )
    else:
        launched = []
    verb = "would launch" if a.dry_run else "launched"
    print(
        f"── async: reaped {len(reaped)} dead · harvested {applied} · {running} still running · "
        f"{verb} {len(launched)} (local cap {a.max}, local per-lane {a.local_per_lane}) → "
        f"{[t for _, t in launched]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
