"""Resource-bounded, launchd-safe one-shot heartbeat supervisor."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
from typing import Any, Callable

from limen.bounded_subprocess import BoundedSubprocessError, run_bounded_subprocess
from limen.host_admission import AdmissionController, AdmissionStateError


LABEL = "com.limen.heartbeat"
CONTRACT_RELATIVE_PATH = Path("spec/scheduled-process-contracts.json")
STATE_SCHEMA = "limen.heartbeat_state.v1"
PRIVATE_RECEIPT_SCHEMA = "limen.heartbeat_private_receipt.v1"
PUBLIC_RECEIPT_SCHEMA = "limen.heartbeat_public_receipt.v1"
SYSTEM_FAILURES = frozenset({"descendants", "invalid", "output", "resource", "timeout", "unavailable"})
Clock = Callable[[], float]


class HeartbeatContractError(RuntimeError):
    """The declared scheduled-process contract cannot be trusted."""


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_contract(root: Path) -> tuple[dict[str, Any], str]:
    path = root / CONTRACT_RELATIVE_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        contract = payload["processes"][LABEL]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HeartbeatContractError("scheduled-process contract is missing or malformed") from exc
    if payload.get("schema") != "limen.scheduled_process_contracts.v1" or not isinstance(contract, dict):
        raise HeartbeatContractError("scheduled-process contract schema is incompatible")
    launchd = contract.get("launchd") or {}
    limits = contract.get("limits") or {}
    failure = contract.get("failure_policy") or {}
    audit = contract.get("audit") or {}
    required = {
        "mode": contract.get("mode") == "read_only_one_shot",
        "irf": isinstance(contract.get("irf_id"), str) and contract["irf_id"].startswith("IRF-"),
        "keep_alive": launchd.get("keep_alive") is False,
        "run_at_load": launchd.get("run_at_load") is False,
        "process_type": launchd.get("process_type") == "Background",
        "low_priority_io": launchd.get("low_priority_io") is True,
        "nice": isinstance(launchd.get("nice"), int) and launchd["nice"] >= 5,
        "interval": isinstance(launchd.get("start_interval_seconds"), int) and launchd["start_interval_seconds"] >= 300,
        "throttle": launchd.get("throttle_interval_seconds") == launchd.get("start_interval_seconds"),
        "wall": isinstance(limits.get("wall_seconds_per_tick"), int) and 1 <= limits["wall_seconds_per_tick"] <= 300,
        "cpu": isinstance(limits.get("cpu_seconds_per_tick"), int)
        and 1 <= limits["cpu_seconds_per_tick"] <= limits.get("wall_seconds_per_tick", 0),
        "rss": isinstance(limits.get("rss_bytes"), int) and 1 <= limits["rss_bytes"] <= 536870912,
        "single": limits.get("max_concurrent_probes") == 1,
        "heavy": limits.get("max_heavy_probes_per_tick") == 1,
        "kill_switch": failure.get("consecutive_system_failures") == 3,
        "disable": failure.get("disable_with_launchctl") is True,
        "audit_stream": isinstance(audit.get("max_stream_bytes"), int) and 1 <= audit["max_stream_bytes"] <= 262144,
        "audit_receipts": isinstance(audit.get("max_receipts"), int) and 1 <= audit["max_receipts"] <= 96,
        "public_receipt": audit.get("public_receipt") == "public-latest.json",
    }
    failed = sorted(key for key, valid in required.items() if not valid)
    if failed:
        raise HeartbeatContractError("contract violates Rule #55a: " + ",".join(failed))
    probes = contract.get("probes")
    if not isinstance(probes, list) or not probes:
        raise HeartbeatContractError("contract declares no probes")
    names: set[str] = set()
    for probe in probes:
        if not isinstance(probe, dict):
            raise HeartbeatContractError("probe contract is malformed")
        name = probe.get("name")
        command = probe.get("command")
        timeout = probe.get("timeout_seconds")
        cadence = probe.get("cadence_seconds")
        if (
            not isinstance(name, str)
            or not name
            or name in names
            or not isinstance(command, list)
            or not command
            or not all(isinstance(value, str) and value for value in command)
            or probe.get("cost") not in {"cheap", "heavy"}
            or not isinstance(timeout, int)
            or timeout <= 0
            or timeout > limits["wall_seconds_per_tick"]
            or not isinstance(cadence, int)
            or cadence < launchd["start_interval_seconds"]
        ):
            raise HeartbeatContractError(f"probe contract is unsafe: {name!r}")
        if any(value in {"--apply", "--emit", "--live", "dispatch"} for value in command):
            raise HeartbeatContractError(f"probe is not read-only: {name}")
        names.add(name)
    required_fires = sum(86_400 / probe["cadence_seconds"] for probe in probes)
    available_fires = 86_400 / launchd["start_interval_seconds"]
    if math.ceil(required_fires) > math.floor(available_fires):
        raise HeartbeatContractError(
            f"probe cadences are unschedulable: need {math.ceil(required_fires)} fires/day, "
            f"have {math.floor(available_fires)}"
        )
    return contract, _sha256(path)


def _default_state_root() -> Path:
    configured = os.environ.get("LIMEN_HEARTBEAT_STATE_ROOT")
    return Path(configured).expanduser() if configured else Path.home() / ".local" / "share" / "limen" / "heartbeat"


def _initial_state() -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "consecutive_system_failures": 0,
        "disabled": False,
        "probes": {},
    }


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _initial_state()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HeartbeatContractError("heartbeat state is unreadable") from exc
    if (
        not isinstance(state, dict)
        or state.get("schema") != STATE_SCHEMA
        or not isinstance(state.get("consecutive_system_failures"), int)
        or not isinstance(state.get("disabled"), bool)
        or not isinstance(state.get("probes"), dict)
    ):
        raise HeartbeatContractError("heartbeat state schema is incompatible")
    return state


def _acquire_lock(state_root: Path, now: float) -> tuple[Path | None, str]:
    lock = state_root / "single-flight.lock"
    lock_nonce = uuid.uuid4().hex
    state_root.mkdir(parents=True, exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError:
        try:
            age = max(0.0, now - lock.stat().st_mtime)
        except OSError:
            return None, "lock-unreadable"
        if age <= 300:
            return None, "coalesced"
        try:
            shutil.rmtree(lock)
            lock.mkdir()
        except OSError:
            return None, "stale-lock-unrecoverable"
    _atomic_json(lock / "owner.json", {"pid": os.getpid(), "lock_nonce": lock_nonce})
    return lock, lock_nonce


def _release_lock(lock: Path | None, lock_nonce: str) -> None:
    if lock is None:
        return
    try:
        owner = json.loads((lock / "owner.json").read_text(encoding="utf-8"))
        if owner.get("lock_nonce") == lock_nonce:
            shutil.rmtree(lock)
    except (OSError, json.JSONDecodeError):
        return


def _select_probe(contract: dict[str, Any], state: dict[str, Any], now: float) -> dict[str, Any] | None:
    due: list[tuple[float, int, dict[str, Any]]] = []
    probe_state = state["probes"]
    for index, probe in enumerate(contract["probes"]):
        last = float((probe_state.get(probe["name"]) or {}).get("last_attempt_epoch") or 0.0)
        if now - last >= probe["cadence_seconds"]:
            due.append((last, index, probe))
    return min(due, default=(0.0, 0, None), key=lambda value: (value[0], value[1]))[2]


def _command(root: Path, declared: list[str]) -> list[str]:
    command = list(declared)
    if command[0] == "python":
        command[0] = sys.executable
    for value in command[1:]:
        if value.startswith("scripts/") and not (root / value).is_file():
            raise HeartbeatContractError(f"declared probe entrypoint is missing: {value}")
    return command


def _runtime_identity(root: Path, contract_digest: str, probe: dict[str, Any] | None) -> tuple[str, str]:
    files = [
        root / CONTRACT_RELATIVE_PATH,
        Path(__file__),
        Path(__file__).with_name("bounded_subprocess.py"),
        Path(__file__).with_name("host_admission.py"),
    ]
    if probe is not None:
        for value in probe["command"]:
            if value.startswith("scripts/"):
                files.append(root / value)
    rows = {str(path.relative_to(root)) if path.is_relative_to(root) else path.name: _sha256(path) for path in files}
    rows["contract"] = contract_digest
    runtime_digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    receipt = root.parent / "receipt.json"
    runtime_sha = "development"
    try:
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        if isinstance(payload.get("sha"), str):
            runtime_sha = payload["sha"]
    except (OSError, json.JSONDecodeError):
        pass
    return runtime_sha, runtime_digest


def _append_audit(state_root: Path, receipt: dict[str, Any]) -> None:
    audit = state_root / "audit.jsonl"
    audit.parent.mkdir(parents=True, exist_ok=True)
    if audit.exists() and audit.stat().st_size >= 1024 * 1024:
        os.replace(audit, audit.with_suffix(".jsonl.1"))
    with audit.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _write_receipts(state_root: Path, contract: dict[str, Any], receipt: dict[str, Any]) -> None:
    receipts = state_root / "receipts"
    private_path = receipts / f"{int(receipt['observed_epoch'])}-{receipt['run_id']}.json"
    _atomic_json(private_path, receipt)
    maximum = int(contract["audit"]["max_receipts"])
    for stale in sorted(receipts.glob("*.json"))[:-maximum]:
        stale.unlink(missing_ok=True)
    public = {
        "schema": PUBLIC_RECEIPT_SCHEMA,
        "label": LABEL,
        "status": receipt["status"],
        "observed_at": receipt["observed_at"],
        "runtime_sha": receipt["runtime_sha"],
        "runtime_digest": receipt["runtime_digest"],
        "probe_count": 1 if receipt.get("probe") else 0,
        "counts": {
            key: int(receipt["status"] == key)
            for key in ("passed", "finding", "deferred", "idle", "coalesced", "disabled", "failed")
        },
        "consecutive_system_failures": receipt["consecutive_system_failures"],
    }
    _atomic_json(state_root / contract["audit"]["public_receipt"], public)


def _disable_launch_agent() -> None:
    target = f"gui/{os.getuid()}/{LABEL}"
    commands = (
        ["launchctl", "disable", f"gui/{os.getuid()}/{LABEL}"],
        ["launchctl", "bootout", target],
    )
    failures = 0
    for command in commands:
        try:
            completed = subprocess.run(command, capture_output=True, timeout=3, check=False)
        except (OSError, subprocess.SubprocessError):
            failures += 1
        else:
            if completed.returncode not in {0, 113}:
                failures += 1
    if failures:
        raise HeartbeatContractError("launchd kill switch could not be fully enacted")


def heartbeat_once(
    root: Path,
    *,
    state_root: Path | None = None,
    clock: Clock = time.time,
    controller: AdmissionController | None = None,
    disable_launch_agent: Callable[[], None] = _disable_launch_agent,
) -> dict[str, Any]:
    """Run at most one due read-only probe, then leave no resident child."""

    root = root.resolve()
    state_root = (state_root or _default_state_root()).resolve()
    now = clock()
    contract, contract_digest = _load_contract(root)
    lock, lock_state = _acquire_lock(state_root, now)
    if lock is None:
        fail_closed = lock_state != "coalesced"
        runtime_sha, runtime_digest = _runtime_identity(root, contract_digest, None)
        contention_receipt = {
            "schema": PRIVATE_RECEIPT_SCHEMA,
            "run_id": uuid.uuid4().hex,
            "label": LABEL,
            "status": "coalesced" if lock_state == "coalesced" else "failed",
            "reason": lock_state,
            "observed_epoch": now,
            "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "probe": None,
            "probe_cost": None,
            "duration_ms": 0,
            "returncode": None,
            "output_bytes": 0,
            "surviving_descendant_count": 0,
            "runtime_sha": runtime_sha,
            "runtime_digest": runtime_digest,
            "contract_digest": contract_digest,
            "consecutive_system_failures": -1,
            "disabled": fail_closed,
        }
        _atomic_json(
            state_root / "receipts" / f"{int(now)}-{contention_receipt['run_id']}.json",
            contention_receipt,
        )
        _append_audit(state_root, contention_receipt)
        if fail_closed:
            disable_launch_agent()
        return contention_receipt

    state_path = state_root / "state.json"
    lease: dict[str, Any] | None = None
    admission = controller or AdmissionController()
    receipt: dict[str, Any]
    trip_kill_switch = False
    try:
        state_error: str | None = None
        try:
            state = _read_state(state_path)
        except HeartbeatContractError as exc:
            state_error = str(exc)
            if state_path.exists():
                invalid = state_root / f"state.invalid.{int(now)}.json"
                os.replace(state_path, invalid)
            state = _initial_state()
            state["consecutive_system_failures"] = contract["failure_policy"]["consecutive_system_failures"] - 1
            state["disabled"] = True
        probe = None if state_error else _select_probe(contract, state, now)
        runtime_sha, runtime_digest = _runtime_identity(root, contract_digest, probe)
        status = "failed" if state_error else "disabled" if state["disabled"] else "idle" if probe is None else "passed"
        reason: str | None = state_error
        duration_ms = 0
        returncode: int | None = None
        output_bytes = 0
        system_failure = state_error is not None
        if probe is not None and not state["disabled"]:
            if probe["cost"] == "heavy":
                try:
                    decision = admission.acquire(
                        "heavy",
                        owner=f"heartbeat-{os.getpid()}",
                        surface=LABEL,
                        pid=os.getpid(),
                        ttl_seconds=contract["limits"]["wall_seconds_per_tick"],
                    )
                except (AdmissionStateError, ValueError):
                    decision = {"allowed": False, "reasons": ["pressure-or-admission-unavailable"]}
                if not decision.get("allowed"):
                    status = "deferred"
                    reason = ",".join(str(value) for value in decision.get("reasons") or ["host-pressure"])
                else:
                    lease = decision.get("lease")
                    if lease is None:
                        status = "deferred"
                        reason = "admission-returned-no-lease"
            if probe["cost"] == "cheap" or lease is not None:
                started = time.monotonic()
                try:
                    completed = run_bounded_subprocess(
                        _command(root, probe["command"]),
                        cwd=root,
                        timeout_seconds=probe["timeout_seconds"],
                        stdout_ceiling=contract["audit"]["max_stream_bytes"],
                        stderr_ceiling=contract["audit"]["max_stream_bytes"],
                        cpu_seconds=contract["limits"]["cpu_seconds_per_tick"],
                        rss_ceiling=contract["limits"]["rss_bytes"],
                    )
                    returncode = completed.returncode
                    output_bytes = len(completed.stdout) + len(completed.stderr)
                    if returncode == 0:
                        status = "passed"
                    elif returncode < 0:
                        status = "failed"
                        reason = f"signal:{-returncode}"
                        system_failure = True
                    else:
                        status = "finding"
                        reason = f"probe-returncode:{returncode}"
                except BoundedSubprocessError as exc:
                    status = "failed"
                    reason = exc.kind
                    system_failure = exc.kind in SYSTEM_FAILURES
                except HeartbeatContractError as exc:
                    status = "failed"
                    reason = str(exc)
                    system_failure = True
                duration_ms = round((time.monotonic() - started) * 1000)
            if status != "deferred":
                state["probes"][probe["name"]] = {
                    "last_attempt_epoch": now,
                    "last_status": status,
                }
        if system_failure:
            state["consecutive_system_failures"] += 1
        elif status not in {"disabled"}:
            state["consecutive_system_failures"] = 0
        if state["consecutive_system_failures"] >= contract["failure_policy"]["consecutive_system_failures"]:
            state["disabled"] = True
            trip_kill_switch = True
        _atomic_json(state_path, state)
        receipt = {
            "schema": PRIVATE_RECEIPT_SCHEMA,
            "run_id": uuid.uuid4().hex,
            "label": LABEL,
            "observed_epoch": now,
            "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "status": status,
            "reason": reason,
            "probe": probe["name"] if probe is not None else None,
            "probe_cost": probe["cost"] if probe is not None else None,
            "duration_ms": duration_ms,
            "returncode": returncode,
            "output_bytes": output_bytes,
            "surviving_descendant_count": 0,
            "runtime_sha": runtime_sha,
            "runtime_digest": runtime_digest,
            "contract_digest": contract_digest,
            "consecutive_system_failures": state["consecutive_system_failures"],
            "disabled": state["disabled"],
        }
        _append_audit(state_root, receipt)
        _write_receipts(state_root, contract, receipt)
    finally:
        if lease is not None:
            try:
                admission.release(
                    lease_id=lease["lease_id"],
                    owner=f"heartbeat-{os.getpid()}",
                    pid=os.getpid(),
                )
            except (AdmissionStateError, ValueError):
                pass
        _release_lock(lock, lock_state)
    if trip_kill_switch:
        disable_launch_agent()
    return receipt


def is_system_failure(receipt: dict[str, Any]) -> bool:
    return receipt.get("status") == "failed"
