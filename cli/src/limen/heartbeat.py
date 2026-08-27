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
from dataclasses import dataclass
from typing import Any, Callable

from limen.bounded_subprocess import BoundedSubprocessError, run_bounded_subprocess
from limen.host_admission import AdmissionController, AdmissionStateError
from limen.notification_effect import DeliveryReceipt, emit_notification_event


LABEL = "com.limen.heartbeat"
CONTRACT_RELATIVE_PATH = Path("spec/scheduled-process-contracts.json")
NOTIFICATION_REGISTRY_RELATIVE_PATH = Path("institutio/governance/notification-events.limen.json")
STATE_SCHEMA = "limen.heartbeat_state.v1"
PRIVATE_RECEIPT_SCHEMA = "limen.heartbeat_private_receipt.v1"
PUBLIC_RECEIPT_SCHEMA = "limen.heartbeat_public_receipt.v1"
REVIEWED_RUNTIME_DIGEST_ENV = "LIMEN_HEARTBEAT_REVIEWED_RUNTIME_DIGEST"
SYSTEM_FAILURES = frozenset({"descendants", "invalid", "output", "resource", "timeout", "unavailable"})
NOTIFICATION_STABLE_ID = "limen.heartbeat.finding"
NOTIFICATION_SEVERITY_ORDER = {"urgent": 0, "normal": 1, "summary": 2}
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


def _runtime_identity(
    root: Path,
    contract: dict[str, Any],
    contract_digest: str,
    probe: dict[str, Any] | None,
) -> tuple[str, str]:
    files = [root / CONTRACT_RELATIVE_PATH]
    files.extend(root / value for value in contract["runtime_artifacts"])
    if probe is not None:
        for value in probe["command"]:
            if value.startswith("scripts/"):
                files.append(root / value)
    rows = {str(path.relative_to(root)) if path.is_relative_to(root) else path.name: _sha256(path) for path in files}
    rows["contract"] = contract_digest
    runtime_digest = _reviewed_runtime_digest() or hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    receipt = root.parent / "receipt.json"
    runtime_sha = "development"
    try:
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        if isinstance(payload.get("sha"), str):
            runtime_sha = payload["sha"]
    except (OSError, json.JSONDecodeError):
        pass
    return runtime_sha, runtime_digest


@dataclass(frozen=True)
class NotificationCandidate:
    """One re-derivable notification transition competing for the single effect slot."""

    condition_key: str
    transition: str
    severity: str
    target_active: bool
    event: dict[str, Any]
    digest: str


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _observe_notification_condition(
    state: dict[str, Any],
    *,
    probe: str,
    status: str,
    reason: str | None,
    returncode: int | None,
    observed_at: str,
) -> None:
    """Project a probe transition without consuming its notification entitlement."""

    if status not in {"passed", "finding", "failed"}:
        return
    conditions = state.setdefault("notification_conditions", {})
    row = conditions.get(probe)
    if not isinstance(row, dict):
        row = {"accepted_active": False, "accepted_severity": None}
        conditions[probe] = row
    active = status in {"finding", "failed"}
    severity = "urgent" if status == "failed" else "normal" if active else None
    changed = row.get("active") != active or (active and row.get("severity") != severity)
    row.update(
        {
            "active": active,
            "severity": severity,
            "status": status,
            "reason": reason,
            "returncode": returncode,
        }
    )
    if changed:
        transition_facts = {
            "active": active,
            "observed_at": observed_at,
            "probe": probe,
            "reason": reason,
            "returncode": returncode,
            "severity": severity,
            "status": status,
        }
        row["transition_observed_at"] = observed_at
        row["transition_digest"] = _canonical_digest(transition_facts)


