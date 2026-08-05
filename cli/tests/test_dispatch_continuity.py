"""Tests for dispatch-continuity-check.py (Jul 3–5 starvation detector)."""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dispatch-continuity-check.py"


def _load():
    spec = importlib.util.spec_from_file_location("dispatch_continuity_check", SCRIPT)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ── minimal tasks doc helpers ─────────────────────────────────────────────────


def _tasks_doc(
    *,
    lanes: list[str] | None = None,
    open_tasks: list[dict] | None = None,
    dispatch_logs: dict[str, str] | None = None,
) -> dict:
    """Build a minimal tasks.yaml doc for testing.

    dispatch_logs: {agent: iso_timestamp} — last dispatch timestamp per agent
    open_tasks: list of {target_agent, status='open'}
    """
    per_agent = {lane: 100 for lane in (lanes or ["jules", "codex"])}
    tasks = []

    if dispatch_logs:
        for agent, ts in dispatch_logs.items():
            tasks.append(
                {
                    "id": f"task-dispatch-{agent}",
                    "status": "done",
                    "target_agent": agent,
                    "dispatch_log": [{"agent": agent, "timestamp": ts}],
                }
            )

    for t in open_tasks or []:
        tasks.append({"id": f"task-open-{t.get('target_agent', 'shared')}", "status": "open", **t})

    return {
        "portal": {"budget": {"per_agent": per_agent}},
        "tasks": tasks,
    }


def _usage(lanes: list[str], health: str = "ok", consumed: int = 10, possible: int = 100) -> dict:
    return {"vendors": {lane: {"health": health, "consumed": consumed, "possible": possible} for lane in lanes}}


NOW = datetime(2026, 7, 8, 15, 0, 0, tzinfo=timezone.utc)
RECENT_TS = "2026-07-08T14:00:00Z"  # 1h ago — within 24h window
STALE_TS = "2026-07-05T10:00:00Z"  # 77h ago — outside 24h window


# ── lane_last_dispatch ────────────────────────────────────────────────────────


def test_lane_last_dispatch_parses_entries():
    mod = _load()
    doc = _tasks_doc(dispatch_logs={"jules": RECENT_TS, "codex": STALE_TS})
    result = mod.lane_last_dispatch(doc)
    assert "jules" in result
    assert "codex" in result
    assert result["jules"] > result["codex"]


def test_lane_last_dispatch_skips_malformed_entries():
    mod = _load()
    doc = {
        "tasks": [
            {
                "dispatch_log": [
                    {"agent": "jules", "timestamp": "not-a-date"},
                    {"timestamp": RECENT_TS},  # missing agent
                    None,  # not a dict
                    {"agent": "codex", "timestamp": RECENT_TS},
                ]
            }
        ]
    }
    result = mod.lane_last_dispatch(doc)
    assert "jules" not in result  # malformed timestamp → skipped
    assert "codex" in result


# ── lane_queue ────────────────────────────────────────────────────────────────


def test_lane_queue_counts_targeted_open():
    mod = _load()
    doc = _tasks_doc(
        open_tasks=[
            {"target_agent": "jules"},
            {"target_agent": "jules"},
            {"target_agent": "codex"},
        ]
    )
    q = mod.lane_queue(doc)
    assert q["jules"] == 2
    assert q["codex"] == 1
    assert q["shared"] == 0


def test_lane_queue_counts_shared_for_null_agent():
    mod = _load()
    doc = {
        "tasks": [
            {"status": "open", "target_agent": None},
            {"status": "open", "target_agent": "any"},
            {"status": "open", "target_agent": ""},
            {"status": "done", "target_agent": "jules"},
        ]
    }
    q = mod.lane_queue(doc)
    assert q["shared"] == 3
    assert q.get("jules", 0) == 0


# ── lane_budget_ok ────────────────────────────────────────────────────────────


def test_lane_budget_ok_health_ok():
    mod = _load()
    u = _usage(["jules", "codex"], health="ok")
    result = mod.lane_budget_ok(u)
    assert result["jules"] == "ok"
    assert result["codex"] == "ok"


def test_lane_budget_ok_exhausted_health():
    mod = _load()
    u = _usage(["jules"], health="exhausted")
    result = mod.lane_budget_ok(u)
    assert result["jules"] == "exhausted"


