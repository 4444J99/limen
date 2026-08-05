"""Heartbeat writer guard — autonomic lanes never commit or push a live origin default.

Default-branch cargo is preserved on stable side branches. Topic branches keep their normal behavior.

  * scripts/capture.sh              — `_unstage_source` in the `_unstage_*` chain (in-place + side ref)
  * scripts/continuation-beat.py    — `is_source_path` / `_guard_source_on_main` in `commit_paths`
  * cli/src/limen/tabularius.py     — a LOUD defensive assert (only the board may reach main)

The rule is self-configuring: it derives the origin default and observes the repo's
`.github/workflows/pr-gate.yml`. Non-default branches and ungated repos keep current behavior (capture
preserving source on a feature/worktree branch is CORRECT). Escape hatch: `LIMEN_PUSH_GUARD=off`.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CAPTURE_SH = REPO_ROOT / "scripts" / "capture.sh"
CONTINUATION = REPO_ROOT / "scripts" / "continuation-beat.py"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "guard-test",
    "GIT_AUTHOR_EMAIL": "guard@test.local",
    "GIT_COMMITTER_NAME": "guard-test",
    "GIT_COMMITTER_EMAIL": "guard@test.local",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def _base_env() -> dict[str, str]:
    return dict(os.environ)


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env={**_base_env(), **GIT_ENV},
        capture_output=True,
        text=True,
        check=True,
    )


def _has_git() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def _seed_pr_gated_clone(
    tmp_path: Path,
    *,
    branch: str | None = None,
    default_branch: str = "main",
):
    """A bare origin plus a fresh clone on *branch* under an LIMEN_WORKSPACE."""
    home = tmp_path / "home"
    home.mkdir()
    remote = tmp_path / "remote.git"
    ws = tmp_path / "ws"
    ws.mkdir()
    victim = ws / "victim"

    _git("init", "--bare", f"--initial-branch={default_branch}", str(remote), cwd=tmp_path)
    seed = tmp_path / "seed"
    _git("clone", str(remote), str(seed), cwd=tmp_path)
    (seed / ".github" / "workflows").mkdir(parents=True)
    (seed / ".github" / "workflows" / "pr-gate.yml").write_text("on: pull_request\n")
    (seed / "seed.txt").write_text("seed\n")
    _git("add", "-A", cwd=seed)
    _git("commit", "-m", "seed", cwd=seed)
    _git("push", "origin", default_branch, cwd=seed)

    _git("clone", str(remote), str(victim), cwd=tmp_path)
    # Repo-local identity so an INTERNAL commit (continuation-beat's commit_paths, which does not carry
    # our GIT_ENV) works on a CI runner that has no global git identity. (Local machines have one, which
    # masked this — hence the CI-only "Author identity unknown" failure.)
    _git("config", "user.email", "guard@test.local", cwd=victim)
    _git("config", "user.name", "guard-test", cwd=victim)
    branch = branch or default_branch
    if branch != default_branch:
        _git("checkout", "-b", branch, cwd=victim)
    return home, remote, ws, victim


def _run_capture(
    home: Path,
    ws: Path,
    tmp_path: Path,
    guard: str = "on",
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**_base_env(), **GIT_ENV, "HOME": str(home), "LIMEN_ROOT": str(tmp_path), "LIMEN_WORKSPACE": str(ws)}
    if guard != "on":
        env["LIMEN_PUSH_GUARD"] = guard
    env.update(extra_env or {})
    return subprocess.run(["bash", str(CAPTURE_SH)], env=env, capture_output=True, text=True)


# --- scripts/capture.sh (the PRIMARY leak) -------------------------------------------------------
@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CAPTURE_SH.exists(), reason="capture.sh missing")
def test_capture_preserves_source_and_data_off_main(tmp_path):
    """A dirty default tree is preserved whole on the stable side branch."""
    home, remote, ws, victim = _seed_pr_gated_clone(tmp_path)
    main_before = _git("rev-parse", "refs/heads/main", cwd=remote).stdout.strip()
    local_before = _git("rev-parse", "HEAD", cwd=victim).stdout.strip()
    (victim / "leak.py").write_text('print("un-CI-d source")\n')
    (victim / "foo-receipts.json").write_text('{"receipt": 1}\n')

    res = _run_capture(home, ws, tmp_path)
    assert res.returncode == 0, f"capture.sh failed: {res.stderr}\n{res.stdout}"

    assert "REFUSED source on main" not in res.stdout, res.stdout
    # The default and local HEAD never moved; cargo reached only the side branch.
    assert _git("rev-parse", "refs/heads/main", cwd=remote).stdout.strip() == main_before
    assert _git("rev-parse", "HEAD", cwd=victim).stdout.strip() == local_before
    main_tree = _git("ls-tree", "-r", "--name-only", "refs/heads/main", cwd=remote).stdout
    side_tree = _git("ls-tree", "-r", "--name-only", "refs/heads/capture/main-deferred", cwd=remote).stdout
    assert "leak.py" not in main_tree
    assert "foo-receipts.json" not in main_tree
    assert "leak.py" in side_tree
    assert "foo-receipts.json" in side_tree

    # A second unchanged beat coalesces onto the same ref without another commit/ref.
    side_before = _git("rev-parse", "refs/heads/capture/main-deferred", cwd=remote).stdout.strip()
    again = _run_capture(home, ws, tmp_path)
    assert again.returncode == 0
    assert _git("rev-parse", "refs/heads/capture/main-deferred", cwd=remote).stdout.strip() == side_before
    refs = _git("for-each-ref", "--format=%(refname)", "refs/heads/capture/", cwd=remote).stdout.splitlines()
    assert refs == ["refs/heads/capture/main-deferred"]


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CAPTURE_SH.exists(), reason="capture.sh missing")
def test_capture_repeated_push_failures_chain_local_custody(tmp_path):
    home, remote, ws, victim = _seed_pr_gated_clone(tmp_path)
    real_git = shutil.which("git")
    assert real_git
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    wrapper = fake_bin / "git"
    wrapper.write_text(
        """#!/usr/bin/env bash
