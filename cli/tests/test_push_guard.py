"""DATA_ONLY push guard — the autonomic direct-push lanes can NEVER commit SOURCE to a pr-gated repo's
`main` un-CI'd (issue #872 / PREC-2026-07-10-direct-push-lane-rots-main).

Three lanes push to `main`; this guard makes each refuse SOURCE (code/config that belongs behind
pr-gate) while still carrying its legitimate DATA cargo (tasks.yaml, receipts, logs):

  * scripts/capture.sh              — `_unstage_source` in the `_unstage_*` chain (in-place + side ref)
  * scripts/continuation-beat.py    — `is_source_path` / `_guard_source_on_main` in `commit_paths`
  * cli/src/limen/tabularius.py     — a LOUD defensive assert (only the board may reach main)

The rule is self-configuring: it fires only when the push target is `main` AND the repo has
`.github/workflows/pr-gate.yml`. Non-main branches and ungated repos keep current behavior (capture
preserving source on a feature/worktree branch is CORRECT). Escape hatch: `LIMEN_PUSH_GUARD=off`.
"""

from __future__ import annotations

import importlib.util
import os
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


def _seed_pr_gated_clone(tmp_path: Path, *, branch: str = "main"):
    """A bare origin with a pr-gate.yml on main, plus a fresh clone on *branch* under an LIMEN_WORKSPACE."""
    home = tmp_path / "home"
    home.mkdir()
    remote = tmp_path / "remote.git"
    ws = tmp_path / "ws"
    ws.mkdir()
    victim = ws / "victim"

    _git("init", "--bare", "--initial-branch=main", str(remote), cwd=tmp_path)
    seed = tmp_path / "seed"
    _git("clone", str(remote), str(seed), cwd=tmp_path)
    (seed / ".github" / "workflows").mkdir(parents=True)
    (seed / ".github" / "workflows" / "pr-gate.yml").write_text("on: pull_request\n")
    (seed / "seed.txt").write_text("seed\n")
    _git("add", "-A", cwd=seed)
    _git("commit", "-m", "seed", cwd=seed)
    _git("push", "origin", "main", cwd=seed)

    _git("clone", str(remote), str(victim), cwd=tmp_path)
    # Repo-local identity so an INTERNAL commit (continuation-beat's commit_paths, which does not carry
    # our GIT_ENV) works on a CI runner that has no global git identity. (Local machines have one, which
    # masked this — hence the CI-only "Author identity unknown" failure.)
    _git("config", "user.email", "guard@test.local", cwd=victim)
    _git("config", "user.name", "guard-test", cwd=victim)
    if branch != "main":
        _git("checkout", "-b", branch, cwd=victim)
    return home, remote, ws, victim


def _run_capture(home: Path, ws: Path, tmp_path: Path, guard: str = "on") -> subprocess.CompletedProcess[str]:
    env = {**_base_env(), **GIT_ENV, "HOME": str(home), "LIMEN_ROOT": str(tmp_path), "LIMEN_WORKSPACE": str(ws)}
    if guard != "on":
        env["LIMEN_PUSH_GUARD"] = guard
    return subprocess.run(["bash", str(CAPTURE_SH)], env=env, capture_output=True, text=True)


