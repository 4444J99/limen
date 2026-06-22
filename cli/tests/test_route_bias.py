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


def test_ledger_bias_sheds_waste_class_but_exempts_winners(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    _ledger(tmp_path, {
        "opencode": {"waste_classes": ["code", "build-out"], "win_classes": []},
        "jules": {"waste_classes": ["coverage", "code"], "win_classes": ["revenue", "product"]},
    })
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
    _ledger(tmp_path, {
        "opencode": {"waste_classes": ["code", "build-out"], "win_classes": []},
        "codex": {"waste_classes": [], "win_classes": ["code", "build-out"]},
        "claude": {"waste_classes": [], "win_classes": ["code", "build-out"]},
        "agy": {"waste_classes": [], "win_classes": ["code", "build-out"]},
    })
    health = {"codex": True, "claude": True, "agy": True, "opencode": True}
    budget = {"codex": 100, "claude": 100, "agy": 100, "opencode": 100}
    assigned: dict[str, int] = {}
    picks = []
    for _ in range(28):
        v = route._pick_local({"title": "build it", "type": "code", "labels": ["build-out"]},
                              health, assigned, budget)
        picks.append(v)
        assigned[v] = assigned.get(v, 0) + 1
    c = Counter(picks)
    # opencode is floored (0.2) for this class → far fewer than every earner, but NOT zero (never starved)
    assert c["opencode"] < min(c["codex"], c["claude"], c["agy"]), c
    assert c["opencode"] >= 1, "floored, not starved"


def test_deploy_still_opencode_despite_bias(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    _ledger(tmp_path, {"opencode": {"waste_classes": ["code"], "win_classes": []}})
    health = {"codex": True, "claude": True, "agy": True, "opencode": True}
    budget = {"codex": 100, "claude": 100, "agy": 100}
    v = route._pick_local({"title": "deploy cloudflare worker", "type": "infra"}, health, {}, budget)
    assert v == "opencode", "the deploy specialty fires before weighting — bias never blocks it"


def test_jules_not_stranded_when_sole_capable(tmp_path, monkeypatch):
    monkeypatch.setattr(route, "ROOT", tmp_path)
    _ledger(tmp_path, {"jules": {"waste_classes": ["coverage"], "win_classes": ["revenue"]}})
    # only jules healthy; repo set but no local checkout under workdir → extended pick, jules sole option
    task = {"title": "add coverage", "type": "code", "labels": ["coverage"], "repo": "o/r"}
    health = {a: (a == "jules") for a in route.PAID_AGENT_ORDER}
    pick, _reason = route.route_task(task, health, tmp_path, assigned={}, budget={})
    assert pick == "jules", "a coverage task on a no-checkout repo still routes to jules — never stranded"
