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


def test_chronic_tasks_flags_reopened_without_pr(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    tasks = [
        {"id": "CH", "target_agent": "codex", "repo": "x/y",
         "dispatch_log": [{"status": "open"}, {"status": "open"}, {"status": "open"}]},
        {"id": "OK", "target_agent": "codex", "repo": "x/y",  # has a PR → not chronic
         "dispatch_log": [{"status": "open"}, {"status": "open"}, {"status": "open"},
                          {"session_id": "github.com/x/y/pull/1"}]},
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


def test_classification_includes_async_running_marker(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch)
    now = datetime.datetime.now(datetime.timezone.utc)
    old = (now - datetime.timedelta(hours=2)).isoformat()
    board = {"tasks": [
        {"id": "MERGED", "status": "dispatched", "target_agent": "codex", "repo": "x/y", "updated": old,
         "dispatch_log": [{"session_id": "https://github.com/x/y/pull/5"}]},
        {"id": "RUNNING_ASYNC", "status": "dispatched", "target_agent": "codex", "repo": "x/y",
         "updated": old, "dispatch_log": []},
        {"id": "STRANDED", "status": "dispatched", "target_agent": "codex", "repo": "x/y",
         "updated": old, "dispatch_log": []},
    ]}
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
    assert "STRANDED" in ids("DISPATCHED_NO_PR")         # old, no marker → genuinely stranded
