"""Tests for the self-feeding backlog generator.

generate-backlog.py runs autonomously in the heartbeat, so its safety properties matter:
(1) it must NO-OP when the queue is healthy (never flood a full queue),
(2) it must respect the max-new anti-flood cap,
(3) when it does generate, it spreads across DISTINCT repos (no repo gets dumped on).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "generate-backlog.py"


def _board(path: Path, repos: list[str], n_open_per_repo: int = 1) -> None:
    tasks = []
    i = 0
    for r in repos:
        for _ in range(n_open_per_repo):
            i += 1
            tasks.append({
                "id": f"SEED-{i}", "title": f"seed {i}", "repo": r,
                "target_agent": "codex", "priority": "medium", "budget_cost": 1,
                "status": "open", "created": "2026-06-01", "dispatch_log": [],
            })
    doc = {
        "version": "1.0",
        "portal": {"name": "t", "budget": {
            "daily": 600, "unit": "runs",
            "per_agent": {"codex": 100, "claude": 100, "agy": 100},
            "track": {"date": "", "spent": 0, "per_agent": {}},
        }},
        "tasks": tasks,
    }
    path.write_text(yaml.safe_dump(doc, sort_keys=False))


def _run(path: Path, *args: str) -> str:
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--tasks", str(path), *args],
        capture_output=True, text=True, timeout=60,
    )
    assert p.returncode == 0, p.stderr
    return p.stdout


def _count_generated(path: Path) -> int:
    doc = yaml.safe_load(path.read_text())
    return sum(1 for t in doc["tasks"] if str(t["id"]).startswith("GEN-"))


def test_noop_when_queue_healthy(tmp_path: Path):
    p = tmp_path / "tasks.yaml"
    _board(p, [f"o/r{i}" for i in range(5)], n_open_per_repo=20)  # 100 open
    out = _run(p, "--floor", "60", "--apply")
    assert "nothing to generate" in out
    assert _count_generated(p) == 0


def test_generates_up_to_floor_and_respects_cap(tmp_path: Path):
    p = tmp_path / "tasks.yaml"
    _board(p, [f"o/r{i}" for i in range(30)], n_open_per_repo=1)  # 30 open, 30 repos
    # floor 100 would want 70, but the cap must hold it to 10
    _run(p, "--floor", "100", "--max-new", "10", "--apply")
    assert _count_generated(p) == 10


def test_spreads_across_distinct_repos(tmp_path: Path):
    p = tmp_path / "tasks.yaml"
    _board(p, [f"o/r{i}" for i in range(20)], n_open_per_repo=1)
    _run(p, "--floor", "100", "--max-new", "12", "--apply")
    doc = yaml.safe_load(p.read_text())
    gen_repos = [t["repo"] for t in doc["tasks"] if str(t["id"]).startswith("GEN-")]
    assert len(gen_repos) == 12
    assert len(set(gen_repos)) == 12, "generated tasks must hit distinct repos, not pile on one"
