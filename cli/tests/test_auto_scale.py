from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from limen.tabularius import drain_once

ROOT = Path(__file__).resolve().parents[2]


class FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class FrozenDate:
    @staticmethod
    def today() -> dt.date:
        return dt.date(2026, 6, 6)


def load_auto_scale() -> ModuleType:
    spec = importlib.util.spec_from_file_location("limen_auto_scale", ROOT / "scripts" / "auto-scale.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_board(path: Path, tasks: list[dict], daily: int = 100) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "portal": {
                    "name": "Universal Task Intake",
                    "budget": {
                        "daily": daily,
                        "unit": "runs",
                        "track": {"date": "", "spent": 0, "per_agent": {}},
                    },
                },
                "tasks": tasks,
            },
            sort_keys=False,
        )
    )


def read_board(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def isolate_value_tier(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LIMEN_VALUE_REPOS", raising=False)
    monkeypatch.setenv("LIMEN_VALUE_REPOS_FILE", str(tmp_path / "missing-value-repos.json"))


def test_auto_scale_requires_github_token(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    auto_scale = load_auto_scale()
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert auto_scale.main() == 1

    assert "GITHUB_TOKEN is required" in capsys.readouterr().err


def test_auto_scale_noops_when_task_depth_is_met(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    auto_scale = load_auto_scale()
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {"id": "LIMEN-001", "title": "One", "target_agent": "jules", "created": "2026-06-01"},
            {"id": "LIMEN-002", "title": "Two", "target_agent": "jules", "created": "2026-06-01"},
        ],
        daily=2,
    )
    before = tasks_path.read_text()
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(auto_scale, "TASKS_FILE", tasks_path)
    monkeypatch.setattr(auto_scale.requests, "get", lambda *args, **kwargs: pytest.fail("unexpected GitHub call"))

    assert auto_scale.main() == 0

    assert tasks_path.read_text() == before
    assert "Task depth 2 already at or above 2." in capsys.readouterr().out


def test_auto_scale_adds_schema_shaped_tasks_and_skips_existing_urls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auto_scale = load_auto_scale()
    tasks_path = tmp_path / "tasks.yaml"
    duplicate_url = "https://github.com/a-organvm/existing/issues/1"
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-099",
                "title": "Existing",
                "repo": "a-organvm/existing",
                "type": "code",
                "target_agent": "jules",
                "priority": "medium",
                "budget_cost": 1,
                "status": "open",
                "urls": [duplicate_url],
                "created": "2026-06-01",
            }
        ],
        daily=3,
    )
    calls = []
    isolate_value_tier(monkeypatch, tmp_path)

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> FakeResponse:
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return FakeResponse(
            200,
            {
                "items": [
                    {"html_url": duplicate_url, "title": "Duplicate"},
                    {"html_url": "https://github.com/a-organvm/repo-one/issues/2", "title": "First issue"},
                    {"html_url": "https://github.com/a-organvm/repo-two/issues/3", "title": "Second issue"},
                ]
            },
        )

    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(auto_scale, "TASKS_FILE", tasks_path)
    # Control the org list explicitly (the module default consolidated to `organvm` post-move);
    # this test's fixtures use a-organvm, so pin the input here rather than asserting a default.
    monkeypatch.setattr(auto_scale, "ORGS", ["a-organvm"])
    monkeypatch.setattr(auto_scale, "date", FrozenDate)
    monkeypatch.setattr(auto_scale.requests, "get", fake_get)

    assert auto_scale.main() == 0

    board = read_board(tasks_path)
    assert len(board["tasks"]) == 1
    tickets = list((tmp_path / "logs" / "tickets" / "inbox").glob("*.json"))
    assert len(tickets) == 2
    drain_once(tasks_path)
    board = read_board(tasks_path)
    assert len(board["tasks"]) == 3
    assert len(calls) == 1
    assert calls[0]["url"] == "https://api.github.com/search/issues"
    assert calls[0]["params"]["q"] == "org:a-organvm is:issue is:open label:jules-ready"
    assert calls[0]["headers"]["Authorization"] == "token test-token"
    assert calls[0]["timeout"] == 30
    projected = [
        {
            k: task[k]
            for k in (
                "id",
                "title",
                "repo",
                "type",
                "target_agent",
                "priority",
                "budget_cost",
                "status",
                "labels",
                "urls",
                "created",
            )
        }
        for task in board["tasks"][1:]
    ]
    assert projected == [
        {
            "id": "LIMEN-100",
            "title": "First issue",
            "repo": "a-organvm/repo-one",
            "type": "code",
            "target_agent": "jules",
            "priority": "medium",
            "budget_cost": 1,
            "status": "open",
            "labels": ["jules-ready"],
            "urls": ["https://github.com/a-organvm/repo-one/issues/2"],
            "created": "2026-06-06",
        },
        {
            "id": "LIMEN-101",
            "title": "Second issue",
            "repo": "a-organvm/repo-two",
            "type": "code",
            "target_agent": "jules",
            "priority": "medium",
            "budget_cost": 1,
            "status": "open",
            "labels": ["jules-ready"],
            "urls": ["https://github.com/a-organvm/repo-two/issues/3"],
            "created": "2026-06-06",
        },
    ]


