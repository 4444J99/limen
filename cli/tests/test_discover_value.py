"""Tests for the value-discovery organ.

discover-value.py runs autonomously in the heartbeat to ensure NO repo stays dark — every org repo
that isn't already ranked or under work gets exactly ONE discovery task. Its safety properties:
(1) it NO-OPs when enough discovery is already open (never floods),
(2) it emits ONE task per dark repo (never 6 busywork levers), round-robined across thinking lanes,
(3) it skips ranked repos (those have value already) and repos already under work,
(4) the headroom-scaled floor lifts coverage when the tank is full.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "discover-value.py"
_THINK = {"codex", "claude", "opencode"}


def _board(path: Path, busy_repos: list[str]) -> None:
    """A board where `busy_repos` already have an active task (so they're NOT dark)."""
    tasks = [
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
        for i, r in enumerate(busy_repos)
    ]
    path.write_text(yaml.safe_dump({"version": "1.0", "portal": {"name": "t"}, "tasks": tasks}, sort_keys=False))


def _run(
    path: Path,
    *args: str,
    org_repos: str = "",
    ranked: str = "",
    dispositions: list[dict] | None = None,
    headroom: str | None = None,
) -> str:
    disposition_path = path.parent / "value-discovery-dispositions.json"
    if dispositions is not None:
        disposition_path.write_text(
            json.dumps({"schema_version": "limen.value_discovery_dispositions.v1", "dispositions": dispositions}),
            encoding="utf-8",
        )
    env = {
        **os.environ,
        "LIMEN_ORGS": "",
        "LIMEN_ROOT": str(path.parent),
        "LIMEN_DISCOVER_REPOS": org_repos,
        "LIMEN_VALUE_REPOS": ranked,
        "LIMEN_VALUE_REPOS_FILE": str(path.parent / "no-such-tier.json"),
        "LIMEN_VALUE_DISCOVERY_DISPOSITIONS_FILE": str(disposition_path),
    }
    if headroom is not None:
        (path.parent / "logs").mkdir(exist_ok=True)
        vendors = {"codex": {"headroom_pct": int(headroom), "reserve_pct": 15}}
        (path.parent / "logs" / "usage.json").write_text(json.dumps({"vendors": vendors}))
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--tasks", str(path), *args], capture_output=True, text=True, timeout=60, env=env
    )
    assert p.returncode == 0, p.stderr
    return p.stdout


def _generated(path: Path) -> list[dict]:
    doc = yaml.safe_load(path.read_text()) or {}
    return [t for t in doc.get("tasks", []) if str(t["id"]).startswith("DISCOVER-")]


def test_one_task_per_dark_repo_on_think_lanes(tmp_path: Path):
    p = tmp_path / "tasks.yaml"
    _board(p, busy_repos=[])  # nothing busy → all org repos are dark
    org = [f"o/dark{i}" for i in range(8)]
    _run(p, "--apply", "--floor", "8", "--max-new", "8", org_repos=",".join(org))
    gen = _generated(p)
    assert len(gen) == 8, "one discovery task per dark repo"
    assert {t["repo"] for t in gen} == set(org), "exactly the dark repos, each once"
    assert all(t["target_agent"] in _THINK for t in gen), "discovery routes to thinking lanes"
    assert all(t["labels"][0] == "discover" for t in gen)


def test_skips_ranked_and_busy(tmp_path: Path):
    p = tmp_path / "tasks.yaml"
    _board(p, busy_repos=["o/busy"])  # o/busy already has work
    org = ["o/busy", "o/ranked", "o/dark"]
    _run(
        p, "--apply", "--floor", "8", "--max-new", "8", org_repos=",".join(org), ranked="o/ranked"
    )  # o/ranked has discovered value
    repos = {t["repo"] for t in _generated(p)}
    assert repos == {"o/dark"}, f"only the dark repo gets discovery, got {repos}"


