"""Session closeout integration cases with real Git porcelain and publication."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from limen import session_closeout as closeout

SID = "test-native-session"
OWNER = "https://github.com/example/project/issues/1"


def command(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).rstrip("\n")


@pytest.fixture
def case(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    root = tmp_path / "session"
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "work", str(root)], check=True, capture_output=True)
    command(root, "config", "user.name", "Fixture")
    command(root, "config", "user.email", "fixture@example.test")
    command(root, "config", "commit.gpgsign", "false")
    command(root, "remote", "add", "origin", str(remote))
    (root / "implementation.py").write_text("value = 1\n")
    (root / "sibling.txt").write_text("baseline\n")
    command(root, "add", "implementation.py", "sibling.txt")
    command(root, "commit", "-m", "implementation")
    head = command(root, "rev-parse", "HEAD")
    (root / "evidence.txt").write_text("fixture predicate exited 0; fixture has no private payload\n")
    digest = hashlib.sha256((root / "evidence.txt").read_bytes()).hexdigest()
    receipt = {
        "base_head": head,
        "schema": closeout.SCHEMA,
        "session_id": SID,
        "worktree_name": root.name,
        "repository": str(remote).removesuffix(".git"),
        "publication_branch": "work",
        "disposition": "handoff",
        "owner_url": OWNER,
        "owned_paths": ["implementation.py"],
        "retained_work": [],
        "verification": [{"head": head, "exit_code": 0, "evidence": "evidence.txt", "sha256": digest}],
        "custody": {"verified": True, "evidence": "evidence.txt", "sha256": digest},
    }
    audit = {
        "session_id": SID,
        "session_present": True,
        "active_lease_count": 0,
        "retained_run_count": 0,
        "coverage": {"retained_state_complete": True, "request_history": "unmeasured"},
        "runs": [],
    }
    binding = {"session_id": SID, "worktree": str(root)}
    path = root / "session-closeout.json"

    def publish():
        path.write_text(json.dumps(receipt))
        command(root, "add", "session-closeout.json", "evidence.txt")
        command(root, "commit", "--allow-empty", "-m", "owner receipt")
        command(root, "push", "-u", "origin", "work")

    def evaluate(**kwargs):
        return closeout.evaluate(
            root,
            SID,
            path,
            audit=audit,
            binding=binding,
            read_owner=lambda url: {"html_url": url, "state": "open"},
            observe_processes=lambda *args: [],
            **kwargs,
        )

    publish()
    return root, receipt, audit, binding, publish, evaluate


def test_handoff_releases_session_without_claiming_task_or_estate_completion(case):
    *_, evaluate = case
    result = evaluate()
    assert result["session_released"]
    assert not result["task_completed"]
    assert not result["estate_completed"]
    assert not result["retirement_authorized"]
    assert not result["successor_required"]


def test_completed_session_needs_no_successor_and_recheck_has_no_writes(case):
    root, receipt, _, _, publish, evaluate = case
    receipt["disposition"] = "complete"
    publish()
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert evaluate()["task_completed"]
    assert evaluate() == evaluate()
    after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert before == after


def test_proven_sibling_edits_do_not_contaminate_session(case):
    root, receipt, _, _, publish, evaluate = case
    receipt["retained_work"] = [{"paths": ["sibling.txt"], "owner_url": OWNER}]
    publish()
    (root / "sibling.txt").write_text("concurrent edit one\n")
    first = evaluate()
    (root / "sibling.txt").write_text("concurrent edit two\n")
    assert evaluate() == first
    assert first["session_released"]


@pytest.mark.parametrize("name", ["implementation.py", "unknown file\nwith space"])
def test_owned_and_unattributed_dirty_paths_fail(case, name):
    root, *_, evaluate = case
    (root / name).write_text("dirty\n")
    result = evaluate()
    assert not result["session_released"]
    assert any(name in finding for finding in result["findings"])


def test_real_porcelain_preserves_first_modified_path_and_rename_source(case):
    root, *_, evaluate = case
    (root / "implementation.py").write_text("dirty\n")
    command(root, "mv", "sibling.txt", "renamed file.txt")
    data = closeout.git(root, "status", "--porcelain=v1", "-z", raw=True)
    assert closeout.dirty_paths(data) == {"implementation.py", "sibling.txt", "renamed file.txt"}
    assert not evaluate()["session_released"]


def test_detached_head_can_have_exact_remote_custody(case):
    root, *_, evaluate = case
    command(root, "checkout", "--detach")
    assert evaluate()["session_released"]


def test_unpublished_head_is_not_green(case):
    root, *_, evaluate = case
    command(root, "commit", "--allow-empty", "-m", "unpublished")
    assert "inspected head is not remotely durable" in evaluate()["findings"]


def test_changed_implementation_invalidates_passing_receipt(case):
    root, _, _, _, publish, evaluate = case
    (root / "implementation.py").write_text("value = 2\n")
    command(root, "add", "implementation.py")
    command(root, "commit", "-m", "changed")
    publish()
    assert "owned implementation changed since verification" in evaluate()["findings"]


@pytest.mark.parametrize("change", ["audit", "binding", "custody", "verification", "lease"])
def test_missing_or_wrong_evidence_never_releases(case, change):
    root, receipt, audit, binding, publish, evaluate = case
    if change == "audit":
        audit["coverage"]["retained_state_complete"] = False
    elif change == "binding":
        binding["worktree"] = str(root.parent)
    elif change == "custody":
        receipt["custody"]["verified"] = False
    elif change == "verification":
        receipt["verification"][0]["exit_code"] = 1
    else:
        audit["active_lease_count"] = 1
    publish()
    try:
        result = evaluate()
    except closeout.Unmeasured:
        return
    assert not result["session_released"]


def test_no_registration_is_not_zero_obligations(case):
    root, _, audit, _, _, _ = case
    audit["session_present"] = False
    with pytest.raises(closeout.Unmeasured, match="witness"):
        closeout.evaluate(root, SID, root / "session-closeout.json", audit=audit, binding=None)


def test_wrapper_requires_identity_instead_of_guessing_checkout():
    root = Path(__file__).resolve().parents[2]
    for script in ("scripts/no-tasks-on-me.sh", "scripts/closeout-fast.sh"):
        result = subprocess.run(["bash", str(root / script), "--json"], capture_output=True, text=True, check=False)
        assert result.returncode == 2
        assert "--session-id" in result.stderr


def test_native_witness_reads_only_exact_metadata(tmp_path):
    path = tmp_path / "transcript.jsonl"
    path.write_text(json.dumps({"type": "session_meta", "payload": {"id": SID}}) + "\nnot parsed")
    assert closeout.native_witness(path, SID)
    assert not closeout.native_witness(path, "another")


def test_omitted_committed_implementation_is_not_sibling_work(case):
    root, _, _, _, publish, evaluate = case
    (root / "forgotten.py").write_text("change\n")
    command(root, "add", "forgotten.py")
    command(root, "commit", "-m", "unattributed")
    publish()
    assert "unattributed committed path: forgotten.py" in evaluate()["findings"]


def test_surviving_process_blocks_release_without_signaling(case):
    root, _, audit, binding, _, _ = case
    result = closeout.evaluate(
        root,
        SID,
        root / "session-closeout.json",
        audit=audit,
        binding=binding,
        read_owner=lambda url: {"state": "open"},
        observe_processes=lambda *args: [12345],
    )
    assert not result["session_released"]
    assert result["process_count"] == 1


def test_remote_missing_or_unavailable_never_becomes_success(case):
    root, _, _, _, _, evaluate = case
    command(root, "remote", "set-url", "origin", str(root.parent / "absent.git"))
    with pytest.raises(closeout.Unmeasured):
        evaluate()


def test_external_receipt_preserves_subject_checkout(case, tmp_path):
    root, receipt, audit, binding, _, _ = case
    subject_head = command(root, "rev-parse", "HEAD")
    receipt_root = tmp_path / "receipt-owner"
    command(root, "worktree", "add", "-b", "receipt-owner", str(receipt_root))
    receipt.update(subject_head=subject_head, subject_publication_branch="work", publication_branch="receipt-owner")
    path = receipt_root / "session-closeout.json"
    path.write_text(json.dumps(receipt))
    command(receipt_root, "add", "session-closeout.json")
    command(receipt_root, "commit", "-m", "external owner receipt")
    command(receipt_root, "push", "origin", "receipt-owner")
    before = command(root, "status", "--porcelain=v1")
    result = closeout.evaluate(
        root,
        SID,
        path,
        audit=audit,
        binding=binding,
        read_owner=lambda url: {"state": "open"},
        observe_processes=lambda *args: [],
    )
    assert result["session_released"]
    assert command(root, "rev-parse", "HEAD") == subject_head
    assert command(root, "status", "--porcelain=v1") == before
    command(root, "commit", "--allow-empty", "-m", "moved subject")
    with pytest.raises(closeout.Unmeasured, match="exact subject head"):
        closeout.evaluate(root, SID, path, audit=audit, binding=binding)


def test_failed_completion_gate_can_be_handed_off_but_not_claimed_complete(case):
    _, receipt, _, _, publish, evaluate = case
    check = receipt["verification"][0]
    check.update(exit_code=75, purpose="completion", owner_url=OWNER)
    publish()
    result = evaluate()
    assert result["session_released"]
    assert not result["task_completed"]
    receipt["disposition"] = "complete"
    publish()
    assert not evaluate()["session_released"]


def test_failed_release_predicate_is_not_erased_by_handoff(case):
    _, receipt, _, _, publish, evaluate = case
    receipt["verification"][0].update(exit_code=1, purpose="release", owner_url=OWNER)
    publish()
    assert not evaluate()["session_released"]


def test_process_observer_does_not_count_its_own_lsof_child(tmp_path, monkeypatch):
    from unittest.mock import MagicMock
    import os

    monkeypatch.setattr(closeout, "run", lambda command: f"{os.getpid()} 1 checker")
    child = MagicMock()
    child.pid = 999999
    child.returncode = 0
    child.communicate.return_value = (f"p{child.pid}\nn{tmp_path}\n".encode(), b"")
    context = MagicMock()
    context.__enter__.return_value = child
    monkeypatch.setattr(closeout.subprocess, "Popen", lambda *args, **kwargs: context)
    assert closeout.process_observation(tmp_path, SID) == []
