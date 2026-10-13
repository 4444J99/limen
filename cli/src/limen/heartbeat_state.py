"""Standard-library contract, state and failure accounting for the heartbeat."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from limen.heartbeat import NotificationCandidate
    from limen.notification_effect import DeliveryReceipt

LABEL = "com.limen.heartbeat"


CONTRACT_RELATIVE_PATH = Path("spec/scheduled-process-contracts.json")


NOTIFICATION_REGISTRY_RELATIVE_PATH = Path("institutio/governance/notification-events.limen.json")


STATE_SCHEMA = "limen.heartbeat_state.v1"


PRIVATE_RECEIPT_SCHEMA = "limen.heartbeat_private_receipt.v1"


PUBLIC_RECEIPT_SCHEMA = "limen.heartbeat_public_receipt.v1"


MAX_AUDIT_STREAM_BYTES = 262144


REVIEWED_RUNTIME_DIGEST_ENV = "LIMEN_HEARTBEAT_REVIEWED_RUNTIME_DIGEST"


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
        "interval": isinstance(launchd.get("start_interval_seconds"), int) and launchd["start_interval_seconds"] >= 180,
        "throttle": launchd.get("throttle_interval_seconds") == launchd.get("start_interval_seconds"),
        "wall": isinstance(limits.get("wall_seconds_per_tick"), int)
        and 1 <= limits["wall_seconds_per_tick"] <= min(300, launchd.get("start_interval_seconds", 0)),
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
        "notification_effect": contract.get("allowed_effects") == ["notification_event_v1"],
        "notification_limit": contract.get("max_notification_events_per_fire") == 1,
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
            or type(probe.get("priority", 0)) is not int
            or not 0 <= probe.get("priority", 0) <= 100
            or probe.get("system_failure_exit_codes", []) not in ([], [78])
        ):
            raise HeartbeatContractError(f"probe contract is unsafe: {name!r}")
        if any(value in {"--apply", "--emit", "--live", "dispatch"} for value in command):
            raise HeartbeatContractError(f"probe is not read-only: {name}")
        names.add(name)
    runtime_artifacts = contract.get("runtime_artifacts")
    if (
        not isinstance(runtime_artifacts, list)
        or not runtime_artifacts
        or not all(
            isinstance(value, str)
            and value
            and not Path(value).is_absolute()
            and ".." not in Path(value).parts
            and (root / value).is_file()
            for value in runtime_artifacts
        )
    ):
        raise HeartbeatContractError("heartbeat runtime artifact declaration is unsafe")
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


def _reviewed_runtime_digest() -> str | None:
    configured = os.environ.get(REVIEWED_RUNTIME_DIGEST_ENV)
    if configured is None:
        return None
    if len(configured) != 64 or any(character not in "0123456789abcdef" for character in configured):
        raise HeartbeatContractError(f"{REVIEWED_RUNTIME_DIGEST_ENV} must be a lowercase SHA-256")
    return configured


def _initial_state() -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "consecutive_system_failures": 0,
        "disabled": False,
        "probes": {},
        "notification_conditions": {},
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
        or not isinstance(state.get("notification_conditions", {}), dict)
    ):
        raise HeartbeatContractError("heartbeat state schema is incompatible")
    state.setdefault("notification_conditions", {})
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


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _notification_receipt_fields(
    candidate: NotificationCandidate | None,
    delivery: DeliveryReceipt | None,
) -> dict[str, Any]:
    return {
        "notification_event_selected_count": int(candidate is not None),
        "notification_event_attempted_count": int(delivery is not None and delivery.broker_invoked),
        "notification_event_accepted_count": int(delivery is not None and delivery.accepted),
        "notification_event_stable_id": candidate.event["stable_id"] if candidate is not None else None,
        "notification_event_id": candidate.event["event_id"] if candidate is not None else None,
        "notification_event_digest": candidate.digest if candidate is not None else None,
        "notification_broker_schema": delivery.broker_schema if delivery is not None else None,
        "notification_broker_status": delivery.status if delivery is not None else None,
        "notification_broker_channels": dict(delivery.channels) if delivery is not None else {},
    }


def _append_audit(state_root: Path, receipt: dict[str, Any]) -> None:
    audit = state_root / "audit.jsonl"
    audit.parent.mkdir(parents=True, exist_ok=True)
    if audit.is_symlink() or (audit.exists() and not audit.is_file()):
        raise HeartbeatContractError("heartbeat audit path is unsafe")
    encoded = (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

    def preserve(contents: bytes) -> None:
        history = state_root / "history"
        if history.is_symlink() or (history.exists() and not history.is_dir()):
            raise HeartbeatContractError("heartbeat audit history path is unsafe")
        history.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(contents).hexdigest()
        archived = history / f"audit.jsonl-{digest}"
        if archived.exists():
            if archived.is_symlink() or not archived.is_file() or _sha256(archived) != digest:
                raise HeartbeatContractError("heartbeat audit archive identity mismatch")
            if archived.read_bytes() != contents:
                raise HeartbeatContractError("heartbeat audit archive collision")
        else:
            descriptor = os.open(archived, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(contents)
                handle.flush()
                os.fsync(handle.fileno())
        if audit.exists():
            audit.unlink()

    existing = audit.read_bytes() if audit.exists() else b""
    if len(encoded) > MAX_AUDIT_STREAM_BYTES:
        if existing:
            preserve(existing)
        preserve(encoded)
    else:
        if len(existing) + len(encoded) > MAX_AUDIT_STREAM_BYTES:
            preserve(existing)
        descriptor = os.open(audit, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "ab") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    if not audit.exists():
        descriptor = os.open(audit, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)


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
        "notification_effect": {
            "selected_count": receipt["notification_event_selected_count"],
            "attempted_count": receipt["notification_event_attempted_count"],
            "accepted_count": receipt["notification_event_accepted_count"],
            "stable_id": receipt["notification_event_stable_id"],
            "event_id": receipt["notification_event_id"],
            "event_digest": receipt["notification_event_digest"],
            "broker_schema": receipt["notification_broker_schema"],
            "broker_status": receipt["notification_broker_status"],
            "broker_channels": receipt["notification_broker_channels"],
        },
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


def _initialization_failure_receipt(
    root: Path,
    state_root: Path,
    now: float,
    reason: str,
    *,
    failures: int = 1,
    disabled: bool = True,
    runtime_sha: str = "development",
    duration_ms: int = 0,
) -> dict[str, Any]:
    """Persist a fail-closed receipt even when the declared contract is unusable."""

    runtime_files = [
        Path(__file__),
        Path(__file__).with_name("bounded_subprocess.py"),
        Path(__file__).with_name("host_admission.py"),
        Path(__file__).with_name("notification_effect.py"),
    ]
    contract_path = root / CONTRACT_RELATIVE_PATH
    if contract_path.is_file():
        runtime_files.append(contract_path)
    rows = {
        str(path.relative_to(root)) if path.is_relative_to(root) else path.name: _sha256(path) for path in runtime_files
    }
    runtime_digest = _reviewed_runtime_digest() or _canonical_digest(rows)
    run_id = uuid.uuid4().hex
    receipt = {
        "schema": PRIVATE_RECEIPT_SCHEMA,
        "run_id": run_id,
        "label": LABEL,
        "status": "failed",
        "reason": reason,
        "observed_epoch": now,
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "probe": None,
        "probe_cost": None,
        "duration_ms": duration_ms,
        "returncode": None,
        "output_bytes": 0,
        "surviving_descendant_count": 0,
        "runtime_sha": runtime_sha,
        "runtime_digest": runtime_digest,
        "contract_digest": None,
        "consecutive_system_failures": failures,
        "disabled": disabled,
        **_notification_receipt_fields(None, None),
    }
    _atomic_json(state_root / "receipts" / f"{int(now)}-{run_id}.json", receipt)
    _append_audit(state_root, receipt)
    _atomic_json(
        state_root / "public-latest.json",
        {
            "schema": PUBLIC_RECEIPT_SCHEMA,
            "label": LABEL,
            "status": "failed",
            "observed_at": receipt["observed_at"],
            "runtime_sha": receipt["runtime_sha"],
            "runtime_digest": runtime_digest,
            "probe_count": 0,
            "counts": {
                key: int(key == "failed")
                for key in (
                    "passed",
                    "finding",
                    "deferred",
                    "idle",
                    "coalesced",
                    "disabled",
                    "failed",
                )
            },
            "consecutive_system_failures": failures,
            "notification_effect": {
                "selected_count": 0,
                "attempted_count": 0,
                "accepted_count": 0,
                "stable_id": None,
                "event_id": None,
                "event_digest": None,
                "broker_schema": None,
                "broker_status": None,
                "broker_channels": {},
            },
        },
    )
    return receipt


def record_tick_timeout(
    root: Path,
    state_root: Path,
    duration_ms: int,
    failures_before: int | None = None,
    *,
    disable_launch_agent: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Persist whole-tick timeout accounting after normal child/lease unwinding."""
    now = time.time()
    contract, _digest = _load_contract(root)
    lock, lock_state = _acquire_lock(state_root, now)
    if lock is None:
        raise HeartbeatContractError("deadline receipt lock unavailable")
    try:
        state = _read_state(state_root / "state.json")
        state["consecutive_system_failures"] = (
            max(state["consecutive_system_failures"], failures_before + 1)
            if failures_before is not None
            else state["consecutive_system_failures"] + 1
        )
        state["disabled"] = (
            state["consecutive_system_failures"] >= contract["failure_policy"]["consecutive_system_failures"]
        )
        _atomic_json(state_root / "state.json", state)
        receipt = _initialization_failure_receipt(
            root,
            state_root,
            now,
            "tick_wall_timeout",
            failures=state["consecutive_system_failures"],
            disabled=state["disabled"],
            runtime_sha=root.parent.name if len(root.parent.name) == 40 else "development",
            duration_ms=duration_ms,
        )
    finally:
        _release_lock(lock, lock_state)
    if state["disabled"]:
        (disable_launch_agent or _disable_launch_agent)()
    return receipt
