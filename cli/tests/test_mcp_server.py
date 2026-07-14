import importlib.util
import sys
import types
from pathlib import Path

import yaml


def _load_server():
    # Core CI installs cli[test], not the optional MCP runtime. The server only needs FastMCP's
    # decorator behavior for these model/board tests, so provide a hermetic no-op implementation
    # when the package is absent. This keeps the persistence and claim regressions executable in
    # the core suite rather than silently skipping them.
    try:
        from mcp.server.fastmcp import FastMCP as _FastMCP  # noqa: F401
    except ImportError:
        mcp_package = types.ModuleType("mcp")
        mcp_server_package = types.ModuleType("mcp.server")
        fastmcp_module = types.ModuleType("mcp.server.fastmcp")

        class FastMCP:
            def __init__(self, _name):
                pass

            def tool(self):
                return lambda function: function

            def run(self):
                pass

        fastmcp_module.FastMCP = FastMCP
        mcp_package.server = mcp_server_package
        mcp_server_package.fastmcp = fastmcp_module
        sys.modules["mcp"] = mcp_package
        sys.modules["mcp.server"] = mcp_server_package
        sys.modules["mcp.server.fastmcp"] = fastmcp_module
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
    assert "execution_requirements" not in task
    # normalize_selected_legacy_task derived the merged-PR fallback contract from the task's repo
    assert "gh pr list --repo organvm/limen" in task["predicate"]
    assert task["receipt_target"] == "github:organvm/limen:pull-request:TASK-1"


def test_agent_claim_rejects_unavailable_runtime_without_mutating(tmp_path, monkeypatch):
    server = _load_server()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "portal": {
                    "budget": {
                        "track": {
                            "date": "2026-07-13",
                            "spent": 4,
                            "per_agent": {"opencode": 2},
                        }
                    }
                },
                "tasks": [
                    {
                        "id": "TASK-MOUNT",
                        "title": "Wait for runtime",
                        "repo": "organvm/limen",
                        "target_agent": "any",
                        "priority": "high",
                        "budget_cost": 3,
                        "status": "open",
                        "created": "2026-07-13",
                        "execution_requirements": [{"kind": "mount", "path": "/runtime/unavailable"}],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    before = tasks.read_bytes()
    monkeypatch.setenv("LIMEN_TASKS", str(tasks))
    monkeypatch.setattr(server, "CIRCUIT_BREAKER_TRIPPED", False)
    monkeypatch.setattr(server.runtime_requirements.os.path, "ismount", lambda _path: False)

    result = server.agent_claim("TASK-MOUNT", "opencode")

    assert "runtime requirements unavailable" in result
    assert "cannot claim" in result
    assert tasks.read_bytes() == before


def test_agent_claim_accepts_available_explicit_mount(tmp_path, monkeypatch):
    server = _load_server()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "portal": {
                    "budget": {
                        "track": {
                            "date": "2026-07-13",
                            "spent": 0,
                            "per_agent": {"opencode": 0},
                        }
                    }
                },
                "tasks": [
                    {
                        "id": "TASK-MOUNT",
                        "title": "Use available runtime",
                        "repo": "organvm/limen",
                        "target_agent": "any",
                        "priority": "high",
                        "budget_cost": 1,
                        "status": "open",
                        "created": "2026-07-13",
                        "predicate": "python3 scripts/check.py",
                        "receipt_target": "git:organvm/limen:logs/check.json",
                        "execution_requirements": [{"kind": "mount", "path": "/runtime/available"}],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMEN_TASKS", str(tasks))
    monkeypatch.setattr(server, "CIRCUIT_BREAKER_TRIPPED", False)
    monkeypatch.setattr(
        server.runtime_requirements.os.path,
        "ismount",
        lambda path: path == "/runtime/available",
    )

    result = server.agent_claim("TASK-MOUNT", "opencode")

    assert result == "opencode claimed task TASK-MOUNT (status=dispatched)"
    saved = yaml.safe_load(tasks.read_text(encoding="utf-8"))
    assert saved["tasks"][0]["status"] == "dispatched"
    assert saved["portal"]["budget"]["track"]["spent"] == 1
    assert saved["tasks"][0]["execution_requirements"] == [{"kind": "mount", "path": "/runtime/available"}]


def test_mcp_save_preserves_execution_requirement_field_absence(tmp_path, monkeypatch):
    server = _load_server()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "tasks": [
                    {
                        "id": "LEGACY-ABSENT",
                        "title": "Legacy absent field",
                        "target_agent": "any",
                        "created": "2026-07-13",
                    },
                    {
                        "id": "EXPLICIT-NULL",
                        "title": "Explicit null field",
                        "target_agent": "any",
                        "created": "2026-07-13",
                        "execution_requirements": None,
                    },
                    {
                        "id": "EXPLICIT-EMPTY",
                        "title": "Explicit empty field",
                        "target_agent": "any",
                        "created": "2026-07-13",
                        "execution_requirements": [],
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMEN_TASKS", str(tasks))

    server._save_data(server._load_data())

    saved = yaml.safe_load(tasks.read_text(encoding="utf-8"))
    by_id = {task["id"]: task for task in saved["tasks"]}
    assert "execution_requirements" not in by_id["LEGACY-ABSENT"]
    assert by_id["EXPLICIT-NULL"]["execution_requirements"] is None
    assert by_id["EXPLICIT-EMPTY"]["execution_requirements"] == []
    # Do not globally switch to exclude_none: established optional-field serialization stays intact.
    assert "description" in by_id["LEGACY-ABSENT"]
    assert by_id["LEGACY-ABSENT"]["description"] is None
