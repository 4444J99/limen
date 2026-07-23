import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def test_sync_release_census_is_counts_only(tmp_path):
    repo = tmp_path / "private-limen-root"
    home = tmp_path / "home"
    repo.mkdir()
    home.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "tasks.yaml").write_text("tasks: []\n", encoding="utf-8")
    (repo / "logs").mkdir()
    (repo / "private-untracked.txt").write_text("private body\n", encoding="utf-8")

    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "sync-release.sh"), "--census"],
        capture_output=True,
        text=True,
        env={**os.environ, "LIMEN_ROOT": str(repo), "HOME": str(home)},
        check=True,
    )
    census = json.loads(proc.stdout)
    encoded = json.dumps(census, sort_keys=True)

    assert census["root_present"] is True
    assert census["git_repo"] is True
    assert census["on_release_branch"] is True
    assert census["tasks_present"] is True
    assert census["logs_present"] is True
    assert census["untracked_count"] == 2
    assert "private-limen-root" not in encoded
    assert "private-untracked" not in encoded
