"""reclassify-needs-human CHRONIC bucket: a needs_human task that heal-dispatch stamped chronic
(reopened >=3x, never a PR) and that carries NO human marker parks failed_blocked on --apply —
never back to open (that re-run of the churn is the ping-pong that refilled the queue 154→406 in
13h on 2026-07-13). A human-marked task stays KEEP (needs_human) even when chronic; a genuinely
fleet-buildable, never-chronic task still FLIPs to open."""

import os
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "reclassify-needs-human.py"

_CHRONIC_LOG = [
    {
        "timestamp": "2026-07-13T00:00:00+00:00",
        "agent": "limen",
        "session_id": "heal",
        "status": "needs_human",
        "output": "heal-dispatch: chronic (reopened ≥3×, never a PR) → escalated, stop re-looping",
    }
]


def _task(tid, title, log=None):
    return {
        "id": tid,
        "title": title,
        "type": "code",
        "created": "2026-06-20T00:00:00+00:00",
        "status": "needs_human",
        "target_agent": "codex",
        "repo": "x/y",
        "dispatch_log": log or [],
    }


def _run(root, board, apply=True):
    (root / "tasks.yaml").write_text(yaml.safe_dump(board))
    env = dict(os.environ, LIMEN_ROOT=str(root), LIMEN_TASKS=str(root / "tasks.yaml"))
    argv = [sys.executable, str(SCRIPT)] + (["--apply"] if apply else [])
    r = subprocess.run(argv, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r, {t["id"]: t for t in yaml.safe_load((root / "tasks.yaml").read_text())["tasks"]}


def test_apply_parks_chronic_flips_buildable_keeps_human(tmp_path):
    board = {
        "tasks": [
            # chronic-stamped, no human marker → CHRONIC → failed_blocked (never open)
            _task("CHR1", "improve the readme", log=_CHRONIC_LOG),
            # chronic-stamped BUT human-marked → KEEP wins, stays needs_human
            _task("CHR-CRED", "blocked on the wrangler credential", log=_CHRONIC_LOG),
            # fleet-buildable, never chronic → FLIP → open
            _task("BUILD1", "write the landing page"),
        ]
    }
    _, out = _run(tmp_path, board)
    assert out["CHR1"]["status"] == "failed_blocked", out["CHR1"]
    assert "chronic-fleet-debt" in (out["CHR1"].get("labels") or []), out["CHR1"]
    assert out["CHR-CRED"]["status"] == "needs_human", out["CHR-CRED"]
    assert out["BUILD1"]["status"] == "open", out["BUILD1"]
    assert "reclassified-from-needs-human" in (out["BUILD1"].get("labels") or []), out["BUILD1"]


def test_dry_run_reports_chronic_and_changes_nothing(tmp_path):
    board = {"tasks": [_task("CHR1", "improve the readme", log=_CHRONIC_LOG)]}
    r, out = _run(tmp_path, board, apply=False)
    assert out["CHR1"]["status"] == "needs_human", out["CHR1"]  # dry-run mutates nothing
    assert "CHRONIC" in r.stdout and "failed_blocked" in r.stdout, r.stdout
    assert (tmp_path / "docs" / "RECLASSIFY-PROPOSAL.md").exists()
