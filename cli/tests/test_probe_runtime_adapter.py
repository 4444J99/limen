from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
OWNER_TOKEN = "owner-token"
CLIENT_TOKEN = "client-token"


def load_probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "limen_probe_runtime_adapter",
        ROOT / "scripts" / "probe-runtime-adapter.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def throughput() -> dict[str, Any]:
    return {
        "first_created": "2026-06-01",
        "current_date": "2026-06-20",
        "age_days": 20,
        "daily_capacity": 100,
        "expected_capacity_runs": 2000,
        "task_burndown_target_per_day": 1,
        "recorded_events": 2,
        "recorded_starts": 1,
        "recorded_finishes": 1,
        "done": 1,
        "not_done": 2,
        "unrecorded_capacity_runs": 1999,
        "by_event_status": {"dispatched": 1, "done": 1},
        "by_event_agent": {"jules": 2},
        "by_event_date": {"2026-06-20": 2},
    }


def status_payload(surface: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "total": 3,
        "completed": 1,
        "completion_rate": 0.333,
        "active": 1,
        "by_status": {"open": 1, "done": 1, "dispatched": 1},
        "generated_at": "2026-06-20T00:00:00Z",
        "throughput": throughput(),
    }
    payload: dict[str, Any] = {"status": "ok", "surface": surface, "summary": summary}
    if surface == "client":
        summary.update(
            {
                "stale_count": 1,
                "lifecycle": {"recover": 1, "verify": 1, "assign": 1, "archive": 0, "archived": 0},
                "budget": {"daily": 100},
                "top_repos": [{"repo": "4444J99/limen", "count": 3}],
                "active_tasks": [
                    {
                        "id": "LIMEN-ACTIVE",
                        "title": "Active task",
                        "repo": "4444J99/limen",
                        "target_agent": "jules",
                        "status": "dispatched",
                        "priority": "high",
                        "stale": True,
                        "phase": "recover",
                        "next_gate": "release stale claim or reassign with failure note",
                    }
                ],
            }
        )
        payload["storage"] = {"mode": "inline"}
    if surface == "internal":
        payload["portal"] = {"name": "Universal Task Intake"}
        payload["storage"] = {"mode": "inline"}
    return payload


def surface_entry(surface_id: str) -> dict[str, Any]:
    definitions = {
        "internal": ("Internal operations", "/", "/api/status", "owner", ["owner"]),
        "qa": ("QA and steering", "/qa", "/api/qa-status", "owner", ["owner"]),
        "client": ("Client status", "/client", "/api/client-status", "client", ["owner", "client"]),
        "public": ("Public status", "/public", "/api/public-status", "public", ["owner", "client", "public"]),
    }
    title, route, contract, persona, sanctions = definitions[surface_id]
    return {
        "id": surface_id,
        "title": title,
        "route": route,
        "contract": contract,
        "persona": persona,
        "sanctioned_personas": sanctions,
        "disclosure": f"{surface_id} disclosure",
    }


def manifest_payload(persona: str) -> dict[str, Any]:
    allowed = {
        "owner": ["internal", "client", "public", "qa"],
        "client": ["client", "public"],
        "public": ["public"],
    }[persona]
    contracts: dict[str, Any] = {}
    if "internal" in allowed:
        contracts["internal"] = {"path": "/api/status", "total": 3, "stale_count": 1}
    if "client" in allowed:
        contracts["client"] = {
            "path": "/api/client-status",
            "total": 3,
            "stale_count": 1,
            "max_active_tasks": 25,
            "includes_dispatch_logs": False,
        }
    if "public" in allowed:
        contracts["public"] = {
            "path": "/api/public-status",
            "total": 3,
            "includes_tasks": False,
            "includes_dispatch_logs": False,
        }
    if "qa" in allowed:
        contracts["qa"] = {
            "path": "/api/qa-status",
            "total": 3,
            "stale_count": 1,
            "verify_endpoint": "/api/tasks/{task_id}/verify",
            "assignment_endpoint": "/api/tasks/{task_id}/assign",
            "archive_endpoint": "/api/tasks/{task_id}/archive",
            "includes_dispatch_logs": False,
            "includes_task_context": False,
            "includes_task_urls": False,
        }
        contracts["readiness"] = {"path": "/api/readiness", "includes_dispatch_logs": False}
    return {
        "status": "ok",
        "persona": persona,
        "generated_at": "2026-06-20T00:00:00Z",
        "source": {
            "type": "cloudflare-worker",
            "task_file": "tasks.yaml",
            "api_runtime": "connected",
            "api_url_configured": True,
            "blocker": None,
            "storage": {"mode": "inline"},
        },
        "surfaces": [surface_entry(surface_id) for surface_id in allowed],
        "contracts": contracts,
    }