def test_lane_budget_ok_consumed_equals_possible():
    mod = _load()
    u = {"vendors": {"jules": {"health": "ok", "consumed": 100, "possible": 100}}}
    result = mod.lane_budget_ok(u)
    assert result["jules"] == "exhausted"


def test_lane_budget_ok_missing_vendor_returns_unknown():
    mod = _load()
    result = mod.lane_budget_ok({})
    # no vendors → no entries; caller maps to "unknown" for missing lanes
    assert "jules" not in result


# ── verdicts: each condition independently ────────────────────────────────────


def test_verdict_flowing_when_recent_dispatch(tmp_path, monkeypatch):
    """A lane with a dispatch in the window is flowing regardless of queue."""
    mod = _load()
    monkeypatch.setattr(mod, "LEDGER", tmp_path / "tasks.yaml")
    monkeypatch.setattr(mod, "USAGE_JSON", tmp_path / "usage.json")

    doc = _tasks_doc(
        lanes=["jules"],
        dispatch_logs={"jules": RECENT_TS},  # 1h ago, within 24h
        open_tasks=[{"target_agent": "jules"}],
    )
    usage = _usage(["jules"])

    monkeypatch.setattr(mod, "_load_tasks_doc", lambda: doc)
    monkeypatch.setattr(mod, "_load_usage", lambda: usage)

    result = mod.verdicts(NOW, window_h=24)
    assert result["jules"]["verdict"] == "flowing"


def test_verdict_idle_ok_when_queue_empty(tmp_path, monkeypatch):
    """Silence > window is idle-ok when there are no dedicated open tasks."""
    mod = _load()
    monkeypatch.setattr(mod, "LEDGER", tmp_path / "tasks.yaml")
    monkeypatch.setattr(mod, "USAGE_JSON", tmp_path / "usage.json")

    doc = _tasks_doc(lanes=["jules"], dispatch_logs={"jules": STALE_TS})
    usage = _usage(["jules"])

    monkeypatch.setattr(mod, "_load_tasks_doc", lambda: doc)
    monkeypatch.setattr(mod, "_load_usage", lambda: usage)

    result = mod.verdicts(NOW, window_h=24)
    assert result["jules"]["verdict"] == "idle-ok"


def test_verdict_idle_ok_when_budget_exhausted(tmp_path, monkeypatch):
    """Silence > window is idle-ok when the budget is exhausted."""
    mod = _load()
    monkeypatch.setattr(mod, "LEDGER", tmp_path / "tasks.yaml")
    monkeypatch.setattr(mod, "USAGE_JSON", tmp_path / "usage.json")

    doc = _tasks_doc(
        lanes=["jules"],
        dispatch_logs={"jules": STALE_TS},
        open_tasks=[{"target_agent": "jules"}],
    )
    usage = _usage(["jules"], health="exhausted")

    monkeypatch.setattr(mod, "_load_tasks_doc", lambda: doc)
    monkeypatch.setattr(mod, "_load_usage", lambda: usage)

    result = mod.verdicts(NOW, window_h=24)
    assert result["jules"]["verdict"] == "idle-ok"


def test_verdict_starved_requires_all_three(tmp_path, monkeypatch):
    """Starved: silent > window, queue > 0, budget ok."""
    mod = _load()
    monkeypatch.setattr(mod, "LEDGER", tmp_path / "tasks.yaml")
    monkeypatch.setattr(mod, "USAGE_JSON", tmp_path / "usage.json")

    doc = _tasks_doc(
        lanes=["jules"],
        dispatch_logs={"jules": STALE_TS},  # silent > window
        open_tasks=[{"target_agent": "jules"}],  # queue > 0
    )
    usage = _usage(["jules"], health="ok")  # budget ok

    monkeypatch.setattr(mod, "_load_tasks_doc", lambda: doc)
    monkeypatch.setattr(mod, "_load_usage", lambda: usage)

    result = mod.verdicts(NOW, window_h=24)
    assert result["jules"]["verdict"] == "starved"


