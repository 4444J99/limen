#!/usr/bin/env python3
"""Verify safe containment or the evolved Rule-#55a one-shot heartbeat."""

from __future__ import annotations

import os
from pathlib import Path
import plistlib
import re
import subprocess


HEARTBEAT_LABEL = "com.limen.heartbeat"
WATCHDOG_LABEL = "com.limen.watchdog"
HEARTBEAT_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{HEARTBEAT_LABEL}.plist"
WATCHDOG_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{WATCHDOG_LABEL}.plist"
PUBLIC_RECEIPT = Path.home() / ".local" / "share" / "limen" / "heartbeat" / "public-latest.json"
PROCESS_PATTERNS = (
    "scripts/heartbeat-loop.sh",
    "scripts/watchdog.py",
    "fast-wave",
    "host-pressure-watchdog",
)


def _resident_pids() -> list[int]:
    pids: set[int] = set()
    for pattern in PROCESS_PATTERNS:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        pids.update(int(value) for value in result.stdout.split() if value.isdigit())
    return sorted(pids)


def _label_loaded(label: str) -> bool:
    result = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{label}"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return result.returncode == 0


def _legacy_findings() -> list[str]:
    findings = []
    if _label_loaded(WATCHDOG_LABEL):
        findings.append(f"label:{WATCHDOG_LABEL}")
    if os.path.lexists(WATCHDOG_PLIST):
        findings.append(f"plist:{WATCHDOG_PLIST.name}")
    pids = _resident_pids()
    if pids:
        findings.append(f"processes:{len(pids)}")
    return findings


def _one_shot_findings() -> list[str]:
    findings = _legacy_findings()
    loaded = _label_loaded(HEARTBEAT_LABEL)
    installed = os.path.lexists(HEARTBEAT_PLIST)
    if loaded != installed:
        findings.append("heartbeat-label-plist-partial")
        return findings
    if not loaded:
        return findings
    if HEARTBEAT_PLIST.is_symlink() or not HEARTBEAT_PLIST.is_file():
        findings.append("heartbeat-plist-unsafe")
        return findings
    try:
        with HEARTBEAT_PLIST.open("rb") as handle:
            plist = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException):
        findings.append("heartbeat-plist-unreadable")
        return findings
    arguments = plist.get("ProgramArguments") or []
    checks = {
        "keepalive": plist.get("KeepAlive", False) is False,
        "runatload": plist.get("RunAtLoad", False) is False,
        "interval": isinstance(plist.get("StartInterval"), int) and plist["StartInterval"] >= 300,
        "process-type": plist.get("ProcessType") == "Background",
        "low-priority-io": plist.get("LowPriorityIO") is True,
        "nice": isinstance(plist.get("Nice"), int) and plist["Nice"] >= 5,
        "one-shot-command": len(arguments) >= 3 and arguments[1:] == ["heartbeat", "--once"],
    }
    findings.extend(f"contract:{name}" for name, passed in checks.items() if not passed)
    if checks["one-shot-command"]:
        match = re.search(r"/runtimes/([0-9a-f]{40})/venv/bin/limen$", arguments[0])
        if not match:
            findings.append("runtime-not-immutable")
        else:
            try:
                import json

                receipt = json.loads(PUBLIC_RECEIPT.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                findings.append("receipt-unreadable")
            else:
                if receipt.get("runtime_sha") != match.group(1):
                    findings.append("runtime-sha-drift")
    return findings


def main() -> int:
    if os.environ.get("LIMEN_BEAT_FRESHNESS", "1") == "0":
        print("  beat-freshness: gated off (LIMEN_BEAT_FRESHNESS=0) — skip")
        return 0
    findings = _one_shot_findings()
    if findings:
        print(
            "  beat-freshness: FAIL — heartbeat safety contract is not proven "
            f"({', '.join(findings)}); run domus-limen-runtime verify-heartbeat"
        )
        return 1
    state = "active one-shot" if os.path.lexists(HEARTBEAT_PLIST) else "safely contained"
    print(f"  beat-freshness: OK — heartbeat {state}; no legacy resident descendants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
