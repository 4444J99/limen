from __future__ import annotations

import copy
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-collaboration-operations-plan.py"
SPEC = importlib.util.spec_from_file_location("check_collaboration_operations_plan", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def live_plan() -> dict:
    return MODULE.load_yaml(MODULE.DAG_PATH)


def test_live_alpha_to_omega_plan_is_complete_and_acyclic() -> None:
    assert MODULE.validate_plan(live_plan()) == []


def test_missing_phase_and_duplicate_packet_are_rejected() -> None:
    plan = live_plan()
    plan["phases"] = plan["phases"][:-1]
    plan["phases"][1]["packets"][0]["id"] = "ALPHA-01"

    errors = MODULE.validate_plan(plan)

    assert "phases must contain Alpha through Omega exactly once in canonical order" in errors
    assert any("duplicate packet id: ALPHA-01" in error for error in errors)
    assert "execution DAG must contain exactly 72 bounded packets" in errors


def test_unknown_dependency_and_unbounded_team_are_rejected() -> None:
    plan = copy.deepcopy(live_plan())
    plan["team"]["max_children"] = 99
    plan["phases"][0]["packets"][0]["depends_on"] = ["MISSING-99"]

    errors = MODULE.validate_plan(plan)

    assert "team fanout must remain bounded to four children at depth one" in errors
    assert any("packet ALPHA-01 has unknown dependencies: MISSING-99" in error for error in errors)
