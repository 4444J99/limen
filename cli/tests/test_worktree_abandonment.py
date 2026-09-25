from __future__ import annotations

import hashlib
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
    expected_head = result["result"]["head"]
    assert (
        abandonment.completed_worktree_retirement(repo, target, expected_head, receipts)["receipt_path"]
        == result["receipt_path"]
    )
    assert abandonment.completed_worktree_retirement(repo, target, "f" * 40, receipts) is None
    retained = Path(result["result"]["admin_preservation"]["retained_original"])
    (retained / "new-evidence").write_text("changed since receipt")
    assert abandonment.completed_worktree_retirement(repo, target, expected_head, receipts) is None


def test_detach_retains_original_admin_inode_and_anchors_unique_reflog(tmp_path: Path) -> None:
    repo, target = _repo_with_worktree(tmp_path)
    base = _git(target, "rev-parse", "HEAD")
    (target / "tracked.txt").write_text("unique historical work\n")
    _git(target, "commit", "-qam", "unique worktree history")
    unique = _git(target, "rev-parse", "HEAD")
    _git(target, "reset", "--hard", base)
    _git(target, "update-ref", "refs/worktree/keep", unique)
    admin = Path(_git(target, "rev-parse", "--absolute-git-dir"))
    identity = admin.stat().st_ino
    log = (admin / "logs/HEAD").read_bytes()
    metadata = admin / "private-owner-record"
    metadata.write_bytes(b"local administrative evidence\n")
    metadata.chmod(0o600)
    metadata_identity = metadata.stat()
    result = abandonment.detach_registered_worktree(
        repo, target, reason="released", receipt_root=tmp_path / "receipts", owner_probe=lambda _: None
    )
    evidence = result["result"]["admin_preservation"]
    original = Path(evidence["retained_original"])
    assert original.stat().st_ino == identity
    assert (original / "logs/HEAD").read_bytes() == log
    assert (original / "private-owner-record").stat().st_ino == metadata_identity.st_ino
    assert (original / "private-owner-record").stat().st_mtime_ns == metadata_identity.st_mtime_ns
    assert (original / "private-owner-record").stat().st_mode == metadata_identity.st_mode
    assert not target.exists()
    assert not admin.exists()
    assert evidence["anchored_objects"] >= 2
    assert evidence["custody"] == "local-original-retained-store-must-remain"
    # Even after native reflogs expire, the original history remains reachable.
    _git(repo, "reflog", "expire", "--expire=now", "--all")
    reachable = _git(repo, "rev-list", "--all").splitlines()
    assert unique in reachable
    assert _git(repo, "show", f"{unique}:tracked.txt") == "unique historical work"


@pytest.mark.parametrize("entry", ["index.lock", "locked", "symlink", "MERGE_HEAD", "rebase-merge"])
def test_detach_rejects_locked_or_linked_admin(tmp_path: Path, entry: str) -> None:
    repo, target = _repo_with_worktree(tmp_path)
    admin = Path(_git(target, "rev-parse", "--absolute-git-dir"))
    if entry == "symlink":
        (admin / entry).symlink_to(admin / "HEAD")
    else:
        (admin / entry).write_text("retain")
    with pytest.raises(abandonment.WorktreeAbandonmentError):
        abandonment.detach_registered_worktree(
            repo, target, reason="released", receipt_root=tmp_path / "receipts", owner_probe=lambda _: None
        )
    assert target.exists()
    assert admin.exists()


