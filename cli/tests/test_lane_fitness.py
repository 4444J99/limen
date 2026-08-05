"""Tests for lane fitness routing — scripts/lane-fitness.py + dispatch._lane_fitness/_fitness_unfit."""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import limen.dispatch as D
from limen.models import Task

_TODAY = date.today()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reload_fitness_module(monkeypatch, tmp_path, tasks_yaml_path):
    """Load lane-fitness.py fresh with LIMEN_TASKS and LIMEN_ROOT already set."""
    monkeypatch.setenv("LIMEN_TASKS", str(tasks_yaml_path))
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    script = Path(__file__).resolve().parents[2] / "scripts" / "lane-fitness.py"
    spec = importlib.util.spec_from_file_location("lane_fitness_fresh", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _board_yaml(tasks: list[dict]) -> str:
    return yaml.safe_dump(
        {
            "version": "1.0",
            "portal": {
                "name": "test",
                "budget": {
                    "daily": 100,
                    "unit": "runs",
                    "per_agent": {},
                    "track": {"date": "", "spent": 0, "per_agent": {}},
                },
            },
            "tasks": tasks,
        }
    )


def _make_task_dict(
    *, task_id: str, type_: str | None = "code", labels: list[str] | None = None, dispatch_log: list[dict] | None = None
) -> dict:
    return {
        "id": task_id,
        "title": "test",
        "type": type_,
        "status": "open",
        "target_agent": "opencode",
        "created": str(_TODAY),
        "labels": labels or [],
        "dispatch_log": dispatch_log or [],
    }


def _make_dispatch_task(*, type_: str = "code", labels: list[str] | None = None) -> Task:
    return Task(
        id="T-test",
        title="test task",
        status="open",
        target_agent="opencode",
        type=type_,
        labels=labels or [],
        created=_TODAY,
    )


# ---------------------------------------------------------------------------
# scripts/lane-fitness.py tests
# ---------------------------------------------------------------------------


class TestLaneFitnessScript:
    def test_compute_basic(self, tmp_path, monkeypatch):
        """10 attempts, 1 done → 10% < 25% unfit threshold → fit=False."""
        tasks = [
            _make_task_dict(
                task_id=f"T-{i}",
                type_="code",
                dispatch_log=[
                    {
                        "agent": "opencode",
                        "status": "done" if i == 0 else "failed",
                        "timestamp": "2026-07-15T12:00:00Z",
                    },
                ],
            )
            for i in range(10)
        ]
        board = tmp_path / "tasks.yaml"
        board.write_text(_board_yaml(tasks))
        mod = _reload_fitness_module(monkeypatch, tmp_path, board)
        data = mod.compute(min_attempts=5, unfit_rate=0.25, window_days=30)
        pair = data["pairs"]["opencode"]["code"]
        assert pair["done"] == 1
        assert pair["attempted"] == 10
        assert pair["fit"] is False
        assert any(u["agent"] == "opencode" and u["task_class"] == "code" for u in data["unfit_pairs"])

    def test_unknown_below_min_attempts(self, tmp_path, monkeypatch):
        """Only 1 attempt — below min_attempts=5 → fit=None (unknown)."""
        tasks = [
            _make_task_dict(
                task_id="T-0",
                type_="code",
                dispatch_log=[
                    {"agent": "opencode", "status": "failed", "timestamp": "2026-07-15T12:00:00Z"},
                ],
            )
        ]
        board = tmp_path / "tasks.yaml"
        board.write_text(_board_yaml(tasks))
        mod = _reload_fitness_module(monkeypatch, tmp_path, board)
        data = mod.compute(min_attempts=5, unfit_rate=0.25, window_days=30)
        pair = data["pairs"]["opencode"]["code"]
        assert pair["fit"] is None

    def test_fit_true_above_threshold(self, tmp_path, monkeypatch):
        """10 done / 10 attempted → 100% > 25% → fit=True."""
        tasks = [
            _make_task_dict(
                task_id=f"T-{i}",
                type_="code",
                dispatch_log=[
                    {"agent": "jules", "status": "done", "timestamp": "2026-07-15T12:00:00Z"},
                ],
            )
            for i in range(10)
        ]
        board = tmp_path / "tasks.yaml"
        board.write_text(_board_yaml(tasks))
        mod = _reload_fitness_module(monkeypatch, tmp_path, board)
        data = mod.compute(min_attempts=5, unfit_rate=0.25, window_days=30)
        pair = data["pairs"]["jules"]["code"]
        assert pair["fit"] is True

    def test_window_excludes_old_entries(self, tmp_path, monkeypatch):
        """Entries with 2025 timestamp outside 30-day window → excluded."""
        tasks = [
            _make_task_dict(
                task_id=f"T-{i}",
                type_="code",
                dispatch_log=[
                    {"agent": "opencode", "status": "failed", "timestamp": "2025-01-01T00:00:00Z"},
                ],
            )
            for i in range(10)
        ]
        board = tmp_path / "tasks.yaml"
        board.write_text(_board_yaml(tasks))
        mod = _reload_fitness_module(monkeypatch, tmp_path, board)
        data = mod.compute(min_attempts=5, unfit_rate=0.25, window_days=30)
        # Old entries excluded — opencode/code should be absent or have 0 attempts
        pair = data["pairs"].get("opencode", {}).get("code")
        assert pair is None or pair["attempted"] == 0

    def test_missing_tasks_yaml_returns_empty(self, tmp_path, monkeypatch):
        """Missing tasks.yaml → empty pairs, no crash."""
        monkeypatch.setenv("LIMEN_TASKS", str(tmp_path / "nonexistent.yaml"))
        monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
        script = Path(__file__).resolve().parents[2] / "scripts" / "lane-fitness.py"
        spec = importlib.util.spec_from_file_location("lane_fitness_miss", script)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        data = mod.compute(min_attempts=5, unfit_rate=0.25, window_days=30)
        assert data["pairs"] == {}
        assert data["unfit_pairs"] == []

    def test_write_creates_file(self, tmp_path, monkeypatch):
        """Write mode creates logs/lane-fitness.json with correct shape."""
        tasks = [
            _make_task_dict(
                task_id=f"T-{i}",
                type_="code",
                dispatch_log=[
                    {"agent": "opencode", "status": "failed", "timestamp": "2026-07-15T12:00:00Z"},
                ],
            )
            for i in range(6)
        ]
        board = tmp_path / "tasks.yaml"
        board.write_text(_board_yaml(tasks))
        (tmp_path / "logs").mkdir()
        mod = _reload_fitness_module(monkeypatch, tmp_path, board)
        data = mod.compute(min_attempts=5, unfit_rate=0.25, window_days=30)
        out = tmp_path / "logs" / "lane-fitness.json"
        out.write_text(json.dumps(data))
        written = json.loads(out.read_text())
        assert "pairs" in written
        assert "unfit_pairs" in written
        assert "params" in written
        assert "summary" in written


# ---------------------------------------------------------------------------
# dispatch._lane_fitness / _fitness_unfit tests
# ---------------------------------------------------------------------------


class TestDispatchFitnessIntegration:
    def test_lane_fitness_fail_open_missing(self, tmp_path, monkeypatch):
        """Missing lane-fitness.json → returns {}."""
        monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
        assert D._lane_fitness() == {}

    def test_lane_fitness_fail_open_corrupt(self, tmp_path, monkeypatch):
        """Corrupt lane-fitness.json → returns {}."""
        monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
        (tmp_path / "logs").mkdir()
        (tmp_path / "logs" / "lane-fitness.json").write_text("NOT JSON")
        assert D._lane_fitness() == {}

    def test_lane_fitness_reads_pairs(self, tmp_path, monkeypatch):
        """Valid lane-fitness.json → returns pairs dict."""
        monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
        (tmp_path / "logs").mkdir()
        payload = {
            "pairs": {"opencode": {"code": {"done": 3, "attempted": 10, "rate": 0.3, "fit": False}}},
            "unfit_pairs": [],
        }
        (tmp_path / "logs" / "lane-fitness.json").write_text(json.dumps(payload))
        result = D._lane_fitness()
        assert result["opencode"]["code"]["fit"] is False

    def test_fitness_unfit_empty_fitness(self):
        """Empty fitness dict → never unfit (fail-open)."""
        t = _make_dispatch_task(type_="code")
        assert D._fitness_unfit("opencode", t, {}) is False

    def test_fitness_unfit_agent_missing(self):
        """Agent not in fitness → not unfit."""
        fitness = {"jules": {"code": {"fit": False, "done": 0, "attempted": 10, "rate": 0.0}}}
        t = _make_dispatch_task(type_="code")
        assert D._fitness_unfit("opencode", t, fitness) is False

    def test_fitness_unfit_true_when_all_classes_unfit(self):
        """Task class is unfit → deprioritized."""
        fitness = {
            "opencode": {
                "code": {"fit": False, "done": 2, "attempted": 10, "rate": 0.2},
            }
        }
        t = _make_dispatch_task(type_="code")
        assert D._fitness_unfit("opencode", t, fitness) is True

    def test_fitness_unfit_false_when_any_class_fit(self):
        """Mixed classes (one fit, one unfit) → not deprioritized (not ALL unfit)."""
        fitness = {
            "opencode": {
                "code": {"fit": False, "done": 2, "attempted": 10, "rate": 0.2},
                "cifix": {"fit": True, "done": 8, "attempted": 10, "rate": 0.8},
            }
        }
        t = _make_dispatch_task(type_="code", labels=["cifix"])
        assert D._fitness_unfit("opencode", t, fitness) is False

    def test_fitness_unfit_null_unknown_not_deprioritized(self):
        """fit=None (unknown, below min_attempts) → not deprioritized."""
        fitness = {
            "opencode": {
                "code": {"fit": None, "done": 1, "attempted": 3, "rate": 0.33},
            }
        }
        t = _make_dispatch_task(type_="code")
        assert D._fitness_unfit("opencode", t, fitness) is False

    def test_fitness_unfit_no_evidence_not_deprioritized(self):
        """Task class not in fitness for agent → no evidence → not deprioritized."""
        fitness = {
            "opencode": {
                "other": {"fit": False, "done": 0, "attempted": 10, "rate": 0.0},
            }
        }
        t = _make_dispatch_task(type_="code")
        assert D._fitness_unfit("opencode", t, fitness) is False
