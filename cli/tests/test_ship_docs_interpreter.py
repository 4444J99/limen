"""`scripts/ship-docs.sh` must resolve its gate interpreter before it reserves or creates anything.

Its admission and release organs need PyYAML. Under a Homebrew-first PATH a bare `python3` lacks it, and
the script used to find that out only after it had fetched, named a branch and worktree, and installed its
EXIT trap — leaving retained-worktree and retained-branch litter behind a failure that had nothing to do
with the docs being shipped. Failing first leaves nothing to clean up.
"""

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _git(repo: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    done = subprocess.run(["git", "-C", str(repo), *args], env=env, capture_output=True, text=True, check=True)
    return done.stdout


def test_unusable_interpreter_fails_before_any_branch_or_worktree_exists(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    (repo / "scripts" / "lib").mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "ship-docs.sh", repo / "scripts" / "ship-docs.sh")
    shutil.copy2(ROOT / "scripts" / "lib" / "gate-python.sh", repo / "scripts" / "lib" / "gate-python.sh")
    (repo / "docs").mkdir()
    (repo / "docs" / "note.md").write_text("hello\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-q", "origin", "main")

    # PATH holds a python3 that cannot import yaml (exit 99) and the resolver is told no other exists.
    poisoned = tmp_path / "path"
    poisoned.mkdir()
    python = poisoned / "python3"
    python.write_text("#!/bin/sh\nexit 99\n")
    python.chmod(0o700)
    env = {k: v for k, v in os.environ.items() if not k.startswith("LIMEN_")}
    env["PATH"] = f"{poisoned}:/usr/bin:/bin:{Path(shutil.which('git') or '/usr/bin/git').parent}"
    env["LIMEN_GATE_PYTHON_CANDIDATES"] = "no-such-python-anywhere"
    env["LIMEN_WORKTREES"] = str(tmp_path / "wt")

    result = subprocess.run(
        ["/bin/bash", str(repo / "scripts" / "ship-docs.sh"), "note", "docs: note", "docs/note.md"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "no usable gate interpreter" in result.stderr
    assert "retained" not in result.stdout  # the EXIT trap was never armed
    assert _git(repo, "branch", "--list", "docs/*").strip() == ""
    assert len(_git(repo, "worktree", "list").strip().splitlines()) == 1
    assert not (tmp_path / "wt").exists()