@pytest.mark.parametrize("failure", ["corrupt-copy", "source-change", "copy-error", "swap-error"])
def test_admin_preservation_failure_retains_checkout_and_original(tmp_path: Path, monkeypatch, failure: str) -> None:
    repo, target = _repo_with_worktree(tmp_path)
    admin = Path(_git(target, "rev-parse", "--absolute-git-dir"))
    before = admin.stat().st_ino
    copytree = abandonment.shutil.copytree
    rename = Path.rename

    def copy(source, destination, *args, **kwargs):
        if Path(source) == admin:
            if failure == "copy-error":
                raise OSError("simulated copy failure")
            result = copytree(source, destination, *args, **kwargs)
            if failure == "corrupt-copy":
                (Path(destination) / "HEAD").write_text("corruption")
            elif failure == "source-change":
                (admin / "new-evidence").write_text("keep")
            return result
        return copytree(source, destination, *args, **kwargs)

    def move(self, destination):
        if failure == "swap-error" and self.name == "replica":
            raise OSError("simulated swap failure")
        return rename(self, destination)

    monkeypatch.setattr(abandonment.shutil, "copytree", copy)
    monkeypatch.setattr(Path, "rename", move)
    with pytest.raises(abandonment.WorktreeAbandonmentError) as caught:
        abandonment.detach_registered_worktree(
            repo, target, reason="released", receipt_root=tmp_path / "receipts", owner_probe=lambda _: None
        )
    assert target.exists()
    assert admin.stat().st_ino == before
    assert _git(target, "rev-parse", "HEAD") == _git(repo, "rev-parse", "HEAD")
    assert "admin_preservation" in caught.value.receipt["result"]


@pytest.mark.parametrize("changed", [False, True])
def test_recover_interrupted_admin_rename_requires_exact_original(tmp_path: Path, monkeypatch, changed: bool) -> None:
    repo, target = _repo_with_worktree(tmp_path)
    admin = Path(_git(target, "rev-parse", "--absolute-git-dir"))
    before = admin.stat().st_ino
    receipts = tmp_path / "receipts"
    rename = Path.rename

    def interrupted(self, destination):
        result = rename(self, destination)
        if self == admin:
            raise SystemExit("simulated hard interruption after original rename")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(Path, "rename", interrupted)
        with pytest.raises(SystemExit):
            abandonment.detach_registered_worktree(
                repo, target, reason="released", receipt_root=receipts, owner_probe=lambda _: None
            )
    assert target.exists()
    assert not admin.exists()
    receipt = json.loads(next(receipts.glob("*.json")).read_text())
    original = Path(receipt["result"]["admin_preservation"]["retained_original"])
    assert original.stat().st_ino == before
    if changed:
        (original / "new-private-evidence").write_text("retain this change")
        with pytest.raises(RuntimeError, match="recovery-evidence-mismatch"):
            abandonment.recover_worktree_registration(
                repo.resolve(), target.resolve(), receipts, owner_probe=lambda _: None
            )
        assert original.exists()
        assert not admin.exists()
    else:
        with pytest.raises(RuntimeError, match="owner-active-or-unavailable"):
            abandonment.recover_worktree_registration(
                repo.resolve(), target.resolve(), receipts, owner_probe=lambda _: 1234
            )
        assert original.exists()
        abandonment.recover_worktree_registration(
            repo.resolve(), target.resolve(), receipts, owner_probe=lambda _: None
        )
        assert admin.stat().st_ino == before
        assert _git(target, "rev-parse", "HEAD") == _git(repo, "rev-parse", "HEAD")
        result = abandonment.detach_registered_worktree(
            repo, target, reason="released", receipt_root=receipts, owner_probe=lambda _: None
        )
        assert result["state"] == "completed"


def test_detach_rechecks_ignored_payload_created_during_preservation(tmp_path: Path, monkeypatch) -> None:
    repo, target = _repo_with_worktree(tmp_path)
    (repo / ".git/info/exclude").write_text("private-late\n")
    preserve = abandonment._preserve_worktree_admin

    def changed(*args, **kwargs):
        result = preserve(*args, **kwargs)
        (target / "private-late").write_text("late payload")
        return result

    monkeypatch.setattr(abandonment, "_preserve_worktree_admin", changed)
    with pytest.raises(abandonment.WorktreeAbandonmentError, match="ignored-payload-custody-unproven"):
        abandonment.detach_registered_worktree(
            repo, target, reason="released", receipt_root=tmp_path / "receipts", owner_probe=lambda _: None
        )
    assert (target / "private-late").read_text() == "late payload"
    assert _git(target, "rev-parse", "HEAD") == _git(repo, "rev-parse", "HEAD")


