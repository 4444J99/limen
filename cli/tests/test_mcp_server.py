import importlib.util
import sys
import types
from pathlib import Path

import pytest
import yaml


class FakeConductClient:
    def __init__(self):
        self.sessions = []
        self.packets = []
        self.calls = []

    def register(self, session):
        self.sessions.append(session)
        return session.model_dump(mode="json")

    def submit(self, packet):
        self.packets.append(packet)
        return {"status": "reserved", "run_id": f"run-{packet.work_id}"}

    def capabilities(self):
        return {"schema_version": "limen.conduct_capabilities.v1", "sessions": []}

    def split(self, parent_run, packet):
        self.calls.append(("split", parent_run, packet))
        return {"status": "reserved", "run_id": "run-child"}

    def graph(self, root_run):
        self.calls.append(("graph", root_run))
        return {"root_run_id": root_run, "nodes": []}

    def heartbeat(self, lease, capability_token, *, generation, observed_heads):
        self.calls.append(("heartbeat", lease, generation, capability_token, observed_heads))
        return {"status": "active"}

    def report(self, lease, capability_token, receipt, *, generation):
        self.calls.append(("report", lease, generation, capability_token, receipt))
        return {"mutation_authorized": True}

    def harvest(self, root_run):
        self.calls.append(("harvest", root_run))
        return {"root_run_id": root_run, "unharvested": []}

    def adopt(self, run, session_id):
        self.calls.append(("adopt", run, session_id))
        return {"status": "adopted"}

    def cancel(self, run, session_id):
        self.calls.append(("cancel", run, session_id))
        return {"status": "cancelled"}

    def request_stop(self, run, session_id):
        self.calls.append(("request_stop", run, session_id))
        return {"status": "stop_requested", "cooperative": True}


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


def test_agent_claim_submits_atomic_compatibility_event_without_mutating_projection(tmp_path, monkeypatch):
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
    before = tasks.read_bytes()
    client = FakeConductClient()
    monkeypatch.setattr(server, "_conduct_client", lambda: client)

    result = server.agent_claim("TASK-1", "opencode")

    assert "submitted claim for opencode" in result
    assert "status=reserved" in result
    assert tasks.read_bytes() == before
    assert len(client.sessions) == 1
    assert len(client.packets) == 1
    packet = client.packets[0]
    assert packet.intent["kind"] == "task.claim"
    assert packet.intent["expected_status"] == "open"
    assert "budget_debit" not in packet.intent
    assert "budget_agent" not in packet.intent
    assert packet.intent["patch"]["target_agent"] == "opencode"
    assert packet.intent["patch"]["status"] == "dispatched"
    assert packet.intent["patch"]["target_agent"] == "opencode"
    assert "gh pr list --repo organvm/limen" in packet.intent["patch"]["predicate"]
    assert packet.resource_claims[0].key == "task/TASK-1"
    assert packet.required_capabilities == frozenset({"board-write"})


