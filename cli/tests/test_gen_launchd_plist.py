from __future__ import annotations

import os
import plistlib
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts" / "gen-launchd-plist.sh"


def render(
    tmp_path: Path,
    scratch: Path,
    *,
    agent_host: str | None = None,
) -> dict:
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "LIMEN_ROOT": str(ROOT),
        "LIMEN_WORKDIR": str(tmp_path / "Workspace"),
        "LIMEN_SCRATCH_ROOT": str(scratch),
    }
    env.pop("DOMUS_AGENT_HOST_BIN", None)
    env.pop("LIMEN_AGENT_HOST_BIN", None)
    if agent_host is not None:
        env["LIMEN_AGENT_HOST_BIN"] = agent_host
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


def test_generator_routes_heartbeat_through_stable_host(tmp_path: Path) -> None:
    scratch = tmp_path / "Scratch"
    scratch.mkdir()

    plist = render(tmp_path, scratch)

    assert plist["ProgramArguments"] == [
        str(tmp_path / "home/Applications/DomusAgentHost.app/Contents/MacOS/DomusAgentHost"),
        "run",
        "--",
        "/bin/bash",
        str(ROOT / "scripts/heartbeat-loop.sh"),
    ]


def test_generator_expands_configured_host_home_path(tmp_path: Path) -> None:
    scratch = tmp_path / "Scratch"
    scratch.mkdir()

    plist = render(
        tmp_path,
        scratch,
        agent_host=("~/Applications/ConfiguredHost.app/Contents/MacOS/DomusAgentHost"),
    )

    assert plist["ProgramArguments"][0] == str(
        tmp_path / "home/Applications/ConfiguredHost.app/Contents/MacOS/DomusAgentHost"
    )


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
