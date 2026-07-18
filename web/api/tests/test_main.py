from __future__ import annotations

import stat
import sys
import os
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


def write_board(path: Path, tasks: list[dict]) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "portal": {
                    "name": "Universal Task Intake",
                    "description": "test board",
                    "budget": {
                        "daily": 100,
                        "unit": "runs",
                        "per_agent": {"jules": 100, "codex": 10},
                        "track": {"date": "", "spent": 0, "per_agent": {}},
                    },
                },
                "tasks": tasks,
            },
            sort_keys=False,
        )
    )


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    tasks_path = tmp_path / "tasks.yaml"
    monkeypatch.setenv("LIMEN_TASKS", str(tasks_path))
    monkeypatch.setattr(main, "GITHUB_REPO", "")
    monkeypatch.setattr(main, "GITHUB_TOKEN", "")
    monkeypatch.setattr(main, "LIMEN_TOKEN", "")
    monkeypatch.delenv("LIMEN_API_TOKEN", raising=False)
    monkeypatch.delenv("LIMEN_OWNER_TOKEN", raising=False)
    monkeypatch.delenv("LIMEN_CLIENT_TOKEN", raising=False)
    return TestClient(main.app)


def read_board(tmp_path: Path) -> dict:
    return yaml.safe_load((tmp_path / "tasks.yaml").read_text())


def test_dispatch_dry_run_does_not_mutate_board(client: TestClient, tmp_path: Path) -> None:
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "LIMEN-001",
                "title": "Open Jules task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-03",
                "dispatch_log": [],
            }
        ],
    )
    before = (tmp_path / "tasks.yaml").read_text()

    response = client.post("/api/dispatch", json={"agent": "jules", "limit": 1, "live": False})

    assert response.status_code == 200
    assert response.json()["status"] == "dry_run"
    assert response.json()["count"] == 1
    assert (tmp_path / "tasks.yaml").read_text() == before


def test_release_stale_reopens_tasks_only_when_not_dry_run(client: TestClient, tmp_path: Path) -> None:
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "LIMEN-002",
                "title": "Stale active task",
                "repo": "4444J99/limen",
                "target_agent": "codex",
                "priority": "high",
                "budget_cost": 1,
                "status": "dispatched",
                "created": "2026-06-01",
                "dispatch_log": [
                    {
                        "timestamp": "2026-06-01T00:00:00+00:00",
                        "agent": "jules",
                        "session_id": "test",
                        "status": "dispatched",
                    }
                ],
            }
        ],
    )

    preview = client.post("/api/release-stale?hours=24&dry_run=true")

    assert preview.status_code == 200
    assert preview.json()["count"] == 1
    assert read_board(tmp_path)["tasks"][0]["status"] == "dispatched"

    released = client.post("/api/release-stale?hours=24&dry_run=false")

    assert released.status_code == 200
    task = read_board(tmp_path)["tasks"][0]
    assert task["status"] == "open"
    assert task["dispatch_log"][-1]["session_id"] == "release-stale"


def test_release_stale_api_holds_jules_when_remote_probe_is_unavailable(
    client: TestClient,
    tmp_path: Path,
) -> None:
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "JULES-STALE",
                "title": "Remote claim",
                "repo": "organvm/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "dispatched",
                "created": "2026-06-01",
                "dispatch_log": [
                    {
                        "timestamp": "2026-06-01T00:00:00+00:00",
                        "agent": "jules",
                        "session_id": "12345678901234567890",
                        "status": "dispatched",
                    }
                ],
            }
        ],
    )

    response = client.post("/api/release-stale?hours=24&dry_run=false")

    assert response.status_code == 200
    assert response.json()["count"] == 0
    assert response.json()["candidate_count"] == 1
    assert response.json()["held"] == ["JULES-STALE"]
    assert response.json()["released"] == []
    assert response.json()["remote_probe"]["status"] == "unavailable"
    assert read_board(tmp_path)["tasks"][0]["status"] == "dispatched"


