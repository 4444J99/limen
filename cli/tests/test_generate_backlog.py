"""Tests for the self-feeding backlog generator.

generate-backlog.py runs autonomously in the heartbeat, so its safety properties matter:
(1) it must NO-OP when the queue is healthy (never flood a full queue),
(2) it must respect the max-new anti-flood cap,
(3) when it does generate, it spreads across DISTINCT repos (no repo gets dumped on).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from limen.tabularius import drain_once

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "generate-backlog.py"


def _board(path: Path, repos: list[str], n_open_per_repo: int = 1) -> None:
    tasks = []
    i = 0
    for r in repos:
        for _ in range(n_open_per_repo):
            i += 1
            tasks.append(
                {
                    "id": f"SEED-{i}",
                    "title": f"seed {i}",
                    "repo": r,
                    "target_agent": "codex",
                    "priority": "medium",
                    "budget_cost": 1,
                    "status": "open",
                    "created": "2026-06-01",
                    "dispatch_log": [],
                }
            )
    doc = {
        "version": "1.0",
        "portal": {
            "name": "t",
            "budget": {
                "daily": 600,
                "unit": "runs",
                "per_agent": {"codex": 100, "claude": 100, "agy": 100},
                "track": {"date": "", "spent": 0, "per_agent": {}},
            },
        },
        "tasks": tasks,
    }
    path.write_text(yaml.safe_dump(doc, sort_keys=False))


def _run(
    path: Path,
    *args: str,
    value_repos: str | None = None,
    worktree_root: Path | None = None,
) -> str:
    # LIMEN_ORGS="" disables the live-org repo source so the test is deterministic against the
    # repos in its temp tasks.yaml (the generator falls back to the queue set when no org is given).
    # value-tier gate: by default allow exactly the repos on the board (so floor/cap/spread logic is
    # exercised); pass value_repos="" to test the fail-closed (no-tier) path.
    if value_repos is None:
        doc = yaml.safe_load(path.read_text()) or {}
        value_repos = ",".join(sorted({t["repo"] for t in doc.get("tasks", []) if t.get("repo")}))
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--tasks", str(path), *args],
        capture_output=True,
        text=True,
        timeout=60,
        # LIMEN_ORGS="" → no live-org source; LIMEN_ROOT=tmp → _down_lanes finds no usage.json,
        # so the routable-open floor count == total open (deterministic, no real lane-health bleed).
        env={
            **os.environ,
            "LIMEN_ORGS": "",
            "LIMEN_ROOT": str(path.parent),
            "LIMEN_DISPATCH_LANES": "codex,claude,agy",
            "LIMEN_VALUE_REPOS": value_repos,
            "LIMEN_VALUE_REPOS_FILE": str(path.parent / "no-such-tier.json"),
            "LIMEN_WORKTREE_ROOT": str(worktree_root or path.parent / "empty-worktrees"),
            # Pin the gate flag so tests are hermetic against LIMEN_WORKTREE_DEBT_GATE=0
            # leaking in from test_async_dispatch._load() when the suite runs together.
            "LIMEN_WORKTREE_DEBT_GATE": "1",
        },
    )
    assert p.returncode == 0, p.stderr
    if "--apply" in args:
        # Producers submit immutable tickets; the keeper owns the canonical
        # transition and only then refreshes this isolated test projection.
        drained = drain_once(path)
        assert not drained.deferred, drained.note
        assert drained.rejected == 0, drained.note
    return p.stdout


def _count_generated(path: Path) -> int:
    doc = yaml.safe_load(path.read_text())
    return sum(1 for t in doc["tasks"] if str(t["id"]).startswith("GEN-"))


def test_census_is_counts_only(tmp_path: Path):
    p = tmp_path / "tasks.yaml"
    p.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "portal": {"name": "t"},
                "tasks": [
                    {
                        "id": "SECRET-FEED-1",
                        "title": "confidential launch task",
                        "repo": "secret-owner/private-repo",
                        "type": "code",
                        "target_agent": "codex",
                        "priority": "medium",
                        "budget_cost": 1,
                        "status": "open",
                        "labels": ["test-coverage", "secret-label", "generated", "build-out"],
                        "context": "private customer context",
                        "created": "2026-06-01",
                        "dispatch_log": [],
                    }
                ],
            },
            sort_keys=False,
        )
    )

    census = json.loads(_run(p, "--census"))
    encoded = json.dumps(census, sort_keys=True)

    assert census["tasks_present"] is True
    assert census["tasks_readable"] is True
    assert census["task_count"] == 1
    assert census["status_counts"] == {"open": 1}
    assert census["value_tier_count"] == 1
    assert census["generated_buildout_count"] == 1
    assert census["worktree_debt_count"] == 0
    assert census["worktree_debt_complete"] is True
    assert "worktree_debt_limit" not in census
    assert "worktree_debt_exceeded" not in census
    assert "SECRET-FEED-1" not in encoded
    assert "confidential" not in encoded
    assert "secret-owner" not in encoded
    assert "private-repo" not in encoded
    assert "secret-label" not in encoded
    assert "private customer" not in encoded


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


def test_value_tier_gate_fail_closed_and_filters(tmp_path: Path):
    # No ranked tier → generate NO build-out levers (anti-flood: never dump levers on every repo).
    # NOT starvation: dark repos get a DISCOVERY task from discover-value.py, so the message points
    # there instead of dead-ending. ([[distillation-not-reduction]])
    p = tmp_path / "tasks.yaml"
    _board(p, [f"o/r{i}" for i in range(20)], n_open_per_repo=1)
    out = _run(p, "--floor", "100", "--max-new", "12", "--apply", value_repos="")
    assert "discover-value" in out
    assert _count_generated(p) == 0

    # Tier set to ONE repo → generation only for that repo, never the others.
    p2 = tmp_path / "tasks2.yaml"
    _board(p2, [f"o/r{i}" for i in range(20)], n_open_per_repo=1)
    _run(p2, "--floor", "100", "--max-new", "12", "--apply", value_repos="o/r3")
    doc = yaml.safe_load(p2.read_text())
    gen_repos = {t["repo"] for t in doc["tasks"] if str(t["id"]).startswith("GEN-")}
    assert gen_repos == {"o/r3"}, f"gate leaked to non-tier repos: {gen_repos}"


def test_high_legacy_debt_does_not_scan_or_stop_normal_generation(tmp_path: Path):
    # Normal feed must not classify the estate at all. The explicit --census surface owns that
    # diagnostic; per-task admission owns launch safety. A worktree inventory here used to cost
    # roughly 51 seconds on the live estate before the generator even checked the queue floor.
    p = tmp_path / "tasks.yaml"
    _board(p, [f"o/r{i}" for i in range(20)], n_open_per_repo=1)
    debt_root = tmp_path / "debt"
    for i in range(7):  # arbitrary nonzero debt (non-git residue roots), never 12
        (debt_root / f"residue-{i}").mkdir(parents=True)

    out = _run(
        p,
        "--floor",
        "100",
        "--max-new",
        "12",
        "--apply",
        worktree_root=debt_root,
    )

    # No hot-path diagnostic scan/output, and no kill switch — generation continues to the cap.
    assert "lifecycle debt diagnostic" not in out
    assert "lifecycle debt gate" not in out
    assert _count_generated(p) == 12