def test_agent_claim_rejects_successor_required_open_row_without_mutating(tmp_path, monkeypatch):
    server = _load_server()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "portal": {
                    "budget": {
                        "track": {
                            "date": "2026-07-17",
                            "spent": 0,
                            "per_agent": {"opencode": 0},
                        }
                    }
                },
                "tasks": [
                    {
                        "id": "TASK-SUCCESSOR",
                        "title": "Expired owner row",
                        "repo": "organvm/limen",
                        "target_agent": "any",
                        "status": "open",
                        "labels": ["workstream:successor-required"],
                        "created": "2026-07-17",
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

    result = server.agent_claim("TASK-SUCCESSOR", "opencode")

    assert "separately admitted successor" in result
    assert tasks.read_bytes() == before


def test_mcp_status_update_cannot_reopen_successor_required_row(tmp_path, monkeypatch):
    server = _load_server()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "tasks": [
                    {
                        "id": "TASK-SUCCESSOR",
                        "title": "Expired owner row",
                        "repo": "organvm/limen",
                        "target_agent": "codex",
                        "status": "failed",
                        "labels": ["workstream:successor-required"],
                        "created": "2026-07-17",
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

    result = server.update_task_status("TASK-SUCCESSOR", "open")

    assert "separately admitted successor" in result
    assert tasks.read_bytes() == before


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
    client = FakeConductClient()
    monkeypatch.setattr(server, "_conduct_client", lambda: client)
    before = tasks.read_bytes()

    result = server.agent_claim("TASK-MOUNT", "opencode")

    assert "submitted claim for opencode" in result
    assert tasks.read_bytes() == before
    assert "budget_debit" not in client.packets[0].intent
    assert client.packets[0].intent["patch"]["target_agent"] == "opencode"


def test_mcp_server_has_no_direct_board_writer_or_git_sync(tmp_path, monkeypatch):
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
    before = tasks.read_bytes()

    assert not hasattr(server, "_save_data")
    source = Path(server.__file__).read_text(encoding="utf-8")
    assert "git stash" not in source
    assert "git pull --rebase" not in source
    assert "yaml.dump" not in source
    assert tasks.read_bytes() == before


def test_task_add_and_status_are_conduct_compatibility_events(tmp_path, monkeypatch):
    server = _load_server()
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "tasks": [
                    {
                        "id": "TASK-STATUS",
                        "title": "Status event",
                        "repo": "organvm/limen",
                        "target_agent": "any",
                        "status": "in_progress",
                        "created": "2026-07-18",
                        "predicate": "pytest -q",
                        "receipt_target": "git:organvm/limen:logs/status.json",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMEN_TASKS", str(tasks))
    client = FakeConductClient()
    monkeypatch.setattr(server, "_conduct_client", lambda: client)
    before = tasks.read_bytes()

    added = server.add_task(
        "New task",
        "organvm/limen",
        "pytest -q",
        "github:organvm/limen:pull-request:LIMEN-001",
        "Deliver the explicitly requested MCP task",
        agent="codex",
    )
    updated = server.update_task_status("TASK-STATUS", "done", context="predicate passed")

    assert "submitted task upsert" in added
    assert "submitted status done" in updated
    assert [packet.intent["kind"] for packet in client.packets] == ["task.upsert", "task.status"]
    assert tasks.read_bytes() == before


def test_task_add_rejects_noncanonical_work_loan_enums() -> None:
    server = _load_server()
    arguments = (
        "New task",
        "organvm/limen",
        "pytest -q",
        "github:organvm/limen:pull-request:LIMEN-001",
        "Deliver the explicitly requested MCP task",
    )
    with pytest.raises(ValueError, match="origin must be one of"):
        server.add_task(*arguments, origin="urgent")
    with pytest.raises(ValueError, match="horizon must be one of"):
        server.add_task(*arguments, horizon="soon")
    with pytest.raises(ValueError, match="due_at is required"):
        server.add_task(*arguments, external_deadline=True)
    with pytest.raises(ValueError, match="valid ISO date"):
        server.add_task(*arguments, external_deadline=True, due_at="soon")


def test_mcp_conduct_tools_forward_the_identical_protocol_models(monkeypatch):
    server = _load_server()
    client = FakeConductClient()
    monkeypatch.setattr(server, "_conduct_client", lambda: client)
    monkeypatch.setattr(server, "CIRCUIT_BREAKER_TRIPPED", False)

    assert server.conduct_capabilities()["schema_version"] == "limen.conduct_capabilities.v1"
    assert server.conduct_graph("run-root")["root_run_id"] == "run-root"
    assert server.conduct_harvest("run-root")["unharvested"] == []
    assert server.conduct_adopt("run-root", "session-a")["status"] == "adopted"
    assert server.conduct_cancel("run-root", "session-a")["status"] == "cancelled"
    assert server.conduct_request_stop("run-root", "session-a")["cooperative"] is True