@pytest.mark.parametrize("flag", ["--skip-worktree", "--assume-unchanged"])
def test_detach_retains_hidden_tracked_edits(tmp_path: Path, flag: str) -> None:
    repo, target = _repo_with_worktree(tmp_path)
    _git(target, "update-index", flag, "tracked.txt")
    (target / "tracked.txt").write_text("hidden private edit")
    with pytest.raises(abandonment.WorktreeAbandonmentError, match="hidden-modifications"):
        abandonment.detach_registered_worktree(
            repo, target, reason="released", receipt_root=tmp_path / "receipts", owner_probe=lambda _: None
        )
    assert (target / "tracked.txt").read_text() == "hidden private edit"


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


def test_detach_preserves_ignored_payload_without_restoration_proof(tmp_path: Path) -> None:
    repo, target = _repo_with_worktree(tmp_path)
    (repo / ".git/info/exclude").write_text("private-payload\n")
    payload = target / "private-payload"
    payload.write_bytes(b"unfinished ignored content")
    with pytest.raises(abandonment.WorktreeAbandonmentError, match="ignored-payload-custody-unproven"):
        abandonment.detach_registered_worktree(
            repo, target, reason="released", receipt_root=tmp_path / "receipts", owner_probe=lambda _: None
        )
    assert payload.read_bytes() == b"unfinished ignored content"


