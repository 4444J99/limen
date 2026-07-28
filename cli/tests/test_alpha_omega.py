from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from limen.alpha_omega import (
    LAMBDA_PREDICATES,
    AlphaOmegaError,
    LambdaRungRegistryV1,
    LambdaRungV1,
    ReclaimCensusReceiptV1,
    SourceInventoryReceiptV1,
    build_reconciliation_manifest,
    fixed_point_pair,
    frozen_wave_digest,
    lambda_rung_registry_digest,
    repository_projection,
)
from limen.omega_owner_receipt import build_owner_receipt, write_owner_receipt
from limen.prima_materia import (
    FrozenDeviceRoleV1,
    FrozenRepositoryV1,
    FrozenSourceInstanceV1,
    FrozenWaveManifestV1,
    ResourceClaimV1,
    SourceAdapterV1,
)
from limen.prima_materia_store import SourceRegistry
from limen.protected_exclusions import (
    ProtectedExclusion,
    ProtectedExclusionRegistry,
)
from limen.resource_envelope import ResourceTelemetry

DIGEST = "a" * 64
MAIN_SHA = "b" * 40
RUNTIME_SHA = "c" * 40
INSTANT = datetime(2026, 7, 28, 12, tzinfo=UTC)


def _path_digest(path: Path) -> str:
    return hashlib.sha256(str(path.resolve(strict=False)).encode()).hexdigest()


def _registry() -> SourceRegistry:
    return SourceRegistry.from_adapters(
        (
            SourceAdapterV1(
                adapter_id="git-native",
                source_id="gitRepositories01",
                owner_ref="owner:git",
                source_native_acquisition="git provider and local object database",
                cursor_schema_digest=DIGEST,
                completeness_predicate="all configured repository roots observed",
                privacy_transform_digest=DIGEST,
                claim_recipe="git-source-instance-resource-claim-v1",
                recipe_version="v1",
                custody_target_refs=("archive", "recovery"),
                restoration_predicate="all refs and working state restore",
            ),
        )
    )


def _repository_with_protected_worktree(tmp_path: Path) -> tuple[Path, Path]:
    repository = tmp_path / "repository"
    remote = tmp_path / "remote.git"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=repository,
        check=True,
    )
    (repository / "file.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repository, check=True)
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", str(remote)],
        cwd=repository,
        check=True,
    )
    protected = repository / ".worktrees" / "career"
    protected.parent.mkdir()
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "work/career", str(protected)],
        cwd=repository,
        check=True,
    )
    subprocess.run(["git", "push", "-q", "--all", "origin"], cwd=repository, check=True)
    (protected / "file.txt").write_text("live work\n", encoding="utf-8")
    return repository, protected


def _rungs() -> LambdaRungRegistryV1:
    return LambdaRungRegistryV1(
        rungs=tuple(
            LambdaRungV1(
                rung_id=rung_id,
                predicate=(f"python3 owner.py --rung-id {rung_id} --frozen-wave-sha {{frozen_wave_sha256}}"),
                timeout_seconds=60,
                max_age_seconds=3600,
                receipt_path=f"logs/owner/{rung_id}.json",
            )
            for rung_id in sorted(LAMBDA_PREDICATES)
        )
    )


def _claim() -> ResourceClaimV1:
    return ResourceClaimV1(
        claim_id="claimGitRepos001",
        source_instance_id="sourceInstance0000000001",
        operation_id="inspectGitRepos001",
        hydrated_inputs_bytes=1,
        workspace_bytes=1,
        temporary_expansion_bytes=1,
        output_bytes=1,
        encryption_chunking_bytes=1,
        rollback_bytes=1,
        memory_bytes=1,
        file_count=1,
        network_bytes=1,
        wall_time_seconds=60,
        effective_from=INSTANT - timedelta(minutes=1),
        effective_until=INSTANT + timedelta(hours=1),
        rollback_until=INSTANT + timedelta(hours=2),
    )


