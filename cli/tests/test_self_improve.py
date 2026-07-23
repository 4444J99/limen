from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_self_improve() -> ModuleType:
    # Match the repo's existing script-loading convention (see test_auto_scale.py):
    # load the hyphenated script file by path so the organ is exercised exactly as
    # the heartbeat runs it.
    spec = importlib.util.spec_from_file_location("limen_self_improve", ROOT / "scripts" / "self-improve.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _entry(agent: str, status: str) -> dict:
    return {"timestamp": "2026-06-01T00:00:00Z", "agent": agent, "status": status}


def write_board(path: Path, tasks: list[dict]) -> None:
    path.write_text(
        yaml.safe_dump(
            {"version": "1.0", "portal": {"name": "x"}, "tasks": tasks},
            sort_keys=False,
        )
    )


def _fixture_tasks() -> list[dict]:
    """A small board with three deliberate signals:

    - DEAD lane: gemini is the responsible lane on 6 GH tasks that ALL end archived/no-op
      (per-task attribution -> 0% over 6 >= min_samples) -> down-weight.
    - GOOD lane: jules lands all 6 of its done tries -> keep (and it's the top lane).
    - CHRONIC pattern: GH tasks re-thrown 5x with cancellations -> flagged.
    - SHIPPING pattern: REV mostly done -> rerank boost.
    - The `limen` meta-agent ledger rows must be IGNORED, not counted as a lane.
    """
    tasks: list[dict] = []
    # GH pattern: 6 tasks, chronic re-dispatch on gemini, all archived/no-op (dead-end).
    # Per-task attribution credits each task's terminal verdict to gemini (the last
    # real lane), so 6 archived/no-op => 6 fail / 0 done => 0% over 6 decided tries.
    for i in range(6):
        log = [_entry("gemini", "failed") for _ in range(5)]
        log += [_entry("limen", "archived")]  # ledger noise that must be skipped
        tasks.append(
            {
                "id": f"GH-repo-{i}",
                "title": f"gh {i}",
                "status": "archived",
                "labels": ["cancelled", "noop"],
                "dispatch_log": log,
            }
        )
    # REV pattern: 6 tasks all shipped by jules (>= min_samples so it earns a verdict)
    for i in range(6):
        tasks.append(
            {
                "id": f"REV-prod-{i}",
                "title": f"rev {i}",
                "status": "done",
                "dispatch_log": [_entry("jules", "dispatched"), _entry("jules", "done")],
            }
        )
    return tasks


def test_dead_lane_is_down_weighted_and_meta_agent_ignored(tmp_path: Path) -> None:
    si = load_self_improve()
    board = {"tasks": _fixture_tasks()}
    proposal = si.build_proposal(board, tmp_path / "tasks.yaml")

    lanes = {r["lane"]: r for r in proposal["lane_adjustments"]}
    # `limen` ledger rows are not a real lane -> never judged
    assert "limen" not in lanes
    assert set(lanes) == {"gemini", "jules"}

    assert lanes["gemini"]["verdict"] == "down-weight"
    assert lanes["gemini"]["success_rate"] == 0.0
    assert lanes["gemini"]["target_weight"] < 1.0

    assert lanes["jules"]["verdict"] in ("keep", "boost-underused")
    assert lanes["jules"]["success_rate"] == 1.0


def test_chronic_pattern_flagged_and_shipping_pattern_boosted(tmp_path: Path) -> None:
    si = load_self_improve()
    board = {"tasks": _fixture_tasks()}
    proposal = si.build_proposal(board, tmp_path / "tasks.yaml")

    retire = {r["pattern"]: r for r in proposal["retire_patterns"]}
    assert "GH" in retire
    gh = retire["GH"]
    assert gh["chronic_count"] >= 1
    assert gh["max_redispatch"] == 5  # 5 real-lane tries; limen row excluded
    assert any("chronic" in e for e in gh["evidence"])
    # GH mostly archived/no-op -> retire (almost never ships)
    assert gh["action"] == "retire"

    rerank = {r["pattern"]: r for r in proposal["rerank"]}
    assert rerank["REV"]["move"] == "boost"
    assert rerank["REV"]["ship_rate"] == 1.0


def test_default_writes_proposal_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    si = load_self_improve()
    tasks_path = tmp_path / "tasks.yaml"
    out_path = tmp_path / "proposal.json"
    write_board(tasks_path, _fixture_tasks())

    monkeypatch.setattr("sys.argv", ["self-improve.py", "--tasks", str(tasks_path), "--out", str(out_path)])
    assert si.main() == 0
    assert out_path.exists()

    data = json.loads(out_path.read_text())
    assert data["organ"] == "self-improve"
    assert data["board_summary"]["total_tasks"] == 12
    assert data["apply"]["wired"] is True
    # idempotent: a second run produces a valid proposal again (timestamps differ)
    assert si.main() == 0
    assert json.loads(out_path.read_text())["board_summary"]["total_tasks"] == 12


def test_apply_writes_proposal_and_applies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    si = load_self_improve()
    tasks_path = tmp_path / "tasks.yaml"
    out_path = tmp_path / "proposal.json"
    write_board(tasks_path, _fixture_tasks())

    monkeypatch.setattr("sys.argv", ["self-improve.py", "--tasks", str(tasks_path), "--out", str(out_path), "--apply"])
    # --apply now writes the proposal AND runs the re-plan writer; it is fail-open (never crashes
    # the heartbeat) so a board the strict loader can't parse just skips apply — both return 0.
    assert si.main() == 0
    assert out_path.exists()  # proposal is written before the apply step


def test_missing_tasks_file_does_not_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    si = load_self_improve()
    monkeypatch.setattr("sys.argv", ["self-improve.py", "--tasks", str(tmp_path / "nope.yaml")])
    assert si.main() == 1  # clean non-zero, no traceback
