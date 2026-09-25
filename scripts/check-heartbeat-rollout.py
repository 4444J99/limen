#!/usr/bin/env python3
"""Verify the evolved heartbeat's 44-rung ownership and live receipt proof."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import time
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OWNERSHIP = ROOT / "institutio" / "governance" / "heartbeat-ownership.json"
CONTRACTS = ROOT / "spec" / "scheduled-process-contracts.json"
OBSERVER = ROOT / "cli" / "src" / "limen" / "observer.py"
EXPECTED_RUNG_COUNT = 44
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


def active_errors(receipts_dir: Path, expected_sha: str, min_fires: int, *, now: float | None = None) -> list[str]:
    errors: list[str] = []
    receipts: list[dict[str, Any]] = []
    now = time.time() if now is None else now
    for path in sorted(receipts_dir.glob("*.json")):
        try:
            payload = _load_json(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: unreadable receipt: {exc}")
            continue
        epoch = payload.get("observed_epoch")
        if type(epoch) not in (int, float) or not 0 < epoch <= now or not math.isfinite(epoch):
            errors.append(f"{path.name}: invalid or future receipt timestamp")
            continue
        receipts.append(payload)
    receipts.sort(key=lambda row: (float(row.get("observed_epoch", 0)), str(row.get("run_id", ""))))
    selected = receipts[-min_fires:]
    if len(selected) < min_fires:
        errors.append(f"recorded fires are {len(selected)}, expected at least {min_fires}")
        return errors
    contract = _load_json(CONTRACTS)["processes"]["com.limen.heartbeat"]
    interval = contract["launchd"]["start_interval_seconds"]
    maximum_age = interval + contract["limits"]["wall_seconds_per_tick"]
    if now - selected[-1]["observed_epoch"] > maximum_age:
        errors.append(f"latest receipt is stale: age exceeds {maximum_age}s")
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


def scheduled_probe_report(receipts_dir: Path, expected_sha: str, *, now: float | None = None) -> dict[str, Any]:
    """Measure scheduled execution from current-runtime receipts, never retired voice stamps."""
    now = time.time() if now is None else now
    contract = _load_json(CONTRACTS)["processes"]["com.limen.heartbeat"]
    probes = {probe["name"]: probe for probe in contract["probes"]}
    latest: dict[str, dict[str, Any]] = {}
    malformed = 0
    for path in receipts_dir.glob("*.json"):
        try:
            row = _load_json(path)
        except (OSError, ValueError):
            malformed += 1
            continue
        epoch = row.get("observed_epoch")
        if type(epoch) not in (int, float) or not 0 < epoch <= now or not math.isfinite(epoch):
            malformed += 1
            continue
        name = row.get("probe")
        if row.get("runtime_sha") != expected_sha or not isinstance(name, str) or name not in probes:
            continue
        previous = latest.get(name)
        if previous is None or epoch > previous["observed_epoch"]:
            latest[name] = row
        elif epoch == previous["observed_epoch"] and row != previous:
            malformed += 1
    counts = {"observed": 0, "finding": 0, "missing": 0, "stale": 0, "unmeasured": 0}
    # One probe runs per fire. Allow one complete rotation after each declared cadence.
    rotation = len(probes) * contract["launchd"]["start_interval_seconds"]
    for name, probe in probes.items():
        row = latest.get(name)
        if row is None:
            counts["missing"] += 1
        elif now - row["observed_epoch"] > probe["cadence_seconds"] + rotation:
            counts["stale"] += 1
        elif (
            row.get("schema") != "limen.heartbeat_private_receipt.v1"
            or row.get("status") not in {"passed", "finding"}
            or type(row.get("returncode")) is not int
            or row["returncode"] < 0
            or (row["status"] == "passed") != (row["returncode"] == 0)
            or type(row.get("surviving_descendant_count")) is not int
            or row["surviving_descendant_count"] != 0
            or row.get("disabled") is not False
        ):
            counts["unmeasured"] += 1
        else:
            counts["observed"] += 1
            counts["finding"] += int(row["status"] == "finding")
    return {
        "scope": "scheduled_probe_execution",
        "scheduled_total": len(probes),
        "other_owners": "unmeasured_by_this_probe",
        "malformed_receipts": malformed,
        **counts,
        "execution_complete": counts["observed"] == len(probes) and malformed == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry-only", action="store_true")
    parser.add_argument("--require-active", action="store_true")
    parser.add_argument("--scheduled-probes", action="store_true")
    parser.add_argument("--expected-sha")
    parser.add_argument("--min-fires", type=int, default=3)
    parser.add_argument(
        "--receipts-dir",
        type=Path,
        default=Path.home() / ".local" / "share" / "limen" / "heartbeat" / "receipts",
    )
    args = parser.parse_args()
    if sum((args.registry_only, args.require_active, args.scheduled_probes)) > 1:
        parser.error("select only one verification mode")
    if args.require_active and not args.expected_sha:
        parser.error("--require-active needs --expected-sha")
    if args.min_fires < 1:
        parser.error("--min-fires must be positive")

    errors = registry_errors()
    if args.scheduled_probes and not errors:
        expected_sha = args.expected_sha
        if not expected_sha:
            try:
                expected_sha = _load_json(ROOT.parent / "receipt.json")["sha"]
            except (OSError, ValueError, KeyError):
                print("heartbeat-rollout: UNMEASURED — installed runtime identity unavailable")
                return 1
        if (
            not isinstance(expected_sha, str)
            or len(expected_sha) != 40
            or any(char not in "0123456789abcdef" for char in expected_sha)
        ):
            print("heartbeat-rollout: UNMEASURED — invalid runtime identity")
            return 1
        report = scheduled_probe_report(args.receipts_dir.expanduser(), expected_sha)
        print(json.dumps(report, sort_keys=True))
        return 0 if report["execution_complete"] else 1
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
