"""The ledger→routing loop: steer a lane away from the work-classes it WASTES, keep it for its winners.

opencode noops on code/build-out → shed it there (keep its deploy specialty). jules wastes coverage/docs
busywork but LANDS revenue/product async → shed only the busywork, never the winners, never stranded.
Derived from logs/ledger.json (waste_classes/win_classes) — no lane names pinned. Fails open + floored.
"""

from __future__ import annotations

import importlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
route = importlib.import_module("route")


def _ledger(tmp: Path, lanes: dict):
    (tmp / "logs").mkdir(parents=True, exist_ok=True)
    (tmp / "logs" / "ledger.json").write_text(json.dumps({"lanes": lanes}))


def _self_improve(tmp: Path, lane_adjustments: list[dict]):
    (tmp / "logs").mkdir(parents=True, exist_ok=True)
    (tmp / "logs" / "self-improve-proposal.json").write_text(json.dumps({"lane_adjustments": lane_adjustments}))


def test_ledger_bias_sheds_waste_class_but_exempts_winners(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    _ledger(
        tmp_path,
        {
            "opencode": {"waste_classes": ["code", "build-out"], "win_classes": []},
            "jules": {"waste_classes": ["coverage", "code"], "win_classes": ["revenue", "product"]},
        },
    )
    # a pure coverage task → jules is shed (it wastes coverage and wins nothing here)
    b = route._ledger_bias({"type": "code", "labels": ["coverage"]})
    assert b.get("jules") == 0.2 and "opencode" in b
    # a revenue task that is ALSO type=code → jules EXEMPT (it lands revenue), opencode still shed
    b2 = route._ledger_bias({"type": "code", "labels": ["revenue", "build-out"]})
    assert "jules" not in b2, "win class must override waste — don't shed jules's revenue work"
    assert b2.get("opencode") == 0.2


def test_missing_ledger_no_bias(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)  # no logs/ledger.json written
    assert route._ledger_bias({"type": "code", "labels": ["build-out"]}) == {}


def test_bias_off_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    _ledger(tmp_path, {"opencode": {"waste_classes": ["code"], "win_classes": []}})
    monkeypatch.setenv("LIMEN_LEDGER_BIAS", "0")
    assert route._ledger_bias({"type": "code"}) == {}


def test_opencode_shed_from_its_waste_class(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    _ledger(
        tmp_path,
        {
            "opencode": {"waste_classes": ["code", "build-out"], "win_classes": []},
            "codex": {"waste_classes": [], "win_classes": ["code", "build-out"]},
            "claude": {"waste_classes": [], "win_classes": ["code", "build-out"]},
            "agy": {"waste_classes": [], "win_classes": ["code", "build-out"]},
        },
    )
    health = {"codex": True, "claude": True, "agy": True, "opencode": True}
    budget = {"codex": 100, "claude": 100, "agy": 100, "opencode": 100}
    assigned: dict[str, int] = {}
    picks = []
    for _ in range(28):
        v = route._pick_local({"title": "build it", "type": "code", "labels": ["build-out"]}, health, assigned, budget)
        picks.append(v)
        assigned[v] = assigned.get(v, 0) + 1
    c = Counter(picks)
    # opencode is floored (0.2) for this class → far fewer than every earner, but NOT zero (never starved)
    assert c["opencode"] < min(c["codex"], c["claude"], c["agy"]), c
    assert c["opencode"] >= 1, "floored, not starved"


def test_self_improve_boost_weight_is_honored(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    monkeypatch.setenv("LIMEN_LEDGER_BIAS", "0")
    _self_improve(
        tmp_path,
        [
            {"lane": "codex", "target_weight": 1.0},
            {"lane": "opencode", "target_weight": 1.25},
        ],
    )

    assert route._learned_weights()["opencode"] == 1.25

    health = {"codex": True, "opencode": True}
    budget = {"codex": 100, "opencode": 100}
    assigned = {"codex": 1, "opencode": 1}
    pick = route._pick_local({"title": "ordinary code task", "type": "code"}, health, assigned, budget)

    assert pick == "opencode"


def test_route_float_knobs_fail_open_when_malformed(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    _self_improve(tmp_path, [{"lane": "opencode", "target_weight": 0.1}])

    monkeypatch.setenv("LIMEN_SI_WEIGHT_FLOOR", "not-a-float")
    monkeypatch.setenv("LIMEN_SI_WEIGHT_CEILING", "also-not-a-float")
    assert route._learned_weights()["opencode"] == 0.25

    _ledger(tmp_path, {"opencode": {"waste_classes": ["code"], "win_classes": []}})
    monkeypatch.setenv("LIMEN_LEDGER_BIAS_FLOOR", "not-a-float")
    assert route._ledger_bias({"type": "code"})["opencode"] == 0.2


def test_malformed_usage_runway_fails_open(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "usage.json").write_text(
        json.dumps({"vendors": {"codex": {"runway_h": "bad-meter-value"}, "claude": {"runway_h": 3}}})
    )

    runway = route._vendor_runway()

    assert runway["codex"] == float("inf")
    assert runway["claude"] == 3.0


def test_deploy_still_opencode_despite_bias(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    _ledger(tmp_path, {"opencode": {"waste_classes": ["code"], "win_classes": []}})
    health = {"codex": True, "claude": True, "agy": True, "opencode": True}
    budget = {"codex": 100, "claude": 100, "agy": 100}
    v = route._pick_local({"title": "deploy cloudflare worker", "type": "infra"}, health, {}, budget)
    assert v == "opencode", "the deploy specialty fires before weighting — bias never blocks it"


def test_slow_task_routes_to_jules_not_back_to_local(tmp_path, monkeypatch):
    """A "slow"-labelled task already timed out on a wall-clock-bound sync local lane (dispatch.py's
    timeout->jules path). The local-first router must NOT steal it back to a local lane — that re-times-
    out and retargets to jules every beat, an infinite loop where jules never actually runs. It must go
    to the async remote lane (jules) while jules is healthy."""
    monkeypatch.setattr(route, "ROOT", tmp_path)
    # every local lane is healthy, so the local-first path WOULD fire (clone-on-demand) — the slow
    # guard must intercept and route to jules before that.
    task = {"id": "S1", "repo": "o/r", "type": "content", "labels": ["slow", "generated"], "budget_cost": 2}
    health = {a: True for a in route.PAID_AGENT_ORDER}
    pick, reason = route.route_task(task, health, tmp_path, assigned={}, budget={"jules": 100}, runway={})
    assert pick == "jules", f"slow task stolen back to a local sync lane (infinite loop): {pick} ({reason})"


def test_slow_task_falls_through_to_local_when_jules_down(tmp_path, monkeypatch):
    """Never strand: if jules is DOWN, a slow task still routes to a healthy local lane rather than
    going unroutable — the async carve-out only applies while jules can actually take it."""
    monkeypatch.setattr(route, "ROOT", tmp_path)
    task = {"id": "S2", "repo": "o/r", "type": "content", "labels": ["slow"], "budget_cost": 2}
    health = {a: True for a in route.PAID_AGENT_ORDER}
    health["jules"] = False
    budget = {a: 100 for a in route.PAID_AGENT_ORDER}
    pick, _reason = route.route_task(task, health, tmp_path, assigned={}, budget=budget, runway={})
    assert pick in route.LOCAL_CHECKOUT_AGENTS, f"slow task stranded when jules down: {pick}"


def test_existing_healthy_assignment_is_sticky(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    task = {"id": "T-STICKY", "repo": "o/r", "type": "code", "target_agent": "opencode"}
    health = {"opencode": True, "codex": True, "jules": False}

    assert route._existing_assignment_usable(task, "opencode", health, tmp_path)


def test_existing_down_assignment_is_not_sticky(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    task = {"id": "T-DOWN", "repo": "o/r", "type": "code", "target_agent": "opencode"}
    health = {"opencode": False, "codex": True}

    assert not route._existing_assignment_usable(task, "opencode", health, tmp_path)


def test_slow_local_assignment_not_sticky_when_jules_healthy(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    task = {"id": "T-SLOW", "repo": "o/r", "type": "code", "labels": ["slow"], "target_agent": "opencode"}
    health = {"opencode": True, "codex": True, "jules": True}

    assert not route._existing_assignment_usable(task, "opencode", health, tmp_path)
    assert route._existing_assignment_usable(task, "jules", health, tmp_path)


def test_jules_not_stranded_when_sole_capable(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    _ledger(tmp_path, {"jules": {"waste_classes": ["coverage"], "win_classes": ["revenue"]}})
    # only jules healthy; repo set but no local checkout under workdir → extended pick, jules sole option
    task = {"title": "add coverage", "type": "code", "labels": ["coverage"], "repo": "o/r"}
    health = {a: (a == "jules") for a in route.PAID_AGENT_ORDER}
    pick, _reason = route.route_task(task, health, tmp_path, assigned={}, budget={})
    assert pick == "jules", "a coverage task on a no-checkout repo still routes to jules — never stranded"