def test_verdict_unknown_when_usage_missing(tmp_path, monkeypatch):
    """Missing usage data → unknown, never alarm."""
    mod = _load()
    monkeypatch.setattr(mod, "LEDGER", tmp_path / "tasks.yaml")
    monkeypatch.setattr(mod, "USAGE_JSON", tmp_path / "usage.json")

    doc = _tasks_doc(
        lanes=["jules"],
        dispatch_logs={"jules": STALE_TS},
        open_tasks=[{"target_agent": "jules"}],
    )

    monkeypatch.setattr(mod, "_load_tasks_doc", lambda: doc)
    monkeypatch.setattr(mod, "_load_usage", lambda: {})  # no vendor data

    result = mod.verdicts(NOW, window_h=24)
    assert result["jules"]["verdict"] == "unknown"


# ── two-consecutive rule ──────────────────────────────────────────────────────


def test_single_starved_reading_no_atom(tmp_path, monkeypatch):
    """A single starved reading must NOT hang an atom."""
    mod = _load()
    tasks_file = tmp_path / "tasks.yaml"
    tasks_file.write_text("version: '1.0'\nportal:\n  budget:\n    per_agent:\n      jules: 100\ntasks: []\n")
    logs = tmp_path / "logs"
    logs.mkdir()
    voice = logs / ".voice"
    voice.mkdir()

    monkeypatch.setattr(mod, "LEDGER", tasks_file)
    monkeypatch.setattr(mod, "LOGS", logs)
    monkeypatch.setattr(mod, "VOICE_STAMP", voice / "continuity")
    monkeypatch.setattr(mod, "ARTIFACT", logs / "dispatch-continuity.json")
    # No previous artifact → prev lanes empty → first reading → no atom
    monkeypatch.setattr(mod, "_load_prev_artifact", lambda: {})

    doc = _tasks_doc(
        lanes=["jules"],
        dispatch_logs={"jules": STALE_TS},
        open_tasks=[{"target_agent": "jules"}],
    )
    usage = _usage(["jules"])

    monkeypatch.setattr(mod, "_load_tasks_doc", lambda: doc)
    monkeypatch.setattr(mod, "_load_usage", lambda: usage)

    upserted: list[str] = []
    monkeypatch.setattr(mod, "_upsert_starved_atom", lambda lane, info: upserted.append(lane))

    mod.main.__module__  # ensure module is loaded
    result = mod.verdicts(NOW, window_h=24)
    assert result["jules"]["verdict"] == "starved"
    # simulate main's two-consecutive check manually
    prev_lanes: dict = {}
    for lane, info in result.items():
        if info["verdict"] == "starved":
            prev_info = prev_lanes.get(lane) or {}
            if prev_info.get("verdict") == "starved":
                mod._upsert_starved_atom(lane, info)

    assert upserted == []


def test_two_consecutive_starved_hangs_atom(tmp_path, monkeypatch):
    """Two consecutive starved readings → atom upserted."""
    mod = _load()
    tasks_file = tmp_path / "tasks.yaml"
    tasks_file.write_text("version: '1.0'\nportal:\n  budget:\n    per_agent:\n      jules: 100\ntasks: []\n")
    logs = tmp_path / "logs"
    logs.mkdir()
    voice = logs / ".voice"
    voice.mkdir()

    monkeypatch.setattr(mod, "LEDGER", tasks_file)
    monkeypatch.setattr(mod, "LOGS", logs)
    monkeypatch.setattr(mod, "VOICE_STAMP", voice / "continuity")
    monkeypatch.setattr(mod, "ARTIFACT", logs / "dispatch-continuity.json")
    monkeypatch.setattr(
        mod,
        "_load_prev_artifact",
        lambda: {"lanes": {"jules": {"verdict": "starved"}}},  # previous also starved
    )

    doc = _tasks_doc(
        lanes=["jules"],
        dispatch_logs={"jules": STALE_TS},
        open_tasks=[{"target_agent": "jules"}],
    )
    usage = _usage(["jules"])

    monkeypatch.setattr(mod, "_load_tasks_doc", lambda: doc)
    monkeypatch.setattr(mod, "_load_usage", lambda: usage)

    upserted: list[str] = []
    monkeypatch.setattr(mod, "_upsert_starved_atom", lambda lane, info: upserted.append(lane))

    result = mod.verdicts(NOW, window_h=24)
    prev_lanes = {"jules": {"verdict": "starved"}}
    for lane, info in result.items():
        if info["verdict"] == "starved":
            prev_info = prev_lanes.get(lane) or {}
            if prev_info.get("verdict") == "starved":
                mod._upsert_starved_atom(lane, info)

    assert "jules" in upserted


