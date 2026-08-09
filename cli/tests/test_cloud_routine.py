from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from limen.cloud_routine import (
    CloudRoutineReceiptV1,
    plan_task_upserts,
    task_for,
    task_id_for,
)
from limen.intake import is_executable_predicate, validate_intake_contract


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
    with pytest.raises(ValidationError, match="exact owner/repo"):
        _receipt(owner_ref="../..")


def test_material_non_new_work_requires_durable_owner() -> None:
    with pytest.raises(ValidationError, match="durable owner_ref"):
        _receipt(
            disposition="owned",
            owner_ref="missing-owner",
        )
    with pytest.raises(ValidationError, match="durable owner_ref"):
        _receipt(
            disposition="owned",
            owner_ref="https://github.com/../limen/issues/1",
        )
    with pytest.raises(ValidationError, match="durable owner_ref"):
        _receipt(
            disposition="owned",
            owner_ref="https://github.com/organvm/../issues/1",
        )


def test_observation_time_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError, match="include a timezone"):
        _receipt(observed_at="2026-08-08T12:00:00")


def test_observation_time_rejects_excessive_future_skew() -> None:
    with pytest.raises(ValidationError, match="more than 300 seconds"):
        _receipt(observed_at="9999-01-01T00:00:00Z")


def test_non_material_observation_can_have_no_owner() -> None:
    receipt = _receipt(
        status="ok",
        disposition="no_change",
        owner_ref=None,
        stable_finding_key="fleet.daily-green",
        predicate="python scripts/check-cloud-routine-ingest.py",
    )

    assert receipt.owner_ref is None


def test_predicate_bound_matches_published_schema() -> None:
    with pytest.raises(ValidationError, match="at most 8192"):
        _receipt(predicate="x" * 8193)


def test_human_gate_requires_material_status_and_owner() -> None:
    with pytest.raises(ValidationError, match="material finding"):
        _receipt(status="ok", disposition="human_gate")
    with pytest.raises(ValidationError, match="require owner_ref"):
        _receipt(status="finding", disposition="human_gate", owner_ref=None)
    with pytest.raises(ValidationError, match="lever:<id>"):
        _receipt(
            status="finding",
            disposition="human_gate",
            owner_ref="https://github.com/organvm/limen/issues/2120",
        )


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


def test_equal_timestamp_conflicts_are_rejected_deterministically() -> None:
    owned = _receipt(
        disposition="owned",
        owner_ref="https://github.com/organvm/limen/issues/2120",
    )

    with pytest.raises(ValueError, match="conflicting cloud-routine observations"):
        plan_task_upserts([_receipt(), owned])


def test_latest_lineage_disposition_wins_before_task_planning() -> None:
    older = _receipt(observed_at="2026-08-08T11:00:00Z")
    newer = _receipt(
        observed_at="2026-08-08T12:00:00Z",
        disposition="owned",
        owner_ref="https://github.com/organvm/limen/issues/2120",
    )

    plan = plan_task_upserts([older, newer])

    assert plan.tasks == ()
    assert plan.classified == 1
    assert plan.duplicates == 1


def test_active_recurrence_occurrence_blocks_another_lineage_task() -> None:
    receipt = _receipt()
    lineage_id = task_id_for(receipt)

    plan = plan_task_upserts(
        [receipt],
        pending_ids={f"{lineage_id}-20260808T110000Z"},
        historical_ids={lineage_id},
    )

    assert plan.tasks == ()
    assert plan.duplicates == 1


def test_terminal_lineage_can_emit_a_new_occurrence() -> None:
    receipt = _receipt()
    lineage_id = task_id_for(receipt)

    plan = plan_task_upserts(
        [receipt],
        historical_ids={lineage_id},
        historical_observed_at={lineage_id: _receipt(observed_at="2026-08-08T11:00:00Z").observed_at},
    )

    assert len(plan.tasks) == 1
    assert plan.tasks[0].id == f"{lineage_id}-20260808T120000Z"
    assert plan.duplicates == 0


def test_terminal_lineage_preserves_subsecond_recurrences() -> None:
    receipt_one = _receipt(observed_at="2026-08-08T12:00:00.000001Z")
    receipt_two = _receipt(observed_at="2026-08-08T12:00:00.000002Z")
    lineage_id = task_id_for(receipt_one)
    baseline = _receipt(observed_at="2026-08-08T11:00:00Z").observed_at

    first = plan_task_upserts(
        [receipt_one],
        historical_ids={lineage_id},
        historical_observed_at={lineage_id: baseline},
    )
    first_id = first.tasks[0].id
    second = plan_task_upserts(
        [receipt_two],
        historical_ids={lineage_id, first_id},
        historical_observed_at={lineage_id: baseline},
    )

    assert first_id != second.tasks[0].id
    assert second.duplicates == 0