def _contracts(
    repository: Path,
    protected: Path,
    protected_registry: ProtectedExclusionRegistry,
) -> tuple[
    FrozenWaveManifestV1,
    SourceInventoryReceiptV1,
    ReclaimCensusReceiptV1,
    LambdaRungRegistryV1,
]:
    source_registry = _registry()
    source_instance = FrozenSourceInstanceV1(
        instance_id="sourceInstance0000000001",
        source_id="gitRepositories01",
    )
    devices = (
        FrozenDeviceRoleV1(
            role_id="archive",
            physical_device_sha256=hashlib.sha256(b"disk-a").hexdigest(),
        ),
        FrozenDeviceRoleV1(
            role_id="recovery",
            physical_device_sha256=hashlib.sha256(b"disk-b").hexdigest(),
        ),
    )
    wave = FrozenWaveManifestV1(
        wave_id="waveIdentifier0001",
        frozen_at=INSTANT,
        enumeration_complete=True,
        repositories=(
            FrozenRepositoryV1(
                repository_id="careerRepository0001",
                path_sha256=_path_digest(protected),
            ),
        ),
        storage_roots=(),
        source_instances=(source_instance,),
        device_roles=devices,
        protected_exclusion_ids=("career",),
        protected_registry_digest=protected_registry.registry_digest,
        source_registry_digest=source_registry.registry_digest,
        source_inventory_producer_digest=DIGEST,
        lambda_rung_registry_digest=lambda_rung_registry_digest(_rungs()),
        remote_main_sha=MAIN_SHA,
        installed_runtime_sha=RUNTIME_SHA,
        control_plane_runtime_path_sha256=hashlib.sha256(b"installed-runtime").hexdigest(),
        control_plane_repository="https://example.invalid/repository.git",
        control_plane_default_branch="main",
    )
    wave_sha256 = frozen_wave_digest(wave)
    inventory = SourceInventoryReceiptV1(
        observed_at=INSTANT,
        frozen_wave_sha256=wave_sha256,
        producer_digest=DIGEST,
        complete=True,
        source_instances=(source_instance,),
    )
    census = ReclaimCensusReceiptV1(
        observed_at=INSTANT,
        frozen_wave_sha256=wave_sha256,
        plan_sha256=DIGEST,
        protected_registry_digest=protected_registry.registry_digest,
        scanned_count=1,
        candidate_count=0,
        deferred_count=0,
        failure_count=0,
        complete=True,
    )
    return wave, inventory, census, _rungs()


def _write_owner_receipts(
    repository: Path,
    wave: FrozenWaveManifestV1,
    rungs: LambdaRungRegistryV1,
    *,
    observed_at: datetime = INSTANT,
    wrong_rung: str | None = None,
) -> None:
    wave_sha256 = frozen_wave_digest(wave)
    for rung in rungs.rungs:
        predicate = rung.predicate.replace("{frozen_wave_sha256}", wave_sha256)
        if rung.rung_id == wrong_rung:
            predicate += " --wrong"
        receipt = build_owner_receipt(
            rung_id=rung.rung_id,
            predicate=predicate,
            returncode=0,
            observed_at=observed_at,
        )
        write_owner_receipt(repository / rung.receipt_path, receipt)


def _arguments(tmp_path: Path) -> tuple[dict, Path]:
    repository, protected = _repository_with_protected_worktree(tmp_path)
    protected_registry = ProtectedExclusionRegistry.from_exclusions(
        repository,
        (
            ProtectedExclusion(
                exclusion_id="career",
                owner="career-owner",
                path=Path(".worktrees/career"),
                branch="work/career",
                registration=Path(".git/worktrees/career"),
                blocks_omega=True,
                reason="active externally owned workstream",
            ),
        ),
    )
    wave, inventory, census, rungs = _contracts(
        repository,
        protected,
        protected_registry,
    )
    _write_owner_receipts(repository, wave, rungs)
    arguments = {
        "repository_root": repository,
        "frozen_wave": wave,
        "repositories": {"careerRepository0001": protected},
        "private_roots": {},
        "source_registry": _registry(),
        "source_inventory": inventory,
        "protected_registry": protected_registry,
        "resource_claims": (_claim(),),
        "resource_task_graph_digest": DIGEST,
        "reclaim_census": census,
        "lambda_rungs": rungs,
        "resource_telemetry": ResourceTelemetry(
            observed_at=INSTANT,
            ram_total_bytes=16 * 1024**3,
            ram_available_bytes=8 * 1024**3,
            swap_used_bytes=0,
            updater_claim_bytes=0,
            apfs_churn_bytes=0,
            telemetry_error_bytes=0,
        ),
        "physical_devices": {
            "available": True,
            "device_count": 2,
            "device_identity_digests": [
                hashlib.sha256(b"disk-a").hexdigest(),
                hashlib.sha256(b"disk-b").hexdigest(),
            ],
        },
        "protected_processes": {
            "available": True,
            "protected_cwds": [{"exclusion_id": "career", "active_cwd_count": 1}],
        },
        "control_plane": {
            "available": True,
            "matches_frozen_wave": True,
            "remote_main_sha": MAIN_SHA,
            "installed_runtime_sha": RUNTIME_SHA,
        },
        "audit_deadline_seconds": 60,
        "observed_at": INSTANT,
    }
    return arguments, protected


def test_fixed_point_is_complete_but_omega_stops_at_protected_owner(
    tmp_path: Path,
) -> None:
    arguments, protected = _arguments(tmp_path)

    first = build_reconciliation_manifest(**arguments)
    second = build_reconciliation_manifest(**arguments)
    pair = fixed_point_pair(first, second)

    assert first["audit_complete"] is True
    assert first["lambda_passed"] is True
    assert first["omega_admitted"] is False
    assert pair["complete"] is True
    assert pair["unchanged"] is True
    assert pair["lambda_passed"] is True
    assert pair["omega_admitted"] is False
    encoded = json.dumps(first, sort_keys=True)
    assert str(tmp_path) not in encoded
    assert str(protected) not in encoded
    assert "work/career" not in encoded


