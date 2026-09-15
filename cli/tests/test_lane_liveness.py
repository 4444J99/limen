from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("lane_liveness", ROOT / "scripts" / "lane-liveness.py")
assert SPEC and SPEC.loader
lane_liveness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lane_liveness)


def write_tasks(path: Path, tasks: list[dict]) -> None:
    if not tasks:
        path.joinpath("tasks.yaml").write_text("tasks: []\n")
        return
    path.joinpath("tasks.yaml").write_text("tasks:\n" + "\n".join(f"  - {task!r}" for task in tasks) + "\n")


def test_idle_catalog_lanes_are_not_failures(tmp_path, monkeypatch):
    write_tasks(tmp_path, [])
    monkeypatch.setattr(lane_liveness, "ROOT", tmp_path)
    monkeypatch.setattr(lane_liveness, "VENDORS", (SimpleNamespace(name="codex"),))

    report = lane_liveness.evaluate(tmp_path, "codex", datetime(2026, 9, 15, tzinfo=timezone.utc), 24)

    assert report["status"] == "pass"
    assert report["lanes"][0]["state"] == "idle"


def test_recent_and_stale_tasks_are_distinguished(tmp_path, monkeypatch):
    # Use YAML rather than Python repr so this fixture matches the production projection.
    tmp_path.joinpath("tasks.yaml").write_text(
        "tasks:\n"
        "  - id: recent\n"
        "    target_agent: codex\n"
        "    status: in_progress\n"
        "    dispatch_log:\n"
        "      - timestamp: '2026-09-15T12:00:00Z'\n"
        "  - id: old\n"
        "    target_agent: claude\n"
        "    status: dispatched\n"
        "    dispatch_log:\n"
        "      - timestamp: '2026-09-13T00:00:00Z'\n"
    )
    monkeypatch.setattr(lane_liveness, "ROOT", tmp_path)
    monkeypatch.setattr(
        lane_liveness,
        "VENDORS",
        (SimpleNamespace(name="codex"), SimpleNamespace(name="claude")),
    )
    now = datetime(2026, 9, 15, 13, 0, tzinfo=timezone.utc)

    recent = lane_liveness.evaluate(tmp_path, "codex", now, 24)
    stale = lane_liveness.evaluate(tmp_path, "claude", now, 24)

    assert recent["status"] == "pass"
    assert recent["lanes"][0]["state"] == "active"
    assert stale["status"] == "fail"
    assert stale["lanes"][0]["state"] == "stalled"


def test_unreadable_projection_is_unmeasured(tmp_path, monkeypatch):
    monkeypatch.setattr(lane_liveness, "ROOT", tmp_path)
    monkeypatch.setattr(lane_liveness, "VENDORS", (SimpleNamespace(name="codex"),))
    tmp_path.joinpath("tasks.yaml").write_text("tasks: [")

    report = lane_liveness.evaluate(tmp_path, "codex", datetime.now(timezone.utc), 24)

    assert report["status"] == "fail"
    assert report["unmeasured"] is True
    assert report["lanes"][0]["state"] == "unmeasured"
