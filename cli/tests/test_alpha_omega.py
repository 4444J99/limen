from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from limen.alpha_omega import (
    build_reconciliation_manifest,
    fixed_point_pair,
)
from limen.prima_materia import ResourceClaimV1, SourceAdapterV1
from limen.prima_materia_store import SourceRegistry
from limen.protected_exclusions import (
    ProtectedExclusion,
    ProtectedExclusionRegistry,
)
from limen.resource_envelope import ResourceTelemetry

DIGEST = "a" * 64


def _registry() -> SourceRegistry:
    instant = datetime(2026, 7, 28, tzinfo=UTC)
    adapter = SourceAdapterV1(
        adapter_id="git-native",
        source_id="gitRepositories01",
        owner_ref="owner:git",
        source_native_acquisition="git provider and local object database",
        cursor_schema_digest=DIGEST,
        completeness_predicate="all configured repository roots observed",
        privacy_transform_digest=DIGEST,
        resource_claim=ResourceClaimV1(
            claim_id="claimGitRepos001",
            hydrated_inputs_bytes=1,
            workspace_bytes=1,
            temporary_expansion_bytes=1,
            output_bytes=1,
            encryption_chunking_bytes=1,
            rollback_bytes=1,
            effective_from=instant,
            effective_until=instant + timedelta(days=1),
            rollback_until=instant + timedelta(days=2),
        ),
        recipe_version="v1",
        custody_target_refs=("archive", "recovery"),
        restoration_predicate="all refs and working state restore",
    )
    return SourceRegistry.from_adapters((adapter,))


def _repository_with_protected_worktree(tmp_path: Path) -> tuple[Path, Path]:
    repository = tmp_path / "repository"
    remote = tmp_path / "remote.git"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repository, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repository, check=True)
    (repository / "file.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repository, check=True)
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repository, check=True)
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


def test_fixed_point_is_deterministic_but_omega_stops_at_protected_owner(
    tmp_path: Path,
) -> None:
    repository, protected = _repository_with_protected_worktree(tmp_path)
    exclusion = ProtectedExclusion(
        exclusion_id="career",
        owner="career-owner",
        path=Path(".worktrees/career"),
        branch="work/career",
        registration=Path(".git/worktrees/career"),
        blocks_omega=True,
        reason="active externally owned workstream",
    )
    protected_registry = ProtectedExclusionRegistry.from_exclusions(
        repository,
        (exclusion,),
    )
    instant = datetime(2026, 7, 28, 12, tzinfo=UTC)
    telemetry = ResourceTelemetry(
        observed_at=instant,
        ram_total_bytes=16 * 1024**3,
        ram_available_bytes=8 * 1024**3,
        swap_used_bytes=0,
        updater_claim_bytes=0,
        apfs_churn_bytes=0,
        telemetry_error_bytes=0,
    )
    receipts = {
        "frozen_storage_terminal_custody": True,
        "removed_repositories_reconstruct": True,
        "private_material_restores_from_two_devices": True,
        "empty_scratch_bootstrap_passed": True,
        "hydration_passed": True,
        "replay_passed": True,
        "composition_passed": True,
        "dematerialization_passed": True,
    }
    arguments = {
        "repository_root": repository,
        "base_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "repositories": {"career": protected},
        "private_roots": {},
        "source_registry": _registry(),
        "observed_source_ids": ("gitRepositories01",),
        "protected_registry": protected_registry,
        "resource_telemetry": telemetry,
        "physical_devices": {"available": True, "device_count": 2},
        "protected_processes": {
            "available": True,
            "protected_cwds": [{"exclusion_id": "career", "active_cwd_count": 1}],
        },
        "automatically_safe_reclaim_count": 0,
        "receipt_predicates": receipts,
        "observed_at": instant,
    }

    first = build_reconciliation_manifest(**arguments)
    second = build_reconciliation_manifest(**arguments)
    pair = fixed_point_pair(first, second)

    assert first["lambda_passed"] is True
    assert first["omega_admitted"] is False
    assert first["protected_exclusions"]["omega_blocker_count"] == 1
    assert pair["unchanged"] is True
    assert pair["lambda_passed"] is True
    assert pair["omega_admitted"] is False
    encoded = json.dumps(first, sort_keys=True)
    assert str(tmp_path) not in encoded
    assert str(protected) not in encoded
    assert "work/career" not in encoded


def test_unknown_source_remains_visible_lambda_debt(tmp_path: Path) -> None:
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
                reason="active",
            ),
        ),
    )
    instant = datetime(2026, 7, 28, 12, tzinfo=UTC)
    manifest = build_reconciliation_manifest(
        repository_root=repository,
        base_sha="a" * 40,
        repositories={"career": protected},
        private_roots={},
        source_registry=_registry(),
        observed_source_ids=("gitRepositories01", "unknownSource001"),
        protected_registry=protected_registry,
        resource_telemetry=ResourceTelemetry(
            observed_at=instant,
            ram_total_bytes=16 * 1024**3,
            ram_available_bytes=8 * 1024**3,
            swap_used_bytes=0,
            updater_claim_bytes=0,
            apfs_churn_bytes=0,
            telemetry_error_bytes=0,
        ),
        physical_devices={"available": True, "device_count": 2},
        protected_processes={"available": True, "protected_cwds": []},
        automatically_safe_reclaim_count=None,
        repository_census_complete=False,
        observed_at=instant,
    )

    assert manifest["source_coverage"]["missing_adapter_count"] == 1
    assert manifest["lambda_predicates"]["frozen_wave_adapter_debt_zero"] is False
    assert manifest["automatically_safe_reclaim_count"] is None
    assert manifest["lambda_predicates"]["automatically_safe_reclaim_zero"] is False
    assert manifest["repository_census_complete"] is False
    assert manifest["lambda_predicates"]["frozen_repository_terminal_custody"] is False
    assert manifest["lambda_passed"] is False