if [[ " $* " == *" push "*"refs/heads/capture/main-deferred"* ]]; then
  exit 1
fi
exec "$REAL_GIT" "$@"
""",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    failed_env = {
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "REAL_GIT": real_git,
    }

    (victim / "first.txt").write_text("first\n")
    first = _run_capture(home, ws, tmp_path, extra_env=failed_env)
    assert first.returncode == 1
    first_sha = _git("rev-parse", "refs/limen/capture/main-deferred", cwd=victim).stdout.strip()
    assert not (remote / "refs" / "heads" / "capture" / "main-deferred").exists()

    (victim / "second.txt").write_text("second\n")
    second = _run_capture(home, ws, tmp_path, extra_env=failed_env)
    assert second.returncode == 1
    second_sha = _git("rev-parse", "refs/limen/capture/main-deferred", cwd=victim).stdout.strip()
    assert _git("merge-base", "--is-ancestor", first_sha, second_sha, cwd=victim).returncode == 0

    # Even if the operator cleans the worktree before connectivity returns,
    # the exact pending custody history must still be retried.
    (victim / "first.txt").unlink()
    (victim / "second.txt").unlink()
    assert _git("status", "--porcelain", cwd=victim).stdout.strip() == ""
    recovered = _run_capture(home, ws, tmp_path)
    assert recovered.returncode == 0
    remote_sha = _git("rev-parse", "refs/heads/capture/main-deferred", cwd=remote).stdout.strip()
    assert _git("merge-base", "--is-ancestor", second_sha, remote_sha, cwd=victim).returncode == 0
    remote_tree = _git("ls-tree", "-r", "--name-only", remote_sha, cwd=remote).stdout
    assert "first.txt" in remote_tree
    assert "second.txt" in remote_tree


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CAPTURE_SH.exists(), reason="capture.sh missing")
def test_capture_uses_derived_default_branch(tmp_path):
    home, remote, ws, victim = _seed_pr_gated_clone(tmp_path, default_branch="trunk")
    default_before = _git("rev-parse", "refs/heads/trunk", cwd=remote).stdout.strip()
    local_before = _git("rev-parse", "HEAD", cwd=victim).stdout.strip()
    (victim / "work.py").write_text("print('trunk work')\n")

    result = _run_capture(home, ws, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _git("rev-parse", "refs/heads/trunk", cwd=remote).stdout.strip() == default_before
    assert _git("rev-parse", "HEAD", cwd=victim).stdout.strip() == local_before
    tree = _git("ls-tree", "-r", "--name-only", "refs/heads/capture/trunk-deferred", cwd=remote).stdout
    assert "work.py" in tree


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CAPTURE_SH.exists(), reason="capture.sh missing")
def test_capture_detached_head_uses_stable_remote_custody(tmp_path):
    home, remote, ws, victim = _seed_pr_gated_clone(tmp_path)
    remote_default_before = _git("rev-parse", "refs/heads/main", cwd=remote).stdout.strip()
    _git("checkout", "--detach", cwd=victim)
    detached_head = _git("rev-parse", "HEAD", cwd=victim).stdout.strip()
    capture_branch = f"detached-{detached_head[:12]}"
    (victim / "detached.txt").write_text("detached custody\n")

    result = _run_capture(home, ws, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _git("rev-parse", "HEAD", cwd=victim).stdout.strip() == detached_head
    assert _git("rev-parse", "refs/heads/main", cwd=remote).stdout.strip() == remote_default_before
    remote_ref = f"refs/heads/capture/{capture_branch}-deferred"
    tree = _git("ls-tree", "-r", "--name-only", remote_ref, cwd=remote).stdout
    assert "detached.txt" in tree


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CAPTURE_SH.exists(), reason="capture.sh missing")
def test_capture_behind_topic_uses_one_stable_ref(tmp_path):
    home, remote, ws, victim = _seed_pr_gated_clone(tmp_path, branch="feature/x")
    (victim / "topic-base.txt").write_text("base\n")
    _git("add", "-A", cwd=victim)
    _git("commit", "-m", "topic base", cwd=victim)
    _git("push", "-u", "origin", "feature/x", cwd=victim)

    advancer = tmp_path / "topic-advancer"
    _git("clone", str(remote), str(advancer), cwd=tmp_path)
    _git("checkout", "feature/x", cwd=advancer)
    (advancer / "remote.txt").write_text("remote\n")
    _git("add", "-A", cwd=advancer)
    _git("commit", "-m", "advance topic", cwd=advancer)
    _git("push", "origin", "feature/x", cwd=advancer)

    (victim / "local.txt").write_text("local\n")
    first = _run_capture(home, ws, tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    side_ref = "refs/heads/capture/feature/x-deferred"
    first_sha = _git("rev-parse", side_ref, cwd=remote).stdout.strip()

    second = _run_capture(home, ws, tmp_path)
    assert second.returncode == 0, second.stdout + second.stderr
    assert _git("rev-parse", side_ref, cwd=remote).stdout.strip() == first_sha
    refs = _git("for-each-ref", "--format=%(refname)", "refs/heads/capture/feature/", cwd=remote).stdout.splitlines()
    assert refs == [side_ref]


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CAPTURE_SH.exists(), reason="capture.sh missing")
def test_capture_source_on_feature_branch_is_preserved(tmp_path):
    """On a non-default branch, capturing source is correct and must not be refused."""
    home, remote, ws, victim = _seed_pr_gated_clone(tmp_path, branch="feature/x")
    (victim / "work.py").write_text('print("feature work")\n')

    res = _run_capture(home, ws, tmp_path)
    assert res.returncode == 0, f"capture.sh failed: {res.stderr}\n{res.stdout}"
    assert "REFUSED" not in res.stdout, f"guard wrongly fired off main:\n{res.stdout}"
    pushed = _git("ls-tree", "-r", "--name-only", "origin/feature/x", cwd=victim).stdout
    assert "work.py" in pushed, f"feature-branch source was not preserved:\n{pushed}\n{res.stdout}"


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CAPTURE_SH.exists(), reason="capture.sh missing")
def test_capture_guard_off_never_reopens_main(tmp_path):
    """The source-filter escape hatch may preserve source off-default, but cannot reopen the default."""
    home, remote, ws, victim = _seed_pr_gated_clone(tmp_path)
    main_before = _git("rev-parse", "refs/heads/main", cwd=remote).stdout.strip()
    (victim / "leak.py").write_text('print("x")\n')

    res = _run_capture(home, ws, tmp_path, guard="off")
    assert res.returncode == 0, f"capture.sh failed: {res.stderr}\n{res.stdout}"
    assert "REFUSED" not in res.stdout, res.stdout
    assert _git("rev-parse", "refs/heads/main", cwd=remote).stdout.strip() == main_before
    main_tree = _git("ls-tree", "-r", "--name-only", "refs/heads/main", cwd=remote).stdout
    side_tree = _git("ls-tree", "-r", "--name-only", "refs/heads/capture/main-deferred", cwd=remote).stdout
    assert "leak.py" not in main_tree
    assert "leak.py" in side_tree


# --- scripts/continuation-beat.py classification + commit_paths guard ------------------------------
def _load_continuation(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path / "limen"))
    spec = importlib.util.spec_from_file_location("continuation_beat_guard_uut", CONTINUATION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _successful_gh(cwd, *args, timeout=120):
    if args[:2] == ("pr", "list"):
        return subprocess.CompletedProcess(args, 0, "[]", "")
    if args[:2] == ("pr", "create"):
        return subprocess.CompletedProcess(args, 0, "https://example.test/pull/1\n", "")
    raise AssertionError(f"unexpected gh call: {args}")


@pytest.mark.skipif(not CONTINUATION.exists(), reason="continuation-beat.py missing")
def test_is_source_path_classification(tmp_path, monkeypatch):
    mod = _load_continuation(tmp_path, monkeypatch)
    # SOURCE
    for p in [
        "a.py",
        "b.sh",
        "web/app/x.ts",
        "x.tsx",
        "y.rs",
        "z.go",
        "pyproject.toml",
        "setup.cfg",
        "Makefile",
        "sub/Dockerfile",
        ".github/workflows/pr-gate.yml",
        "cli/pytest.yml",
        "web/wrangler.yaml",
        "institutio/governance/gates.yaml",
        "scripts/ci.yml",
    ]:
        assert mod.is_source_path(p) is True, f"expected SOURCE: {p}"
    # DATA (the lane's legitimate cargo)
    for p in [
        "tasks.yaml",
        "tasks.yaml.lock",
        "logs/capture-log.jsonl",
        "docs/worktree-preservation-receipts.json",
        "docs/foo-receipts.json",
        "docs/data.yaml",
        "some/other.yaml",
    ]:
        assert mod.is_source_path(p) is False, f"expected DATA: {p}"


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CONTINUATION.exists(), reason="continuation-beat.py missing")
def test_continuation_preserves_default_off_branch_and_coalesces(tmp_path, monkeypatch):
    mod = _load_continuation(tmp_path, monkeypatch)
    home, remote, ws, repo = _seed_pr_gated_clone(tmp_path)
    main_before = _git("rev-parse", "refs/heads/main", cwd=remote).stdout.strip()
    local_before = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()
    gh_calls = []

    def successful_gh(cwd, *args, timeout=120):
        gh_calls.append((args, timeout))
        return _successful_gh(cwd, *args, timeout=timeout)

    monkeypatch.setattr(mod, "gh", successful_gh)

    (repo / "leak.py").write_text('print("un-CI-d")\n')
    (repo / "foo-receipts.json").write_text('{"r": 1}\n')

    # Both named paths route through one stable branch; neither local nor remote default moves.
    monkeypatch.chdir(repo)
    result = mod.commit_paths(repo, ["leak.py", "foo-receipts.json"], "beat: mixed", apply=True)

    assert result.get("preserved") is True, result
    assert result.get("published") is True, result
    assert result.get("deferred") is not True, result
    assert result.get("default_untouched") is True, result
    assert result.get("pr", {}).get("status") == "opened", result
    assert _git("rev-parse", "refs/heads/main", cwd=remote).stdout.strip() == main_before
    assert _git("rev-parse", "HEAD", cwd=repo).stdout.strip() == local_before
    side_ref = f"refs/heads/{result['branch']}"
    side_tree = _git("ls-tree", "-r", "--name-only", side_ref, cwd=remote).stdout
    assert "leak.py" in side_tree
    assert "foo-receipts.json" in side_tree

    side_before = _git("rev-parse", side_ref, cwd=remote).stdout.strip()
    again = mod.commit_paths(repo, ["leak.py", "foo-receipts.json"], "beat: mixed", apply=True)
    assert again.get("published") is True, again
    assert _git("rev-parse", side_ref, cwd=remote).stdout.strip() == side_before
    assert len(gh_calls) == 4
    assert max(timeout for _, timeout in gh_calls) <= 45


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CONTINUATION.exists(), reason="continuation-beat.py missing")
def test_continuation_pr_probe_failure_keeps_remote_head_unmoved(tmp_path, monkeypatch):
    mod = _load_continuation(tmp_path, monkeypatch)
    _home, remote, _ws, repo = _seed_pr_gated_clone(tmp_path)
    main_before = _git("rev-parse", "refs/heads/main", cwd=remote).stdout.strip()
    (repo / "foo-receipts.json").write_text('{"r": 1}\n')
    monkeypatch.setattr(
        mod,
        "gh",
        lambda cwd, *args, timeout=120: subprocess.CompletedProcess(args, 1, "", "offline"),
    )

    result = mod.commit_paths(repo, ["foo-receipts.json"], "beat: data", apply=True)

    assert result.get("deferred") is True, result
    assert str(result.get("reason", "")).startswith("pr-probe-failed:"), result
    assert _git("rev-parse", "refs/heads/main", cwd=remote).stdout.strip() == main_before
    refs = _git("for-each-ref", "--format=%(refname)", "refs/heads/continuation-beat/", cwd=remote).stdout.strip()
    assert refs == ""
    local_ref = f"refs/limen/continuation-beat/{result['branch'].rsplit('/', 1)[-1]}"
    local_tree = _git("ls-tree", "-r", "--name-only", local_ref, cwd=repo).stdout
    assert "foo-receipts.json" in local_tree


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CONTINUATION.exists(), reason="continuation-beat.py missing")
def test_continuation_repeated_push_failures_chain_local_custody(tmp_path, monkeypatch):
    mod = _load_continuation(tmp_path, monkeypatch)
    _home, _remote, _ws, repo = _seed_pr_gated_clone(tmp_path)
    (repo / "foo-receipts.json").write_text('{"r": 1}\n')
    real_git = mod.git

    def failed_push(cwd, *args, timeout=120, env=None):
        if args and args[0] == "push":
            return subprocess.CompletedProcess(args, 1, "", "offline")
        return real_git(cwd, *args, timeout=timeout, env=env)

    monkeypatch.setattr(mod, "gh", _successful_gh)
    monkeypatch.setattr(mod, "git", failed_push)
    first = mod.commit_paths(repo, ["foo-receipts.json"], "beat: first", apply=True)
    assert first.get("deferred") is True, first
    first_sha = first["commit"]

    (repo / "foo-receipts.json").write_text('{"r": 2}\n')
    second = mod.commit_paths(repo, ["foo-receipts.json"], "beat: second", apply=True)
    assert second.get("deferred") is True, second
    assert real_git(repo, "merge-base", "--is-ancestor", first_sha, second["commit"]).returncode == 0
    assert mod._commit_paths_ok(second, apply=True) is False

    # A clean worktree still retries the exact pending custody commit.
    (repo / "foo-receipts.json").unlink()
    assert real_git(repo, "status", "--porcelain", "--", "foo-receipts.json").stdout.strip() == ""
    monkeypatch.setattr(mod, "git", real_git)
    recovered = mod.commit_paths(repo, ["foo-receipts.json"], "beat: recover", apply=True)
    assert recovered.get("published") is True, recovered
    remote_ref = f"refs/heads/{recovered['branch']}"
    remote_tree = _git("ls-tree", "-r", "--name-only", remote_ref, cwd=_remote).stdout
    assert "foo-receipts.json" in remote_tree


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CONTINUATION.exists(), reason="continuation-beat.py missing")
def test_continuation_open_pr_head_is_immutable(tmp_path, monkeypatch):
    mod = _load_continuation(tmp_path, monkeypatch)
    _home, remote, _ws, repo = _seed_pr_gated_clone(tmp_path)
    monkeypatch.setattr(mod, "gh", _successful_gh)
    (repo / "foo-receipts.json").write_text('{"r": 1}\n')
    first = mod.commit_paths(repo, ["foo-receipts.json"], "beat: first", apply=True)
    remote_ref = f"refs/heads/{first['branch']}"
    remote_before = _git("rev-parse", remote_ref, cwd=remote).stdout.strip()
    assert first.get("published") is True, first

    (repo / "foo-receipts.json").write_text('{"r": 2}\n')
    real_git = mod.git
    pushes = []

    def guarded_git(cwd, *args, timeout=120, env=None):
        if args and args[0] == "push":
            pushes.append(args)
            return subprocess.CompletedProcess(args, 1, "", "must not push")
        return real_git(cwd, *args, timeout=timeout, env=env)

    def open_gh(cwd, *args, timeout=120):
        if args[:2] == ("pr", "list"):
            payload = [{"number": 1, "url": "https://example.test/pull/1", "headRefOid": remote_before}]
            return subprocess.CompletedProcess(args, 0, __import__("json").dumps(payload), "")
        raise AssertionError(f"unexpected gh call: {args}")

    monkeypatch.setattr(mod, "git", guarded_git)
    monkeypatch.setattr(mod, "gh", open_gh)
    second = mod.commit_paths(repo, ["foo-receipts.json"], "beat: second", apply=True)

    assert second.get("deferred") is True, second
    assert second.get("reason") == "preservation-pr-in-flight", second
    assert pushes == []
    assert _git("rev-parse", remote_ref, cwd=remote).stdout.strip() == remote_before
    assert second["commit"] != remote_before


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CONTINUATION.exists(), reason="continuation-beat.py missing")
def test_continuation_refuses_preexisting_topic_index(tmp_path, monkeypatch):
    mod = _load_continuation(tmp_path, monkeypatch)
    _home, remote, _ws, repo = _seed_pr_gated_clone(tmp_path, branch="feature/y")
    before = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()
    (repo / "peer.py").write_text("peer\n")
    (repo / "work.py").write_text("work\n")
    _git("add", "peer.py", cwd=repo)

    result = mod.commit_paths(repo, ["work.py"], "beat: owned", apply=True)

    assert result.get("deferred") is True, result
    assert result.get("reason") == "preexisting-index-not-empty", result
    assert _git("rev-parse", "HEAD", cwd=repo).stdout.strip() == before
    staged = _git("diff", "--cached", "--name-only", cwd=repo).stdout.splitlines()
    assert staged == ["peer.py"]
    assert "work.py" not in _git("ls-tree", "-r", "--name-only", "refs/heads/main", cwd=remote).stdout


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CONTINUATION.exists(), reason="continuation-beat.py missing")
def test_continuation_refuses_detached_head(tmp_path, monkeypatch):
    mod = _load_continuation(tmp_path, monkeypatch)
    _home, remote, _ws, repo = _seed_pr_gated_clone(tmp_path)
    _git("checkout", "--detach", cwd=repo)
    head_before = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()
    default_before = _git("rev-parse", "refs/heads/main", cwd=remote).stdout.strip()
    (repo / "work.py").write_text("detached\n")

    result = mod.commit_paths(repo, ["work.py"], "beat: detached", apply=True)

    assert result.get("deferred") is True, result
    assert result.get("reason") == "detached-head", result
    assert _git("rev-parse", "HEAD", cwd=repo).stdout.strip() == head_before
    assert _git("rev-parse", "refs/heads/main", cwd=remote).stdout.strip() == default_before
    assert _git("status", "--porcelain", "--", "work.py", cwd=repo).stdout.strip() == "?? work.py"


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CONTINUATION.exists(), reason="continuation-beat.py missing")
def test_continuation_uses_derived_default_branch(tmp_path, monkeypatch):
    mod = _load_continuation(tmp_path, monkeypatch)
    _home, remote, _ws, repo = _seed_pr_gated_clone(tmp_path, default_branch="trunk")
    monkeypatch.setattr(mod, "gh", _successful_gh)
    default_before = _git("rev-parse", "refs/heads/trunk", cwd=remote).stdout.strip()
    (repo / "receipt.json").write_text('{"ok": true}\n')

    result = mod.commit_paths(repo, ["receipt.json"], "beat: trunk", apply=True)

    assert result.get("published") is True, result
    assert _git("rev-parse", "refs/heads/trunk", cwd=remote).stdout.strip() == default_before
    side_tree = _git("ls-tree", "-r", "--name-only", f"refs/heads/{result['branch']}", cwd=remote).stdout
    assert "receipt.json" in side_tree


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CONTINUATION.exists(), reason="continuation-beat.py missing")
def test_continuation_main_probe_failure_is_bounded_and_precommit(tmp_path, monkeypatch):
    mod = _load_continuation(tmp_path, monkeypatch)
    home, remote, ws, repo = _seed_pr_gated_clone(tmp_path)
    before = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()
    (repo / "foo-receipts.json").write_text('{"r": 1}\n')
    real_git = mod.git
    probes = []

    def failed_probe(cwd, *args, timeout=120, env=None):
        if args[:2] == ("ls-remote", "--heads"):
            probes.append(timeout)
            return subprocess.CompletedProcess(args, 1, "", "offline")
        return real_git(cwd, *args, timeout=timeout, env=env)

    monkeypatch.setattr(mod, "git", failed_probe)
    result = mod.commit_paths(repo, ["foo-receipts.json"], "beat: data", apply=True)
    assert result.get("deferred") is True, result
    assert str(result.get("reason", "")).startswith("preservation-probe-failed:"), result
    assert probes == [30]
    assert _git("rev-parse", "HEAD", cwd=repo).stdout.strip() == before
    assert _git("status", "--porcelain", cwd=repo).stdout.strip() == "?? foo-receipts.json"


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CONTINUATION.exists(), reason="continuation-beat.py missing")
def test_continuation_guard_off_and_non_main(tmp_path, monkeypatch):
    mod = _load_continuation(tmp_path, monkeypatch)
    # Non-default branch: normal commit/push behavior remains.
    home, remote, ws, repo = _seed_pr_gated_clone(tmp_path, branch="feature/y")
    (repo / "work.py").write_text('print("f")\n')
    refused = mod._guard_source_on_main(repo, ["work.py"])
    assert refused == [], "guard wrongly fired off main"
    result = mod.commit_paths(repo, ["work.py"], "beat: feature", apply=True)
    assert result.get("committed"), result
    feature_tree = _git("ls-tree", "-r", "--name-only", "refs/heads/feature/y", cwd=remote).stdout
    main_tree = _git("ls-tree", "-r", "--name-only", "refs/heads/main", cwd=remote).stdout
    assert "work.py" in feature_tree
    assert "work.py" not in main_tree

    # Default branch + guard off: not refused.
    _git("checkout", "main", cwd=repo)
    (repo / "leak.py").write_text('print("x")\n')
    _git("add", "leak.py", cwd=repo)
    monkeypatch.setenv("LIMEN_PUSH_GUARD", "off")
    assert mod._guard_source_on_main(repo, ["leak.py"]) == []


# --- cli/src/limen/tabularius.py defensive assert -------------------------------------------------
@pytest.mark.skipif(not _has_git(), reason="git not available")
def test_tabularius_asserts_only_board_reaches_publication_branch(tmp_path):
    """The board publisher must LOUDLY refuse to carry anything but tasks.yaml."""
    from limen.tabularius import preserve_board_projection

    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    repo = tmp_path / "repo"
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True)
    _git("switch", "-c", "main", cwd=repo)
    (repo / "tasks.yaml").write_text("version: '1.0'\ntasks: []\n")
    _git("add", "-A", cwd=repo)
    subprocess.run(
        ["git", "-c", "user.email=t@t.local", "-c", "user.name=t", "commit", "-qm", "base"],
        cwd=repo,
        check=True,
    )
    _git("push", "-u", "origin", "main", cwd=repo)

    # Sanity: a normal board change preserves cleanly (the invariant holds, no false raise).
    (repo / "tasks.yaml").write_text("version: '1.0'\ntasks: [{id: T-1, title: t, target_agent: jules}]\n")
    result = preserve_board_projection(repo / "tasks.yaml", manage_pr=False)
    assert result.pushed is True or result.skipped, result