def _notification_candidates(state: dict[str, Any]) -> list[NotificationCandidate]:
    candidates: list[NotificationCandidate] = []
    conditions = state.get("notification_conditions") or {}
    for condition_key in sorted(conditions):
        row = conditions[condition_key]
        if not isinstance(row, dict):
            continue
        active = bool(row.get("active"))
        accepted_active = bool(row.get("accepted_active"))
        severity = str(row.get("severity") or row.get("accepted_severity") or "normal")
        if active != accepted_active:
            transition = "onset" if active else "clear"
        elif (
            active
            and accepted_active
            and NOTIFICATION_SEVERITY_ORDER.get(severity, 99)
            < NOTIFICATION_SEVERITY_ORDER.get(str(row.get("accepted_severity") or "summary"), 99)
        ):
            transition = "update"
        else:
            continue
        observed_at = str(row.get("transition_observed_at") or "")
        transition_digest = str(row.get("transition_digest") or "")
        if not observed_at or len(transition_digest) != 64:
            continue
        event = {
            "event_id": f"heartbeat-{transition_digest[:24]}",
            "transition": transition,
            "subject_key": condition_key,
            "observed_at": observed_at,
            "stable_id": NOTIFICATION_STABLE_ID,
            "facts": {
                "probe": condition_key,
                "reason": row.get("reason"),
                "returncode": row.get("returncode"),
                "snapshot_time": observed_at,
                "status": row.get("status"),
            },
            "evidence_ref": f"heartbeat-observation:{transition_digest}",
            "producer": "limen.heartbeat",
            "owner": "limen",
        }
        candidates.append(
            NotificationCandidate(
                condition_key=condition_key,
                transition=transition,
                severity=severity,
                target_active=active,
                event=event,
                digest=_canonical_digest(event),
            )
        )
    return candidates


def _select_notification_candidate(
    candidates: list[NotificationCandidate],
) -> NotificationCandidate | None:
    """Choose one stable candidate; every loser remains derivable from state."""

    def ordering(candidate: NotificationCandidate) -> tuple[int, int, str, str]:
        severity = NOTIFICATION_SEVERITY_ORDER.get(candidate.severity, 99)
        transition = 0 if candidate.transition in {"onset", "clear"} else 1
        return severity, transition, candidate.condition_key, candidate.digest

    return min(candidates, key=ordering) if candidates else None


def _emit_candidate(root: Path, candidate: NotificationCandidate) -> DeliveryReceipt:
    return emit_notification_event(
        candidate.event,
        registry=root / NOTIFICATION_REGISTRY_RELATIVE_PATH,
        level=candidate.severity,
    )


def _accept_notification_candidate(state: dict[str, Any], candidate: NotificationCandidate) -> None:
    row = (state.get("notification_conditions") or {}).get(candidate.condition_key)
    if not isinstance(row, dict):
        return
    row["accepted_active"] = candidate.target_active
    row["accepted_severity"] = candidate.severity if candidate.target_active else None
    row["accepted_event_id"] = candidate.event["event_id"]


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


def _initialization_failure_receipt(root: Path, state_root: Path, now: float, reason: str) -> dict[str, Any]:
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
        "duration_ms": 0,
        "returncode": None,
        "output_bytes": 0,
        "surviving_descendant_count": 0,
        "runtime_sha": "development",
        "runtime_digest": runtime_digest,
        "contract_digest": None,
        "consecutive_system_failures": 1,
        "disabled": True,
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
            "consecutive_system_failures": 1,
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


