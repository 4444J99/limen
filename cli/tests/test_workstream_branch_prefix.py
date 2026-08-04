"""`--branch-prefix` — the branch namespace for a NEW worktree.

`branch="work/$slug"` was hardcoded, so `branch_prefix` in the STREAMS registry was inert: a row
declaring `heal` still opened on `work/`. These tests pin the three properties that make the flag
safe to add rather than merely present.

The interesting one is ORDERING. An unknown prefix must be refused BEFORE any binary probe, because
argument validity is a property of the arguments and not of what happens to be installed — CI (no
agent CLI) must reach the same verdict as a workstation that has one. That lesson was paid for twice
already in this launcher (the lane tier pin, then the Codex sandbox), each time as a test that
passed locally and failed in CI on environment alone.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STARTER = ROOT / "scripts" / "start-worktree-session.sh"


def _git(*args: str, cwd: Path) -> None:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\n{result.stdout}\n{result.stderr}")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "demo-repo"
    r.mkdir()
    _git("init", "-q", "-b", "main", cwd=r)
    _git("config", "user.email", "test@example.invalid", cwd=r)
    _git("config", "user.name", "Test User", cwd=r)
    (r / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=r)
    _git("commit", "-qm", "init", cwd=r)
    return r


def _run(*args: str, path: str | None = None):
    env = {**os.environ}
    if path is not None:
        env["PATH"] = path
    return subprocess.run(["bash", str(STARTER), *args], env=env, text=True, capture_output=True, timeout=60)


def _branches(repo: Path) -> list[str]:
    out = subprocess.run(
        ["git", "branch", "--format=%(refname:short)"], cwd=repo, text=True, capture_output=True, check=True
    )
    return out.stdout.split()


def test_the_default_is_unchanged(repo: Path):
    """`work` reproduces the old hardcoded behaviour exactly, so every existing caller — cli.py,
    lead-spawn.py, the test harnesses, humans — is unaffected by construction."""
    proc = _run(str(repo), "prefix-default")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "work/prefix-default" in _branches(repo)


def test_a_declared_prefix_is_honoured(repo: Path):
    proc = _run("--branch-prefix", "heal", str(repo), "prefix-honoured")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    branches = _branches(repo)
    assert "heal/prefix-honoured" in branches
    assert "work/prefix-honoured" not in branches, "the prefix was accepted and then ignored"


def test_an_unknown_prefix_is_refused_not_coerced(repo: Path):
    """Coercing to `work` would put the lane on a branch the caller did not choose — and `branch` is
    bound into the capsule identity digest, so the wrong namespace is not cosmetic."""
    proc = _run("--branch-prefix", "not-a-prefix", str(repo), "prefix-refused")
    assert proc.returncode == 2
    assert "unknown --branch-prefix" in proc.stderr
    assert not _branches(repo) or "not-a-prefix/prefix-refused" not in _branches(repo)


def test_the_refusal_does_not_depend_on_what_is_installed(repo: Path, tmp_path: Path):
    """THE ORDERING PROPERTY. Same verdict with and without an agent CLI on PATH.

    Without this the check would sit after the binary probe and exit 127 in CI while exiting 2
    locally — an assertion passing or failing on environment alone, which is exactly how the lane
    tier pin and the Codex sandbox each broke before.
    """
    stripped = tmp_path / "bin"
    stripped.mkdir()
    # shutil.which, NOT `command -v`: `command` is a shell BUILTIN, not an executable. macOS happens
    # to ship /usr/bin/command so this passed locally and raised FileNotFoundError on the Linux
    # runner — a test-harness bug that looked like a product failure.
    for tool in ("git", "python3", "bash", "sed", "tr", "awk", "grep", "cat", "mktemp", "dirname", "basename"):
        src = shutil.which(tool)
        if src:
            os.symlink(src, stripped / tool)

    bad_stripped = _run("--branch-prefix", "nope", "--agent", "claude", str(repo), "p1", path=str(stripped))
    bad_full = _run("--branch-prefix", "nope", "--agent", "claude", str(repo), "p2")
    assert bad_stripped.returncode == bad_full.returncode == 2, (
        f"verdict depends on environment: stripped={bad_stripped.returncode} full={bad_full.returncode}"
    )
    assert "unknown --branch-prefix" in bad_stripped.stderr

    # And the probe is not swallowed: a VALID prefix with no binary must still reach 127.
    good_stripped = _run("--branch-prefix", "heal", "--agent", "claude", str(repo), "p3", path=str(stripped))
    assert good_stripped.returncode == 127, (
        "the prefix check swallowed the binary probe — a valid prefix must still fail on a missing CLI"
    )
