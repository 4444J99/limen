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
STATE_ROOT = Path(os.environ.get("LIMEN_NOTIFICATION_STATE_DIR", Path.home() / ".local/state/limen")).expanduser()
RECEIPT = STATE_ROOT / "notification-one-shot.json"
LOCK = STATE_ROOT / "notification-one-shot.lock"
FAILURE_STATE = STATE_ROOT / "notification-one-shot-failures.json"
OUTPUT_LINES = 20
MAX_CONSECUTIVE_FAILURES = 3


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
        ("ci-observation", [python, str(scripts / "check-main-green.py"), "--dry-run"], 90),
        ("host-observation", [python, str(scripts / "host-relief.py"), "--check", "--no-notify", "--json"], 30),
        ("events", [python, str(scripts / "notify-events.py"), "--apply"], 30),
        ("diurnal", [python, str(scripts / "diurnal.py"), "--phase", "auto"], 240),
    ]


def _run_step(name: str, command: list[str], timeout: int, environment: dict[str, str]) -> dict[str, object]:
    started = _now()
    try:
        executable = Path(command[0]).resolve()
        script = Path(command[1]).resolve()
        script.relative_to((SOURCE_ROOT / "scripts").resolve())
        if executable != Path(sys.executable).resolve() or script.suffix not in {".py", ".sh"}:
            raise ValueError("command is outside the immutable notification producer allowlist")
    except (IndexError, OSError, ValueError) as exc:
        return {
            "name": name,
            "started_at": started,
            "finished_at": _now(),
            "returncode": 126,
            "output_tail": [str(exc)],
            "timed_out": False,
            "producer_complete": False,
        }
    try:
        completed = subprocess.run(
            command,
            cwd=SOURCE_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
        output = [line for line in (completed.stdout + completed.stderr).splitlines() if line]
        return {
            "name": name,
            "started_at": started,
            "finished_at": _now(),
            "returncode": completed.returncode,
            "output_tail": output[-OUTPUT_LINES:],
            "timed_out": False,
            "producer_complete": _producer_complete(name, completed.returncode),
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
            "producer_complete": False,
        }


def _producer_complete(name: str, returncode: int) -> bool:
    if returncode != 0:
        return False
    if name != "ships-24h":
        return True
    cache = LIVE_ROOT / "logs" / "ships-24h.json"
    try:
        payload = json.loads(cache.read_text(encoding="utf-8"))
        generated_at = datetime.fromisoformat(str(payload["generated_at"]))
        if generated_at.tzinfo is None:
            generated_at = generated_at.astimezone()
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    age_seconds = (datetime.now(UTC) - generated_at.astimezone(UTC)).total_seconds()
    return payload.get("complete") is True and payload.get("error") is None and 0 <= age_seconds <= 2400


def _load_failure_state() -> dict[str, object]:
    try:
        payload = json.loads(FAILURE_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"consecutive_failures": 0}
    count = payload.get("consecutive_failures") if isinstance(payload, dict) else 0
    return {"consecutive_failures": count if isinstance(count, int) and count >= 0 else 0}


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
    parser.add_argument("--apply", action="store_true", help="acquire the local lease and run producer effects")
    parser.add_argument("--reset-failures", action="store_true", help="clear the consecutive-failure kill switch")
    arguments = parser.parse_args(argv)
    if arguments.status:
        return _status()
    plan = [{"name": name, "command": command, "timeout_seconds": timeout} for name, command, timeout in _steps()]
    if arguments.dry_run or not arguments.apply:
        print(
            json.dumps(
                {"schema": "limen.notification_one_shot_plan.v1", "apply_required": True, "steps": plan},
                indent=2,
            )
        )
        return 0

    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    if arguments.reset_failures:
        _atomic_json(FAILURE_STATE, {"consecutive_failures": 0, "reset_at": _now()})
        return 0
    failure_state = _load_failure_state()
    prior_failures = int(failure_state["consecutive_failures"])
    if prior_failures >= MAX_CONSECUTIVE_FAILURES:
        return 78
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
        complete = len(results) == len(plan) and all(
            row["returncode"] == 0 and row.get("producer_complete") is True for row in results
        )
        consecutive_failures = 0 if complete else prior_failures + 1
        kill_switch_active = consecutive_failures >= MAX_CONSECUTIVE_FAILURES
        _atomic_json(
            FAILURE_STATE,
            {
                "consecutive_failures": consecutive_failures,
                "kill_switch_active": kill_switch_active,
                "updated_at": _now(),
            },
        )
        runtime_sha = SOURCE_ROOT.parent.name if len(SOURCE_ROOT.parent.name) == 40 else None
        receipt = {
            "schema": "limen.notification_one_shot.v1",
            "observed_at": _now(),
            "status": "complete" if complete else "failed",
            "execution_lease": "local-exclusive-flock",
            "runtime_sha": runtime_sha,
            "source_root": str(SOURCE_ROOT),
            "live_root": str(LIVE_ROOT),
            "consecutive_failures": consecutive_failures,
            "kill_switch_active": kill_switch_active,
            "steps": results,
        }
        _atomic_json(RECEIPT, receipt)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