def test_auto_scale_reloads_under_queue_lock_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auto_scale = load_auto_scale()
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-001",
                "title": "Existing",
                "repo": "a-organvm/existing",
                "type": "code",
                "target_agent": "jules",
                "priority": "medium",
                "budget_cost": 1,
                "status": "open",
                "urls": ["https://github.com/a-organvm/existing/issues/1"],
                "created": "2026-06-01",
            }
        ],
        daily=3,
    )
    isolate_value_tier(monkeypatch, tmp_path)
    inserted_concurrent = False

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> FakeResponse:
        nonlocal inserted_concurrent
        if not inserted_concurrent:
            board = read_board(tasks_path)
            board["tasks"].append(
                {
                    "id": "LIMEN-002",
                    "title": "Concurrent heartbeat task",
                    "repo": "a-organvm/concurrent",
                    "type": "code",
                    "target_agent": "codex",
                    "priority": "high",
                    "budget_cost": 1,
                    "status": "open",
                    "urls": ["https://github.com/a-organvm/concurrent/issues/9"],
                    "created": "2026-06-06",
                }
            )
            tasks_path.write_text(yaml.safe_dump(board, sort_keys=False))
            inserted_concurrent = True
        return FakeResponse(
            200,
            {
                "items": [
                    {"html_url": "https://github.com/a-organvm/repo-one/issues/2", "title": "First issue"},
                ]
            },
        )

    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(auto_scale, "TASKS_FILE", tasks_path)
    monkeypatch.setattr(auto_scale, "ORGS", ["a-organvm"])
    monkeypatch.setattr(auto_scale, "date", FrozenDate)
    monkeypatch.setattr(auto_scale.requests, "get", fake_get)

    assert auto_scale.main() == 0

    drain_once(tasks_path)
    tasks = read_board(tasks_path)["tasks"]
    assert [task["id"] for task in tasks] == ["LIMEN-001", "LIMEN-002", "LIMEN-003"]
    assert tasks[1]["title"] == "Concurrent heartbeat task"
    assert tasks[2]["urls"] == ["https://github.com/a-organvm/repo-one/issues/2"]


def test_auto_scale_stops_repeated_duplicate_pages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    auto_scale = load_auto_scale()
    tasks_path = tmp_path / "tasks.yaml"
    duplicate_url = "https://github.com/a-organvm/existing/issues/1"
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-001",
                "title": "Existing",
                "repo": "a-organvm/existing",
                "type": "code",
                "target_agent": "jules",
                "priority": "medium",
                "budget_cost": 1,
                "status": "open",
                "urls": [duplicate_url],
                "created": "2026-06-01",
            }
        ],
        daily=2,
    )
    isolate_value_tier(monkeypatch, tmp_path)
    calls = []

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> FakeResponse:
        calls.append(params["page"])
        return FakeResponse(200, {"items": [{"html_url": duplicate_url, "title": "Duplicate"}]})

    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(auto_scale, "TASKS_FILE", tasks_path)
    monkeypatch.setattr(auto_scale, "ORGS", ["a-organvm"])
    monkeypatch.setattr(auto_scale.requests, "get", fake_get)

    assert auto_scale.main() == 0

    assert calls == [1, 2]
    assert len(read_board(tasks_path)["tasks"]) == 1
    assert "repeated page 2" in capsys.readouterr().err


def test_auto_scale_continues_after_search_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    auto_scale = load_auto_scale()
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-001",
                "title": "Existing",
                "repo": "a-organvm/existing",
                "type": "code",
                "target_agent": "jules",
                "priority": "medium",
                "budget_cost": 1,
                "status": "open",
                "urls": ["https://github.com/a-organvm/existing/issues/1"],
                "created": "2026-06-01",
            }
        ],
        daily=2,
    )

    def fake_get(url: str, *, params: dict, headers: dict, timeout: int) -> FakeResponse:
        return FakeResponse(500, {})

    isolate_value_tier(monkeypatch, tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(auto_scale, "TASKS_FILE", tasks_path)
    # Pin the searched org so the failure-path assertion matches the configured input, not the
    # post-move default (`organvm`).
    monkeypatch.setattr(auto_scale, "ORGS", ["a-organvm"])
    monkeypatch.setattr(auto_scale.requests, "get", fake_get)

    assert auto_scale.main() == 0

    assert len(read_board(tasks_path)["tasks"]) == 1
    assert "Search failed for a-organvm (page 1): HTTP 500" in capsys.readouterr().err
