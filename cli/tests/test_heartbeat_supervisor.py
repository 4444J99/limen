import json
from pathlib import Path

from limen import heartbeat
from limen.bounded_subprocess import BoundedCompletedProcess, BoundedSubprocessError


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


def _state(path, *, failures=0, disabled=False, probes=None):
    path.mkdir(parents=True, exist_ok=True)
    (path / "state.json").write_text(
        json.dumps(
            {
                "schema": heartbeat.STATE_SCHEMA,
                "consecutive_system_failures": failures,
                "disabled": disabled,
                "probes": probes or {},
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
    commands = {probe["name"]: probe["command"] for probe in contract["probes"]}
    assert "--no-receipt" in commands["background-items-census"]
    assert "--no-receipt" in commands["live-checkout-currency"]
    assert "--no-write" in commands["cloud-storage-doctor"]
    assert "--no-write" in commands["tcc-track-c"]


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
    )
    assert receipt["status"] == "failed"
    assert receipt["consecutive_system_failures"] == 3
    assert receipt["disabled"] is True
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
