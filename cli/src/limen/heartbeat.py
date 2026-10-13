"""Resource-bounded, launchd-safe one-shot heartbeat supervisor."""

from __future__ import annotations

import hashlib
import ctypes
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


from limen.heartbeat_state import (
    CONTRACT_RELATIVE_PATH as CONTRACT_RELATIVE_PATH,
    HeartbeatContractError as HeartbeatContractError,
    LABEL as LABEL,
    MAX_AUDIT_STREAM_BYTES as MAX_AUDIT_STREAM_BYTES,
    NOTIFICATION_REGISTRY_RELATIVE_PATH as NOTIFICATION_REGISTRY_RELATIVE_PATH,
    PRIVATE_RECEIPT_SCHEMA as PRIVATE_RECEIPT_SCHEMA,
    PUBLIC_RECEIPT_SCHEMA as PUBLIC_RECEIPT_SCHEMA,
    REVIEWED_RUNTIME_DIGEST_ENV as REVIEWED_RUNTIME_DIGEST_ENV,
    STATE_SCHEMA as STATE_SCHEMA,
    _acquire_lock as _acquire_lock,
    _append_audit as _append_audit,
    _atomic_json as _atomic_json,
    _canonical_digest as _canonical_digest,
    _default_state_root as _default_state_root,
    _disable_launch_agent as _disable_launch_agent,
    _initial_state as _initial_state,
    _initialization_failure_receipt as _initialization_failure_receipt,
    _load_contract as _load_contract,
    _notification_receipt_fields as _notification_receipt_fields,
    _read_state as _read_state,
    _release_lock as _release_lock,
    _reviewed_runtime_digest as _reviewed_runtime_digest,
    _sha256 as _sha256,
    _write_receipts as _write_receipts,
    record_tick_timeout as _record_tick_timeout,
)

from limen.bounded_subprocess import BoundedSubprocessError, run_bounded_subprocess
from limen.host_admission import AdmissionController, AdmissionStateError
from limen.notification_effect import DeliveryReceipt, emit_notification_event

SYSTEM_FAILURES = frozenset({"descendants", "invalid", "output", "resource", "timeout", "unavailable"})
NOTIFICATION_STABLE_ID = "limen.heartbeat.finding"
NOTIFICATION_SEVERITY_ORDER = {"urgent": 0, "normal": 1, "summary": 2}
Clock = Callable[[], float]


def _clock_observation() -> dict[str, Any]:
    """Measure independent Darwin awake/continuous clocks; never infer old sleep."""
    unavailable = {"schema": "limen.heartbeat_clock.v1", "measured": False}
    if sys.platform != "darwin" or not hasattr(time, "CLOCK_UPTIME_RAW"):
        return {**unavailable, "reason": "native_clock_unsupported"}
    try:
        library = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
        native = library.sysctlbyname
        native.argtypes = [
            ctypes.c_char_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_void_p,
            ctypes.c_size_t,
        ]
        native.restype = ctypes.c_int
        value = ctypes.create_string_buffer(128)
        size = ctypes.c_size_t(len(value))
        if native(b"kern.bootsessionuuid", value, ctypes.byref(size), None, 0) != 0:
            raise OSError("boot identity unavailable")
        identity = str(uuid.UUID(value.value.decode("ascii")))
        continuous = time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
        awake = time.clock_gettime_ns(time.CLOCK_UPTIME_RAW)
        return {
            "schema": "limen.heartbeat_clock.v1",
            "measured": True,
            "boot_id": hashlib.sha256(identity.encode()).hexdigest(),
            "continuous_ns": continuous,
            "awake_ns": awake,
        }
    except (OSError, ValueError, AttributeError, UnicodeError):
        return {**unavailable, "reason": "native_clock_unavailable"}


