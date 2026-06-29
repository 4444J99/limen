from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from click.testing import CliRunner

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.cli import main  # noqa: E402


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\n{result.stdout}\n{result.stderr}")
    return result


def test_workstream_command_writes_private_kickstart_packet(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    result = CliRunner().invoke(
        main,
        [
            "workstream",
            "--prompt",
            "Ship a bounded packet.",
            str(repo),
            "Demo Packet",
        ],
    )

    assert result.exit_code == 0, result.output
    wt = repo / ".worktrees" / "demo-packet"
    readme = wt / ".limen-workstream" / "README.md"
    kickstart = wt / ".limen-workstream" / "kickstart.sh"
    assert readme.exists()
    assert kickstart.exists()
    assert "Ship a bounded packet." in readme.read_text(encoding="utf-8")
    assert "bash " in result.output and "kickstart.sh" in result.output
    assert ".limen-workstream" not in _git("status", "--short", cwd=wt).stdout