def test_live_dispatch_mutates_after_command_success(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatch_bin = tmp_path / "agent-dispatch"
    dispatch_bin.write_text("#!/bin/sh\nprintf 'ok %s\\n' \"$1\"\n")
    dispatch_bin.chmod(dispatch_bin.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("LIMEN_DISPATCH_CMD", str(dispatch_bin))
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "LIMEN-003",
                "title": "Open Codex task",
                "repo": "4444J99/limen",
                "target_agent": "codex",
                "priority": "critical",
                "budget_cost": 2,
                "status": "open",
                "created": "2026-06-03",
                "dispatch_log": [],
            }
        ],
    )

    response = client.post(
        "/api/dispatch",
        json={"agent": "codex", "limit": 1, "live": True, "session_id": "test-live"},
    )

    assert response.status_code == 200
    assert response.json()["count"] == 1
    board = read_board(tmp_path)
    task = board["tasks"][0]
    assert task["status"] == "dispatched"
    assert task["dispatch_log"][-1]["status"] == "dispatched"
    assert board["portal"]["budget"]["track"]["spent"] == 2
    assert board["portal"]["budget"]["track"]["per_agent"]["codex"] == 2


def test_live_dispatch_does_not_normalize_over_budget_unselected_sibling(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatch_bin = tmp_path / "agent-dispatch"
    dispatch_bin.write_text("#!/bin/sh\nprintf 'ok\\n'\n")
    dispatch_bin.chmod(dispatch_bin.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("LIMEN_DISPATCH_CMD", str(dispatch_bin))
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "OVER-BUDGET",
                "title": "Do not mutate this legacy sibling",
                "repo": "4444J99/limen",
                "target_agent": "codex",
                "priority": "critical",
                "budget_cost": 11,
                "status": "open",
                "created": "2026-06-03",
            },
            {
                "id": "AFFORDABLE",
                "title": "Dispatch this task",
                "repo": "4444J99/limen",
                "target_agent": "codex",
                "priority": "high",
                "budget_cost": 1,
                "status": "open",
                "predicate": "pytest -q web/api/tests/test_main.py",
                "receipt_target": "github:4444J99/limen:pull-request:AFFORDABLE",
                "created": "2026-06-03",
            },
        ],
    )

    response = client.post("/api/dispatch", json={"agent": "codex", "limit": 1, "live": True})

    assert response.status_code == 200
    tasks = {task["id"]: task for task in read_board(tmp_path)["tasks"]}
    assert tasks["AFFORDABLE"]["status"] == "dispatched"
    assert "predicate" not in tasks["OVER-BUDGET"]
    assert "receipt_target" not in tasks["OVER-BUDGET"]


@pytest.mark.parametrize("branch", ["main", "master", "tabularius/board-projection", "feature/runtime"])
def test_github_storage_refuses_every_branch_before_contents_access(
    branch: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_github_request(method: str, _url: str, _payload: dict | None = None) -> dict:
        calls.append(method)
        raise AssertionError("GitHub-backed mutation reached the Contents adapter")

    monkeypatch.setattr(main, "GITHUB_REPO", "organvm/limen")
    monkeypatch.setattr(main, "GITHUB_TOKEN", "token")
    monkeypatch.setattr(main, "GITHUB_BRANCH", branch)
    monkeypatch.setattr(main, "GITHUB_PATH", "tasks.yaml")
    monkeypatch.setattr(main, "github_request", fake_github_request)
    client = TestClient(main.app)

    response = client.post(
        "/api/tasks",
        json={
            "id": "LIMEN-DIRECT-MAIN-BLOCKED",
            "title": "Must route through Tabularius",
            "repo": "organvm/limen",
            "target_agent": "codex",
            "predicate": "pytest -q web/api/tests/test_main.py",
            "receipt_target": "github:organvm/limen:pull-request:LIMEN-DIRECT-MAIN-BLOCKED",
        },
    )

    assert response.status_code == 409
    receipt = response.json()["detail"]
    assert receipt["status"] == "mutation_deferred"
    assert receipt["code"] == "board_mutation_deferred"
    assert receipt["retryable"] is True
    assert receipt["owner"] == "tabularius"
    assert receipt["target"]["access"] == "read_only"
    assert receipt["target"]["writable"] is False
    assert receipt["target"]["branch"] == branch
    assert receipt["target"]["mutation_route"] == "tabularius_ticket"
    assert calls == []


def test_github_live_dispatch_fails_before_command_or_storage_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_calls: list[str] = []
    dispatch_calls: list[list[str]] = []

    def fake_github_request(method: str, _url: str, _payload: dict | None = None) -> dict:
        storage_calls.append(method)
        raise AssertionError("live dispatch reached GitHub storage")

    def fake_dispatch(command: list[str]) -> tuple[bool, str]:
        dispatch_calls.append(command)
        raise AssertionError("live dispatch launched before persistence was proven")

    monkeypatch.setattr(main, "GITHUB_REPO", "organvm/limen")
    monkeypatch.setattr(main, "GITHUB_TOKEN", "token")
    monkeypatch.setattr(main, "GITHUB_BRANCH", "tabularius/board-projection")
    monkeypatch.setattr(main, "github_request", fake_github_request)
    monkeypatch.setattr(main, "run_dispatch_command", fake_dispatch)
    client = TestClient(main.app)

    response = client.post(
        "/api/dispatch",
        json={"agent": "codex", "limit": 1, "live": True, "session_id": "must-not-launch"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "board_mutation_deferred"
    assert storage_calls == []
    assert dispatch_calls == []


def test_public_status_is_aggregate_only(client: TestClient, tmp_path: Path) -> None:
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "LIMEN-005",
                "title": "Private implementation detail",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "done",
                "created": "2026-06-03",
                "dispatch_log": [],
            }
        ],
    )

    response = client.get("/api/public-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total"] == 1
    assert payload["summary"]["completed"] == 1
    assert payload["summary"]["throughput"]["first_created"] == "2026-06-03"
    assert payload["summary"]["throughput"]["done"] == 1
    assert payload["summary"]["throughput"]["not_done"] == 0
    assert "tasks" not in payload
    assert "Private implementation detail" not in str(payload)