def lifecycle_item(task_id: str, phase: str) -> dict[str, Any]:
    return {
        "id": task_id,
        "title": f"{task_id} title",
        "repo": "4444J99/limen",
        "status": "open" if phase == "assign" else "done",
        "priority": "medium",
        "assignee": "jules",
        "phase": phase,
        "next_gate": f"{phase} gate",
        "stale": False,
        "has_issue": False,
        "has_pr": phase == "verify",
        "latest_event_at": "2026-06-20T00:00:00Z",
    }


def qa_payload(assign_ids: list[str] | None = None, archive_ready: int = 1, archived: int = 0) -> dict[str, Any]:
    assignment_queue = [lifecycle_item(task_id, "assign") for task_id in (assign_ids or [])]
    archive_queue = [lifecycle_item(f"DONE-{index}", "archive") for index in range(archive_ready)]
    return {
        "status": "ok",
        "surface": "qa",
        "generated_at": "2026-06-20T00:00:00Z",
        "lifecycle": {
            "total": len(assignment_queue) + archive_ready + archived,
            "assign": len(assignment_queue),
            "verify": 0,
            "recover": 0,
            "archive_ready": archive_ready,
            "archived": archived,
        },
        "steering": {
            "principle": "Every visible item is a portal into one task lifecycle.",
            "next_batch": assignment_queue,
            "qa_queue": [],
            "recovery_queue": [],
            "assignment_queue": assignment_queue,
            "archive_queue": archive_queue,
        },
        "mechanisms": [
            {
                "id": "release-stale",
                "label": "Release stale claims",
                "agent": "jules",
                "command": "POST /api/release-stale?hours=24&dry_run=false",
                "mode": "human-approved apply",
                "count": 0,
            },
            {
                "id": "qa-verify",
                "label": "Verify PR and runtime evidence",
                "agent": "qa",
                "command": "POST /api/tasks/{task_id}/verify",
                "mode": "human-approved evidence gate",
                "count": 0,
            },
            {
                "id": "assign-next",
                "label": "Assign or reassign next task",
                "agent": "steering",
                "command": "POST /api/tasks/{task_id}/assign",
                "mode": "human-approved assignment",
                "count": len(assignment_queue),
            },
            {
                "id": "archive-done",
                "label": "Archive closed evidence",
                "agent": "system",
                "command": "POST /api/tasks/{task_id}/archive",
                "mode": "human-approved archive",
                "count": archive_ready,
            },
        ],
    }


def readiness_payload() -> dict[str, Any]:
    return {
        "status": "ready",
        "generated_at": "2026-06-20T00:00:00Z",
        "agent": "jules",
        "counts": {"total": 3, "active": 1, "stale": 0, "open": 1, "open_jules": 1},
        "budget": {"daily": 100, "agent_limit": 100, "agent_spent": 0, "remaining": 100},
        "checks": [{"id": "api_runtime", "status": "pass", "detail": "runtime attached"}],
        "next_actions": ["No immediate action required"],
    }


