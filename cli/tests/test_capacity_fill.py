from __future__ import annotations

import datetime as dt

from limen import capacity
from limen.capacity import derived_daily_floor, derived_floor_from_budget
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
    now = dt.datetime(2026, 6, 29, 22, 0, tzinfo=dt.UTC)
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
    now = dt.datetime(2026, 6, 29, 22, 0, tzinfo=dt.UTC)
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
    # expected_now is derived from the floor (ceil(budget×0.25)=3) × progress(0.7) ≈ 2,
    # not the raw budget (10) — the derived-floor fix for codex/jules starvation.
    assert row["expected_now"] >= 1
    assert row["attempts"] >= row["expected_now"]
    assert row["status"] == "unproductive"


def test_depleted_usage_lane_is_not_reported_as_underfilled(monkeypatch):
    now = dt.datetime(2026, 6, 29, 22, 0, tzinfo=dt.UTC)
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
                    "health": "exhausted",
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
    now = dt.datetime(2026, 6, 29, 22, 0, tzinfo=dt.UTC)
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


# ---------------------------------------------------------------------------
# derived_floor_from_budget / derived_daily_floor — precedence tests
# ---------------------------------------------------------------------------


def test_derived_floor_env_wins(monkeypatch):
    """Env var LIMEN_<AGENT>_DAILY_TASKS takes highest precedence."""
    monkeypatch.setenv("LIMEN_CODEX_DAILY_TASKS", "42")
    assert derived_floor_from_budget("codex", {"codex": 100}) == 42


def test_derived_floor_defaults_dict_second(monkeypatch):
    """DEFAULT_DAILY_TASK_TARGETS[agent] wins over budget×frac."""
    monkeypatch.delenv("LIMEN_CLAUDE_DAILY_TASKS", raising=False)
    # claude is in DEFAULT_DAILY_TASK_TARGETS with 15; budget here is 1000
    assert derived_floor_from_budget("claude", {"claude": 1000}) == 15


def test_derived_floor_budget_frac_default(monkeypatch):
    """Without env or defaults, floor = ceil(budget × 0.25)."""
    monkeypatch.delenv("LIMEN_CODEX_DAILY_TASKS", raising=False)
    monkeypatch.delenv("LIMEN_LANE_FLOOR_FRAC", raising=False)
    assert derived_floor_from_budget("codex", {"codex": 100}) == 25


def test_derived_floor_budget_frac_env_override(monkeypatch):
    """LIMEN_LANE_FLOOR_FRAC=0.1 changes the fraction used."""
    monkeypatch.delenv("LIMEN_CODEX_DAILY_TASKS", raising=False)
    monkeypatch.setenv("LIMEN_LANE_FLOOR_FRAC", "0.1")
    assert derived_floor_from_budget("codex", {"codex": 100}) == 10


def test_derived_floor_agent_absent_returns_zero(monkeypatch):
    """Agent not in budget map (and not in defaults) → floor = 0."""
    monkeypatch.delenv("LIMEN_GEMINI_DAILY_TASKS", raising=False)
    assert derived_floor_from_budget("gemini", {}) == 0


def test_derived_floor_jules_vendor_quota_default(monkeypatch):
    """Jules targets its full 100/day vendor quota even with no budget entry."""
    monkeypatch.delenv("LIMEN_JULES_DAILY_TASKS", raising=False)
    assert derived_floor_from_budget("jules", {}) == 100


def test_derived_floor_minimum_one_when_budget_exists(monkeypatch):
    """Even a tiny budget gives floor=1 (never 0 when lane has any budget)."""
    monkeypatch.delenv("LIMEN_CODEX_DAILY_TASKS", raising=False)
    monkeypatch.setenv("LIMEN_LANE_FLOOR_FRAC", "0.001")
    # 1 × 0.001 = 0.001, ceil → 1
    assert derived_floor_from_budget("codex", {"codex": 1}) == 1


def test_derived_floor_bad_frac_falls_back_to_default(monkeypatch):
    """A non-numeric LIMEN_LANE_FLOOR_FRAC falls back to 0.25."""
    monkeypatch.delenv("LIMEN_CODEX_DAILY_TASKS", raising=False)
    monkeypatch.setenv("LIMEN_LANE_FLOOR_FRAC", "not-a-float")
    assert derived_floor_from_budget("codex", {"codex": 100}) == 25


def test_derived_daily_floor_reads_board(monkeypatch):
    """derived_daily_floor extracts per_agent from a board object (budget×frac path)."""
    monkeypatch.delenv("LIMEN_GEMINI_DAILY_TASKS", raising=False)
    monkeypatch.delenv("LIMEN_LANE_FLOOR_FRAC", raising=False)
    # gemini has no DEFAULT_DAILY_TASK_TARGETS entry, so the budget×frac path is exercised
    # (jules now short-circuits at its 100/day vendor-quota default).
    board = _board({"gemini": 100}, {}, {}, [])
    assert derived_daily_floor("gemini", board) == 25


def test_daily_task_target_now_returns_derived_floor(monkeypatch):
    """_daily_task_target now delegates to derived_daily_floor (not raw budget)."""
    monkeypatch.delenv("LIMEN_CODEX_DAILY_TASKS", raising=False)
    monkeypatch.delenv("LIMEN_LANE_FLOOR_FRAC", raising=False)
    board = _board({"codex": 100}, {}, {}, [])
    # Old behavior: returned raw budget = 100. New: returns ceil(100 × 0.25) = 25.
    assert capacity._daily_task_target("codex", board) == 25


def test_codex_fill_snapshot_uses_derived_floor(monkeypatch):
    """capacity_fill_snapshot with codex budget=100 reports target=25, not 100.

    This is the canonical starvation fix: the Jul 3–5 period saw codex report 5/100
    as its fill state, making the board look like only 5% utilization when 25/day
    would be a sensible target and 5 is a real underfill — not a misleading one.
    """
    now = dt.datetime(2026, 7, 5, 22, 0, tzinfo=dt.UTC)
    monkeypatch.setattr(capacity, "capacity_census", lambda board: _census("codex"))
    monkeypatch.delenv("LIMEN_CODEX_DAILY_TASKS", raising=False)
    monkeypatch.delenv("LIMEN_LANE_FLOOR_FRAC", raising=False)
    board = _board(
        {"codex": 100},
        {"codex": 5},
        {"codex": (now - dt.timedelta(hours=22)).isoformat()},
        [Task(id="OPEN", title="open work", target_agent="any", status="open", created=now.date())],
    )
    snap = capacity.capacity_fill_snapshot(
        board,
        now=now,
        usage={"vendors": {"codex": {"health": "ok", "time_left_frac": 0.0}}},
        agents=("codex",),
    )
    row = snap["rows"][0]
    assert row["target"] == 25, f"expected derived floor 25 but got {row['target']}"
    assert row["status"] == "underfilled"
