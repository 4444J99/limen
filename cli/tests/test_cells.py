from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _init_repo(path: Path, branch: str) -> None:
    subprocess.run(["git", "init", "-b", branch], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True, text=True)


def test_scoped_conductor_never_falls_back_to_full_board(tmp_path: Path) -> None:
    root = tmp_path / "limen"
    cell = root / ".claude" / "worktrees" / "demo"
    (cell / "scripts").mkdir(parents=True)
    (root / "logs" / "cells").mkdir(parents=True)
    (cell / "tasks.yaml").write_text(
        """version: "1.0"
portal:
  name: test
tasks:
  - id: T1
    title: mixed-purpose task
    target_agent: any
    status: open
    created: "2026-07-01"
""",
        encoding="utf-8",
    )
    heartbeat = cell / "scripts" / "heartbeat.sh"
    heartbeat.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    heartbeat.chmod(0o755)
    _init_repo(cell, "cell/demo")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_limen = fake_bin / "limen"
    fake_limen.write_text("#!/usr/bin/env bash\nexit 23\n", encoding="utf-8")
    fake_limen.chmod(0o755)

    env = {
        **os.environ,
        "LIMEN_ROOT": str(root),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }
    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "cells.sh"), "conduct", "demo", "--workstream", "financial"],
        text=True,
        capture_output=True,
        env=env,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr
    cell_board = cell / "tasks.cell.yaml"
    for _ in range(50):
        if cell_board.exists():
            break
        time.sleep(0.02)

    assert cell_board.exists()
    data = yaml.safe_load(cell_board.read_text(encoding="utf-8"))
    assert data["tasks"] == []
    assert "T1" not in cell_board.read_text(encoding="utf-8")


def test_cell_commands_ignore_non_cell_worktrees(tmp_path: Path) -> None:
    root = tmp_path / "limen"
    cells = root / ".claude" / "worktrees"
    (root / "logs" / "cells").mkdir(parents=True)

    real = cells / "demo"
    other = cells / "not-a-cell"
    for path, branch in ((real, "cell/demo"), (other, "worktree-not-a-cell")):
        (path / "scripts").mkdir(parents=True)
        (path / "tasks.yaml").write_text('version: "1.0"\ntasks: []\n', encoding="utf-8")
        _init_repo(path, branch)

    env = {**os.environ, "LIMEN_ROOT": str(root)}
    listing = subprocess.run(
        ["bash", str(ROOT / "scripts" / "cells.sh"), "ls"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert listing.returncode == 0
    assert "demo" in listing.stdout
    assert "not-a-cell" not in listing.stdout

    rejected = subprocess.run(
        ["bash", str(ROOT / "scripts" / "cells.sh"), "cd", "not-a-cell"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert rejected.returncode != 0
    assert "not a cell" in rejected.stderr
