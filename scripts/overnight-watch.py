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
from limen.dispatch import agent_can_run_task  # noqa: E402
from limen.execution_contract import execution_contract_hash, execution_contract_payload  # noqa: E402
from limen.intake import validate_intake_contract  # noqa: E402
from limen.io import load_limen_file  # noqa: E402
from limen.models import Task  # noqa: E402
from limen.tabularius import (  # noqa: E402
    INTENT_UPSERT,
    Ticket,
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

MAX_LOG_AGE_SEC = int(os.environ.get("LIMEN_OVERNIGHT_WATCH_MAX_LOG_AGE_SEC", "1200") or "1200")
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
PLIST_DRIFT_KEYS = ("LIMEN_ASYNC_MAX", "LIMEN_DISPATCH_ASYNC", "LIMEN_DISPATCH_LANES", "LIMEN_ROOT")
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

EXPECT_DISPATCH_ASYNC = os.environ.get("LIMEN_OVERNIGHT_WATCH_EXPECT_DISPATCH_ASYNC", "")
EXPECT_DISPATCH_LANES = os.environ.get("LIMEN_OVERNIGHT_WATCH_EXPECT_DISPATCH_LANES", "")
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


def run(args: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
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
        board = load_limen_file(TASKS_PATH)
    except Exception:
        return None
    current = next((task for task in board.tasks if task.id == task_id), None)
    last = current.dispatch_log[-1] if current is not None and current.dispatch_log else None
    if (
        current is None
        or current.status != "dispatched"
        or last is None
        or last.status != "dispatched"
        or (last.session_id != "async-reserve" and not _ASYNC_RESERVATION_RE.fullmatch(last.session_id))
    ):
        return None
    return last.session_id


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
        board = load_limen_file(TASKS_PATH)
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


def _drain_and_dispatch_one_owner_task(task: Task, owner_state: str) -> dict[str, Any]:
    """Drain/launch one exact packet, or return a named fail-closed blocker."""

    existing_async = _async_task_state(task.id)
    if existing_async:
        if existing_async.get("status") in {"already_running", "result_pending_harvest"}:
            return {**existing_async, "owner_state": owner_state, "targeted_launch_count": 0}
        return _active_owner_outcome(task, owner_state)
    if owner_state in {"dispatched", "in_progress"}:
        return _active_owner_outcome(task, owner_state)

    if owner_state == "pending":
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

    try:
        board = load_limen_file(TASKS_PATH)
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
        board = load_limen_file(TASKS_PATH)
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
        board = load_limen_file(TASKS_PATH)
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
        execution = _drain_and_dispatch_one_owner_task(task, execution_state)
        base.update(execution)
        if base.get("status") in LANE_SWITCH_GOOD_STATUSES:
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
        result.update(
            {
                "exit_code": 10,
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
) -> dict[str, Any]:
    text = tail_text(HEARTBEAT_LOG)
    heartbeat = parse_heartbeat(text)
    previous = load_json(STATE_PATH)
    stale_count = next_stale_count(previous, heartbeat.get("latest_tick"))
    workers = active_workers()
    launchd = launchd_snapshot()
    children = heartbeat_child_processes(launchd.get("pid"))

    captured_at = utc_now().replace(microsecond=0)
    snapshot: dict[str, Any] = {
        "timestamp": captured_at.isoformat(timespec="seconds"),
        "root": str(ROOT),
        "log_age_sec": log_age(HEARTBEAT_LOG),
        "heartbeat": heartbeat,
        "launchd": launchd,
        "workers": workers,
        "worker_count": len(workers),
        "heartbeat_children": children,
        "heartbeat_child_count": len(children),
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

    if EXPECT_DISPATCH_ASYNC and env.get("LIMEN_DISPATCH_ASYNC") != EXPECT_DISPATCH_ASYNC:
        alerts.append(
            {
                "id": "heartbeat-async-env-mismatch",
                "evidence": f"LIMEN_DISPATCH_ASYNC={env.get('LIMEN_DISPATCH_ASYNC')} expected={EXPECT_DISPATCH_ASYNC}",
            }
        )
    if EXPECT_DISPATCH_LANES and env.get("LIMEN_DISPATCH_LANES") != EXPECT_DISPATCH_LANES:
        alerts.append(
            {
                "id": "heartbeat-lanes-env-mismatch",
                "evidence": f"LIMEN_DISPATCH_LANES={env.get('LIMEN_DISPATCH_LANES')} expected={EXPECT_DISPATCH_LANES}",
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
        f"- Log age: `{snapshot.get('log_age_sec')}` seconds",
        f"- Launchd: `{launchd.get('state')}`",
        f"- Latest tick: `{tick.get('raw')}`",
        f"- Latest async: `{async_line.get('raw')}`",
        f"- Stale tick samples: `{snapshot.get('stale_tick_count')}`",
        f"- Active workers: `{len(workers)}`",
        f"- Heartbeat child processes: `{len(children)}`",
        "",
        "## Overnight Summary",
        "",
        f"- Launched: `{counts.get('launched', 0)}`; harvested: `{counts.get('harvested', 0)}`; reaped: `{counts.get('reaped', 0)}`.",
        f"- Done: `{counts.get('done', 0)}`; failed: `{counts.get('failed', 0)}`; no-op: `{counts.get('no_op', 0)}`; timed out: `{counts.get('timed_out', 0)}`.",
        f"- Stale handoff: `{str(counts.get('stale_handoff', False)).lower()}`.",
        f"- Gate action: `{counts.get('gate_action', 'unknown')}` (exit `{counts.get('gate_exit', 'n/a')}`).",
        f"- Dispatch allowed: `{str(counts.get('dispatch_allowed', True)).lower()}`.",
        f"- Lane switch: `{counts.get('lane_switch_status', 'not_requested')}`; owner packet: "
        f"`{counts.get('lane_switch_task') or 'none'}`; tickets: `{counts.get('lane_switch_ticket_count', 0)}`.",
        f"- Lane blocker: `{counts.get('lane_switch_blocker') or 'none'}`.",
        f"- Next command: `{counts.get('next_command') or 'none'}`.",
        "",
        "## Gate Checks",
        "",
        f"- Handoff refresh: `{handoff.get('refresh_returncode')}`; check: `{handoff.get('check_returncode')}`.",
        f"- Value gate: `{value_gate.get('returncode')}`; action: `{value_gate.get('action')}`.",
        f"- Dispatch control: {dispatch.get('reason', 'dispatch allowed')}.",
        f"- Selected owner: `{lane_packet.get('repo') or lane_blocker.get('owner') or 'none'}`.",
    ]
    throughput = snapshot.get("throughput") if isinstance(snapshot.get("throughput"), dict) else {}
    if throughput:
        lines.extend(
            [
                "",
                "## Throughput",
                "",
                f"- Recent per-{throughput.get('window_min')}min completions: `{throughput.get('recent_deltas')}`"
                f" (derived floor `{throughput.get('floor')}`, median `{throughput.get('baseline_median')}`).",
                f"- Below floor: `{str(throughput.get('below_floor', False)).lower()}`;"
                f" suppressed: `{throughput.get('suppressed') or 'no'}`.",
            ]
        )
    for worker in workers[:10]:
        lines.append(f"  - `{worker.get('name')}` age `{worker.get('age_sec')}` seconds")
    for child in children[:10]:
        lines.append(
            f"  - child `{child.get('pid')}` `{child.get('stat')}` `{child.get('etime')}` `{child.get('command')}`"
        )
    if snapshot.get("alerts"):
        lines.extend(["", "## WATCH_ALERT"])
        for alert in snapshot["alerts"]:
            lines.append(f"- `{alert['id']}`: {alert['evidence']}")
    if snapshot.get("heal"):
        lines.extend(["", "## HEAL"])
        for action in snapshot["heal"]:
            lines.append(f"- {json.dumps(action, sort_keys=True)}")
    RECEIPT_MD.write_text("\n".join(lines) + "\n")


def update_alert(snapshot: dict[str, Any]) -> None:
    alerts = snapshot.get("alerts") or []
    prior = load_json(ALERT_PATH)
    prior_active = bool(prior.get("active"))
    prior_sig = prior.get("signature")
    sig = "+".join(alert["id"] for alert in alerts)
    if not alerts:
        if prior_active:
            prior.update({"active": False, "resolved_at": snapshot.get("timestamp")})
            ALERT_PATH.write_text(json.dumps(prior, indent=2, sort_keys=True) + "\n")
        return
    if prior_active and prior_sig == sig:
        return
    ALERT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALERT_PATH.write_text(
        json.dumps(
            {
                "active": True,
                "fired_at": snapshot.get("timestamp"),
                "signature": sig,
                "alerts": alerts,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def write_receipts(snapshot: dict[str, Any]) -> None:
    update_state(snapshot)
    write_jsonl(snapshot)
    write_markdown(snapshot)
    update_alert(snapshot)


def _bounded_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _strict_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_custody(path: Path) -> dict[str, Any]:
    payload, _, file_errors = _read_trusted_regular_file(path, label="custody source")
    present = not file_errors and payload is not None
    if payload is None:
        payload = b""
    return {
        "present": present,
        "size": len(payload),
        "digest": _sha256_bytes(payload),
    }


def _custody_errors(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["source custody is missing"]
    errors: list[str] = []
    if not isinstance(value.get("present"), bool):
        errors.append("source custody present flag is invalid")
    if not _strict_nonnegative_int(value.get("size")):
        errors.append("source custody size is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(value.get("digest") or "")):
        errors.append("source custody digest is invalid")
    return errors


def _prefix_matches(path: Path, custody: dict[str, Any]) -> bool:
    if _custody_errors(custody):
        return False
    size = int(custody["size"])
    try:
        path.lstat()
    except OSError:
        return size == 0 and custody.get("present") is False and custody.get("digest") == _sha256_bytes(b"")
    payload, _, file_errors = _read_trusted_regular_file(path, label="prefix source")
    if file_errors or payload is None:
        return False
    prefix = payload[:size]
    current_size = len(payload)
    return current_size >= size and len(prefix) == size and _sha256_bytes(prefix) == custody.get("digest")


def _jsonl_bytes(payload: bytes) -> tuple[list[dict[str, Any]], int]:
    if payload and not payload.endswith(b"\n"):
        return [], 1
    try:
        lines = payload.decode("utf-8", "strict").splitlines()
    except UnicodeError:
        return [], 1
    rows: list[dict[str, Any]] = []
    errors = 0
    for line in lines:
        try:
            value = json.loads(line)
        except ValueError:
            errors += 1
            continue
        if not isinstance(value, dict):
            errors += 1
            continue
        rows.append(value)
    return rows, errors


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    parent_errors = _trusted_custody_path_errors(
        path.parent,
        label="trial append parent",
        final_directory=True,
    )
    file_errors = _trusted_canonical_file_errors(
        path,
        label="trial append ledger",
        allow_missing=True,
    )
    if parent_errors or file_errors:
        raise TrialContractError("; ".join([*parent_errors, *file_errors]))
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open(path.parent, directory_flags)
    try:
        file_flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path.name, file_flags, 0o600, dir_fd=directory_fd)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _trial_windows(start: dt.datetime, end: dt.datetime) -> list[tuple[dt.datetime, dt.datetime]]:
    width = dt.timedelta(seconds=TRIAL_VALUE_WINDOW_SEC)
    windows: list[tuple[dt.datetime, dt.datetime]] = []
    cursor = start
    while cursor + width <= end:
        windows.append((cursor, cursor + width))
        cursor += width
    final_start = end - width
    if final_start >= start and (not windows or final_start > windows[-1][0]):
        windows.append((final_start, end))
    return windows


class TrialContractError(RuntimeError):
    """The unattended-trial lifecycle cannot advance truthfully."""


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    parent_errors = _trusted_custody_path_errors(
        path.parent,
        label="trial JSON parent",
        final_directory=True,
    )
    if parent_errors:
        raise TrialContractError("; ".join(parent_errors))
    existing_errors = _trusted_canonical_file_errors(
        path,
        label="trial JSON output",
        allow_missing=True,
    )
    if existing_errors:
        raise TrialContractError("; ".join(existing_errors))
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary_name = f".{path.name}.{os.getpid()}.tmp"
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open(path.parent, directory_flags)
    created = False
    try:
        file_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(temporary_name, file_flags, 0o600, dir_fd=directory_fd)
        created = True
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            temporary_name,
            path.name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        created = False
        os.fsync(directory_fd)
    finally:
        if created:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except OSError:
                pass
        os.close(directory_fd)


def _content_hash_valid(value: dict[str, Any]) -> bool:
    claimed = str(value.get("content_hash") or "")
    deterministic = {key: item for key, item in value.items() if key != "content_hash"}
    return bool(re.fullmatch(r"[0-9a-f]{64}", claimed)) and claimed == canonical_hash(deterministic)


def _trial_anchor_path(marker: dict[str, Any]) -> Path:
    return TRIAL_WINDOW_PATH.parent / "overnight-trial-anchors" / f"{marker.get('content_hash')}.json"


def _anchor_created_ns(path: Path) -> int:
    metadata = path.lstat()
    birth = getattr(metadata, "st_birthtime", None)
    return int((birth if birth is not None else metadata.st_ctime) * 1_000_000_000)


def _write_trial_anchor(marker: dict[str, Any]) -> None:
    path = _trial_anchor_path(marker)
    configured_errors = _trusted_custody_path_errors(
        path.parent.parent,
        label="prospective anchor configured root",
        final_directory=True,
    )
    if configured_errors:
        raise TrialContractError("; ".join(configured_errors))
    if path.parent.is_symlink():
        raise TrialContractError("prospective anchor directory is a symlink")
    path.parent.mkdir(mode=0o700, exist_ok=True)
    anchor_root_errors = _trusted_custody_path_errors(
        path.parent,
        label="prospective anchor directory",
        final_directory=True,
    )
    if anchor_root_errors:
        raise TrialContractError("; ".join(anchor_root_errors))
    payload = {
        "trial_id": marker.get("content_hash"),
        "started_at": marker.get("started_at"),
        "evaluator_hash": marker.get("evaluator_hash"),
        "monotonic_start_ns": marker.get("monotonic_start_ns"),
    }
    material = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open(path.parent, directory_flags)
    try:
        file_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path.name, file_flags, 0o400, dir_fd=directory_fd)
        with os.fdopen(fd, "wb") as handle:
            handle.write(material)
            handle.flush()
            os.fsync(handle.fileno())
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _trial_anchor_errors(marker: dict[str, Any]) -> list[str]:
    path = _trial_anchor_path(marker)
    path_errors = _trusted_canonical_file_errors(
        path,
        label="prospective trial anchor",
    )
    if path_errors:
        if path_errors == ["prospective trial anchor is missing"]:
            return ["prospective trial anchor is missing or malformed"]
        return path_errors
    expected = {
        "trial_id": marker.get("content_hash"),
        "started_at": marker.get("started_at"),
        "evaluator_hash": marker.get("evaluator_hash"),
        "monotonic_start_ns": marker.get("monotonic_start_ns"),
    }
    payload, _, read_errors = _read_trusted_regular_file(path, label="prospective trial anchor")
    if read_errors:
        return read_errors
    try:
        actual = json.loads(payload or b"{}")
        created_ns = _anchor_created_ns(path)
    except (OSError, ValueError):
        return ["prospective trial anchor is missing or malformed"]
    errors: list[str] = []
    if actual != expected:
        errors.append("prospective trial anchor does not match the active marker")
    started_at = parse_iso(str(marker.get("started_at") or ""))
    if started_at is None or abs(created_ns / 1_000_000_000 - started_at.timestamp()) > TRIAL_CLOCK_TOLERANCE_SEC:
        errors.append("prospective trial anchor creation time does not match trial start")
    return errors


def _observation_custody_directory(marker: dict[str, Any]) -> Path:
    trial_id = str(marker.get("content_hash") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", trial_id):
        raise TrialContractError("observation custody trial id is invalid")
    return TRIAL_WINDOW_PATH.parent / "overnight-trial-observation-custody" / trial_id


def _observation_custody_path(marker: dict[str, Any], observation: dict[str, Any]) -> Path:
    sequence = observation.get("sequence")
    content_hash = str(observation.get("content_hash") or "")
    if not isinstance(sequence, int) or sequence < 1 or not re.fullmatch(r"[0-9a-f]{64}", content_hash):
        raise TrialContractError("observation custody identity is invalid")
    return _observation_custody_directory(marker) / f"{sequence:06d}-{content_hash}.json"


def _observation_custody_payload(marker: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": TRIAL_OBSERVATION_CUSTODY_SCHEMA_VERSION,
        "trial_id": marker.get("content_hash"),
        "sequence": observation.get("sequence"),
        "observed_at": observation.get("observed_at"),
        "observation_hash": observation.get("content_hash"),
        "observation_digest": canonical_hash(observation),
        "proof_digest": canonical_hash(
            {name: observation.get(name) or [] for name in ("value_proofs", "blocker_proofs", "session_proofs")}
        ),
    }


def _prepare_observation_custody(marker: dict[str, Any]) -> None:
    directory = _observation_custody_directory(marker)
    configured_root = directory.parent
    configured_errors = _trusted_custody_path_errors(
        configured_root.parent,
        label="observation custody configured root",
        final_directory=True,
    )
    if configured_errors:
        raise TrialContractError("; ".join(configured_errors))
    if configured_root.is_symlink():
        raise TrialContractError("observation custody root is a symlink")
    configured_root.mkdir(mode=0o700, exist_ok=True)
    root_errors = _trusted_custody_path_errors(
        configured_root,
        label="observation custody root",
        final_directory=True,
    )
    if root_errors:
        raise TrialContractError("; ".join(root_errors))
    if directory.is_symlink():
        raise TrialContractError("observation custody trial directory is a symlink")
    directory.mkdir(mode=0o700, exist_ok=True)
    directory_errors = _trusted_custody_path_errors(
        directory,
        label="observation custody trial directory",
        final_directory=True,
    )
    if directory_errors:
        raise TrialContractError("; ".join(directory_errors))


def _observation_custody_created_ns(path: Path) -> int:
    metadata = path.lstat()
    birth = getattr(metadata, "st_birthtime", None)
    return int((birth if birth is not None else metadata.st_ctime) * 1_000_000_000)


def _observation_custody_errors(marker: dict[str, Any], observation: dict[str, Any]) -> list[str]:
    try:
        path = _observation_custody_path(marker, observation)
    except TrialContractError as exc:
        return [str(exc)]
    payload, mode, read_errors = _read_trusted_regular_file(path, label="prospective observation custody")
    if read_errors or payload is None or mode is None:
        return read_errors or ["prospective observation custody is missing"]
    try:
        actual = json.loads(payload)
    except (UnicodeError, ValueError):
        return ["prospective observation custody is malformed"]
    errors: list[str] = []
    if actual != _observation_custody_payload(marker, observation):
        errors.append("prospective observation custody does not match the observation")
    if mode & 0o222:
        errors.append("prospective observation custody is writable")
    observed_at = parse_iso(str(observation.get("observed_at") or ""))
    try:
        created_ns = _observation_custody_created_ns(path)
    except OSError:
        created_ns = 0
    if observed_at is None or abs(created_ns / 1_000_000_000 - observed_at.timestamp()) > TRIAL_CLOCK_TOLERANCE_SEC:
        errors.append("prospective observation custody creation time does not match observation time")
    return errors


def _write_observation_custody(marker: dict[str, Any], observation: dict[str, Any]) -> None:
    _prepare_observation_custody(marker)
    path = _observation_custody_path(marker, observation)
    if path.exists():
        existing_errors = _observation_custody_errors(marker, observation)
        if existing_errors:
            raise TrialContractError("; ".join(existing_errors))
        return
    material = (json.dumps(_observation_custody_payload(marker, observation), sort_keys=True) + "\n").encode("utf-8")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open(path.parent, directory_flags)
    try:
        file_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path.name, file_flags, 0o400, dir_fd=directory_fd)
        with os.fdopen(fd, "wb") as handle:
            handle.write(material)
            handle.flush()
            os.fsync(handle.fileno())
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _event_digest(event_ids: list[str]) -> str:
    return canonical_hash(sorted(event_ids))


def _task_event_payload(
    task: dict[str, Any],
    log: dict[str, Any],
    *,
    log_index: int,
    status: str,
) -> dict[str, Any]:
    return {
        "task_id": str(task.get("id") or ""),
        "log_index": log_index,
        "timestamp": str(log.get("timestamp") or ""),
        "status": status,
        "agent": str(log.get("agent") or ""),
        "session_id": str(log.get("session_id") or ""),
        "predicate_hash": canonical_hash(str(task.get("predicate") or "")),
        "receipt_target_hash": canonical_hash(str(task.get("receipt_target") or "")),
        "output_hash": canonical_hash(str(log.get("output") or "")),
    }


def _typed_terminal_event(task: dict[str, Any], log: dict[str, Any]) -> bool:
    predicate = str(task.get("predicate") or "").strip()
    receipt_target = str(task.get("receipt_target") or "").strip()
    cli_src = Path(__file__).resolve().parents[1] / "cli" / "src"
    if str(cli_src) not in sys.path:
        sys.path.insert(0, str(cli_src))
    try:
        from limen.intake import is_durable_receipt_target, is_executable_predicate

        contract_ok = is_executable_predicate(predicate) and is_durable_receipt_target(receipt_target)
    except (ImportError, ModuleNotFoundError):
        try:
            argv = shlex.split(predicate)
        except ValueError:
            argv = []
        predicate_ok = bool(
            argv
            and (
                argv[0] in {"[", "bash", "git", "gh", "python", "python3", "sh", "test"}
                or "/" in argv[0]
                or argv[0].endswith((".py", ".sh"))
            )
        )
        github_target = bool(
            re.fullmatch(r"https://github\.com/[^/]+/[^/]+/(?:issues|pull|actions|commit)/.+", receipt_target)
        )
        git_target = re.fullmatch(r"git:[^/:]+/[^:]+:(?P<path>[^\s]+)", receipt_target)
        git_target_ok = bool(
            git_target
            and not git_target.group("path").startswith("/")
            and all(part not in {"", ".", "..", ".git"} for part in git_target.group("path").split("/"))
        )
        contract_ok = predicate_ok and (github_target or git_target_ok)
    return bool(contract_ok and str(log.get("output") or "").strip())


def _load_task_event_ledger(path: Path | None = None) -> dict[str, Any]:
    source = path or TASKS_PATH
    streams: dict[str, list[tuple[dt.datetime, str]]] = {
        "value_done": [],
        "owner_blocked": [],
        "session_seams": [],
    }
    all_events: dict[str, dict[str, Any]] = {}
    payload, _, file_errors = _read_trusted_regular_file(source, label="task source")
    errors = len(file_errors)
    try:
        board = yaml.safe_load(payload.decode("utf-8", "strict")) if payload is not None else {}
    except (UnicodeError, yaml.YAMLError):
        board = {}
        errors += 1
    tasks = board.get("tasks") if isinstance(board, dict) else None
    if not isinstance(tasks, list):
        tasks = []
        errors += 1

    session_events: dict[str, tuple[dt.datetime, str]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            errors += 1
            continue
        logs = task.get("dispatch_log") or []
        if not isinstance(logs, list):
            errors += 1
            continue
        for log_index, log in enumerate(logs):
            if not isinstance(log, dict):
                errors += 1
                continue
            status = str(log.get("status") or "")
            if status not in {"done", "failed_blocked", "needs_human", "in_progress"}:
                continue
            timestamp = parse_iso(str(log.get("timestamp") or ""))
            if timestamp is None:
                errors += 1
                continue
            payload = _task_event_payload(task, log, log_index=log_index, status=status)
            event_id = canonical_hash(payload)
            entry = {
                "event_id": event_id,
                "task_id": str(task.get("id") or ""),
                "status": status,
                "timestamp": timestamp.isoformat(timespec="seconds"),
                "agent": str(log.get("agent") or ""),
                "session_id": str(log.get("session_id") or ""),
                "predicate": str(task.get("predicate") or ""),
                "receipt_target": str(task.get("receipt_target") or ""),
                "output_present": bool(str(log.get("output") or "").strip()),
            }
            if event_id in all_events and all_events[event_id] != entry:
                errors += 1
                continue
            all_events[event_id] = entry
            if status == "done" and _typed_terminal_event(task, log):
                streams["value_done"].append((timestamp, event_id))
            elif status in {"failed_blocked", "needs_human"} and _typed_terminal_event(task, log):
                streams["owner_blocked"].append((timestamp, event_id))
            elif status == "in_progress":
                agent = str(log.get("agent") or "").strip()
                session_id = str(log.get("session_id") or "").strip()
                if (
                    not agent
                    or not session_id
                    or session_id.lower()
                    in {
                        "heal",
                        "none",
                        "null",
                        "receipt_refresh",
                        "unknown",
                    }
                ):
                    continue
                session_key = canonical_hash({"agent": agent, "session_id": session_id})
                event = (timestamp, event_id)
                if session_key not in session_events or event < session_events[session_key]:
                    session_events[session_key] = event
    streams["session_seams"].extend(session_events.values())
    for events in streams.values():
        events.sort(key=lambda item: (item[0], item[1]))
    return {
        "ok": errors == 0,
        "error_count": errors,
        "streams": streams,
        "all_events": all_events,
        "file_custody": _file_custody(source),
    }


def _task_source_snapshot(ledger: dict[str, Any]) -> dict[str, Any]:
    event_ids = sorted(str(value) for value in (ledger.get("all_events") or {}))
    return {
        "ok": ledger.get("ok") is True,
        "error_count": _bounded_int(ledger.get("error_count")),
        "event_count": len(event_ids),
        "event_digest": _event_digest(event_ids),
        "event_ids": event_ids,
        "file_custody": ledger.get("file_custody"),
    }


def _task_source_errors(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["task source snapshot is missing"]
    errors: list[str] = []
    if value.get("ok") is not True or value.get("error_count") != 0:
        errors.append("task source is invalid")
    event_ids = value.get("event_ids")
    if not isinstance(event_ids, list) or any(
        not re.fullmatch(r"[0-9a-f]{64}", str(event_id or "")) for event_id in (event_ids or [])
    ):
        errors.append("task source event ids are invalid")
        event_ids = []
    if len(event_ids) != len(set(event_ids)) or event_ids != sorted(event_ids):
        errors.append("task source event ids are not unique and sorted")
    if value.get("event_count") != len(event_ids):
        errors.append("task source event count mismatch")
    if value.get("event_digest") != _event_digest(event_ids):
        errors.append("task source event digest mismatch")
    errors.extend(_custody_errors(value.get("file_custody")))
    return errors


def _task_event_within_observation(
    entry: dict[str, Any],
    *,
    window_start: dt.datetime,
    observed_at: dt.datetime,
) -> bool:
    event_time = parse_iso(str(entry.get("timestamp") or ""))
    if event_time is None:
        return False
    return window_start <= event_time <= observed_at


_TRUSTED_EXECUTION_DIRS = tuple(Path(value) for value in ("/usr/bin", "/bin", "/usr/local/bin", "/opt/homebrew/bin"))


def _trusted_execution_path() -> str:
    return os.pathsep.join(str(path) for path in _TRUSTED_EXECUTION_DIRS if path.is_dir())


def _trusted_fixed_executable(name: str, *, system_only: bool = False) -> str | None:
    directories = _TRUSTED_EXECUTION_DIRS[:2] if system_only else _TRUSTED_EXECUTION_DIRS
    for directory in directories:
        candidate = directory / name
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            continue
        resolved = candidate.resolve()
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return str(resolved)
    return None


def _trusted_git_executable() -> str | None:
    return _trusted_fixed_executable("git", system_only=True)


def _trusted_tool_environment() -> dict[str, str]:
    allowed = {
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "JULES_API_KEY",
        "TMPDIR",
        "TZ",
    }
    environment = {name: value for name, value in os.environ.items() if name in allowed}
    account = pwd.getpwuid(os.getuid())
    environment.update(
        {
            "GH_NO_UPDATE_NOTIFIER": "1",
            "GH_PAGER": "",
            "GH_PROMPT_DISABLED": "1",
            "HOME": account.pw_dir,
            "LANG": "C",
            "LC_ALL": "C",
            "NO_COLOR": "1",
            "PAGER": "",
            "PATH": _trusted_execution_path(),
            "USER": account.pw_name,
        }
    )
    return environment


def _execute_fixed_argv(
    execution_argv: list[str],
    *,
    environment: dict[str, str],
    timeout: int = TRIAL_PREDICATE_TIMEOUT_SEC,
) -> tuple[int, str, str] | None:
    try:
        proc = subprocess.Popen(
            execution_argv,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            env=environment,
        )
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        return None
    except (OSError, subprocess.SubprocessError, UnboundLocalError):
        return None
    return proc.returncode, stdout or "", stderr or ""


def _run_trusted_tool_argv(
    name: str,
    argv: list[str],
    *,
    timeout: int = TRIAL_PREDICATE_TIMEOUT_SEC,
) -> tuple[int, str, str] | None:
    executable = _trusted_fixed_executable(name)
    if not executable:
        return None
    return _execute_fixed_argv(
        [executable, *argv],
        environment=_trusted_tool_environment(),
        timeout=timeout,
    )


def _run_predicate_argv(argv: list[str]) -> tuple[int, str, str] | None:
    if not argv:
        return None
    execution_argv = list(argv)
    environment = os.environ.copy()
    if argv[0] == "git":
        trusted_git = _trusted_git_executable()
        if not trusted_git:
            return None
        environment = {"LANG": "C", "LC_ALL": "C", "PATH": os.defpath}
        environment.update(
            {
                "GIT_ALLOW_PROTOCOL": "",
                "GIT_ATTR_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_SYSTEM": "/dev/null",
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_PAGER": "",
                "GIT_PROTOCOL_FROM_USER": "0",
                "GIT_TERMINAL_PROMPT": "0",
                "PAGER": "",
            }
        )
        git_prefix = [
            trusted_git,
            "--no-pager",
            "--no-optional-locks",
            "--no-replace-objects",
            "-c",
            "core.alternateRefsCommand=",
            "-c",
            "core.askPass=",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.pager=",
            "-c",
            "core.sshCommand=",
            "-c",
            "credential.helper=",
            "-c",
            "diff.external=",
            "-c",
            "format.pretty=medium",
            "-c",
            "http.proxy=",
            "-c",
            "log.showSignature=false",
            "-c",
            "protocol.allow=never",
            "-c",
            "protocol.ext.allow=never",
            "-c",
            "protocol.file.allow=never",
            "-c",
            "protocol.git.allow=never",
            "-c",
            "protocol.http.allow=never",
            "-c",
            "protocol.https.allow=never",
            "-c",
            "protocol.ssh.allow=never",
        ]
        if len(argv) >= 2 and argv[1] in {"log", "show"}:
            execution_argv = [
                *git_prefix,
                argv[1],
                "--format=medium",
                "--no-show-signature",
                "--no-ext-diff",
                "--no-textconv",
                *argv[2:],
            ]
        elif len(argv) >= 2 and argv[1] == "diff":
            execution_argv = [*git_prefix, argv[1], "--no-ext-diff", "--no-textconv", *argv[2:]]
        else:
            execution_argv = [*git_prefix, *argv[1:]]
    elif argv[0] == "gh":
        return _run_trusted_tool_argv("gh", argv[1:])
    elif argv[0] in {"test", "["}:
        executable = _trusted_fixed_executable(argv[0], system_only=True)
        if not executable:
            return None
        execution_argv[0] = executable
        environment = {"LANG": "C", "LC_ALL": "C", "PATH": _trusted_execution_path()}
    else:
        return None
    return _execute_fixed_argv(
        execution_argv,
        environment=environment,
    )


def _gh_read_only(argv: list[str]) -> bool:
    if len(argv) < 2 or argv[0] != "gh":
        return False

    def exact_options(
        values: list[str],
        *,
        value_options: set[str],
        flag_options: set[str],
        minimum_positionals: int,
        maximum_positionals: int,
    ) -> bool:
        positionals: list[str] = []
        index = 0
        while index < len(values):
            value = values[index]
            if value.startswith("--"):
                name, separator, attached = value.partition("=")
                if name in flag_options:
                    if separator:
                        return False
                    index += 1
                    continue
                if name not in value_options:
                    return False
                if separator:
                    if not attached:
                        return False
                    index += 1
                    continue
                index += 1
                if index >= len(values):
                    return False
                index += 1
                continue
            if value.startswith("-"):
                # No short option is needed for proof. Rejecting all of them also
                # rejects bundles such as ``-iXPOST`` instead of guessing how gh
                # will split the token.
                return False
            positionals.append(value)
            index += 1
        return minimum_positionals <= len(positionals) <= maximum_positionals

    if argv[1] == "api":
        return exact_options(
            argv[2:],
            value_options={"--jq"},
            flag_options={"--paginate", "--slurp"},
            minimum_positionals=1,
            maximum_positionals=1,
        )
    if len(argv) < 3:
        return False
    command = (argv[1], argv[2])
    specifications = {
        ("issue", "list"): (
            {
                "--app",
                "--assignee",
                "--author",
                "--json",
                "--jq",
                "--label",
                "--limit",
                "--mention",
                "--milestone",
                "--repo",
                "--search",
                "--state",
            },
            set(),
            0,
            0,
        ),
        ("issue", "view"): ({"--json", "--jq", "--repo", "--template"}, {"--comments"}, 0, 1),
        ("pr", "checks"): ({"--json", "--jq", "--repo"}, {"--required"}, 0, 1),
        ("pr", "list"): (
            {
                "--app",
                "--author",
                "--base",
                "--head",
                "--json",
                "--jq",
                "--label",
                "--limit",
                "--repo",
                "--search",
                "--state",
            },
            {"--draft"},
            0,
            0,
        ),
        ("pr", "view"): ({"--json", "--jq", "--repo", "--template"}, {"--comments"}, 0, 1),
        ("repo", "view"): ({"--json", "--jq", "--template"}, set(), 0, 1),
        ("run", "list"): (
            {
                "--branch",
                "--commit",
                "--created",
                "--event",
                "--json",
                "--jq",
                "--limit",
                "--repo",
                "--status",
                "--user",
                "--workflow",
            },
            set(),
            0,
            0,
        ),
        ("run", "view"): ({"--job", "--json", "--jq", "--repo", "--template"}, set(), 0, 1),
    }
    specification = specifications.get(command)
    if specification is None:
        return False
    value_options, flag_options, minimum_positionals, maximum_positionals = specification
    return exact_options(
        argv[3:],
        value_options=value_options,
        flag_options=flag_options,
        minimum_positionals=minimum_positionals,
        maximum_positionals=maximum_positionals,
    )


def _git_read_only(argv: list[str]) -> bool:
    if len(argv) < 2 or argv[0] != "git":
        return False
    subcommand = argv[1]
    if subcommand not in {"diff", "log", "ls-files", "merge-base", "rev-parse", "show", "status"}:
        return False
    forbidden_exact = {
        "-c",
        "-h",
        "-o",
        "-p",
        "-u",
        "-v",
        "--config-env",
        "--exec",
        "--exec-path",
        "--ext-diff",
        "--external-diff",
        "--format",
        "--help",
        "--output",
        "--pager",
        "--paginate",
        "--pretty",
        "--show-signature",
        "--textconv",
        "--upload-pack",
    }
    forbidden_prefixes = (
        "--config-env=",
        "--exec-path=",
        "--exec=",
        "--ext-diff=",
        "--external-diff=",
        "--format=",
        "--help=",
        "--output=",
        "--pager=",
        "--pretty=",
        "--show-signature=",
        "--textconv=",
        "--upload-pack=",
    )
    forbidden_abbreviations = (
        "--conf",
        "--exec",
        "--ext",
        "--for",
        "--h",
        "--out",
        "--pag",
        "--pre",
        "--show-s",
        "--textc",
        "--upl",
        "--v",
    )
    forbidden_attached_short = ("-c", "-h", "-o", "-p", "-u", "-v")
    for value in argv[2:]:
        if (
            value in forbidden_exact
            or value.startswith(forbidden_prefixes)
            or value.startswith(forbidden_abbreviations)
            or (len(value) > 2 and value.startswith(forbidden_attached_short))
        ):
            return False
        if "%G" in value:
            return False
    return True


def _extract_single_substitution(command: str) -> tuple[str, str | None] | None:
    start = command.find("$(")
    if start < 0:
        return command, None
    depth = 1
    quote = ""
    escaped = False
    index = start + 2
    while index < len(command):
        char = command[index]
        if escaped:
            escaped = False
        elif char == "\\" and quote != "'":
            escaped = True
        elif quote:
            if char == quote:
                quote = ""
        elif char in {"'", '"'}:
            quote = char
        elif command.startswith("$(", index):
            return None
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                break
        index += 1
    if depth != 0 or command.find("$(", index + 1) >= 0:
        return None
    inner = command[start + 2 : index]
    return f"{command[:start]}VALUE{command[index + 1 :]}", inner


def _has_unquoted_shell_control(command: str) -> bool:
    quote = ""
    escaped = False
    for char in command:
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote != "'":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char in ";|&<>`(){}\n\r":
            return True
    return bool(quote or escaped)


def _direct_observation_command(argv: list[str]) -> bool:
    if not argv:
        return False
    if argv[0] == "test":
        return True
    if argv[0] == "[":
        return len(argv) >= 2 and argv[-1] == "]"
    if _gh_read_only(argv):
        return True
    if argv[0] == "git":
        return _git_read_only(argv)
    return False


def _classify_observation_predicate(command: str) -> dict[str, Any] | None:
    extracted = _extract_single_substitution(command)
    if extracted is None:
        return None
    outer, inner = extracted
    if _has_unquoted_shell_control(outer):
        return None
    try:
        outer_argv = shlex.split(outer)
    except ValueError:
        return None
    if inner is None:
        return {"outer": outer_argv, "inner": None}
    if outer_argv.count("VALUE") != 1 or not outer_argv or outer_argv[0] not in {"test", "["}:
        return None
    if _has_unquoted_shell_control(inner):
        return None
    try:
        inner_argv = shlex.split(inner)
    except ValueError:
        return None
    if not _gh_read_only(inner_argv):
        return None
    return {"outer": outer_argv, "inner": inner_argv}


def _predicate_is_observation_only(command: str) -> bool:
    classified = _classify_observation_predicate(command)
    if classified is None:
        return False
    if classified["inner"] is not None:
        return True
    return _direct_observation_command(classified["outer"])


def _predicate_proof(command: str) -> dict[str, Any] | None:
    classified = _classify_observation_predicate(command)
    if classified is None:
        return None
    outer_argv = list(classified["outer"])
    results: list[dict[str, Any]] = []
    inner_argv = classified["inner"]
    if inner_argv is not None:
        inner_result = _run_predicate_argv(inner_argv)
        if inner_result is None or inner_result[0] != 0:
            return None
        inner_rc, inner_stdout, inner_stderr = inner_result
        outer_argv[outer_argv.index("VALUE")] = inner_stdout.strip()
        results.append({"returncode": inner_rc, "stdout": inner_stdout, "stderr": inner_stderr})
    elif not _direct_observation_command(outer_argv):
        return None
    outer_result = _run_predicate_argv(outer_argv)
    if outer_result is None or outer_result[0] != 0:
        return None
    outer_rc, outer_stdout, outer_stderr = outer_result
    results.append({"returncode": outer_rc, "stdout": outer_stdout, "stderr": outer_stderr})
    return {"predicate_hash": canonical_hash(command), "result_hash": canonical_hash(results)}


def _github_api_object(endpoint: str) -> dict[str, Any] | list[Any] | None:
    result = _run_trusted_tool_argv("gh", ["api", endpoint], timeout=30)
    if result is None or result[0] != 0:
        return None
    try:
        payload = json.loads(result[1] or "{}")
    except ValueError:
        return None
    return payload if isinstance(payload, (dict, list)) else None


def _github_api_proof(endpoint: str) -> dict[str, Any] | None:
    payload = _github_api_object(endpoint)
    if payload is None:
        return None
    return {"endpoint_hash": canonical_hash(endpoint), "object_hash": canonical_hash(payload)}


def _exact_key_in_text(value: Any, key: str) -> bool:
    if not isinstance(value, str) or not key:
        return False
    boundary = r"A-Za-z0-9._/-"
    return re.search(rf"(?<![{boundary}]){re.escape(key)}(?![{boundary}])", value) is not None


def _json_contains_exact_value(value: Any, expected: str) -> bool:
    if isinstance(value, dict):
        return expected in value or any(_json_contains_exact_value(item, expected) for item in value.values())
    if isinstance(value, list):
        return any(_json_contains_exact_value(item, expected) for item in value)
    return isinstance(value, str) and value == expected


def _content_has_exact_anchor(payload: dict[str, Any], anchor: str) -> bool:
    if not anchor or payload.get("encoding") != "base64" or not isinstance(payload.get("content"), str):
        return False
    try:
        encoded = re.sub(rb"\s+", b"", payload["content"].encode("ascii", "strict"))
        decoded = base64.b64decode(encoded, validate=True)
    except (UnicodeError, ValueError):
        return False
    try:
        value = json.loads(decoded)
    except (UnicodeError, ValueError):
        try:
            text = decoded.decode("utf-8", "strict")
        except UnicodeError:
            return False
        return any(line.strip() == anchor for line in text.splitlines())
    return _json_contains_exact_value(value, anchor)


def _receipt_target_proof(target: str) -> dict[str, Any] | None:
    git_match = re.fullmatch(r"git:(?P<repo>[^/:]+/[^:]+):(?P<path>[^#\s]+)(?:#(?P<anchor>\S+))?", target)
    if git_match:
        repo = git_match.group("repo")
        path = git_match.group("path")
        endpoint = f"repos/{repo}/contents/{path}"
        payload = _github_api_object(endpoint)
        if not isinstance(payload, dict):
            return None
        object_id = str(payload.get("sha") or "")
        if not object_id:
            return None
        anchor = str(git_match.group("anchor") or "")
        if anchor and not _content_has_exact_anchor(payload, anchor):
            return None
        return {
            "target_hash": canonical_hash(target),
            "object_hash": canonical_hash(
                {"repo": repo, "path": path, "object_id": object_id, "anchor": anchor or None}
            ),
        }

    declared = re.fullmatch(
        r"github:(?P<repo>[^/:]+/[^:]+):(?P<kind>pull-request|issue):(?P<key>[A-Za-z0-9._/-]+)",
        target,
    )
    if declared:
        repo = declared.group("repo")
        kind = declared.group("kind")
        key = declared.group("key")
        if kind == "pull-request":
            result = _run_trusted_tool_argv(
                "gh",
                [
                    "pr",
                    "list",
                    "--repo",
                    repo,
                    "--state",
                    "merged",
                    "--search",
                    f"{key} in:body",
                    "--json",
                    "number,url,title,body,state,mergedAt,mergeCommit",
                ],
                timeout=30,
            )
        else:
            result = _run_trusted_tool_argv(
                "gh",
                [
                    "issue",
                    "list",
                    "--repo",
                    repo,
                    "--state",
                    "closed",
                    "--search",
                    f"{key} in:title",
                    "--json",
                    "number,url,title,body,state,closedAt,stateReason",
                ],
                timeout=30,
            )
        try:
            objects = json.loads(result[1] or "[]") if result is not None and result[0] == 0 else []
        except ValueError:
            objects = []
        if not isinstance(objects, list):
            return None
        if kind == "pull-request":
            exact = [
                item
                for item in objects
                if isinstance(item, dict)
                and _exact_key_in_text(item.get("body"), key)
                and str(item.get("state") or "").upper() == "MERGED"
                and bool(item.get("mergedAt"))
                and isinstance(item.get("mergeCommit"), dict)
                and bool(item["mergeCommit"].get("oid"))
            ]
        else:
            exact = [
                item
                for item in objects
                if isinstance(item, dict)
                and _exact_key_in_text(item.get("title"), key)
                and str(item.get("state") or "").upper() == "CLOSED"
                and bool(item.get("closedAt"))
            ]
        if not exact:
            return None
        return {"target_hash": canonical_hash(target), "object_hash": canonical_hash(exact)}

    parsed = urlparse(target)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or parsed.query or parsed.fragment:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 4:
        return None
    repo = f"{parts[0]}/{parts[1]}"
    kind = parts[2]
    key = parts[3]
    endpoint = ""
    validator = ""
    if kind == "issues" and key.isdigit() and len(parts) == 4:
        endpoint = f"repos/{repo}/issues/{key}"
        validator = "closed_issue"
    elif kind == "pull" and key.isdigit() and len(parts) == 4:
        endpoint = f"repos/{repo}/pulls/{key}"
        validator = "merged_pull"
    elif kind == "commit" and len(parts) == 4:
        endpoint = f"repos/{repo}/commits/{key}"
        validator = "commit"
    elif kind == "actions" and len(parts) >= 5 and parts[3] == "runs" and parts[4].isdigit():
        if len(parts) != 5:
            return None
        endpoint = f"repos/{repo}/actions/runs/{parts[4]}"
        validator = "successful_run"
    elif kind == "actions" and len(parts) >= 5 and parts[3] == "workflows":
        return None
    elif kind in {"blob", "tree"}:
        # A browser URL does not delimit a slash-bearing ref from its path.
        # Proving only the commit/ref would let a nonexistent path count as a
        # durable receipt. Require the unambiguous ``git:owner/repo:path`` form,
        # which resolves the exact contents object above.
        return None
    if not endpoint:
        return None
    payload = _github_api_object(endpoint)
    if not isinstance(payload, dict):
        return None
    if validator == "closed_issue" and not (
        str(payload.get("state") or "").lower() == "closed" and bool(payload.get("closed_at"))
    ):
        return None
    if validator == "merged_pull" and not (bool(payload.get("merged_at")) and bool(payload.get("merge_commit_sha"))):
        return None
    if validator == "commit" and not str(payload.get("sha") or "").startswith(key):
        return None
    if validator == "successful_run" and not (
        str(payload.get("status") or "").lower() == "completed"
        and str(payload.get("conclusion") or "").lower() == "success"
        and str(payload.get("id") or "") == parts[4]
    ):
        return None
    return {
        "target_hash": canonical_hash(target),
        "endpoint_hash": canonical_hash(endpoint),
        "object_hash": canonical_hash(payload),
    }


def _prove_terminal_event(entry: dict[str, Any]) -> dict[str, Any] | None:
    task = {"predicate": entry.get("predicate"), "receipt_target": entry.get("receipt_target")}
    log = {"output": "present" if entry.get("output_present") else ""}
    if not _typed_terminal_event(task, log):
        return None
    predicate = _predicate_proof(str(entry.get("predicate") or ""))
    receipt = _receipt_target_proof(str(entry.get("receipt_target") or ""))
    if predicate is None or receipt is None:
        return None
    return {
        "event_id": entry["event_id"],
        "proof_hash": canonical_hash({"predicate": predicate, "receipt": receipt}),
    }


def _jules_last_active_at(raw: str, observed_at: dt.datetime) -> dt.datetime | None:
    match = re.search(r"(?P<age>(?:(?:\d+)[dhms])+\s+ago|just now)\s*$", raw, re.IGNORECASE)
    if not match:
        return None
    age = match.group("age").lower()
    if age == "just now":
        return observed_at
    seconds = 0
    for amount, unit in re.findall(r"(\d+)([dhms])", age):
        seconds += int(amount) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]
    return observed_at - dt.timedelta(seconds=seconds)


def _prove_session_event(
    entry: dict[str, Any],
    *,
    window_start: dt.datetime | None = None,
    observed_at: dt.datetime | None = None,
    require_active: bool = True,
) -> dict[str, Any] | None:
    provider = str(entry.get("agent") or "").strip()
    session_id = str(entry.get("session_id") or "").strip()
    event_time = parse_iso(str(entry.get("timestamp") or ""))
    if window_start is None or observed_at is None or event_time is None:
        return None
    if not window_start <= event_time <= observed_at:
        return None
    if provider == "jules" and session_id.isdigit() and len(session_id) >= 12:
        cli_src = Path(__file__).resolve().parents[1] / "cli" / "src"
        if str(cli_src) not in sys.path:
            sys.path.insert(0, str(cli_src))
        try:
            from limen.jules_remote import classify_jules_remote_status, parse_jules_remote_sessions
        except (ImportError, ModuleNotFoundError):
            return None
        remote = _run_trusted_tool_argv("jules", ["remote", "list", "--session"], timeout=90)
        if remote is None or remote[0] != 0:
            return None
        session = parse_jules_remote_sessions(remote[1]).get(session_id)
        if session is None:
            return None
        status = session.status
        if status == "unknown":
            without_activity = re.sub(
                r"(?:(?:(?:\d+)[dhms])+\s+ago|just now)\s*$",
                "",
                session.raw,
                flags=re.IGNORECASE,
            ).rstrip()
            columns = re.split(r"\s{2,}", without_activity)
            status = classify_jules_remote_status(columns[-1] if columns else "")
        last_active_at = _jules_last_active_at(session.raw, observed_at)
        if require_active and (
            status not in {"planning", "in_progress"}
            or last_active_at is None
            or not window_start <= last_active_at <= observed_at
        ):
            return None
        return {
            "event_id": entry["event_id"],
            "provider": provider,
            "proof_hash": canonical_hash(
                {
                    "provider": provider,
                    "session_id": session_id,
                    "event_time": event_time.isoformat(timespec="seconds"),
                    "observed_at": observed_at.isoformat(timespec="seconds"),
                }
            ),
        }
    if provider == "github_actions" and "/actions/runs/" in session_id:
        parsed = urlparse(session_id)
        parts = [part for part in parsed.path.split("/") if part]
        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() != "github.com"
            or len(parts) != 5
            or parts[2:4] != ["actions", "runs"]
            or not parts[4].isdigit()
        ):
            return None
        endpoint = f"repos/{parts[0]}/{parts[1]}/actions/runs/{parts[4]}"
        payload = _github_api_object(endpoint)
        if not isinstance(payload, dict):
            return None
        status = str(payload.get("status") or "").lower()
        started_at = parse_iso(str(payload.get("run_started_at") or payload.get("created_at") or ""))
        activity_at = parse_iso(str(payload.get("updated_at") or ""))
        active_statuses = {"in_progress", "pending", "queued", "requested", "waiting"}
        if (
            str(payload.get("id") or "") != parts[4]
            or started_at is None
            or not window_start <= started_at <= observed_at + dt.timedelta(seconds=TRIAL_CLOCK_TOLERANCE_SEC)
            or (
                require_active
                and (
                    status not in active_statuses
                    or activity_at is None
                    or not window_start <= activity_at <= observed_at + dt.timedelta(seconds=TRIAL_CLOCK_TOLERANCE_SEC)
                )
            )
        ):
            return None
        return {
            "event_id": entry["event_id"],
            "provider": provider,
            "proof_hash": canonical_hash(
                {
                    "endpoint": endpoint,
                    "run_id": str(payload.get("id")),
                    "html_url": str(payload.get("html_url") or ""),
                    "head_sha": str(payload.get("head_sha") or ""),
                    "head_branch": str(payload.get("head_branch") or ""),
                    "created_at": str(payload.get("created_at") or ""),
                    "run_started_at": str(payload.get("run_started_at") or ""),
                    "event_time": event_time.isoformat(timespec="seconds"),
                    "observed_at": observed_at.isoformat(timespec="seconds"),
                }
            ),
        }
    return None


def task_event_snapshot(
    captured_at: dt.datetime,
    *,
    ledger: dict[str, Any] | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    captured_at = captured_at.astimezone(dt.timezone.utc).replace(microsecond=0)
    source = ledger or _load_task_event_ledger(path)
    snapshots: dict[str, dict[str, Any]] = {}
    all_ids: list[str] = []
    for name in ("value_done", "owner_blocked", "session_seams"):
        event_ids = [
            event_id for timestamp, event_id in (source.get("streams") or {}).get(name, []) if timestamp <= captured_at
        ]
        all_ids.extend(event_ids)
        snapshots[name] = {"count": len(event_ids), "digest": _event_digest(event_ids)}
    return {
        "schema_version": TRIAL_TASK_EVENT_SCHEMA_VERSION,
        "captured_at": captured_at.isoformat(timespec="seconds"),
        "ok": source.get("ok") is True,
        "error_count": _bounded_int(source.get("error_count")),
        "source_digest": _event_digest(all_ids),
        **snapshots,
    }


def _cursor_digest(cursor: dict[str, Any]) -> str:
    cli_src = Path(__file__).resolve().parents[1] / "cli" / "src"
    if str(cli_src) not in sys.path:
        sys.path.insert(0, str(cli_src))
    try:
        from limen.prompt_corpus import cursor_digest

        return str(cursor_digest(cursor))
    except Exception:
        return ""


def _cursor_semantic(cursor: dict[str, Any]) -> dict[str, Any]:
    cli_src = Path(__file__).resolve().parents[1] / "cli" / "src"
    if str(cli_src) not in sys.path:
        sys.path.insert(0, str(cli_src))
    try:
        from limen.prompt_corpus import cursor_semantic

        value = cursor_semantic(cursor)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _prompt_paths(source: Path) -> dict[str, Path]:
    return {
        "events": source.parent / "prompt-events.jsonl",
        "outcomes": source.parent / "prompt-atom-outcomes.jsonl",
        "cursor": source.parent / "source-cursor.json",
        "snapshot": source,
    }


def _operator_count_from_event_bytes(payload: bytes) -> tuple[int, int]:
    rows, errors = _jsonl_bytes(payload)
    occurrence_order: list[str] = []
    occurrences: dict[str, dict[str, Any]] = {}
    for row in rows:
        occurrence = row.get("occurrence")
        atoms = row.get("atoms")
        if not isinstance(occurrence, dict) or not isinstance(atoms, list):
            errors += 1
            continue
        occurrence_id = str(occurrence.get("occurrence_id") or "")
        revision_of = str(row.get("revision_of") or "")
        if not occurrence_id:
            errors += 1
            continue
        if occurrence_id in occurrences and revision_of != occurrence_id:
            errors += 1
            continue
        if revision_of and revision_of not in occurrences:
            errors += 1
            continue
        if occurrence_id not in occurrences:
            occurrence_order.append(occurrence_id)
        occurrences[occurrence_id] = occurrence
    count = sum(1 for occurrence_id in occurrence_order if occurrences[occurrence_id].get("authority") == "operator")
    return count, errors


def _operator_count_at_custody(path: Path, custody: dict[str, Any]) -> tuple[int, int]:
    if not _prefix_matches(path, custody):
        return 0, 1
    payload, _, file_errors = _read_trusted_regular_file(path, label="prompt operator journal")
    if file_errors or payload is None:
        return 0, 1
    return _operator_count_from_event_bytes(payload[: int(custody["size"])])


def _prompt_scope_exact(snapshot: dict[str, Any], cursor: dict[str, Any]) -> bool:
    scope = snapshot.get("source_scope") if isinstance(snapshot.get("source_scope"), dict) else {}
    cursor_scope = _cursor_semantic(cursor) if isinstance(cursor, dict) else {}
    families = scope.get("source_families") if isinstance(scope.get("source_families"), dict) else {}
    families_exact = bool(families) and all(
        isinstance(item, dict)
        and all(
            _strict_nonnegative_int(item.get(key))
            for key in ("pending", "errors", "unsupported", "converged", "discovered")
        )
        and item.get("pending") == 0
        and item.get("errors") == 0
        and item.get("unsupported") == 0
        and item.get("converged") == item.get("discovered")
        for item in families.values()
    )
    cursor_families = (
        cursor_scope.get("source_families") if isinstance(cursor_scope.get("source_families"), dict) else {}
    )
    cursor_families_exact = bool(cursor_families) and all(
        isinstance(item, dict)
        and all(
            _strict_nonnegative_int(item.get(key))
            for key in ("pending", "errors", "unsupported", "converged", "discovered")
        )
        and item.get("pending") == 0
        and item.get("errors") == 0
        and item.get("unsupported") == 0
        and item.get("converged") == item.get("discovered")
        for item in cursor_families.values()
    )
    compared_keys = (
        "scope",
        "target_scope",
        "all_baseline_complete",
        "pending_files",
        "source_errors",
        "unsupported_source_count",
        "unresolved_unit_count",
        "adapter_gaps",
        "source_families",
    )
    scopes_agree = all(scope.get(key) == cursor_scope.get(key) for key in compared_keys)
    source_error_count = scope.get("source_error_count", len(scope.get("source_errors") or []))
    return bool(
        scopes_agree
        and scope.get("scope") == "all"
        and scope.get("target_scope") == "all"
        and scope.get("all_baseline_complete") is True
        and _strict_nonnegative_int(scope.get("pending_files"))
        and scope.get("pending_files") == 0
        and _strict_nonnegative_int(source_error_count)
        and source_error_count == 0
        and _strict_nonnegative_int(scope.get("unsupported_source_count"))
        and scope.get("unsupported_source_count") == 0
        and _strict_nonnegative_int(scope.get("unresolved_unit_count"))
        and scope.get("unresolved_unit_count") == 0
        and not (scope.get("adapter_gaps") or [])
        and families_exact
        and cursor_scope.get("scope") == "all"
        and cursor_scope.get("target_scope") == "all"
        and cursor_scope.get("all_baseline_complete") is True
        and _strict_nonnegative_int(cursor_scope.get("pending_files"))
        and cursor_scope.get("pending_files") == 0
        and not (cursor_scope.get("source_errors") or [])
        and _strict_nonnegative_int(cursor_scope.get("unsupported_source_count"))
        and cursor_scope.get("unsupported_source_count") == 0
        and _strict_nonnegative_int(cursor_scope.get("unresolved_unit_count"))
        and cursor_scope.get("unresolved_unit_count") == 0
        and not (cursor_scope.get("adapter_gaps") or [])
        and cursor_families_exact
    )


def prompt_authority_snapshot(
    captured_at: dt.datetime,
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    captured_at = captured_at.astimezone(dt.timezone.utc).replace(microsecond=0)
    source = path or PROMPT_ATOM_SNAPSHOT
    paths = _prompt_paths(source)
    path_errors = [
        error
        for name, path_value in paths.items()
        for error in _trusted_canonical_file_errors(
            path_value,
            label=f"prompt {name} source",
        )
    ]
    payloads: dict[str, bytes] = {}
    for name, path_value in paths.items():
        payload, _, file_errors = _read_trusted_regular_file(path_value, label=f"prompt {name} source")
        if not file_errors and payload is not None:
            payloads[name] = payload
    try:
        snapshot_value = json.loads(payloads.get("snapshot", b"{}"))
    except (UnicodeError, ValueError):
        snapshot_value = {}
    try:
        cursor_value = json.loads(payloads.get("cursor", b"{}"))
    except (UnicodeError, ValueError):
        cursor_value = {}
    snapshot = snapshot_value if isinstance(snapshot_value, dict) else {}
    cursor = cursor_value if isinstance(cursor_value, dict) else {}
    errors = len(path_errors)
    if not snapshot:
        errors += 1
    if not cursor:
        errors += 1
    coverage = snapshot.get("coverage") if isinstance(snapshot.get("coverage"), dict) else {}
    operator_value = coverage.get("operator_occurrences")
    operator_valid = _strict_nonnegative_int(operator_value)
    if not operator_valid:
        errors += 1
    validation_ok = bool((snapshot.get("validation") or {}).get("ok"))
    exact = not path_errors and validation_ok and _prompt_scope_exact(snapshot, cursor)
    expected_cursor_digest = str(snapshot.get("source_cursor_digest") or "")
    actual_cursor_digest = _cursor_digest(cursor) if cursor else ""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_cursor_digest) or expected_cursor_digest != actual_cursor_digest:
        errors += 1
        exact = False
    signatures = snapshot.get("journal_signatures") if isinstance(snapshot.get("journal_signatures"), dict) else {}
    for name in ("events", "outcomes", "cursor"):
        signature = signatures.get(name) if isinstance(signatures.get(name), dict) else {}
        try:
            metadata = paths[name].lstat()
            signature_ok = (
                _strict_nonnegative_int(signature.get("size"))
                and signature.get("size") == metadata.st_size
                and _strict_nonnegative_int(signature.get("mtime_ns"))
                and signature.get("mtime_ns") == metadata.st_mtime_ns
            )
        except OSError:
            signature_ok = False
        if not signature_ok:
            errors += 1
            exact = False
    source_custody = {name: _file_custody(path_value) for name, path_value in paths.items()}
    event_bytes = payloads.get("events", b"")
    journal_operator_count, journal_errors = _operator_count_from_event_bytes(event_bytes)
    if journal_errors or not operator_valid or journal_operator_count != operator_value:
        errors += max(1, journal_errors)
        exact = False
    last_scan_at = parse_iso(str(cursor.get("last_scan_at") or ""))
    age_sec: int | None = None
    fresh = False
    if last_scan_at:
        age_sec = int((captured_at - last_scan_at).total_seconds())
        fresh = -TRIAL_CLOCK_TOLERANCE_SEC <= age_sec <= TRIAL_PROMPT_MAX_AGE_SEC
    else:
        errors += 1
    return {
        "schema_version": TRIAL_PROMPT_AUTHORITY_SCHEMA_VERSION,
        "captured_at": captured_at.isoformat(timespec="seconds"),
        "present": bool(snapshot and cursor),
        "validation_ok": validation_ok,
        "exact_all": exact,
        "fresh": fresh,
        "last_scan_at": last_scan_at.isoformat(timespec="seconds") if last_scan_at else None,
        "age_sec": age_sec,
        "operator_occurrences": int(operator_value) if operator_valid else 0,
        "snapshot_digest": canonical_hash(snapshot) if snapshot else "",
        "cursor_digest": actual_cursor_digest,
        "source_custody": source_custody,
        "error_count": errors,
    }


def _task_snapshot_errors(value: Any, captured_at: dt.datetime | None = None) -> list[str]:
    if not isinstance(value, dict):
        return ["task event snapshot is missing"]
    errors: list[str] = []
    if value.get("schema_version") != TRIAL_TASK_EVENT_SCHEMA_VERSION:
        errors.append("task event schema mismatch")
    if value.get("ok") is not True or _bounded_int(value.get("error_count")) != 0:
        errors.append("task event source is not valid")
    actual_time = parse_iso(str(value.get("captured_at") or ""))
    if captured_at and actual_time != captured_at:
        errors.append("task event capture time mismatch")
    for key in ("source_digest",):
        if not re.fullmatch(r"[0-9a-f]{64}", str(value.get(key) or "")):
            errors.append(f"{key} is not sha256")
    for name in ("value_done", "owner_blocked", "session_seams"):
        stream = value.get(name) if isinstance(value.get(name), dict) else {}
        if not isinstance(stream.get("count"), int) or _bounded_int(stream.get("count")) != stream.get("count"):
            errors.append(f"{name} count is invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", str(stream.get("digest") or "")):
            errors.append(f"{name} digest is not sha256")
    return errors


def _prompt_snapshot_errors(value: Any, captured_at: dt.datetime | None = None) -> list[str]:
    if not isinstance(value, dict):
        return ["prompt authority snapshot is missing"]
    errors: list[str] = []
    if value.get("schema_version") != TRIAL_PROMPT_AUTHORITY_SCHEMA_VERSION:
        errors.append("prompt authority schema mismatch")
    actual_time = parse_iso(str(value.get("captured_at") or ""))
    if captured_at and actual_time != captured_at:
        errors.append("prompt authority capture time mismatch")
    last_scan_at = parse_iso(str(value.get("last_scan_at") or ""))
    if actual_time is None or last_scan_at is None:
        errors.append("prompt authority scan time is invalid")
        computed_age = None
    else:
        computed_age = int((actual_time - last_scan_at).total_seconds())
        if value.get("age_sec") != computed_age:
            errors.append("prompt authority age is not derived from scan time")
        computed_fresh = -TRIAL_CLOCK_TOLERANCE_SEC <= computed_age <= TRIAL_PROMPT_MAX_AGE_SEC
        if value.get("fresh") is not computed_fresh:
            errors.append("prompt authority freshness claim is invalid")
    if not all(value.get(key) is True for key in ("present", "validation_ok", "exact_all", "fresh")):
        errors.append("prompt authority is not fresh exact all/all")
    if not _strict_nonnegative_int(value.get("error_count")) or value.get("error_count") != 0:
        errors.append("prompt authority has source errors")
    if not _strict_nonnegative_int(value.get("operator_occurrences")):
        errors.append("operator occurrence count is invalid")
    for key in ("snapshot_digest", "cursor_digest"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(value.get(key) or "")):
            errors.append(f"prompt {key} is not sha256")
    custody = value.get("source_custody") if isinstance(value.get("source_custody"), dict) else {}
    for name in ("events", "outcomes", "cursor", "snapshot"):
        for error in _custody_errors(custody.get(name)):
            errors.append(f"prompt {name} {error}")
    return errors


def _active_marker_errors(marker: Any) -> list[str]:
    if not isinstance(marker, dict):
        return ["active trial marker is missing"]
    errors: list[str] = []
    if marker.get("schema_version") != TRIAL_MARKER_SCHEMA_VERSION:
        errors.append("trial marker schema mismatch")
    if marker.get("active") is not True:
        errors.append("trial marker is not active")
    if not _content_hash_valid(marker):
        errors.append("trial marker content hash mismatch")
    else:
        errors.extend(_trial_anchor_errors(marker))
    start = parse_iso(str(marker.get("window_start") or ""))
    end = parse_iso(str(marker.get("window_end") or ""))
    started_at = parse_iso(str(marker.get("started_at") or ""))
    if not start or not end or started_at != start:
        errors.append("trial marker timestamps are invalid")
    elif int((end - start).total_seconds()) != TRIAL_DURATION_SEC:
        errors.append("trial marker is not exactly eight hours")
    if not re.fullmatch(r"[0-9a-f]{64}", str(marker.get("evaluator_hash") or "")):
        errors.append("trial marker evaluator hash is unavailable")
    elif marker.get("evaluator_hash") != evaluator_hash():
        errors.append("trial marker evaluator changed during the window")
    if not _strict_nonnegative_int(marker.get("monotonic_start_ns")):
        errors.append("trial marker monotonic start is invalid")
    baseline = marker.get("baseline") if isinstance(marker.get("baseline"), dict) else {}
    errors.extend(_task_source_errors(baseline.get("task_source")))
    errors.extend(_prompt_snapshot_errors(baseline.get("prompt_authority"), start))
    for name, path in (("watch_ledger", RECEIPT_JSONL), ("observation_ledger", TRIAL_OBSERVATION_PATH)):
        custody = baseline.get(name)
        errors.extend(f"{name} {error}" for error in _custody_errors(custody))
        allow_missing = isinstance(custody, dict) and custody.get("present") is False
        path_errors = _trusted_canonical_file_errors(
            path,
            label=name,
            allow_missing=allow_missing,
        )
        errors.extend(path_errors)
        if not path_errors and isinstance(custody, dict) and not _prefix_matches(path, custody):
            errors.append(f"{name} prefix was rewritten or truncated")
    return errors


def _terminal_marker_errors(marker: Any, receipt: dict[str, Any]) -> list[str]:
    if not isinstance(marker, dict):
        return ["terminal trial marker is missing"]
    errors: list[str] = []
    if marker.get("schema_version") != TRIAL_MARKER_SCHEMA_VERSION or marker.get("active") is not False:
        errors.append("terminal trial marker schema/state mismatch")
    if not _content_hash_valid(marker):
        errors.append("terminal trial marker content hash mismatch")
    active_marker = marker.get("active_marker") if isinstance(marker.get("active_marker"), dict) else {}
    errors.extend(_active_marker_errors(active_marker))
    if marker.get("trial_id") != active_marker.get("content_hash"):
        errors.append("terminal marker trial id mismatch")
    if marker.get("receipt_content_hash") != receipt.get("content_hash"):
        errors.append("terminal marker receipt content hash mismatch")
    if marker.get("receipt_input_hash") != receipt.get("input_hash"):
        errors.append("terminal marker receipt input hash mismatch")
    if marker.get("receipt_pass") is not receipt.get("pass"):
        errors.append("terminal marker receipt verdict mismatch")
    return errors


def start_trial() -> tuple[dict[str, Any], bool]:
    marker_path = TRIAL_WINDOW_PATH
    reference = utc_now().astimezone(dt.timezone.utc).replace(microsecond=0)
    lock_path = marker_path.with_suffix(marker_path.suffix + ".lock")
    prompt_paths = _prompt_paths(PROMPT_ATOM_SNAPSHOT)
    configured_paths = {
        "trial task source": (TASKS_PATH, False),
        "trial watch ledger": (RECEIPT_JSONL, True),
        "trial watch ledger lock": (RECEIPT_JSONL.with_suffix(RECEIPT_JSONL.suffix + ".lock"), True),
        "trial observation ledger": (TRIAL_OBSERVATION_PATH, True),
        "trial receipt": (TRIAL_PATH, True),
        "trial marker": (marker_path, True),
        "trial marker lock": (lock_path, True),
        **{f"prompt {name} source": (path, False) for name, path in prompt_paths.items()},
    }
    path_errors = [
        error
        for label, (path, allow_missing) in configured_paths.items()
        for error in _trusted_canonical_file_errors(
            path,
            label=label,
            allow_missing=allow_missing,
        )
    ]
    if path_errors:
        raise TrialContractError("trial source paths are not canonical: " + "; ".join(sorted(set(path_errors))))
    lock_flags = os.O_RDWR | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    lock_fd = os.open(lock_path, lock_flags, 0o600)
    with os.fdopen(lock_fd, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        existing, existing_errors = _load_trusted_json(
            marker_path,
            label="trial marker",
            allow_missing=True,
        )
        if existing_errors:
            raise TrialContractError("; ".join(existing_errors))
        if existing.get("active") is True:
            raise TrialContractError("an unattended trial is already active")
        task_ledger = _load_task_event_ledger()
        task_source = _task_source_snapshot(task_ledger)
        prompt_authority = prompt_authority_snapshot(reference)
        baseline_errors = [
            *_task_source_errors(task_source),
            *_prompt_snapshot_errors(prompt_authority, reference),
        ]
        if baseline_errors:
            raise TrialContractError("trial baseline is not authoritative: " + "; ".join(sorted(set(baseline_errors))))
        current_evaluator_hash = evaluator_hash()
        if not re.fullmatch(r"[0-9a-f]{64}", current_evaluator_hash):
            raise TrialContractError("trial evaluator dependency set is unavailable")
        marker: dict[str, Any] = {
            "schema_version": TRIAL_MARKER_SCHEMA_VERSION,
            "active": True,
            "started_at": reference.isoformat(timespec="seconds"),
            "window_start": reference.isoformat(timespec="seconds"),
            "window_end": (reference + dt.timedelta(seconds=TRIAL_DURATION_SEC)).isoformat(timespec="seconds"),
            "monotonic_start_ns": time.monotonic_ns(),
            "evaluator_hash": current_evaluator_hash,
            "baseline": {
                "task_source": task_source,
                "prompt_authority": prompt_authority,
                "watch_ledger": _file_custody(RECEIPT_JSONL),
                "observation_ledger": _file_custody(TRIAL_OBSERVATION_PATH),
            },
        }
        marker["content_hash"] = canonical_hash(marker)
        _prepare_observation_custody(marker)
        _write_trial_anchor(marker)
        _write_json_atomic(marker_path, marker)
        return marker, True


def _proof_list_errors(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        return [f"{label} proofs are missing"]
    errors: list[str] = []
    seen: set[str] = set()
    for proof in value:
        if not isinstance(proof, dict):
            errors.append(f"{label} proof is not an object")
            continue
        event_id = str(proof.get("event_id") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", event_id):
            errors.append(f"{label} proof event id is invalid")
        if event_id in seen:
            errors.append(f"{label} proof event id is duplicated")
        seen.add(event_id)
        if not re.fullmatch(r"[0-9a-f]{64}", str(proof.get("proof_hash") or "")):
            errors.append(f"{label} proof hash is invalid")
        if label == "session" and proof.get("provider") not in {"jules", "github_actions"}:
            errors.append("session proof provider is unsupported")
    return errors


def _watch_row_binding(value: dict[str, Any]) -> dict[str, Any]:
    status, alerts = evaluate(value)
    return {
        "record_hash": canonical_hash(value),
        "timestamp": str(value.get("timestamp") or ""),
        "status": status,
        "alert_count": len(alerts),
        "alert_digest": canonical_hash(alerts),
    }


def _watch_span_status(value: list[dict[str, Any]]) -> str:
    statuses = {str(item.get("status") or "") for item in value}
    if "alert" in statuses:
        return "alert"
    if "blocked" in statuses:
        return "blocked"
    return "ok"


def _observation_errors(value: Any, *, marker: dict[str, Any]) -> list[str]:
    if not isinstance(value, dict):
        return ["trial observation is missing"]
    errors: list[str] = []
    if value.get("schema_version") != TRIAL_OBSERVATION_SCHEMA_VERSION:
        errors.append("trial observation schema mismatch")
    if value.get("trial_id") != marker.get("content_hash"):
        errors.append("trial observation id mismatch")
    if not _strict_nonnegative_int(value.get("sequence")) or value.get("sequence") < 1:
        errors.append("trial observation sequence is invalid")
    if not _content_hash_valid(value):
        errors.append("trial observation content hash mismatch")
    observed_at = parse_iso(str(value.get("observed_at") or ""))
    if observed_at is None:
        errors.append("trial observation timestamp is invalid")
    if not _strict_nonnegative_int(value.get("monotonic_ns")):
        errors.append("trial observation monotonic clock is invalid")
    errors.extend(_task_source_errors(value.get("task_source")))
    errors.extend(_prompt_snapshot_errors(value.get("prompt_authority"), observed_at))
    watch_span = value.get("watch_span") if isinstance(value.get("watch_span"), list) else []
    if not watch_span:
        errors.append("trial observation watch span is missing")
    for binding in watch_span:
        if not isinstance(binding, dict):
            errors.append("trial observation watch binding is invalid")
            continue
        if not re.fullmatch(r"[0-9a-f]{64}", str(binding.get("record_hash") or "")):
            errors.append("trial observation watch record hash is invalid")
        if parse_iso(str(binding.get("timestamp") or "")) is None:
            errors.append("trial observation watch timestamp is invalid")
        if binding.get("status") not in {"ok", "blocked", "alert"}:
            errors.append("trial observation watch status is invalid")
        if not _strict_nonnegative_int(binding.get("alert_count")):
            errors.append("trial observation watch alert count is invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", str(binding.get("alert_digest") or "")):
            errors.append("trial observation watch alert digest is invalid")
    expected_alert_count = sum(_bounded_int(item.get("alert_count")) for item in watch_span if isinstance(item, dict))
    if value.get("status") != _watch_span_status([item for item in watch_span if isinstance(item, dict)]):
        errors.append("trial observation status is invalid")
    if not _strict_nonnegative_int(value.get("alert_count")) or value.get("alert_count") != expected_alert_count:
        errors.append("trial observation alert count is invalid")
    handoff = value.get("handoff") if isinstance(value.get("handoff"), dict) else {}
    if not isinstance(handoff.get("ok"), bool) or not isinstance(handoff.get("check_returncode"), int):
        errors.append("trial observation handoff proof is incomplete")
    errors.extend(f"handoff {error}" for error in _custody_errors(handoff.get("source_custody")))
    if handoff.get("ok") is True and (handoff.get("source_custody") or {}).get("present") is not True:
        errors.append("trial observation passing handoff has no durable source receipt")
    errors.extend(f"watch {error}" for error in _custody_errors(value.get("watch_custody")))
    errors.extend(_proof_list_errors(value.get("value_proofs"), "value"))
    errors.extend(_proof_list_errors(value.get("blocker_proofs"), "blocker"))
    errors.extend(_proof_list_errors(value.get("session_proofs"), "session"))
    return errors


def _read_observation_chain(
    marker: dict[str, Any],
    *,
    allow_unbound_watch_tail: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    baseline = marker.get("baseline") if isinstance(marker.get("baseline"), dict) else {}
    prefix = baseline.get("observation_ledger") if isinstance(baseline.get("observation_ledger"), dict) else {}
    errors = [f"observation ledger {error}" for error in _custody_errors(prefix)]
    watch_prefix = baseline.get("watch_ledger") if isinstance(baseline.get("watch_ledger"), dict) else {}
    source_paths = {
        "observation ledger": (TRIAL_OBSERVATION_PATH, prefix.get("present") is False),
        "watch ledger": (RECEIPT_JSONL, watch_prefix.get("present") is False),
        "task source": (TASKS_PATH, False),
        **{f"prompt {name} source": (path, False) for name, path in _prompt_paths(PROMPT_ATOM_SNAPSHOT).items()},
    }
    path_errors = [
        error
        for label, (path, allow_missing) in source_paths.items()
        for error in _trusted_canonical_file_errors(
            path,
            label=label,
            allow_missing=allow_missing,
        )
    ]
    errors.extend(path_errors)
    if path_errors:
        return [], errors
    observation_payload, _, observation_errors = _read_trusted_regular_file(
        TRIAL_OBSERVATION_PATH,
        label="observation ledger",
    )
    if observation_errors:
        if prefix.get("present") is False and not TRIAL_OBSERVATION_PATH.exists():
            payload = b""
        else:
            errors.extend(observation_errors)
            return [], errors
    else:
        payload = observation_payload or b""
    size = int(prefix.get("size") or 0)
    if len(payload) < size or _sha256_bytes(payload[:size]) != prefix.get("digest"):
        errors.append("observation ledger baseline prefix was rewritten or truncated")
        return [], errors
    rows, parse_errors = _jsonl_bytes(payload[size:])
    if parse_errors:
        errors.append(f"observation ledger has {parse_errors} malformed appended rows")
    previous_hash = marker.get("content_hash")
    previous_time = parse_iso(str(marker.get("window_start") or ""))
    previous_monotonic = int(marker.get("monotonic_start_ns") or 0)
    previous_task = baseline.get("task_source") if isinstance(baseline.get("task_source"), dict) else {}
    previous_watch = watch_prefix
    watch_payload, _, watch_read_errors = _read_trusted_regular_file(RECEIPT_JSONL, label="watch ledger")
    if watch_read_errors:
        if watch_prefix.get("present") is False and not RECEIPT_JSONL.exists():
            current_watch_bytes = b""
        else:
            errors.extend(watch_read_errors)
            return [], errors
    else:
        current_watch_bytes = watch_payload or b""
    current_task_ledger = _load_task_event_ledger()
    current_task_ids = set((current_task_ledger.get("all_events") or {}).keys())
    for expected_sequence, row in enumerate(rows, start=1):
        errors.extend(_observation_errors(row, marker=marker))
        errors.extend(_observation_custody_errors(marker, row))
        if row.get("sequence") != expected_sequence:
            errors.append("observation sequence is not contiguous")
        if row.get("previous_hash") != previous_hash:
            errors.append("observation hash chain is broken")
        observed_at = parse_iso(str(row.get("observed_at") or ""))
        if observed_at and previous_time and observed_at <= previous_time:
            errors.append("observation timestamps are not strictly increasing")
        monotonic_ns = int(row.get("monotonic_ns") or 0)
        if monotonic_ns <= previous_monotonic:
            errors.append("observation monotonic clock is not strictly increasing")
        if observed_at and previous_time and monotonic_ns > previous_monotonic:
            wall_delta = (observed_at - previous_time).total_seconds()
            monotonic_delta = (monotonic_ns - previous_monotonic) / 1_000_000_000
            if abs(wall_delta - monotonic_delta) > TRIAL_CLOCK_TOLERANCE_SEC:
                errors.append("observation wall clock diverges from monotonic custody")
        task_source = row.get("task_source") if isinstance(row.get("task_source"), dict) else {}
        previous_ids = set(previous_task.get("event_ids") or [])
        current_ids = set(task_source.get("event_ids") or [])
        if not previous_ids.issubset(current_ids):
            errors.append("task source was rewritten or truncated between observations")
        new_ids = current_ids - previous_ids
        proof_ids: set[str] = set()
        for key in ("value_proofs", "blocker_proofs", "session_proofs"):
            proof_ids.update(str(item.get("event_id") or "") for item in (row.get(key) or []) if isinstance(item, dict))
        if not proof_ids.issubset(new_ids):
            errors.append("observation credits an event that was not newly observed")

        watch = row.get("watch_custody") if isinstance(row.get("watch_custody"), dict) else {}
        previous_size = int(previous_watch.get("size") or 0)
        current_size = int(watch.get("size") or 0)
        if current_size <= previous_size or current_size > len(current_watch_bytes):
            errors.append("watch ledger did not append for an observation")
        elif _sha256_bytes(current_watch_bytes[:current_size]) != watch.get("digest") or _sha256_bytes(
            current_watch_bytes[:previous_size]
        ) != previous_watch.get("digest"):
            errors.append("watch ledger was rewritten or truncated")
        else:
            watch_rows, watch_errors = _jsonl_bytes(current_watch_bytes[previous_size:current_size])
            actual_span = [_watch_row_binding(item) for item in watch_rows]
            recorded_span = row.get("watch_span") if isinstance(row.get("watch_span"), list) else []
            if watch_errors or not watch_rows or actual_span != recorded_span:
                errors.append("observation does not bind every authoritative watch append")
            elif actual_span[-1].get("record_hash") != row.get("watch_record_hash") or actual_span[-1].get(
                "timestamp"
            ) != row.get("observed_at"):
                errors.append("observation is not bound to its terminal authoritative watch append")
            for binding in actual_span:
                watch_time = parse_iso(str(binding.get("timestamp") or ""))
                if (
                    watch_time is None
                    or (previous_time and watch_time <= previous_time)
                    or (observed_at and watch_time > observed_at)
                ):
                    errors.append("watch append timestamp is outside its observation span")

        prompt = row.get("prompt_authority") if isinstance(row.get("prompt_authority"), dict) else {}
        custody = prompt.get("source_custody") if isinstance(prompt.get("source_custody"), dict) else {}
        for name in ("events", "outcomes"):
            source_path = _prompt_paths(PROMPT_ATOM_SNAPSHOT)[name]
            if not _prefix_matches(source_path, custody.get(name) or {}):
                errors.append(f"prompt {name} journal was rewritten or truncated")
        operator_count, operator_errors = _operator_count_at_custody(
            _prompt_paths(PROMPT_ATOM_SNAPSHOT)["events"], custody.get("events") or {}
        )
        if operator_errors or operator_count != prompt.get("operator_occurrences"):
            errors.append("prompt operator count does not match its append-only journal prefix")

        previous_hash = row.get("content_hash")
        previous_time = observed_at or previous_time
        previous_monotonic = monotonic_ns
        previous_task = task_source
        previous_watch = watch
    if rows:
        last_ids = set((rows[-1].get("task_source") or {}).get("event_ids") or [])
        if not last_ids.issubset(current_task_ids):
            errors.append("task source was rewritten or truncated after the last observation")
    terminal_watch_size = int(previous_watch.get("size") or 0)
    if terminal_watch_size <= len(current_watch_bytes):
        tail_rows, tail_errors = _jsonl_bytes(current_watch_bytes[terminal_watch_size:])
        if tail_errors:
            errors.append("watch ledger has malformed rows after the last observation")
        if not allow_unbound_watch_tail:
            window_end = parse_iso(str(marker.get("window_end") or ""))
            for item in tail_rows:
                timestamp = parse_iso(str(item.get("timestamp") or ""))
                if timestamp is None:
                    errors.append("unbound watch append timestamp is invalid")
                elif window_end and timestamp <= window_end:
                    errors.append("in-window watch append is not bound to an observation")
    return rows, errors


def _terminal_source_paths() -> dict[str, Path]:
    prompt_paths = _prompt_paths(PROMPT_ATOM_SNAPSHOT)
    return {
        "handoff": LOGS / "handoff.json",
        "prompt_cursor": prompt_paths["cursor"],
        "prompt_snapshot": prompt_paths["snapshot"],
    }


def _terminal_custody_directory(trial_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", trial_id):
        raise TrialContractError("terminal custody trial id is invalid")
    return TRIAL_WINDOW_PATH.parent / "overnight-trial-custody" / trial_id


def _trusted_custody_path_errors(path: Path, *, label: str, final_directory: bool) -> list[str]:
    anchor = Path(os.path.abspath(ROOT))
    candidate = Path(os.path.abspath(path))
    try:
        relative = candidate.relative_to(anchor)
    except ValueError:
        return [f"{label} escapes the trusted Limen root"]
    errors: list[str] = []
    components = [anchor]
    current = anchor
    for part in relative.parts:
        current /= part
        components.append(current)
    for index, component in enumerate(components):
        try:
            metadata = component.lstat()
        except OSError:
            errors.append(f"{label} component {index} is missing")
            break
        if stat.S_ISLNK(metadata.st_mode):
            errors.append(f"{label} component {index} is a symlink")
            break
        if index < len(components) - 1 or final_directory:
            if not stat.S_ISDIR(metadata.st_mode):
                errors.append(f"{label} component {index} is not a directory")
                break
    if not errors:
        try:
            anchor_real = anchor.resolve(strict=True)
            candidate_real = candidate.resolve(strict=True)
        except OSError:
            errors.append(f"{label} realpath custody is unavailable")
        else:
            if candidate_real != anchor_real.joinpath(relative):
                errors.append(f"{label} realpath escaped its trusted component chain")
    return errors


def _trusted_canonical_file_errors(
    path: Path,
    *,
    label: str,
    allow_missing: bool = False,
) -> list[str]:
    parent_errors = _trusted_custody_path_errors(
        path.parent,
        label=f"{label} parent",
        final_directory=True,
    )
    if parent_errors:
        return parent_errors
    try:
        metadata = path.lstat()
    except OSError:
        return [] if allow_missing else [f"{label} is missing"]
    if stat.S_ISLNK(metadata.st_mode):
        return [f"{label} is a symlink"]
    if not stat.S_ISREG(metadata.st_mode):
        return [f"{label} is not a regular file"]
    try:
        expected = path.parent.resolve(strict=True) / path.name
        actual = path.resolve(strict=True)
    except OSError:
        return [f"{label} realpath custody is unavailable"]
    if actual != expected:
        return [f"{label} realpath escaped its trusted component chain"]
    return []


def _read_trusted_regular_file(path: Path, *, label: str) -> tuple[bytes | None, int | None, list[str]]:
    path_errors = _trusted_canonical_file_errors(path, label=label)
    if path_errors:
        return None, None, path_errors
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_fd: int | None = None
    file_fd: int | None = None
    try:
        directory_fd = os.open(path.parent, directory_flags)
        file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        file_fd = os.open(path.name, file_flags, dir_fd=directory_fd)
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode):
            return None, None, [f"{label} is not a regular file"]
        with os.fdopen(file_fd, "rb") as handle:
            file_fd = None
            payload = handle.read()
        return payload, metadata.st_mode & 0o777, []
    except OSError as exc:
        return None, None, [f"{label} no-follow read failed: {exc}"]
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def _load_trusted_json(
    path: Path,
    *,
    label: str,
    allow_missing: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    path_errors = _trusted_canonical_file_errors(path, label=label, allow_missing=allow_missing)
    if path_errors:
        return {}, path_errors
    if allow_missing:
        try:
            path.lstat()
        except OSError:
            return {}, []
    payload, _, read_errors = _read_trusted_regular_file(path, label=label)
    if read_errors or payload is None:
        return {}, read_errors
    try:
        value = json.loads(payload)
    except (UnicodeError, ValueError):
        return {}, [f"{label} is malformed JSON"]
    if not isinstance(value, dict):
        return {}, [f"{label} is not a JSON object"]
    return value, []


def _terminal_custody_path(trial_id: str, name: str, digest: str) -> Path:
    if name not in {"handoff", "prompt_cursor", "prompt_snapshot"} or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise TrialContractError("terminal custody path components are invalid")
    return _terminal_custody_directory(trial_id) / f"{name}-{digest}.bin"


def _terminal_observation_custody(observations: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    if not observations:
        return {}, ["terminal observation is missing"]
    terminal = observations[-1]
    terminal_prompt = terminal.get("prompt_authority") if isinstance(terminal.get("prompt_authority"), dict) else {}
    prompt_custody = (
        terminal_prompt.get("source_custody") if isinstance(terminal_prompt.get("source_custody"), dict) else {}
    )
    handoff = terminal.get("handoff") if isinstance(terminal.get("handoff"), dict) else {}
    recorded = {
        "handoff": handoff.get("source_custody"),
        "prompt_cursor": prompt_custody.get("cursor"),
        "prompt_snapshot": prompt_custody.get("snapshot"),
    }
    sources: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for name in _terminal_source_paths():
        expected = recorded.get(name)
        expected_errors = _custody_errors(expected)
        if expected_errors or not isinstance(expected, dict) or expected.get("present") is not True:
            errors.append(f"terminal observation {name} custody is invalid")
            continue
        sources[name] = {"size": expected["size"], "digest": expected["digest"]}
    return {"schema_version": TRIAL_TERMINAL_CUSTODY_SCHEMA_VERSION, "sources": sources}, errors


def _terminal_live_custody_errors(value: dict[str, Any]) -> list[str]:
    sources = value.get("sources") if isinstance(value.get("sources"), dict) else {}
    errors: list[str] = []
    for name, path in _terminal_source_paths().items():
        path_errors = _trusted_canonical_file_errors(path, label=f"terminal {name} source")
        errors.extend(path_errors)
        if path_errors:
            continue
        expected = sources.get(name)
        live = _file_custody(path)
        if (
            not isinstance(expected, dict)
            or live.get("present") is not True
            or live.get("size") != expected.get("size")
            or live.get("digest") != expected.get("digest")
        ):
            errors.append(f"terminal {name} custody does not match the live authoritative file")
    return errors


def _terminal_custody_directory_errors(trial_id: str) -> list[str]:
    directory = _terminal_custody_directory(trial_id)
    errors = _trusted_custody_path_errors(
        directory,
        label="terminal custody directory",
        final_directory=True,
    )
    if errors:
        return errors
    for label, path in (("root", directory.parent), ("trial", directory)):
        if path.is_symlink():
            errors.append(f"terminal custody {label} directory is a symlink")
        elif not path.is_dir():
            errors.append(f"terminal custody {label} directory is missing or invalid")
    return errors


def _terminal_custody_errors(
    value: Any,
    *,
    trial_id: str,
    verify_sidecars: bool,
) -> list[str]:
    if not isinstance(value, dict):
        return ["terminal custody descriptor is missing"]
    errors: list[str] = []
    trial_id_valid = bool(re.fullmatch(r"[0-9a-f]{64}", trial_id))
    if not trial_id_valid:
        errors.append("terminal custody trial id is invalid")
    if value.get("schema_version") != TRIAL_TERMINAL_CUSTODY_SCHEMA_VERSION:
        errors.append("terminal custody schema mismatch")
    sources = value.get("sources") if isinstance(value.get("sources"), dict) else {}
    if set(sources) != set(_terminal_source_paths()):
        errors.append("terminal custody source set mismatch")
    verify_paths = verify_sidecars and trial_id_valid
    if verify_paths:
        directory_errors = _terminal_custody_directory_errors(trial_id)
        errors.extend(directory_errors)
        verify_paths = not directory_errors
    for name in _terminal_source_paths():
        source = sources.get(name) if isinstance(sources.get(name), dict) else {}
        if not _strict_nonnegative_int(source.get("size")):
            errors.append(f"terminal {name} custody size is invalid")
        digest = str(source.get("digest") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append(f"terminal {name} custody digest is invalid")
            continue
        if not verify_paths:
            continue
        path = _terminal_custody_path(trial_id, name, digest)
        payload, mode, file_errors = _read_trusted_regular_file(
            path,
            label=f"terminal {name} custody sidecar",
        )
        if file_errors:
            errors.extend(file_errors)
            continue
        if payload is None or mode is None:
            errors.append(f"terminal {name} custody sidecar no-follow read was incomplete")
            continue
        if len(payload) != source.get("size") or _sha256_bytes(payload) != digest:
            errors.append(f"terminal {name} custody sidecar content mismatch")
        if mode & 0o222:
            errors.append(f"terminal {name} custody sidecar is writable")
    return errors


def _preserve_terminal_custody(trial_id: str, value: dict[str, Any]) -> None:
    errors = _terminal_custody_errors(value, trial_id=trial_id, verify_sidecars=False)
    if errors:
        raise TrialContractError("invalid terminal custody: " + "; ".join(sorted(set(errors))))
    directory = _terminal_custody_directory(trial_id)
    configured_root_errors = _trusted_custody_path_errors(
        directory.parent.parent,
        label="terminal custody configured root",
        final_directory=True,
    )
    if configured_root_errors:
        raise TrialContractError("; ".join(sorted(set(configured_root_errors))))
    if directory.parent.is_symlink():
        raise TrialContractError("terminal custody root directory is a symlink or invalid")
    try:
        directory.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise TrialContractError(f"terminal custody root directory is unavailable: {exc}") from exc
    if directory.parent.is_symlink() or not directory.parent.is_dir():
        raise TrialContractError("terminal custody root directory is a symlink or invalid")
    custody_root_errors = _trusted_custody_path_errors(
        directory.parent,
        label="terminal custody root directory",
        final_directory=True,
    )
    if custody_root_errors:
        raise TrialContractError("; ".join(sorted(set(custody_root_errors))))
    if directory.is_symlink():
        raise TrialContractError("terminal custody trial directory is a symlink or invalid")
    try:
        directory.mkdir(mode=0o700, exist_ok=True)
    except OSError as exc:
        raise TrialContractError(f"terminal custody trial directory is unavailable: {exc}") from exc
    if directory.is_symlink() or not directory.is_dir():
        raise TrialContractError("terminal custody trial directory is a symlink or invalid")
    trial_directory_errors = _trusted_custody_path_errors(
        directory,
        label="terminal custody trial directory",
        final_directory=True,
    )
    if trial_directory_errors:
        raise TrialContractError("; ".join(sorted(set(trial_directory_errors))))
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_fd = os.open(directory, directory_flags)
    except OSError as exc:
        raise TrialContractError(f"terminal custody trial directory is unavailable: {exc}") from exc
    try:
        os.fchmod(directory_fd, 0o700)
        for name, source_path in _terminal_source_paths().items():
            descriptor = value["sources"][name]
            payload, _, source_errors = _read_trusted_regular_file(
                source_path,
                label=f"terminal {name} source",
            )
            if source_errors or payload is None:
                raise TrialContractError(f"terminal {name} source is unavailable: {'; '.join(source_errors)}")
            digest = str(descriptor["digest"])
            if len(payload) != descriptor["size"] or _sha256_bytes(payload) != digest:
                raise TrialContractError(f"terminal {name} source changed before custody preservation")
            destination = _terminal_custody_path(trial_id, name, digest)
            file_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            try:
                fd = os.open(destination.name, file_flags, 0o400, dir_fd=directory_fd)
            except FileExistsError:
                continue
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    sidecar_errors = _terminal_custody_errors(value, trial_id=trial_id, verify_sidecars=True)
    if sidecar_errors:
        raise TrialContractError("terminal custody preservation failed: " + "; ".join(sorted(set(sidecar_errors))))


def append_trial_observation(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    marker_path_errors = _trusted_canonical_file_errors(
        TRIAL_WINDOW_PATH,
        label="active trial marker",
        allow_missing=True,
    )
    if marker_path_errors:
        raise TrialContractError("; ".join(marker_path_errors))
    marker, marker_read_errors = _load_trusted_json(
        TRIAL_WINDOW_PATH,
        label="active trial marker",
        allow_missing=True,
    )
    if marker_read_errors:
        raise TrialContractError("; ".join(marker_read_errors))
    if marker.get("active") is not True:
        return None
    marker_errors = _active_marker_errors(marker)
    if marker_errors:
        raise TrialContractError("invalid active marker: " + "; ".join(sorted(set(marker_errors))))
    wall_now = utc_now().astimezone(dt.timezone.utc).replace(microsecond=0)
    observed_at = parse_iso(str(snapshot.get("timestamp") or ""))
    start = parse_iso(str(marker.get("window_start") or ""))
    end = parse_iso(str(marker.get("window_end") or ""))
    if (
        not start
        or not end
        or not observed_at
        or observed_at < start
        or observed_at > end + dt.timedelta(seconds=TRIAL_EDGE_TOLERANCE_SEC)
    ):
        raise TrialContractError("observation is outside the prospective trial window")
    wall_age = int((wall_now - observed_at).total_seconds())
    if wall_age < 0 or wall_age > 60:
        raise TrialContractError("watch snapshot is not a current wall-clock observation")

    lock_path = TRIAL_OBSERVATION_PATH.with_suffix(TRIAL_OBSERVATION_PATH.suffix + ".lock")
    lock_errors = _trusted_canonical_file_errors(
        lock_path,
        label="trial observation lock",
        allow_missing=True,
    )
    if lock_errors:
        raise TrialContractError("; ".join(lock_errors))
    lock_flags = os.O_RDWR | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    lock_fd = os.open(lock_path, lock_flags, 0o600)
    with os.fdopen(lock_fd, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        rows, chain_errors = _read_observation_chain(marker, allow_unbound_watch_tail=True)
        if chain_errors:
            raise TrialContractError("trial observation chain is invalid: " + "; ".join(sorted(set(chain_errors))))
        baseline = marker.get("baseline") if isinstance(marker.get("baseline"), dict) else {}
        previous_task = (
            rows[-1].get("task_source")
            if rows and isinstance(rows[-1].get("task_source"), dict)
            else baseline.get("task_source")
        )
        previous_ids = set((previous_task or {}).get("event_ids") or [])
        task_ledger = _load_task_event_ledger()
        task_source = _task_source_snapshot(task_ledger)
        task_errors = _task_source_errors(task_source)
        current_ids = set(task_source.get("event_ids") or [])
        if task_errors or not previous_ids.issubset(current_ids):
            raise TrialContractError("task source was rewritten or truncated")
        new_ids = sorted(current_ids - previous_ids)
        value_proofs: list[dict[str, Any]] = []
        blocker_proofs: list[dict[str, Any]] = []
        session_proofs: list[dict[str, Any]] = []
        for event_id in new_ids:
            entry = (task_ledger.get("all_events") or {}).get(event_id) or {}
            if not _task_event_within_observation(entry, window_start=start, observed_at=observed_at):
                continue
            if entry.get("status") == "done":
                proof = _prove_terminal_event(entry)
                if proof:
                    value_proofs.append(proof)
            elif entry.get("status") in {"failed_blocked", "needs_human"}:
                proof = _prove_terminal_event(entry)
                if proof:
                    blocker_proofs.append(proof)
            elif entry.get("status") == "in_progress":
                proof = _prove_session_event(
                    entry,
                    window_start=start,
                    observed_at=observed_at,
                )
                if proof:
                    session_proofs.append(proof)

        prompt = prompt_authority_snapshot(observed_at)
        handoff_live = handoff_relay_snapshot(refresh=False)
        watch_custody = _file_custody(RECEIPT_JSONL)
        previous_watch = (
            rows[-1].get("watch_custody")
            if rows and isinstance(rows[-1].get("watch_custody"), dict)
            else baseline.get("watch_ledger")
        )
        previous_watch_size = int((previous_watch or {}).get("size") or 0)
        watch_bytes, _, watch_read_errors = _read_trusted_regular_file(RECEIPT_JSONL, label="watch ledger")
        if watch_read_errors or watch_bytes is None:
            raise TrialContractError("watch source is not a canonical regular file")
        current_watch_size = int(watch_custody.get("size") or 0)
        appended_rows, appended_errors = _jsonl_bytes(watch_bytes[previous_watch_size:current_watch_size])
        matches = [item for item in appended_rows if canonical_hash(item) == canonical_hash(snapshot)]
        if (
            appended_errors
            or not _prefix_matches(RECEIPT_JSONL, previous_watch or {})
            or current_watch_size <= previous_watch_size
            or len(matches) != 1
            or not appended_rows
            or canonical_hash(appended_rows[-1]) != canonical_hash(snapshot)
        ):
            raise TrialContractError("watch source did not append the authoritative sample")
        watch_span = [_watch_row_binding(item) for item in appended_rows]
        span_status = _watch_span_status(watch_span)
        span_alert_count = sum(int(item["alert_count"]) for item in watch_span)

        handoff_path = LOGS / "handoff.json"
        record: dict[str, Any] = {
            "schema_version": TRIAL_OBSERVATION_SCHEMA_VERSION,
            "trial_id": marker.get("content_hash"),
            "sequence": len(rows) + 1,
            "previous_hash": rows[-1].get("content_hash") if rows else marker.get("content_hash"),
            "observed_at": observed_at.isoformat(timespec="seconds"),
            "monotonic_ns": time.monotonic_ns(),
            "status": span_status,
            "alert_count": span_alert_count,
            "watch_custody": watch_custody,
            "watch_record_hash": canonical_hash(snapshot),
            "watch_span": watch_span,
            "task_source": task_source,
            "prompt_authority": prompt,
            "handoff": {
                "ok": handoff_live.get("ok") is True,
                "check_returncode": handoff_live.get("check_returncode"),
                "source_custody": _file_custody(handoff_path),
            },
            "value_proofs": value_proofs,
            "blocker_proofs": blocker_proofs,
            "session_proofs": session_proofs,
        }
        record["content_hash"] = canonical_hash(record)
        _write_observation_custody(marker, record)
        _append_jsonl(TRIAL_OBSERVATION_PATH, record)
        return record


def build_trial_receipt(
    active_marker: dict[str, Any],
    *,
    terminal_custody: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verifying_preserved_custody = terminal_custody is not None
    marker_errors = _active_marker_errors(active_marker)
    start = parse_iso(str(active_marker.get("window_start") or ""))
    end = parse_iso(str(active_marker.get("window_end") or ""))
    if not start or not end:
        raise TrialContractError("trial marker timestamps are invalid")
    if utc_now().astimezone(dt.timezone.utc) < end:
        raise TrialContractError("trial cannot be finalized before its prospective eight-hour window ends")
    monotonic_elapsed_ns = time.monotonic_ns() - int(active_marker.get("monotonic_start_ns") or 0)
    if monotonic_elapsed_ns < (TRIAL_DURATION_SEC - TRIAL_CLOCK_TOLERANCE_SEC) * 1_000_000_000:
        raise TrialContractError("trial cannot be finalized before eight hours of monotonic custody")
    observations, source_errors = _read_observation_chain(active_marker)
    bounded = [
        (observed_at, record)
        for record in observations
        if (observed_at := parse_iso(str(record.get("observed_at") or "")))
        and start <= observed_at <= end + dt.timedelta(seconds=TRIAL_EDGE_TOLERANCE_SEC)
    ]
    recorded_custody, recorded_custody_errors = _terminal_observation_custody([record for _, record in bounded])
    source_errors.extend(recorded_custody_errors)
    if terminal_custody is None:
        terminal_custody = recorded_custody
        custody_errors = _terminal_live_custody_errors(terminal_custody)
    else:
        if terminal_custody != recorded_custody:
            raise TrialContractError("terminal custody descriptor does not match the terminal observation")
        custody_errors = _terminal_custody_errors(
            terminal_custody,
            trial_id=str(active_marker.get("content_hash") or ""),
            verify_sidecars=True,
        )
    source_errors.extend(custody_errors)
    evidence_records = [(timestamp, record) for timestamp, record in bounded if timestamp <= end]
    sample_times = [timestamp for timestamp, _ in bounded]
    gap_points = sorted([start, *sample_times, end])
    max_gap_seconds = (
        max(max(0, int((later - earlier).total_seconds())) for earlier, later in zip(gap_points, gap_points[1:]))
        if len(gap_points) >= 2
        else TRIAL_DURATION_SEC
    )
    boundary_sample_ok = bool(
        sample_times and end <= sample_times[-1] <= end + dt.timedelta(seconds=TRIAL_MAX_SAMPLE_GAP_SEC)
    )
    coverage_ok = bool(
        sample_times
        and sample_times[0] <= start + dt.timedelta(seconds=TRIAL_MAX_SAMPLE_GAP_SEC)
        and boundary_sample_ok
        and max_gap_seconds <= TRIAL_MAX_SAMPLE_GAP_SEC
    )
    alert_count = sum(_bounded_int(record.get("alert_count")) for _, record in bounded)
    sample_schema_complete = not source_errors

    baseline = active_marker.get("baseline") if isinstance(active_marker.get("baseline"), dict) else {}
    baseline_task = baseline.get("task_source") if isinstance(baseline.get("task_source"), dict) else {}
    task_ledger = _load_task_event_ledger()
    current_entries = task_ledger.get("all_events") if isinstance(task_ledger.get("all_events"), dict) else {}
    terminal_source = bounded[-1][1].get("task_source") if bounded else baseline_task
    if not set((terminal_source or {}).get("event_ids") or []).issubset(set(current_entries)):
        source_errors.append("task source lost events after the terminal observation")

    value_proofs = [proof for _, record in evidence_records for proof in (record.get("value_proofs") or [])]
    blocker_proofs = [proof for _, record in evidence_records for proof in (record.get("blocker_proofs") or [])]
    session_proofs = [proof for _, record in evidence_records for proof in (record.get("session_proofs") or [])]
    for proof in value_proofs:
        entry = current_entries.get(proof.get("event_id")) or {}
        if entry.get("status") != "done":
            source_errors.append("value proof no longer maps to a done event")
        elif _prove_terminal_event(entry) != proof:
            source_errors.append("value proof no longer re-executes exactly")
    for proof in blocker_proofs:
        entry = current_entries.get(proof.get("event_id")) or {}
        if entry.get("status") not in {
            "failed_blocked",
            "needs_human",
        }:
            source_errors.append("blocker proof no longer maps to an owner-blocked event")
        elif _prove_terminal_event(entry) != proof:
            source_errors.append("blocker proof no longer re-executes exactly")
    for proof in session_proofs:
        entry = current_entries.get(proof.get("event_id")) or {}
        if entry.get("status") != "in_progress":
            source_errors.append("session proof no longer maps to an in-progress event")
    activity_times = [
        timestamp
        for timestamp, record in evidence_records
        if (record.get("value_proofs") or []) or (record.get("blocker_proofs") or [])
    ]
    activity_points = [start, *activity_times, end]
    max_value_gap_seconds = (
        max(int((later - earlier).total_seconds()) for earlier, later in zip(activity_points, activity_points[1:]))
        if activity_times
        else TRIAL_DURATION_SEC
    )
    rolling_value_ok = bool(activity_times and max_value_gap_seconds <= TRIAL_VALUE_WINDOW_SEC)

    windows: list[dict[str, Any]] = []
    for index, (window_start, window_end) in enumerate(_trial_windows(start, end), start=1):
        window_records = [record for timestamp, record in evidence_records if window_start < timestamp <= window_end]
        value_done_events = sum(len(record.get("value_proofs") or []) for record in window_records)
        owner_blocked_events = sum(len(record.get("blocker_proofs") or []) for record in window_records)
        windows.append(
            {
                "index": index,
                "start": window_start.isoformat(timespec="seconds"),
                "end": window_end.isoformat(timespec="seconds"),
                "value_done_events": max(0, value_done_events),
                "owner_blocked_events": max(0, owner_blocked_events),
                "pass": value_done_events > 0 or owner_blocked_events > 0,
            }
        )
    value_done_events = len({str(proof.get("event_id")) for proof in value_proofs})
    owner_blocked_events = len({str(proof.get("event_id")) for proof in blocker_proofs})
    seam_count = len({str(proof.get("event_id")) for proof in session_proofs})
    task_monotonic = not any("task source" in error for error in source_errors)

    baseline_prompt = baseline.get("prompt_authority")
    prompt_snapshots = [baseline_prompt, *(record.get("prompt_authority") for _, record in bounded)]
    prompt_counts = [
        _bounded_int(item.get("operator_occurrences")) for item in prompt_snapshots if isinstance(item, dict)
    ]
    prompt_monotonic = len(prompt_counts) == len(prompt_snapshots) and all(
        later >= earlier for earlier, later in zip(prompt_counts, prompt_counts[1:])
    )
    operator_interventions = prompt_counts[-1] - prompt_counts[0] if prompt_counts and prompt_monotonic else 0
    prompt_authority_ok = bool(
        prompt_snapshots and all(not _prompt_snapshot_errors(item) for item in prompt_snapshots) and prompt_monotonic
    )
    if isinstance(baseline_prompt, dict):
        baseline_custody = baseline_prompt.get("source_custody") or {}
        operator_count, operator_errors = _operator_count_at_custody(
            _prompt_paths(PROMPT_ATOM_SNAPSHOT)["events"], baseline_custody.get("events") or {}
        )
        if operator_errors or operator_count != baseline_prompt.get("operator_occurrences"):
            prompt_authority_ok = False
            source_errors.append("prompt baseline does not match its append-only journal prefix")
        for name in ("events", "outcomes"):
            if not _prefix_matches(_prompt_paths(PROMPT_ATOM_SNAPSHOT)[name], baseline_custody.get(name) or {}):
                prompt_authority_ok = False
                source_errors.append(f"prompt baseline {name} journal was rewritten or truncated")

    terminal_record = bounded[-1][1] if bounded else {}
    terminal_handoff = terminal_record.get("handoff") if isinstance(terminal_record.get("handoff"), dict) else {}
    handoff_fresh = bool(terminal_handoff.get("ok") and terminal_handoff.get("check_returncode") == 0)
    duration_seconds = int((end - start).total_seconds())
    duration_ok = duration_seconds == TRIAL_DURATION_SEC
    monotonic_duration_ok = monotonic_elapsed_ns >= (TRIAL_DURATION_SEC - TRIAL_CLOCK_TOLERANCE_SEC) * 1_000_000_000
    windows_ok = rolling_value_ok

    if verifying_preserved_custody and source_errors:
        raise TrialContractError("trial reconstruction source errors: " + "; ".join(sorted(set(source_errors))))

    normalized_input = {
        "trial_id": active_marker.get("content_hash"),
        "baseline": baseline,
        "observation_hashes": [record.get("content_hash") for _, record in bounded],
        "source_errors": sorted(set(source_errors)),
        "terminal_custody": terminal_custody,
        "task_window_end": terminal_source,
        "task_windows": windows,
    }
    receipt: dict[str, Any] = {
        "schema_version": TRIAL_SCHEMA_VERSION,
        "trial_id": active_marker.get("content_hash"),
        "window_start": start.isoformat(timespec="seconds"),
        "window_end": end.isoformat(timespec="seconds"),
        "duration_seconds": duration_seconds,
        "hours": 8,
        "value_window_seconds": TRIAL_VALUE_WINDOW_SEC,
        "window_count": len(windows),
        "windows": windows,
        "sample_count": len(bounded),
        "max_sample_gap_seconds": max_gap_seconds,
        "max_value_gap_seconds": max_value_gap_seconds,
        "sample_schema_complete": sample_schema_complete,
        "source_parse_errors": len(source_errors),
        "value_done_events": max(0, value_done_events),
        "owner_blocked_events": max(0, owner_blocked_events),
        "seam_count": max(0, seam_count),
        "handoff_fresh": handoff_fresh,
        "operator_interventions": max(0, operator_interventions),
        "prompt_authority_exact": prompt_authority_ok,
        "watch_alerts": alert_count,
        "coverage_ok": coverage_ok,
        "duration_ok": duration_ok,
        "monotonic_duration_ok": monotonic_duration_ok,
        "windows_ok": windows_ok,
        "rolling_value_ok": rolling_value_ok,
        "task_events_monotonic": task_monotonic,
        "terminal_custody": terminal_custody,
        "evaluator_hash": evaluator_hash(),
        "input_hash": canonical_hash(normalized_input),
    }
    receipt["pass"] = bool(
        not marker_errors
        and not source_errors
        and duration_ok
        and monotonic_duration_ok
        and coverage_ok
        and sample_schema_complete
        and windows_ok
        and task_monotonic
        and seam_count > 0
        and prompt_authority_ok
        and operator_interventions == 0
        and handoff_fresh
        and receipt["watch_alerts"] == 0
    )
    return receipt


def write_trial_receipt(receipt: dict[str, Any], path: Path | None = None) -> tuple[dict[str, Any], bool]:
    output = path or TRIAL_PATH
    deterministic = {key: value for key, value in receipt.items() if key not in {"generated_at", "content_hash"}}
    content_hash = canonical_hash(deterministic)
    existing, existing_errors = _load_trusted_json(
        output,
        label="trial receipt",
        allow_missing=True,
    )
    if existing_errors:
        raise TrialContractError("; ".join(existing_errors))
    existing_deterministic = {
        key: value for key, value in existing.items() if key not in {"generated_at", "content_hash"}
    }
    if (
        existing.get("content_hash") == content_hash
        and existing_deterministic == deterministic
        and parse_iso(str(existing.get("generated_at") or "")) is not None
    ):
        return existing, False
    payload = {**deterministic, "generated_at": iso_now(), "content_hash": content_hash}
    _write_json_atomic(output, payload)
    return payload, True


def finalize_trial(
    active_marker: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    errors = _active_marker_errors(active_marker)
    if errors:
        raise TrialContractError("invalid active marker: " + "; ".join(sorted(set(errors))))
    receipt = build_trial_receipt(active_marker)
    _preserve_terminal_custody(str(active_marker.get("content_hash") or ""), receipt["terminal_custody"])
    return write_trial_receipt(receipt)


def maybe_finalize_trial() -> dict[str, Any] | None:
    marker_path = TRIAL_WINDOW_PATH
    lock_path = marker_path.with_suffix(marker_path.suffix + ".lock")
    marker_path_errors = _trusted_canonical_file_errors(
        marker_path,
        label="trial marker",
        allow_missing=True,
    )
    lock_path_errors = _trusted_canonical_file_errors(
        lock_path,
        label="trial marker lock",
        allow_missing=True,
    )
    path_errors = [*marker_path_errors, *lock_path_errors]
    if path_errors:
        return {"error": "; ".join(sorted(set(path_errors)))}
    lock_flags = os.O_RDWR | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    lock_fd = os.open(lock_path, lock_flags, 0o600)
    with os.fdopen(lock_fd, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        marker, marker_read_errors = _load_trusted_json(
            marker_path,
            label="trial marker",
            allow_missing=True,
        )
        if marker_read_errors:
            return {"error": "; ".join(marker_read_errors)}
        if not marker.get("active"):
            if marker.get("active") is False:
                receipt, receipt_read_errors = _load_trusted_json(TRIAL_PATH, label="terminal trial receipt")
                if receipt_read_errors:
                    return {"error": "; ".join(receipt_read_errors)}
                ok, receipt_errors = check_trial_receipt(TRIAL_PATH)
                if ok:
                    return {"receipt": receipt, "changed": False, "already_finalized": True}
                return {"error": "; ".join(receipt_errors) or "terminal trial receipt is invalid"}
            return None
        errors = _active_marker_errors(marker)
        if errors:
            return {"error": "; ".join(sorted(set(errors)))}
        end = parse_iso(str(marker.get("window_end") or ""))
        reference = utc_now().astimezone(dt.timezone.utc)
        if not end or reference < end:
            return {"pending": True, "window_end": marker.get("window_end")}
        receipt, changed = finalize_trial(marker)
        completed: dict[str, Any] = {
            "schema_version": TRIAL_MARKER_SCHEMA_VERSION,
            "active": False,
            "trial_id": marker.get("content_hash"),
            "active_marker": marker,
            "finalized_at": receipt.get("generated_at"),
            "receipt_content_hash": receipt.get("content_hash"),
            "receipt_input_hash": receipt.get("input_hash"),
            "receipt_pass": receipt.get("pass"),
        }
        completed["content_hash"] = canonical_hash(completed)
        _write_json_atomic(marker_path, completed)
        return {"receipt": receipt, "changed": changed}


def check_trial_receipt(
    path: Path | None = None,
) -> tuple[bool, list[str]]:
    output = path or TRIAL_PATH
    terminal_path = TRIAL_WINDOW_PATH
    receipt_path_errors = _trusted_canonical_file_errors(output, label="terminal trial receipt")
    marker_path_errors = _trusted_canonical_file_errors(terminal_path, label="terminal trial marker")
    errors = [*receipt_path_errors, *marker_path_errors]
    authoritative_paths = {
        "trial observation ledger": TRIAL_OBSERVATION_PATH,
        "trial watch ledger": RECEIPT_JSONL,
        "trial task source": TASKS_PATH,
        **{f"prompt {name} source": path for name, path in _prompt_paths(PROMPT_ATOM_SNAPSHOT).items()},
        **{f"terminal {name} source": path for name, path in _terminal_source_paths().items()},
    }
    errors.extend(
        error
        for label, source_path in authoritative_paths.items()
        for error in _trusted_canonical_file_errors(source_path, label=label)
    )
    receipt, receipt_read_errors = (
        ({}, receipt_path_errors) if receipt_path_errors else _load_trusted_json(output, label="terminal trial receipt")
    )
    marker, marker_read_errors = (
        ({}, marker_path_errors)
        if marker_path_errors
        else _load_trusted_json(terminal_path, label="terminal trial marker")
    )
    errors.extend([*receipt_read_errors, *marker_read_errors])
    errors.extend(_terminal_marker_errors(marker, receipt))
    active_marker = marker.get("active_marker") if isinstance(marker.get("active_marker"), dict) else {}
    if receipt.get("schema_version") != TRIAL_SCHEMA_VERSION:
        errors.append("trial receipt schema mismatch")
    if receipt.get("pass") is not True:
        errors.append("trial receipt is not passing")
    generated_at = parse_iso(str(receipt.get("generated_at") or ""))
    if generated_at is None:
        errors.append("trial receipt generation time is invalid")
    deterministic = {key: value for key, value in receipt.items() if key not in {"generated_at", "content_hash"}}
    if receipt.get("content_hash") != canonical_hash(deterministic):
        errors.append("trial receipt content hash mismatch")
    errors.extend(
        _terminal_custody_errors(
            receipt.get("terminal_custody"),
            trial_id=str(receipt.get("trial_id") or ""),
            verify_sidecars=True,
        )
    )
    # Do not reconstruct from sources after the receipt, marker, authoritative paths, or immutable
    # custody sidecars have already failed trust validation. Besides avoiding work on untrusted
    # input, this guarantees FIFOs/devices are rejected without reaching predicate re-execution.
    if errors:
        return False, sorted(set(errors))
    try:
        expected = build_trial_receipt(
            active_marker,
            terminal_custody=receipt.get("terminal_custody"),
        )
    except TrialContractError as exc:
        errors.append(str(exc))
        expected = {}
    if deterministic != expected:
        errors.append("trial receipt does not match exact bounded source reconstruction")
    if receipt.get("evaluator_hash") != evaluator_hash():
        errors.append("trial receipt evaluator hash mismatch")
    return not errors, sorted(set(errors))


def print_summary(snapshot: dict[str, Any]) -> None:
    heartbeat = snapshot.get("heartbeat") or {}
    async_line = (heartbeat.get("latest_async") or {}).get("raw")
    tick_line = (heartbeat.get("latest_tick") or {}).get("raw")
    dispatch = snapshot.get("dispatch_control") or {}
    print(
        "overnight-watch: "
        f"{snapshot.get('status')} log_age={snapshot.get('log_age_sec')} "
        f"stale_ticks={snapshot.get('stale_tick_count')} workers={snapshot.get('worker_count')} "
        f"children={snapshot.get('heartbeat_child_count')}"
    )
    if tick_line:
        print(f"  tick: {tick_line}")
    if async_line:
        print(f"  async: {async_line}")
    if not dispatch.get("allow_dispatch", True):
        print(f"  dispatch blocked: {dispatch.get('reason')}")
        if dispatch.get("next_command"):
            print(f"  next: {dispatch.get('next_command')}")
    for alert in snapshot.get("alerts") or []:
        print(f"  WATCH_ALERT {alert['id']}: {alert['evidence']}")
    for action in snapshot.get("heal") or []:
        print(f"  HEAL {json.dumps(action, sort_keys=True)}")


def pause_guard_snapshot() -> dict[str, Any]:
    """Build the cheap, counts-only receipt for an intentional autonomy pause."""

    previous = load_json(STATE_PATH)
    latest_tick = previous.get("latest_tick")
    heartbeat: dict[str, Any] = {}
    if latest_tick:
        heartbeat["latest_tick"] = {
            "timestamp": latest_tick,
            "raw": "watch sampling skipped: autonomy paused",
        }
    next_command = "python3 scripts/autonomy-governor.py explain"
    return {
        "timestamp": iso_now(),
        "root": str(ROOT),
        "status": "blocked",
        "pause_guard": {
            "active": True,
            "marker": "logs/AUTONOMY_PAUSED",
            "source": "autonomy_pause",
            "expensive_probes_run": 0,
        },
        "log_age_sec": None,
        "heartbeat": heartbeat,
        "launchd": {"ok": True, "state": "paused"},
        "workers": [],
        "worker_count": 0,
        "heartbeat_children": [],
        "heartbeat_child_count": 0,
        "stale_tick_count": int(previous.get("stale_tick_count") or 0),
        "thresholds": {
            "max_log_age_sec": MAX_LOG_AGE_SEC,
            "max_stale_ticks": MAX_STALE_TICKS,
        },
        "token_report": {},
        "task_events": {},
        "prompt_authority": {},
        "handoff_relay": {
            "ok": False,
            "skipped": "autonomy_pause",
            "refresh_returncode": None,
            "check_returncode": None,
        },
        "value_gate": {
            "action": "autonomy_paused",
            "returncode": 0,
            "skipped": True,
        },
        "dispatch_control": {
            "allow_dispatch": False,
            "exit_code": 0,
            "reason": "autonomy pause marker is present",
            "next_command": next_command,
        },
        "lane_switch": {"status": "skipped_autonomy_pause", "ticket_count": 0},
        "overnight_counts": {
            "launched": 0,
            "harvested": 0,
            "reaped": 0,
            "done": 0,
            "failed": 0,
            "no_op": 0,
            "timed_out": 0,
            "stale_handoff": False,
            "gate_action": "autonomy_paused",
            "gate_exit": 0,
            "dispatch_allowed": False,
            "lane_switch_status": "skipped_autonomy_pause",
            "lane_switch_task": "",
            "lane_switch_ticket_count": 0,
            "lane_switch_blocker": "",
            "next_command": next_command,
        },
        "plist_drift": [],
        "throughput": {"suppressed": "governor-paused"},
        "alerts": [],
    }


def stop_for_autonomy_pause(*, dry_run: bool, json_output: bool) -> int | None:
    """Write one blocked receipt and exit zero before any expensive watch probe."""

    if not autonomy_pause_active():
        return None
    snapshot = pause_guard_snapshot()
    if not dry_run:
        write_receipts(snapshot)
    if json_output:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    else:
        print_summary(snapshot)
    return 0


def run_once(*, dry_run: bool, json_output: bool) -> int:
    paused_rc = stop_for_autonomy_pause(dry_run=dry_run, json_output=json_output)
    if paused_rc is not None:
        return paused_rc
    snapshot = build_snapshot(
        refresh_handoff=not dry_run,
        record_gate=not dry_run,
        submit_lane_switch=not dry_run,
    )
    if not dry_run:
        heal_actions = heal(snapshot)
        if heal_actions:
            snapshot["heal"] = heal_actions
        write_receipts(snapshot)
        try:
            trial_observation = append_trial_observation(snapshot)
        except TrialContractError as exc:
            trial_observation = None
            snapshot["trial_observation_error"] = str(exc)
        if trial_observation:
            snapshot["trial_observation"] = {
                "sequence": trial_observation.get("sequence"),
                "content_hash": trial_observation.get("content_hash"),
            }
        try:
            trial_finalization = maybe_finalize_trial()
        except TrialContractError as exc:
            trial_finalization = {"error": str(exc)}
        if trial_finalization and not trial_finalization.get("pending"):
            snapshot["trial_finalization"] = trial_finalization
    if json_output:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    else:
        print_summary(snapshot)
    if snapshot.get("status") == "alert":
        return 1
    finalization = snapshot.get("trial_finalization") or {}
    if (
        snapshot.get("trial_observation_error")
        or finalization.get("error")
        or (isinstance(finalization.get("receipt"), dict) and finalization["receipt"].get("pass") is not True)
    ):
        return 1
    if snapshot.get("status") == "blocked":
        return int((snapshot.get("dispatch_control") or {}).get("exit_code") or 10)
    return 0


def _rss_mb() -> float:
    """This process's peak RSS in MB (fail-open 0.0). macOS reports bytes, Linux KiB."""
    try:
        import resource

        divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / divisor
    except Exception:
        return 0.0


def _vitals_shedding() -> bool:
    """True iff VITALS currently reports 'shed' (memory/swap >= critical).

    Read-only gate path (shed=False) so reading it here never perturbs the heartbeat's
    sustained-warn -> shed streak (only beat_gate(shed=True) counts). In-process (no fork)
    to stay off the macOS fork/os_log crash path. Fail-open False: a sensor fault must
    never tighten the bound spuriously.
    """
    try:
        from limen.vigilia import vitals

        return vitals.beat_gate(shed=False).get("action") == vitals.SHED
    except Exception:
        return False


def _arm_wall_clock_bound() -> int:
    """Bound any single tick's wall clock (IF-HOST-PRESSURE form 4, issue #1148).

    2026-07-16: one launchd one-shot tick wedged for 51 minutes at 3.1 GiB under an
    I/O storm. The bound exits 0 (fail-open — a wedged monitor must never redden
    launchd); StartInterval respawns a fresh process within 5 minutes. Returns the
    bound in seconds (0 = disabled); callers re-arm per tick via signal.alarm().

    Under VITALS shed the bound tightens to ~1/5 (240 -> 48s, floor 30s) so the monitor
    never piles a full heavy scan onto an already-thrashing host — it runs a short pass,
    exits fail-open, and StartInterval respawns a fresh tick once pressure clears. Local
    dispatch is already refused under shed (_local_admission_gate); this cuts the monitor's
    own scan duty cycle too, complementing the heartbeat hygiene-shed gate.
    """
    wall_s = int(os.environ.get("LIMEN_WATCH_WALL_S", "240") or 0)
    if wall_s > 0 and _vitals_shedding():
        wall_s = max(30, wall_s // 5)
    if wall_s <= 0:
        return 0

    def _wall_timeout(signum, frame):  # noqa: ARG001 — signal handler signature
        print(
            f"overnight-watch: wall-clock bound {wall_s}s hit — exiting fail-open; "
            "launchd StartInterval respawns fresh (2026-07-16 wedged-tick incident)",
            file=sys.stderr,
        )
        os._exit(0)

    signal.signal(signal.SIGALRM, _wall_timeout)
    return wall_s


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="inspect without writing receipts")
    parser.add_argument("--json", action="store_true", help="print the full snapshot")
    trial_mode = parser.add_mutually_exclusive_group()
    trial_mode.add_argument(
        "--start-trial",
        action="store_true",
        help="start a fixed eight-hour unattended trial consumed by later one-shot invocations",
    )
    trial_mode.add_argument(
        "--finalize-trial",
        action="store_true",
        help="finalize the due active trial, or the explicit --trial-start/--trial-end window",
    )
    trial_mode.add_argument(
        "--check-trial",
        action="store_true",
        help="validate the content-addressed final trial receipt and inactive marker",
    )
    parser.add_argument(
        "--trial-output",
        default=str(TRIAL_PATH),
        help="counts-only receipt path for --check-trial (finalization always uses the active marker owner)",
    )
    parser.add_argument(
        "--watch", action="store_true", help="run an attached loop; launchd should prefer one-shot mode"
    )
    parser.add_argument(
        "--interval", type=int, default=int(os.environ.get("LIMEN_OVERNIGHT_WATCH_INTERVAL_SEC", "300"))
    )
    parser.add_argument("--max-samples", type=int, default=0, help="watch-loop sample cap; 0 means forever")
    args = parser.parse_args(argv)

    if args.start_trial:
        paused_rc = stop_for_autonomy_pause(dry_run=False, json_output=args.json)
        if paused_rc is not None:
            return paused_rc
        try:
            marker, changed = start_trial()
        except TrialContractError as exc:
            print(f"overnight-watch: trial start FAIL - {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps({**marker, "changed": changed}, indent=2, sort_keys=True))
        else:
            print(
                "overnight-watch: trial "
                f"{'started' if changed else 'already-active'} "
                f"{marker.get('window_start')} -> {marker.get('window_end')}"
            )
        return 0

    if args.finalize_trial:
        result = maybe_finalize_trial()
        if result is None:
            print("overnight-watch: trial finalization FAIL - no active trial", file=sys.stderr)
            return 1
        if result.get("pending"):
            print(f"overnight-watch: trial pending until {result.get('window_end')}")
            return 10
        if result.get("error"):
            print(f"overnight-watch: trial finalization FAIL - {result['error']}", file=sys.stderr)
            return 1
        receipt = result["receipt"]
        changed = bool(result.get("changed"))
        if args.json:
            print(json.dumps({**receipt, "changed": changed}, indent=2, sort_keys=True))
        else:
            print(
                "overnight-watch: trial "
                f"pass={str(receipt.get('pass', False)).lower()} hours={receipt.get('hours')} "
                f"windows={receipt.get('window_count')} value={receipt.get('value_done_events')} "
                f"blockers={receipt.get('owner_blocked_events')} seams={receipt.get('seam_count')} "
                f"prompts={receipt.get('operator_interventions')} alerts={receipt.get('watch_alerts')} "
                f"changed={str(changed).lower()}"
            )
        return 0 if receipt.get("pass") else 1

    if args.check_trial:
        ok, errors = check_trial_receipt(Path(args.trial_output).expanduser())
        if ok:
            receipt = load_json(Path(args.trial_output).expanduser())
            print(
                "overnight-watch: trial receipt OK "
                f"hours={receipt.get('hours')} windows={receipt.get('window_count')} "
                f"value={receipt.get('value_done_events')} blockers={receipt.get('owner_blocked_events')} "
                f"seams={receipt.get('seam_count')}"
            )
            return 0
        for error in errors:
            print(f"overnight-watch: trial receipt FAIL - {error}", file=sys.stderr)
        return 1

    wall_s = _arm_wall_clock_bound()

    if not args.watch:
        if wall_s:
            signal.alarm(wall_s)
        rc = run_once(dry_run=args.dry_run, json_output=args.json)
        signal.alarm(0)
        return rc

    rss_cap_mb = float(os.environ.get("LIMEN_WATCH_RSS_MB", "512") or 0)
    samples = 0
    while True:
        paused_rc = stop_for_autonomy_pause(dry_run=args.dry_run, json_output=args.json)
        if paused_rc is not None:
            return paused_rc
        if wall_s:
            signal.alarm(wall_s)
        rc = run_once(dry_run=args.dry_run, json_output=args.json)
        signal.alarm(0)
        if rc:
            return rc
        samples += 1
        rss_mb = _rss_mb()
        if rss_cap_mb and rss_mb > rss_cap_mb:
            # Self-bound (issue #1148): a low-cost receipt writer holding this much
            # heap is accumulation — exit clean; the next invocation starts at ~100 MB.
            print(
                f"overnight-watch: RSS {rss_mb:.0f} MB > cap {rss_cap_mb:.0f} MB — "
                "exiting after receipts; launchd/StartInterval respawns fresh"
            )
            return 0
        if args.max_samples and samples >= args.max_samples:
            return 0
        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