def test_status_summary_reports_creation_age_and_run_ledger(client: TestClient, tmp_path: Path) -> None:
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "LIMEN-AGE-001",
                "title": "Completed task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "done",
                "created": "2026-05-31",
                "dispatch_log": [
                    {
                        "timestamp": "2026-05-31T00:00:00+00:00",
                        "agent": "jules",
                        "session_id": "test",
                        "status": "dispatched",
                    },
                    {
                        "timestamp": "2026-05-31T01:00:00+00:00",
                        "agent": "jules",
                        "session_id": "test",
                        "status": "done",
                    },
                ],
            },
            {
                "id": "LIMEN-AGE-002",
                "title": "Still active",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "dispatched",
                "created": "2026-06-01",
                "dispatch_log": [],
            },
        ],
    )

    response = client.get("/api/status")

    assert response.status_code == 200
    throughput = response.json()["summary"]["throughput"]
    assert throughput["first_created"] == "2026-05-31"
    assert throughput["daily_capacity"] == 100
    assert throughput["recorded_events"] == 2
    assert throughput["recorded_starts"] == 1
    assert throughput["recorded_finishes"] == 1
    assert throughput["done"] == 1
    assert throughput["not_done"] == 1
    assert throughput["unrecorded_capacity_runs"] >= 0


def test_client_status_respects_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-006",
                "title": "Client visible active task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "dispatched",
                "created": "2026-06-01",
                "dispatch_log": [],
            }
        ],
    )
    monkeypatch.setenv("LIMEN_TASKS", str(tasks_path))
    monkeypatch.setattr(main, "GITHUB_REPO", "")
    monkeypatch.setattr(main, "LIMEN_TOKEN", "secret")
    client = TestClient(main.app)

    assert client.get("/api/client-status").status_code == 401
    response = client.get("/api/client-status", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200


def test_client_persona_is_sanctioned_only_for_client_and_public(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-006C",
                "title": "Client visible active task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "dispatched",
                "created": "2026-06-01",
                "dispatch_log": [],
            }
        ],
    )
    monkeypatch.setenv("LIMEN_TASKS", str(tasks_path))
    monkeypatch.setenv("LIMEN_CLIENT_TOKEN", "client-secret")
    monkeypatch.setattr(main, "GITHUB_REPO", "")
    monkeypatch.setattr(main, "LIMEN_TOKEN", "owner-secret")
    client = TestClient(main.app)
    client_headers = {"Authorization": "Bearer client-secret"}

    assert client.get("/api/public-status").status_code == 200
    public_manifest = client.get("/api/surface-manifest")
    assert public_manifest.status_code == 200
    assert [surface["id"] for surface in public_manifest.json()["surfaces"]] == ["public"]
    assert client.get("/api/surface-manifest", headers={"Authorization": "Bearer invalid-token"}).status_code == 401
    assert client.get("/api/client-status", headers=client_headers).status_code == 200
    client_manifest = client.get("/api/surface-manifest", headers=client_headers)
    assert client_manifest.status_code == 200
    client_manifest_payload = client_manifest.json()
    assert client_manifest_payload["persona"] == "client"
    assert sorted(surface["id"] for surface in client_manifest_payload["surfaces"]) == ["client", "public"]
    assert "internal" not in client_manifest_payload["contracts"]
    assert "qa" not in client_manifest_payload["contracts"]
    assert "readiness" not in client_manifest_payload["contracts"]
    assert client.get("/api/status", headers=client_headers).status_code == 403
    assert client.get("/api/qa-status", headers=client_headers).status_code == 403
    assert client.get("/api/readiness", headers=client_headers).status_code == 403
    assert (
        client.post("/api/tasks/LIMEN-006C/verify", headers=client_headers, json={"status": "done"}).status_code == 403
    )
    assert (
        client.post("/api/tasks/LIMEN-006C/assign", headers=client_headers, json={"target_agent": "jules"}).status_code
        == 403
    )
    assert client.post("/api/tasks/LIMEN-006C/archive", headers=client_headers, json={}).status_code == 403


