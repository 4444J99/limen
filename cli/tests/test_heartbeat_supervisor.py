import json
from pathlib import Path

import pytest

from limen import heartbeat
from limen.bounded_subprocess import BoundedCompletedProcess, BoundedSubprocessError
from limen.notification_effect import DeliveryReceipt


ROOT = Path(__file__).resolve().parents[2]


class FakeAdmission:
    def __init__(self, *, allowed=True):
        self.allowed = allowed
        self.acquired = 0
        self.released = 0

    def acquire(self, *_args, **_kwargs):
        self.acquired += 1
        return {
            "allowed": self.allowed,
            "reasons": [] if self.allowed else ["synthetic-pressure"],
            "lease": {"lease_id": "lease"} if self.allowed else None,
        }

    def release(self, **_kwargs):
        self.released += 1
        return {"allowed": True}


def _state(path, *, failures=0, disabled=False, probes=None, notification_conditions=None):
    path.mkdir(parents=True, exist_ok=True)
    (path / "state.json").write_text(
        json.dumps(
            {
                "schema": heartbeat.STATE_SCHEMA,
                "consecutive_system_failures": failures,
                "disabled": disabled,
                "probes": probes or {},
                "notification_conditions": notification_conditions or {},
            }
        )
    )


def test_contract_is_a_one_shot_resource_contract():
    contract, _digest = heartbeat._load_contract(ROOT)
    assert contract["launchd"]["keep_alive"] is False
    assert contract["launchd"]["run_at_load"] is False
    assert contract["launchd"]["nice"] >= 5
    assert contract["limits"]["max_concurrent_probes"] == 1
    assert contract["limits"]["rss_bytes"] <= 512 * 1024 * 1024
    assert contract["failure_policy"]["consecutive_system_failures"] == 3
    assert contract["allowed_effects"] == ["notification_event_v1"]
    assert contract["max_notification_events_per_fire"] == 1
    assert "cli/src/limen/notification_effect.py" in contract["runtime_artifacts"]
    commands = {probe["name"]: probe["command"] for probe in contract["probes"]}
    assert "--no-receipt" in commands["background-items-census"]
    assert "--no-receipt" in commands["live-checkout-currency"]
    assert "--no-write" in commands["cloud-storage-doctor"]
    assert "--no-write" in commands["tcc-track-c"]


def test_runtime_identity_uses_reviewed_digest_for_every_probe(monkeypatch):
    contract, contract_digest = heartbeat._load_contract(ROOT)
    reviewed_digest = "a" * 64
    monkeypatch.setenv(heartbeat.REVIEWED_RUNTIME_DIGEST_ENV, reviewed_digest)

    idle_identity = heartbeat._runtime_identity(ROOT, contract, contract_digest, None)
    probe_identity = heartbeat._runtime_identity(ROOT, contract, contract_digest, contract["probes"][0])

    assert idle_identity[1] == reviewed_digest
    assert probe_identity[1] == reviewed_digest


def test_runtime_identity_rejects_malformed_reviewed_digest(monkeypatch):
    contract, contract_digest = heartbeat._load_contract(ROOT)
    monkeypatch.setenv(heartbeat.REVIEWED_RUNTIME_DIGEST_ENV, "A" * 64)

    with pytest.raises(heartbeat.HeartbeatContractError, match="lowercase SHA-256"):
        heartbeat._runtime_identity(ROOT, contract, contract_digest, None)


def test_cheap_probe_passes_without_heavy_admission(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        heartbeat,
        "run_bounded_subprocess",
        lambda command, **kwargs: calls.append((command, kwargs)) or BoundedCompletedProcess(0, b"ok", b""),
    )
    admission = FakeAdmission()
    receipt = heartbeat.heartbeat_once(
        ROOT,
        state_root=tmp_path,
        clock=lambda: 1_000_000,
        controller=admission,
    )
    assert receipt["status"] == "passed"
    assert admission.acquired == 0
    assert len(calls) == 1
    assert calls[0][1]["cpu_seconds"] == 60
    assert calls[0][1]["rss_ceiling"] == 512 * 1024 * 1024
    public = json.loads((tmp_path / "public-latest.json").read_text())
    assert "command" not in public
    assert public["counts"]["passed"] == 1


def test_probe_finding_does_not_increment_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setattr(
        heartbeat,
        "run_bounded_subprocess",
        lambda *_args, **_kwargs: BoundedCompletedProcess(2, b"", b"finding"),
    )
    receipt = heartbeat.heartbeat_once(ROOT, state_root=tmp_path, clock=lambda: 1_000_000)
    assert receipt["status"] == "finding"
    assert receipt["consecutive_system_failures"] == 0