def test_wrong_predicate_receipt_fails_closed(tmp_path: Path) -> None:
    arguments, _protected = _arguments(tmp_path)
    repository = arguments["repository_root"]
    wave = arguments["frozen_wave"]
    rungs = arguments["lambda_rungs"]
    _write_owner_receipts(
        repository,
        wave,
        rungs,
        wrong_rung="hydration_passed",
    )

    manifest = build_reconciliation_manifest(**arguments)

    assert manifest["audit_complete"] is False
    assert manifest["state"]["lambda_predicates"]["hydration_passed"] is False
    assert "owner_receipts_complete" in manifest["state"]["incomplete_inputs"]


def test_stale_owner_receipt_fails_closed(tmp_path: Path) -> None:
    arguments, _protected = _arguments(tmp_path)
    _write_owner_receipts(
        arguments["repository_root"],
        arguments["frozen_wave"],
        arguments["lambda_rungs"],
        observed_at=INSTANT - timedelta(days=2),
    )

    manifest = build_reconciliation_manifest(**arguments)

    assert manifest["audit_complete"] is False
    assert manifest["lambda_passed"] is False


def test_source_disappearance_and_unknown_source_remain_visible(tmp_path: Path) -> None:
    arguments, _protected = _arguments(tmp_path)
    inventory = arguments["source_inventory"]
    arguments["source_inventory"] = inventory.model_copy(
        update={
            "source_instances": (
                FrozenSourceInstanceV1(
                    instance_id="unknownInstance00000001",
                    source_id="unknownSource000000001",
                ),
            )
        }
    )

    manifest = build_reconciliation_manifest(**arguments)

    assert manifest["audit_complete"] is False
    assert manifest["state"]["source_coverage"]["missing_adapter_count"] == 1
    assert manifest["state"]["lambda_predicates"]["frozen_wave_adapter_debt_zero"] is False


def test_incomplete_denominator_and_unavailable_probe_fail_closed(
    tmp_path: Path,
) -> None:
    arguments, _protected = _arguments(tmp_path)
    arguments["repositories"] = {}
    arguments["physical_devices"] = {
        "available": False,
        "device_count": 0,
        "device_identity_digests": [],
    }

    manifest = build_reconciliation_manifest(**arguments)

    assert manifest["audit_complete"] is False
    assert "repository_denominator_matches" in manifest["state"]["incomplete_inputs"]
    assert "physical_device_probe_complete" in manifest["state"]["incomplete_inputs"]
    assert manifest["lambda_passed"] is False


def test_repository_command_timeout_is_not_misreported_as_absence(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    row = repository_projection(
        "repositoryIdentifier01",
        repository,
        runner=lambda command, _cwd, _timeout: subprocess.CompletedProcess(
            command,
            124,
            "",
            "timeout",
        ),
    )

    assert row["available"] is False
    assert row["reason"] == "repository-probe-incomplete"


def test_empty_task_graph_and_unauthorized_control_anchor_fail_closed(
    tmp_path: Path,
) -> None:
    arguments, _protected = _arguments(tmp_path)
    arguments["resource_claims"] = ()
    arguments["control_plane"] = {
        "available": True,
        "matches_frozen_wave": False,
    }

    manifest = build_reconciliation_manifest(**arguments)

    assert manifest["audit_complete"] is False
    assert manifest["state"]["lambda_predicates"]["dynamic_resource_envelope_nonnegative"] is False
    assert "control_plane_anchor_matches" in manifest["state"]["incomplete_inputs"]


def test_unrelated_resource_claim_cannot_cover_the_frozen_source(
    tmp_path: Path,
) -> None:
    arguments, _protected = _arguments(tmp_path)
    arguments["resource_claims"] = (
        _claim().model_copy(
            update={"source_instance_id": "unrelatedSourceInstance01"},
        ),
    )

    manifest = build_reconciliation_manifest(**arguments)

    assert manifest["audit_complete"] is False
    assert manifest["state"]["resource_envelope"]["claims_complete"] is False
    assert manifest["state"]["lambda_predicates"]["dynamic_resource_envelope_nonnegative"] is False


def test_self_asserted_source_inventory_producer_fails_closed(
    tmp_path: Path,
) -> None:
    arguments, _protected = _arguments(tmp_path)
    inventory = arguments["source_inventory"]
    arguments["source_inventory"] = inventory.model_copy(
        update={"producer_digest": "d" * 64},
    )

    manifest = build_reconciliation_manifest(**arguments)

    assert manifest["audit_complete"] is False
    assert "source_inventory_matches" in manifest["state"]["incomplete_inputs"]


def test_fixed_point_recomputes_state_digest(tmp_path: Path) -> None:
    arguments, _protected = _arguments(tmp_path)
    first = build_reconciliation_manifest(**arguments)
    second = build_reconciliation_manifest(**arguments)
    second["state"]["lambda_predicates"]["hydration_passed"] = False

    with pytest.raises(AlphaOmegaError, match="state-digest-invalid"):
        fixed_point_pair(first, second)
