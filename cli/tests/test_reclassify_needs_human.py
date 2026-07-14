"""reclassify-needs-human chronic handling under the OWNERSHIP rule (shared _human_signals):
a machine-escalated chronic task with no human marker parks failed_blocked on --apply — never
back to open (the flip-to-open leg of the reclassify<->heal-dispatch oscillation that refilled
the queue 154→406 in 13h). A human-marked task stays KEEP even when chronic. Covers the three
legacy pre-heal-dispatch escalation strings the `heal-dispatch:`-prefixed match would miss."""

import os
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "reclassify-needs-human.py"
CREATED = "2026-06-20T00:00:00+00:00"

CHRONIC_EVIDENCE = "heal-dispatch: chronic (reopened ≥3×, never a PR) → escalated, stop re-looping"
LEGACY_EVIDENCE = "chronic (reopened >=3x, never a PR, fails all lanes) -> escalated out of dispatch loop"


def _task(tid, *, title=None, log=None):
    return {
        "id": tid,
        "title": title or f"{tid} build the docs page",
        "created": CREATED,
        "status": "needs_human",
        "type": "code",
        "target_agent": "codex",
        "repo": "x/y",
        "labels": [],
        "dispatch_log": log or [],
    }


def _entry(status, output=""):
    return {
        "timestamp": "2026-06-21T00:00:00+00:00",
        "agent": "limen",
        "session_id": "heal",
        "status": status,
        "output": output,
    }


def _run(root, tasks, *, apply=False):
    path = root / "tasks.yaml"
    path.write_text(yaml.safe_dump({"tasks": tasks}))
    env = dict(os.environ, LIMEN_ROOT=str(root), LIMEN_TASKS=str(path))
    args = [sys.executable, str(SCRIPT), "--tasks", str(path)] + (["--apply"] if apply else [])
    r = subprocess.run(args, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout, {t["id"]: t for t in yaml.safe_load(path.read_text())["tasks"]}


def test_apply_parks_chronic_including_legacy_strings_and_still_flips_buildable(tmp_path):
    tasks = [
        _task("CHR1", log=[_entry("needs_human", CHRONIC_EVIDENCE)]),
        _task("CHR2", log=[_entry("needs_human", LEGACY_EVIDENCE)]),  # legacy wording still counts
        _task("FLIP1"),
    ]
    out, board = _run(tmp_path, tasks, apply=True)
    assert "CHRONIC" in out
    for tid in ("CHR1", "CHR2"):
        assert board[tid]["status"] == "failed_blocked", board[tid]
        assert "chronic-fleet-debt" in board[tid]["labels"], board[tid]
    # the drain still works for genuinely mis-parked fleet-buildable work
    assert board["FLIP1"]["status"] == "open", board["FLIP1"]


def test_human_marked_chronic_stays_keep(tmp_path):
    # ownership wins over chronic history (shared _human_signals rule, matching heal-dispatch):
    # a chronic task carrying a human marker stays on the human surface, untouched by --apply
    t = _task("CHR3", title="CHR3 wire the billing account token", log=[_entry("needs_human", CHRONIC_EVIDENCE)])
    out, board = _run(tmp_path, [t], apply=True)
    assert board["CHR3"]["status"] == "needs_human", board["CHR3"]
    assert "chronic-fleet-debt" not in (board["CHR3"].get("labels") or [])


def test_human_parked_after_chronic_is_not_treated_as_chronic(tmp_path):
    # last-entry-wins: a human deliberately re-parking a once-chronic task overrides the machine
    # stamp, so it is NOT parked failed_blocked as chronic. With no human marker it classifies as
    # ordinary fleet-buildable work and FLIPs to open — the sanctioned drain, not the chronic park.
    t = _task(
        "HIS1",
        log=[
            _entry("needs_human", CHRONIC_EVIDENCE),
            _entry("open", "operator: reopened for a fresh try"),
            _entry("needs_human", "operator: hold for my review"),
        ],
    )
    out, board = _run(tmp_path, [t], apply=True)
    assert board["HIS1"]["status"] == "open", board["HIS1"]
    assert "chronic-fleet-debt" not in (board["HIS1"].get("labels") or [])
    assert "reclassified-from-needs-human" in board["HIS1"]["labels"]
