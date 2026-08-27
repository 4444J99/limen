#!/usr/bin/env python3
"""Install or verify the processless local notification one-shot schedule."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path


BEGIN = "# BEGIN LIMEN NOTIFICATION ONE-SHOT v1"
END = "# END LIMEN NOTIFICATION ONE-SHOT v1"
DEFAULT_INTERVAL = "*/10 * * * *"
STATE_ROOT = Path(os.environ.get("LIMEN_NOTIFICATION_STATE_DIR", Path.home() / ".local/state/limen"))
RECEIPT = STATE_ROOT / "notification-schedule.json"


def _paths() -> tuple[Path, Path]:
    runtime = Path(
        os.environ.get("LIMEN_IMMUTABLE_RUNTIME", Path.home() / ".local/share/limen/current")
    ).expanduser()
    live_root = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace/limen")).expanduser()
    return runtime, live_root


def expected_block() -> str:
    runtime, live_root = _paths()
    python = runtime / "venv/bin/python"
    one_shot = runtime / "source/scripts/notification-one-shot.py"
    path = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
    command = " ".join(
        [
            f"PATH={shlex.quote(path)}",
            f"LIMEN_ROOT={shlex.quote(str(live_root))}",
            shlex.quote(str(python)),
            shlex.quote(str(one_shot)),
            ">/dev/null 2>&1",
        ]
    )
    interval = os.environ.get("LIMEN_NOTIFICATION_CRON", DEFAULT_INTERVAL)
    return f"{BEGIN}\n{interval} {command}\n{END}"


def replace_block(existing: str, block: str) -> str:
    lines = existing.splitlines()
    begin = [index for index, line in enumerate(lines) if line == BEGIN]
    end = [index for index, line in enumerate(lines) if line == END]
    if len(begin) != len(end) or len(begin) > 1:
        raise ValueError("notification schedule markers are corrupt")
    if begin and begin[0] >= end[0]:
        raise ValueError("notification schedule markers are reversed")
    if begin:
        lines = lines[: begin[0]] + lines[end[0] + 1 :]
    while lines and not lines[-1].strip():
        lines.pop()
    if lines:
        lines.append("")
    lines.extend(block.splitlines())
    return "\n".join(lines) + "\n"


def _read_crontab() -> str:
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False, timeout=10)
    if result.returncode == 0:
        return result.stdout
    if result.returncode == 1 and not result.stdout:
        return ""
    raise RuntimeError("crontab read failed")


def _plan() -> dict[str, object]:
    existing = _read_crontab()
    block = expected_block()
    proposed = replace_block(existing, block)
    digest = hashlib.sha256(proposed.encode()).hexdigest()
    runtime, live_root = _paths()
    return {
        "schema": "limen.notification_schedule_plan.v1",
        "plan_sha256": digest,
        "changed": proposed != existing,
        "schedule": block,
        "runtime": str(runtime),
        "live_root": str(live_root),
        "proposed": proposed,
    }


def _write_receipt(payload: object) -> None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(prefix=".notification-schedule.", dir=STATE_ROOT)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        temporary.replace(RECEIPT)
        RECEIPT.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _apply(expected_digest: str) -> int:
    plan = _plan()
    if plan["plan_sha256"] != expected_digest:
        raise ValueError("notification schedule plan digest changed")
    descriptor, raw = tempfile.mkstemp(prefix="limen-notification-crontab-")
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(str(plan["proposed"]))
        result = subprocess.run(["crontab", str(temporary)], capture_output=True, text=True, check=False, timeout=10)
        if result.returncode != 0:
            raise RuntimeError("crontab install failed")
    finally:
        temporary.unlink(missing_ok=True)
    observed = _read_crontab()
    if observed != plan["proposed"]:
        raise RuntimeError("notification schedule readback mismatch")
    receipt = {key: value for key, value in plan.items() if key != "proposed"}
    receipt.update({"schema": "limen.notification_schedule_receipt.v1", "status": "installed"})
    _write_receipt(receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


def _status() -> int:
    block = expected_block()
    current = _read_crontab()
    runtime, _ = _paths()
    installed = block in current
    executable = (runtime / "venv/bin/python").is_file()
    one_shot = (runtime / "source/scripts/notification-one-shot.py").is_file()
    payload = {
        "schema": "limen.notification_schedule_status.v1",
        "installed": installed,
        "runtime_interpreter": executable,
        "one_shot": one_shot,
        "complete": installed and executable and one_shot,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["complete"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--status", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-plan-sha256")
    arguments = parser.parse_args(argv)
    try:
        if arguments.status:
            return _status()
        if arguments.apply:
            if not arguments.expected_plan_sha256:
                parser.error("--apply requires --expected-plan-sha256")
            return _apply(arguments.expected_plan_sha256)
        plan = _plan()
        plan.pop("proposed", None)
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"notification-schedule: {exc}", file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