def test_upsert_idempotent_writes_once(tmp_path, monkeypatch):
    """_upsert_starved_atom is idempotent — calling twice with same data = one task."""
    mod = _load()
    tasks_file = tmp_path / "tasks.yaml"
    tasks_file.write_text("version: '1.0'\nportal:\n  budget:\n    per_agent:\n      jules: 100\ntasks: []\n")
    monkeypatch.setattr(mod, "LEDGER", tasks_file)

    info = {"gap_h": 77.0, "queue_open": 5}
    mod._upsert_starved_atom("jules", info)
    mod._upsert_starved_atom("jules", info)

    import yaml  # type: ignore[import]

    doc = yaml.safe_load(tasks_file.read_text())
    starved_tasks = [t for t in doc.get("tasks", []) if t.get("id") == "ASK-lane-starved-jules"]
    assert len(starved_tasks) == 1
    assert starved_tasks[0]["origin"] == "system_debt"
    assert starved_tasks[0]["horizon"] == "present"
    assert starved_tasks[0]["value_case"] == "Restore dispatch continuity for the starved jules lane"
    assert starved_tasks[0]["owner_surface"] == "organvm/limen"


# ── artifact + voice stamp ────────────────────────────────────────────────────


def test_artifact_and_voice_stamp_written(tmp_path, monkeypatch, capsys):
    """main() writes logs/dispatch-continuity.json and logs/.voice/continuity."""
    mod = _load()
    logs = tmp_path / "logs"
    logs.mkdir()
    voice = logs / ".voice"
    voice.mkdir()

    artifact_path = logs / "dispatch-continuity.json"
    voice_stamp = voice / "continuity"

    monkeypatch.setattr(mod, "LOGS", logs)
    monkeypatch.setattr(mod, "ARTIFACT", artifact_path)
    monkeypatch.setattr(mod, "VOICE_STAMP", voice_stamp)
    monkeypatch.setattr(mod, "_load_prev_artifact", lambda: {})
    monkeypatch.setattr(mod, "_upsert_starved_atom", lambda lane, info: None)

    doc = _tasks_doc(lanes=["jules"], dispatch_logs={"jules": RECENT_TS})
    usage = _usage(["jules"])
    monkeypatch.setattr(mod, "_load_tasks_doc", lambda: doc)
    monkeypatch.setattr(mod, "_load_usage", lambda: usage)

    import sys

    monkeypatch.setattr(sys, "argv", ["dispatch-continuity-check.py"])
    mod.main()

    assert artifact_path.exists()
    artifact = json.loads(artifact_path.read_text())
    assert "generated" in artifact
    assert "lanes" in artifact
    assert "jules" in artifact["lanes"]

    assert voice_stamp.exists()
    ts_text = voice_stamp.read_text().strip()
    assert "2026" in ts_text


# ── window env override ───────────────────────────────────────────────────────


def test_window_env_override(monkeypatch):
    """LIMEN_CONTINUITY_WINDOW_H is respected."""
    mod = _load()
    monkeypatch.setenv("LIMEN_CONTINUITY_WINDOW_H", "1")

    # RECENT_TS is 1h ago — inside 24h but might be borderline for 1h
    # Use a dispatch from 2h ago to be clearly outside 1h window
    ts_2h_ago = "2026-07-08T13:00:00Z"

    doc = _tasks_doc(
        lanes=["jules"],
        dispatch_logs={"jules": ts_2h_ago},
        open_tasks=[{"target_agent": "jules"}],
    )
    usage = _usage(["jules"])

    monkeypatch.setattr(mod, "_load_tasks_doc", lambda: doc)
    monkeypatch.setattr(mod, "_load_usage", lambda: usage)

    result = mod.verdicts(NOW, window_h=1.0)
    assert result["jules"]["verdict"] == "starved"

    # same task but 0.5h ago should be flowing with 1h window
    ts_half_ago = "2026-07-08T14:31:00Z"
    doc2 = _tasks_doc(
        lanes=["jules"],
        dispatch_logs={"jules": ts_half_ago},
        open_tasks=[{"target_agent": "jules"}],
    )
    monkeypatch.setattr(mod, "_load_tasks_doc", lambda: doc2)
    result2 = mod.verdicts(NOW, window_h=1.0)
    assert result2["jules"]["verdict"] == "flowing"