def test_owner_persona_can_reach_owner_surfaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(tasks_path, [])
    monkeypatch.setenv("LIMEN_TASKS", str(tasks_path))
    monkeypatch.setenv("LIMEN_CLIENT_TOKEN", "client-secret")
    monkeypatch.setattr(main, "GITHUB_REPO", "")
    monkeypatch.setattr(main, "LIMEN_TOKEN", "owner-secret")
    client = TestClient(main.app)
    owner_headers = {"Authorization": "Bearer owner-secret"}

    assert client.get("/api/status", headers=owner_headers).status_code == 200
    assert client.get("/api/qa-status", headers=owner_headers).status_code == 200
    assert client.get("/api/readiness", headers=owner_headers).status_code == 200
    manifest = client.get("/api/surface-manifest", headers=owner_headers)
    assert manifest.status_code == 200
    payload = manifest.json()
    assert payload["persona"] == "owner"
    assert sorted(surface["id"] for surface in payload["surfaces"]) == ["client", "internal", "public", "qa"]
    assert "internal" in payload["contracts"]
    assert "qa" in payload["contracts"]


def test_qa_status_derives_lifecycle_without_private_logs(client: TestClient, tmp_path: Path) -> None:
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "LIMEN-007",
                "title": "Stale active task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "dispatched",
                "context": "private context must not leak",
                "urls": ["https://github.com/4444J99/limen/issues/7"],
                "created": "2026-06-01",
                "dispatch_log": [
                    {
                        "timestamp": "2026-06-01T00:00:00+00:00",
                        "agent": "jules",
                        "session_id": "private-session",
                        "status": "dispatched",
                    }
                ],
            },
            {
                "id": "LIMEN-008",
                "title": "Verify task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "medium",
                "budget_cost": 1,
                "status": "in_progress",
                "urls": ["https://github.com/4444J99/limen/pull/8"],
                "created": "2026-06-03",
                "dispatch_log": [
                    {
                        "timestamp": main.now_iso(),
                        "agent": "jules",
                        "session_id": "private-session",
                        "status": "in_progress",
                    }
                ],
            },
            {
                "id": "LIMEN-009",
                "title": "Assignable task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "low",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-03",
                "dispatch_log": [],
            },
            {
                "id": "LIMEN-010",
                "title": "Closed task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "low",
                "budget_cost": 1,
                "status": "done",
                "created": "2026-06-03",
                "dispatch_log": [],
            },
        ],
    )

    response = client.get("/api/qa-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["surface"] == "qa"
    assert payload["status"] == "degraded"
    assert payload["lifecycle"] == {
        "total": 4,
        "assign": 1,
        "verify": 1,
        "recover": 1,
        "archive_ready": 1,
        "archived": 0,
    }
    assert [item["id"] for item in payload["steering"]["next_batch"]] == ["LIMEN-007", "LIMEN-008", "LIMEN-009"]
    text = str(payload)
    assert "dispatch_log" not in text
    assert "private context must not leak" not in text
    assert "private-session" not in text
    assert "https://github.com/4444J99/limen/pull/8" not in text
    assert {mechanism["id"] for mechanism in payload["mechanisms"]} == {
        "release-stale",
        "qa-verify",
        "assign-next",
        "archive-done",
    }
    mechanisms = {mechanism["id"]: mechanism for mechanism in payload["mechanisms"]}
    assert mechanisms["qa-verify"]["command"] == "POST /api/tasks/{task_id}/verify"
    assert mechanisms["qa-verify"]["mode"] == "human-approved evidence gate"
    assert mechanisms["assign-next"]["command"] == "POST /api/tasks/{task_id}/assign"
    assert mechanisms["archive-done"]["command"] == "POST /api/tasks/{task_id}/archive"


def test_qa_status_respects_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(tasks_path, [])
    monkeypatch.setenv("LIMEN_TASKS", str(tasks_path))
    monkeypatch.setattr(main, "GITHUB_REPO", "")
    monkeypatch.setattr(main, "LIMEN_TOKEN", "secret")
    client = TestClient(main.app)

    assert client.get("/api/qa-status").status_code == 401
    assert client.get("/api/qa-status", headers={"Authorization": "Bearer secret"}).status_code == 200


def test_assign_task_updates_steering_fields_and_logs(client: TestClient, tmp_path: Path) -> None:
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "LIMEN-011",
                "title": "Assignable task",
                "repo": "4444J99/limen",
                "target_agent": "any",
                "priority": "low",
                "budget_cost": 1,
                "status": "needs_human",
                "created": "2026-06-03",
                "dispatch_log": [],
            }
        ],
    )

    response = client.post(
        "/api/tasks/LIMEN-011/assign",
        json={
            "target_agent": "jules",
            "priority": "high",
            "budget_cost": 2,
            "status": "open",
            "predicate": "pytest -q web/api/tests/test_main.py",
            "receipt_target": "github:4444J99/limen:pull-request:LIMEN-011",
            "note": "Route through Jules after QA steering",
            "session_id": "qa-panel",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "assigned"
    assert set(payload["changed"]) == {"target_agent", "priority", "budget_cost", "status"}
    task = read_board(tmp_path)["tasks"][0]
    assert task["target_agent"] == "jules"
    assert task["priority"] == "high"
    assert task["budget_cost"] == 2
    assert task["status"] == "open"
    assert task["dispatch_log"][-1]["status"] == "assigned"
    assert task["dispatch_log"][-1]["session_id"] == "qa-panel"
    assert "Route through Jules" in task["dispatch_log"][-1]["output"]


def test_assign_task_rejects_boolean_budget_cost(client: TestClient, tmp_path: Path) -> None:
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "LIMEN-011B",
                "title": "Assignable task",
                "repo": "4444J99/limen",
                "target_agent": "any",
                "priority": "low",
                "budget_cost": 1,
                "status": "needs_human",
                "created": "2026-06-03",
                "dispatch_log": [],
            }
        ],
    )

    response = client.post("/api/tasks/LIMEN-011B/assign", json={"budget_cost": True})

    assert response.status_code == 422


