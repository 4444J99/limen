#!/usr/bin/env python3
"""Low-cost overnight heartbeat progress monitor.

This is the cheap receipt writer that should replace interactive-agent-attached
"watch all night" polling. Each default invocation is one-shot: inspect the live
heartbeat, write compact receipts, update a stale-tick counter, and exit
non-zero only when there is a concrete WATCH_ALERT. launchd/cron can run it
every few minutes without replaying any agent conversation.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import fcntl
import hashlib
import json
import os
import pwd
import re
import shlex
import shutil
import signal
import stat
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT / "cli" / "src"))

from limen.capacity import LOCAL_CHECKOUT_AGENTS, canonical_agent  # noqa: E402
from limen.conduct.client import HttpConductClient, client_from_env  # noqa: E402
from limen.conduct.task_execution import (  # noqa: E402
    TaskExecutionError,
    start_task_execution,
)
from limen.dispatch import agent_can_run_task  # noqa: E402
from limen.execution_contract import execution_contract_hash, execution_contract_payload  # noqa: E402
from limen.intake import validate_intake_contract  # noqa: E402
from limen.io import load_limen_file  # noqa: E402
from limen.private_board import operational_board_path  # noqa: E402
from limen.models import Task, dispatch_session_id  # noqa: E402
from limen.tabularius import (  # noqa: E402
    INTENT_UPSERT,
    Ticket,
    drain_once,
    fetch_canonical_task_projection,
    new_ticket_id,
    pending_upsert_patches,
    submit_task_upsert,
    submit_ticket,
    task_state_sha256,
)
from limen.worktree_debt import take_admission_snapshot  # noqa: E402


ROOT = Path(os.environ.get("LIMEN_ROOT") or SOURCE_ROOT).expanduser().resolve()
LOGS = ROOT / "logs"
PAUSE_MARKER = LOGS / "AUTONOMY_PAUSED"
TASKS_PATH = ROOT / "tasks.yaml"
PRIVATE_SESSION_CORPUS = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PROMPT_ATOM_SNAPSHOT = PRIVATE_SESSION_CORPUS / "prompt-atoms" / "prompt-atom-ledger.json"
HEARTBEAT_LOG = LOGS / "heartbeat.out.log"
FAST_WAVE_PID_PATH = LOGS / "vigilia" / "fast-wave.pid"
HOST_PRESSURE_WATCHDOG_PID_PATH = LOGS / "vigilia" / "host-pressure-watchdog.pid"
HOST_PRESSURE_STALE_SCRIPT = ROOT / "scripts" / "host-pressure-stale.py"
ASYNC_RUNS = LOGS / "async-runs"
STATE_PATH = Path(os.environ.get("LIMEN_OVERNIGHT_WATCH_STATE", LOGS / "overnight-watch-state.json"))
RECEIPT_JSONL = Path(os.environ.get("LIMEN_OVERNIGHT_WATCH_RECEIPT", LOGS / "overnight-watch.jsonl"))
RECEIPT_MD = LOGS / "overnight-watch.md"
ALERT_PATH = Path(os.environ.get("LIMEN_OVERNIGHT_WATCH_ALERT", LOGS / "overnight-watch-alert.json"))
TRIAL_PATH = Path(os.environ.get("LIMEN_OVERNIGHT_TRIAL_RECEIPT", LOGS / "overnight-trial.json"))
TRIAL_WINDOW_PATH = Path(os.environ.get("LIMEN_OVERNIGHT_TRIAL_WINDOW", LOGS / "overnight-trial-window.json"))
TRIAL_OBSERVATION_PATH = Path(
    os.environ.get("LIMEN_OVERNIGHT_TRIAL_OBSERVATIONS", LOGS / "overnight-trial-observations.jsonl")
)
TOKEN_REPORT = Path(os.environ.get("LIMEN_CODEX_TOKEN_REPORT", LOGS / "codex-token-report.json"))
HANDOFF_SCRIPT = ROOT / "scripts" / "handoff-relay.py"
SESSION_VALUE_SCRIPT = ROOT / "scripts" / "session-value-review.py"
ALWAYS_WORKING_SCRIPT = Path(os.environ.get("LIMEN_ALWAYS_WORKING_SCRIPT", ROOT / "scripts" / "always-working.py"))
TABULARIUS_SCRIPT = ROOT / "scripts" / "tabularius-organ.py"
DISPATCH_ASYNC_SCRIPT = ROOT / "scripts" / "dispatch-async.py"
USAGE_PATH = Path(os.environ.get("LIMEN_USAGE_JSON", LOGS / "usage.json"))
LANE_SWITCH_LOCK = Path(os.environ.get("LIMEN_OVERNIGHT_LANE_SWITCH_LOCK", LOGS / "overnight-lane-switch.lock"))
_ASYNC_RESERVATION_RE = re.compile(r"^async-reserve:[0-9a-f]{32}$")
LABEL = os.environ.get("LIMEN_HEARTBEAT_LABEL", os.environ.get("LIMEN_LAUNCHD_LABEL", "com.limen.heartbeat"))
WATCHDOG_LABEL = os.environ.get("LIMEN_WATCHDOG_LABEL", "com.limen.watchdog")
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"


def _positive_env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)) or str(default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


# The heartbeat writes its tick at the end of a beat. Its longest healthy silence is therefore
# the idle backoff plus bounded dispatch work plus reconciliation overhead. Keep this derivation
# aligned with watchdog.py and heartbeat-loop.sh; a shorter independent literal guarantees false
# alerts whenever the healthy idle cadence exceeds the monitor threshold.
_HEARTBEAT_MAX_BEAT_SEC = _positive_env_int("LIMEN_LOOP_MAX", 1800)
_HEARTBEAT_CAMPAIGN_WAKE_SEC = _positive_env_int("LIMEN_CAMPAIGN_WAKE_TIMEOUT", 300) + 30
_HEARTBEAT_OVERHEAD_SEC = _positive_env_int("LIMEN_WATCHDOG_OVERHEAD_SEC", 600)
_HEARTBEAT_MAX_INTER_TICK_SEC = _HEARTBEAT_MAX_BEAT_SEC + _HEARTBEAT_CAMPAIGN_WAKE_SEC + _HEARTBEAT_OVERHEAD_SEC
MAX_LOG_AGE_SEC = _positive_env_int("LIMEN_OVERNIGHT_WATCH_MAX_LOG_AGE_SEC", _HEARTBEAT_MAX_INTER_TICK_SEC)
MAX_STALE_TICKS = int(os.environ.get("LIMEN_OVERNIGHT_WATCH_MAX_STALE_TICKS", "6") or "6")
HEAL_ENABLED = (os.environ.get("LIMEN_OVERNIGHT_WATCH_HEAL", "1") or "1") != "0"
HEAL_COOLDOWN_SEC = int(os.environ.get("LIMEN_OVERNIGHT_WATCH_HEAL_COOLDOWN_SEC", "1200") or "1200")

# Throughput floor (2026-07-08 incident: the fleet idled a full night at ~5% of baseline while
# every liveness alert stayed green — liveness is not velocity). The floor is DERIVED from the
# trailing per-window completion history, never pinned.
TICKS_PATH = LOGS / "ticks.jsonl"
COMMITTED_PLIST = ROOT / "container" / "launchd" / f"{LABEL}.plist"
THROUGHPUT_WINDOW_MIN = int(os.environ.get("LIMEN_THROUGHPUT_WINDOW_MIN", "60") or "60")
THROUGHPUT_WINDOWS = int(os.environ.get("LIMEN_THROUGHPUT_WINDOWS", "3") or "3")
THROUGHPUT_FLOOR_FRACTION = float(os.environ.get("LIMEN_THROUGHPUT_FLOOR_FRACTION", "0.25") or "0.25")
THROUGHPUT_BASELINE_DAYS = int(os.environ.get("LIMEN_THROUGHPUT_BASELINE_DAYS", "7") or "7")
ISSUE_ESCALATE = (os.environ.get("LIMEN_THROUGHPUT_ISSUE_ESCALATE", "1") or "1") != "0"
ESCALATE_REPO = os.environ.get("LIMEN_CENSOR_ISSUES_REPO", "organvm/limen")
PLIST_DRIFT_KEYS = ("LIMEN_CAMPAIGN_WAKE_TIMEOUT", "LIMEN_ROOT", "LIMEN_VIGILIA")
TAIL_BYTES = 192 * 1024
TRIAL_SCHEMA_VERSION = "overnight-trial.v2"
TRIAL_MARKER_SCHEMA_VERSION = "overnight-trial-window.v2"
TRIAL_OBSERVATION_SCHEMA_VERSION = "overnight-trial-observation.v2"
TRIAL_OBSERVATION_CUSTODY_SCHEMA_VERSION = "overnight-observation-custody.v1"
TRIAL_TERMINAL_CUSTODY_SCHEMA_VERSION = "overnight-terminal-custody.v1"
TRIAL_TASK_EVENT_SCHEMA_VERSION = "overnight-task-events.v2"
TRIAL_PROMPT_AUTHORITY_SCHEMA_VERSION = "overnight-prompt-authority.v2"
TRIAL_DURATION_SEC = 8 * 60 * 60
TRIAL_VALUE_WINDOW_SEC = 90 * 60
TRIAL_EDGE_TOLERANCE_SEC = 10 * 60
TRIAL_MAX_SAMPLE_GAP_SEC = 10 * 60
TRIAL_PROMPT_MAX_AGE_SEC = 10 * 60
TRIAL_PREDICATE_TIMEOUT_SEC = 120
TRIAL_CLOCK_TOLERANCE_SEC = 60

EXPECT_CAMPAIGN_WAKE_TIMEOUT = os.environ.get("LIMEN_OVERNIGHT_WATCH_EXPECT_CAMPAIGN_WAKE_TIMEOUT", "")
try:
    VALUE_GATE_HOURS = float(os.environ.get("LIMEN_OVERNIGHT_VALUE_GATE_HOURS", "1.5") or "1.5")
except ValueError:
    VALUE_GATE_HOURS = 1.5
try:
    LANE_SWITCH_PROVIDER_MAX_AGE_MIN = float(os.environ.get("LIMEN_OVERNIGHT_PROVIDER_MAX_AGE_MIN", "90") or "90")
except ValueError:
    LANE_SWITCH_PROVIDER_MAX_AGE_MIN = 90.0

LANE_SWITCH_OPEN_STATUSES = frozenset({"assigned_from_existing_work", "needs_assignment"})
LANE_SWITCH_ACTIVE_TASK_STATUSES = frozenset({"open", "dispatched", "in_progress"})
LANE_SWITCH_GOOD_STATUSES = frozenset(
    {"would_submit", "would_launch", "launched", "already_running", "result_pending_harvest"}
)
LANE_SWITCH_EXECUTION_PROGRESS_STATUSES = frozenset({"launched", "already_running", "result_pending_harvest"})
LANE_SWITCH_BAD_PROVIDER_HEALTH = frozenset(
    {"blocked", "disabled", "down", "exhausted", "low", "rate_limited", "unavailable"}
)

TICK_RE = re.compile(
    r"tick emitted:\s*(?P<ts>\S+).*?\btotal=(?P<total>\d+)\s+open=(?P<open>\d+)\s+spent=(?P<spent>\S+)"
)
BEAT_RE = re.compile(r"^\s*(?P<line>.*beat\s+\d+.*)$", re.MULTILINE)
DISPATCH_LANES_RE = re.compile(r"dispatch lanes:\s*(?P<lanes>.+)")
ASYNC_RE = re.compile(
    r"async:\s*reaped\s+(?P<reaped>\d+)\s+dead\s+.\s+"
    r"harvested\s+(?P<harvested>\d+)\s+.\s+"
    r"(?P<running>\d+)\s+still running\s+.\s+"
    r"(?P<verb>would launch|launched)\s+(?P<launched>\d+)"
)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def run(
    args: list[str],
    timeout: int = 10,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        kwargs: dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "timeout": timeout,
        }
        if env is not None:
            kwargs["env"] = env
        return subprocess.run(args, **kwargs)
    except Exception as exc:
        return subprocess.CompletedProcess(args, 1, "", str(exc))


def autonomy_pause_active() -> bool:
    """Return whether the repo-local autonomy pause must stop watch work.

    ``LIMEN_FORCE_AUTONOMY=1`` is the existing governor/dispatch escape hatch.  The
    watcher deliberately does not invent a second override.  An unreadable marker
    path fails closed; a broken marker symlink is still a marker.
    """

    if os.environ.get("LIMEN_FORCE_AUTONOMY") == "1":
        return False
    try:
        PAUSE_MARKER.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def tail_text(path: Path, nbytes: int = TAIL_BYTES) -> str:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > nbytes:
                handle.seek(size - nbytes)
            return handle.read().decode("utf-8", "replace")
    except OSError:
        return ""


def log_age(path: Path) -> int | None:
    try:
        return max(0, int(time.time() - path.stat().st_mtime))
    except OSError:
        return None


def latest_match(regex: re.Pattern[str], text: str) -> re.Match[str] | None:
    match = None
    for match in regex.finditer(text):
        pass
    return match


def parse_heartbeat(text: str) -> dict[str, Any]:
    tick = latest_match(TICK_RE, text)
    beat = latest_match(BEAT_RE, text)
    lanes = latest_match(DISPATCH_LANES_RE, text)
    async_match = latest_match(ASYNC_RE, text)

    tick_payload: dict[str, Any] | None = None
    if tick:
        tick_ts = tick.group("ts")
        parsed = parse_iso(tick_ts)
        tick_payload = {
            "raw": tick.group(0).strip(),
            "timestamp": tick_ts,
            "age_sec": int((utc_now() - parsed).total_seconds()) if parsed else None,
            "total": int(tick.group("total")),
            "open": int(tick.group("open")),
            "spent": tick.group("spent"),
        }

    async_payload: dict[str, Any] | None = None
    if async_match:
        async_payload = {
            "raw": async_match.group(0).strip(),
            "reaped": int(async_match.group("reaped")),
            "harvested": int(async_match.group("harvested")),
            "still_running": int(async_match.group("running")),
            "verb": async_match.group("verb"),
            "launched": int(async_match.group("launched")),
        }

    return {
        "latest_beat": beat.group("line").strip() if beat else None,
        "latest_tick": tick_payload,
        "latest_dispatch_lanes": lanes.group("lanes").strip() if lanes else None,
        "latest_async": async_payload,
    }


def parse_launchd_env(stdout: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in stdout.splitlines():
        match = re.match(r"\s*([A-Z][A-Z0-9_]+)\s*=>\s*(.+?)\s*$", line)
        if not match:
            continue
        env[match.group(1)] = match.group(2).strip().strip('"')
    return env


def launchd_snapshot() -> dict[str, Any]:
    proc = run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"])
    stdout = proc.stdout or ""
    state = None
    pid = None
    last_exit = None
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("state ="):
            state = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("pid ="):
            pid = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("last exit code ="):
            last_exit = stripped.split("=", 1)[1].strip()
    return {
        "label": LABEL,
        "ok": proc.returncode == 0,
        "state": state,
        "pid": pid,
        "last_exit_code": last_exit,
        "env": parse_launchd_env(stdout),
        "error": (proc.stderr or "").strip() if proc.returncode else "",
    }


def active_workers() -> list[dict[str, Any]]:
    workers: list[dict[str, Any]] = []
    if not ASYNC_RUNS.exists():
        return workers
    now = time.time()
    for path in sorted(ASYNC_RUNS.glob("*.running")):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        workers.append(
            {
                "name": path.name.removesuffix(".running"),
                "path": str(path),
                "age_sec": int(max(0, now - mtime)),
            }
        )
    return workers


def heartbeat_child_processes(pid: str | None) -> list[dict[str, Any]]:
    if not pid:
        return []
    pgrep = run(["pgrep", "-P", str(pid)], timeout=5)
    if pgrep.returncode != 0:
        return []
    children: list[dict[str, Any]] = []
    for child_pid in [line.strip() for line in pgrep.stdout.splitlines() if line.strip()]:
        ps = run(["ps", "-o", "pid=,ppid=,stat=,etime=,command=", "-p", child_pid], timeout=5)
        line = (ps.stdout or "").strip()
        if ps.returncode != 0 or not line:
            children.append({"pid": child_pid})
            continue
        parts = line.split(None, 4)
        children.append(
            {
                "pid": parts[0] if len(parts) > 0 else child_pid,
                "ppid": parts[1] if len(parts) > 1 else None,
                "stat": parts[2] if len(parts) > 2 else None,
                "etime": parts[3] if len(parts) > 3 else None,
                "command": parts[4] if len(parts) > 4 else "",
            }
        )
    return children


def _resident_pid(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value if value.isdigit() else None


def resident_fast_wave_pid() -> str | None:
    return _resident_pid(FAST_WAVE_PID_PATH)


def resident_host_pressure_watchdog_pid() -> str | None:
    return _resident_pid(HOST_PRESSURE_WATCHDOG_PID_PATH)


def _resident_alive(pid: str | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        return False
    return True


def _resident_state(pid: str | None, child: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "pid": pid,
        "alive": _resident_alive(pid),
        "process": child,
    }


def host_pressure_snapshot(
    *,
    read_only: bool = False,
    effective_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not HOST_PRESSURE_STALE_SCRIPT.is_file():
        return {"ok": None, "returncode": None, "detail": "host-pressure-stale.py missing"}
    command = [sys.executable, str(HOST_PRESSURE_STALE_SCRIPT)]
    if read_only:
        command.append("--read-only")
    probe_env = None
    if effective_env:
        probe_env = os.environ.copy()
        for key in (
            "LIMEN_ENV_FILE",
            "LIMEN_HOST_PRESSURE_STALE",
            "LIMEN_VIGILIA",
            "LIMEN_VITALS_SAMPLE_SECONDS",
            "LIMEN_VITALS_STALE_BEATS",
        ):
            if key in effective_env:
                probe_env[key] = effective_env[key]
    if probe_env is None:
        completed = run(command, timeout=30)
    else:
        completed = run(command, timeout=30, env=probe_env)
    detail = ((completed.stdout or "") + (completed.stderr or "")).strip()
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "detail": detail[-500:],
    }


def load_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _evaluator_dependency_paths() -> dict[str, Path]:
    repository = Path(__file__).resolve().parents[1]
    return {
        "cli/src/limen/intake.py": repository / "cli" / "src" / "limen" / "intake.py",
        "cli/src/limen/jules_remote.py": repository / "cli" / "src" / "limen" / "jules_remote.py",
        "cli/src/limen/prompt_corpus.py": repository / "cli" / "src" / "limen" / "prompt_corpus.py",
        "scripts/autonomy-governor.py": repository / "scripts" / "autonomy-governor.py",
        "scripts/handoff-relay.py": repository / "scripts" / "handoff-relay.py",
        "scripts/overnight-watch.py": Path(__file__).resolve(),
        "scripts/session-value-review.py": repository / "scripts" / "session-value-review.py",
    }


def evaluator_hash() -> str:
    dependencies: dict[str, dict[str, Any]] = {}
    for name, path in sorted(_evaluator_dependency_paths().items()):
        try:
            payload = path.read_bytes()
        except OSError:
            return "unavailable"
        dependencies[name] = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
        }
    return canonical_hash({"schema_version": "overnight-evaluator.v1", "dependencies": dependencies})


def token_snapshot() -> dict[str, Any]:
    report = load_json(TOKEN_REPORT)
    if not report:
        return {"present": False}
    totals = report.get("aggregate_totals") if isinstance(report.get("aggregate_totals"), dict) else {}
    return {
        "present": True,
        "status": report.get("status"),
        "generated_at": report.get("generated_at"),
        "session_count": report.get("session_count"),
        "budget_tokens": totals.get("budget_tokens"),
        "uncached_input_tokens": totals.get("uncached_input_tokens"),
        "failures": report.get("failures") if isinstance(report.get("failures"), list) else [],
    }


def short_output(proc: subprocess.CompletedProcess[str], limit: int = 500) -> str:
    text = (proc.stdout or proc.stderr or "").strip()
    if len(text) > limit:
        return f"{text[:limit]}...[truncated]"
    return text


def parse_json_stdout(stdout: str) -> dict[str, Any]:
    try:
        payload = json.loads(stdout or "{}")
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def handoff_relay_snapshot(*, refresh: bool) -> dict[str, Any]:
    refresh_proc: subprocess.CompletedProcess[str] | None = None
    if refresh:
        refresh_proc = run([sys.executable, str(HANDOFF_SCRIPT)], timeout=20)
    check_proc = run([sys.executable, str(HANDOFF_SCRIPT), "--check"], timeout=20)
    return {
        "refreshed": bool(refresh),
        "refresh_returncode": refresh_proc.returncode if refresh_proc else None,
        "refresh_output": short_output(refresh_proc) if refresh_proc else "",
        "check_returncode": check_proc.returncode,
        "check_output": short_output(check_proc),
        "ok": check_proc.returncode == 0,
    }


def session_value_gate_snapshot(*, record_gate: bool) -> dict[str, Any]:
    args = [
        sys.executable,
        str(SESSION_VALUE_SCRIPT),
        "--gate",
        "--hours",
        str(VALUE_GATE_HOURS),
    ]
    if not record_gate:
        args.append("--no-record-gate")
    proc = run(args, timeout=90)
    gate = parse_json_stdout(proc.stdout)
    return {
        "returncode": proc.returncode,
        "output": short_output(proc),
        "gate": gate,
        "action": gate.get("action"),
        "exit_code": gate.get("exit_code", proc.returncode),
        "next_commands": gate.get("next_commands") if isinstance(gate.get("next_commands"), list) else [],
    }


def first_next_command(value_gate: dict[str, Any]) -> str:
    commands = value_gate.get("next_commands") if isinstance(value_gate.get("next_commands"), list) else []
    return str(commands[0]) if commands else ""


def always_working_snapshot() -> dict[str, Any]:
    """Read the counts/receipt-derived owner-packet surface without writing it.

    ``always-working.py --json`` reads reconciled owner receipts and private counts-only
    lifecycle indexes; it does not read or return raw prompt bodies.  Keeping this as a
    subprocess also prevents its comparatively broad estate discovery imports from becoming
    part of the watcher's cheap normal path when the value gate is green.
    """

    proc = run([sys.executable, str(ALWAYS_WORKING_SCRIPT), "--json"], timeout=120)
    payload = parse_json_stdout(proc.stdout)
    items = payload.get("items") if isinstance(payload.get("items"), list) else None
    return {
        "returncode": proc.returncode,
        "output": short_output(proc),
        "snapshot": payload if items is not None else {},
    }


def _owner_task_id(item: dict[str, Any], packet: dict[str, Any], target_agent: str) -> str:
    """Stable per-contract task id, so one unresolved receipt cannot ticket-storm.

    Historical ``AW-<item>`` tasks may already be terminal while the current receipt proves the
    condition is open again.  The contract fingerprint creates the new task required by the task
    lifecycle protocol without reopening the terminal row.  The same live contract always maps to
    the same id, making repeated watch beats idempotent.
    """

    stable = {
        "item_id": item.get("id"),
        "workstream": item.get("workstream"),
        "target_agent": target_agent,
        "repo": packet.get("repo"),
        "execution_scope": packet.get("execution_scope"),
        "packet_epoch": packet.get("packet_epoch"),
        "task": packet.get("task"),
        "predicate": packet.get("predicate"),
        "receipt_target": packet.get("receipt_target"),
        "stop_condition": packet.get("stop_condition"),
    }
    digest = hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    raw = re.sub(r"[^A-Za-z0-9._/-]+", "-", str(item.get("id") or "owner-packet")).strip("-")
    max_base = 128 - len("AW--") - len(digest)
    return f"AW-{raw[:max_base]}-{digest}"


def _priority_name(value: Any) -> str:
    try:
        priority = int(value)
    except (TypeError, ValueError):
        priority = 100
    if priority <= 20:
        return "critical"
    if priority <= 50:
        return "high"
    return "medium"


def _priority_order(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 100


def owner_task_from_item(item: dict[str, Any]) -> Task:
    """Compile one always-working row into a fail-fast, predicate-shaped owner task."""

    packet = item.get("assignment_packet")
    if not isinstance(packet, dict):
        raise ValueError("assignment packet is missing")
    target_agent = canonical_agent(str(item.get("target_agent") or packet.get("target_agent") or ""))
    repo = str(packet.get("repo") or "").strip()
    if not target_agent or target_agent == "any":
        raise ValueError("owner packet requires one concrete target agent")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("owner packet requires one exact owner/repo")
    workstream = str(item.get("workstream") or "always-working")
    context = "\n".join(
        [
            f"Receipt-first verdict: {item.get('verdict') or ''}",
            f"Execution scope: {packet.get('execution_scope') or 'repository'}",
            f"Packet epoch: {packet.get('packet_epoch') or 'static'}",
            f"Task: {packet.get('task') or item.get('title') or ''}",
            f"Predicate: {packet.get('predicate') or ''}",
            f"Receipt target: {packet.get('receipt_target') or ''}",
            f"Stop condition: {packet.get('stop_condition') or ''}",
            "This is the single bounded alternate selected after generic dispatch was value-gated.",
        ]
    )
    labels = ["always-working", "receipt-first", "overnight-lane-switch", workstream]
    if packet.get("execution_scope") == "control-host":
        labels.append("execution:control-host")
    task = Task.model_validate(
        {
            "id": _owner_task_id(item, packet, target_agent),
            "title": str(item.get("title") or item.get("id") or "Always-working owner packet"),
            "description": str(item.get("verdict") or ""),
            "repo": repo,
            "type": "coordination",
            "target_agent": target_agent,
            "workstream": workstream,
            "priority": _priority_name(item.get("priority")),
            "budget_cost": 1,
            "status": "open",
            "origin": "human_prompt",
            "horizon": "present",
            "value_case": f"Close the selected always-working owner packet {item.get('id') or item.get('title') or ''}",
            "labels": labels,
            "context": context,
            "predicate": str(packet.get("predicate") or ""),
            "receipt_target": str(packet.get("receipt_target") or ""),
            "created": utc_now().date().isoformat(),
        }
    )
    validate_intake_contract(task, is_new=True)
    return task


def _packet_summary(task: Task) -> dict[str, str]:
    return {
        "task_id": task.id,
        "execution_contract_hash": execution_contract_hash(task),
        "target_agent": task.target_agent,
        "workstream": str(task.workstream or ""),
        "repo": str(task.repo or ""),
        "predicate": str(task.predicate or ""),
        "receipt_target": str(task.receipt_target or ""),
    }


def _named_lane_blocker(
    blocker_id: str,
    reason: str,
    *,
    owner: str = "organvm/limen",
    failed_predicate: str = "python3 scripts/always-working.py --json",
    next_command: str = "python3 scripts/always-working.py --write",
) -> dict[str, str]:
    return {
        "id": blocker_id,
        "owner": owner,
        "reason": reason[:500],
        "failed_predicate": failed_predicate,
        "next_command": next_command,
    }


def _usage_snapshot() -> tuple[dict[str, Any], str]:
    try:
        payload = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, "provider usage receipt is missing or malformed"
    if not isinstance(payload, dict) or not isinstance(payload.get("vendors"), dict):
        return {}, "provider usage receipt has no vendor map"
    generated = parse_iso(str(payload.get("generated") or payload.get("generated_at") or ""))
    if generated is None:
        return {}, "provider usage receipt has no parseable generation time"
    age_min = (utc_now() - generated).total_seconds() / 60
    if age_min < -5 or age_min > LANE_SWITCH_PROVIDER_MAX_AGE_MIN:
        return {}, (
            f"provider usage receipt is not fresh ({age_min:.1f}m; limit {LANE_SWITCH_PROVIDER_MAX_AGE_MIN:g}m)"
        )
    return payload, ""


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not (number == number and abs(number) != float("inf")):
        return None
    return number


def _provider_gate(agent: str, usage: dict[str, Any]) -> tuple[bool, str]:
    vendors = usage.get("vendors") if isinstance(usage.get("vendors"), dict) else {}
    info = vendors.get(agent) if isinstance(vendors, dict) else None
    if not isinstance(info, dict):
        return False, f"provider {agent} has no current capacity receipt"
    health = str(info.get("health") or info.get("state") or info.get("status") or "").strip().lower()
    health = health.replace("-", "_")
    weak_agy_proxy = bool(
        agent == "agy"
        and str(info.get("signal") or "") in {"dispatch-count", "count", "runs"}
        and "operator board cap" in str(info.get("limit_source") or "")
        and not info.get("recent_rate_limit")
        and health != "rate_limited"
    )
    if health in LANE_SWITCH_BAD_PROVIDER_HEALTH and not weak_agy_proxy:
        return False, f"provider {agent} is measured {health or 'unavailable'}"
    remaining = _finite_number(info.get("remaining"))
    headroom = _finite_number(info.get("headroom_pct"))
    reserve = _finite_number(info.get("effective_reserve_pct"))
    if remaining is not None and remaining <= 0 and not weak_agy_proxy:
        return False, f"provider {agent} has no measured remaining capacity"
    if headroom is not None and headroom <= 0 and not weak_agy_proxy:
        return False, f"provider {agent} has no measured headroom"
    if headroom is not None and reserve is not None and headroom <= reserve and not weak_agy_proxy:
        return False, f"provider {agent} headroom does not clear its live reserve"
    if remaining is None and headroom is None and not weak_agy_proxy:
        return False, f"provider {agent} capacity is unknown"
    return True, ""


def _local_admission_gate(agent: str, admission: dict[str, Any]) -> tuple[bool, str, str]:
    if canonical_agent(agent) not in LOCAL_CHECKOUT_AGENTS:
        return True, "", "remote"
    if admission.get("resource_blocked") or admission.get("vitals_shed"):
        return False, str(admission.get("reason") or "local resource gate is closed"), "resource"
    if admission.get("reaper_blocked") or admission.get("block_new_local"):
        return False, str(admission.get("reason") or "local lifecycle gate is closed"), "lifecycle"
    return True, "", "local"


def _owned_task_state(task: Task, board: Any, pending_ids: set[str]) -> str | None:
    if task.id in pending_ids:
        return "pending"
    for current in getattr(board, "tasks", []) or []:
        if current.id == task.id:
            return str(current.status)
    return None


def _targeted_dispatch_argv(task: Task) -> list[str]:
    return [
        sys.executable,
        str(DISPATCH_ASYNC_SCRIPT),
        "--lanes",
        task.target_agent,
        "--per-lane",
        "1",
        "--local-per-lane",
        "1",
        "--max",
        "1",
        "--task-id",
        task.id,
        "--execution-contract-hash",
        execution_contract_hash(task),
        "--targeted-only",
        "--json-output",
    ]


def _exact_task_command(task: Task) -> str:
    relative = [
        "python3",
        "scripts/dispatch-async.py",
        "--lanes",
        task.target_agent,
        "--per-lane",
        "1",
        "--local-per-lane",
        "1",
        "--max",
        "1",
        "--task-id",
        task.id,
        "--execution-contract-hash",
        execution_contract_hash(task),
        "--targeted-only",
        "--json-output",
    ]
    return "PYTHONPATH=cli/src " + shlex.join(relative)


def _targeted_recovery_command(task: Task, reservation_id: str | None = None) -> str:
    relative = [
        "python3",
        "scripts/dispatch-async.py",
        "--recover-task",
        task.id,
        *(
            ["--reservation-id", reservation_id]
            if reservation_id and _ASYNC_RESERVATION_RE.fullmatch(reservation_id)
            else []
        ),
        "--execution-contract-hash",
        execution_contract_hash(task),
        "--json-output",
    ]
    return "PYTHONPATH=cli/src " + shlex.join(relative)


def _current_async_reservation_id(task_id: str) -> str | None:
    try:
        board = load_limen_file(operational_board_path(TASKS_PATH))
    except Exception:
        return None
    current = next((task for task in board.tasks if task.id == task_id), None)
    last = current.dispatch_log[-1] if current is not None and current.dispatch_log else None
    reservation_id = dispatch_session_id(last) if last is not None else ""
    if (
        current is None
        or current.status != "dispatched"
        or last is None
        or last.status != "dispatched"
        or (reservation_id != "async-reserve" and not _ASYNC_RESERVATION_RE.fullmatch(reservation_id))
    ):
        return None
    return reservation_id


def _artifact_matches_reservation(artifact_reservation_id: object, current_reservation_id: str) -> bool:
    if current_reservation_id == "async-reserve":
        # Pre-nonce receipts omitted this field; workers produced during the
        # migration may write the explicit legacy value.
        return artifact_reservation_id in {None, "async-reserve"}
    return artifact_reservation_id == current_reservation_id


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _async_task_state(task_id: str) -> dict[str, Any] | None:
    """Return only durable exact-task async state; never infer from a lossy filename alone."""

    current_reservation_id = _current_async_reservation_id(task_id)
    if current_reservation_id is None:
        # Filesystem residue has no authority when the board has no current
        # async owner.  In particular, recovered reservation A must not suppress
        # a new launch B while the task is open.
        return None
    for result_path in sorted(ASYNC_RUNS.glob("*.result.json")):
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if str(payload.get("task_id") or "") != task_id:
            continue
        artifact_reservation_id = payload.get("reservation_id")
        if not _artifact_matches_reservation(artifact_reservation_id, current_reservation_id):
            continue
        return {
            "status": "result_pending_harvest",
            "receipt": result_path.name,
            "reservation_id": artifact_reservation_id if isinstance(artifact_reservation_id, str) else None,
        }
    for marker_path in sorted(ASYNC_RUNS.glob("*.running")):
        try:
            payload = json.loads(marker_path.read_text(encoding="utf-8"))
            marker_task_id = str(payload.get("task_id") or "")
            pid = int(payload.get("pid"))
        except (OSError, TypeError, ValueError):
            continue
        if marker_task_id != task_id:
            continue
        artifact_reservation_id = payload.get("reservation_id")
        if not _artifact_matches_reservation(artifact_reservation_id, current_reservation_id):
            continue
        return {
            "status": "already_running" if _pid_alive(pid) else "orphaned_claim",
            "receipt": marker_path.name,
            "pid": pid,
            "reservation_id": artifact_reservation_id if isinstance(artifact_reservation_id, str) else None,
        }
    return None


def _targeted_dispatch_receipt(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if isinstance(payload, dict) and payload.get("schema_version") == "limen-targeted-dispatch.v1":
            return payload
    return {}


def _active_owner_outcome(task: Task, owner_state: str) -> dict[str, Any]:
    async_state = _async_task_state(task.id)
    if async_state and async_state.get("status") in {"already_running", "result_pending_harvest"}:
        return {**async_state, "owner_state": owner_state}
    receipt = async_state.get("receipt") if async_state else ""
    reservation_id = (
        async_state.get("reservation_id")
        if async_state and isinstance(async_state.get("reservation_id"), str)
        else _current_async_reservation_id(task.id)
    )
    return {
        "status": "blocked",
        "owner_state": owner_state,
        "blocker": _named_lane_blocker(
            "overnight-owner-claim-orphaned",
            (
                f"exact owner packet {task.id} is {owner_state} without a live worker or result receipt"
                + (f" ({receipt})" if receipt else "")
            ),
            owner=str(task.repo or "organvm/limen"),
            failed_predicate=str(task.predicate or ""),
            next_command=(
                _targeted_recovery_command(task, reservation_id)
                if owner_state == "dispatched"
                else str(task.predicate or "python3 scripts/always-working.py --json")
            ),
        ),
    }


# Execution-contract fields the keeper may safely realign on an open owner-packet task whose
# board row drifted from the freshly-compiled always-working packet.  Lifecycle fields
# (status/created/updated/dispatch_log) are never touched here; a live (dispatched/in_progress)
# task is never realigned — only an ``open`` packet the watch itself owns.
_OWNER_CONTRACT_RECONCILE_FIELDS = (
    "target_agent",
    "execution_requirements",
    "predicate",
    "receipt_target",
    "priority",
    "workstream",
    "repo",
    "type",
    "labels",
    "context",
    "budget_cost",
    "urls",
    "claude_tier",
    "depends_on",
)


def _owner_contract_reconcile_ticket(task: Task) -> dict[str, Any]:
    """Self-heal one wedged owner packet: realign the drifted board row to the compiled packet.

    The overnight lane re-selects the highest-priority owner packet every beat.  If the board row
    for that packet id acquired a different execution contract from another writer (e.g. a mount
    requirement, or a target-agent flip from a failed run + heal), every beat recomputes the packet
    contract, the dispatcher re-reads the drifted board row, the hashes disagree, and the lane
    wedges forever on ``targeted-execution-contract-mismatch``.  The always-working packet is
    authoritative for an ``AW-*`` owner packet, so submit exactly one keeper upsert ticket that
    folds the packet's execution-owned fields back onto the board row, guarded by a ``task_sha256``
    precondition so a concurrent daemon write is never clobbered.  The keeper (single writer) lands
    it next drain and the following beat re-selects with matching contracts.  A ``dispatched`` or
    ``in_progress`` row is deliberately left alone — realigning a claimed contract is unsafe.
    """

    try:
        board = load_limen_file(operational_board_path(TASKS_PATH))
    except Exception as exc:
        return {"status": "unavailable", "reason": f"board unreadable: {exc}"[:300]}
    current = next((row for row in board.tasks if row.id == task.id), None)
    if current is None:
        return {"status": "absent", "reason": "board row disappeared before reconcile"}
    if current.status != "open":
        return {
            "status": "unsafe",
            "reason": f"board row is {current.status}; only an open owner packet is realigned",
        }
    if execution_contract_hash(current) == execution_contract_hash(task):
        return {"status": "already_aligned", "reason": "board row already matches the packet"}
    packet_payload = execution_contract_payload(task)
    board_payload = execution_contract_payload(current)
    patch = {
        field: packet_payload[field]
        for field in _OWNER_CONTRACT_RECONCILE_FIELDS
        if field in packet_payload and packet_payload[field] != board_payload.get(field)
    }
    if not patch:
        return {"status": "no_delta", "reason": "no execution-owned field drift to realign"}
    fields = current.model_dump(mode="json", exclude_none=True)
    ticket = Ticket(
        ticket_id=new_ticket_id("overnight-owner-contract-reconcile"),
        timestamp=utc_now(),
        agent=os.environ.get("LIMEN_AGENT", "github_actions"),
        session_id="overnight-owner-contract-reconcile",
        intent=INTENT_UPSERT,
        task_id=task.id,
        patch=patch,
        precondition={"status": "open", "task_sha256": task_state_sha256(fields)},
    )
    try:
        path = submit_ticket(TASKS_PATH, ticket)
    except Exception as exc:
        return {"status": "submit_failed", "reason": str(exc)[:300]}
    return {"status": "reconcile_submitted", "ticket_name": path.name, "fields": sorted(patch)}


def _drain_and_dispatch_one_owner_task(
    task: Task,
    owner_state: str,
    canonical_task: Task | None = None,
) -> dict[str, Any]:
    """Drain/launch one exact packet, or return a named fail-closed blocker."""

    try:
        conduct_client = client_from_env()
    except Exception as exc:
        return {
            "status": "blocked",
            "blocker": _named_lane_blocker(
                "overnight-owner-conduct-unavailable",
                f"authenticated conduct is unavailable for exact owner packet {task.id}: {exc}",
                owner=str(task.repo or "organvm/limen"),
                failed_predicate=str(task.predicate or ""),
                next_command="PYTHONPATH=cli/src limen conduct capabilities",
            ),
        }
    remote_conduct = isinstance(conduct_client, HttpConductClient)
    if not remote_conduct:
        existing_async = _async_task_state(task.id)
        if existing_async:
            if existing_async.get("status") in {"already_running", "result_pending_harvest"}:
                return {**existing_async, "owner_state": owner_state, "targeted_launch_count": 0}
            return _active_owner_outcome(task, owner_state)
        if owner_state in {"dispatched", "in_progress"}:
            return _active_owner_outcome(task, owner_state)

    if owner_state == "pending":
        if remote_conduct:
            try:
                keeper_result = drain_once(TASKS_PATH)
            except Exception as exc:
                keeper_result = None
                keeper_error = str(exc)
            else:
                keeper_error = keeper_result.note
            if (
                keeper_result is None
                or keeper_result.deferred
                or keeper_result.rejected
                or task.id not in keeper_result.projected_tasks
            ):
                return {
                    "status": "blocked",
                    "blocker": _named_lane_blocker(
                        "overnight-owner-ticket-drain-failed",
                        (f"TABVLARIVS returned no canonical receipt for exact owner packet {task.id}: {keeper_error}"),
                        owner=str(task.repo or "organvm/limen"),
                        failed_predicate="python3 scripts/check-tabularius.py",
                        next_command="PYTHONPATH=cli/src python3 scripts/tabularius-organ.py",
                    ),
                }
            try:
                canonical_task = Task.model_validate(keeper_result.projected_tasks[task.id])
            except ValueError as exc:
                return {
                    "status": "blocked",
                    "blocker": _named_lane_blocker(
                        "overnight-owner-canonical-task-invalid",
                        f"keeper receipt for exact owner packet {task.id} is invalid: {exc}",
                        owner=str(task.repo or "organvm/limen"),
                        failed_predicate="python3 scripts/validate-task-board.py --tasks tasks.yaml",
                        next_command="PYTHONPATH=cli/src python3 scripts/tabularius-organ.py",
                    ),
                }
        else:
            keeper = run([sys.executable, str(TABULARIUS_SCRIPT)], timeout=120)
            if keeper.returncode != 0:
                return {
                    "status": "blocked",
                    "blocker": _named_lane_blocker(
                        "overnight-owner-ticket-drain-failed",
                        f"TABVLARIVS could not drain exact owner packet {task.id} (exit {keeper.returncode})",
                        owner=str(task.repo or "organvm/limen"),
                        failed_predicate="python3 scripts/check-tabularius.py",
                        next_command="PYTHONPATH=cli/src python3 scripts/tabularius-organ.py",
                    ),
                }

    if remote_conduct:
        if canonical_task is None:
            return {
                "status": "blocked",
                "blocker": _named_lane_blocker(
                    "overnight-owner-canonical-receipt-missing",
                    f"exact owner packet {task.id} has no fresh canonical remote task receipt",
                    owner=str(task.repo or "organvm/limen"),
                    failed_predicate="python3 scripts/check-tabularius.py",
                    next_command="PYTHONPATH=cli/src python3 scripts/tabularius-organ.py",
                ),
            }
        if canonical_task.id != task.id or execution_contract_hash(canonical_task) != execution_contract_hash(task):
            return {
                "status": "blocked",
                "blocker": _named_lane_blocker(
                    "overnight-owner-canonical-contract-mismatch",
                    f"canonical remote task receipt for {task.id} changed its execution contract",
                    owner=str(task.repo or "organvm/limen"),
                    failed_predicate=str(task.predicate or ""),
                    next_command="PYTHONPATH=cli/src python3 scripts/overnight-watch.py --dry-run --json",
                ),
            }
        current_state = canonical_task.status
    else:
        try:
            board = load_limen_file(operational_board_path(TASKS_PATH))
            pending_ids = {
                str(patch.get("id"))
                for patch in pending_upsert_patches(TASKS_PATH)
                if isinstance(patch, dict) and patch.get("id")
            }
            current_state = _owned_task_state(task, board, pending_ids)
        except Exception:
            current_state = None
    if current_state == "pending" or current_state is None:
        return {
            "status": "blocked",
            "owner_state": current_state,
            "blocker": _named_lane_blocker(
                "overnight-owner-ticket-not-drained",
                f"exact owner packet {task.id} did not become an open board task after its keeper pass",
                owner=str(task.repo or "organvm/limen"),
                failed_predicate="python3 scripts/check-tabularius.py",
                next_command="PYTHONPATH=cli/src python3 scripts/tabularius-organ.py",
            ),
        }
    if remote_conduct and current_state in {"open", "dispatched", "in_progress"}:
        try:
            execution = start_task_execution(canonical_task, client=conduct_client)
        except TaskExecutionError as exc:
            return {
                "status": "blocked",
                "owner_state": current_state,
                "targeted_launch_count": 0,
                "blocker": _named_lane_blocker(
                    "overnight-owner-conduct-reservation-failed",
                    str(exc),
                    owner=str(task.repo or "organvm/limen"),
                    failed_predicate=str(task.predicate or ""),
                    next_command="PYTHONPATH=cli/src python3 scripts/overnight-watch.py --json",
                ),
            }
        return {
            **execution,
            "execution_mode": "conduct",
            "owner_state": "dispatched" if execution.get("status") != "result_pending_harvest" else current_state,
            "next_command": "PYTHONPATH=cli/src python3 scripts/overnight-watch.py --dry-run --json",
        }
    if current_state in {"dispatched", "in_progress"}:
        return _active_owner_outcome(task, current_state)
    if current_state != "open":
        return {
            "status": "blocked",
            "owner_state": current_state,
            "blocker": _named_lane_blocker(
                "overnight-owner-packet-terminal",
                f"exact owner packet {task.id} became terminal ({current_state}) before launch",
                owner=str(task.repo or "organvm/limen"),
                failed_predicate=str(task.predicate or ""),
                next_command=str(task.receipt_target or ""),
            ),
        }

    dispatched = run(_targeted_dispatch_argv(task), timeout=120)
    receipt = _targeted_dispatch_receipt(dispatched.stdout)
    exact_launch = receipt.get("launched") == [[task.target_agent, task.id]]
    post_state = _async_task_state(task.id)
    if (
        dispatched.returncode == 0
        and exact_launch
        and post_state
        and post_state.get("status")
        in {
            "already_running",
            "result_pending_harvest",
        }
    ):
        return {
            "status": "launched",
            "owner_state": "dispatched",
            "async_state": post_state.get("status"),
            "receipt": post_state.get("receipt"),
            "targeted_launch_count": 1,
        }
    # A durable task-specific marker/result outranks a lost subprocess response: the worker really
    # did launch, so preserve idempotence instead of launching it again.
    if post_state and post_state.get("status") in {"already_running", "result_pending_harvest"}:
        return {
            "status": "launched",
            "owner_state": "dispatched",
            "async_state": post_state.get("status"),
            "receipt": post_state.get("receipt"),
            "targeted_launch_count": 1,
        }
    dispatch_blocker = receipt.get("blocker") if isinstance(receipt.get("blocker"), dict) else {}
    if dispatch_blocker.get("id") == "targeted-execution-contract-mismatch":
        # Sensor-with-effector: the drift between the compiled owner packet and its (open) board row
        # is deterministic, so a bare blocker would re-wedge the lane every beat.  Realign the row to
        # the authoritative packet through the keeper's single-writer ticket lane; the next beat then
        # re-selects with matching contracts.  Only fall through to the fail-closed blocker when the
        # self-heal cannot safely apply (row now claimed, disappeared, or the keeper rejected it).
        reconcile = _owner_contract_reconcile_ticket(task)
        if reconcile.get("status") == "reconcile_submitted":
            return {
                "status": "reconciled",
                "owner_state": current_state,
                "targeted_launch_count": 0,
                "reconcile": reconcile,
            }
        return {
            "status": "blocked",
            "owner_state": current_state,
            "targeted_launch_count": 0,
            "reconcile": reconcile,
            "blocker": _named_lane_blocker(
                "overnight-owner-execution-contract-mismatch",
                str(dispatch_blocker.get("reason") or "selected owner execution contract changed before reserve"),
                owner=str(task.repo or "organvm/limen"),
                failed_predicate=str(task.predicate or ""),
                next_command="PYTHONPATH=cli/src python3 scripts/overnight-watch.py --dry-run --json",
            ),
        }
    launched_count = int(receipt.get("launched_count") or 0) if receipt else 0
    named_refusal = (
        f"; dispatcher blocker {dispatch_blocker.get('id')}: {str(dispatch_blocker.get('reason') or '')[:200]}"
        if dispatch_blocker.get("id")
        else ""
    )
    return {
        "status": "blocked",
        "owner_state": current_state,
        "targeted_launch_count": launched_count,
        "blocker": _named_lane_blocker(
            "overnight-owner-targeted-zero-launch",
            (
                f"exact owner packet {task.id} produced no durable targeted launch "
                f"(exit {dispatched.returncode}, launched {launched_count}){named_refusal}"
            ),
            owner=str(task.repo or "organvm/limen"),
            failed_predicate=str(task.predicate or ""),
            next_command=_exact_task_command(task),
        ),
    }


def _submit_one_owner_task(task: Task) -> dict[str, Any]:
    """Recheck ownership under a short machine lock, then append at most one ticket."""

    LANE_SWITCH_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LANE_SWITCH_LOCK.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        board = load_limen_file(operational_board_path(TASKS_PATH))
        pending_ids = {
            str(patch.get("id"))
            for patch in pending_upsert_patches(TASKS_PATH)
            if isinstance(patch, dict) and patch.get("id")
        }
        state = _owned_task_state(task, board, pending_ids)
        if state == "pending" or state in LANE_SWITCH_ACTIVE_TASK_STATUSES:
            return {"status": "already_owned", "ticket_submitted": False, "owner_state": state}
        if state:
            return {
                "status": "blocked",
                "ticket_submitted": False,
                "blocker": _named_lane_blocker(
                    "overnight-owner-packet-terminal",
                    f"exact owner packet {task.id} is terminal ({state}) while its receipt remains unresolved",
                    owner=str(task.repo or "organvm/limen"),
                    failed_predicate=str(task.predicate or ""),
                    next_command=str(task.receipt_target or ""),
                ),
            }
        path = submit_task_upsert(
            TASKS_PATH,
            task,
            agent=os.environ.get("LIMEN_AGENT", "github_actions"),
            session_id="overnight-lane-switch",
        )
        return {
            "status": "submitted",
            "ticket_submitted": True,
            "ticket_name": path.name,
        }


def lane_switch_snapshot(snapshot: dict[str, Any], *, submit: bool) -> dict[str, Any]:
    """Choose exactly one bounded alternate while generic fan-out stays closed."""

    value_gate = snapshot.get("value_gate") if isinstance(snapshot.get("value_gate"), dict) else {}
    try:
        gate_rc = int(value_gate.get("returncode") or 0)
    except (TypeError, ValueError):
        gate_rc = -1
    base: dict[str, Any] = {
        "requested": gate_rc in {10, 20},
        "value_gate_exit": gate_rc,
        "generic_dispatch_allowed": False if gate_rc in {10, 20} else None,
        "status": "not_requested",
        "ticket_submitted": False,
        "ticket_count": 0,
        "skipped": [],
        "quarantined": [],
    }
    if gate_rc not in {10, 20}:
        return base
    handoff = snapshot.get("handoff_relay") if isinstance(snapshot.get("handoff_relay"), dict) else {}
    if handoff and not handoff.get("ok"):
        base.update(
            {
                "status": "blocked",
                "blocker": _named_lane_blocker(
                    "overnight-handoff-blocked",
                    "handoff relay is not fresh enough to transfer one owner packet",
                    next_command="python3 scripts/handoff-relay.py && python3 scripts/handoff-relay.py --check",
                ),
            }
        )
        return base

    always = always_working_snapshot()
    owner_snapshot = always.get("snapshot") if isinstance(always.get("snapshot"), dict) else {}
    if always.get("returncode") != 0 or not isinstance(owner_snapshot.get("items"), list):
        base.update(
            {
                "status": "blocked",
                "blocker": _named_lane_blocker(
                    "always-working-owner-surface-unavailable",
                    "always-working did not return a valid owner-packet snapshot",
                ),
            }
        )
        return base
    try:
        board = load_limen_file(operational_board_path(TASKS_PATH))
        pending_ids = {
            str(patch.get("id"))
            for patch in pending_upsert_patches(TASKS_PATH)
            if isinstance(patch, dict) and patch.get("id")
        }
    except Exception:
        base.update(
            {
                "status": "blocked",
                "blocker": _named_lane_blocker(
                    "overnight-owner-board-unavailable",
                    "the task board or keeper inbox could not be read safely",
                    failed_predicate="python3 scripts/check-tabularius.py",
                    next_command="python3 scripts/tabularius-organ.py",
                ),
            }
        )
        return base

    usage, usage_error = _usage_snapshot()
    if usage_error:
        base.update(
            {
                "status": "blocked",
                "blocker": _named_lane_blocker(
                    "overnight-provider-telemetry-blocked",
                    usage_error,
                    failed_predicate="python3 scripts/usage-telemetry.py",
                    next_command="python3 scripts/usage-telemetry.py",
                ),
            }
        )
        return base

    items = [item for item in owner_snapshot["items"] if isinstance(item, dict)]
    candidates = sorted(
        (item for item in items if item.get("status") in LANE_SWITCH_OPEN_STATUSES),
        key=lambda item: (_priority_order(item.get("priority")), str(item.get("id") or "")),
    )
    local_admission: dict[str, Any] | None = None
    first_owner = "organvm/limen"
    for item in candidates:
        packet = item.get("assignment_packet") if isinstance(item.get("assignment_packet"), dict) else {}
        if packet.get("repo"):
            first_owner = str(packet["repo"])
        try:
            task = owner_task_from_item(item)
        except Exception as exc:
            item_id = str(item.get("id") or "unknown")[:128]
            base["quarantined"].append(
                {
                    "item_id": item_id,
                    "gate": "intake",
                    "reason": str(exc)[:300] or "typed intake rejected the owner packet",
                }
            )
            base["skipped"].append(
                {
                    "task_id": item_id,
                    "gate": "intake",
                    "reason": "owner packet quarantined before ticket submission",
                }
            )
            continue
        provider_ok, provider_reason = _provider_gate(task.target_agent, usage)
        if not provider_ok:
            base["skipped"].append({"task_id": task.id, "gate": "provider", "reason": provider_reason[:300]})
            continue
        # The dispatcher checks agent_can_run_task against the queue-locked board row before any
        # reservation; selecting a packet that predicate refuses can only ever produce a targeted
        # zero-launch (the 2026-07-16 wedge: local lane + self-modifying repo + non-narrow
        # predicate).  Apply the same predicate here — board row when present, compiled packet
        # otherwise — and skip with a named gate so the lane proceeds to the next launchable packet.
        capability_task = next((row for row in board.tasks if row.id == task.id), task)
        if not agent_can_run_task(task.target_agent, capability_task):
            base["skipped"].append(
                {
                    "task_id": task.id,
                    "gate": "capability",
                    "reason": (
                        f"lane {task.target_agent} cannot launch this packet under the dispatch "
                        "capability contract (agent_can_run_task); a local lane requires an "
                        "isolated narrow-verification predicate for a self-modifying repo packet"
                    )[:300],
                }
            )
            continue
        if canonical_agent(task.target_agent) in LOCAL_CHECKOUT_AGENTS:
            if local_admission is None:
                try:
                    local_admission = dict(take_admission_snapshot(ROOT))
                except Exception:
                    local_admission = {
                        "block_new_local": True,
                        "resource_blocked": True,
                        "reason": "local admission snapshot failed closed",
                    }
            local_ok, local_reason, local_gate = _local_admission_gate(task.target_agent, local_admission)
            if not local_ok:
                base["skipped"].append({"task_id": task.id, "gate": local_gate, "reason": local_reason[:300]})
                continue
        owner_state = _owned_task_state(task, board, pending_ids)
        canonical_owner_task: Task | None = None
        try:
            configured_conduct = client_from_env()
        except Exception:
            configured_conduct = None
        if isinstance(configured_conduct, HttpConductClient):
            try:
                projection = fetch_canonical_task_projection(task.id)
            except Exception as exc:
                base.update(
                    {
                        "status": "blocked",
                        "blocker": _named_lane_blocker(
                            "overnight-owner-remote-projection-unavailable",
                            f"canonical remote task lookup failed for {task.id}: {exc}",
                            owner=str(task.repo or "organvm/limen"),
                            failed_predicate="python3 scripts/check-tabularius.py",
                            next_command="PYTHONPATH=cli/src python3 scripts/tabularius-organ.py",
                        ),
                    }
                )
                return base
            canonical_owner_task = projection.task
            if canonical_owner_task is not None:
                if execution_contract_hash(canonical_owner_task) != execution_contract_hash(task):
                    base.update(
                        {
                            "status": "blocked",
                            "blocker": _named_lane_blocker(
                                "overnight-owner-canonical-contract-mismatch",
                                f"canonical remote task {task.id} changed its execution contract",
                                owner=str(task.repo or "organvm/limen"),
                                failed_predicate=str(task.predicate or ""),
                                next_command="PYTHONPATH=cli/src python3 scripts/overnight-watch.py --dry-run --json",
                            ),
                        }
                    )
                    return base
                owner_state = canonical_owner_task.status
            else:
                # The remote publication is authoritative.  A row left behind
                # in the disposable local projection must not suppress the
                # canonical upsert that creates this task.  Preserve only an
                # actual pending inbox ticket, which the drain below can
                # consume idempotently.
                owner_state = "pending" if task.id in pending_ids else None
        if owner_state and owner_state not in {"pending", *LANE_SWITCH_ACTIVE_TASK_STATUSES}:
            base["skipped"].append(
                {
                    "task_id": task.id,
                    "gate": "owner",
                    "reason": f"exact packet is terminal ({owner_state}) while receipt remains unresolved",
                }
            )
            continue
        base["packet"] = _packet_summary(task)
        if not submit:
            if canonical_owner_task is not None and owner_state in LANE_SWITCH_ACTIVE_TASK_STATUSES:
                base.update(
                    {
                        "status": "would_launch",
                        "execution_mode": "conduct",
                        "owner_state": owner_state,
                        "next_command": "PYTHONPATH=cli/src python3 scripts/overnight-watch.py --json",
                    }
                )
                return base
            if owner_state in {"dispatched", "in_progress"}:
                base.update(_active_owner_outcome(task, owner_state))
                if base.get("status") in LANE_SWITCH_GOOD_STATUSES:
                    base["next_command"] = _exact_task_command(task)
                return base
            base.update(
                {
                    "status": "would_launch" if owner_state in {"pending", "open"} else "would_submit",
                    "owner_state": owner_state,
                    "next_command": "python3 scripts/overnight-watch.py",
                }
            )
            return base
        outcome: dict[str, Any] = {
            "status": "already_owned",
            "ticket_submitted": False,
            "owner_state": owner_state,
        }
        if owner_state is None:
            try:
                outcome = _submit_one_owner_task(task)
            except Exception:
                outcome = {
                    "status": "blocked",
                    "ticket_submitted": False,
                    "blocker": _named_lane_blocker(
                        "overnight-owner-ticket-rejected",
                        "TABVLARIVS rejected the selected owner packet before it entered the inbox",
                        owner=str(task.repo or "organvm/limen"),
                        failed_predicate=str(task.predicate or ""),
                        next_command="PYTHONPATH=cli/src python3 scripts/tabularius-organ.py",
                    ),
                }
        base.update(outcome)
        base["ticket_count"] = 1 if base.get("ticket_submitted") else 0
        if base.get("status") == "blocked":
            return base
        execution_state = str(base.get("owner_state") or ("pending" if base.get("ticket_submitted") else ""))
        execution = (
            _drain_and_dispatch_one_owner_task(task, execution_state)
            if canonical_owner_task is None
            else _drain_and_dispatch_one_owner_task(
                task,
                execution_state,
                canonical_task=canonical_owner_task,
            )
        )
        base.update(execution)
        if base.get("status") in LANE_SWITCH_GOOD_STATUSES and base.get("execution_mode") != "conduct":
            base["next_command"] = _exact_task_command(task)
        return base

    blocked_items = [item for item in items if item.get("status") == "blocked"]
    if base["skipped"]:
        gates = sorted({str(entry.get("gate") or "unknown") for entry in base["skipped"]})
        if gates == ["intake"]:
            reason = f"all {len(base['quarantined'])} bounded owner packet(s) failed typed intake"
            blocker_id = "always-working-invalid-owner-packets"
        else:
            reason = f"all bounded owner packets are closed by current {', '.join(gates)} gate(s)"
            blocker_id = "overnight-owner-packets-gated"
    elif blocked_items:
        item = sorted(
            blocked_items,
            key=lambda row: (_priority_order(row.get("priority")), str(row.get("id") or "")),
        )[0]
        packet = item.get("assignment_packet") if isinstance(item.get("assignment_packet"), dict) else {}
        first_owner = str(packet.get("repo") or first_owner)
        reason = f"always-working owner item {str(item.get('id') or 'unknown')[:128]} is externally blocked"
        blocker_id = "always-working-owner-blocked"
    else:
        reason = "always-working has no unresolved predicate-shaped alternate to own"
        blocker_id = "always-working-no-owner-packet"
    base.update(
        {
            "status": "blocked",
            "blocker": _named_lane_blocker(blocker_id, reason, owner=first_owner),
        }
    )
    return base


def apply_lane_switch_control(dispatch: dict[str, Any], lane_switch: dict[str, Any]) -> dict[str, Any]:
    if not lane_switch.get("requested"):
        return dispatch
    result = dict(dispatch)
    result["allow_dispatch"] = False
    if lane_switch.get("status") in LANE_SWITCH_GOOD_STATUSES:
        task_id = str((lane_switch.get("packet") or {}).get("task_id") or "owner packet")
        exit_code = 0 if lane_switch.get("status") in LANE_SWITCH_EXECUTION_PROGRESS_STATUSES else 10
        result.update(
            {
                "exit_code": exit_code,
                "reason": f"generic dispatch remains closed; bounded owner packet {task_id} selected",
                "next_command": str(lane_switch.get("next_command") or ""),
            }
        )
        return result
    if lane_switch.get("status") == "reconciled":
        # The lane self-healed a wedged owner packet through the keeper this beat; it is progress,
        # not a stop.  Keep generic dispatch closed and re-select next beat with matching contracts.
        task_id = str((lane_switch.get("packet") or {}).get("task_id") or "owner packet")
        result.update(
            {
                "exit_code": 10,
                "reason": (
                    f"generic dispatch remains closed; owner packet {task_id} contract realigned "
                    "through the keeper — re-select next beat"
                ),
                "next_command": "PYTHONPATH=cli/src python3 scripts/overnight-watch.py --dry-run --json",
            }
        )
        return result
    blocker = lane_switch.get("blocker") if isinstance(lane_switch.get("blocker"), dict) else {}
    result.update(
        {
            "exit_code": 20,
            "reason": str(blocker.get("reason") or "no bounded owner packet clears current gates"),
            "next_command": str(blocker.get("next_command") or "python3 scripts/always-working.py --write"),
        }
    )
    return result


def dispatch_control(snapshot: dict[str, Any]) -> dict[str, Any]:
    handoff = snapshot.get("handoff_relay") if isinstance(snapshot.get("handoff_relay"), dict) else {}
    value_gate = snapshot.get("value_gate") if isinstance(snapshot.get("value_gate"), dict) else {}
    gate_rc = int(value_gate.get("returncode") or 0)
    next_command = first_next_command(value_gate)
    if handoff and not handoff.get("ok"):
        return {
            "allow_dispatch": False,
            "exit_code": 1,
            "reason": "handoff relay check failed; refresh handoff before launching workers",
            "next_command": "python3 scripts/handoff-relay.py && python3 scripts/handoff-relay.py --check",
        }
    if gate_rc == 10:
        return {
            "allow_dispatch": False,
            "exit_code": 10,
            "reason": "session value gate requested a lane switch before generic dispatch",
            "next_command": next_command,
        }
    if gate_rc >= 20:
        return {
            "allow_dispatch": False,
            "exit_code": 20,
            "reason": "session value gate stopped overnight dispatch",
            "next_command": next_command,
        }
    if gate_rc not in {0, 10, 20}:
        return {
            "allow_dispatch": False,
            "exit_code": 1,
            "reason": "session value gate failed to produce a valid dispatch decision",
            "next_command": "python3 scripts/session-value-review.py --gate --hours 1.5 --no-record-gate",
        }
    return {"allow_dispatch": True, "exit_code": 0, "reason": "dispatch allowed", "next_command": next_command}


def load_ticks() -> list[tuple[dt.datetime, dict[str, Any]]]:
    cutoff = utc_now() - dt.timedelta(days=THROUGHPUT_BASELINE_DAYS)
    out: list[tuple[dt.datetime, dict[str, Any]]] = []
    try:
        handle = TICKS_PATH.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return out
    with handle:
        for line in handle:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            ts = parse_iso(rec.get("ts"))
            if ts and ts >= cutoff:
                out.append((ts, rec))
    return out


def _completed(rec: dict[str, Any]) -> int | None:
    try:
        return int(rec.get("done", 0)) + int(rec.get("archived", 0))
    except (TypeError, ValueError):
        return None


def throughput_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Windowed completion velocity vs a floor derived from trailing history.

    below_floor is True only when the recent windows are all under the floor AND open work
    exists AND no sanctioned suppression explains the quiet (governor pause,
    budget exhaustion, dispatch gate). VITALS shed is not a suppression because off-box lanes
    remain eligible. Sanctioned quiet is surfaced as `suppressed`, never
    hidden.
    """
    result: dict[str, Any] = {
        "window_min": THROUGHPUT_WINDOW_MIN,
        "windows_required": THROUGHPUT_WINDOWS,
        "floor_fraction": THROUGHPUT_FLOOR_FRACTION,
        "evaluable": False,
        "below_floor": False,
        "suppressed": None,
    }
    ticks = load_ticks()
    window_sec = max(60, THROUGHPUT_WINDOW_MIN * 60)
    buckets: dict[int, int] = {}
    for ts, rec in ticks:
        completed = _completed(rec)
        if completed is None:
            continue
        bucket = int(ts.timestamp() // window_sec)
        buckets[bucket] = max(buckets.get(bucket, 0), completed)
    keys = sorted(buckets)
    if len(keys) < THROUGHPUT_WINDOWS + 2:
        result["reason"] = f"insufficient tick windows ({len(keys)})"
        return result
    deltas = [max(0, buckets[keys[i]] - buckets[keys[i - 1]]) for i in range(1, len(keys))]
    baseline = statistics.median(deltas)
    floor = baseline * THROUGHPUT_FLOOR_FRACTION
    recent = deltas[-THROUGHPUT_WINDOWS:]
    result.update(
        {
            "evaluable": True,
            "baseline_median": baseline,
            "floor": round(floor, 2),
            "recent_deltas": recent,
        }
    )
    if floor <= 0:
        result["reason"] = "no meaningful baseline (median 0)"
        return result
    if not all(delta < floor for delta in recent):
        return result
    last_rec = ticks[-1][1]
    try:
        open_count = int(last_rec.get("open") or 0)
    except (TypeError, ValueError):
        open_count = 0
    if open_count <= 0:
        result["suppressed"] = "no-open-work"
        return result
    dispatch = snapshot.get("dispatch_control") if isinstance(snapshot.get("dispatch_control"), dict) else {}
    try:
        spent = float(last_rec.get("daily_spent") or 0)
        cap = float(last_rec.get("daily_cap") or 0)
    except (TypeError, ValueError):
        spent, cap = 0.0, 0.0
    if dispatch and not dispatch.get("allow_dispatch", True):
        result["suppressed"] = "dispatch-gated"
    elif cap and spent >= cap:
        result["suppressed"] = "daily-budget-exhausted"
    elif governor_mode() == "paused":
        result["suppressed"] = "governor-paused"
    else:
        result["below_floor"] = True
    return result


def _plist_env(text: str) -> dict[str, str]:
    return dict(re.findall(r"<key>([A-Z_]+)</key><string>([^<]*)</string>", text))


def plist_drift() -> list[dict[str, str]]:
    """Live launchd plist vs the committed copy — the Jul-7 failure class (a hand-edited
    live plist silently starving the fleet) becomes an alert with a remediation."""
    try:
        live = _plist_env((LAUNCH_AGENTS / f"{LABEL}.plist").read_text(encoding="utf-8"))
        committed = _plist_env(COMMITTED_PLIST.read_text(encoding="utf-8"))
    except OSError:
        return []
    return [
        {"key": key, "live": live.get(key, ""), "committed": committed[key]}
        for key in PLIST_DRIFT_KEYS
        if key in committed and live.get(key) != committed[key]
    ]


def next_stale_count(previous: dict[str, Any], tick: dict[str, Any] | None) -> int:
    current = tick.get("timestamp") if tick else None
    if current and current != previous.get("latest_tick"):
        return 0
    return int(previous.get("stale_tick_count") or 0) + 1


def build_snapshot(
    *,
    refresh_handoff: bool = True,
    record_gate: bool = True,
    submit_lane_switch: bool = False,
    host_pressure_read_only: bool = False,
) -> dict[str, Any]:
    text = tail_text(HEARTBEAT_LOG)
    heartbeat = parse_heartbeat(text)
    previous = load_json(STATE_PATH)
    stale_count = next_stale_count(previous, heartbeat.get("latest_tick"))
    workers = active_workers()
    launchd = launchd_snapshot()
    children = heartbeat_child_processes(launchd.get("pid"))
    fast_wave_pid = resident_fast_wave_pid()
    watchdog_pid = resident_host_pressure_watchdog_pid()
    resident_pids = {str(pid) for pid in (fast_wave_pid, watchdog_pid) if pid}
    progress_children = [
        child
        for child in children
        if str(child.get("pid") or "") not in resident_pids
    ]
    resident_fast_wave_child = next(
        (
            child
            for child in children
            if str(child.get("pid") or "") == str(fast_wave_pid or "")
        ),
        None,
    )
    resident_host_pressure_watchdog_child = next(
        (
            child
            for child in children
            if str(child.get("pid") or "") == str(watchdog_pid or "")
        ),
        None,
    )
    resident_fast_wave = _resident_state(fast_wave_pid, resident_fast_wave_child)
    resident_host_pressure_watchdog = _resident_state(watchdog_pid, resident_host_pressure_watchdog_child)
    host_pressure = host_pressure_snapshot(
        read_only=host_pressure_read_only,
        effective_env=launchd.get("env") if isinstance(launchd.get("env"), dict) else None,
    )

    captured_at = utc_now().replace(microsecond=0)
    snapshot: dict[str, Any] = {
        "timestamp": captured_at.isoformat(timespec="seconds"),
        "root": str(ROOT),
        "log_age_sec": log_age(HEARTBEAT_LOG),
        "heartbeat": heartbeat,
        "launchd": launchd,
        "workers": workers,
        "worker_count": len(workers),
        "heartbeat_children": progress_children,
        "heartbeat_child_count": len(progress_children),
        "resident_fast_wave": resident_fast_wave,
        "resident_host_pressure_watchdog": resident_host_pressure_watchdog,
        "host_pressure": host_pressure,
        "stale_tick_count": stale_count,
        "thresholds": {
            "max_log_age_sec": MAX_LOG_AGE_SEC,
            "max_stale_ticks": MAX_STALE_TICKS,
        },
        "token_report": token_snapshot(),
        "task_events": task_event_snapshot(captured_at),
        "prompt_authority": prompt_authority_snapshot(captured_at),
    }
    snapshot["handoff_relay"] = handoff_relay_snapshot(refresh=refresh_handoff)
    snapshot["value_gate"] = session_value_gate_snapshot(record_gate=record_gate)
    snapshot["dispatch_control"] = dispatch_control(snapshot)
    snapshot["lane_switch"] = lane_switch_snapshot(snapshot, submit=submit_lane_switch)
    snapshot["dispatch_control"] = apply_lane_switch_control(snapshot["dispatch_control"], snapshot["lane_switch"])
    snapshot["overnight_counts"] = overnight_counts(snapshot)
    snapshot["plist_drift"] = plist_drift()
    snapshot["throughput"] = throughput_snapshot(snapshot)
    snapshot["status"], snapshot["alerts"] = evaluate(snapshot)
    return snapshot


def overnight_counts(snapshot: dict[str, Any]) -> dict[str, Any]:
    async_line = (snapshot.get("heartbeat") or {}).get("latest_async") or {}
    value_gate = snapshot.get("value_gate") if isinstance(snapshot.get("value_gate"), dict) else {}
    dispatch = snapshot.get("dispatch_control") if isinstance(snapshot.get("dispatch_control"), dict) else {}
    handoff = snapshot.get("handoff_relay") if isinstance(snapshot.get("handoff_relay"), dict) else {}
    lane_switch = snapshot.get("lane_switch") if isinstance(snapshot.get("lane_switch"), dict) else {}
    packet = lane_switch.get("packet") if isinstance(lane_switch.get("packet"), dict) else {}
    blocker = lane_switch.get("blocker") if isinstance(lane_switch.get("blocker"), dict) else {}
    return {
        "launched": int(async_line.get("launched") or 0),
        "harvested": int(async_line.get("harvested") or 0),
        "reaped": int(async_line.get("reaped") or 0),
        "done": 0,
        "failed": 0,
        "no_op": 0,
        "timed_out": 0,
        "stale_handoff": not bool(handoff.get("ok", False)),
        "gate_action": value_gate.get("action") or "unknown",
        "gate_exit": int(value_gate.get("returncode") or 0),
        "dispatch_allowed": bool(dispatch.get("allow_dispatch", True)),
        "lane_switch_status": lane_switch.get("status") or "not_requested",
        "lane_switch_task": packet.get("task_id") or "",
        "lane_switch_ticket_count": int(lane_switch.get("ticket_count") or 0),
        "lane_switch_blocker": blocker.get("id") or "",
        "next_command": dispatch.get("next_command") or "",
    }


def evaluate(snapshot: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    alerts: list[dict[str, str]] = []
    launchd = snapshot.get("launchd") or {}
    host_pressure = snapshot.get("host_pressure") or {}
    if host_pressure.get("ok") is False:
        alerts.append(
            {
                "id": "vitals-sample-stale",
                "evidence": str(host_pressure.get("detail") or "host-pressure watcher failed")[:500],
            }
        )
    env = launchd.get("env") if isinstance(launchd.get("env"), dict) else {}
    handoff = snapshot.get("handoff_relay") if isinstance(snapshot.get("handoff_relay"), dict) else {}
    value_gate = snapshot.get("value_gate") if isinstance(snapshot.get("value_gate"), dict) else {}
    dispatch = snapshot.get("dispatch_control") if isinstance(snapshot.get("dispatch_control"), dict) else {}
    lane_switch = snapshot.get("lane_switch") if isinstance(snapshot.get("lane_switch"), dict) else {}

    if not launchd.get("ok") or launchd.get("state") not in (None, "active", "running"):
        alerts.append(
            {
                "id": "heartbeat-launchd-not-running",
                "evidence": f"state={launchd.get('state')} error={launchd.get('error')}",
            }
        )

    heartbeat_active = launchd.get("ok") and launchd.get("state") in (None, "active", "running")
    if heartbeat_active:
        fast_wave = snapshot.get("resident_fast_wave")
        watchdog = snapshot.get("resident_host_pressure_watchdog")
        if env.get("LIMEN_VIGILIA", "1") == "1" and isinstance(fast_wave, dict) and not fast_wave.get("alive"):
            alerts.append(
                {
                    "id": "vigilia-fast-wave-missing",
                    "evidence": f"resident fast-wave pid={fast_wave.get('pid') or 'missing'} is not alive",
                }
            )
        if (
            env.get("LIMEN_HOST_PRESSURE_STALE", "1") == "1"
            and isinstance(watchdog, dict)
            and not watchdog.get("alive")
        ):
            alerts.append(
                {
                    "id": "host-pressure-watchdog-missing",
                    "evidence": f"resident watchdog pid={watchdog.get('pid') or 'missing'} is not alive",
                }
            )

    log_age_sec = snapshot.get("log_age_sec")
    if log_age_sec is None:
        alerts.append({"id": "heartbeat-log-missing", "evidence": str(HEARTBEAT_LOG)})
    elif int(log_age_sec) > MAX_LOG_AGE_SEC:
        alerts.append(
            {"id": "heartbeat-log-stale", "evidence": f"log_age_sec={log_age_sec} threshold={MAX_LOG_AGE_SEC}"}
        )

    latest_tick = (snapshot.get("heartbeat") or {}).get("latest_tick")
    if not latest_tick:
        alerts.append(
            {"id": "heartbeat-tick-missing", "evidence": "no tick emitted line found in recent heartbeat log"}
        )
    elif (
        snapshot.get("stale_tick_count", 0) >= MAX_STALE_TICKS
        and snapshot.get("worker_count", 0) == 0
        and snapshot.get("heartbeat_child_count", 0) == 0
    ):
        alerts.append(
            {
                "id": "heartbeat-progress-stale",
                "evidence": (
                    f"same tick for {snapshot.get('stale_tick_count')} monitor samples "
                    "and no active workers or heartbeat child processes"
                ),
            }
        )

    if EXPECT_CAMPAIGN_WAKE_TIMEOUT and env.get("LIMEN_CAMPAIGN_WAKE_TIMEOUT") != EXPECT_CAMPAIGN_WAKE_TIMEOUT:
        alerts.append(
            {
                "id": "heartbeat-campaign-timeout-env-mismatch",
                "evidence": (
                    "LIMEN_CAMPAIGN_WAKE_TIMEOUT="
                    f"{env.get('LIMEN_CAMPAIGN_WAKE_TIMEOUT')} expected={EXPECT_CAMPAIGN_WAKE_TIMEOUT}"
                ),
            }
        )

    if handoff and not handoff.get("ok"):
        alerts.append(
            {
                "id": "handoff-relay-stale",
                "evidence": str(handoff.get("check_output") or "handoff-relay --check failed")[:500],
            }
        )
    gate_rc = int(value_gate.get("returncode") or 0)
    lane_status = str(lane_switch.get("status") or "")
    if lane_switch.get("requested") and lane_status == "blocked":
        blocker = lane_switch.get("blocker") if isinstance(lane_switch.get("blocker"), dict) else {}
        alerts.append(
            {
                "id": "overnight-lane-switch-blocked",
                "evidence": (
                    f"blocker={blocker.get('id') or 'unnamed'} owner={blocker.get('owner') or 'unknown'} "
                    f"reason={blocker.get('reason') or 'no eligible owner packet'}"
                )[:500],
            }
        )
    elif gate_rc >= 20 and lane_status not in LANE_SWITCH_GOOD_STATUSES and lane_status != "reconciled":
        # A self-healed lane (reconciled this beat via the keeper) is progress, not a gate stop.
        alerts.append(
            {
                "id": "session-value-gate-stop",
                "evidence": str(value_gate.get("output") or dispatch.get("reason") or "gate stopped")[:500],
            }
        )
    elif gate_rc not in {0, 10, 20}:
        alerts.append(
            {
                "id": "session-value-gate-error",
                "evidence": str(value_gate.get("output") or "session-value-review gate failed")[:500],
            }
        )

    drift = snapshot.get("plist_drift") or []
    if drift:
        alerts.append(
            {
                "id": "plist-drift",
                "evidence": "; ".join(f"{d['key']}: live={d['live']!r} committed={d['committed']!r}" for d in drift)[
                    :500
                ],
            }
        )

    throughput = snapshot.get("throughput") if isinstance(snapshot.get("throughput"), dict) else {}
    if throughput.get("below_floor"):
        alerts.append(
            {
                "id": "throughput-collapse",
                "evidence": (
                    f"recent per-{throughput.get('window_min')}min completions "
                    f"{throughput.get('recent_deltas')} all below derived floor {throughput.get('floor')} "
                    f"({THROUGHPUT_BASELINE_DAYS}d median {throughput.get('baseline_median')}) "
                    "with open work and no sanctioned suppression"
                ),
            }
        )

    if alerts:
        return "alert", alerts
    if dispatch and not dispatch.get("allow_dispatch", True):
        return "blocked", alerts
    return "ok", alerts


def governor_mode() -> str:
    """Fail toward 'paused' (no heal) like heartbeat-loop.sh does when the governor is unreachable."""
    script = ROOT / "scripts" / "autonomy-governor.py"
    if not script.exists():
        return "paused"
    proc = run([sys.executable, str(script), "mode"], timeout=15)
    if proc.returncode != 0:
        return "paused"
    return (proc.stdout or "").strip() or "paused"


def service_missing(label: str) -> bool:
    return run(["launchctl", "print", f"gui/{os.getuid()}/{label}"]).returncode != 0


def bootstrap_service(label: str) -> dict[str, Any]:
    plist = LAUNCH_AGENTS / f"{label}.plist"
    if not plist.exists():
        return {"label": label, "action": "skip", "reason": f"plist missing: {plist}"}
    proc = run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist)], timeout=30)
    return {
        "label": label,
        "action": "bootstrap",
        "ok": proc.returncode == 0,
        "error": (proc.stderr or "").strip() if proc.returncode else "",
    }


