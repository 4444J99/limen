from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from limen.cloud_routine import (
    CloudRoutineReceiptV1,
    plan_task_upserts,
    task_for,
    task_id_for,
)
from limen.intake import validate_intake_contract


ROOT = Path(__file__).resolve().parents[2]


def _receipt(**overrides) -> CloudRoutineReceiptV1:
    payload = {
        "schema_version": "limen.cloud_routine_receipt.v1",
        "routine_id": "fleet-audit",
        "observed_at": "2026-08-08T12:00:00Z",
        "status": "finding",
        "stable_finding_key": "fleet.session-meta-push-ci",
        "disposition": "new_work",
        "owner_ref": "organvm/limen",
        "predicate": "python scripts/check-cloud-routine-ingest.py",
    }
    payload.update(overrides)
    return CloudRoutineReceiptV1.model_validate(payload)


def test_material_finding_without_owner_is_rejected() -> None:
    with pytest.raises(ValidationError, match="require owner_ref"):
        _receipt(owner_ref=None)


def test_new_work_requires_exact_repository_owner() -> None:
    with pytest.raises(ValidationError, match="exact owner/repo"):
        _receipt(owner_ref="organvm/limen#2120")


def test_observation_time_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError, match="include a timezone"):
        _receipt(observed_at="2026-08-08T12:00:00")


def test_non_material_observation_can_have_no_owner() -> None:
    receipt = _receipt(
        status="ok",
        disposition="no_change",
        owner_ref=None,
        stable_finding_key="fleet.daily-green",
        predicate="python scripts/check-cloud-routine-ingest.py",
    )

    assert receipt.owner_ref is None


def test_task_translation_preserves_predicate_and_intake_contract() -> None:
    receipt = _receipt()

    task = task_for(receipt)

    assert task.id == task_id_for(receipt)
    assert task.repo == "organvm/limen"
    assert task.created.isoformat() == "2026-08-08"
    assert task.predicate == receipt.predicate
    assert validate_intake_contract(task, is_new=True) is not None


def test_repeated_finding_and_pending_ticket_are_idempotent() -> None:
    receipt = _receipt()
    duplicate_batch = plan_task_upserts([receipt, receipt])
    pending_batch = plan_task_upserts(
        [receipt],
        pending_ids={task_id_for(receipt)},
    )

    assert len(duplicate_batch.tasks) == 1
    assert duplicate_batch.duplicates == 1
    assert pending_batch.tasks == ()
    assert pending_batch.duplicates == 1


def test_owned_and_superseded_findings_do_not_create_tasks() -> None:
    owned = _receipt(
        disposition="owned",
        owner_ref="https://github.com/organvm/limen/issues/2120",
    )
    superseded = _receipt(
        disposition="superseded",
        owner_ref="https://github.com/organvm/limen/pull/2121",
    )

    plan = plan_task_upserts([owned, superseded])

    assert plan.tasks == ()
    assert plan.classified == 2


def test_manifest_publishes_the_receipt_contract() -> None:
    manifest = json.loads((ROOT / "cloud-routines.json").read_text())

    assert manifest["receipt_schema_version"] == "limen.cloud_routine_receipt.v1"
    assert manifest["receipt_schema"] == ("spec/contracts/cloud-routine-receipt-v1.schema.json")
    assert manifest["consumer"] == "scripts/cloud-routine-ingest.py"


def test_current_findings_are_typed_and_already_owned() -> None:
    payload = json.loads((ROOT / "docs" / "receipts" / "cloud-routine-findings-20260808.json").read_text())
    receipts = [CloudRoutineReceiptV1.model_validate(item) for item in payload]

    assert len(receipts) == 11
    assert all(receipt.owner_ref for receipt in receipts)
    assert all(receipt.disposition != "new_work" for receipt in receipts)


def test_irf_denominator_is_fully_classified_without_packet_emissions() -> None:
    receipt = json.loads((ROOT / "docs" / "receipts" / "irf-p0-owner-classification-20260808.json").read_text())
    rows = receipt["rows"]

    assert receipt["denominator"] == receipt["classified"] == len(rows) == 41
    assert len({row["irf_id"] for row in rows}) == 41
    assert all(row["owner_kind"] == "irf" and row["owner_ref"] for row in rows)
    assert receipt["unowned"] == []
    assert receipt["packet_emissions"] == []


def test_cloud_human_gates_have_named_levers() -> None:
    lever_data = json.loads((ROOT / "his-hand-levers.json").read_text())
    lever_ids = {lever["id"] for lever in lever_data["levers"]}

    assert {
        "L-CLOUD-BULK-PR-CLOSE-N75",
        "L-CLOUD-EXTERNAL-GOVERNANCE-N77",
        "L-CLOUD-SESSION-SCOPE-EXPANSION",
        "L-CLOUD-ARCHIVE-ENTERPRISE-PLUGIN-N80",
    } <= lever_ids
