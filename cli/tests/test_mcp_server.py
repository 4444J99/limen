import importlib.util
import sys
from pathlib import Path

import pytest
import yaml


def _load_server():
    # The mcp server imports the `mcp` runtime package (mcp.server.fastmcp). Core CI installs only
    # cli[test], not the mcp/ package (it lints/compiles/type-checks the mcp source with
    # --ignore-missing-imports but never installs its runtime), so skip rather than fail the whole
    # suite when the runtime is absent — this test only means something where mcp is installed.
    pytest.importorskip("mcp.server.fastmcp")
    # server.py imports its own package absolutely (`from limen_mcp.intake import …`), so the repo's
    # mcp/src must be importable even when limen_mcp isn't pip-installed — otherwise this test FAILS
    # (not skips) on any host that has the `mcp` runtime but not the limen_mcp package: the skip
    # guard above passes, then exec_module hits ModuleNotFoundError. Resolving the package from the
    # repo also means the code under test is always THIS checkout, never a stale installed copy.
    src_root = Path(__file__).resolve().parents[2] / "mcp" / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    path = src_root / "limen_mcp" / "server.py"
    spec = importlib.util.spec_from_file_location("limen_mcp_server_under_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_agent_claim_preserves_board_extensions_and_reserves_budget(tmp_path, monkeypatch):
    server = _load_server()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "portal": {
                    "name": "test",
                    "agents": {"opencode": {"status": "idle"}},
                    "budget": {
                        "daily": 100,
                        "unit": "runs",
                        "track": {
                            "date": "2026-07-02",
                            "spent": 4,
                            "per_agent": {"opencode": 2},
                            "per_agent_reset": {"opencode": "2026-07-02T00:00:00+00:00"},
                        },
                    },
                },
                "tasks": [
                    {
                        "id": "TASK-1",
                        "title": "Claim me",
                        "target_agent": "any",
                        "priority": "high",
                        "budget_cost": 3,
                        "status": "open",
                        "created": "2026-07-02",
                        "claude_tier": "sonnet",
                        "depends_on": ["TASK-0"],
                        # claim-time intake normalization fails CLOSED without owner data: a legacy
                        # task needs at least an exact owner/repo so the merged-PR fallback contract
                        # (github_pr_contract) is derivable. Without it agent_claim correctly raises
                        # IntakeContractError instead of dispatching unverifiable work.
                        "repo": "organvm/limen",
                        "custom_extension": {"keep": True},
                    }
                ],
            },
            sort_keys=False,
        )
    )
    monkeypatch.setenv("LIMEN_TASKS", str(tasks))

    assert server.agent_claim("TASK-1", "opencode") == "opencode claimed task TASK-1 (status=dispatched)"

    data = yaml.safe_load(tasks.read_text())
    assert data["portal"]["agents"]["opencode"]["status"] == "idle"
    assert data["portal"]["budget"]["track"]["spent"] == 7
    assert data["portal"]["budget"]["track"]["per_agent"]["opencode"] == 5
    assert data["portal"]["budget"]["track"]["per_agent_reset"]["opencode"] == "2026-07-02T00:00:00+00:00"
    task = data["tasks"][0]
    assert task["status"] == "dispatched"
    assert task["target_agent"] == "opencode"
    assert task["claude_tier"] == "sonnet"
    assert task["depends_on"] == ["TASK-0"]
    assert task["custom_extension"] == {"keep": True}
    assert task["dispatch_log"][-1]["status"] == "dispatched"
    # normalize_selected_legacy_task derived the merged-PR fallback contract from the task's repo
    assert "gh pr list --repo organvm/limen" in task["predicate"]
    assert task["receipt_target"] == "github:organvm/limen:pull-request:TASK-1"
