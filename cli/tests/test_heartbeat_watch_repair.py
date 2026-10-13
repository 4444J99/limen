"""Watch regressions: complete single inventory, reason custody and clock provenance."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from limen import heartbeat
from limen.bounded_subprocess import BoundedCompletedProcess
from limen.bounded_subprocess import BoundedSubprocessError, run_bounded_subprocess
from limen.notification_effect import DeliveryReceipt

ROOT = Path(__file__).resolve().parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROLLOUT = _load("watch_rollout", ROOT / "scripts/check-heartbeat-rollout.py")
AUDIT = _load("watch_audit", ROOT / "scripts/tcc-identity-audit.py")


def test_malformed_clock_sample_stays_unmeasured_instead_of_crashing_watch():
    before = {"observed_epoch": 1000, "clock_observation": "untrusted"}
    after = {"observed_epoch": 2500, "clock_observation": {}}
    assert ROLLOUT.cadence_interval(before, after, 1080)["classification"] == "unmeasured"


def test_malformed_reason_collection_does_not_invent_one_character_denials():
    payload = {
        "schema": "limen.runtime_maintenance_observation.v1",
        "status": "blocked",
        "pool": {"denial_reasons": "private"},
    }
    assert heartbeat._probe_evidence({"name": "runtime-maintenance-observation"}, json.dumps(payload).encode()) is None


def _dialog_run(tmp_path, *, measured, malformed):
    root = tmp_path / "repository"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    home = tmp_path / "home"
    home.mkdir()
    binary = tmp_path / "bin"
    binary.mkdir()
    os.symlink(sys.executable, binary / "python3")
    marker = tmp_path / "extra-inventory"
    registry = binary / "lsregister"
    registry.write_text(f"#!/bin/sh\necho duplicate >> '{marker}'\nexit 0\n")
    registry.chmod(0o755)
    source = (ROOT / "scripts/dialogs-silenced.sh").read_text()
    source = source.replace(
        "/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Support/lsregister",
        str(registry),
    )
    (scripts / "dialogs-silenced.sh").write_text(source)
    helpers = [{"path": str(home / ".local/share/claude/ClaudeCode.app"), "detail": "not sealed"}] if malformed else []
    payload = {
        "schema": "limen.tcc_identity_audit.v2",
        "ok": not malformed and measured,
        "status": "blocked" if malformed else "ok" if measured else "unmeasured",
        "measured": {
            "launchservices": measured,
            "blind_failures": [] if measured else ["claude_helper_registration_unreadable"],
        },
        "malformed_claude_helpers": helpers,
        "failures": ["malformed_claude_helper_registration"]
        if malformed
        else []
        if measured
        else ["claude_helper_registration_unreadable"],
    }
    audit = scripts / "tcc-identity-audit"
    audit.write_text(
        f"#!{sys.executable}\nimport json\nprint(json.dumps({payload!r}))\nraise SystemExit({int(not payload['ok'])})\n"
    )
    audit.chmod(0o755)
    result = subprocess.run(
        ["/bin/bash", str(scripts / "dialogs-silenced.sh"), "--agent-curable-only"],
        env={"HOME": str(home), "PATH": f"{binary}:/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result, marker


def test_dialogs_uses_complete_audit_inventory_without_a_second_launchservices_pass(tmp_path):
    result, marker = _dialog_run(tmp_path, measured=True, malformed=True)
    assert result.returncode == 1
    assert "ClaudeCode.app cannot be assessed" in result.stdout
    assert not marker.exists(), "A second inventory can overrun the unchanged 30-second probe"


def test_dialogs_missing_inventory_never_reports_inert(tmp_path):
    result, marker = _dialog_run(tmp_path, measured=False, malformed=False)
    assert result.returncode == 1
    assert "UNMEASURED" in result.stdout
    assert "ClaudeCode.app is inert" not in result.stdout
    assert not marker.exists()


def test_dialogs_complete_empty_inventory_is_inert_without_reenumeration(tmp_path):
    result, marker = _dialog_run(tmp_path, measured=True, malformed=False)
    assert result.returncode == 0
    assert "ClaudeCode.app is inert" in result.stdout
    assert not marker.exists()


def test_maintenance_finding_keeps_typed_denial_without_private_output(tmp_path, monkeypatch):
    report = {
        "schema": "limen.runtime_maintenance_observation.v1",
        "status": "inspection_blocked",
        "pool": {"allowed": False, "denial_reasons": ["broker_storage_census_unavailable"]},
        "private": "Bearer secret /private/customer",
    }
    monkeypatch.setattr(
        heartbeat,
        "run_bounded_subprocess",
        lambda *_a, **_k: BoundedCompletedProcess(1, json.dumps(report).encode(), b""),
    )
    receipt = heartbeat.heartbeat_once(
        ROOT,
        state_root=tmp_path,
        clock=lambda: 1000000,
        notification_emitter=lambda _root, candidate: DeliveryReceipt(
            "withheld",
            candidate.event["stable_id"],
            candidate.event["event_id"],
            {},
        ),
    )
    assert receipt.get("probe_evidence", {}).get("reason_codes") == ["broker_storage_census_unavailable"]
    assert "Bearer secret" not in json.dumps(receipt)
    assert "probe_evidence" not in json.loads((tmp_path / "public-latest.json").read_text())


def test_each_fire_records_clock_provenance_without_changing_probe_selection(tmp_path, monkeypatch):
    sample = {
        "schema": "limen.heartbeat_clock.v1",
        "measured": True,
        "boot_id": "a" * 64,
        "awake_ns": 1000000000,
        "continuous_ns": 2000000000,
    }
    monkeypatch.setattr(heartbeat, "_clock_observation", lambda: sample, raising=False)
    monkeypatch.setattr(heartbeat, "run_bounded_subprocess", lambda *_a, **_k: BoundedCompletedProcess(0, b"{}", b""))
    receipt = heartbeat.heartbeat_once(ROOT, state_root=tmp_path, clock=lambda: 1000000)
    assert receipt.get("clock_observation") == sample
    assert receipt["probe"] == "runtime-maintenance-observation"


def test_clock_sample_is_bound_to_fire_start_not_variable_probe_completion(tmp_path, monkeypatch):
    ticks = [1_000_000_000]
    monkeypatch.setattr(heartbeat, "_clock_observation", lambda: {"awake_ns": ticks[0]}, raising=False)

    def probe(*_args, **_kwargs):
        ticks[0] += 30_000_000_000
        return BoundedCompletedProcess(0, b"{}", b"")

    monkeypatch.setattr(heartbeat, "run_bounded_subprocess", probe)
    receipt = heartbeat.heartbeat_once(ROOT, state_root=tmp_path, clock=lambda: 1000000)
    assert receipt["clock_observation"]["awake_ns"] == 1_000_000_000


@pytest.mark.parametrize(
    "wall,continuous,awake,boot,expected",
    [
        (1825, 1825, 925, "a", "sleep_explained"),
        (1502, 1502, 928, "a", "sleep_explained"),
        (1500, 1500, 1500, "a", "awake_gap"),
        (1800, 900, 900, "a", "wall_clock_changed"),
        (1500, 50, 50, "b", "boot_changed"),
    ],
)
def test_cadence_distinguishes_sleep_backlog_clock_change_and_reboot(wall, continuous, awake, boot, expected):
    before = {
        "observed_epoch": 1000,
        "clock_observation": {
            "schema": "limen.heartbeat_clock.v1",
            "measured": True,
            "boot_id": "a" * 64,
            "awake_ns": 1000000000,
            "continuous_ns": 1000000000,
        },
    }
    after = {
        "observed_epoch": 1000 + wall,
        "clock_observation": {
            "schema": "limen.heartbeat_clock.v1",
            "measured": True,
            "boot_id": boot * 64,
            "awake_ns": (1 + awake) * 10**9,
            "continuous_ns": (1 + continuous) * 10**9,
        },
    }
    classify = getattr(ROLLOUT, "cadence_interval", None)
    assert callable(classify), "Cadence needs independently measured awake/boot evidence"
    result = classify(before, after, 1080)
    assert result["classification"] == expected
    assert result["wall_seconds"] == wall


def test_legacy_receipts_do_not_invent_sleep_or_elapsed_coverage():
    classify = getattr(ROLLOUT, "cadence_interval", None)
    assert callable(classify), "Legacy gaps must stay unmeasured"
    result = classify({"observed_epoch": 1000}, {"observed_epoch": 2800}, 1080)
    assert result["classification"] == "unmeasured"
    assert result["wall_seconds"] == 1800


def test_executed_probes_cannot_hide_a_measured_awake_cadence_violation(tmp_path, monkeypatch):
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps(
            {
                "processes": {
                    "com.limen.heartbeat": {
                        "launchd": {"start_interval_seconds": 180},
                        "probes": [{"name": "runtime-maintenance-observation", "cadence_seconds": 900}],
                    }
                }
            }
        )
    )
    monkeypatch.setattr(ROLLOUT, "CONTRACTS", contract)
    rows = tmp_path / "receipts"
    rows.mkdir()
    for index, epoch in enumerate((1000, 2500)):
        row = {
            "schema": "limen.heartbeat_private_receipt.v1",
            "runtime_sha": "a" * 40,
            "probe": "runtime-maintenance-observation",
            "observed_epoch": epoch,
            "status": "passed",
            "returncode": 0,
            "disabled": False,
            "surviving_descendant_count": 0,
            "clock_observation": {
                "schema": "limen.heartbeat_clock.v1",
                "measured": True,
                "boot_id": "b" * 64,
                "awake_ns": epoch * 10**9,
                "continuous_ns": epoch * 10**9,
            },
        }
        (rows / f"{index}.json").write_text(json.dumps(row))
    result = ROLLOUT.scheduled_probe_report(rows, "a" * 40, now=2600)
    assert result["execution_complete"] is True
    assert result.get("maintenance_cadence_violations") == 1
    assert result["complete_elapsed_window_claimed"] is False


def test_audit_budget_caps_every_native_command(tmp_path, monkeypatch):
    # Real audit runs against an unreadable database; only OS command boundaries are substituted.
    ticks = iter([0.0, 0.1, 20.1])
    monkeypatch.setattr(AUDIT, "monotonic", lambda: next(ticks, 20.1), raising=False)
    calls = []

    def native(command, **kwargs):
        calls.append((command, kwargs["timeout"]))
        return subprocess.CompletedProcess(command, 1, "", "unavailable")

    report = AUDIT.audit(
        {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}, platform_name="Darwin", runner=native, budget_seconds=20
    )
    assert report["ok"] is False
    assert report["measured"]["budget_exhausted"] is True
    assert all(timeout <= 20 for _, timeout in calls)


def test_timeout_preserves_bounded_partial_output_without_claiming_descendant_cleanup():
    with pytest.raises(BoundedSubprocessError) as caught:
        run_bounded_subprocess(
            [sys.executable, "-c", "import time; print('before-timeout', flush=True); time.sleep(60)"],
            cwd=ROOT,
            timeout_seconds=0.5,
            stdout_ceiling=1024,
            stderr_ceiling=1024,
        )
    assert caught.value.kind == "timeout"
    assert getattr(caught.value, "stdout", None) == b"before-timeout\n"
    assert getattr(caught.value, "root_reaped", None) is True