def test_assign_task_respects_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-012",
                "title": "Protected assignable task",
                "repo": "4444J99/limen",
                "target_agent": "any",
                "priority": "low",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-03",
                "dispatch_log": [],
            }
        ],
    )
    monkeypatch.setenv("LIMEN_TASKS", str(tasks_path))
    monkeypatch.setattr(main, "GITHUB_REPO", "")
    monkeypatch.setattr(main, "LIMEN_TOKEN", "secret")
    client = TestClient(main.app)

    assert client.post("/api/tasks/LIMEN-012/assign", json={"target_agent": "jules"}).status_code == 401
    response = client.post(
        "/api/tasks/LIMEN-012/assign",
        headers={"Authorization": "Bearer secret"},
        json={
            "target_agent": "jules",
            "predicate": "pytest -q web/api/tests/test_main.py",
            "receipt_target": "github:4444J99/limen:pull-request:LIMEN-012",
        },
    )
    assert response.status_code == 200


def test_verify_task_moves_active_work_to_closure_gate(client: TestClient, tmp_path: Path) -> None:
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "LIMEN-014V",
                "title": "Verify active task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "in_progress",
                "created": "2026-06-03",
                "urls": ["https://github.com/4444J99/limen/pull/14"],
                "dispatch_log": [],
            }
        ],
    )

    response = client.post(
        "/api/tasks/LIMEN-014V/verify",
        json={"status": "done", "note": "Evidence passed", "session_id": "qa-verify"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "verified"
    assert payload["verified_status"] == "done"
    task = read_board(tmp_path)["tasks"][0]
    assert task["status"] == "done"
    assert task["dispatch_log"][-1]["agent"] == "qa"
    assert task["dispatch_log"][-1]["status"] == "done"
    assert task["dispatch_log"][-1]["session_id"] == "qa-verify"
    assert "Evidence passed" in task["dispatch_log"][-1]["output"]
    qa = client.get("/api/qa-status").json()
    assert qa["lifecycle"]["verify"] == 0
    assert qa["lifecycle"]["archive_ready"] == 1


def test_verify_task_can_return_attention_status(client: TestClient, tmp_path: Path) -> None:
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "LIMEN-014A",
                "title": "Needs followup",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "in_progress",
                "created": "2026-06-03",
                "dispatch_log": [],
            }
        ],
    )

    response = client.post(
        "/api/tasks/LIMEN-014A/verify",
        json={"status": "needs_human", "note": "Missing evidence", "session_id": "qa-verify"},
    )

    assert response.status_code == 200
    task = read_board(tmp_path)["tasks"][0]
    assert task["status"] == "needs_human"
    qa = client.get("/api/qa-status").json()
    assert qa["lifecycle"]["recover"] == 1
    assert qa["steering"]["recovery_queue"][0]["id"] == "LIMEN-014A"


