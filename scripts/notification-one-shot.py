#!/usr/bin/env python3
"""Run the local Limen notification producers once with finite deadlines."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]
LIVE_ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen")).expanduser()
STATE_ROOT = Path(os.environ.get("LIMEN_NOTIFICATION_STATE_DIR", Path.home() / ".local/state/limen"))
RECEIPT = STATE_ROOT / "notification-one-shot.json"
LOCK = STATE_ROOT / "notification-one-shot.lock"
OUTPUT_LINES = 20


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _steps() -> list[tuple[str, list[str], int]]:
    python = sys.executable
    scripts = SOURCE_ROOT / "scripts"
    return [
        ("live-root", [python, str(scripts / "_root.py"), "--require-body"], 15),
        ("ships-24h", [python, str(scripts / "ships-24h-refresh.py")], 120),
        ("events", [python, str(scripts / "notify-events.py")], 30),
        ("diurnal", [python, str(scripts / "diurnal.py"), "--phase", "auto"], 240),
    ]


def _run_step(name: str, command: list[str], timeout: int, environment: dict[str, str]) -> dict[str, object]:
    started = _now()
    try:
        completed = subprocess.run(
            command,
            cwd=SOURCE_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = [line for line in (completed.stdout + completed.stderr).splitlines() if line]
        return {
            "name": name,
            "started_at": started,
            "finished_at": _now(),
            "returncode": completed.returncode,
            "output_tail": output[-OUTPUT_LINES:],
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        output = [line for line in str(exc.stdout or "").splitlines() if line]
        return {
            "name": name,
            "started_at": started,
            "finished_at": _now(),
            "returncode": 124,
            "output_tail": output[-OUTPUT_LINES:],
            "timed_out": True,
        }


def _status() -> int:
    try:
        payload = json.loads(RECEIPT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {"schema": "limen.notification_one_shot.v1", "status": "unavailable"}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("status") == "complete" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="print the latest private run receipt")
    parser.add_argument("--dry-run", action="store_true", help="print the bounded execution plan")
    arguments = parser.parse_args(argv)
    if arguments.status:
        return _status()
    plan = [
        {"name": name, "command": command, "timeout_seconds": timeout}
        for name, command, timeout in _steps()
    ]
    if arguments.dry_run:
        print(json.dumps({"schema": "limen.notification_one_shot_plan.v1", "steps": plan}, indent=2))
        return 0

    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 75
        environment = dict(os.environ)
        environment["LIMEN_ROOT"] = str(LIVE_ROOT)
        environment["LIMEN_DIURNAL_SHIP"] = "0"
        results: list[dict[str, object]] = []
        for name, command, timeout in _steps():
            result = _run_step(name, command, timeout, environment)
            results.append(result)
            if name == "live-root" and result["returncode"] != 0:
                break
        complete = len(results) == len(plan) and all(row["returncode"] == 0 for row in results)
        receipt = {
            "schema": "limen.notification_one_shot.v1",
            "observed_at": _now(),
            "status": "complete" if complete else "failed",
            "source_root": str(SOURCE_ROOT),
            "live_root": str(LIVE_ROOT),
            "steps": results,
        }
        _atomic_json(RECEIPT, receipt)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
