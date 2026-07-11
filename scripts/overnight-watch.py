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
import datetime as dt
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
LOGS = ROOT / "logs"
HEARTBEAT_LOG = LOGS / "heartbeat.out.log"
ASYNC_RUNS = LOGS / "async-runs"
STATE_PATH = Path(os.environ.get("LIMEN_OVERNIGHT_WATCH_STATE", LOGS / "overnight-watch-state.json"))
RECEIPT_JSONL = Path(os.environ.get("LIMEN_OVERNIGHT_WATCH_RECEIPT", LOGS / "overnight-watch.jsonl"))
RECEIPT_MD = LOGS / "overnight-watch.md"
ALERT_PATH = Path(os.environ.get("LIMEN_OVERNIGHT_WATCH_ALERT", LOGS / "overnight-watch-alert.json"))
TOKEN_REPORT = Path(os.environ.get("LIMEN_CODEX_TOKEN_REPORT", LOGS / "codex-token-report.json"))
HANDOFF_SCRIPT = ROOT / "scripts" / "handoff-relay.py"
SESSION_VALUE_SCRIPT = ROOT / "scripts" / "session-value-review.py"
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
VITALS_SKIP_MARKER = "vitals-pressure: dispatch skipped"
TAIL_BYTES = 192 * 1024

EXPECT_DISPATCH_ASYNC = os.environ.get("LIMEN_OVERNIGHT_WATCH_EXPECT_DISPATCH_ASYNC", "")
EXPECT_DISPATCH_LANES = os.environ.get("LIMEN_OVERNIGHT_WATCH_EXPECT_DISPATCH_LANES", "")
try:
    VALUE_GATE_HOURS = float(os.environ.get("LIMEN_OVERNIGHT_VALUE_GATE_HOURS", "1.5") or "1.5")
except ValueError:
    VALUE_GATE_HOURS = 1.5

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
        lines = TICKS_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for line in lines:
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
    exists AND no sanctioned suppression explains the quiet (governor pause, vitals shed,
    budget exhaustion, dispatch gate). Sanctioned quiet is surfaced as `suppressed`, never
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
    elif VITALS_SKIP_MARKER in tail_text(HEARTBEAT_LOG):
        result["suppressed"] = "vitals-critical-shed"
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


def build_snapshot(*, refresh_handoff: bool = True, record_gate: bool = True) -> dict[str, Any]:
    text = tail_text(HEARTBEAT_LOG)
    heartbeat = parse_heartbeat(text)
    previous = load_json(STATE_PATH)
    stale_count = next_stale_count(previous, heartbeat.get("latest_tick"))
    workers = active_workers()
    launchd = launchd_snapshot()
    children = heartbeat_child_processes(launchd.get("pid"))

    snapshot: dict[str, Any] = {
        "timestamp": iso_now(),
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
    }
    snapshot["handoff_relay"] = handoff_relay_snapshot(refresh=refresh_handoff)
    snapshot["value_gate"] = session_value_gate_snapshot(record_gate=record_gate)
    snapshot["dispatch_control"] = dispatch_control(snapshot)
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
        "next_command": dispatch.get("next_command") or "",
    }


def evaluate(snapshot: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    alerts: list[dict[str, str]] = []
    launchd = snapshot.get("launchd") or {}
    env = launchd.get("env") if isinstance(launchd.get("env"), dict) else {}
    handoff = snapshot.get("handoff_relay") if isinstance(snapshot.get("handoff_relay"), dict) else {}
    value_gate = snapshot.get("value_gate") if isinstance(snapshot.get("value_gate"), dict) else {}
    dispatch = snapshot.get("dispatch_control") if isinstance(snapshot.get("dispatch_control"), dict) else {}

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
    if gate_rc >= 20:
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
    RECEIPT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT_JSONL.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, sort_keys=True) + "\n")


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
        f"- Next command: `{counts.get('next_command') or 'none'}`.",
        "",
        "## Gate Checks",
        "",
        f"- Handoff refresh: `{handoff.get('refresh_returncode')}`; check: `{handoff.get('check_returncode')}`.",
        f"- Value gate: `{value_gate.get('returncode')}`; action: `{value_gate.get('action')}`.",
        f"- Dispatch control: {dispatch.get('reason', 'dispatch allowed')}.",
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


def run_once(*, dry_run: bool, json_output: bool) -> int:
    snapshot = build_snapshot(refresh_handoff=not dry_run, record_gate=not dry_run)
    if not dry_run:
        heal_actions = heal(snapshot)
        if heal_actions:
            snapshot["heal"] = heal_actions
        write_receipts(snapshot)
    if json_output:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    else:
        print_summary(snapshot)
    if snapshot.get("status") == "alert":
        return 1
    if snapshot.get("status") == "blocked":
        return int((snapshot.get("dispatch_control") or {}).get("exit_code") or 10)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="inspect without writing receipts")
    parser.add_argument("--json", action="store_true", help="print the full snapshot")
    parser.add_argument(
        "--watch", action="store_true", help="run an attached loop; launchd should prefer one-shot mode"
    )
    parser.add_argument(
        "--interval", type=int, default=int(os.environ.get("LIMEN_OVERNIGHT_WATCH_INTERVAL_SEC", "300"))
    )
    parser.add_argument("--max-samples", type=int, default=0, help="watch-loop sample cap; 0 means forever")
    args = parser.parse_args(argv)

    if not args.watch:
        return run_once(dry_run=args.dry_run, json_output=args.json)

    samples = 0
    while True:
        rc = run_once(dry_run=args.dry_run, json_output=args.json)
        if rc:
            return rc
        samples += 1
        if args.max_samples and samples >= args.max_samples:
            return 0
        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
