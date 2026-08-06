from __future__ import annotations

import datetime as dt
import json

from limen import capacity, dispatch
from limen.capacity import lane_throughput_cap, lane_throughput_window
from limen.models import Budget, BudgetTrack, DispatchLogEntry, LimenFile, Portal, Task

NOW = dt.datetime(2026, 8, 6, 12, 0, tzinfo=dt.timezone.utc)


def _board(
    tasks: list[Task], *, per_agent: dict[str, int] | None = None, spent: dict[str, int] | None = None
) -> LimenFile:
    per_agent = per_agent if per_agent is not None else {"jules": 100}
    spent = spent if spent is not None else {agent: 0 for agent in per_agent}
    return LimenFile(
        portal=Portal(
            budget=Budget(
                daily=600,
                per_agent=per_agent,
                track=BudgetTrack(
                    date=NOW.date().isoformat(),
                    spent=sum(spent.values()),
                    per_agent=spent,
                    per_agent_reset={agent: NOW.isoformat() for agent in per_agent},
                ),
            )
        ),
        tasks=tasks,
    )


def _task_with_log(task_id: str, entries: list[DispatchLogEntry]) -> Task:
    return Task(
        id=task_id,
        title="t",
        target_agent="jules",
        status="open",
        created=NOW.date(),
        dispatch_log=entries,
    )


def _entry(status: str, *, hours_ago: float = 1.0, agent: str = "jules", session_id: str = "s-1") -> DispatchLogEntry:
    return DispatchLogEntry(
        timestamp=NOW - dt.timedelta(hours=hours_ago),
        agent=agent,
        session_id=session_id,
        status=status,
        output="",
    )


def _burst(n: int, status: str = "dispatched", **kw) -> list[DispatchLogEntry]:
    return [_entry(status, session_id=f"s-{i}", **kw) for i in range(n)]


def test_bootstrap_cap_never_zero_on_empty_board():
    board = _board([])
    cap = lane_throughput_cap(board, "jules", now=NOW)
    assert cap["mode"] == "bootstrap"
    assert cap["cap"] == 25
    assert cap["cap"] > 0


def test_full_target_earned_at_floor_rate():
    entries = _burst(30) + [_entry("done", session_id=f"d-{i}", hours_ago=2.0) for i in range(10)]
    board = _board([_task_with_log("T1", entries)])
    cap = lane_throughput_cap(board, "jules", now=NOW)
    assert cap["mode"] == "earned"
    assert cap["cap"] == 100
    assert cap["rate"] is not None and cap["rate"] >= 0.30


def test_throttled_when_landed_rate_below_floor():
    entries = _burst(50) + [_entry("done", session_id="d-0", hours_ago=2.0)]
    board = _board([_task_with_log("T1", entries)])
    cap = lane_throughput_cap(board, "jules", now=NOW)
    assert cap["mode"] == "throttled"
    # max(bootstrap 25, 3 x 1 landed) = 25, never below bootstrap
    assert cap["cap"] == 25
    assert "landed rate" in cap["reason"]


def test_throttled_ramp_scales_with_landings():
    entries = _burst(100) + [_entry("pr_open", session_id=f"p-{i}", hours_ago=2.0) for i in range(12)]
    board = _board([_task_with_log("T1", entries)])
    cap = lane_throughput_cap(board, "jules", now=NOW)
    assert cap["mode"] == "throttled"
    assert cap["cap"] == 36  # 3 x 12 landed


def test_window_excludes_old_entries():
    entries = _burst(40, hours_ago=24.0 * 10)
    board = _board([_task_with_log("T1", entries)])
    dispatched, landed = lane_throughput_window(board, "jules", now=NOW)
    assert dispatched == 0 and landed == 0


def test_dispatched_with_pr_url_counts_as_landed():
    entries = _burst(25) + [
        _entry("dispatched", session_id=f"https://github.com/o/r/pull/{i}", hours_ago=2.0) for i in range(8)
    ]
    board = _board([_task_with_log("T1", entries)])
    _, landed = lane_throughput_window(board, "jules", now=NOW)
    assert landed == 8


def test_kill_switch_disables_clamp(monkeypatch):
    monkeypatch.setenv("LIMEN_THROUGHPUT_GOVERNOR", "0")
    board = _board([])
    cap = lane_throughput_cap(board, "jules", now=NOW)
    assert cap["mode"] == "disabled"


def test_remaining_budget_clamped_by_governor_with_receipt(monkeypatch, tmp_path):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    board = _board([])  # cold start: governor bootstrap cap = 25
    remaining = dispatch._remaining_budget(board, "jules", 600)
    assert remaining == 25
    receipt = tmp_path / "logs" / "throughput-governor.jsonl"
    assert receipt.exists()
    row = json.loads(receipt.read_text().splitlines()[0])
    assert row["agent"] == "jules"
    assert row["mode"] == "bootstrap"
    assert row["clamped_remaining"] == 25


def test_remaining_budget_untouched_when_earned(monkeypatch, tmp_path):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    entries = _burst(30) + [_entry("done", session_id=f"d-{i}", hours_ago=2.0) for i in range(15)]
    board = _board([_task_with_log("T1", entries)])
    remaining = dispatch._remaining_budget(board, "jules", 600)
    assert remaining == 100
    assert not (tmp_path / "logs" / "throughput-governor.jsonl").exists()


def test_remaining_budget_governor_counts_todays_spend(monkeypatch, tmp_path):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    board = _board([], spent={"jules": 10})
    remaining = dispatch._remaining_budget(board, "jules", 600)
    assert remaining == 15  # bootstrap 25 minus 10 already spent


def test_lane_balance_blocker_when_jules_saturated_and_others_starved(monkeypatch):
    monkeypatch.setattr(
        capacity,
        "capacity_census",
        lambda board: [
            {
                "agent": agent,
                "kind": "local-cli",
                "reachable": True,
                "detail": "test lane",
                "command": [agent],
                "limit": 100,
                "spent": 0,
                "remaining": 100,
            }
            for agent in ("jules", "codex")
        ],
    )
    open_task = Task(id="OPEN", title="open work", target_agent="any", status="open", created=NOW.date())
    board = LimenFile(
        portal=Portal(
            budget=Budget(
                daily=600,
                per_agent={"jules": 100, "codex": 100},
                track=BudgetTrack(
                    date=NOW.date().isoformat(),
                    spent=100,
                    per_agent={"jules": 100, "codex": 0},
                    per_agent_reset={
                        "jules": (NOW - dt.timedelta(hours=20)).isoformat(),
                        "codex": (NOW - dt.timedelta(hours=4)).isoformat(),
                    },
                ),
            )
        ),
        tasks=[open_task],
    )
    snap = capacity.capacity_fill_snapshot(
        board,
        now=NOW,
        usage={
            "vendors": {
                "jules": {"health": "ok", "time_left_frac": 0.0},
                "codex": {"health": "ok", "time_left_frac": 0.0},
            }
        },
        agents=("jules", "codex"),
    )
    ids = [blocker["id"] for blocker in snap["blockers"]]
    assert "lane-balance-jules" in ids