def test_verify_task_rejects_open_assignment_work(client: TestClient, tmp_path: Path) -> None:
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "LIMEN-014O",
                "title": "Open task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-03",
                "dispatch_log": [],
            }
        ],
    )

    response = client.post("/api/tasks/LIMEN-014O/verify", json={"status": "done"})

    assert response.status_code == 409


def test_archive_done_task_suppresses_it_from_qa_steering(client: TestClient, tmp_path: Path) -> None:
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "LIMEN-013",
                "title": "Done task to archive",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "low",
                "budget_cost": 1,
                "status": "done",
                "created": "2026-06-03",
                "dispatch_log": [],
            }
        ],
    )

    response = client.post(
        "/api/tasks/LIMEN-013/archive",
        json={"note": "Evidence retained", "session_id": "qa-archive"},
    )

    assert response.status_code == 200
    task = read_board(tmp_path)["tasks"][0]
    assert task["status"] == "archived"
    assert task["dispatch_log"][-1]["status"] == "archived"
    assert task["dispatch_log"][-1]["session_id"] == "qa-archive"
    qa = client.get("/api/qa-status").json()
    assert qa["lifecycle"]["archive_ready"] == 0
    assert qa["lifecycle"]["archived"] == 1
    assert qa["steering"]["next_batch"] == []
    public = client.get("/api/public-status").json()
    assert public["summary"]["completed"] == 1


def test_archive_rejects_unresolved_task(client: TestClient, tmp_path: Path) -> None:
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "LIMEN-014",
                "title": "Open task cannot archive",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "low",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-03",
                "dispatch_log": [],
            }
        ],
    )

    response = client.post("/api/tasks/LIMEN-014/archive", json={})

    assert response.status_code == 409
    assert read_board(tmp_path)["tasks"][0]["status"] == "open"


def test_surface_manifest_advertises_qa_contract(client: TestClient, tmp_path: Path) -> None:
    write_board(tmp_path / "tasks.yaml", [])

    response = client.get("/api/surface-manifest")

    assert response.status_code == 200
    payload = response.json()
    assert "/api/qa-status" in [surface["contract"] for surface in payload["surfaces"]]
    assert payload["contracts"]["qa"]["verify_endpoint"] == "/api/tasks/{task_id}/verify"
    assert payload["contracts"]["qa"]["assignment_endpoint"] == "/api/tasks/{task_id}/assign"
    assert payload["contracts"]["qa"]["archive_endpoint"] == "/api/tasks/{task_id}/archive"
    assert payload["contracts"]["qa"]["includes_dispatch_logs"] is False
    assert payload["contracts"]["qa"]["includes_task_context"] is False
    assert payload["contracts"]["qa"]["includes_task_urls"] is False


