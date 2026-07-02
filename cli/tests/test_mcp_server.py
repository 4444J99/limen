import importlib.util
import sys
from pathlib import Path

import yaml


def _load_server():
    path = Path(__file__).resolve().parents[2] / "mcp" / "src" / "limen_mcp" / "server.py"
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