def test_detach_retains_gitlink_without_submodule_custody(tmp_path: Path) -> None:
    repo, target = _repo_with_worktree(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{head},nested")
    _git(repo, "commit", "-qm", "record gitlink")
    _git(target, "merge", "--ff-only", "main")
    (target / "nested").mkdir(exist_ok=True)
    (target / "nested" / "private.txt").write_text("unique nested payload")
    with pytest.raises(abandonment.WorktreeAbandonmentError, match="submodule-custody-unproven"):
        abandonment.detach_registered_worktree(
            repo, target, reason="released", receipt_root=tmp_path / "receipts", owner_probe=lambda _: None
        )
    assert target.exists()
    assert (target / "nested" / "private.txt").read_text() == "unique nested payload"


def test_detach_allows_empty_gitlink_and_preserves_parent_ref(tmp_path: Path) -> None:
    repo, target = _repo_with_worktree(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{head},nested")
    _git(repo, "commit", "-qm", "record gitlink")
    _git(target, "merge", "--ff-only", "main")
    nested = target / "nested"
    nested.mkdir(exist_ok=True)
    expected = _git(target, "rev-parse", "HEAD")
    result = abandonment.detach_registered_worktree(
        repo, target, reason="released", receipt_root=tmp_path / "receipts", owner_probe=lambda _: None
    )
    assert result["state"] == "completed"
    assert not target.exists()
    assert _git(repo, "rev-parse", "refs/heads/work/test") == expected


def test_absent_gitlink_still_requires_clean_worktree(tmp_path: Path) -> None:
    repo, target = _repo_with_worktree(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{head},nested")
    _git(repo, "commit", "-qm", "record gitlink")
    _git(target, "merge", "--ff-only", "main")
    (target / "nested").rmdir()
    with pytest.raises(abandonment.WorktreeAbandonmentError, match="worktree-not-clean"):
        abandonment.detach_registered_worktree(
            repo, target, reason="released", receipt_root=tmp_path / "receipts", owner_probe=lambda _: None
        )
    assert target.exists()


def test_nested_gitlink_probe_rejects_symlinked_parent(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "checkout"
    target.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "nested").mkdir()
    (target / "alias").symlink_to(elsewhere, target_is_directory=True)
    monkeypatch.setattr(
        abandonment,
        "_run_git",
        lambda *_args: subprocess.CompletedProcess([], 0, f"160000 {'a' * 40} 0\talias/nested\x00", ""),
    )
    assert abandonment._nested_payload_custody_reason(target) == "submodule-custody-unproven"


def test_detach_retains_lfs_pointer_without_object_custody(tmp_path: Path, monkeypatch) -> None:
    repo, target = _repo_with_worktree(tmp_path)
    original = abandonment._run_git

    def reported_lfs(path: Path, *args: str, **kwargs):
        if args == ("lfs", "ls-files", "--name-only"):
            return subprocess.CompletedProcess([], 0, "large.bin\n", "")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(abandonment, "_run_git", reported_lfs)
    with pytest.raises(abandonment.WorktreeAbandonmentError, match="lfs-custody-unproven"):
        abandonment.detach_registered_worktree(
            repo, target, reason="released", receipt_root=tmp_path / "receipts", owner_probe=lambda _: None
        )
    assert target.exists()


def test_registered_worktree_scan_retains_missing_registration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = tmp_path / "missing-linked-root"
    monkeypatch.setattr(
        abandonment,
        "_run_git",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["git", "worktree", "list"],
            0,
            f"worktree {missing}\n",
            "",
        ),
    )

    assert abandonment._registered_worktree_paths(tmp_path) == (missing,)


def test_registered_worktree_scan_fails_closed_on_resolution_error(tmp_path, monkeypatch):
    monkeypatch.setattr(
        abandonment,
        "_run_git",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 0, f"worktree {tmp_path}\n", ""),
    )

    def unavailable(self, **kwargs):
        raise OSError("unavailable")

    monkeypatch.setattr(Path, "resolve", unavailable)
    with pytest.raises(RuntimeError, match="registered-worktree-path-unavailable"):
        abandonment._registered_worktree_paths(tmp_path)


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


def test_custody_purge_requires_exact_identity_and_removes_only_isolated_tree(tmp_path: Path) -> None:
    source = tmp_path / "creation-root" / "candidate"
    source.mkdir(parents=True)
    (source / "tracked.txt").write_text("restored elsewhere\n", encoding="utf-8")
    symlink_target = tmp_path / "outside.txt"
    symlink_target.write_text("do not follow\n", encoding="utf-8")
    (source / "link").symlink_to(symlink_target)
    raw = source.stat()
    resolved = source.resolve()
    identity = abandonment.CustodyPathIdentity(
        path=str(resolved),
        path_sha256=hashlib.sha256(str(resolved).encode()).hexdigest(),
        device=raw.st_dev,
        inode=raw.st_ino,
        mtime_ns=raw.st_mtime_ns,
    )

    result = abandonment.purge_custody_proven_path(
        source,
        identity,
        reason="custody-restored+idle",
        custody_plan_sha256="a" * 64,
        custody_content_sha256="b" * 64,
        receipt_root=tmp_path / "receipts",
        owner_probe=lambda _path: None,
    )

    assert result["state"] == "completed"
    assert result["result"]["purged"] is True
    assert not source.exists()
    assert symlink_target.read_text(encoding="utf-8") == "do not follow\n"


def test_custody_purge_identity_or_owner_drift_preserves_source(tmp_path: Path) -> None:
    source = tmp_path / "candidate"
    source.mkdir()
    raw = source.stat()
    resolved = source.resolve()
    wrong = abandonment.CustodyPathIdentity(
        path=str(resolved),
        path_sha256="0" * 64,
        device=raw.st_dev,
        inode=raw.st_ino,
        mtime_ns=raw.st_mtime_ns,
    )

    with pytest.raises(abandonment.WorktreeAbandonmentError, match="identity"):
        abandonment.purge_custody_proven_path(
            source,
            wrong,
            reason="custody-restored+idle",
            custody_plan_sha256="a" * 64,
            custody_content_sha256="b" * 64,
            receipt_root=tmp_path / "receipts",
            owner_probe=lambda _path: None,
        )
    assert source.exists()

    exact = abandonment.CustodyPathIdentity(
        path=str(resolved),
        path_sha256=hashlib.sha256(str(resolved).encode()).hexdigest(),
        device=raw.st_dev,
        inode=raw.st_ino,
        mtime_ns=raw.st_mtime_ns,
    )
    with pytest.raises(abandonment.WorktreeAbandonmentError, match="active-process"):
        abandonment.purge_custody_proven_path(
            source,
            exact,
            reason="custody-restored+idle",
            custody_plan_sha256="a" * 64,
            custody_content_sha256="b" * 64,
            receipt_root=tmp_path / "receipts",
            owner_probe=lambda _path: 4242,
        )
    assert source.exists()


def test_remote_purge_requires_exact_remote_head_proof(tmp_path: Path) -> None:
    source = tmp_path / "remote-clone"
    source.mkdir()
    (source / "tracked.txt").write_text("remote copy\n", encoding="utf-8")
    raw = source.stat()
    resolved = source.resolve()
    identity = abandonment.CustodyPathIdentity(
        path=str(resolved),
        path_sha256=hashlib.sha256(str(resolved).encode()).hexdigest(),
        device=raw.st_dev,
        inode=raw.st_ino,
        mtime_ns=raw.st_mtime_ns,
    )

    result = abandonment.purge_remote_proven_path(
        source,
        identity,
        reason="clean+pushed+idle",
        head="a" * 40,
        remote_refs=("refs/heads/work/example",),
        local_ref_proof=(
            {
                "local_ref": "refs/heads/work/example",
                "object": "a" * 40,
                "peeled_object": None,
                "remote_refs": ["refs/heads/work/example"],
            },
        ),
        receipt_root=tmp_path / "receipts",
        owner_probe=lambda _path: None,
        content_probe=lambda _path: None,
    )

    assert result["result"]["proof"]["kind"] == "remote-all-local-refs"
    assert result["result"]["purged"] is True
    assert not source.exists()


@pytest.mark.parametrize("remote_ref", ["refs/remotes/origin/main", "refs/heads/main\n", "refs/heads/"])
def test_remote_purge_rejects_tracking_or_malformed_refs(tmp_path, remote_ref):
    source = tmp_path / "preserved"
    source.mkdir()
    raw = source.stat()
    identity = abandonment.CustodyPathIdentity(
        path=str(source),
        path_sha256=hashlib.sha256(str(source).encode()).hexdigest(),
        device=raw.st_dev,
        inode=raw.st_ino,
        mtime_ns=raw.st_mtime_ns,
    )
    with pytest.raises(ValueError, match="remote-purge-refs-invalid"):
        abandonment.purge_remote_proven_path(
            source,
            identity,
            reason="clean+pushed+idle",
            head="a" * 40,
            remote_refs=(remote_ref,),
            local_ref_proof=(),
            receipt_root=tmp_path / "receipts",
        )
    assert source.exists()


def test_custody_purge_rehashes_after_root_prepare_before_isolation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "candidate"
    source.mkdir()
    document = source / "document.txt"
    document.write_text("preserved\n", encoding="utf-8")
    raw = source.stat()
    resolved = source.resolve()
    identity = abandonment.CustodyPathIdentity(
        path=str(resolved),
        path_sha256=hashlib.sha256(str(resolved).encode()).hexdigest(),
        device=raw.st_dev,
        inode=raw.st_ino,
        mtime_ns=raw.st_mtime_ns,
    )
    probe_calls = 0

    def exact_content_probe(_path: Path) -> None:
        nonlocal probe_calls
        probe_calls += 1
        if document.read_text(encoding="utf-8") != "preserved\n":
            raise RuntimeError("content-changed")

    def mutate_during_prepare(_path: Path) -> None:
        document.write_text("changed\n", encoding="utf-8")

    with pytest.raises(
        abandonment.WorktreeAbandonmentError,
        match="content-changed",
    ):
        abandonment.purge_custody_proven_path(
            source,
            identity,
            reason="custody-restored+idle",
            custody_plan_sha256="a" * 64,
            custody_content_sha256="b" * 64,
            receipt_root=tmp_path / "receipts",
            owner_probe=lambda _path: None,
            root_prepare=mutate_during_prepare,
            content_probe=exact_content_probe,
        )

    assert probe_calls == 3
    assert source.is_dir()
    assert document.read_text(encoding="utf-8") == "changed\n"


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


def test_remote_purge_requires_fresh_content_revalidation(tmp_path):
    source = tmp_path / "retained"
    source.mkdir()
    raw = source.stat()
    identity = abandonment.CustodyPathIdentity(
        path=str(source),
        path_sha256=hashlib.sha256(str(source).encode()).hexdigest(),
        device=raw.st_dev,
        inode=raw.st_ino,
        mtime_ns=raw.st_mtime_ns,
    )
    with pytest.raises(ValueError, match="remote-purge-fresh-content-probe-required"):
        abandonment.purge_remote_proven_path(
            source,
            identity,
            reason="clean+pushed+idle",
            head="a" * 40,
            remote_refs=("refs/heads/main",),
            local_ref_proof=({"local_ref": "refs/heads/main", "object": "a" * 40, "remote_refs": ["refs/heads/main"]},),
            receipt_root=tmp_path / "receipts",
        )
    assert source.exists()