def test_finding_emits_one_notification_event_with_bound_broker_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(
        heartbeat,
        "run_bounded_subprocess",
        lambda *_args, **_kwargs: BoundedCompletedProcess(2, b"", b"finding"),
    )
    emitted = []

    def accept(_root, candidate):
        emitted.append(candidate)
        return DeliveryReceipt(
            "submitted",
            candidate.event["stable_id"],
            candidate.event["event_id"],
            {"macos": "submitted"},
            broker_schema="domus.notification_delivery_receipt.v2",
        )

    receipt = heartbeat.heartbeat_once(
        ROOT,
        state_root=tmp_path,
        clock=lambda: 1_000_000,
        notification_emitter=accept,
    )

    assert len(emitted) == 1
    event = emitted[0].event
    assert event["stable_id"] == "limen.heartbeat.finding"
    assert event["transition"] == "onset"
    assert event["owner"] == "limen"
    assert receipt["notification_event_selected_count"] == 1
    assert receipt["notification_event_attempted_count"] == 1
    assert receipt["notification_event_accepted_count"] == 1
    assert receipt["notification_broker_schema"] == "domus.notification_delivery_receipt.v2"
    assert receipt["notification_broker_status"] == "submitted"
    assert receipt["notification_broker_channels"] == {"macos": "submitted"}
    public = json.loads((tmp_path / "public-latest.json").read_text())
    assert public["notification_effect"]["event_digest"] == receipt["notification_event_digest"]
    assert public["notification_effect"]["accepted_count"] == 1


def test_notification_selection_is_deterministic_and_losers_rederive():
    state = heartbeat._initial_state()
    heartbeat._observe_notification_condition(
        state,
        probe="normal-probe",
        status="finding",
        reason="probe-returncode:2",
        returncode=2,
        observed_at="2026-08-25T12:00:00Z",
    )
    heartbeat._observe_notification_condition(
        state,
        probe="urgent-probe",
        status="failed",
        reason="timeout",
        returncode=None,
        observed_at="2026-08-25T12:00:01Z",
    )

    first = heartbeat._select_notification_candidate(heartbeat._notification_candidates(state))
    assert first is not None
    assert first.condition_key == "urgent-probe"
    assert first.severity == "urgent"
    heartbeat._accept_notification_candidate(state, first)

    second = heartbeat._select_notification_candidate(heartbeat._notification_candidates(state))
    assert second is not None
    assert second.condition_key == "normal-probe"
    assert second.event["event_id"] == heartbeat._notification_candidates(state)[0].event["event_id"]


def test_heavy_probe_is_deferred_under_pressure_without_spawn(tmp_path, monkeypatch):
    contract, _digest = heartbeat._load_contract(ROOT)
    cheap = {row["name"]: {"last_attempt_epoch": 1_000_000} for row in contract["probes"] if row["cost"] == "cheap"}
    _state(tmp_path, probes=cheap)
    monkeypatch.setattr(
        heartbeat,
        "run_bounded_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("probe spawned")),
    )
    admission = FakeAdmission(allowed=False)
    receipt = heartbeat.heartbeat_once(
        ROOT,
        state_root=tmp_path,
        clock=lambda: 1_000_001,
        controller=admission,
    )
    assert receipt["status"] == "deferred"
    assert receipt["reason"] == "synthetic-pressure"
    assert admission.acquired == 1


def test_third_system_failure_disables_launch_agent(tmp_path, monkeypatch):
    _state(tmp_path, failures=2)
    monkeypatch.setattr(
        heartbeat,
        "run_bounded_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(BoundedSubprocessError("timeout")),
    )
    disabled = []
    receipt = heartbeat.heartbeat_once(
        ROOT,
        state_root=tmp_path,
        clock=lambda: 1_000_000,
        disable_launch_agent=lambda: disabled.append(True),
        notification_emitter=lambda _root, candidate: DeliveryReceipt(
            "submitted",
            candidate.event["stable_id"],
            candidate.event["event_id"],
            {"macos": "submitted"},
        ),
    )
    assert receipt["status"] == "failed"
    assert receipt["consecutive_system_failures"] == 3
    assert receipt["disabled"] is True
    assert receipt["surviving_descendant_count"] == "unknown"
    assert disabled == [True]


def test_kill_switch_keeps_bounded_sender_until_pending_notification_is_accepted(tmp_path, monkeypatch):
    _state(tmp_path, failures=2)
    monkeypatch.setattr(
        heartbeat,
        "run_bounded_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(BoundedSubprocessError("timeout")),
    )
    disabled = []
    attempts = []

    def emit(_root, candidate):
        attempts.append(candidate.event["event_id"])
        if len(attempts) == 1:
            return DeliveryReceipt(
                "failed",
                candidate.event["stable_id"],
                candidate.event["event_id"],
                {},
                "synthetic broker outage",
            )
        return DeliveryReceipt(
            "submitted",
            candidate.event["stable_id"],
            candidate.event["event_id"],
            {"macos": "submitted"},
        )

    first = heartbeat.heartbeat_once(
        ROOT,
        state_root=tmp_path,
        clock=lambda: 1_000_000,
        disable_launch_agent=lambda: disabled.append(True),
        notification_emitter=emit,
    )
    assert first["disabled"] is True
    assert first["notification_event_accepted_count"] == 0
    assert disabled == []

    second = heartbeat.heartbeat_once(
        ROOT,
        state_root=tmp_path,
        clock=lambda: 1_000_300,
        disable_launch_agent=lambda: disabled.append(True),
        notification_emitter=emit,
    )
    assert second["status"] == "disabled"
    assert second["notification_event_accepted_count"] == 1
    assert attempts == [attempts[0], attempts[0]]
    assert disabled == [True]