def test_historical_occurrence_timestamp_blocks_older_replay() -> None:
    receipt = _receipt(observed_at="2026-08-08T12:00:00Z")
    lineage_id = task_id_for(receipt)
    first = plan_task_upserts(
        [receipt],
        historical_ids={lineage_id},
        historical_observed_at={lineage_id: _receipt(observed_at="2026-08-08T11:00:00Z").observed_at},
    )
    occurrence_id = first.tasks[0].id

    delayed = _receipt(observed_at="2026-08-08T11:30:00Z")
    plan = plan_task_upserts(
        [delayed],
        historical_ids={lineage_id, occurrence_id},
        historical_observed_at={
            lineage_id: _receipt(observed_at="2026-08-08T11:00:00Z").observed_at,
            occurrence_id: receipt.observed_at,
        },
    )

    assert plan.tasks == ()
    assert plan.duplicates == 1


def test_terminal_lineage_replay_is_a_duplicate() -> None:
    receipt = _receipt()
    lineage_id = task_id_for(receipt)

    plan = plan_task_upserts(
        [receipt],
        historical_ids={lineage_id},
        historical_observed_at={lineage_id: receipt.observed_at},
    )

    assert plan.tasks == ()
    assert plan.duplicates == 1


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


def test_published_schema_carries_executable_and_human_gate_constraints() -> None:
    schema = json.loads((ROOT / "spec" / "contracts" / "cloud-routine-receipt-v1.schema.json").read_text())
    validator = Draft202012Validator(schema)
    valid = _receipt().model_dump(mode="json")
    invalid_placeholder = {**valid, "predicate": "python <TODO>"}
    invalid_quote = {**valid, "predicate": "python '"}
    valid_substitution = {**valid, "predicate": 'test "$(git rev-parse --show-toplevel)" = /tmp'}
    invalid_backtick = {**valid, "predicate": "test `false` = success"}
    invalid_semicolon = {**valid, "predicate": "python check.py; true"}
    invalid_nested_substitution = {**valid, "predicate": 'test "$(false; echo success)" = success'}
    invalid_pipeline = {**valid, "predicate": "python check.py | true"}
    invalid_owner = {**valid, "disposition": "owned", "owner_ref": "   "}
    invalid_durable_owner = {**valid, "disposition": "owned", "owner_ref": "missing-owner"}
    invalid_path_owner = {**valid, "owner_ref": "../.."}
    invalid_dotted_owner = {
        **valid,
        "disposition": "owned",
        "owner_ref": "https://github.com/../limen/issues/1",
    }
    invalid_dotted_repo_owner = {
        **valid,
        "disposition": "owned",
        "owner_ref": "https://github.com/organvm/../issues/1",
    }
    invalid_clustered_shell = {**valid, "predicate": "bash -uc 'false; true'"}
    invalid_ansi_c = {**valid, "predicate": "bash -c $'false\\ntrue'"}
    assert not list(validator.iter_errors(valid_substitution))
    assert list(validator.iter_errors(invalid_placeholder))
    assert list(validator.iter_errors(invalid_quote))
    assert list(validator.iter_errors(invalid_backtick))
    assert list(validator.iter_errors(invalid_semicolon))
    assert list(validator.iter_errors(invalid_nested_substitution))
    assert list(validator.iter_errors(invalid_pipeline))
    assert list(validator.iter_errors(invalid_owner))
    assert list(validator.iter_errors(invalid_durable_owner))
    assert list(validator.iter_errors(invalid_path_owner))
    assert list(validator.iter_errors(invalid_dotted_owner))
    assert list(validator.iter_errors(invalid_dotted_repo_owner))
    assert list(validator.iter_errors(invalid_clustered_shell))
    assert list(validator.iter_errors(invalid_ansi_c))
    human_gate = schema["allOf"][-1]
    assert human_gate["if"]["properties"]["disposition"]["const"] == "human_gate"
    assert human_gate["then"]["properties"]["status"]["enum"] == ["finding", "failed"]
    assert human_gate["then"]["properties"]["owner_ref"]["pattern"].startswith("^lever:")


