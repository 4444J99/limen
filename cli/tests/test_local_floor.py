"""Local-floor routing (MANVMISSIO Phase 1) — ships DARK, armed only by the parity gate.

Pins the operator rule of 2026-07-09: nothing switches over until the math maths.
With LIMEN_LOCAL_FLOOR unset/0 the router must behave byte-identically to before;
armed, mechanical floor classes route to the unmetered ollama lane, reserved classes
never do, and a ledger-graded wasted class rolls back automatically.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from limen import dispatch
from limen.capacity import local_floor_classes, local_floor_enabled
from limen.models import Task

# route.py lives in scripts/ (not the limen package); import it directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
route = importlib.import_module("route")

HEALTH = {"codex": True, "claude": True, "agy": True, "opencode": True, "ollama": True, "jules": True}


def _scan_task(**overrides) -> dict:
    task = {"id": "t-floor-1", "title": "sweep links", "type": "scan", "repo": "organvm/limen", "labels": []}
    task.update(overrides)
    return task


def _arm(monkeypatch, model="qwen3:8b"):
    monkeypatch.setenv("LIMEN_LOCAL_FLOOR", "1")
    monkeypatch.setattr(route, "ollama_model", lambda: model)


# ---------------------------------------------------------------------------
# The arm switch (dark by default)
# ---------------------------------------------------------------------------


def test_dark_by_default(monkeypatch):
    monkeypatch.delenv("LIMEN_LOCAL_FLOOR", raising=False)
    assert not local_floor_enabled()
    monkeypatch.setattr(route, "ollama_model", lambda: "qwen3:8b")
    assert route._local_floor_lane(_scan_task(), HEALTH) is None


def test_dark_routing_is_unchanged_from_today(monkeypatch, tmp_path):
    monkeypatch.delenv("LIMEN_LOCAL_FLOOR", raising=False)
    monkeypatch.setattr(route, "ollama_model", lambda: "qwen3:8b")
    lane, _reason = route.route_task(_scan_task(), HEALTH, tmp_path, {}, {"codex": 10, "claude": 10, "agy": 10})
    assert lane != "ollama"


def test_armed_routes_floor_class_to_ollama(monkeypatch, tmp_path):
    _arm(monkeypatch)
    assert route._local_floor_lane(_scan_task(), HEALTH) == "ollama"
    lane, reason = route.route_task(_scan_task(), HEALTH, tmp_path, {}, {"codex": 10})
    assert lane == "ollama" and "floor" in reason


def test_kill_switch_zero_restores_today(monkeypatch):
    monkeypatch.setenv("LIMEN_LOCAL_FLOOR", "0")
    monkeypatch.setattr(route, "ollama_model", lambda: "qwen3:8b")
    assert route._local_floor_lane(_scan_task(), HEALTH) is None


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def test_floor_dark_when_no_model_pulled(monkeypatch):
    _arm(monkeypatch, model=None)
    assert route._local_floor_lane(_scan_task(), HEALTH) is None


def test_unhealthy_ollama_falls_through(monkeypatch):
    _arm(monkeypatch)
    health = dict(HEALTH, ollama=False)
    assert route._local_floor_lane(_scan_task(), health) is None


def test_reserved_classes_never_route_local(monkeypatch):
    _arm(monkeypatch)
    assert route._local_floor_lane(_scan_task(labels=["canon"]), HEALTH) is None
    assert route._local_floor_lane(_scan_task(labels=["long-horizon"]), HEALTH) is None


def test_non_floor_class_falls_through(monkeypatch):
    _arm(monkeypatch)
    assert route._local_floor_lane(_scan_task(type="code"), HEALTH) is None


def test_no_repo_falls_through(monkeypatch):
    _arm(monkeypatch)
    assert route._local_floor_lane(_scan_task(repo=None), HEALTH) is None


def test_class_set_env_override(monkeypatch):
    monkeypatch.setenv("LIMEN_LOCAL_FLOOR_CLASSES", "triage")
    assert local_floor_classes() == {"triage"}
    _arm(monkeypatch)
    assert route._local_floor_lane(_scan_task(), HEALTH) is None  # scan no longer a floor class
    assert route._local_floor_lane(_scan_task(type="triage"), HEALTH) == "ollama"


def test_ledger_waste_class_rolls_back(monkeypatch, tmp_path):
    _arm(monkeypatch)
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "ledger.json").write_text(json.dumps({"lanes": {"ollama": {"waste_classes": ["scan"]}}}))
    monkeypatch.setattr(route, "ROOT", tmp_path)
    assert route._local_floor_lane(_scan_task(), HEALTH) is None
    assert route._local_floor_lane(_scan_task(type="verify"), HEALTH) == "ollama"


def test_slow_label_still_escapes_to_jules(monkeypatch, tmp_path):
    _arm(monkeypatch)
    lane, _reason = route.route_task(_scan_task(labels=["slow"]), HEALTH, tmp_path, {}, {})
    assert lane == "jules"


# ---------------------------------------------------------------------------
# Dispatch artifact capture (kills the ollama _NOOP trap)
# ---------------------------------------------------------------------------


def test_ollama_stdout_lands_as_report_artifact(monkeypatch, tmp_path):
    task = Task(id="t-floor-2", title="sweep", type="scan", created="2026-07-09T00:00:00Z", target_agent="ollama")

    class FakeRun:
        returncode = 0
        stdout = "3 links checked, 0 broken"
        stderr = ""

    monkeypatch.setattr(dispatch, "_run_capture", lambda *a, **k: FakeRun())
    monkeypatch.setattr(dispatch, "_lane_run_env", lambda agent, wt, task: {})
    ok = dispatch._run_isolated_agent("ollama", task, tmp_path, ["ollama", "run", "m", "p"], 60)
    assert ok is True
    report = tmp_path / "reports" / "t-floor-2.md"
    assert report.exists() and "3 links checked" in report.read_text()


def test_non_ollama_agent_writes_no_report(monkeypatch, tmp_path):
    task = Task(id="t-floor-3", title="sweep", type="scan", created="2026-07-09T00:00:00Z", target_agent="codex")

    class FakeRun:
        returncode = 0
        stdout = "done"
        stderr = ""

    monkeypatch.setattr(dispatch, "_run_capture", lambda *a, **k: FakeRun())
    monkeypatch.setattr(dispatch, "_lane_run_env", lambda agent, wt, task: {})
    assert dispatch._run_isolated_agent("codex", task, tmp_path, ["codex"], 60) is True
    assert not (tmp_path / "reports").exists()