def test_surface_manifest_describes_surface_contracts(client: TestClient, tmp_path: Path) -> None:
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "LIMEN-007",
                "title": "Manifest task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "dispatched",
                "created": "2026-06-01",
                "dispatch_log": [],
            }
        ],
    )

    response = client.get("/api/surface-manifest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["api_runtime"] == "connected"
    assert {surface["id"] for surface in payload["surfaces"]} == {"internal", "client", "public", "qa"}
    surface_by_id = {surface["id"]: surface for surface in payload["surfaces"]}
    assert surface_by_id["internal"]["sanctioned_personas"] == ["owner"]
    assert surface_by_id["qa"]["sanctioned_personas"] == ["owner"]
    assert surface_by_id["client"]["sanctioned_personas"] == ["owner", "client"]
    assert surface_by_id["public"]["sanctioned_personas"] == ["owner", "client", "public"]
    assert payload["contracts"]["public"]["includes_tasks"] is False
    assert payload["contracts"]["client"]["includes_dispatch_logs"] is False
    assert payload["contracts"]["qa"]["verify_endpoint"] == "/api/tasks/{task_id}/verify"
    assert payload["contracts"]["qa"]["assignment_endpoint"] == "/api/tasks/{task_id}/assign"
    assert payload["contracts"]["qa"]["archive_endpoint"] == "/api/tasks/{task_id}/archive"
    assert payload["contracts"]["qa"]["includes_task_context"] is False


def test_readiness_reports_operator_next_actions(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatch_bin = tmp_path / "jules"
    dispatch_bin.write_text("#!/bin/sh\nexit 0\n")
    dispatch_bin.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ.get('PATH', '')}")
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "LIMEN-008",
                "title": "Stale active task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "dispatched",
                "created": "2026-06-01",
                "dispatch_log": [],
            },
            {
                "id": "LIMEN-009",
                "title": "Open task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-03",
                "dispatch_log": [],
            },
        ],
    )

    response = client.get("/api/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["counts"]["stale"] == 1
    assert payload["counts"]["open"] == 1
    assert any("release-stale" in action for action in payload["next_actions"])
    assert "dispatch_log" not in str(payload)


def test_github_readiness_advertises_deferred_ticket_route_not_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import base64

    board = yaml.safe_dump(
        {
            "version": "1.0",
            "portal": {
                "name": "Universal Task Intake",
                "budget": {
                    "daily": 100,
                    "per_agent": {"codex": 10},
                    "track": {"date": "", "spent": 0, "per_agent": {}},
                },
            },
            "tasks": [
                {
                    "id": "STALE",
                    "title": "Stale claim",
                    "repo": "organvm/limen",
                    "target_agent": "codex",
                    "priority": "high",
                    "budget_cost": 1,
                    "status": "dispatched",
                    "created": "2026-06-01",
                    "dispatch_log": [],
                },
                {
                    "id": "OPEN",
                    "title": "Open task",
                    "repo": "organvm/limen",
                    "target_agent": "codex",
                    "priority": "high",
                    "budget_cost": 1,
                    "status": "open",
                    "created": "2026-06-03",
                    "dispatch_log": [],
                },
            ],
        },
        sort_keys=False,
    )
    calls: list[str] = []

    def fake_github_request(method: str, _url: str, _payload: dict | None = None) -> dict:
        calls.append(method)
        assert method == "GET"
        return {
            "encoding": "base64",
            "content": base64.b64encode(board.encode()).decode(),
            "sha": "abc123",
        }

    monkeypatch.setattr(main, "GITHUB_REPO", "organvm/limen")
    monkeypatch.setattr(main, "GITHUB_TOKEN", "token")
    monkeypatch.setattr(main, "GITHUB_BRANCH", "main")
    monkeypatch.setattr(main, "GITHUB_PATH", "tasks.yaml")
    monkeypatch.setattr(main, "github_request", fake_github_request)
    client = TestClient(main.app)

    response = client.get("/api/readiness?agent=codex")

    assert response.status_code == 200
    payload = response.json()
    storage = next(check for check in payload["checks"] if check["id"] == "storage")
    assert storage["status"] == "warn"
    assert payload["mutation"] == {
        "status": "deferred",
        "code": "board_mutation_deferred",
        "owner": "tabularius",
        "route": "tabularius_ticket",
        "next_action": main.TABULARIUS_TICKET_ACTION,
    }
    assert main.TABULARIUS_TICKET_ACTION in payload["next_actions"]
    assert all("release-stale" not in action for action in payload["next_actions"])
    assert all("live=true" not in action for action in payload["next_actions"])
    assert calls == ["GET"]


def test_create_task_rejects_malformed_untrusted_fields(client: TestClient, tmp_path: Path) -> None:
    write_board(tmp_path / "tasks.yaml", [])

    bad_id = client.post(
        "/api/tasks",
        json={
            "id": "../escape",
            "title": "Bad task",
            "repo": "4444J99/limen",
            "target_agent": "jules",
        },
    )
    assert bad_id.status_code == 422

    bad_repo = client.post(
        "/api/tasks",
        json={
            "id": "LIMEN-SEC-001",
            "title": "Bad repo",
            "repo": "https://example.com/repo.git",
            "target_agent": "jules",
        },
    )
    assert bad_repo.status_code == 422

    bad_label = client.post(
        "/api/tasks",
        json={
            "id": "LIMEN-SEC-002",
            "title": "Bad label",
            "repo": "4444J99/limen",
            "target_agent": "jules",
            "labels": ["ok", "bad label"],
        },
    )
    assert bad_label.status_code == 422

    bad_budget = client.post(
        "/api/tasks",
        json={
            "id": "LIMEN-SEC-003",
            "title": "Bad budget",
            "repo": "4444J99/limen",
            "target_agent": "jules",
            "budget_cost": True,
        },
    )
    assert bad_budget.status_code == 422


def test_create_and_open_update_enforce_typed_intake_contract(client: TestClient, tmp_path: Path) -> None:
    assert main.TaskCreate.model_fields["predicate"].is_required()
    assert main.TaskCreate.model_fields["receipt_target"].is_required()
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "LIMEN-CONTRACT-LEGACY",
                "title": "Legacy terminal task",
                "repo": "organvm/limen",
                "target_agent": "codex",
                "status": "needs_human",
                "created": "2026-07-01",
            }
        ],
    )

    missing = client.post(
        "/api/tasks",
        json={
            "id": "LIMEN-CONTRACT-MISSING",
            "title": "Missing typed contract",
            "repo": "organvm/limen",
            "target_agent": "codex",
        },
    )
    assert missing.status_code == 422
    assert {error["loc"][-1] for error in missing.json()["detail"]} == {"predicate", "receipt_target"}

    created = client.post(
        "/api/tasks",
        json={
            "id": "LIMEN-CONTRACT-OK",
            "title": "Typed task",
            "repo": "organvm/limen",
            "target_agent": "codex",
            "predicate": "pytest -q web/api/tests/test_main.py",
            "receipt_target": "github:organvm/limen:pull-request:LIMEN-CONTRACT-OK",
        },
    )
    assert created.status_code == 200
    assert created.json()["task"]["predicate"].startswith("pytest")

    invalid_update = client.patch(
        "/api/tasks/LIMEN-CONTRACT-OK",
        json={"predicate": "tests should pass"},
    )
    assert invalid_update.status_code == 422

    bypassed_dispatch = client.patch(
        "/api/tasks/LIMEN-CONTRACT-LEGACY",
        json={"status": "dispatched"},
    )
    assert bypassed_dispatch.status_code == 422


