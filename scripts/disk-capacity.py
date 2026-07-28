#!/usr/bin/env python3
"""disk-capacity.py — telemetry-backed beat sensor for disk pressure.

The gap this closes: disk-full was a silent failure mode — worktrees and artifacts
accumulated until the host ran out of space, stalling the fleet with zero beat-visible
signal. This sensor makes disk headroom a continuous-runtime invariant: green
means live free bytes cover the selected task graph's resource envelope.

Two modes:

  --check   advisory gate: exits 1 when free space is below the live resource
            envelope or when required telemetry is unavailable on the live host.
            PII-clean: only numeric readings and the volume path are printed.

  --apply   safety effector (armed via LIMEN_DISK_CAPACITY_APPLY=1 in sensors.yaml):
            1. Removes git-check-ignored .heal-probe-*.yaml artifacts under LIMEN_ROOT
               (safe: these are gitignored transient probes; removing is always safe).
            2. Truncates logs/heartbeat.err.log when it exceeds LIMEN_DISK_LOG_CAP_MB
               (default 50 MiB) — the log file that most commonly grows unbounded.
            Writes a JSON receipt to logs/disk-capacity-apply.json.

Exit codes: 0 = ok; 1 = envelope breached (--check) or effector error (--apply);
77 = the declared volume is unavailable under --strict.

Usage:
  python3 scripts/disk-capacity.py --check
  python3 scripts/disk-capacity.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("LIMEN_ROOT", SCRIPT_ROOT))
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.resource_envelope import current_required_free_gib  # noqa: E402

VOLUME = "/System/Volumes/Data"
DEFAULT_LOG_CAP_MB = 50  # truncate heartbeat.err.log when it exceeds this
HEARTBEAT_ERR_LOG = ROOT / "logs" / "heartbeat.err.log"
RECEIPT_PATH = ROOT / "logs" / "disk-capacity-apply.json"


def _free_gib(volume: str = VOLUME) -> float | None:
    """Return live free GiB for the exact mounted volume."""

    try:
        return shutil.disk_usage(volume).free / (1024**3)
    except OSError:
        return None


def check(*, strict: bool = False) -> int:
    free_gib = _free_gib()
    if free_gib is None:
        # Volume absent (CI / non-macOS / VM) — fail open.
        print(f"disk-capacity: volume {VOLUME!r} not found — check skipped (fail-open)")
        return 77 if strict else 0
    try:
        required_gib = current_required_free_gib()
    except (RuntimeError, ValueError):
        print("disk-capacity: resource envelope unavailable — live check failed closed")
        return 1
    print(f"disk-capacity: {VOLUME} free {free_gib:.3f} GiB (required {required_gib:.3f} GiB)")
    if free_gib < required_gib:
        print(
            f"  ↑ disk-capacity BREACHED — {free_gib:.3f} GiB free is below "
            f"{required_gib:.3f} GiB required; "
            f"arm LIMEN_DISK_CAPACITY_APPLY=1 so the beat removes gitignored probes "
            f"and truncates the heartbeat error log"
        )
        return 1
    return 0


def _remove_heal_probes() -> tuple[int, list[str]]:
    """Remove git-check-ignored .heal-probe-*.yaml artifacts under ROOT."""
    removed: list[str] = []
    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--ignored", "--exclude-standard", "-z"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(ROOT),
        )
        candidates = result.stdout.split("\0") if result.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired):
        candidates = []

    for rel in candidates:
        if not rel:
            continue
        if Path(rel).name.startswith(".heal-probe-") and rel.endswith(".yaml"):
            target = ROOT / rel
            try:
                target.unlink()
                removed.append(rel)
            except OSError:
                pass
    return len(removed), removed


def _truncate_log(path: Path, cap_mb: int) -> tuple[bool, int | None]:
    """Truncate *path* to zero bytes when it exceeds *cap_mb* MiB.

    Returns (truncated: bool, size_before_bytes: int | None).
    """
    try:
        size = path.stat().st_size
    except OSError:
        return False, None
    cap_bytes = cap_mb * 1024 * 1024
    if size <= cap_bytes:
        return False, size
    try:
        path.write_text("", encoding="utf-8")
        return True, size
    except OSError:
        return False, size


def apply(log_cap_mb: int) -> int:
    probe_count, probe_paths = _remove_heal_probes()
    truncated, log_size = _truncate_log(HEARTBEAT_ERR_LOG, log_cap_mb)

    receipt: dict = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "heal_probes_removed": probe_count,
        "heal_probes": probe_paths,
        "heartbeat_err_log": str(HEARTBEAT_ERR_LOG),
        "heartbeat_err_log_size_bytes_before": log_size,
        "heartbeat_err_log_truncated": truncated,
    }

    try:
        RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
        RECEIPT_PATH.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"disk-capacity --apply: could not write receipt: {exc}", file=sys.stderr)
        return 1

    print(
        f"disk-capacity --apply: removed {probe_count} heal-probe artifact(s); "
        f"heartbeat.err.log truncated={truncated} (was {log_size} bytes); "
        f"receipt -> {RECEIPT_PATH.relative_to(ROOT)}"
    )
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="disk-capacity beat sensor — check + optional effector")
    ap.add_argument(
        "--check",
        action="store_true",
        help="advisory check: exit 1 when free space is below the live envelope",
    )
    ap.add_argument("--strict", action="store_true", help="exit 77 when the declared volume is unavailable")
    ap.add_argument("--apply", action="store_true", help="safety effector: remove probes + truncate log")
    ap.add_argument(
        "--log-cap-mb",
        type=int,
        default=int(os.environ.get("LIMEN_DISK_LOG_CAP_MB", DEFAULT_LOG_CAP_MB)),
        help=f"truncate heartbeat.err.log above this many MiB (default {DEFAULT_LOG_CAP_MB})",
    )
    args = ap.parse_args(argv)

    if args.check:
        return check(strict=args.strict)
    if args.apply:
        return apply(args.log_cap_mb)

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
