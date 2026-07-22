from __future__ import annotations

import os
import plistlib
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts" / "gen-launchd-plist.sh"


def render(tmp_path: Path, scratch: Path) -> dict:
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "LIMEN_ROOT": str(ROOT),
        "LIMEN_WORKDIR": str(tmp_path / "Workspace"),
        "LIMEN_SCRATCH_ROOT": str(scratch),
    }
    proc = subprocess.run(
        ["bash", str(GENERATOR), "--stdout"],
        check=True,
        capture_output=True,
        env=env,
    )
    return plistlib.loads(proc.stdout)


def worktree_env(plist: dict) -> tuple[str, str]:
    env = plist["EnvironmentVariables"]
    return env["LIMEN_WORKTREES"], env["LIMEN_WORKTREE_ROOT"]


def test_generator_selects_writable_scratch_without_creating_children(tmp_path: Path) -> None:
    scratch = tmp_path / "Scratch"
    scratch.mkdir()

    values = worktree_env(render(tmp_path, scratch))

    expected = str(scratch / "limen-worktrees")
    assert values == (expected, expected)
    assert not (scratch / "limen-worktrees").exists()


def test_generator_falls_back_when_scratch_is_absent_without_creating_it(tmp_path: Path) -> None:
    scratch = tmp_path / "absent-Scratch"

    values = worktree_env(render(tmp_path, scratch))

    expected = str(tmp_path / "Workspace" / ".limen-worktrees")
    assert values == (expected, expected)
    assert not scratch.exists()


def test_generator_falls_back_when_scratch_is_unwritable(tmp_path: Path) -> None:
    scratch = tmp_path / "Scratch"
    scratch.mkdir()
    scratch.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        values = worktree_env(render(tmp_path, scratch))
    finally:
        scratch.chmod(stat.S_IRWXU)

    expected = str(tmp_path / "Workspace" / ".limen-worktrees")
    assert values == (expected, expected)
    assert not (scratch / "limen-worktrees").exists()
