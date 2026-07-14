"""heal-dispatch chronic parking: a chronic task (reopened >=3x, never a PR — surfaced by
verify-dispatch into dispatch-verify.json) is FLEET-debt, not a human atom — it parks in
`failed_blocked` (which nothing recycles), never `needs_human` (the human surface). A task the
machine previously escalated to needs_human for chronic churn is re-homed the same way on the
next pass (self-migration via the log-evidence predicate — this is how the historical cohort
drains without a one-shot script). The exact `needs-human` label is the his-hand opt-out.
Reversible status flips; non-chronic tasks are left untouched."""

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "heal-dispatch.py"
CREATED = "2026-06-20T00:00:00+00:00"

# the evidence strings historical escalations wrote (current heal-dispatch + the legacy manual one)
CHRONIC_EVIDENCE = "heal-dispatch: chronic (reopened ≥3×, never a PR) → escalated, stop re-looping"
LEGACY_EVIDENCE = "chronic (reopened >=3x, never a PR, fails all lanes) -> escalated out of dispatch loop"


def _task(tid, status, *, labels=None, log=None):
    return {
        "id": tid,
        "title": tid,
        "created": CREATED,
        "status": status,
        "target_agent": "codex",
        "repo": "x/y",
        "labels": labels or [],
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


def _run(root, tasks, *, chronic_ids=(), detail=None):
    (root / "logs").mkdir(exist_ok=True)
    (root / "tasks.yaml").write_text(yaml.safe_dump({"tasks": tasks}))
    (root / "logs" / "dispatch-verify.json").write_text(
        json.dumps(
            {
                "counts": {},
                "detail": detail or {},
                "chronic": [{"id": i, "agent": "codex", "reopens": 3, "repo": "x/y"} for i in chronic_ids],
            }
        )
    )
    env = dict(os.environ, LIMEN_ROOT=str(root), LIMEN_TASKS=str(root / "tasks.yaml"))
    r = subprocess.run([sys.executable, str(SCRIPT), "--apply"], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return {t["id"]: t for t in yaml.safe_load((root / "tasks.yaml").read_text())["tasks"]}


def test_chronic_open_task_parks_in_failed_blocked(tmp_path):
    out = _run(
        tmp_path,
        [_task("CHRONIC1", "open", log=[_entry("open")]), _task("FRESH1", "open")],
        chronic_ids=["CHRONIC1"],
    )
    assert out["CHRONIC1"]["status"] == "failed_blocked", out["CHRONIC1"]
    assert "chronic-fleet-debt" in out["CHRONIC1"]["labels"]
    assert out["FRESH1"]["status"] == "open", "non-chronic untouched"


def test_chronic_dispatched_no_pr_parks(tmp_path):
    out = _run(
        tmp_path,
        [_task("CHRONIC2", "dispatched", log=[_entry("dispatched")])],
        chronic_ids=["CHRONIC2"],
        detail={"DISPATCHED_NO_PR": [{"id": "CHRONIC2"}]},
    )
    assert out["CHRONIC2"]["status"] == "failed_blocked", out["CHRONIC2"]
    assert "chronic-fleet-debt" in out["CHRONIC2"]["labels"]


def test_needs_human_with_chronic_evidence_is_rehomed(tmp_path):
    # the self-migration: both the current evidence string and the legacy variant re-home
    out = _run(
        tmp_path,
        [
            _task("MIG1", "needs_human", log=[_entry("needs_human", CHRONIC_EVIDENCE)]),
            _task("MIG2", "needs_human", log=[_entry("needs_human", LEGACY_EVIDENCE)]),
        ],
    )
    for tid in ("MIG1", "MIG2"):
        assert out[tid]["status"] == "failed_blocked", out[tid]
        assert "chronic-fleet-debt" in out[tid]["labels"]


def test_needs_human_human_authored_is_untouched(tmp_path):
    # a human (or any non-chronic writer) parked it — that decision wins
    out = _run(
        tmp_path,
        [_task("HIS1", "needs_human", log=[_entry("needs_human", "operator: hold for my review")])],
    )
    assert out["HIS1"]["status"] == "needs_human", out["HIS1"]
    assert "chronic-fleet-debt" not in out["HIS1"]["labels"]


def test_needs_human_label_is_the_his_hand_opt_out(tmp_path):
    out = _run(
        tmp_path,
        [
            # labeled + chronic evidence: never re-homed off the human surface
            _task(
                "LBL1",
                "needs_human",
                labels=["needs-human"],
                log=[_entry("needs_human", CHRONIC_EVIDENCE)],
            ),
            # labeled + freshly chronic from open: parks ON the human surface (kept)
            _task("LBL2", "open", labels=["needs-human"], log=[_entry("open")]),
        ],
        chronic_ids=["LBL2"],
    )
    assert out["LBL1"]["status"] == "needs_human", out["LBL1"]
    assert out["LBL2"]["status"] == "needs_human", out["LBL2"]
    assert "chronic-fleet-debt" not in out["LBL2"]["labels"]
    # the "kept" write must never look like a machine escalation to the re-home predicate
    assert "escalat" not in out["LBL2"]["dispatch_log"][-1]["output"]


def test_second_pass_is_a_fixed_point(tmp_path):
    tasks = [
        _task("CHRONIC1", "open", log=[_entry("open")]),
        _task("MIG1", "needs_human", log=[_entry("needs_human", CHRONIC_EVIDENCE)]),
    ]
    _run(tmp_path, tasks, chronic_ids=["CHRONIC1"])
    first = (tmp_path / "tasks.yaml").read_text()
    # second --apply run: parked tasks are neither open/failed nor needs_human → nothing matches
    env = dict(os.environ, LIMEN_ROOT=str(tmp_path), LIMEN_TASKS=str(tmp_path / "tasks.yaml"))
    r = subprocess.run([sys.executable, str(SCRIPT), "--apply"], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "tasks.yaml").read_text() == first, "re-run must change nothing (idempotent)"
