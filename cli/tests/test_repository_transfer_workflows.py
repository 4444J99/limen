from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "repository-transfer-workflows.py"
SPEC = importlib.util.spec_from_file_location("repository_transfer_workflows", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_policy_partitions_every_live_workflow_from_frozen_manifest() -> None:
    policy = json.loads(MODULE.POLICY_PATH.read_text())
    frozen = {value["path"] for value in policy["freeze"]}
    active = set(policy["leave_active_during_freeze"])

    assert not frozen & active
    assert ".github/workflows/ci.yml" in frozen
    assert ".github/workflows/pr-gate.yml" in active
    observed = {value["path"] for value in policy["observe_and_requery_after_transfer"]}
    assert "dynamic/agents/copilot-pull-request-reviewer" in observed
    assert not observed & frozen


def test_enable_predicates_are_stricter_for_apps_and_release() -> None:
    policy = json.loads(MODULE.POLICY_PATH.read_text())
    by_path = {value["path"]: value for value in policy["freeze"]}

    ci = MODULE._required_predicates(policy, by_path[".github/workflows/ci.yml"])
    reviewer = MODULE._required_predicates(policy, by_path[".github/workflows/claude-review.yml"])
    release = MODULE._required_predicates(policy, by_path[".github/workflows/pypi.yml"])

    assert "repository_transferred" in ci
    assert "repository_secrets_verified" not in ci
    assert "public_repository_verified" in ci
    assert "github_hosted_standard_runner_verified" in ci
    assert "zero_spend_policy_verified" in ci
    assert "exact_repository_app_access_verified" in reviewer
    assert "pypi_trusted_publisher_owner_updated" in release
    assert by_path[".github/workflows/limen-warp-oz.yml"]["zero_spend_prohibited"] is True


def test_workflow_census_is_exhaustive_across_pages(monkeypatch) -> None:
    pages = [
        {"total_count": 2, "workflows": [{"id": 10, "path": "a.yml"}]},
        {"total_count": 2, "workflows": [{"id": 11, "path": "b.yml"}]},
    ]
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, json.dumps(pages), ""),
    )

    assert [row["id"] for row in MODULE._workflow_rows("owner/repo")] == [10, 11]


def test_exact_partition_rejects_missing_or_unowned_live_workflows() -> None:
    partition = {"a.yml", "b.yml"}
    exact = {path: {"path": path} for path in partition}
    MODULE._require_exact_partitions(exact, exact, partition)

    with pytest.raises(MODULE.WorkflowTransferError, match="partitions differ"):
        MODULE._require_exact_partitions({"a.yml": exact["a.yml"]}, exact, partition)
    with pytest.raises(MODULE.WorkflowTransferError, match="partitions differ"):
        MODULE._require_exact_partitions({**exact, "extra.yml": {}}, exact, partition)


def test_enable_target_is_single_governed_non_tombstone_and_zero_spend_safe() -> None:
    rows = {
        "ci.yml": {},
        "tombstone.yml": {"non_enableable_tombstone": True},
        "paid.yml": {"zero_spend_prohibited": True},
    }
    assert MODULE._enable_target(["ci.yml"], rows) == "ci.yml"
    with pytest.raises(MODULE.WorkflowTransferError, match="exactly one"):
        MODULE._enable_target(["ci.yml", "paid.yml"], rows)
    with pytest.raises(MODULE.WorkflowTransferError, match="not transfer-governed"):
        MODULE._enable_target(["unknown.yml"], rows)
    with pytest.raises(MODULE.WorkflowTransferError, match="API tombstone"):
        MODULE._enable_target(["tombstone.yml"], rows)
    with pytest.raises(MODULE.WorkflowTransferError, match="zero-spend"):
        MODULE._enable_target(["paid.yml"], rows)


