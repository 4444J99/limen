#!/usr/bin/env python3
"""Verify the evolved heartbeat's 43-rung ownership and live receipt proof."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OWNERSHIP = ROOT / "institutio" / "governance" / "heartbeat-ownership.json"
CONTRACTS = ROOT / "spec" / "scheduled-process-contracts.json"
OBSERVER = ROOT / "cli" / "src" / "limen" / "observer.py"
EXPECTED_RUNG_COUNT = 43
ALLOWED_OWNERS = {
    "cloud_or_broker",
    "explicit_maintenance",
    "observe_host",
    "observe_remote",
    "scheduled_contract",
}
ACCEPTABLE_ACTIVE_STATUSES = {"passed", "finding", "deferred", "idle", "coalesced"}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: root must be an object")
    return payload


def _load_observer() -> Any:
    cli_src = str(ROOT / "cli" / "src")
    if cli_src not in sys.path:
        sys.path.insert(0, cli_src)
    spec = importlib.util.spec_from_file_location("limen_rollout_observer", OBSERVER)
    if spec is None or spec.loader is None:
        raise RuntimeError("observer module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def registry_errors() -> list[str]:
    errors: list[str] = []
    rungs = _load_json(OWNERSHIP).get("rungs")
    if not isinstance(rungs, dict):
        return ["heartbeat ownership registry has no rungs object"]
    if len(rungs) != EXPECTED_RUNG_COUNT:
        errors.append(f"rung denominator is {len(rungs)}, expected {EXPECTED_RUNG_COUNT}")

    observer = _load_observer()
    observer_probes = {
        "observe_host": {name: timeout for name, _command, timeout in observer.HOST_PROBES},
        "observe_remote": {name: timeout for name, _command, timeout in observer.REMOTE_PROBES},
    }
    scheduled = _load_json(CONTRACTS).get("processes", {}).get("com.limen.heartbeat")
    if not isinstance(scheduled, dict):
        errors.append("com.limen.heartbeat scheduled-process contract is absent")
    elif scheduled.get("mode") != "read_only_one_shot":
        errors.append("com.limen.heartbeat is not read_only_one_shot")

    scheduled_rungs: set[str] = set()
    for name, row in sorted(rungs.items()):
        if not isinstance(row, dict):
            errors.append(f"{name}: ownership row is malformed")
            continue
        owner = row.get("owner")
        if owner not in ALLOWED_OWNERS:
            errors.append(f"{name}: unsupported owner {owner!r}")
        for field in ("receipt", "predicate"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                errors.append(f"{name}: missing {field}")
        timeout = row.get("timeout_seconds")
        if not isinstance(timeout, int) or timeout <= 0:
            errors.append(f"{name}: invalid timeout")
        if owner in observer_probes:
            observed_timeout = observer_probes[owner].get(name)
            if observed_timeout is None:
                errors.append(f"{name}: absent from {owner} probes")
            elif observed_timeout != timeout:
                errors.append(f"{name}: observer timeout {observed_timeout} != owner timeout {timeout}")
        elif owner == "scheduled_contract":
            scheduled_rungs.add(name)

    if scheduled_rungs != {"launch-agent-liveness", "beat-freshness"}:
        errors.append(f"scheduled_contract rungs are {sorted(scheduled_rungs)}")
    return errors


def active_errors(receipts_dir: Path, expected_sha: str, min_fires: int) -> list[str]:
    errors: list[str] = []
    receipts: list[dict[str, Any]] = []
    for path in sorted(receipts_dir.glob("*.json")):
        try:
            payload = _load_json(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: unreadable receipt: {exc}")
            continue
        receipts.append(payload)
    receipts.sort(key=lambda row: (float(row.get("observed_epoch", 0)), str(row.get("run_id", ""))))
    selected = receipts[-min_fires:]
    if len(selected) < min_fires:
        errors.append(f"recorded fires are {len(selected)}, expected at least {min_fires}")
        return errors
    interval = _load_json(CONTRACTS)["processes"]["com.limen.heartbeat"]["launchd"]["start_interval_seconds"]
    for receipt in selected:
        run_id = receipt.get("run_id", "unknown")
        if receipt.get("runtime_sha") != expected_sha:
            errors.append(f"{run_id}: runtime SHA does not match {expected_sha}")
        if receipt.get("status") not in ACCEPTABLE_ACTIVE_STATUSES:
            errors.append(f"{run_id}: unacceptable status {receipt.get('status')!r}")
        if receipt.get("surviving_descendant_count") != 0:
            errors.append(f"{run_id}: surviving descendants are not zero")
        if receipt.get("disabled") is True:
            errors.append(f"{run_id}: runtime is disabled")
    for previous, current in zip(selected, selected[1:]):
        spacing = float(current.get("observed_epoch", 0)) - float(previous.get("observed_epoch", 0))
        if spacing < interval:
            errors.append(
                f"{previous.get('run_id', 'unknown')}->{current.get('run_id', 'unknown')}: "
                f"fire spacing {spacing:g}s is below {interval}s"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry-only", action="store_true")
    parser.add_argument("--require-active", action="store_true")
    parser.add_argument("--expected-sha")
    parser.add_argument("--min-fires", type=int, default=3)
    parser.add_argument(
        "--receipts-dir",
        type=Path,
        default=Path.home() / ".local" / "share" / "limen" / "heartbeat" / "receipts",
    )
    args = parser.parse_args()
    if args.registry_only and args.require_active:
        parser.error("--registry-only and --require-active are mutually exclusive")
    if args.require_active and not args.expected_sha:
        parser.error("--require-active needs --expected-sha")
    if args.min_fires < 1:
        parser.error("--min-fires must be positive")

    errors = registry_errors()
    if args.require_active:
        errors.extend(active_errors(args.receipts_dir.expanduser(), args.expected_sha, args.min_fires))
    if errors:
        print("heartbeat-rollout: FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    mode = "active" if args.require_active else "registry"
    print(f"heartbeat-rollout: PASS — {EXPECTED_RUNG_COUNT} rungs, {mode} proof satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
