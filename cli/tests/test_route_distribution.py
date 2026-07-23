"""Regression test for the router serialization bug.

On 2026-06-19 the fleet was found serialized onto codex: route.py's _pick_local did
`for v in ("codex","claude","agy","opencode"): if healthy: return v` — always returning
the first healthy lane (codex), starving claude/agy/jules and violating the use-all-vendors
mandate. The fix distributes by per-agent budget headroom. This test pins that every healthy
local lane gets work and none monopolizes.
"""

from __future__ import annotations

import datetime
import importlib
import sys
from collections import Counter
from pathlib import Path

from limen.io import save_limen_file
from limen.models import Budget, BudgetTrack, LimenFile, Portal

# route.py lives in scripts/ (not the limen package); import it directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
route = importlib.import_module("route")


def _route_n(n: int, health: dict, budget: dict) -> Counter:
    assigned: dict[str, int] = {}
    picks = []
    for _ in range(n):
        v = route._pick_local({"title": "ordinary task", "type": "code"}, health, assigned, budget)
        picks.append(v)
        assigned[v] = assigned.get(v, 0) + 1
    return Counter(picks)


def test_distributes_across_all_healthy_local_lanes():
    health = {"codex": True, "claude": True, "agy": True, "opencode": True}
    budget = {"codex": 100, "claude": 100, "agy": 100}
    c = _route_n(30, health, budget)
    # all three general local lanes must be used — NOT all on codex
    assert set(c) >= {"codex", "claude", "agy"}, c
    # with equal budgets, load is even (~10 each); no lane may hog the batch
    assert max(c.values()) <= 12, c
    assert min(c["codex"], c["claude"], c["agy"]) >= 8, c


def test_budget_weights_distribution():
    # a lane with 2x the budget should receive roughly 2x the work
    health = {"codex": True, "claude": True, "agy": True}
    budget = {"codex": 200, "claude": 100, "agy": 100}
    c = _route_n(40, health, budget)
    assert c["codex"] > c["claude"], c
    assert c["codex"] > c["agy"], c


def test_deploy_work_still_goes_to_opencode():
    health = {"codex": True, "claude": True, "agy": True, "opencode": True}
    budget = {"codex": 100, "claude": 100, "agy": 100}
    v = route._pick_local({"title": "deploy cloudflare worker", "type": "infra"}, health, {}, budget)
    assert v == "opencode", v


def test_falls_back_when_only_one_lane_healthy():
    health = {"codex": False, "claude": True, "agy": False, "opencode": False}
    budget = {"codex": 100, "claude": 100, "agy": 100}
    c = _route_n(5, health, budget)
    assert set(c) == {"claude"}, c


def test_repo_routing_actively_fills_jules_opencode_and_agy(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "_learned_weights", dict)
    monkeypatch.setattr(route, "_ledger_bias", lambda task: {"jules": 0.2})
    monkeypatch.setattr(route, "_vendor_cliff_urgency", dict)
    monkeypatch.setenv("LIMEN_JULES_BATCH_FILL", "1")
    monkeypatch.delenv("LIMEN_REMOTE_BATCH_BIAS", raising=False)
    health = {
        "codex": True,
        "claude": True,
        "agy": True,
        "opencode": True,
        "gemini": False,
        "jules": True,
    }
    budget = {"codex": 100, "claude": 100, "agy": 100, "opencode": 100, "jules": 100}
    tally: Counter = Counter()

    for _ in range(500):
        vendor, _reason = route.route_task(
            {"title": "ordinary repo task", "type": "code", "repo": "org/repo"},
            health,
            tmp_path,
            assigned=tally,
            budget=budget,
            runway={},
        )
        tally[vendor] += 1

    assert tally["jules"] >= 90, tally
    assert tally["agy"] >= 90, tally
    assert tally["opencode"] >= 90, tally


def test_routing_snapshot_projects_stale_budget_resets(tmp_path, monkeypatch):
    now = datetime.datetime(2026, 7, 6, 12, 0, tzinfo=datetime.UTC)
    stale = (now - datetime.timedelta(days=2)).isoformat()
    tasks_path = tmp_path / "tasks.yaml"
    lf = LimenFile(
        portal=Portal(
            budget=Budget(
                daily=600,
                per_agent={"jules": 100},
                track=BudgetTrack(
                    date="2026-07-03",
                    spent=100,
                    per_agent={"jules": 100},
                    per_agent_reset={"jules": stale},
                ),
            )
        )
    )
    save_limen_file(tasks_path, lf)
    monkeypatch.setattr(route, "_now_utc", lambda: now)

    data = route._load_limen_for_routing(tasks_path).model_dump(mode="json", exclude_none=True)

    track = data["portal"]["budget"]["track"]
    assert track["per_agent"]["jules"] == 0
    assert track["spent"] == 0
    assert track["per_agent_reset"]["jules"] == now.isoformat()


