from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "assemble-dashboard-data.py"
SPEC = importlib.util.spec_from_file_location("assemble_dashboard_data", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def event(index: int) -> dict[str, str]:
    return {
        "timestamp": f"2026-07-22T20:{index:02d}:00Z",
        "agent": "codex",
        "session_id": f"session-{index}",
        "status": "in_progress",
        "output": "x" * 180,
    }


def task(index: int, *, status: str = "open") -> dict[str, object]:
    return {
        "id": f"DASH-{index:04d}",
        "title": f"Dashboard fixture {index}",
        "repo": "organvm/limen",
        "target_agent": "codex",
        "priority": "medium",
        "budget_cost": 1,
        "status": status,
        "context": "c" * 450,
        "dispatch_log": [event(1), event(3), event(2)],
    }


def test_high_cardinality_dashboard_stays_below_ratchet_with_latest_log(tmp_path: Path) -> None:
    app = tmp_path / "web" / "app"
    generated = app / ".generated" / "surfaces"
    generated.mkdir(parents=True)
    policy = json.loads((ROOT / "web" / "app" / "dashboard-export-policy.json").read_text(encoding="utf-8"))
    (app / "dashboard-export-policy.json").write_text(json.dumps(policy), encoding="utf-8")
    (generated / "internal-status.json").write_text(
        json.dumps({"portal": {}, "summary": {"generated_at": "2026-07-22T20:00:00Z"}, "storage": {}}),
        encoding="utf-8",
    )
    tasks = [task(index) for index in range(1_250)] + [task(9_999, status="done")]
    (generated / "tasks.json").write_text(json.dumps({"tasks": tasks}), encoding="utf-8")

    result = MODULE.assemble(app, repo_root=tmp_path, write_public=True)

    assert result["max_dispatch_log_entries"] == 1
    assert result["dashboard_bytes"] < result["max_dashboard_bytes"]
    prior_dashboard, _ = MODULE.payloads(
        internal={"summary": {}},
        task_document={"tasks": tasks},
        policy={**policy, "max_dispatch_log_entries": 3},
    )
    assert len(MODULE.encoded(prior_dashboard)) > result["max_dashboard_bytes"]
    dashboard = json.loads((app / "out" / "dashboard.json").read_text(encoding="utf-8"))
    assert len(dashboard["tasks"]) == 1_250
    assert [entry["session_id"] for entry in dashboard["tasks"][0]["dispatch_log"]] == ["session-3"]
    done = json.loads((app / "public" / "done-tasks.json").read_text(encoding="utf-8"))
    assert done["total_done"] == 1
    assert done["tasks"][0]["id"] == "DASH-9999"


def test_invalid_policy_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "dashboard-export-policy.json").write_text(
        json.dumps({"schema_version": "limen.dashboard-export-policy.v1", "max_dispatch_log_entries": -1}),
        encoding="utf-8",
    )
    try:
        MODULE.load_policy(tmp_path)
    except ValueError as error:
        assert "max_dispatch_log_entries" in str(error)
    else:
        raise AssertionError("invalid dashboard export policy was accepted")


def test_dashboard_consumers_share_the_checked_in_policy() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    refresh = (ROOT / "scripts" / "refresh-web.sh").read_text(encoding="utf-8")
    verify_whole = (ROOT / "scripts" / "verify-whole.sh").read_text(encoding="utf-8")
    gates = (ROOT / "institutio" / "governance" / "gates.yaml").read_text(encoding="utf-8")
    generator = (ROOT / "web" / "app" / "scripts" / "generate-static-data.mjs").read_text(encoding="utf-8")
    validator = (ROOT / "web" / "app" / "scripts" / "validate-exported-pages.mjs").read_text(encoding="utf-8")
    assert "scripts/assemble-dashboard-data.py --app web/app" in workflow
    assert "scripts/assemble-dashboard-data.py --app web/app" in ci
    assert "assemble-dashboard-data.py" in refresh
    assert "assemble-dashboard-data.py" in verify_whole
    assert "scripts/assemble-dashboard-data.py" in gates
    assert "scripts/tests/test_assemble_dashboard_data.py" in gates
    assert ci.index("scripts/assemble-dashboard-data.py") < ci.index("validate-exported-pages.mjs")
    assert verify_whole.index("assemble-dashboard-data.py") < verify_whole.index("validate-exported-pages.mjs")
    assert gates.index("scripts/assemble-dashboard-data.py --app web/app") < gates.index(
        "web/app/scripts/validate-exported-pages.mjs"
    )
    assert "dashboard-export-policy.json" in generator
    assert "dashboard-export-policy.json" in validator
    for source in (workflow, ci, refresh, verify_whole, gates, generator, validator):
        assert "MAX_LOG = 3" not in source
        assert "dispatch_log<=3" not in source
