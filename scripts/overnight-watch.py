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
LABEL = os.environ.get("LIMEN_HEARTBEAT_LABEL", os.environ.get("LIMEN_LAUNCHD_LABEL", "com.limen.heartbeat"))

MAX_LOG_AGE_SEC = int(os.environ.get("LIMEN_OVERNIGHT_WATCH_MAX_LOG_AGE_SEC", "1200") or "1200")
MAX_STALE_TICKS = int(os.environ.get("LIMEN_OVERNIGHT_WATCH_MAX_STALE_TICKS", "6") or "6")
TAIL_BYTES = 192 * 1024

EXPECT_DISPATCH_ASYNC = os.environ.get("LIMEN_OVERNIGHT_WATCH_EXPECT_DISPATCH_ASYNC", "")
EXPECT_DISPATCH_LANES = os.environ.get("LIMEN_OVERNIGHT_WATCH_EXPECT_DISPATCH_LANES", "")

TICK_RE = re.compile(r"tick emitted:\s*(?P<ts>\S+).*?\btotal=(?P<total>\d+)\s+open=(?P<open>\d+)\s+spent=(?P<spent>\S+)")
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


def next_stale_count(previous: dict[str, Any], tick: dict[str, Any] | None) -> int:
    current = tick.get("timestamp") if tick else None
    if current and current != previous.get("latest_tick"):
        return 0
    return int(previous.get("stale_tick_count") or 0) + 1


def build_snapshot() -> dict[str, Any]:
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
    snapshot["status"], snapshot["alerts"] = evaluate(snapshot)
    return snapshot


def evaluate(snapshot: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    alerts: list[dict[str, str]] = []
    launchd = snapshot.get("launchd") or {}
    env = launchd.get("env") if isinstance(launchd.get("env"), dict) else {}

    if not launchd.get("ok") or launchd.get("state") not in (None, "active", "running"):
        alerts.append({"id": "heartbeat-launchd-not-running", "evidence": f"state={launchd.get('state')} error={launchd.get('error')}"})

    log_age_sec = snapshot.get("log_age_sec")
    if log_age_sec is None:
        alerts.append({"id": "heartbeat-log-missing", "evidence": str(HEARTBEAT_LOG)})
    elif int(log_age_sec) > MAX_LOG_AGE_SEC:
        alerts.append({"id": "heartbeat-log-stale", "evidence": f"log_age_sec={log_age_sec} threshold={MAX_LOG_AGE_SEC}"})

    latest_tick = (snapshot.get("heartbeat") or {}).get("latest_tick")
    if not latest_tick:
        alerts.append({"id": "heartbeat-tick-missing", "evidence": "no tick emitted line found in recent heartbeat log"})
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

    return ("alert" if alerts else "ok"), alerts


def update_state(snapshot: dict[str, Any]) -> None:
    tick = (snapshot.get("heartbeat") or {}).get("latest_tick") or {}
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(
            {
                "updated_at": snapshot.get("timestamp"),
                "latest_tick": tick.get("timestamp"),
                "stale_tick_count": snapshot.get("stale_tick_count", 0),
                "status": snapshot.get("status"),
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
    lines = [
        "# Overnight Watch",
        "",
        f"- Status: `{snapshot.get('status')}`",
        f"- Updated: `{snapshot.get('timestamp')}`",
        f"- Log age: `{snapshot.get('log_age_sec')}` seconds",
        f"- Launchd: `{launchd.get('state')}` pid `{launchd.get('pid')}`",
        f"- Latest beat: `{heartbeat.get('latest_beat')}`",
        f"- Latest tick: `{tick.get('raw')}`",
        f"- Latest async: `{async_line.get('raw')}`",
        f"- Stale tick samples: `{snapshot.get('stale_tick_count')}`",
        f"- Active workers: `{len(workers)}`",
        f"- Heartbeat child processes: `{len(children)}`",
    ]
    for worker in workers[:10]:
        lines.append(f"  - `{worker.get('name')}` age `{worker.get('age_sec')}` seconds")
    for child in children[:10]:
        lines.append(
            f"  - child `{child.get('pid')}` `{child.get('stat')}` "
            f"`{child.get('etime')}` `{child.get('command')}`"
        )
    if snapshot.get("alerts"):
        lines.extend(["", "## WATCH_ALERT"])
        for alert in snapshot["alerts"]:
            lines.append(f"- `{alert['id']}`: {alert['evidence']}")
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
    for alert in snapshot.get("alerts") or []:
        print(f"  WATCH_ALERT {alert['id']}: {alert['evidence']}")


def run_once(*, dry_run: bool, json_output: bool) -> int:
    snapshot = build_snapshot()
    if not dry_run:
        write_receipts(snapshot)
    if json_output:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    else:
        print_summary(snapshot)
    return 1 if snapshot.get("status") == "alert" else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="inspect without writing receipts")
    parser.add_argument("--json", action="store_true", help="print the full snapshot")
    parser.add_argument("--watch", action="store_true", help="run an attached loop; launchd should prefer one-shot mode")
    parser.add_argument("--interval", type=int, default=int(os.environ.get("LIMEN_OVERNIGHT_WATCH_INTERVAL_SEC", "300")))
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
