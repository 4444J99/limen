from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-collaboration-operations.py"
SPEC = importlib.util.spec_from_file_location("check_collaboration_operations", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def documents() -> tuple[dict, dict, dict, dict]:
    return tuple(
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in (MODULE.CONTRACT, MODULE.ESTATE, MODULE.ACCESS, MODULE.CONSTELLATION)
    )


def test_live_collaboration_operations_contract_is_owner_routed() -> None:
    assert MODULE.validate_documents(*documents()) == []


def test_david_lane_cannot_turn_external_references_into_mutation_authority() -> None:
    contract, estate, access, register = documents()
    drifted = copy.deepcopy(contract)
    drifted["lanes"]["david"]["mutation_authority"] = "platform_genesis"

    errors = MODULE.validate_documents(drifted, estate, access, register, selected_person="david")

    assert errors == ["David lane must deny platform-genesis mutation authority"]


def test_platform_cannot_gain_a_collaborator_grant_or_live_client_fixtures() -> None:
    contract, estate, access, register = documents()
    drifted_contract = copy.deepcopy(contract)
    drifted_access = copy.deepcopy(access)
    drifted_contract["flow_policy"]["live_client_fixtures"] = "allowed"
    drifted_access.setdefault("grants", {})[MODULE.PLATFORM_REPO] = [
        {"login": "example", "person": "david", "role": "push"}
    ]

    errors = MODULE.validate_documents(drifted_contract, estate, drifted_access, register)

    assert "flow_policy.live_client_fixtures must be 'forbidden'" in errors
    assert f"{MODULE.PLATFORM_REPO} must have no collaborator grant rows" in errors
