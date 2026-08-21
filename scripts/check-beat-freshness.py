#!/usr/bin/env python3
"""Compatibility predicate for the retired resident heartbeat.

Freshness now comes from immutable content digests in ``limen observe --once`` receipts.
This check passes only when both retired labels, installed plists, and legacy
process descendants are absent.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess


LABELS = ("com.limen.heartbeat", "com.limen.watchdog")
PLISTS = (
    Path.home() / "Library" / "LaunchAgents" / "com.limen.heartbeat.plist",
    Path.home() / "Library" / "LaunchAgents" / "com.limen.watchdog.plist",
)
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


def _retirement_findings() -> list[str]:
    findings = [f"label:{label}" for label in LABELS if _label_loaded(label)]
    findings.extend(f"plist:{path.name}" for path in PLISTS if path.exists())
    pids = _resident_pids()
    if pids:
        findings.append(f"processes:{len(pids)}")
    return findings


def main() -> int:
    if os.environ.get("LIMEN_BEAT_FRESHNESS", "1") == "0":
        print("  beat-freshness: gated off (LIMEN_BEAT_FRESHNESS=0) — skip")
        return 0
    findings = _retirement_findings()
    if findings:
        print(
            "  beat-freshness: FAIL — heartbeat retirement incomplete "
            f"({', '.join(findings)}); run domus-limen-runtime retire-heartbeat"
        )
        return 1
    print("  beat-freshness: OK — heartbeat retired; observer receipts carry content digests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
