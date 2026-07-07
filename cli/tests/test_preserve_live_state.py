from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "preserve-live-state.py"


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def commit_all(repo: Path, msg: str) -> None:
    git(repo, "add", ".")
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=test", "commit", "-qm", msg],
        cwd=repo,
        check=True,
    )


def make_repo(tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    repo = tmp_path / "repo"
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True)
    git(repo, "switch", "-c", "main")
    (repo / "organs" / "financial").mkdir(parents=True)
    (repo / "tasks.yaml").write_text("tasks: []\n", encoding="utf-8")
    (repo / "organs" / "financial" / "STATUS.md").write_text("old\n", encoding="utf-8")
    (repo / "organs" / "financial" / "cashflow.md").write_text("old\n", encoding="utf-8")
    commit_all(repo, "base")
    git(repo, "push", "-u", "origin", "main")
    return repo, origin


def test_preserve_live_state_pushes_allowed_paths(tmp_path: Path) -> None:
    repo, origin = make_repo(tmp_path)
    (repo / "tasks.yaml").write_text("tasks:\n- id: T1\n", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=repo,
        env={**os.environ, "LIMEN_ROOT": str(repo)},
        capture_output=True,
        text=True,
        check=True,
    )

    assert "preserve-live-state: pushed" in proc.stdout
    assert git(repo, "status", "--porcelain", "--", "tasks.yaml") == ""
    remote_tasks = subprocess.run(
        ["git", "--git-dir", str(origin), "show", "main:tasks.yaml"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "id: T1" in remote_tasks


def test_preserve_live_state_skips_when_not_at_remote_release(tmp_path: Path) -> None:
    repo, _origin = make_repo(tmp_path)
    (repo / "tasks.yaml").write_text("tasks:\n- id: local\n", encoding="utf-8")
    commit_all(repo, "local commit")
    before = git(repo, "rev-parse", "HEAD")

    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=repo,
        env={**os.environ, "LIMEN_ROOT": str(repo)},
        capture_output=True,
        text=True,
        check=True,
    )

    assert "live root not at origin/main; skip" in proc.stdout
    assert git(repo, "rev-parse", "HEAD") == before