def heartbeat_once(
    root: Path,
    *,
    state_root: Path | None = None,
    clock: Clock = time.time,
    controller: AdmissionController | None = None,
    disable_launch_agent: Callable[[], None] = _disable_launch_agent,
    notification_emitter: Callable[[Path, NotificationCandidate], DeliveryReceipt] | None = None,
) -> dict[str, Any]:
    """Run at most one due read-only probe, then leave no resident child."""

    root = root.resolve()
    state_root = (state_root or _default_state_root()).resolve()
    now = clock()
    observed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    try:
        contract, contract_digest = _load_contract(root)
    except HeartbeatContractError as exc:
        initialization_receipt: dict[str, Any] | None = None
        receipt_error: Exception | None = None
        try:
            initialization_receipt = _initialization_failure_receipt(root, state_root, now, str(exc))
        except Exception as storage_error:
            receipt_error = storage_error
        try:
            disable_launch_agent()
        except Exception as disable_error:
            if receipt_error is not None:
                raise HeartbeatContractError(
                    "heartbeat initialization failed; receipt storage and launchd kill switch also failed"
                ) from disable_error
            raise
        if receipt_error is not None:
            raise receipt_error
        if initialization_receipt is None:
            raise HeartbeatContractError("heartbeat initialization failure receipt is unavailable")
        return initialization_receipt
    lock, lock_state = _acquire_lock(state_root, now)
    if lock is None:
        fail_closed = lock_state != "coalesced"
        runtime_sha, runtime_digest = _runtime_identity(root, contract, contract_digest, None)
        contention_receipt = {
            "schema": PRIVATE_RECEIPT_SCHEMA,
            "run_id": uuid.uuid4().hex,
            "label": LABEL,
            "status": "coalesced" if lock_state == "coalesced" else "failed",
            "reason": lock_state,
            "observed_epoch": now,
            "observed_at": observed_at,
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
            **_notification_receipt_fields(None, None),
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
    pending_notification_count = 0
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
        runtime_sha, runtime_digest = _runtime_identity(root, contract, contract_digest, probe)
        status = "failed" if state_error else "disabled" if state["disabled"] else "idle" if probe is None else "passed"
        reason: str | None = state_error
        duration_ms = 0
        returncode: int | None = None
        output_bytes = 0
        surviving_descendant_count: int | str = 0
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
                    surviving_descendant_count = "unknown"
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
                _observe_notification_condition(
                    state,
                    probe=probe["name"],
                    status=status,
                    reason=reason,
                    returncode=returncode,
                    observed_at=observed_at,
                )
        if system_failure:
            state["consecutive_system_failures"] += 1
        elif status not in {"disabled"}:
            state["consecutive_system_failures"] = 0
        if state["consecutive_system_failures"] >= contract["failure_policy"]["consecutive_system_failures"]:
            state["disabled"] = True
            trip_kill_switch = True
        candidate: NotificationCandidate | None = None
        delivery: DeliveryReceipt | None = None
        # A disabled heartbeat runs no probe, but it remains a bounded sender for any notification
        # transition that was not accepted before the kill switch tripped. One candidate is attempted
        # per fire; once the durable broker accepts the final candidate, launchd is unloaded.
        if state_error is None:
            candidate = _select_notification_candidate(_notification_candidates(state))
            if candidate is not None:
                emitter = notification_emitter or _emit_candidate
                try:
                    delivery = emitter(root, candidate)
                except Exception as exc:  # noqa: BLE001 - an effect failure must still yield a receipt
                    delivery = DeliveryReceipt(
                        "failed",
                        candidate.event["stable_id"],
                        candidate.event["event_id"],
                        {},
                        f"notification adapter failed ({type(exc).__name__})",
                        broker_invoked=False,
                    )
                if delivery.accepted:
                    _accept_notification_candidate(state, candidate)
        pending_notification_count = len(_notification_candidates(state))
        _atomic_json(state_path, state)
        receipt = {
            "schema": PRIVATE_RECEIPT_SCHEMA,
            "run_id": uuid.uuid4().hex,
            "label": LABEL,
            "observed_epoch": now,
            "observed_at": observed_at,
            "status": status,
            "reason": reason,
            "probe": probe["name"] if probe is not None else None,
            "probe_cost": probe["cost"] if probe is not None else None,
            "duration_ms": duration_ms,
            "returncode": returncode,
            "output_bytes": output_bytes,
            "surviving_descendant_count": surviving_descendant_count,
            "runtime_sha": runtime_sha,
            "runtime_digest": runtime_digest,
            "contract_digest": contract_digest,
            "consecutive_system_failures": state["consecutive_system_failures"],
            "disabled": state["disabled"],
            **_notification_receipt_fields(candidate, delivery),
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
    if trip_kill_switch and pending_notification_count == 0:
        disable_launch_agent()
    return receipt


def is_system_failure(receipt: dict[str, Any]) -> bool:
    return receipt.get("status") == "failed"