def reinstall_plist() -> dict[str, Any]:
    """Re-install the committed plist over a drifted live copy, then bootout+bootstrap."""
    if not COMMITTED_PLIST.exists():
        return {"action": "skip", "reason": f"committed plist missing: {COMMITTED_PLIST}"}
    dest = LAUNCH_AGENTS / f"{LABEL}.plist"
    try:
        shutil.copyfile(COMMITTED_PLIST, dest)
    except OSError as exc:
        return {"action": "reinstall-plist", "ok": False, "error": str(exc)}
    run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], timeout=30)
    time.sleep(2)
    proc = run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(dest)], timeout=30)
    return {
        "action": "reinstall-plist",
        "ok": proc.returncode == 0,
        "error": (proc.stderr or "").strip() if proc.returncode else "",
    }


def kickstart_service(label: str) -> dict[str, Any]:
    proc = run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{label}"], timeout=30)
    return {
        "action": "kickstart",
        "label": label,
        "ok": proc.returncode == 0,
        "error": (proc.stderr or "").strip() if proc.returncode else "",
    }


def escalate_issue(evidence: str) -> dict[str, Any]:
    """A collapse that survives remediation escalates to the censor issues mirror — never chat."""
    if not ISSUE_ESCALATE:
        return {"action": "skip", "reason": "issue escalation disabled"}
    title = "throughput-collapse survives remediation"
    listing = run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            ESCALATE_REPO,
            "--state",
            "open",
            "--search",
            f"{title} in:title",
            "--json",
            "number",
        ],
        timeout=30,
    )
    if listing.returncode == 0:
        try:
            if json.loads(listing.stdout or "[]"):
                return {"action": "escalate-issue", "ok": True, "deduped": True}
        except ValueError:
            pass
    body = (
        f"The overnight monitor's throughput-collapse alert survived self-remediation.\n\n"
        f"Evidence: {evidence}\n\nReceipts: logs/overnight-watch.md, logs/ticks.jsonl."
    )
    proc = run(
        ["gh", "issue", "create", "--repo", ESCALATE_REPO, "--title", title, "--label", "censor", "--body", body],
        timeout=30,
    )
    return {
        "action": "escalate-issue",
        "ok": proc.returncode == 0,
        "url": (proc.stdout or "").strip() if proc.returncode == 0 else "",
        "error": (proc.stderr or "").strip() if proc.returncode else "",
    }