def test_model_allows_safe_substitution_but_rejects_composition() -> None:
    safe = 'test "$(git rev-parse --show-toplevel)" = /tmp'
    assert _receipt(predicate=safe).predicate == safe
    with pytest.raises(ValidationError, match="bounded shell grammar"):
        _receipt(predicate="python check.py; true")
    with pytest.raises(ValidationError, match="one executable command"):
        _receipt(predicate="bash -c 'false; true'")
    with pytest.raises(ValidationError, match="bounded shell grammar"):
        _receipt(predicate="python check.py | true")
    with pytest.raises(ValidationError, match="bounded shell grammar"):
        _receipt(predicate='test "$(false; echo success)" = success')
    with pytest.raises(ValidationError, match="bounded shell grammar"):
        _receipt(predicate='test -z "$(printf \'%s\' "$(false \\"x; true \\")")"')
    with pytest.raises(ValidationError, match="bounded shell grammar"):
        _receipt(predicate="test `false` = success")


def test_shell_predicate_parsing_stops_at_script_and_rejects_ansi_c_newline() -> None:
    assert is_executable_predicate("bash check.sh -c 'value;literal'")
    with pytest.raises(ValidationError, match="one executable command"):
        _receipt(predicate="bash -c $'false\\ntrue'")


def test_tracked_lineage_remains_a_duplicate(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "cloud-routine-ingest.py"
    spec = importlib.util.spec_from_file_location(
        "cloud_routine_ingest_tracked_test",
        script,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    receipt = _receipt()
    lineage = tmp_path / "docs" / "receipts"
    lineage.mkdir(parents=True)
    (lineage / "cloud-routine-lineage.json").write_text(
        json.dumps(
            {
                "schema_version": "limen.cloud_routine_lineage.v1",
                "entries": [receipt.model_dump(mode="json")],
            }
        ),
        encoding="utf-8",
    )

    historical_ids, observed = module._historical_cloud_task_state(tmp_path / "tasks.yaml")

    assert task_id_for(receipt) in historical_ids
    assert observed[task_id_for(receipt)] == receipt.observed_at
    assert (
        plan_task_upserts(
            [receipt],
            historical_ids=historical_ids,
            historical_observed_at=observed,
        ).tasks
        == ()
    )


def test_tracked_lineage_rejects_invalid_entry(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "cloud-routine-ingest.py"
    spec = importlib.util.spec_from_file_location("cloud_routine_ingest_invalid_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    lineage = tmp_path / "docs" / "receipts"
    lineage.mkdir(parents=True)
    (lineage / "cloud-routine-lineage.json").write_text(
        json.dumps({"schema_version": "limen.cloud_routine_lineage.v1", "entries": [{"bad": True}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="tracked cloud lineage entry\[0\] is invalid"):
        module._historical_cloud_task_state(tmp_path / "tasks.yaml")


def test_pruned_archive_lineage_remains_a_duplicate(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "cloud-routine-ingest.py"
    spec = importlib.util.spec_from_file_location("cloud_routine_ingest_archive_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    receipt = _receipt()
    lineage_id = task_id_for(receipt)
    archive = tmp_path / "logs" / "tickets" / "archive"
    archive.mkdir(parents=True)
    (archive / "removed.json").write_text(
        json.dumps(
            {
                "intent": "task.upsert",
                "task_id": lineage_id,
                "patch": {
                    "id": lineage_id,
                    "context": "CloudRoutineReceiptV1; observed_at=2026-08-08T12:00:00+00:00",
                },
            }
        ),
        encoding="utf-8",
    )

    historical_ids, observed = module._historical_cloud_task_state(tmp_path / "tasks.yaml")

    assert lineage_id in historical_ids
    assert observed[lineage_id].isoformat() == "2026-08-08T12:00:00+00:00"
    assert (
        plan_task_upserts(
            [receipt],
            historical_ids=historical_ids,
            historical_observed_at=observed,
        ).tasks
        == ()
    )


def test_scoped_gate_covers_every_external_cloud_contract_artifact() -> None:
    gates = (ROOT / "institutio" / "governance" / "gates.yaml").read_text(encoding="utf-8")
    for path in (
        "spec/contracts/cloud-routine-receipt-v1.schema.json",
        "scripts/cloud-routine-ingest.py",
        "scripts/check-cloud-routine-ingest.py",
        "docs/receipts/cloud-routine-findings-20260808.json",
        "docs/receipts/cloud-routine-lineage.json",
        "docs/receipts/irf-p0-owner-classification-20260808.json",
    ):
        assert path in gates


def test_current_findings_are_typed_and_already_owned() -> None:
    payload = json.loads((ROOT / "docs" / "receipts" / "cloud-routine-findings-20260808.json").read_text())
    receipts = [CloudRoutineReceiptV1.model_validate(item) for item in payload]

    assert len(receipts) == 11
    assert all(receipt.owner_ref for receipt in receipts)
    assert all(receipt.disposition != "new_work" for receipt in receipts)


def test_irf_denominator_is_fully_classified_without_packet_emissions() -> None:
    receipt = json.loads((ROOT / "docs" / "receipts" / "irf-p0-owner-classification-20260808.json").read_text())
    rows = receipt["rows"]
    by_id = {row["irf_id"]: row for row in rows}
    human_ids = set(receipt["human_gate_irf_ids"])

    assert receipt["denominator"] == receipt["classified"] == len(rows) == 41
    assert len(by_id) == 41
    assert len(human_ids) == 18
    assert all(
        by_id[irf_id]["owner_kind"] == "lever"
        and by_id[irf_id]["owner_ref"] == receipt["human_gate_owner"]
        and by_id[irf_id]["disposition"] == "human_gate"
        for irf_id in human_ids
    )
    assert all(
        row["owner_kind"] == "irf" and row["owner_ref"] == f"irf:{row['irf_id']}" and row["disposition"] == "owned"
        for row in rows
        if row["irf_id"] not in human_ids
    )
    assert receipt["unowned"] == []
    assert receipt["packet_emissions"] == []


def test_consumer_rejects_a_nonexistent_human_lever(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "cloud-routine-ingest.py"
    spec = importlib.util.spec_from_file_location("cloud_routine_ingest_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    registry = tmp_path / "his-hand-levers.json"
    registry.write_text('{"levers": []}', encoding="utf-8")
    receipt = _receipt(
        disposition="human_gate",
        owner_ref="lever:L-NOT-REGISTERED",
    )

    with pytest.raises(ValueError, match="does not resolve"):
        module.validate_human_gate_owners([receipt], lever_path=registry)


def test_consumer_accepts_a_statusless_active_human_lever(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "cloud-routine-ingest.py"
    spec = importlib.util.spec_from_file_location("cloud_routine_ingest_statusless_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    registry = tmp_path / "his-hand-levers.json"
    registry.write_text(
        json.dumps({"levers": [{"id": "L-ACTIVE"}]}),
        encoding="utf-8",
    )
    receipt = _receipt(
        disposition="human_gate",
        owner_ref="lever:L-ACTIVE",
    )

    module.validate_human_gate_owners([receipt], lever_path=registry)
    assert "L-ACTIVE" in module.active_lever_ids(registry)


def test_consumer_collapses_lineages_before_live_owner_resolution(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "cloud-routine-ingest.py"
    spec = importlib.util.spec_from_file_location("cloud_routine_ingest_lineage_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    registry = tmp_path / "his-hand-levers.json"
    registry.write_text(
        json.dumps({"levers": [{"id": "L-CLOSED", "status": "discharged"}]}),
        encoding="utf-8",
    )
    receipt_path = tmp_path / "receipts.json"
    receipt_path.write_text(
        json.dumps(
            [
                _receipt(
                    observed_at="2026-08-08T11:00:00Z",
                    disposition="human_gate",
                    owner_ref="lever:L-CLOSED",
                ).model_dump(mode="json"),
                _receipt(
                    observed_at="2026-08-08T12:00:00Z",
                    disposition="owned",
                    owner_ref="https://github.com/organvm/limen/issues/2120",
                ).model_dump(mode="json"),
            ]
        ),
        encoding="utf-8",
    )

    loaded = module.load_receipts([receipt_path], lever_path=registry)
    assert len(loaded) == 2


@pytest.mark.parametrize("payload", ["[]", "\n"])
def test_consumer_rejects_empty_delivery(tmp_path: Path, payload: str) -> None:
    script = ROOT / "scripts" / "cloud-routine-ingest.py"
    spec = importlib.util.spec_from_file_location("cloud_routine_ingest_empty_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    receipt_path = tmp_path / "empty.json"
    receipt_path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match="receipt delivery is empty"):
        module.load_receipts([receipt_path])


def test_consumer_rejects_a_terminal_human_lever(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "cloud-routine-ingest.py"
    spec = importlib.util.spec_from_file_location("cloud_routine_ingest_terminal_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    registry = tmp_path / "his-hand-levers.json"
    registry.write_text(
        json.dumps({"levers": [{"id": "L-DONE", "status": "discharged"}]}),
        encoding="utf-8",
    )
    receipt = _receipt(
        disposition="human_gate",
        owner_ref="lever:L-DONE",
    )

    with pytest.raises(ValueError, match="terminal/inactive"):
        module.validate_human_gate_owners([receipt], lever_path=registry)


def test_consumer_rejects_a_routine_absent_from_manifest(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "cloud-routine-ingest.py"
    spec = importlib.util.spec_from_file_location("cloud_routine_ingest_manifest_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        json.dumps([_receipt(routine_id="fleat-audit").model_dump(mode="json")]),
        encoding="utf-8",
    )
    manifest = tmp_path / "cloud-routines.json"
    manifest.write_text(json.dumps({"routines": [{"name": "fleet-audit"}]}), encoding="utf-8")

    with pytest.raises(ValueError, match="absent from cloud-routines.json"):
        module.load_receipts([receipt_path], manifest_path=manifest)


def test_closure_checker_delegates_manifest_validation(capsys, monkeypatch) -> None:
    script = ROOT / "scripts" / "check-cloud-routine-ingest.py"
    spec = importlib.util.spec_from_file_location("cloud_routine_checker_manifest_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class _FakeIngest:
        @staticmethod
        def validate_routine_ids(_receipts, *, manifest_path):
            raise ValueError(f"manifest sentinel: {manifest_path.name}")

        @staticmethod
        def validate_human_gate_owners(_receipts, *, lever_path):
            return None

        @staticmethod
        def active_lever_ids(_path):
            return {"L-IRF-P0-HUMAN-ACTIONS-20260808"}

    monkeypatch.setattr(module, "_load_ingest_module", lambda: _FakeIngest)

    assert module.main() == 1
    assert "manifest sentinel" in capsys.readouterr().out


def test_irf_validator_derives_every_row_owner() -> None:
    script = ROOT / "scripts" / "check-cloud-routine-ingest.py"
    spec = importlib.util.spec_from_file_location("cloud_routine_checker_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    receipt = json.loads((ROOT / "docs" / "receipts" / "irf-p0-owner-classification-20260808.json").read_text())
    broken = json.loads(json.dumps(receipt))
    owned_row = next(row for row in broken["rows"] if row["disposition"] == "owned")
    owned_row.pop("owner_ref")

    failures = module.validate_irf_receipt(
        broken,
        active_levers={str(receipt["human_gate_owner"]).removeprefix("lever:")},
    )

    assert any("owned-row ownership drift" in failure for failure in failures)


def test_irf_validator_allows_terminal_empty_human_partition() -> None:
    script = ROOT / "scripts" / "check-cloud-routine-ingest.py"
    spec = importlib.util.spec_from_file_location("cloud_routine_checker_empty_human_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    receipt = json.loads((ROOT / "docs" / "receipts" / "irf-p0-owner-classification-20260808.json").read_text())
    human_ids = set(receipt["human_gate_irf_ids"])
    for row in receipt["rows"]:
        if row["irf_id"] in human_ids:
            row.update(
                owner_kind="irf",
                owner_ref=f"irf:{row['irf_id']}",
                disposition="owned",
            )
    receipt["human_gate_irf_ids"] = []

    assert module.validate_irf_receipt(receipt, active_levers=set()) == []


def test_cloud_human_gates_have_named_levers() -> None:
    lever_data = json.loads((ROOT / "his-hand-levers.json").read_text())
    lever_ids = {lever["id"] for lever in lever_data["levers"]}

    assert {
        "L-CLOUD-BULK-PR-CLOSE-N75",
        "L-CLOUD-EXTERNAL-GOVERNANCE-N77",
        "L-CLOUD-SESSION-SCOPE-EXPANSION",
        "L-CLOUD-ARCHIVE-ENTERPRISE-PLUGIN-N80",
        "L-LAUNCHDARKLY-OAUTH-CONSENT",
        "L-IRF-P0-HUMAN-ACTIONS-20260808",
    } <= lever_ids


def test_cloud_lever_predicates_require_terminal_status() -> None:
    rows = json.loads((ROOT / "docs" / "receipts" / "cloud-routine-findings-20260808.json").read_text())
    by_key = {row["stable_finding_key"]: row for row in rows}

    for key in (
        "LIMEN-N75",
        "LIMEN-N77",
        "hosted-session.repository-scope",
    ):
        predicate = by_key[key]["predicate"]
        assert "{'discharged','retired','done','closed'}" in predicate
        assert "!= 'open'" not in predicate


def test_model_rejects_clustered_shell_command_options() -> None:
    with pytest.raises(ValidationError, match="one executable command"):
        _receipt(predicate="bash -uc 'false; true'")