def test_predicate_receipt_hashes_structured_exact_target_evidence(tmp_path: Path) -> None:
    private = tmp_path / ".limen-private"
    private.mkdir()
    path = private / "predicate.json"
    workflow = {"id": 42, "path": ".github/workflows/ci.yml"}
    manifest = {"github": {"default_sha": "a" * 40}}
    predicate = "repository_transferred"
    proof = {
        "schema_version": "limen.workflow_enable_predicate_evidence.v1",
        "predicate": predicate,
        "repository_id": 1_255_213_941,
        "canonical_coordinate": "4444J99/limen",
        "default_sha": "a" * 40,
        "workflow_path": workflow["path"],
        "workflow_id": workflow["id"],
        "command": "gh api repos/4444J99/limen",
        "exit_code": 0,
        "observed_at": "2026-08-25T12:00:00+00:00",
    }
    receipt = {
        "schema_version": "limen.workflow_enable_evidence.v1",
        "repository_id": 1_255_213_941,
        "observed_coordinate": "4444J99/limen",
        "canonical_coordinate": "4444J99/limen",
        "default_sha": "a" * 40,
        "workflow_path": workflow["path"],
        "workflow_id": workflow["id"],
        "predicates": {
            predicate: {
                "satisfied": True,
                "evidence": proof,
                "evidence_sha256": MODULE.canonical_sha256(proof),
            }
        },
    }
    path.write_text(json.dumps(receipt))
    path.with_suffix(".json.sha256").write_text(MODULE.canonical_sha256(receipt) + "\n")

    assert (
        MODULE._predicate_evidence(
            path,
            required={predicate},
            repo="4444J99/limen",
            workflow=workflow,
            manifest=manifest,
        )
        == receipt
    )

    receipt["predicates"][predicate]["evidence_sha256"] = "b" * 64
    path.write_text(json.dumps(receipt))
    path.with_suffix(".json.sha256").write_text(MODULE.canonical_sha256(receipt) + "\n")
    with pytest.raises(MODULE.WorkflowTransferError, match="lacks durable evidence"):
        MODULE._predicate_evidence(
            path,
            required={predicate},
            repo="4444J99/limen",
            workflow=workflow,
            manifest=manifest,
        )


def test_v2_manifest_is_rejected_even_when_its_digest_is_valid(tmp_path: Path) -> None:
    private = tmp_path / ".limen-private"
    private.mkdir()
    path = private / "manifest.json"
    manifest = {
        "schema_version": "limen.repository_transfer_manifest.v2",
        "identity": MODULE.LIMEN_REPOSITORY_IDENTITY.model_dump(mode="json"),
    }
    path.write_text(json.dumps(manifest))
    path.with_suffix(".json.sha256").write_text(MODULE.canonical_sha256(manifest) + "\n")

    with pytest.raises(MODULE.WorkflowTransferError, match="predates the complete v3"):
        MODULE._private_manifest(path)


def _mutation_fixture() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    manifest = {
        "identity": MODULE.LIMEN_REPOSITORY_IDENTITY.model_dump(mode="json"),
        "github": {"default_sha": "a" * 40},
    }
    before = [{"id": 42, "path": ".github/workflows/ci.yml", "state": "active"}]
    plan = [
        {
            "id": 42,
            "path": ".github/workflows/ci.yml",
            "class": "recovery_ci",
            "current_state": "active",
            "desired_state": "disabled_manually",
        }
    ]
    return manifest, before, plan


def test_mutation_writes_immutable_intent_before_effect_and_terminal_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest, before, plan = _mutation_fixture()
    receipt_path = tmp_path / "freeze-receipt.json"
    intent_path = MODULE._intent_path(receipt_path)
    observed_calls: list[tuple[str, int, str]] = []

    def set_state(repo: str, workflow_id: int, action: str) -> None:
        assert intent_path.is_file()
        assert stat.S_IMODE(intent_path.stat().st_mode) == 0o400
        observed_calls.append((repo, workflow_id, action))

    monkeypatch.setattr(MODULE, "_set_state", set_state)
    monkeypatch.setattr(
        MODULE,
        "_workflow_rows",
        lambda _repo: [{"id": 42, "path": ".github/workflows/ci.yml", "state": "disabled_manually"}],
    )

    MODULE._mutate_with_journal(
        repo="organvm/limen",
        manifest=manifest,
        operation="disable",
        before=before,
        plan=plan,
        receipt_path=receipt_path,
    )

    intent = json.loads(intent_path.read_text())
    receipt = json.loads(receipt_path.read_text())
    assert observed_calls == [("organvm/limen", 42, "disable")]
    assert intent["transitions"][0]["mutation_required"] is True
    intent_payload = {key: value for key, value in intent.items() if key != "intent_payload_sha256"}
    assert intent["intent_payload_sha256"] == MODULE.canonical_sha256(intent_payload)
    assert receipt["status"] == "succeeded"
    assert receipt["intent_sha256"] == MODULE.canonical_sha256(intent)
    assert receipt["after_states_available"] is True
    assert "failure" not in receipt


def test_mutation_failure_keeps_intent_and_writes_terminal_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest, before, plan = _mutation_fixture()
    receipt_path = tmp_path / "freeze-receipt.json"
    intent_path = MODULE._intent_path(receipt_path)
    intent_bytes: bytes | None = None

    def fail_after_intent(_repo: str, _workflow_id: int, _action: str) -> None:
        nonlocal intent_bytes
        assert intent_path.is_file()
        intent_bytes = intent_path.read_bytes()
        raise MODULE.WorkflowTransferError("simulated mutation failure")

    def fail_observation(_repo: str) -> list[dict[str, Any]]:
        raise MODULE.WorkflowTransferError("simulated observation failure")

    monkeypatch.setattr(MODULE, "_set_state", fail_after_intent)
    monkeypatch.setattr(MODULE, "_workflow_rows", fail_observation)

    with pytest.raises(MODULE.WorkflowTransferError, match="simulated mutation failure"):
        MODULE._mutate_with_journal(
            repo="organvm/limen",
            manifest=manifest,
            operation="disable",
            before=before,
            plan=plan,
            receipt_path=receipt_path,
        )

    receipt = json.loads(receipt_path.read_text())
    assert intent_bytes is not None
    assert intent_path.read_bytes() == intent_bytes
    assert receipt["status"] == "failed"
    assert receipt["failure"]["error_class"] == "WorkflowTransferError"
    assert receipt["after_states_available"] is False
    assert receipt["after_observation_failure"]["error_class"] == "WorkflowTransferError"