class FakeRuntime:
    def __init__(self, probe: ModuleType) -> None:
        self.probe = probe
        self.calls: list[dict[str, Any]] = []
        self.tasks = {
            "TASK-DENIED": {"id": "TASK-DENIED", "status": "in_progress"},
            "TASK-VERIFY": {"id": "TASK-VERIFY", "status": "in_progress"},
            "TASK-ASSIGN": {
                "id": "TASK-ASSIGN",
                "repo": "organvm/limen",
                "status": "needs_human",
                "target_agent": "codex",
                "priority": "low",
                "budget_cost": 1,
            },
            "TASK-ARCHIVE": {"id": "TASK-ARCHIVE", "status": "done"},
        }

    def response(self, status: int, payload: dict[str, Any]) -> Any:
        return self.probe.Response(status, payload, json.dumps(payload))

    def request(
        self,
        base_url: str,
        path: str,
        token: str | None = None,
        method: str = "GET",
        body: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append({"base_url": base_url, "path": path, "token": token, "method": method, "body": body})
        route = path.split("?", 1)[0]
        if token not in (None, OWNER_TOKEN, CLIENT_TOKEN):
            return self.response(401, {"detail": "invalid token"})
        if route == "/health":
            return self.response(200, {"status": "ok"})
        if route == "/api/public-status":
            return self.response(200, status_payload("public"))
        if route == "/api/surface-manifest":
            if token == OWNER_TOKEN:
                return self.response(200, manifest_payload("owner"))
            if token == CLIENT_TOKEN:
                return self.response(200, manifest_payload("client"))
            return self.response(200, manifest_payload("public"))
        if route == "/api/client-status":
            if token in (OWNER_TOKEN, CLIENT_TOKEN):
                return self.response(200, status_payload("client"))
            return self.response(401, {"detail": "missing token"})
        if route == "/api/status":
            return self.owner_response(token, status_payload("internal"))
        if route == "/api/qa-status":
            assign_ids = ["TASK-ASSIGN"] if self.tasks["TASK-ASSIGN"]["status"] == "open" else []
            archive_ready = sum(1 for task in self.tasks.values() if task.get("status") == "done")
            archived = sum(1 for task in self.tasks.values() if task.get("status") == "archived")
            return self.owner_response(
                token, qa_payload(assign_ids=assign_ids, archive_ready=archive_ready, archived=archived)
            )
        if route == "/api/readiness":
            return self.owner_response(token, readiness_payload())
        if route == "/api/release-stale":
            return self.owner_response(token, {"status": "dry_run", "candidates": []})
        if route == "/api/dispatch":
            return self.owner_response(token, {"status": "dry_run", "candidates": []})
        if route.startswith("/api/tasks/"):
            return self.task_response(route, token, method, body or {})
        return self.response(404, {"detail": "not found"})

    def owner_response(self, token: str | None, payload: dict[str, Any]) -> Any:
        if token == OWNER_TOKEN:
            return self.response(200, payload)
        if token == CLIENT_TOKEN:
            return self.response(403, {"detail": "client persona is not sanctioned for this endpoint"})
        return self.response(401, {"detail": "missing token"})

    def task_response(self, route: str, token: str | None, method: str, body: dict[str, Any]) -> Any:
        parts = route.removeprefix("/api/tasks/").split("/")
        task_id = parts[0]
        action = parts[1] if len(parts) > 1 else None
        if token == CLIENT_TOKEN:
            return self.response(403, {"detail": "client persona is not sanctioned for this endpoint"})
        if token != OWNER_TOKEN:
            return self.response(401, {"detail": "missing token"})
        task = self.tasks[task_id]
        if method == "GET" and action is None:
            return self.response(200, task)
        if method != "POST":
            return self.response(405, {"detail": "method not allowed"})
        if action == "verify":
            task["status"] = body.get("status", "done")
            return self.response(200, {"status": "verified", "verified_status": task["status"], "task": task})
        if action == "assign":
            task.update(
                {
                    "target_agent": body["target_agent"],
                    "priority": body["priority"],
                    "budget_cost": body["budget_cost"],
                    "status": body["status"],
                    "predicate": body["predicate"],
                    "receipt_target": body["receipt_target"],
                }
            )
            return self.response(
                200,
                {"status": "assigned", "task": task, "changed": ["target_agent", "priority", "budget_cost", "status"]},
            )
        if action == "archive":
            task["status"] = "archived"
            return self.response(200, {"status": "archived", "task": task})
        return self.response(404, {"detail": "not found"})


def run_probe_main(monkeypatch: pytest.MonkeyPatch, probe: ModuleType, fake: FakeRuntime, args: list[str]) -> None:
    monkeypatch.setattr(probe, "request", fake.request)
    monkeypatch.setattr(sys, "argv", ["probe-runtime-adapter.py", *args])
    probe.main()


def test_main_probes_persona_surfaces_and_dry_run_controls(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = load_probe()
    fake = FakeRuntime(probe)

    run_probe_main(
        monkeypatch,
        probe,
        fake,
        ["--api-url", "https://runtime.test", "--owner-token", OWNER_TOKEN, "--client-token", CLIENT_TOKEN],
    )

    assert "Runtime adapter probe passed" in capsys.readouterr().out
    assert any(call["path"] == "/api/surface-manifest" and call["token"] is None for call in fake.calls)
    assert any(
        call["path"] == "/api/dispatch" and call["method"] == "POST" and call["body"]["live"] is False
        for call in fake.calls
    )
    assert any(
        call["path"] == "/api/release-stale?hours=24&dry_run=true" and call["token"] == OWNER_TOKEN
        for call in fake.calls
    )


def test_main_verifies_optional_owner_mutations(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = load_probe()
    fake = FakeRuntime(probe)

    run_probe_main(
        monkeypatch,
        probe,
        fake,
        [
            "--api-url",
            "https://runtime.test",
            "--owner-token",
            OWNER_TOKEN,
            "--client-token",
            CLIENT_TOKEN,
            "--task-id",
            "TASK-DENIED",
            "--verify-task-id",
            "TASK-VERIFY",
            "--assign-task-id",
            "TASK-ASSIGN",
            "--archive-task-id",
            "TASK-ARCHIVE",
        ],
    )

    assert "Runtime adapter probe passed" in capsys.readouterr().out
    assert fake.tasks["TASK-VERIFY"]["status"] == "done"
    assert fake.tasks["TASK-ASSIGN"]["target_agent"] == "jules"
    assert fake.tasks["TASK-ASSIGN"]["status"] == "open"
    assert fake.tasks["TASK-ASSIGN"]["predicate"].startswith('test "$(gh pr list')
    assert fake.tasks["TASK-ASSIGN"]["receipt_target"] == "github:organvm/limen:pull-request:TASK-ASSIGN"
    assert fake.tasks["TASK-ARCHIVE"]["status"] == "archived"


def test_request_encodes_json_and_decodes_success(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = load_probe()
    seen: dict[str, Any] = {}

    class FakeHTTPResponse:
        status = 202

        def __enter__(self) -> "FakeHTTPResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"accepted": true}'

    def fake_urlopen(request: Any, timeout: int) -> FakeHTTPResponse:
        seen["url"] = request.full_url
        seen["method"] = request.get_method()
        seen["body"] = request.data
        seen["headers"] = dict(request.header_items())
        seen["timeout"] = timeout
        return FakeHTTPResponse()

    monkeypatch.setattr(probe.urllib.request, "urlopen", fake_urlopen)

    response = probe.request(
        "https://runtime.test/base",
        "/api/dispatch",
        token="secret-token",
        method="POST",
        body={"live": False},
    )

    assert response.status == 202
    assert response.payload == {"accepted": True}
    assert seen["url"] == "https://runtime.test/base/api/dispatch"
    assert seen["method"] == "POST"
    assert json.loads(seen["body"].decode("utf-8")) == {"live": False}
    assert seen["headers"]["Authorization"] == "Bearer secret-token"
    assert seen["timeout"] == 20


def test_request_returns_http_error_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = load_probe()

    def fake_urlopen(request: Any, timeout: int) -> Any:
        raise probe.urllib.error.HTTPError(
            request.full_url,
            418,
            "teapot",
            hdrs={},
            fp=io.BytesIO(b'{"detail": "short and stout"}'),
        )

    monkeypatch.setattr(probe.urllib.request, "urlopen", fake_urlopen)

    response = probe.request("https://runtime.test", "/api/status", token="wrong")

    assert response.status == 418
    assert response.payload == {"detail": "short and stout"}
    assert "short and stout" in response.text


def test_private_field_guard_rejects_redaction_regressions() -> None:
    probe = load_probe()

    with pytest.raises(SystemExit) as exc:
        probe.assert_no_private_fields(
            {"summary": {"active_tasks": [{"id": "LIMEN-001", "dispatch_log": []}]}},
            "client status",
        )

    assert exc.value.code == 1


def test_schema_validation_rejects_contract_shape_drift() -> None:
    probe = load_probe()

    with pytest.raises(SystemExit) as exc:
        probe.assert_schema(
            {"status": "ok", "surface": "public", "summary": {"total": "3", "by_status": {}, "generated_at": "now"}},
            "status-summary.schema.json",
            "public status",
        )

    assert exc.value.code == 1