def test_live_single_flight_lock_coalesces_without_probe(tmp_path, monkeypatch):
    lock = tmp_path / "single-flight.lock"
    lock.mkdir(parents=True)
    monkeypatch.setattr(
        heartbeat,
        "run_bounded_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("probe spawned")),
    )
    receipt = heartbeat.heartbeat_once(ROOT, state_root=tmp_path, clock=lambda: lock.stat().st_mtime + 1)
    assert receipt["status"] == "coalesced"


def test_unreadable_single_flight_state_disables_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(heartbeat, "_acquire_lock", lambda *_args: (None, "lock-unreadable"))
    disabled = []
    receipt = heartbeat.heartbeat_once(
        ROOT,
        state_root=tmp_path,
        clock=lambda: 1_000_000,
        disable_launch_agent=lambda: disabled.append(True),
    )
    assert receipt["status"] == "failed"
    assert receipt["disabled"] is True
    assert disabled == [True]


def test_unreadable_state_fails_closed_and_disables(tmp_path, monkeypatch):
    (tmp_path / "state.json").write_text("not-json")
    monkeypatch.setattr(
        heartbeat,
        "run_bounded_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("probe spawned")),
    )
    disabled = []
    receipt = heartbeat.heartbeat_once(
        ROOT,
        state_root=tmp_path,
        clock=lambda: 1_000_000,
        disable_launch_agent=lambda: disabled.append(True),
    )
    assert receipt["status"] == "failed"
    assert receipt["consecutive_system_failures"] == 3
    assert disabled == [True]
    assert list(tmp_path.glob("state.invalid.*.json"))


def test_registry_probes_match_observer_host_ownership():
    contract, _digest = heartbeat._load_contract(ROOT)
    scheduled = {row["name"] for row in contract["probes"]}
    ownership = json.loads((ROOT / "institutio/governance/heartbeat-ownership.json").read_text())["rungs"]
    assert {name for name, row in ownership.items() if row["owner"] == "observe_host"} <= scheduled


def test_contract_initialization_failure_writes_receipts_and_disables(tmp_path):
    root = tmp_path / "missing-contract-root"
    root.mkdir()
    state_root = tmp_path / "state"
    disabled = []

    receipt = heartbeat.heartbeat_once(
        root,
        state_root=state_root,
        clock=lambda: 1_000_000,
        disable_launch_agent=lambda: disabled.append(True),
    )

    assert receipt["status"] == "failed"
    assert receipt["disabled"] is True
    assert receipt["contract_digest"] is None
    assert disabled == [True]
    assert json.loads((state_root / "public-latest.json").read_text())["status"] == "failed"
    assert list((state_root / "receipts").glob("*.json"))


def test_contract_initialization_failure_still_disables_when_receipt_storage_fails(tmp_path, monkeypatch):
    root = tmp_path / "missing-contract-root"
    root.mkdir()
    disabled = []
    receipt_attempted = []

    def fail_receipt(*_args, **_kwargs):
        receipt_attempted.append(True)
        raise OSError("receipt storage unavailable")

    def disable():
        assert receipt_attempted == [True]
        disabled.append(True)

    monkeypatch.setattr(heartbeat, "_initialization_failure_receipt", fail_receipt)

    with pytest.raises(OSError, match="receipt storage unavailable"):
        heartbeat.heartbeat_once(
            root,
            state_root=tmp_path / "state",
            clock=lambda: 1_000_000,
            disable_launch_agent=disable,
        )

    assert disabled == [True]


def test_contract_initialization_failure_persists_before_kill_switch_failure(tmp_path):
    root = tmp_path / "missing-contract-root"
    root.mkdir()
    state_root = tmp_path / "state"

    def fail_disable():
        assert json.loads((state_root / "public-latest.json").read_text())["status"] == "failed"
        assert list((state_root / "receipts").glob("*.json"))
        raise heartbeat.HeartbeatContractError("kill switch unavailable")

    with pytest.raises(heartbeat.HeartbeatContractError, match="kill switch unavailable"):
        heartbeat.heartbeat_once(
            root,
            state_root=state_root,
            clock=lambda: 1_000_000,
            disable_launch_agent=fail_disable,
        )
