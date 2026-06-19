"""Regression test for the router serialization bug.

On 2026-06-19 the fleet was found serialized onto codex: route.py's _pick_local did
`for v in ("codex","claude","agy","opencode"): if healthy: return v` — always returning
the first healthy lane (codex), starving claude/agy/jules and violating the use-all-vendors
mandate. The fix distributes by per-agent budget headroom. This test pins that every healthy
local lane gets work and none monopolizes.
"""
from __future__ import annotations

import importlib
import sys
from collections import Counter
from pathlib import Path

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
    v = route._pick_local(
        {"title": "deploy cloudflare worker", "type": "infra"}, health, {}, budget
    )
    assert v == "opencode", v


def test_falls_back_when_only_one_lane_healthy():
    health = {"codex": False, "claude": True, "agy": False, "opencode": False}
    budget = {"codex": 100, "claude": 100, "agy": 100}
    c = _route_n(5, health, budget)
    assert set(c) == {"claude"}, c