# ---------------------------------------------------------------------------
# Lane-floor boost tests (LIMEN_LANE_FLOORS feature, Jul 2026)
# Motivation: Jul 3–5 starvation — Jules had 0 tasks for 3 days; codex sat at
# 5/100 daily budget. The raw budget-ratio ordering already preferred lighter
# lanes, but when loads were close a slightly-above-floor lane could edge out
# an under-floor lane via tiebreaker (cliff, runway, budget, name). The 0.5×
# boost on under-floor lanes ensures they sort first even in those tie cases.
# ---------------------------------------------------------------------------


def test_under_floor_lane_beats_above_floor_lane_at_same_budget(monkeypatch):
    """A lane below its daily floor is picked over a lane above its floor when
    both have the same budget. Floor = ceil(budget × 0.25) = 25 for budget=100.

    codex assigned=20 (below floor=25): boosted effective load = 0.20×0.5 = 0.10
    claude assigned=26 (above floor=25): no boost, effective load = 0.26
    → codex sorts first (0.10 < 0.26).
    """
    monkeypatch.setenv("LIMEN_LANE_FLOORS", "1")
    monkeypatch.delenv("LIMEN_LANE_FLOOR_FRAC", raising=False)
    monkeypatch.delenv("LIMEN_CODEX_DAILY_TASKS", raising=False)
    monkeypatch.delenv("LIMEN_CLAUDE_DAILY_TASKS", raising=False)
    monkeypatch.setattr(route, "_learned_weights", dict)
    monkeypatch.setattr(route, "_ledger_bias", lambda task: {})
    monkeypatch.setattr(route, "_vendor_cliff_urgency", dict)

    health = {"codex": True, "claude": True, "agy": False, "opencode": False}
    budget = {"codex": 100, "claude": 100}
    # codex below floor=25 (assigned 20); claude above floor=25 (assigned 26).
    assigned = {"codex": 20, "claude": 26}
    task = {"title": "ordinary task", "type": "code"}
    pick = route._pick_local(task, health, assigned, budget)
    assert pick == "codex", f"under-floor codex should beat above-floor claude, got {pick}"


def test_under_floor_boost_disabled_by_env(monkeypatch):
    """LIMEN_LANE_FLOORS=0 restores pure raw budget-ratio ordering without the floor boost."""
    monkeypatch.setenv("LIMEN_LANE_FLOORS", "0")
    monkeypatch.delenv("LIMEN_LANE_FLOOR_FRAC", raising=False)
    monkeypatch.setattr(route, "_learned_weights", dict)
    monkeypatch.setattr(route, "_ledger_bias", lambda task: {})
    monkeypatch.setattr(route, "_vendor_cliff_urgency", dict)

    health = {"codex": True, "claude": True, "agy": False, "opencode": False}
    budget = {"codex": 100, "claude": 100}
    # With floors OFF: pure raw ordering. codex=10/100=0.10, claude=5/100=0.05 → claude wins.
    assigned = {"codex": 10, "claude": 5}
    task = {"title": "ordinary task", "type": "code"}
    pick = route._pick_local(task, health, assigned, budget)
    assert pick == "claude", f"lower raw load (claude) should win with floors=0, got {pick}"


def test_floor_boost_starvation_case_runs_cleanly(monkeypatch):
    """The Jul 3–5 starvation scenario (codex 5/100): floor boost code path runs without error."""
    monkeypatch.setenv("LIMEN_LANE_FLOORS", "1")
    monkeypatch.delenv("LIMEN_LANE_FLOOR_FRAC", raising=False)
    monkeypatch.delenv("LIMEN_CODEX_DAILY_TASKS", raising=False)
    monkeypatch.setattr(route, "_learned_weights", dict)
    monkeypatch.setattr(route, "_ledger_bias", lambda task: {})
    monkeypatch.setattr(route, "_vendor_cliff_urgency", dict)

    health = {"codex": True, "claude": False, "agy": False, "opencode": False}
    budget = {"codex": 100}
    assigned = {"codex": 5}  # starvation: only 5 of 100 daily budget used
    task = {"title": "ordinary task", "type": "code"}
    pick = route._pick_local(task, health, assigned, budget)
    # Single candidate → always returns codex. Validates boost path runs without exception.
    assert pick == "codex"
