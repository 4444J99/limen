"""Bounded, read-only, one-shot observation runtime."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from limen.bounded_subprocess import BoundedSubprocessError, run_bounded_subprocess


PROBE_STDOUT_CEILING = 256 * 1024
PROBE_STDERR_CEILING = 256 * 1024


def _digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _boot_identity() -> str:
    try:
        result = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True, text=True, timeout=3)
        if result.returncode != 0 or not result.stdout.strip():
            return "unavailable"
        return hashlib.sha256(result.stdout.strip().encode()).hexdigest()[:20]
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def _run(command: list[str], *, cwd: Path, timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = run_bounded_subprocess(
            command,
            cwd=cwd,
            timeout_seconds=timeout,
            stdout_ceiling=PROBE_STDOUT_CEILING,
            stderr_ceiling=PROBE_STDERR_CEILING,
        )
    except BoundedSubprocessError as exc:
        status = "timed_out" if exc.kind == "timeout" else "failed"
        return {
            "status": status,
            "returncode": None,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "output_bytes": None,
            "failure_kind": exc.kind,
        }
    return {
        "status": "passed" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "duration_ms": round((time.monotonic() - started) * 1000),
        "output_bytes": len(result.stdout) + len(result.stderr),
    }


HOST_PROBES = [
    ("harness-root-probe", [sys.executable, "scripts/harness-root-probe.py"], 30),
    (
        "background-items-census",
        [sys.executable, "scripts/background-items-census.py", "--check", "--no-receipt"],
        30,
    ),
    ("sensor-canary", [sys.executable, "scripts/beat-sensors.py", "--canary"], 30),
    ("orphan-watcher", [sys.executable, "scripts/orphan-watchers.py", "--check"], 30),
    (
        "tcc-track-c",
        [sys.executable, "scripts/tcc-track-c-closeout.py", "--probe", "--json", "--no-write"],
        60,
    ),
    ("dialogs-silenced", ["bash", "scripts/dialogs-silenced.sh", "--agent-curable-only"], 30),
    (
        "cloud-storage-doctor",
        [sys.executable, "scripts/cloud-storage-doctor.py", "--check", "--no-write"],
        60,
    ),
    ("horrevm-custody", [sys.executable, "scripts/horrevm-custody.py", "--status"], 60),
    (
        "live-checkout-currency",
        [sys.executable, "scripts/check-live-checkout.py", "--no-receipt"],
        60,
    ),
    ("hot-cache", ["bash", "scripts/verify-hot-cache.sh"], 30),
    ("residue-census", [sys.executable, "scripts/residue-census.py", "--check"], 60),
    ("notify-gate", [sys.executable, "scripts/check-notify-gate.py"], 30),
    ("host-pressure-freshness", [sys.executable, "scripts/host-pressure-stale.py", "--read-only"], 15),
    ("notification-registry-parity", [sys.executable, "scripts/check-notification-registry.py"], 20),
]

REMOTE_PROBES = [
    (
        "github-estate-census",
        [sys.executable, "scripts/github-estate-census.py", "--check-repositories", "--json"],
        120,
    ),
    ("github-actions-usage", [sys.executable, "scripts/gitvs.py", "usage", "--check", "--no-write"], 60),
    ("estate-audit-posture", [sys.executable, "scripts/estate-audit-posture.py", "--check"], 120),
    ("bifrons-portal", [sys.executable, "scripts/bifrons-organ.py", "--check"], 60),
    ("arca-freshness", [sys.executable, "scripts/arca-freshness.py"], 60),
    ("main-exact-head-ci", [sys.executable, "scripts/check-main-green.py", "--exact-head-check"], 45),
    ("github-estate-parity", [sys.executable, "scripts/gitvs.py", "doctor", "--parity-only"], 45),
]


def observe_once(root: Path, scope: str) -> dict[str, Any]:
    probes = {
        "host": HOST_PROBES,
        "remote": REMOTE_PROBES,
    }
    selected = (
        probes["host"]
        if scope == "host"
        else probes["remote"]
        if scope == "remote"
        else probes["host"] + probes["remote"]
    )
    results = {name: _run(command, cwd=root, timeout=timeout) for name, command, timeout in selected}
    counts = {
        state: sum(1 for result in results.values() if result["status"] == state)
        for state in ("passed", "failed", "timed_out")
    }
    runtime_files = {Path(__file__)}
    for _, command, _ in selected:
        for argument in command[1:]:
            candidate = root / argument
            if argument.startswith("scripts/") and candidate.is_file():
                runtime_files.add(candidate)
    receipt = {
        "schema": "limen.observe_once.v1",
        "scope": scope,
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "boot_identity": _boot_identity(),
        "monotonic_seconds": round(time.monotonic(), 3),
        "wake_state": "FullWake",
        "counts": counts,
        "probe_count": len(results),
        "runtime_content_digest": hashlib.sha256(
            json.dumps(
                {
                    str(path.relative_to(root)) if path.is_relative_to(root) else str(path): _digest(path)
                    for path in sorted(runtime_files)
                },
                sort_keys=True,
            ).encode()
        ).hexdigest(),
    }
    receipt_path = Path(os.environ.get("LIMEN_OBSERVE_RECEIPT", root / "logs" / "observe-once.json"))
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = receipt_path.with_suffix(f"{receipt_path.suffix}.tmp.{os.getpid()}")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, receipt_path)
    receipt["failures"] = {
        name: {key: result.get(key) for key in ("status", "returncode", "failure_kind") if result.get(key) is not None}
        for name, result in results.items()
        if result["status"] != "passed"
    }
    return receipt
