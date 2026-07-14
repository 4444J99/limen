"""Tests for the reconcile CLASSIFIER (scripts/verify-dispatch.py): the chronic-task detector and
the dispatched→{PR_MERGED,DISPATCHED_RUNNING,DISPATCHED_NO_PR} classification — including the
async-marker awareness (a live .running marker must classify as RUNNING, never reopened → no dup).
gh is mocked so no network."""

import datetime
import importlib.util
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify-dispatch.py"


def _load(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_LANE_TIMEOUT", "1")  # GRACE = 1+600s → 2h-old tasks aren't recency-RUNNING
    spec = importlib.util.spec_from_file_location("verify_dispatch_uut", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_malformed_lane_timeout_uses_default_grace(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_LANE_TIMEOUT", "not-an-int")
    spec = importlib.util.spec_from_file_location("verify_dispatch_bad_timeout", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    assert m.GRACE == 1500


def test_chronic_tasks_flags_reopened_without_pr(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    tasks = [
        {
            "id": "CH",
            "target_agent": "codex",
            "repo": "x/y",
            "dispatch_log": [{"status": "open"}, {"status": "open"}, {"status": "open"}],
        },
        {
            "id": "OK",
            "target_agent": "codex",
            "repo": "x/y",  # has a PR → not chronic
            "dispatch_log": [
                {"status": "open"},
                {"status": "open"},
                {"status": "open"},
                {"session_id": "github.com/x/y/pull/1"},
            ],
        },
        {"id": "NEW", "target_agent": "codex", "repo": "x/y", "dispatch_log": [{"status": "open"}]},
    ]
    assert [c[0] for c in m.chronic_tasks(tasks)] == ["CH"]


def test_chronic_tasks_excludes_inflight_dispatched_unless_no_pr_eligible(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    task = {
        "id": "ASYNC",
        "status": "dispatched",
        "target_agent": "jules",
        "repo": "x/y",
        "dispatch_log": [{"status": "open"}, {"status": "open"}, {"status": "open"}],
    }

    assert m.chronic_tasks([task]) == []
    assert [c[0] for c in m.chronic_tasks([task], eligible_dispatched_ids={"ASYNC"})] == ["ASYNC"]


def _failed_attempt(task_id="attempt-amber", receipt="https://github.com/Example/ledger/pull/731"):
    return {
        "id": task_id,
        "status": "failed",
        "target_agent": "codex",
        "repo": "Example/ledger",
        "receipt_target": receipt,
        "dispatch_log": [{"status": "open"}, {"status": "open"}, {"status": "open"}],
    }


def _typed_owner(
    task_id="owner-cobalt",
    *,
    status="open",
    receipt="github:example/LEDGER:pull-request:731",
):
    return {
        "id": task_id,
        "status": status,
        "type": "code",
        "target_agent": "any",
        "repo": "example/ledger",
        "predicate": 'test "$(gh pr view 731 --repo example/ledger --json state --jq .state)" != OPEN',
        "receipt_target": receipt,
        "dispatch_log": [],
    }


def test_chronic_tasks_suppresses_failed_attempt_with_active_typed_pr_owner(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    original = _failed_attempt("historical-raven")
    successor = _typed_owner("current-orchid")

    assert m.chronic_tasks([original, successor]) == []


def test_chronic_tasks_still_flags_failed_attempt_without_successor(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)

    assert [row[0] for row in m.chronic_tasks([_failed_attempt("unowned-raven")])] == ["unowned-raven"]


def test_chronic_tasks_still_flags_failed_attempt_with_wrong_receipt_owner(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    original = _failed_attempt("wrong-receipt-raven")
    successor = _typed_owner("wrong-receipt-orchid", receipt="https://github.com/example/ledger/pull/997")

    assert [row[0] for row in m.chronic_tasks([original, successor])] == ["wrong-receipt-raven"]


def test_chronic_tasks_still_flags_failed_attempt_with_terminal_successor(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    original = _failed_attempt("terminal-owner-raven")
    successor = _typed_owner("terminal-owner-orchid", status="done")

    assert [row[0] for row in m.chronic_tasks([original, successor])] == ["terminal-owner-raven"]


def test_chronic_tasks_still_flags_failed_attempt_with_untyped_successor(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    original = _failed_attempt("untyped-owner-raven")
    successor = _typed_owner("untyped-owner-orchid")
    successor.pop("predicate")

    assert [row[0] for row in m.chronic_tasks([original, successor])] == ["untyped-owner-raven"]


def test_classification_includes_async_running_marker(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    now = datetime.datetime.now(datetime.timezone.utc)
    old = (now - datetime.timedelta(hours=2)).isoformat()
    board = {
        "tasks": [
            {
                "id": "MERGED",
                "status": "dispatched",
                "target_agent": "codex",
                "repo": "x/y",
                "updated": old,
                "dispatch_log": [{"session_id": "https://github.com/x/y/pull/5"}],
            },
            {
                "id": "RUNNING_ASYNC",
                "status": "dispatched",
                "target_agent": "codex",
                "repo": "x/y",
                "updated": old,
                "dispatch_log": [],
            },
            {
                "id": "STRANDED",
                "status": "dispatched",
                "target_agent": "codex",
                "repo": "x/y",
                "updated": old,
                "dispatch_log": [],
            },
        ]
    }
    (tmp_path / "tasks.yaml").write_text(yaml.safe_dump(board))
    (tmp_path / "logs" / "async-runs").mkdir(parents=True)
    (tmp_path / "logs" / "async-runs" / "RUNNING_ASYNC__codex.running").write_text(now.isoformat())
    monkeypatch.setattr(m, "gh_pr_state", lambda o, r, n: (True, "MERGED"))
    monkeypatch.setattr(sys, "argv", ["verify-dispatch"])
    m.main()
    det = json.loads((tmp_path / "logs" / "dispatch-verify.json").read_text())["detail"]

    def ids(k):
        return [x["id"] for x in det.get(k, [])]

    assert "MERGED" in ids("PR_MERGED")
    assert "RUNNING_ASYNC" in ids("DISPATCHED_RUNNING")  # live .running marker → not reopened
    assert "STRANDED" in ids("DISPATCHED_NO_PR")  # old, no marker → genuinely stranded
