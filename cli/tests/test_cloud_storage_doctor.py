from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "cloud-storage-doctor.py"

# Captured live on this host 2026-07-15 (brctl status com.apple.CloudDocs) — ANSI-laden,
# undocumented format; the parser must key on tokens, never on structure.
BRCTL_SAMPLE = (
    "1 containers matching 'com.apple.CloudDocs'\n"
    "<com.apple.CloudDocs[1] \x1b[0;1;32mforeground\x1b[0m {client:idle "
    "server:full-sync|fetched-recents|fetched-favorites|ever-full-sync sync:oob-sync-ack "
    "last-sync:2026-07-15 08:47:34.056, requestID:15128, caught-up, token:unkown-token-size:35 "
    "(HwoFCNaihAIYACIVCIeLwenQxaenZBDuj43Xk6u/urIBKAA=) zoneActiveState:{rid:15129} "
    "appuninstalled:(null)}>"
)


def _load(name: str = "cloud_storage_doctor_uut"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_brctl_parse_caught_up_and_last_sync():
    mod = _load()
    parsed = mod.parse_brctl(0, BRCTL_SAMPLE)
    assert parsed["verdict"] == "match"
    assert parsed["caught_up"] is True
    assert parsed["last_sync"] == "2026-07-15 08:47:34.056"


def test_brctl_parse_no_token_is_drift_and_rc_nonzero_is_unknown():
    mod = _load()
    assert mod.parse_brctl(0, "1 containers matching\n<... client:syncing ...>")["verdict"] == "drift"
    assert mod.parse_brctl(1, "")["verdict"] == "unknown"
    assert mod.parse_brctl(None, "")["verdict"] == "unknown"


def test_account_mask_leaves_no_at_tokens():
    mod = _load()
    report = {
        "rails": {"googledrive": {"notes": ["dir GoogleDrive-4444@example.org present"]}},
        "census": {"unrecognized": ["GoogleDrive-4444@example.org"]},
    }
    masked = mod._mask(report)
    assert "@" not in json.dumps(masked)
    assert "<account>" in json.dumps(masked)


def test_remnant_check_over_baseline_is_drift(tmp_path):
    mod = _load()
    for stamp in ("2-19-26", "2-20-26", "2-22-26", "7-15-26"):
        (tmp_path / f"iCloudDrive-iCloudDrive ({stamp})").mkdir()
    accepted = [{"pattern": str(tmp_path / "iCloudDrive-iCloudDrive (*"), "max_count": 3}]
    notes, drifts = mod.remnant_check(accepted)
    assert len(drifts) == 1 and "4>3" in drifts[0]
    (tmp_path / "iCloudDrive-iCloudDrive (7-15-26)").rmdir()
    notes, drifts = mod.remnant_check(accepted)
    assert drifts == [] and len(notes) == 1


def test_dormant_layer_present_is_drift(tmp_path):
    mod = _load()
    fake_app = tmp_path / "Dropbox.app"
    fake_app.mkdir()
    expect = {"apps": [str(fake_app)], "fileprovider_tokens": ["getdropbox"]}
    notes, drifts = mod.dormant_check(expect, "com.getdropbox.dropbox.fileprovider")
    assert len(drifts) == 2  # app present AND provider registered
    notes, drifts = mod.dormant_check(
        {"apps": [str(tmp_path / "Absent.app")], "fileprovider_tokens": ["getdropbox"]}, "unrelated plugins"
    )
    assert drifts == []


def test_evaluate_rail_pending_gates_are_advisory_but_dormant_layer_drifts(tmp_path):
    mod = _load()
    fake_app = tmp_path / "Google Drive.app"
    fake_app.mkdir()
    rail = {
        "declared_state": "pending-trust-gates",
        "dormant_expectations": {"apps": [str(fake_app)], "fileprovider_tokens": []},
        "trust_gates": [{"id": "token", "gate": "x", "automatable": True}],
    }
    res = mod.evaluate_rail("googledrive", rail, {"ps": "", "pluginkit": ""})
    assert res["verdict"] == "drift"
    rail["dormant_expectations"] = {"apps": [str(tmp_path / "Absent.app")], "fileprovider_tokens": []}
    res = mod.evaluate_rail("googledrive", rail, {"ps": "", "pluginkit": ""})
    assert res["verdict"] == "match"  # unresolved trust gates are advisory while pending


def test_evaluate_rail_required_mount_missing_is_drift():
    mod = _load()
    rail = {
        "declared_state": "adopted",
        "mount": "/Volumes/definitely-not-a-volume-xyz",
        "required_mounted": True,
        "trust_gates": [{"id": "mounted", "gate": "m", "automatable": True}],
    }
    res = mod.evaluate_rail("archive4t", rail, {"ps": "", "pluginkit": ""})
    assert res["verdict"] == "drift"
    assert res["gates"]["automatable_fail"] == 1
    rail["required_mounted"] = False
    res = mod.evaluate_rail("archive4t", rail, {"ps": "", "pluginkit": ""})
    assert res["verdict"] == "match"


def test_gates_summary_counts_manual_outstanding():
    mod = _load()
    rail = {
        "trust_gates": [
            {"id": "a", "gate": "x", "automatable": True},
            {"id": "b", "gate": "y", "automatable": False, "proven": None},
            {"id": "c", "gate": "z", "automatable": False, "proven": "2026-07-01 receipt"},
        ]
    }
    summary = mod.gates_summary(rail, {"a": True})
    assert summary == {"automatable_pass": 1, "automatable_fail": 0, "manual_outstanding": 1}


def test_doctor_flags_bad_registry(tmp_path, monkeypatch):
    mod = _load()
    bad = tmp_path / "storage-roles.yaml"
    bad.write_text("rails:\n  x:\n    service: s\n    declared_state: bogus\n", encoding="utf-8")
    monkeypatch.setattr(mod, "REGISTRY", bad)
    assert mod.doctor() == 1


def test_doctor_ok_on_shipped_registry():
    mod = _load()
    assert mod.doctor() == 0