def heal(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Every alert this monitor owns names its effector (PREC-2026-07-09-sensor-without-effector).

    Lanes, disjoint from watchdog.py's stale-daemon kickstart:
      * heartbeat-launchd-not-running + service absent  -> bootstrap from the plist
      * plist-drift                                     -> reinstall committed plist + reload
      * throughput-collapse (no drift)                  -> kickstart; if it survives a prior
        remediation, escalate to the censor issues mirror — never to the operator in chat
    """
    if not HEAL_ENABLED:
        return []
    alert_ids = {alert["id"] for alert in snapshot.get("alerts") or []}
    launchd_missing = "heartbeat-launchd-not-running" in alert_ids and not (snapshot.get("launchd") or {}).get("ok")
    drift = "plist-drift" in alert_ids
    collapse = "throughput-collapse" in alert_ids
    if not (launchd_missing or drift or collapse):
        return []
    previous = load_json(STATE_PATH)
    last_heal = parse_iso(previous.get("last_heal_at"))
    if last_heal and (utc_now() - last_heal).total_seconds() < HEAL_COOLDOWN_SEC:
        return [{"action": "skip", "reason": f"heal cooldown ({HEAL_COOLDOWN_SEC}s) active"}]
    if governor_mode() == "paused":
        return [{"action": "skip", "reason": "autonomy governor paused"}]

    actions: list[dict[str, Any]] = []
    if launchd_missing:
        actions.append(bootstrap_service(LABEL))
        if service_missing(WATCHDOG_LABEL):
            actions.append(bootstrap_service(WATCHDOG_LABEL))
    elif drift:
        actions.append(reinstall_plist())
    elif collapse:
        actions.append(kickstart_service(LABEL))

    if collapse:
        attempts = int(previous.get("collapse_heal_attempts") or 0) + 1
        snapshot["collapse_heal_attempts"] = attempts
        if attempts >= 2:
            evidence = next(
                (a["evidence"] for a in snapshot.get("alerts") or [] if a["id"] == "throughput-collapse"), ""
            )
            actions.append(escalate_issue(evidence))

    if any(a.get("action") in ("bootstrap", "reinstall-plist", "kickstart") for a in actions):
        snapshot["heal_at"] = snapshot.get("timestamp")
    return actions


def update_state(snapshot: dict[str, Any]) -> None:
    tick = (snapshot.get("heartbeat") or {}).get("latest_tick") or {}
    previous = load_json(STATE_PATH)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(
            {
                "updated_at": snapshot.get("timestamp"),
                "latest_tick": tick.get("timestamp"),
                "stale_tick_count": snapshot.get("stale_tick_count", 0),
                "status": snapshot.get("status"),
                "last_heal_at": snapshot.get("heal_at") or previous.get("last_heal_at"),
                "collapse_heal_attempts": (
                    snapshot.get("collapse_heal_attempts")
                    if snapshot.get("collapse_heal_attempts") is not None
                    else (
                        int(previous.get("collapse_heal_attempts") or 0)
                        if any(a.get("id") == "throughput-collapse" for a in snapshot.get("alerts") or [])
                        else 0
                    )
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def write_jsonl(snapshot: dict[str, Any]) -> None:
    lock_path = RECEIPT_JSONL.with_suffix(RECEIPT_JSONL.suffix + ".lock")
    parent_errors = _trusted_custody_path_errors(
        RECEIPT_JSONL.parent,
        label="watch ledger parent",
        final_directory=True,
    )
    ledger_errors = _trusted_canonical_file_errors(
        RECEIPT_JSONL,
        label="watch ledger",
        allow_missing=True,
    )
    lock_errors = _trusted_canonical_file_errors(
        lock_path,
        label="watch ledger lock",
        allow_missing=True,
    )
    if parent_errors or ledger_errors or lock_errors:
        raise TrialContractError("; ".join([*parent_errors, *ledger_errors, *lock_errors]))
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open(RECEIPT_JSONL.parent, directory_flags)
    try:
        lock_flags = os.O_RDWR | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        lock_fd = os.open(lock_path.name, lock_flags, 0o600, dir_fd=directory_fd)
        with os.fdopen(lock_fd, "a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            ledger_flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(RECEIPT_JSONL.name, ledger_flags, 0o600, dir_fd=directory_fd)
            with os.fdopen(fd, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(snapshot, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def write_markdown(snapshot: dict[str, Any]) -> None:
    heartbeat = snapshot.get("heartbeat") or {}
    tick = heartbeat.get("latest_tick") or {}
    async_line = heartbeat.get("latest_async") or {}
    launchd = snapshot.get("launchd") or {}
    workers = snapshot.get("workers") or []
    children = snapshot.get("heartbeat_children") or []
    counts = snapshot.get("overnight_counts") or {}
    handoff = snapshot.get("handoff_relay") or {}
    value_gate = snapshot.get("value_gate") or {}
    dispatch = snapshot.get("dispatch_control") or {}
    lane_switch = snapshot.get("lane_switch") or {}
    lane_packet = lane_switch.get("packet") or {}
    lane_blocker = lane_switch.get("blocker") or {}
    lines = [
        "# Overnight Watch",
        "",
        f"- Status: `{snapshot.get('status')}`",
        f"- Updated: `{snapshot.get('timestamp')}`",