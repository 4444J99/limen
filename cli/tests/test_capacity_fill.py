from __future__ import annotations

import datetime as dt

from limen import capacity
from limen.models import Budget, BudgetTrack, DispatchLogEntry, LimenFile, Portal, Task


def _board(
    per_agent: dict[str, int],
    spent: dict[str, int],
    reset: dict[str, str],
    tasks: list[Task],
) -> LimenFile:
    return LimenFile(
        portal=Portal(
            budget=Budget(
                daily=600,
                per_agent=per_agent,
                track=BudgetTrack(
                    date="2026-06-29",
                    spent=sum(spent.values()),
                    per_agent=spent,
                    per_agent_reset=reset,
                ),
            )
        ),
        tasks=tasks,
    )


def _census(*agents: str) -> list[capacity.CapacityRow]:
    rows: list[capacity.CapacityRow] = []
    for agent in agents:
        rows.append(
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
        )
    return rows


def test_claude_daily_floor_is_a_capacity_fill_blocker(monkeypatch):
    now = dt.datetime(2026, 6, 29, 22, 0, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(capacity, "capacity_census", lambda board: _census("claude"))
    board = _board(
        {"claude": 100},
        {"claude": 0},
        {"claude": (now - dt.timedelta(hours=5)).isoformat()},
        [Task(id="OPEN", title="open work", target_agent="any", status="open", created=now.date())],
    )
    snap = capacity.capacity_fill_snapshot(
        board,
        now=now,
        usage={"vendors": {"claude": {"health": "ok", "time_left_frac": 0.0}}},
        agents=("claude",),
    )

    row = snap["rows"][0]
    assert row["target"] == 15
    assert row["expected_now"] == 15
    assert row["status"] == "underfilled"
    assert snap["blockers"][0]["id"] == "lane-fill-claude"


def test_failed_attempts_do_not_satisfy_productive_fill(monkeypatch):
    now = dt.datetime(2026, 6, 29, 22, 0, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(capacity, "capacity_census", lambda board: _census("gemini"))
    tasks = []
    for idx in range(7):
        tasks.append(
            Task(
                id=f"G{idx}",
                title="gemini try",
                target_agent="gemini",
                status="open",
                created=now.date(),
                dispatch_log=[
                    DispatchLogEntry(
                        timestamp=now,
                        agent="gemini",
                        session_id="test",
                        status="failed->jules",
                    )
                ],
            )
        )
    board = _board(
        {"gemini": 10},
        {"gemini": 0},
        {"gemini": (now - dt.timedelta(hours=16)).isoformat()},
        tasks,
    )
    snap = capacity.capacity_fill_snapshot(
        board,
        now=now,
        usage={"vendors": {"gemini": {"health": "ok", "time_left_frac": 0.3}}},
        agents=("gemini",),
    )

    row = snap["rows"][0]
    assert row["attempts"] == 7
    assert row["productive"] == 0
    assert row["expected_now"] == 7
    assert row["status"] == "unproductive"


def test_depleted_usage_lane_is_not_reported_as_underfilled(monkeypatch):
    now = dt.datetime(2026, 6, 29, 22, 0, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(capacity, "capacity_census", lambda board: _census("codex"))
    board = _board(
        {"codex": 100},
        {"codex": 1},
        {"codex": (now - dt.timedelta(hours=5)).isoformat()},
        [Task(id="OPEN", title="open work", target_agent="any", status="open", created=now.date())],
    )
    snap = capacity.capacity_fill_snapshot(
        board,
        now=now,
        usage={
            "vendors": {
                "codex": {
                    "health": "throttle",
                    "time_left_frac": 0.0,
                    "signal": "tokens",
                    "consumed": 123,
                }
            }
        },
        agents=("codex",),
    )

    row = snap["rows"][0]
    assert row["status"] == "depleted"
    assert snap["status"] == "healthy"


def test_no_scheduled_work_for_underfilled_lane_blocks(monkeypatch):
    now = dt.datetime(2026, 6, 29, 22, 0, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(capacity, "capacity_census", lambda board: _census("opencode"))
    board = _board(
        {"opencode": 100},
        {"opencode": 1},
        {"opencode": (now - dt.timedelta(hours=23)).isoformat()},
        [Task(id="HUMAN", title="human gate", target_agent="human", status="needs_human", created=now.date())],
    )
    snap = capacity.capacity_fill_snapshot(
        board,
        now=now,
        usage={"vendors": {"opencode": {"health": "ok", "time_left_frac": 0.0}}},
        agents=("opencode",),
    )

    row = snap["rows"][0]
    assert row["status"] == "no_work"
    assert snap["status"] == "blocked"
    assert snap["blockers"][0]["id"] == "lane-fill-opencode"
