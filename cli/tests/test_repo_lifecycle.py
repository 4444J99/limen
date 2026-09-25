from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
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


def test_final_released_store_explicitly_retained_without_metadata_custody(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    store = cache / "github-77123"
    store.mkdir(parents=True)
    leases = cache / ".limen-residency" / "77123" / "leases"
    leases.mkdir(parents=True)
    lease_id = "77123-" + "a" * 32
    (leases / f"{lease_id}.json").write_text(
        json.dumps(
            {
                "repository_id": 77123,
                "lease_id": lease_id,
                "state": "retired-checkout-store-retained",
                "store": str(store),
            }
        )
    )
    monkeypatch.setattr(lifecycle, "_repository", lambda _repo_id: (77123, "owner/project"))
    monkeypatch.setattr(lifecycle, "_verify_store_origin", lambda _store, _id: None)
    monkeypatch.setattr(lifecycle, "dispatch_clone_cache_root", lambda: cache)
    result = lifecycle.reconcile(77123)
    assert result["state"] == "retained-store-metadata-custody-unproven"
    assert store.is_dir()


def test_ensure_is_idempotent_for_session_and_release_retains_checkout(tmp_path, monkeypatch):
    remote = _source_repo(tmp_path)
    cache = tmp_path / "cache"
    worktrees = tmp_path / "worktrees"
    monkeypatch.setattr(lifecycle, "_repository", lambda _repo_id: (77123, "owner/project"))
    monkeypatch.setattr(lifecycle, "_verify_store_origin", lambda _store, _stable_id: None)
    monkeypatch.setattr(lifecycle, "dispatch_clone_cache_root", lambda: cache)
    admitted = {
        "active": True,
        "block_new_local": False,
        "room_gib": 1.0,
        "free_gib": 51.0,
        "floor_gib": 50.0,
        "reserved_gib": 0.0,
    }
    monkeypatch.setattr(lifecycle, "take_admission_snapshot", lambda _root: admitted.copy())
    from limen import dispatch

    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setattr(dispatch, "_remote_hydration_requirement_for_repo_gib", lambda _repo, **_kwargs: 0.001)
    monkeypatch.setattr(dispatch, "_github_repositories_match", lambda _left, _right: True)
    monkeypatch.setattr(dispatch, "_github_slug_from_remote", lambda _remote: "owner/project")
    real_capture = dispatch._run_capture

    def fake_capture(args, **kwargs):
        if args[:3] == ["gh", "repo", "clone"]:
            assert args[5:] == ["--no-upstream", "--", "--bare"]
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
    monkeypatch.setattr(
        lifecycle,
        "take_admission_snapshot",
        lambda _root: {"active": True, "block_new_local": True, "reason": "free space below floor"},
    )
    assert lifecycle.ensure(77123, "main", "session/one") == first
    monkeypatch.setattr(lifecycle, "take_admission_snapshot", lambda _root: admitted.copy())
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
    active_lease = cache / ".limen-residency" / "77123" / "leases" / f"{concurrent_session['lease_id']}.json"
    active_bytes = active_lease.read_bytes()
    atomic_json = lifecycle._atomic_json

    def checkpoint_interrupted(path, record):
        if path == first_lease and record.get("state") == "retired-checkout-store-retained":
            raise OSError("simulated lease checkpoint interruption")
        atomic_json(path, record)

    with monkeypatch.context() as patch:
        patch.setattr(lifecycle, "_atomic_json", checkpoint_interrupted)
        with pytest.raises(OSError, match="checkpoint interruption"):
            lifecycle.reconcile(77123, owner_probe=lambda _path: None)
    assert not Path(first["worktree"]).exists()
    assert json.loads(first_lease.read_text())["state"] == "released-awaiting-custody-investigation"
    isolated = lifecycle.reconcile(77123, owner_probe=lambda _path: None)
    assert isolated["state"] == "retained-active-lease"
    assert isolated["retired_checkouts"] == "0"
    assert isolated["recovered_checkouts"] == "1"
    assert isolated["active_checkouts"] == "2"
    assert not Path(first["worktree"]).exists()
    assert active_lease.read_bytes() == active_bytes
    assert _run("git", "-C", concurrent_session["worktree"], "rev-parse", "HEAD") == concurrent_session["head"]
    assert Path(default_head["worktree"]).is_dir()
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
    assert reconciled["retired_checkouts"] == "1"
    assert reconciled["state"] == "store-retained"
    assert not Path(first["worktree"]).exists()
    assert not Path(default_head["worktree"]).exists()
    assert Path(concurrent_session["worktree"]).is_dir()
    assert Path(first["store"]).is_dir()
    still_dirty = lifecycle.reconcile(77123, owner_probe=lambda _path: None)
    assert still_dirty["state"] == "store-retained"
    assert still_dirty["retained_checkouts"] == "1"
    assert dirty.exists()
    # After its owner preserves the payload and cleans the checkout, the same
    # released lease can pass fresh remote/HEAD/process/payload review.
    preserved = tmp_path / "owner-preserved-payload"
    preserved.write_bytes(dirty.read_bytes())
    assert preserved.read_bytes() == dirty.read_bytes()
    dirty.unlink()
    clean_later = lifecycle.reconcile(77123, owner_probe=lambda _path: None)
    assert clean_later["retired_checkouts"] == "1"
    assert clean_later["state"] == "retained-store-metadata-custody-unproven"
    assert not Path(concurrent_session["worktree"]).exists()
    assert Path(first["store"]).is_dir()


def test_concurrent_ensure_shares_one_store_and_one_session_checkout(tmp_path, monkeypatch):
    remote = _source_repo(tmp_path)
    cache = tmp_path / "cache"
    worktrees = tmp_path / "worktrees"
    monkeypatch.setattr(lifecycle, "_repository", lambda _repo_id: (77123, "owner/project"))
    monkeypatch.setattr(lifecycle, "_verify_store_origin", lambda _store, _stable_id: None)
    monkeypatch.setattr(lifecycle, "dispatch_clone_cache_root", lambda: cache)
    monkeypatch.setattr(
        lifecycle,
        "take_admission_snapshot",
        lambda _root: {
            "active": True,
            "block_new_local": False,
            "room_gib": 1.0,
            "free_gib": 51.0,
            "floor_gib": 50.0,
            "reserved_gib": 0.0,
        },
    )
    from limen import dispatch

    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setattr(dispatch, "_remote_hydration_requirement_for_repo_gib", lambda _repo, **_kwargs: 0.001)
    real_capture = dispatch._run_capture
    clone_calls = 0
    clone_calls_lock = threading.Lock()

    def fake_capture(args, **kwargs):
        nonlocal clone_calls
        if args[:3] == ["gh", "repo", "clone"]:
            with clone_calls_lock:
                clone_calls += 1
            # Make the clone transaction long enough that the second caller
            # would race the same store if acquisition serialization regressed.
            time.sleep(0.05)
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
    barrier = threading.Barrier(2)

    def acquire(session_id):
        barrier.wait(timeout=5)
        return lifecycle.ensure(77123, "main", session_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(acquire, ("concurrent/session-one", "concurrent/session-two")))

    assert first["store"] == second["store"]
    assert first["worktree"] != second["worktree"]
    assert clone_calls == 1
    assert Path(first["store"]).is_dir()
    assert Path(first["worktree"]).is_dir()
    assert Path(second["worktree"]).is_dir()
    assert lifecycle.ensure(77123, "main", "concurrent/session-one") == first
    assert len(list((cache / ".limen-residency" / "77123" / "leases").glob("*.json"))) == 2
    worktree_paths = _run("git", "-C", first["store"], "worktree", "list", "--porcelain").splitlines()
    assert sum(line.startswith("worktree ") for line in worktree_paths) == 3


def test_new_residency_denied_before_clone_under_disk_pressure(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setattr(lifecycle, "_repository", lambda _repo_id: (77123, "owner/project"))
    monkeypatch.setattr(lifecycle, "dispatch_clone_cache_root", lambda: cache)
    monkeypatch.setattr(
        lifecycle,
        "take_admission_snapshot",
        lambda _root: {"active": True, "block_new_local": True, "reason": "free space below floor"},
    )
    with pytest.raises(lifecycle.RepositoryLifecycleError, match="free space below floor"):
        lifecycle.ensure(77123, "main", "new-session")
    assert not (cache / "github-77123").exists()
    assert not list((cache / ".limen-residency" / "77123" / "leases").glob("*.json"))


def test_direct_acquisition_reserves_room_across_sessions(tmp_path, monkeypatch):
    from limen import dispatch

    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setattr(
        lifecycle,
        "take_admission_snapshot",
        lambda _root: {
            "active": True,
            "block_new_local": False,
            "room_gib": 0.6,
            "free_gib": 50.6,
            "floor_gib": 50.0,
            "reserved_gib": 0.0,
        },
    )
    seen_revisions = []

    def estimate(_task, *, tree_ref):
        seen_revisions.append(tree_ref)
        return 0.5

    monkeypatch.setattr(dispatch, "_remote_hydration_requirement_for_repo_gib", estimate)
    with lifecycle._capacity_admission(77123, "owner/project", "feature/ref", "one", None):
        first = dispatch._admission_lease_path(f"repo.ensure:77123:{lifecycle._digest('one')}")
        assert json.loads(first.read_text())["reserved_gib"] == 0.5
        with (
            pytest.raises(lifecycle.RepositoryLifecycleError, match="only 0.100 GiB remains"),
            lifecycle._capacity_admission(77123, "owner/project", "feature/ref", "two", None),
        ):
            pass
    assert seen_revisions == ["feature/ref", "feature/ref"]
    assert not first.exists()


def test_dispatch_handoff_requires_live_selected_lease(tmp_path, monkeypatch):
    from limen import dispatch

    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setattr(lifecycle, "take_admission_snapshot", lambda _root: {"active": True, "block_new_local": False})
    path = dispatch._admission_lease_path("task-1")
    with (
        pytest.raises(lifecycle.RepositoryLifecycleError, match="unavailable"),
        lifecycle._capacity_admission(77123, "owner/project", "main", "session", "task-1"),
    ):
        pass
    lifecycle._atomic_json(
        path,
        {
            "schema": "limen.dispatch_admission_lease.v1",
            "pid": os.getpid(),
            "task_id": "task-1",
            "phase": "selected",
            "reserved_gib": 0.5,
        },
    )
    with lifecycle._capacity_admission(77123, "owner/project", "main", "session", "task-1"):
        assert path.exists()
    assert path.exists()  # Dispatch still owns this reservation.
    monkeypatch.setattr(
        lifecycle,
        "take_admission_snapshot",
        lambda _root: {"active": True, "block_new_local": True, "reason": "live disk floor crossed"},
    )
    with (
        pytest.raises(lifecycle.RepositoryLifecycleError, match="live disk floor crossed"),
        lifecycle._capacity_admission(77123, "owner/project", "main", "session", "task-1"),
    ):
        pass


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


@pytest.mark.parametrize("payload", [[], None, "invalid", {"state": []}])
def test_reconcile_retains_malformed_lease_without_mutation(tmp_path, monkeypatch, payload):
    cache = tmp_path / "cache"
    store = cache / "github-77123"
    store.mkdir(parents=True)
    leases = cache / ".limen-residency" / "77123" / "leases"
    leases.mkdir(parents=True)
    lease_id = "77123-" + "b" * 32
    if isinstance(payload, dict):
        payload.update(repository_id=77123, lease_id=lease_id)
    path = leases / f"{lease_id}.json"
    path.write_text(json.dumps(payload))
    before = path.read_bytes()
    monkeypatch.setattr(lifecycle, "_repository", lambda _: (77123, "owner/project"))
    monkeypatch.setattr(lifecycle, "dispatch_clone_cache_root", lambda: cache)
    monkeypatch.setattr(lifecycle, "_verify_store_origin", lambda *_: None)
    assert lifecycle.reconcile(77123)["state"] == "retained-inconsistent-lease"
    assert path.read_bytes() == before
    assert store.exists()


def test_reconcile_pending_round_robins_and_skips_symlink(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    registry = cache / ".limen-residency"
    (registry / "10").mkdir(parents=True)
    (registry / "20").mkdir()
    (registry / "30").symlink_to(registry / "20", target_is_directory=True)
    monkeypatch.setattr(lifecycle, "dispatch_clone_cache_root", lambda: cache)
    seen = []

    def fake_reconcile(repository_id):
        seen.append(repository_id)
        return {"repository_id": str(repository_id), "state": "retained-test"}

    monkeypatch.setattr(lifecycle, "reconcile", fake_reconcile)
    assert lifecycle.reconcile_pending()["state"] == "reconciled-bounded"
    lifecycle.reconcile_pending()
    lifecycle.reconcile_pending()
    assert seen == [10, 20, 10]
    cursor = json.loads((registry / "reconcile-cursor.json").read_text())
    assert cursor["last_repository_id"] == 10


def test_reconcile_pending_retains_error_and_advances_cursor(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    registry = cache / ".limen-residency"
    (registry / "10").mkdir(parents=True)
    (registry / "20").mkdir()
    monkeypatch.setattr(lifecycle, "dispatch_clone_cache_root", lambda: cache)

    def unavailable(_repository_id):
        raise lifecycle.RepositoryLifecycleError("remote offline")

    monkeypatch.setattr(lifecycle, "reconcile", unavailable)
    first = lifecycle.reconcile_pending()["results"][0]
    assert first == {"repository_id": "10", "state": "retained-investigation-error"}
    assert lifecycle.reconcile_pending()["results"][0]["repository_id"] == "20"
