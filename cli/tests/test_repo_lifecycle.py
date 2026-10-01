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
    return root / "remote.git"


def test_ensure_is_idempotent_for_session_and_release_retains_checkout(tmp_path, monkeypatch):
    remote = _source_repo(tmp_path)
    cache = tmp_path / "cache"
    worktrees = tmp_path / "worktrees"
    monkeypatch.setattr(lifecycle, "_repository", lambda _repo_id: (77123, "owner/project"))
    monkeypatch.setattr(lifecycle, "dispatch_clone_cache_root", lambda: cache)
    from limen import dispatch

    monkeypatch.setattr(dispatch, "_github_repositories_match", lambda _left, _right: True)
    monkeypatch.setattr(dispatch, "_github_slug_from_remote", lambda _remote: "owner/project")
    real_run = subprocess.run

    def fake_run(args, **kwargs):
        if args[:3] == ["gh", "repo", "clone"]:
            return real_run(["git", "clone", "--bare", str(remote), args[4]], **kwargs)
        return real_run(args, **kwargs)

    monkeypatch.setattr(lifecycle.subprocess, "run", fake_run)
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
    assert first == second
    assert concurrent_session["lease_id"] != first["lease_id"]
    assert concurrent_session["worktree"] != first["worktree"]
    assert Path(first["worktree"]).resolve() != Path(concurrent_session["worktree"]).resolve()
    assert Path(first["worktree"]).is_dir()
    clean_release = lifecycle.release(first["lease_id"])
    assert clean_release["state"] == "released-awaiting-custody-investigation"
    assert Path(first["worktree"]).is_dir()
    assert Path(concurrent_session["worktree"]).is_dir()

    dirty = Path(first["worktree"]) / "local.txt"
    dirty.write_text("unpreserved payload\n")
    dirty_release = lifecycle.release(first["lease_id"])
    assert dirty_release["state"] == "retained-dirty-or-unavailable"
    assert dirty.exists()
    lease = cache / ".limen-residency" / "77123" / "leases" / f"{first['lease_id']}.json"
    assert json.loads(lease.read_text())["state"] == "retained-dirty-or-unavailable"


def test_ensure_rejects_non_immutable_repository_identifiers():
    try:
        lifecycle._repository("owner/project")
    except lifecycle.RepositoryLifecycleError as exc:
        assert "immutable positive GitHub" in str(exc)
    else:
        raise AssertionError("coordinate accepted in place of immutable repository ID")