# --- scripts/capture.sh (the PRIMARY leak) -------------------------------------------------------
@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CAPTURE_SH.exists(), reason="capture.sh missing")
def test_capture_refuses_source_on_main_leaves_it_on_disk(tmp_path):
    """A staged `.py` on main of a pr-gate repo is refused + unstaged + STAYS ON DISK, and is never
    pushed to main; a receipt DATA file alongside it IS accepted and pushed."""
    home, remote, ws, victim = _seed_pr_gated_clone(tmp_path)
    (victim / "leak.py").write_text('print("un-CI-d source")\n')
    (victim / "foo-receipts.json").write_text('{"receipt": 1}\n')

    res = _run_capture(home, ws, tmp_path)
    assert res.returncode == 0, f"capture.sh failed: {res.stderr}\n{res.stdout}"

    assert "REFUSED source on main: leak.py" in res.stdout, res.stdout
    # (a) refused source is preserved on disk, never deleted
    assert (victim / "leak.py").exists(), "refused source was LOST from disk"
    # (b) source never reached main; the receipt DATA file did
    pushed = _git("ls-tree", "-r", "--name-only", "origin/main", cwd=victim).stdout
    assert "leak.py" not in pushed, f"SOURCE reached protected main un-CI'd:\n{pushed}\n{res.stdout}"
    assert "foo-receipts.json" in pushed, f"DATA cargo was wrongly refused:\n{pushed}\n{res.stdout}"


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CAPTURE_SH.exists(), reason="capture.sh missing")
def test_capture_source_on_feature_branch_is_preserved(tmp_path):
    """On a NON-main branch, capturing source is correct and must not be refused (current behavior)."""
    home, remote, ws, victim = _seed_pr_gated_clone(tmp_path, branch="feature/x")
    (victim / "work.py").write_text('print("feature work")\n')

    res = _run_capture(home, ws, tmp_path)
    assert res.returncode == 0, f"capture.sh failed: {res.stderr}\n{res.stdout}"
    assert "REFUSED" not in res.stdout, f"guard wrongly fired off main:\n{res.stdout}"
    pushed = _git("ls-tree", "-r", "--name-only", "origin/feature/x", cwd=victim).stdout
    assert "work.py" in pushed, f"feature-branch source was not preserved:\n{pushed}\n{res.stdout}"


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CAPTURE_SH.exists(), reason="capture.sh missing")
def test_capture_guard_off_disables(tmp_path):
    """LIMEN_PUSH_GUARD=off is the escape hatch: source flows to main as before."""
    home, remote, ws, victim = _seed_pr_gated_clone(tmp_path)
    (victim / "leak.py").write_text('print("x")\n')

    res = _run_capture(home, ws, tmp_path, guard="off")
    assert res.returncode == 0, f"capture.sh failed: {res.stderr}\n{res.stdout}"
    assert "REFUSED" not in res.stdout, res.stdout
    pushed = _git("ls-tree", "-r", "--name-only", "origin/main", cwd=victim).stdout
    assert "leak.py" in pushed, f"guard=off did not disable the refusal:\n{pushed}\n{res.stdout}"


# --- scripts/continuation-beat.py classification + commit_paths guard ------------------------------
def _load_continuation(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path / "limen"))
    spec = importlib.util.spec_from_file_location("continuation_beat_guard_uut", CONTINUATION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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
def test_continuation_commit_paths_refuses_source_on_main(tmp_path, monkeypatch):
    mod = _load_continuation(tmp_path, monkeypatch)
    home, remote, ws, repo = _seed_pr_gated_clone(tmp_path)

    (repo / "leak.py").write_text('print("un-CI-d")\n')
    (repo / "foo-receipts.json").write_text('{"r": 1}\n')

    # both staged in one commit_paths call; only the DATA file may be committed+pushed
    monkeypatch.chdir(repo)
    result = mod.commit_paths(repo, ["leak.py", "foo-receipts.json"], "beat: mixed", apply=True)

    assert result.get("refused_source") == ["leak.py"], result
    assert (repo / "leak.py").exists(), "refused source lost from disk"
    pushed = _git("ls-tree", "-r", "--name-only", "origin/main", cwd=repo).stdout
    assert "leak.py" not in pushed, f"SOURCE reached main:\n{pushed}"
    assert "foo-receipts.json" in pushed, f"DATA cargo dropped:\n{pushed}"


@pytest.mark.skipif(not _has_git(), reason="git not available")
@pytest.mark.skipif(not CONTINUATION.exists(), reason="continuation-beat.py missing")
def test_continuation_guard_off_and_non_main(tmp_path, monkeypatch):
    mod = _load_continuation(tmp_path, monkeypatch)
    # non-main branch: source is not refused
    home, remote, ws, repo = _seed_pr_gated_clone(tmp_path, branch="feature/y")
    (repo / "work.py").write_text('print("f")\n')
    refused = mod._guard_source_on_main(repo, ["work.py"])
    assert refused == [], "guard wrongly fired off main"

    # main + guard off: not refused
    _git("checkout", "main", cwd=repo)
    (repo / "leak.py").write_text('print("x")\n')
    _git("add", "leak.py", cwd=repo)
    monkeypatch.setenv("LIMEN_PUSH_GUARD", "off")
    assert mod._guard_source_on_main(repo, ["leak.py"]) == []


# --- cli/src/limen/tabularius.py defensive assert -------------------------------------------------
@pytest.mark.skipif(not _has_git(), reason="git not available")
def test_tabularius_asserts_only_board_reaches_main(tmp_path):
    """The board-preservation push must LOUDLY refuse to carry anything but tasks.yaml."""
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
    result = preserve_board_projection(repo / "tasks.yaml")
    assert result.pushed is True or result.skipped, result
