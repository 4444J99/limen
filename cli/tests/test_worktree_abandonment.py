from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from limen import worktree_abandonment as abandonment
from limen.action_admission import classify_bash


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _repo_with_worktree(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    (repo / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-qm", "initial")
    target = tmp_path / "linked"
    _git(repo, "worktree", "add", "-q", "-b", "work/test", str(target), "HEAD")
    return repo, target


def test_detach_registered_worktree_is_non_forced_and_receipted(tmp_path: Path) -> None:
    repo, target = _repo_with_worktree(tmp_path)
    receipts = tmp_path / "receipts"

    result = abandonment.detach_registered_worktree(
        repo,
        target,
        reason="test-clean-preserved",
        receipt_root=receipts,
        owner_probe=lambda _path: None,
    )

    assert result["schema"] == abandonment.WORKTREE_ABANDONMENT_SCHEMA
    assert result["state"] == "completed"
    assert result["result"]["detached"] is True
    assert not target.exists()
    assert _git(repo, "show-ref", "--verify", "refs/heads/work/test")
    receipt = json.loads(Path(result["receipt_path"]).read_text(encoding="utf-8"))
    assert receipt["state"] == "completed"


@pytest.mark.parametrize("owner", [4242, -1])
def test_detach_denies_active_or_unobservable_owner_and_preserves_root(
    tmp_path: Path,
    owner: int,
) -> None:
    repo, target = _repo_with_worktree(tmp_path)

    with pytest.raises(abandonment.WorktreeAbandonmentError) as caught:
        abandonment.detach_registered_worktree(
            repo,
            target,
            reason="test",
            receipt_root=tmp_path / "receipts",
            owner_probe=lambda _path: owner,
        )

    assert target.exists()
    assert caught.value.receipt["state"] == "crashed"
    assert "active-process-cwd" in str(caught.value) or "owner-probe-unavailable" in str(caught.value)


def test_detach_denies_dirty_root_without_cleanup(tmp_path: Path) -> None:
    repo, target = _repo_with_worktree(tmp_path)
    (target / "untracked.txt").write_text("keep me\n", encoding="utf-8")

    with pytest.raises(abandonment.WorktreeAbandonmentError):
        abandonment.detach_registered_worktree(
            repo,
            target,
            reason="test",
            receipt_root=tmp_path / "receipts",
            owner_probe=lambda _path: None,
        )

    assert (target / "untracked.txt").read_text(encoding="utf-8") == "keep me\n"


def test_quarantine_atomically_preserves_bytes(tmp_path: Path) -> None:
    source = tmp_path / "creation-root" / "candidate"
    source.mkdir(parents=True)
    (source / "private.txt").write_text("preserve\n", encoding="utf-8")
    quarantine = tmp_path / "quarantine"

    result = abandonment.quarantine_path(
        source,
        quarantine,
        reason="test",
        receipt_root=tmp_path / "receipts",
        destination_name="candidate-preserved",
        owner_probe=lambda _path: None,
    )

    destination = Path(result["result"]["destination"])
    assert not source.exists()
    assert (destination / "private.txt").read_text(encoding="utf-8") == "preserve\n"
    assert result["state"] == "completed"


def test_quarantine_cross_filesystem_denial_preserves_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    quarantine = tmp_path / "quarantine"
    monkeypatch.setattr(abandonment, "_same_filesystem", lambda _source, _root: False)

    with pytest.raises(abandonment.WorktreeAbandonmentError) as caught:
        abandonment.quarantine_path(
            source,
            quarantine,
            reason="test",
            receipt_root=tmp_path / "receipts",
            owner_probe=lambda _path: None,
        )

    assert source.exists()
    assert caught.value.receipt["state"] == "crashed"
    assert "cross-filesystem" in str(caught.value)


def test_quarantine_rename_failure_is_typed_and_preserves_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(os, "rename", lambda _source, _destination: (_ for _ in ()).throw(OSError("boom")))

    with pytest.raises(abandonment.WorktreeAbandonmentError) as caught:
        abandonment.quarantine_path(
            source,
            tmp_path / "quarantine",
            reason="test",
            receipt_root=tmp_path / "receipts",
            owner_probe=lambda _path: None,
        )

    assert source.exists()
    assert caught.value.receipt["phase"] == "move"
    assert caught.value.receipt["crash"]["code"] == "quarantine-denied"


def test_quarantine_defaults_to_fail_closed_owner_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(abandonment, "_default_cwd_owner_probe", lambda _path: 4242)

    with pytest.raises(abandonment.WorktreeAbandonmentError, match="active-process-cwd:4242"):
        abandonment.quarantine_path(
            source,
            tmp_path / "quarantine",
            reason="test",
            receipt_root=tmp_path / "receipts",
        )

    assert source.exists()
    assert not (tmp_path / "quarantine").exists()


def test_quarantine_nesting_denial_has_no_preflight_directory_side_effect(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    quarantine = source / "nested" / "quarantine"

    with pytest.raises(abandonment.WorktreeAbandonmentError, match="nesting"):
        abandonment.quarantine_path(
            source,
            quarantine,
            reason="test",
            receipt_root=tmp_path / "receipts",
            owner_probe=lambda _path: None,
        )

    assert source.exists()
    assert not quarantine.exists()


def test_stable_zero_byte_lock_removal_requires_exact_unowned_identity(tmp_path: Path) -> None:
    lock = tmp_path / "index.lock"
    lock.touch()
    identity = abandonment.capture_lock_identity(lock)

    result = abandonment.remove_stable_zero_byte_lock(
        lock,
        identity,
        reason="test-stable-lock",
        receipt_root=tmp_path / "receipts",
        owner_probe=lambda _path: None,
    )

    assert result["state"] == "completed"
    assert result["result"]["removed"] is True
    assert not lock.exists()


@pytest.mark.parametrize("owner", [5150, -1])
def test_stable_lock_owner_or_probe_failure_denies_and_preserves(
    tmp_path: Path,
    owner: int,
) -> None:
    lock = tmp_path / "index.lock"
    lock.touch()
    identity = abandonment.capture_lock_identity(lock)

    with pytest.raises(abandonment.WorktreeAbandonmentError):
        abandonment.remove_stable_zero_byte_lock(
            lock,
            identity,
            reason="test",
            receipt_root=tmp_path / "receipts",
            owner_probe=lambda _path: owner,
        )

    assert lock.exists()


def test_stable_lock_identity_drift_denies_and_preserves(tmp_path: Path) -> None:
    lock = tmp_path / "index.lock"
    lock.touch()
    identity = abandonment.capture_lock_identity(lock)
    lock.write_text("changed\n", encoding="utf-8")

    with pytest.raises(abandonment.WorktreeAbandonmentError):
        abandonment.remove_stable_zero_byte_lock(
            lock,
            identity,
            reason="test",
            receipt_root=tmp_path / "receipts",
            owner_probe=lambda _path: None,
        )

    assert lock.read_text(encoding="utf-8") == "changed\n"


def test_lock_capture_rejects_nonzero_and_symlink(tmp_path: Path) -> None:
    nonzero = tmp_path / "nonzero.lock"
    nonzero.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="zero-byte"):
        abandonment.capture_lock_identity(nonzero)

    target = tmp_path / "target"
    target.touch()
    symlink = tmp_path / "symlink.lock"
    symlink.symlink_to(target)
    with pytest.raises(ValueError, match="regular-file"):
        abandonment.capture_lock_identity(symlink)


def test_abandonment_cli_is_a_sanctioned_control_surface() -> None:
    action = classify_bash(
        "python3 scripts/worktree-abandonment.py quarantine "
        "--source /tmp/example --quarantine-root /tmp/quarantine --reason test"
    )

    assert action.category == "sanctioned_control"


def test_abandonment_sources_contain_no_raw_cleanup_primitive() -> None:
    cli_root = Path(__file__).resolve().parents[1]
    module_text = (cli_root / "src" / "limen" / "worktree_abandonment.py").read_text(encoding="utf-8")
    reaper_text = (cli_root.parent / "scripts" / "reclaim-worktrees.py").read_text(encoding="utf-8")

    for forbidden in ("shutil.rmtree", '["clean"', '"--force", str(d)'):
        assert forbidden not in module_text
        assert forbidden not in reaper_text
