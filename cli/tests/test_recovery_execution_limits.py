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


@pytest.mark.parametrize("condition", ["clean", "dirty", "ignored", "advanced", "active", "remote-missing"])
def test_release_retirement_preserves_uncertain_work_and_is_idempotent(tmp_path, condition):
    import subprocess
    from limen.worktree_abandonment import retire_released_worktree

    def git(*args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()

    repo, remote, wt = (tmp_path / name for name in ("repo", "remote.git", "copy"))
    git("init", "--bare", str(remote))
    git("init", str(repo))
    git("config", "user.email", "test@example.invalid", cwd=repo)
    git("config", "user.name", "Recovery fixture", cwd=repo)
    (repo / "source").write_text("original\n")
    (repo / ".gitignore").write_text("ignored\n")
    git("add", ".", cwd=repo)
    git("commit", "-m", "fixture", cwd=repo)
    git("remote", "add", "origin", str(remote), cwd=repo)
    git("worktree", "add", "-b", "work", str(wt), cwd=repo)
    git("push", "origin", "work", cwd=wt)
    head = git("rev-parse", "HEAD", cwd=wt)
    if condition == "dirty":
        (wt / "source").write_text("unfinished\n")
    if condition == "ignored":
        (wt / "ignored").write_text("private payload\n")
    if condition == "advanced":
        (wt / "source").write_text("advanced\n")
        git("commit", "-am", "new work", cwd=wt)
    if condition == "remote-missing":
        git("push", "origin", "--delete", "work", cwd=wt)
    kwargs = dict(
        expected_head=head,
        remote_ref="refs/heads/work",
        receipt_root=tmp_path / "receipts",
        owner_probe=lambda target: 123 if condition == "active" else None,
    )
    result = retire_released_worktree(repo, wt, **kwargs)
    if condition == "clean":
        assert result["state"] == "completed"
        assert not wt.exists()
        assert git("rev-parse", "refs/heads/work", cwd=repo) == head
        assert retire_released_worktree(repo, wt, **kwargs)["state"] == "already-absent"
    else:
        assert result["state"] == "retained"
        assert wt.exists()
        assert retire_released_worktree(repo, wt, **kwargs)["state"] == "retained"


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


def test_declared_cache_closure_reuses_only_unchanged_inputs_and_retains_live_receipts(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts/verify.py"
    spec = importlib.util.spec_from_file_location("closure_verify", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "git_paths", lambda *args: ["check.py", "requirements.txt", "notes.md"])
    monkeypatch.setattr(module, "git", lambda *args: str(tmp_path / ".git"))
    (tmp_path / "check.py").write_text("pass\n")
    (tmp_path / "requirements.txt").write_text("dep==1\n")
    (tmp_path / "notes.md").write_text("unrelated\n")
    gate = {
        "note": "closure fixture",
        "command": "python3 check.py",
        "cache": {"mode": "content", "inputs": ["check.py", "requirements.txt"]},
    }
    calls = []
    original = module.run_gate

    def observed(*args, **kw):
        calls.append(1)
        return original(*args, **kw)

    monkeypatch.setattr(module, "run_gate", observed)
    kwargs = dict(jobs=1, timeout_seconds=10, output_limit_bytes=1024, wave_name="closure")
    assert module.run_gate_wave(["check"], {"check": gate}, {}, ["check.py"], **kwargs)
    (tmp_path / "notes.md").write_text("changed unrelated input\n")
    assert module.run_gate_wave(["check"], {"check": gate}, {"unrelated": True}, ["notes.md"], **kwargs)
    assert len(calls) == 1
    (tmp_path / "requirements.txt").write_text("dep==2\n")
    assert module.run_gate_wave(["check"], {"check": gate}, {}, ["requirements.txt"], **kwargs)
    assert len(calls) == 2
    monkeypatch.setenv("VERIFY_FIXTURE_DEPENDENCY", "changed")
    assert module.run_gate_wave(["check"], {"check": gate}, {}, [], **kwargs)
    assert len(calls) == 3
    live = {"note": "live fixture", "command": "python3 check.py"}
    for _ in range(2):
        assert module.run_gate_wave(["live"], {"live": live}, {}, [], **kwargs)
    assert len(calls) == 5
    receipt = module.cache_path("live", module.verification_fingerprint(live, {}, []))
    assert json.loads(receipt.read_text())["reusable"] is False