@pytest.mark.parametrize(
    ("live_state", "expected_status", "expected_incomplete"),
    [
        ("disabled_manually", "succeeded", []),
        ("active", "failed", [".github/workflows/ci.yml"]),
    ],
)
def test_interrupted_mutation_reconciliation_binds_live_state_without_replaying_effect(
    tmp_path: Path,
    monkeypatch,
    live_state: str,
    expected_status: str,
    expected_incomplete: list[str],
) -> None:
    manifest, before, plan = _mutation_fixture()
    receipt_path = tmp_path / "freeze-receipt.json"
    intent = MODULE._operation_intent(
        repo="organvm/limen",
        manifest=manifest,
        operation="disable",
        before=before,
        plan=plan,
    )
    MODULE._write_receipt(MODULE._intent_path(receipt_path), intent, immutable=True)
    monkeypatch.setattr(
        MODULE,
        "_set_state",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("effect replayed")),
    )

    receipt = MODULE._reconcile_interrupted_journal(
        repo="organvm/limen",
        manifest=manifest,
        receipt_path=receipt_path,
        observed=[{"id": 42, "path": ".github/workflows/ci.yml", "state": live_state}],
    )

    assert receipt["status"] == expected_status
    assert receipt["intent_sha256"] == MODULE.canonical_sha256(intent)
    assert receipt["reconciliation"]["observed_without_mutation"] is True
    assert receipt["reconciliation"]["incomplete_paths"] == expected_incomplete
    assert json.loads(receipt_path.read_text()) == receipt


def test_interrupted_mutation_reconciliation_rejects_tampered_intent(tmp_path: Path) -> None:
    manifest, before, plan = _mutation_fixture()
    receipt_path = tmp_path / "freeze-receipt.json"
    intent_path = MODULE._intent_path(receipt_path)
    intent = MODULE._operation_intent(
        repo="organvm/limen",
        manifest=manifest,
        operation="disable",
        before=before,
        plan=plan,
    )
    intent["selected_paths"] = [".github/workflows/tampered.yml"]
    intent_path.write_text(json.dumps(intent))

    with pytest.raises(MODULE.WorkflowTransferError, match="invalid or not bound"):
        MODULE._reconcile_interrupted_journal(
            repo="organvm/limen",
            manifest=manifest,
            receipt_path=receipt_path,
            observed=before,
        )

    assert not receipt_path.exists()


def test_existing_intent_or_terminal_path_blocks_mutation_without_overwrite(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest, before, plan = _mutation_fixture()
    receipt_path = tmp_path / "freeze-receipt.json"
    intent_path = MODULE._intent_path(receipt_path)
    intent_path.write_text("existing immutable intent\n")
    effect_attempted = False

    def set_state(_repo: str, _workflow_id: int, _action: str) -> None:
        nonlocal effect_attempted
        effect_attempted = True

    monkeypatch.setattr(MODULE, "_set_state", set_state)

    with pytest.raises(MODULE.WorkflowTransferError, match="intent path already exists"):
        MODULE._mutate_with_journal(
            repo="organvm/limen",
            manifest=manifest,
            operation="disable",
            before=before,
            plan=plan,
            receipt_path=receipt_path,
        )

    assert effect_attempted is False
    assert intent_path.read_text() == "existing immutable intent\n"
    assert not receipt_path.exists()


def test_dangling_terminal_receipt_symlink_blocks_mutation(tmp_path: Path, monkeypatch) -> None:
    manifest, before, plan = _mutation_fixture()
    receipt_path = tmp_path / "freeze-receipt.json"
    receipt_path.symlink_to(tmp_path / "missing-receipt-target.json")
    effect_attempted = False

    def set_state(_repo: str, _workflow_id: int, _action: str) -> None:
        nonlocal effect_attempted
        effect_attempted = True

    monkeypatch.setattr(MODULE, "_set_state", set_state)

    with pytest.raises(MODULE.WorkflowTransferError, match="receipt or intent path already exists"):
        MODULE._mutate_with_journal(
            repo="organvm/limen",
            manifest=manifest,
            operation="disable",
            before=before,
            plan=plan,
            receipt_path=receipt_path,
        )

    assert effect_attempted is False
    assert receipt_path.is_symlink()
