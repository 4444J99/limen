"""Tests for the value-ledger CREDIT side (score-dispatch.py).

Every resolved task is weighed: worth_it (shipped) / marginal (done, nothing shippable) / wasted
archived/no-op or chronic). Unresolved tasks (open/dispatched) are NOT yet weighable. The spent debit on a
wasted task is logged as sunk cost. These properties are what make the ledger an honest verdict.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "score-dispatch.py"


def _task(tid, status, *, pr=None, cost=1, attempts=1, reopens=0, agent="codex", repo="o/r", labels=None):
    log = []
    for _ in range(attempts):
        log.append({"status": "dispatched", "session_id": "x"})
    if pr:
        log.append({"status": "done", "session_id": f"https://github.com/{pr}"})
    for _ in range(reopens):
        log.append({"status": "open", "session_id": "reopened"})
    return {
        "id": tid,
        "title": tid,
        "repo": repo,
        "target_agent": agent,
        "priority": "medium",
        "budget_cost": cost,
        "status": status,
        "labels": labels or [],
        "created": "2026-06-01",
        "dispatch_log": log,
    }


def _run(tmp: Path, tasks: list[dict], *args: str) -> str:
    p = tmp / "tasks.yaml"
    p.write_text(yaml.safe_dump({"version": "1.0", "portal": {"name": "t"}, "tasks": tasks}))
    env = {**os.environ, "LIMEN_ROOT": str(tmp), "LIMEN_TASKS": str(p)}
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--tasks", str(p), *args], capture_output=True, text=True, timeout=60, env=env
    )
    assert r.returncode == 0, r.stderr
    return r.stdout


def _records(out: str) -> list[dict]:
    return [json.loads(ln) for ln in out.splitlines() if ln.startswith("{")]


def test_grades_each_resolved_class(tmp_path: Path):
    tasks = [
        _task("D-ship", "done", pr="o/r/pull/1"),  # worth_it
        _task("D-bare", "done"),  # marginal (no PR)
        _task("D-sup", "archived", labels=["superseded"]),  # marginal (folded)
        _task("D-cancel", "archived", attempts=2, cost=2, labels=["cancelled"]),  # wasted, sunk=4
        _task("D-open", "open"),  # NOT weighed
        _task("D-disp", "dispatched"),  # NOT weighed
    ]
    recs = {r["task_id"]: r for r in _records(_run(tmp_path, tasks, "--backfill", "--print"))}
    assert recs["D-ship"]["grade"] == "worth_it"
    assert recs["D-bare"]["grade"] == "marginal"
    assert recs["D-sup"]["grade"] == "marginal"
    assert recs["D-cancel"]["grade"] == "wasted"
    assert recs["D-cancel"]["sunk"] == 4, "wasted spend (cost 2 x 2 attempts) is logged as sunk"
    assert "D-open" not in recs and "D-disp" not in recs, "in-flight tasks are not yet weighable"


def test_chronic_needs_human_is_wasted(tmp_path: Path):
    tasks = [_task("CHRONIC", "needs_human", reopens=3, attempts=3)]
    recs = {r["task_id"]: r for r in _records(_run(tmp_path, tasks, "--backfill", "--print"))}
    assert recs["CHRONIC"]["grade"] == "wasted", "reopened >=3x, never a PR → wasted"
    assert recs["CHRONIC"]["sunk"] > 0


def test_chronic_failed_blocked_is_wasted_nonchronic_not_weighed(tmp_path: Path):
    # heal-dispatch now parks chronic fleet-debt in failed_blocked (off the human surface);
    # the sunk-cost accounting must follow it there. A genuinely externally-blocked task
    # (non-chronic) stays unweighed — it may still resolve.
    tasks = [
        _task("PARKED", "failed_blocked", reopens=3, attempts=3),
        _task("EXT", "failed_blocked", attempts=1),
    ]
    recs = {r["task_id"]: r for r in _records(_run(tmp_path, tasks, "--backfill", "--print"))}
    assert recs["PARKED"]["grade"] == "wasted", "chronic parked debt is sunk cost"
    assert recs["PARKED"]["sunk"] > 0
    assert "EXT" not in recs, "non-chronic failed_blocked is not yet weighable"


def test_idempotent_append(tmp_path: Path):
    tasks = [_task("D1", "done", pr="o/r/pull/9"), _task("D2", "archived", labels=["cancelled"])]
    _run(tmp_path, tasks)  # first pass appends 2
    out2 = _run(tmp_path, tasks)  # second pass: already scored → 0 new
    assert "0 newly-weighed" in out2
    lines = (tmp_path / "logs" / "ledger.jsonl").read_text().splitlines()
    assert len(lines) == 2, "no duplicate records on re-run"


def test_malformed_budget_cost_falls_back_per_task(tmp_path: Path):
    tasks = [
        _task("bad", "done", pr="o/r/pull/1", cost="bad"),
        _task("bool", "archived", cost=True, attempts=2, labels=["cancelled"]),
    ]
    recs = {r["task_id"]: r for r in _records(_run(tmp_path, tasks, "--backfill", "--print"))}

    assert recs["bad"]["budget_cost"] == 1
    assert recs["bad"]["spent"] == 1
    assert recs["bool"]["budget_cost"] == 1
    assert recs["bool"]["sunk"] == 2