def test_dispatch_rejects_invalid_agent_limit_and_task_id(client: TestClient, tmp_path: Path) -> None:
    write_board(tmp_path / "tasks.yaml", [])

    assert client.post("/api/dispatch", json={"agent": "any"}).status_code == 422
    assert client.post("/api/dispatch", json={"agent": "codex", "limit": 101}).status_code == 422
    assert client.post("/api/dispatch", json={"agent": "codex", "limit": True}).status_code == 422
    assert client.post("/api/dispatch", json={"agent": "codex", "task_id": "../escape"}).status_code == 422


def test_release_stale_rejects_out_of_range_hours(client: TestClient, tmp_path: Path) -> None:
    write_board(tmp_path / "tasks.yaml", [])

    assert client.post("/api/release-stale?hours=-1").status_code == 422
    assert client.post("/api/release-stale?hours=8761").status_code == 422


def test_task_update_rejects_oversized_log_fields(client: TestClient, tmp_path: Path) -> None:
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "LIMEN-SEC-003",
                "title": "Valid task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-03",
                "dispatch_log": [],
            }
        ],
    )

    response = client.patch(
        "/api/tasks/LIMEN-SEC-003",
        json={"status": "done", "session_id": "x" * 129},
    )

    assert response.status_code == 422


def test_task_update_rejects_oversized_label_and_url_lists(client: TestClient, tmp_path: Path) -> None:
    write_board(
        tmp_path / "tasks.yaml",
        [
            {
                "id": "LIMEN-SEC-004",
                "title": "Valid task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-03",
                "dispatch_log": [],
            }
        ],
    )

    too_many_labels = {"labels": [f"label-{i}" for i in range(21)]}
    assert client.patch("/api/tasks/LIMEN-SEC-004", json=too_many_labels).status_code == 422

    too_many_urls = {
        "urls": ["https://github.com/4444J99/limen/issues/1" for _ in range(21)],
    }
    assert client.patch("/api/tasks/LIMEN-SEC-004", json=too_many_urls).status_code == 422
