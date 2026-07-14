"""reclassify-needs-human classification: chronic fleet-debt (machine-escalated, evidence in the
dispatch_log) is REPORT-ONLY — never flipped back to open. Flipping it was one leg of the
reclassify<->heal-dispatch oscillation (flip to open at 13:45, re-escalated 15:02 the same day);
heal-dispatch owns the chronic write (re-homes to failed_blocked). A plain fleet-buildable code
task still FLIPs — the drain keeps working for genuinely mis-parked work."""

import os
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "reclassify-needs-human.py"
CREATED = "2026-06-20T00:00:00+00:00"

CHRONIC_EVIDENCE = "heal-dispatch: chronic (reopened ≥3×, never a PR) → escalated, stop re-looping"
LEGACY_EVIDENCE = "chronic (reopened >=3x, never a PR, fails all lanes) -> escalated out of dispatch loop"


def _task(tid, *, log=None):
    return {
        "id": tid,
        "title": f"{tid} build the docs page",
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


def test_chronic_is_report_only_and_plain_code_still_flips(tmp_path):
    tasks = [
        _task("CHR1", log=[_entry("needs_human", CHRONIC_EVIDENCE)]),
        _task("CHR2", log=[_entry("needs_human", LEGACY_EVIDENCE)]),
        _task("FLIP1"),
    ]
    out, board = _run(tmp_path, tasks, apply=True)
    # chronic tasks are bucketed CHRONIC and --apply never touches them
    assert "CHRONIC" in out
    assert board["CHR1"]["status"] == "needs_human", board["CHR1"]
    assert board["CHR2"]["status"] == "needs_human", board["CHR2"]
    # the drain still works for genuinely mis-parked fleet-buildable work
    assert board["FLIP1"]["status"] == "open", board["FLIP1"]


def test_chronic_wins_over_noisy_human_keywords(tmp_path):
    # many chronic bodies carry credential-cluster keywords; the machine parked them, so they
    # must report CHRONIC (what heal-dispatch will actually do), not KEEP
    t = _task("CHR3", log=[_entry("needs_human", CHRONIC_EVIDENCE)])
    t["title"] = "CHR3 wire the billing account token"
    out, board = _run(tmp_path, [t])
    assert "CHRONIC  1" in out.replace("\n", " ") or "CHRONIC" in out
    assert "KEEP    1" not in out
    assert board["CHR3"]["status"] == "needs_human"