def test_skips_durable_ranked_and_archival_dispositions(tmp_path: Path):
    p = tmp_path / "tasks.yaml"
    _board(p, busy_repos=[])
    org = ["o/ranked-decision", "o/archival-decision", "o/malformed-decision", "o/dark"]
    dispositions = [
        {"repo": "o/ranked-decision", "disposition": "ranked", "receipt": "https://github.com/o/r/pull/1"},
        {"repo": "o/archival-decision", "disposition": "archival", "receipt": "https://github.com/o/r/pull/2"},
        {"repo": "o/malformed-decision", "disposition": "maybe", "receipt": "https://github.com/o/r/pull/3"},
    ]

    _run(
        p,
        "--apply",
        "--floor",
        "8",
        "--max-new",
        "8",
        org_repos=",".join(org),
        ranked="o/ranked-decision",
        dispositions=dispositions,
    )

    repos = {task["repo"] for task in _generated(p)}
    assert repos == {"o/malformed-decision", "o/dark"}


def test_malformed_or_duplicate_dispositions_fail_open(tmp_path: Path):
    p = tmp_path / "tasks.yaml"
    _board(p, busy_repos=[])
    org = ["o/valid-archive", "o/duplicate", "o/mixed-duplicate", "o/no-receipt"]
    dispositions = [
        {"repo": "o/valid-archive", "disposition": "archival", "receipt": "github:o/r:pull-request:1"},
        {"repo": "o/duplicate", "disposition": "archival", "receipt": "github:o/r:pull-request:2"},
        {"repo": "o/duplicate", "disposition": "archival", "receipt": "github:o/r:pull-request:3"},
        {"repo": "o/mixed-duplicate", "disposition": "archival", "receipt": "github:o/r:pull-request:4"},
        {"repo": "o/mixed-duplicate", "disposition": "maybe", "receipt": "github:o/r:pull-request:5"},
        {"repo": "o/no-receipt", "disposition": "archival", "receipt": ""},
    ]

    _run(
        p,
        "--apply",
        "--floor",
        "8",
        "--max-new",
        "8",
        org_repos=",".join(org),
        dispositions=dispositions,
    )

    assert {task["repo"] for task in _generated(p)} == {"o/duplicate", "o/mixed-duplicate", "o/no-receipt"}


def test_partial_receipt_prefixes_fail_open(tmp_path: Path):
    p = tmp_path / "tasks.yaml"
    _board(p, busy_repos=[])
    receipts = {
        "o/bare-github": "https://github.com/",
        "o/partial-github": "https://github.com/not-a-receipt",
        "o/bare-git": "git:",
        "o/partial-git": "git:not-a-durable-target",
    }
    dispositions = [{"repo": repo, "disposition": "archival", "receipt": receipt} for repo, receipt in receipts.items()]

    _run(
        p,
        "--apply",
        "--floor",
        "8",
        "--max-new",
        "8",
        org_repos=",".join(receipts),
        dispositions=dispositions,
    )

    assert {task["repo"] for task in _generated(p)} == set(receipts)


def test_noop_when_discovery_floor_met(tmp_path: Path):
    p = tmp_path / "tasks.yaml"
    # pre-seed the floor with open DISCOVER- tasks
    tasks = [
        {
            "id": f"DISCOVER-o-r{i}",
            "title": "d",
            "repo": f"o/r{i}",
            "target_agent": "codex",
            "priority": "medium",
            "budget_cost": 1,
            "status": "open",
            "created": "2026-06-01",
            "dispatch_log": [],
        }
        for i in range(12)
    ]
    p.write_text(yaml.safe_dump({"version": "1.0", "portal": {"name": "t"}, "tasks": tasks}, sort_keys=False))
    out = _run(
        p,
        "--apply",
        "--floor",
        "12",
        "--max-new",
        "12",
        org_repos=",".join(f"o/new{i}" for i in range(5)),
        headroom="10",
    )  # low tank → no scale-up
    assert "discovery healthy" in out
    assert len([t for t in _generated(p) if t["repo"].startswith("o/new")]) == 0


def test_headroom_scales_floor_up(tmp_path: Path):
    p = tmp_path / "tasks.yaml"
    _board(p, busy_repos=[])
    org = [f"o/d{i}" for i in range(40)]
    # base floor 10, full tank (headroom 100) → floor scales to 3x = 30, capped by max-new 30
    out = _run(p, "--apply", "--floor", "10", "--max-new", "30", org_repos=",".join(org), headroom="100")
    assert "floor=30" in out, out
    assert len(_generated(p)) == 30
