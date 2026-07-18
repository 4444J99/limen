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
# recover.py's old repeated-no-op escalation — the same fleet-debt class, historically routed to
# needs_human; the broadened predicate re-homes these stragglers too.
RECOVER_NOOP_EVIDENCE = "recover: repeated no-op failures (2) -> needs_human; stop fresh cascade"


def _task(tid, status, *, title=None, labels=None, log=None):
    return {
        "id": tid,
        "title": title or tid,
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


def test_successor_required_task_is_not_reclassified_by_stale_chronic_receipt(tmp_path):
    held = _task(
        "WORKSTREAM-SUCCESSOR",
        "failed",
        labels=["workstream:successor-required"],
        log=[_entry("open"), _entry("open"), _entry("open"), _entry("failed", "successor required")],
    )

    out = _run(tmp_path, [held], chronic_ids=["WORKSTREAM-SUCCESSOR"])

    task = out["WORKSTREAM-SUCCESSOR"]
    assert task["status"] == "failed"
    assert task["labels"] == ["workstream:successor-required"]
    assert [(entry["status"], entry["output"]) for entry in task["dispatch_log"]] == [
        (entry["status"], entry["output"]) for entry in held["dispatch_log"]
    ]


def test_jules_landing_hold_is_not_reopened_or_parked(tmp_path):
    dispatched = _task(
        "LANDING-DISPATCHED",
        "dispatched",
        labels=["jules:landing-held"],
        log=[_entry("dispatched")],
    )
    dispatched["target_agent"] = "jules"
    failed = _task(
        "LANDING-FAILED",
        "failed",
        labels=["jules:landing-held"],
        log=[_entry("failed")],
    )
    failed["target_agent"] = "jules"

    out = _run(
        tmp_path,
        [dispatched, failed],
        chronic_ids=["LANDING-DISPATCHED", "LANDING-FAILED"],
        detail={"DISPATCHED_NO_PR": [{"id": "LANDING-DISPATCHED"}]},
    )

    assert out["LANDING-DISPATCHED"]["status"] == "dispatched"
    assert out["LANDING-FAILED"]["status"] == "failed"
    for task in out.values():
        assert task["labels"] == ["jules:landing-held"]
        assert len(task["dispatch_log"]) == 1


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
    # the self-migration: current + legacy chronic strings AND recover.py's repeated-no-op string
    # (same fleet-debt class) all re-home off the human surface.
    out = _run(
        tmp_path,
        [
            _task("MIG1", "needs_human", log=[_entry("needs_human", CHRONIC_EVIDENCE)]),
            _task("MIG2", "needs_human", log=[_entry("needs_human", LEGACY_EVIDENCE)]),
            _task("MIG3", "needs_human", log=[_entry("needs_human", RECOVER_NOOP_EVIDENCE)]),
        ],
    )
    for tid in ("MIG1", "MIG2", "MIG3"):
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


def test_human_gated_chronic_stays_on_the_human_surface(tmp_path):
    # the ownership rule (shared _human_signals, same as reclassify): a chronic task carrying a
    # human marker is his hand — kept on / never re-homed off the human surface
    out = _run(
        tmp_path,
        [
            # freshly chronic from open, credential keyword in title → kept needs_human
            _task("HG1", "open", title="wire the wrangler credential", log=[_entry("open")]),
            # historical chronic escalation + human marker → NOT re-homed
            _task("HG2", "needs_human", title="rotate the oauth token", log=[_entry("needs_human", CHRONIC_EVIDENCE)]),
        ],
        chronic_ids=["HG1"],
    )
    assert out["HG1"]["status"] == "needs_human", out["HG1"]
    assert "chronic-fleet-debt" not in (out["HG1"].get("labels") or [])
    assert out["HG2"]["status"] == "needs_human", out["HG2"]


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


def test_chronic_active_receipt_owner_is_not_parked(tmp_path):
    """A failed chronic attempt with an active typed PR receipt owner is NOT parked.

    The active owner task is accountable for the leaf; the stale failed attempt is
    historical — parking it would incorrectly surface fleet-debt onto the human surface
    or loop a redundant path. The active-owner predicate is checked under the lock so a
    successor created after verification cannot be falsely parked.
    """
    root = tmp_path
    (root / "logs").mkdir()
    created = "2026-07-14T00:00:00+00:00"
    board = {
        "tasks": [
            {
                "id": "past-comet",
                "title": "historical failed attempt",
                "created": created,
                "status": "failed",
                "target_agent": "codex",
                "repo": "novel/harbor",
                "predicate": 'test "$(gh pr view 88 --repo novel/harbor --json state --jq .state)" = MERGED',
                "receipt_target": "https://github.com/novel/harbor/pull/88",
                "dispatch_log": [{"timestamp": created, "agent": "limen", "session_id": "retry", "status": "open"}],
            },
            {
                "id": "owner-lantern",
                "title": "current PR owner",
                "created": created,
                "status": "open",
                "type": "code",
                "target_agent": "any",
                "repo": "novel/harbor",
                "predicate": 'test "$(gh pr view 88 --repo novel/harbor --json state --jq .state)" != OPEN',
                "receipt_target": "github:NOVEL/harbor:pull-request:88",
                "dispatch_log": [],
            },
        ]
    }
    (root / "tasks.yaml").write_text(yaml.safe_dump(board))
    (root / "logs" / "dispatch-verify.json").write_text(
        json.dumps(
            {
                "counts": {"CHRONIC": 1},
                "detail": {},
                "chronic": [{"id": "past-comet", "agent": "codex", "reopens": 3, "repo": "novel/harbor"}],
            }
        )
    )
    env = dict(os.environ, LIMEN_ROOT=str(root), LIMEN_TASKS=str(root / "tasks.yaml"))

    result = subprocess.run([sys.executable, str(SCRIPT), "--apply"], env=env, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    out = {task["id"]: task for task in yaml.safe_load((root / "tasks.yaml").read_text())["tasks"]}
    assert out["past-comet"]["status"] == "failed", "active receipt owner protects the failed attempt"
    assert out["owner-lantern"]["status"] == "open", "owner task is left untouched"
    assert "0 chronic→parked" in result.stdout
