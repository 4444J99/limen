"""Tests for strict, dynamically discovered Omega remediation contracts."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from limen.omega_remediation import (
    OmegaRemediationError,
    OmegaRemediationV1,
    OmegaRungContractV1,
    annotate_omega_stamp,
    load_omega_remediations,
    materialize_remediations,
)

ROOT = Path(__file__).resolve().parents[2]


def _registry() -> dict:
    return {
        "schema": "limen.omega_remediation_registry.v1",
        "defaults": {
            "authority": {
                "schema_version": "limen.authority_envelope.v1",
                "actions": ["read"],
                "repositories": ["organvm/limen"],
                "path_prefixes": ["."],
                "external_effects": [],
                "may_delegate": False,
            },
            "effect": "read",
            "output_ceiling_bytes": 4096,
            "receipt_target": "github:organvm/limen:issue:1571",
            "required_capabilities": ["shell"],
            "work_loan": {
                "schema_version": "limen.work_loan.v1",
                "source_origin": "system_debt",
                "horizon": "present",
                "value_case": "Close one typed strict-Omega predicate.",
                "budget_cost": 1,
                "owner_surface": "campaign-owner",
                "external_deadline": False,
                "due_at": None,
            },
        },
        "rungs": [
            {
                "id": "sensor.renamed",
                "owner": "sensor-owner",
                "next_action": "Run the exact predicate and route its findings.",
            }
        ],
    }


def _rungs(predicate: str = "python3 scripts/future.py --check") -> tuple[OmegaRungContractV1, ...]:
    return (
        OmegaRungContractV1(
            id="sensor.renamed",
            label="renamed future sensor",
            tier="det",
            predicate=predicate,
        ),
    )


def test_shipped_registry_covers_every_live_discovered_rung() -> None:
    rungs, remediations = load_omega_remediations(ROOT)
    assert set(remediations) == {rung.id for rung in rungs}
    assert all(remediation.authority.may_delegate is False for remediation in remediations.values())
    assert all(remediation.work_loan.owner_surface == remediation.owner for remediation in remediations.values())


def test_added_removed_or_unknown_rung_fails_closed() -> None:
    registry = _registry()
    with pytest.raises(OmegaRemediationError, match="missing=.*sensor.added"):
        materialize_remediations(
            registry,
            (
                *_rungs(),
                OmegaRungContractV1(
                    id="sensor.added",
                    label="new sensor",
                    tier="live",
                    predicate="python3 scripts/new.py --check",
                ),
            ),
        )
    registry["rungs"].append(
        {
            "id": "sensor.unknown",
            "owner": "unknown-owner",
            "next_action": "Do not silently accept an unknown rung.",
        }
    )
    with pytest.raises(OmegaRemediationError, match="unknown=.*sensor.unknown"):
        materialize_remediations(registry, _rungs())


def test_dynamic_predicate_change_requires_no_code_or_fixed_catalog() -> None:
    first = materialize_remediations(_registry(), _rungs())["sensor.renamed"]
    renamed = "python3 scripts/completely-renamed.py --verify"
    second = materialize_remediations(_registry(), _rungs(renamed))["sensor.renamed"]
    assert first.predicate != second.predicate
    assert second.predicate == renamed
    assert second.required_capabilities == frozenset({"shell"})


def test_invalid_or_delegating_metadata_is_rejected() -> None:
    registry = _registry()
    registry["defaults"]["authority"]["may_delegate"] = True
    with pytest.raises(OmegaRemediationError, match="must not delegate"):
        materialize_remediations(registry, _rungs())
    registry = _registry()
    registry["rungs"][0]["unexpected"] = "drift"
    with pytest.raises(OmegaRemediationError, match="extra_forbidden"):
        materialize_remediations(registry, _rungs())
    registry = _registry()
    registry["defaults"]["receipt_target"] = "chat-only"
    with pytest.raises(OmegaRemediationError, match="durable GitHub receipt"):
        materialize_remediations(registry, _rungs())
    with pytest.raises(ValueError, match="executable command"):
        _rungs("describe the check in prose")
    remediation = materialize_remediations(_registry(), _rungs())["sensor.renamed"]
    payload = remediation.model_dump(mode="json")
    payload["receipt_target"] = "chat-only"
    with pytest.raises(ValueError, match="durable GitHub receipt"):
        OmegaRemediationV1.model_validate(payload)


def test_stamp_annotation_is_typed_exact_order_and_content_free() -> None:
    rungs = _rungs()
    remediations = materialize_remediations(_registry(), rungs)
    stamp = {
        "schema_version": 2,
        "rungs": [
            {
                "id": "sensor.renamed",
                "rung": "renamed future sensor",
                "status": "FAIL",
                "tier": "det",
            }
        ],
    }
    annotated = annotate_omega_stamp(stamp, rungs, remediations)
    assert annotated["schema_version"] == 3
    metadata = annotated["rungs"][0]["remediation"]
    assert metadata["schema_version"] == "limen.omega_remediation.v1"
    assert metadata["owner"] == "sensor-owner"
    assert metadata["effect"] == "read"
    serialized = json.dumps(metadata).lower()
    assert "credential" not in serialized
    assert "token" not in serialized

    reordered = copy.deepcopy(stamp)
    reordered["rungs"][0]["id"] = "sensor.other"
    with pytest.raises(OmegaRemediationError, match="identity differs"):
        annotate_omega_stamp(reordered, rungs, remediations)
