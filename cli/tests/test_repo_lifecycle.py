from __future__ import annotations

import json
import subprocess
from pathlib import Path

from limen import repo_lifecycle as lifecycle
from limen.worktree_initialization import WorktreeInitialization


def _run(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def _source_repo(root: Path) -> Path:
    _run("git", "init", "--bare", str(root / "remote.git"))
    work = root / "seed"
    work.mkdir()
    _run("git", "init", str(work))
    _run("git", "-C", str(work), "config", "user.email", "test@example.invalid")
    _run("git", "-C", str(work), "config", "user.name", "Test")
    (work / "README.md").write_text("seed\n")
    _run("git", "-C", str(work), "add", "README.md")
    _run("git", "-C", str(work), "commit", "-m", "seed")
    _run("git", "-C", str(work), "branch", "-M", "main")
    _run("git", "-C", str(work), "remote", "add", "origin", str(root / "remote.git"))
    _run("git", "-C", str(work), "push", "-u", "origin", "main")
    _run("git", "--git-dir", str(root / "remote.git"), "symbolic-ref", "HEAD", "refs/heads/main")
    return root / "remote.git"


def test_ensure_is_idempotent_for_session_and_release_retains_checkout(tmp_path, monkeypatch):
    remote = _source_repo(tmp_path)
    cache = tmp_path / "cache"
    worktrees = tmp_path / "worktrees"
    monkeypatch.setattr(lifecycle, "_repository", lambda _repo_id: (77123, "owner/project"))
    monkeypatch.setattr(lifecycle, "_verify_store_origin", lambda _store, _stable_id: None)
    monkeypatch.setattr(lifecycle, "dispatch_clone_cache_root", lambda: cache)
    from limen import dispatch

    monkeypatch.setattr(dispatch, "_github_repositories_match", lambda _left, _right: True)
    monkeypatch.setattr(dispatch, "_github_slug_from_remote", lambda _remote: "owner/project")
    real_capture = dispatch._run_capture

    def fake_capture(args, **kwargs):
        if args[:3] == ["gh", "repo", "clone"]:
            return subprocess.run(
                ["git", "clone", "--bare", str(remote), args[4]],
                capture_output=True,
                text=True,
                timeout=kwargs.get("timeout"),
                check=False,
            )
        return real_capture(args, **kwargs)

    monkeypatch.setattr(dispatch, "_run_capture", fake_capture)
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(worktrees))

    def initialize(store, final_path, *, branch, checkout_ref, task_id):
        _run("git", "-C", str(store), "worktree", "add", "-b", branch, str(final_path), checkout_ref)
        return WorktreeInitialization(
            final_path,
            final_path,
            branch,
            checkout_ref,
            _run("git", "-C", str(final_path), "rev-parse", "HEAD"),
            final_path / "receipt.json",
            {},
        )

    monkeypatch.setattr(lifecycle, "initialize_worktree", initialize)
    first = lifecycle.ensure("77123", "main", "session/one")
    second = lifecycle.ensure(77123, "main", "session/one")
    concurrent_session = lifecycle.ensure(77123, "main", "session/two")
    default_head = lifecycle.ensure(77123, "HEAD", "session/head")
    assert first == second
    assert concurrent_session["lease_id"] != first["lease_id"]
    assert concurrent_session["worktree"] != first["worktree"]
    assert Path(first["worktree"]).resolve() != Path(concurrent_session["worktree"]).resolve()
    assert Path(first["worktree"]).is_dir()
    assert default_head["head"] == first["head"]
    clean_release = lifecycle.release(first["lease_id"])
    assert clean_release["state"] == "released-awaiting-custody-investigation"
    first_lease = cache / ".limen-residency" / "77123" / "leases" / f"{first['lease_id']}.json"
    assert json.loads(first_lease.read_text())["released_head"] == first["head"]
    assert lifecycle.release(first["lease_id"]) == clean_release
    assert Path(first["worktree"]).is_dir()
    assert Path(concurrent_session["worktree"]).is_dir()
    assert lifecycle.reconcile(77123, owner_probe=lambda _path: None)["state"] == "retained-active-lease"

    dirty = Path(concurrent_session["worktree"]) / "local.txt"
    dirty.write_text("unpreserved payload\n")
    dirty_release = lifecycle.release(concurrent_session["lease_id"])
    assert dirty_release["state"] == "retained-dirty-or-unavailable"
    assert dirty.exists()
    lease = cache / ".limen-residency" / "77123" / "leases" / f"{concurrent_session['lease_id']}.json"
    assert json.loads(lease.read_text())["state"] == "retained-dirty-or-unavailable"
    assert lifecycle.release(default_head["lease_id"])["state"] == "released-awaiting-custody-investigation"
    reconciled = lifecycle.reconcile(77123, owner_probe=lambda _path: None)
    assert reconciled["retired_checkouts"] == "2"
    assert reconciled["state"] == "store-retained"
    assert not Path(first["worktree"]).exists()
    assert not Path(default_head["worktree"]).exists()
    assert Path(concurrent_session["worktree"]).is_dir()
    assert Path(first["store"]).is_dir()
    assert lifecycle.reconcile(77123, owner_probe=lambda _path: None)["state"] == "retained-no-eligible-checkout"


def test_ensure_rejects_non_immutable_repository_identifiers():
    try:
        lifecycle._repository("owner/project")
    except lifecycle.RepositoryLifecycleError as exc:
        assert "immutable positive GitHub" in str(exc)
    else:
        raise AssertionError("coordinate accepted in place of immutable repository ID")


def test_store_origin_requires_live_immutable_identity(tmp_path, monkeypatch):
    from limen import dispatch

    monkeypatch.setattr(lifecycle, "_git", lambda _store, *_args: "https://github.com/old/name.git")
    monkeypatch.setattr(dispatch, "_github_slug_from_remote", lambda _remote: "old/name")
    monkeypatch.setattr(lifecycle, "_gh", lambda *_args: '{"id": 77124}')
    try:
        lifecycle._verify_store_origin(tmp_path, 77123)
    except lifecycle.RepositoryLifecycleError as exc:
        assert "immutable identity mismatch" in str(exc)
    else:
        raise AssertionError("mismatched store origin accepted")
    monkeypatch.setattr(lifecycle, "_gh", lambda *_args: '{"id": 77123}')
    lifecycle._verify_store_origin(tmp_path, 77123)


def test_reconcile_retains_unknown_lease_state(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    (cache / "github-77123").mkdir(parents=True)
    leases = cache / ".limen-residency" / "77123" / "leases"
    leases.mkdir(parents=True)
    (leases / "77123-deadbeef.json").write_text(
        json.dumps({"repository_id": 77123, "lease_id": "77123-deadbeef", "state": "unexpected"})
    )
    monkeypatch.setattr(lifecycle, "_repository", lambda _repo_id: (77123, "owner/project"))
    monkeypatch.setattr(lifecycle, "dispatch_clone_cache_root", lambda: cache)
    monkeypatch.setattr(lifecycle, "_verify_store_origin", lambda _store, _stable_id: None)
    assert lifecycle.reconcile(77123)["state"] == "retained-inconsistent-lease"

    def offline(_store, _stable_id):
        raise lifecycle.RepositoryLifecycleError("offline")

    monkeypatch.setattr(lifecycle, "_verify_store_origin", offline)
    assert lifecycle.reconcile(77123)["state"] == "retained-origin-identity-unavailable"
