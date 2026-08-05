"""route.py must tolerate torn writes without claiming local projection authority.

A recurring corruption writes a whole Task object into some task's dispatch_log (an entry missing
timestamp/agent/session_id). Before the fix, route.py read tasks.yaml with raw yaml.safe_load and
spammed a pydantic "Field required" trace. route.py now reads through the resilient loader for its
decision snapshot. TABVLARIVS owns the canonical projection, so route never rewrites the local cache
merely to heal malformed source bytes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "route.py"


def _board_with_torn_write(path: Path) -> None:
    tasks = [
        {
            "id": "SEED-1",
            "title": "seed",
            "repo": "o/r1",
            "target_agent": "codex",
            "priority": "medium",
            "budget_cost": 1,
            "status": "open",
            "created": "2026-06-01",
            "dispatch_log": [
                {"timestamp": "2026-06-01T00:00:00", "agent": "codex", "session_id": "s1", "status": "dispatched"},
                # the torn write: a whole Task dict landed INSIDE the dispatch_log
                {"id": "GEN-x", "title": "garbage", "repo": "o/r1", "status": "open"},
            ],
        },
    ]
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


def _run(path: Path, *args: str) -> subprocess.CompletedProcess:
    # LIMEN_ROOT=tmp -> no real usage.json/lanes bleed; LIMEN_DISPATCH_LANES=codex keeps probing bounded.
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--tasks", str(path), *args],
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "LIMEN_ORGS": "", "LIMEN_ROOT": str(path.parent), "LIMEN_DISPATCH_LANES": "codex"},
    )


def test_route_tolerates_torn_write_dry_run(tmp_path: Path):
    p = tmp_path / "tasks.yaml"
    _board_with_torn_write(p)
    r = _run(p)
    assert r.returncode == 0, r.stderr
    assert "Field required" not in r.stderr, f"pydantic trace leaked: {r.stderr}"
    assert "tolerated 1 malformed" in r.stderr


def test_route_apply_is_retired_without_touching_torn_cache(tmp_path: Path):
    p = tmp_path / "tasks.yaml"
    _board_with_torn_write(p)
    before = p.read_bytes()
    r = _run(p, "--apply")
    assert r.returncode == 2
    assert "Field required" not in r.stderr
    assert "--apply is retired" in r.stderr
    assert p.read_bytes() == before
