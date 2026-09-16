from datetime import datetime, UTC
import json
import importlib.util
from pathlib import Path
import time

import pytest
from limen.inventory_admission import admit_execution, reserve_growth, InventoryAdmissionError

NOW = datetime(2026, 9, 16, tzinfo=UTC)
POLICY = {
    "mode": "dispatch",
    "approved_priorities": [
        {
            "outcome_id": "recovery",
            "enabled": True,
            "work_keys": ["approved", "replacement"],
            "resource_limits": {"issue": 1},
        }
    ],
}


def packet(key="approved", parent=None, digest="first"):
    return {
        "work_key": key,
        "parent_run_id": parent,
        "execution_hash": digest,
        "deadline": "2026-09-17T00:00:00Z",
        "retry": {"max_attempts": 1},
    }


def test_unapproved_and_renamed_denied():
    with pytest.raises(InventoryAdmissionError, match="priority_not_approved"):
        admit_execution(POLICY, {"runs": {}}, packet("renamed"), NOW)


def test_restart_and_child_cannot_replenish_budget():
    p = packet()
    admission = admit_execution(POLICY, {"runs": {}}, p, NOW)
    assert admission["attempt_deadline"] == "2026-09-16T00:30:00+00:00"
    runs = {
        str(i): {
            "status": "expired",
            "packet": p,
            "execution_admission": admission,
            "parent_run_id": None if i == 0 else "0",
        }
        for i in range(4)
    }
    restored = json.loads(json.dumps({"runs": runs}))
    with pytest.raises(InventoryAdmissionError, match="outcome_budget_exhausted"):
        admit_execution(POLICY, restored, packet("renamed-child", "0"), NOW)


def test_retry_requires_changed_inputs_and_stops_after_one_correction():
    p = packet()
    admission = admit_execution(POLICY, {"runs": {}}, p, NOW)
    state = {"runs": {"a": {"status": "failed", "packet": p, "execution_admission": admission, "parent_run_id": None}}}
    with pytest.raises(InventoryAdmissionError, match="inputs_unchanged"):
        admit_execution(POLICY, state, packet("replacement"), NOW)
    new = packet("replacement", digest="changed-inputs")
    state["runs"]["b"] = {
        "status": "failed",
        "packet": new,
        "parent_run_id": None,
        "execution_admission": admit_execution(POLICY, state, new, NOW),
    }
    with pytest.raises(InventoryAdmissionError, match="corrective_retry_exhausted"):
        admit_execution(POLICY, state, packet(digest="third"), NOW)


def test_issue_limit_survives_producer_restart(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs/autonomy-policy.json").write_text(json.dumps(POLICY))
    reserve_growth("issue", "first", work_key="approved", root=tmp_path)
    with pytest.raises(InventoryAdmissionError, match="resource_budget_exhausted"):
        reserve_growth("issue", "second", work_key="replacement", root=tmp_path)


def test_verification_cache_changes_with_dependency_and_deadline_wins(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts/verify.py"
    spec = importlib.util.spec_from_file_location("bounded_verify", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "git_paths", lambda *args: ["check.py", "requirements.txt"])
    monkeypatch.setattr(module, "git", lambda *args: str(tmp_path / ".git"))
    (tmp_path / "check.py").write_text("answer = 42\n")
    (tmp_path / "requirements.txt").write_text("first\n")
    gate = {
        "kind": "per_file",
        "note": "syntax",
        "per_file": {".py": "python3 -m py_compile {file}"},
        "timeout_seconds": 1800,
    }
    kwargs = dict(jobs=1, timeout_seconds=1, output_limit_bytes=1024, wave_name="fixture")
    assert module.run_gate_wave(["syntax"], {"syntax": gate}, {}, ["check.py"], **kwargs)
    calls = []
    original = module.run_gate

    def observed(*args, **kw):
        calls.append(1)
        return original(*args, **kw)

    monkeypatch.setattr(module, "run_gate", observed)
    assert module.run_gate_wave(["syntax"], {"syntax": gate}, {}, ["check.py"], **kwargs)
    assert not calls
    (tmp_path / "requirements.txt").write_text("changed\n")
    assert module.run_gate_wave(["syntax"], {"syntax": gate}, {}, ["check.py"], **kwargs)
    assert calls == [1]
    assert not module.run_gate_wave(
        ["syntax"], {"syntax": gate}, {}, ["check.py"], aggregate_deadline=time.monotonic() - 1, **kwargs
    )