def _probe_evidence(probe: dict[str, Any], stdout: bytes) -> dict[str, Any] | None:
    """Only typed reason codes survive private custody; never persist raw probe text."""
    try:
        if probe["name"] == "runtime-maintenance-observation":
            payload = json.loads(stdout)
            if payload.get("schema") != "limen.runtime_maintenance_observation.v1":
                return None
            pool = payload.get("pool") or {}
            codes = pool.get("denial_reasons") or []
            if not isinstance(codes, list):
                return None
            codes = list(codes)
            if isinstance(payload.get("reason"), str):
                codes.append(payload["reason"])
        elif probe["name"] == "dialogs-silenced":
            line = next(
                line for line in stdout.decode("utf-8").splitlines() if line.startswith("limen-probe-evidence=")
            )
            payload = json.loads(line.partition("=")[2])
            if payload.get("schema") != "limen.dialogs_evidence.v1":
                return None
            codes = payload.get("reason_codes") or []
        else:
            return None
        if not isinstance(codes, list):
            return None
        status = payload.get("status")
        if not isinstance(status, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", status):
            return None
        result = {
            "schema": payload["schema"],
            "status": status,
            "reason_codes": sorted(
                {
                    code
                    for code in codes
                    if isinstance(code, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,95}", code)
                }
            )[:32],
        }
        if isinstance(payload.get("native_job_cleanup"), bool):
            result["native_job_cleanup"] = payload["native_job_cleanup"]
        if isinstance(payload.get("native_output_complete"), bool):
            result["native_output_complete"] = payload["native_output_complete"]
        return result
    except (ValueError, TypeError, AttributeError, StopIteration, UnicodeError):
        return None


def _select_probe(contract: dict[str, Any], state: dict[str, Any], now: float) -> dict[str, Any] | None:
    due: list[tuple[float, int, dict[str, Any]]] = []
    probe_state = state["probes"]
    for index, probe in enumerate(contract["probes"]):
        last = float((probe_state.get(probe["name"]) or {}).get("last_attempt_epoch") or 0.0)
        if now - last >= probe["cadence_seconds"]:
            due.append((last, index, probe))
    return min(
        due,
        default=(0.0, 0, None),
        key=lambda value: (-value[2].get("priority", 0), value[0], value[1]),
    )[2]


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


def record_tick_timeout(root: Path, state_root: Path, duration_ms: int, failures_before: int | None = None):
    return _record_tick_timeout(
        root, state_root, duration_ms, failures_before, disable_launch_agent=_disable_launch_agent
    )


def heartbeat_once(
    root: Path,
    *,
    state_root: Path | None = None,
    clock: Clock = time.time,
    controller: AdmissionController | None = None,
    disable_launch_agent: Callable[[], None] = _disable_launch_agent,
    notification_emitter: Callable[[Path, NotificationCandidate], DeliveryReceipt] | None = None,
    started_monotonic: float | None = None,
) -> dict[str, Any]:
    """Run at most one due read-only probe, then leave no resident child."""

    tick_started = time.monotonic() if started_monotonic is None else started_monotonic
    root = root.resolve()
    state_root = (state_root or _default_state_root()).resolve()
    now = clock()
    clock_observation = _clock_observation()
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
        probe_evidence = None
        output_observation: dict[str, Any] = {"complete": True, "stdout_sha256": None, "stderr_sha256": None}
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
                    probe_evidence = _probe_evidence(probe, completed.stdout)
                    output_observation.update(
                        stdout_sha256=hashlib.sha256(completed.stdout).hexdigest(),
                        stderr_sha256=hashlib.sha256(completed.stderr).hexdigest(),
                    )
                    if returncode == 0:
                        status = "passed"
                    elif returncode in probe.get("system_failure_exit_codes", []):
                        status = "failed"
                        reason = f"probe-contract-returncode:{returncode}"
                        system_failure = True
                    elif returncode < 0:
                        status = "failed"
                        reason = f"signal:{-returncode}"
                        system_failure = True
                    else:
                        status = "finding"
                        reason = f"probe-returncode:{returncode}"
                    if probe_evidence and probe_evidence.get("native_job_cleanup") is False:
                        status = "failed"
                        reason = "native_audit_cleanup_unverified"
                        system_failure = True
                        surviving_descendant_count = "unknown"
                except BoundedSubprocessError as exc:
                    status = "failed"
                    reason = f"{exc.kind}:{exc.stage}" if exc.stage else exc.kind
                    system_failure = exc.kind in SYSTEM_FAILURES
                    surviving_descendant_count = "unknown"
                    partial_stdout = exc.stdout
                    partial_stderr = exc.stderr
                    output_bytes = len(partial_stdout or b"") + len(partial_stderr or b"")
                    output_observation = {
                        "complete": False,
                        "root_reaped": exc.root_reaped,
                        "stdout_sha256": hashlib.sha256(partial_stdout).hexdigest()
                        if partial_stdout is not None
                        else None,
                        "stderr_sha256": hashlib.sha256(partial_stderr).hexdigest()
                        if partial_stderr is not None
                        else None,
                    }
                    probe_evidence = _probe_evidence(probe, partial_stdout) if partial_stdout is not None else None
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
            "whole_tick_duration_ms": round((time.monotonic() - tick_started) * 1000),
            "returncode": returncode,
            "output_bytes": output_bytes,
            "output_observation": output_observation,
            "probe_evidence": probe_evidence,
            "clock_observation": clock_observation,
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
