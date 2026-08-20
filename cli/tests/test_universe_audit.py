from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from limen.prima_materia import (
    CollaboratorProjectRelationshipV1,
    CollaboratorUniverseEntryV1,
    CollaboratorUniverseManifestV1,
    ProjectUniverseEntryV1,
    ProjectUniverseManifestV1,
    UniverseSourceAdapterV1,
    UniverseSourceRegistryV1,
)
from limen.universe_audit import (
    CHECKS,
    GitHubProjectionPlanV1,
    canonical_digest,
    evaluate_universe_check,
)

DIGEST = "a" * 64
RUNTIME_SHA = "b" * 40
INSTANT = datetime(2026, 7, 28, 20, tzinfo=UTC)


def _source_registry() -> UniverseSourceRegistryV1:
    return UniverseSourceRegistryV1(
        registry_id="universeSources001",
        adapters=(
            UniverseSourceAdapterV1(
                adapter_id="source-adapter",
                source_kind="fixture_source",
                owner_ref="fixture-owner",
                census_enumerator_ref="fixture-census",
                project_enumerator_ref="fixture-projects",
                collaborator_enumerator_ref="fixture-collaborators",
                completeness_predicate="every fixture source is observed",
                privacy_projection_ref="fixture-privacy",
            ),
        ),
    )


def _project_manifest(
    source_registry: UniverseSourceRegistryV1,
    *,
    build_status: str = "passed",
    source_complete: bool = True,
    project_complete: bool = True,
) -> ProjectUniverseManifestV1:
    project = ProjectUniverseEntryV1(
        project_id="projectIdentifier01",
        source_lineage_ids=("sourceLineage001",),
        repository_ids=(),
        child_task_ids=("taskIdentifier001",),
        artifact_refs=("artifact-project",) if build_status == "passed" else (),
        collaborator_ids=("collaboratorId01",),
        lifecycle_stage="live",
        predicate_refs=("build-predicate",),
        receipt_refs=("project-receipt",),
        coverage_disposition="complete" if project_complete else "partial",
        build_status=build_status,
    )
    return ProjectUniverseManifestV1(
        manifest_id="projectManifest001",
        frozen_at=INSTANT,
        frozen_wave_digest=DIGEST,
        source_registry_digest=source_registry.canonical_digest,
        enumeration_complete=True,
        required_source_instance_ids=("sourceInstance001",),
        observed_source_instance_ids=("sourceInstance001",) if source_complete else (),
        missing_source_instance_ids=() if source_complete else ("sourceInstance001",),
        unexpected_source_instance_ids=(),
        required_project_ids=("projectIdentifier01",),
        missing_project_ids=(),
        unexpected_project_ids=(),
        projects=(project,),
    )


def _collaborator_manifest(
    source_registry: UniverseSourceRegistryV1,
    project_manifest: ProjectUniverseManifestV1,
    *,
    source_complete: bool = True,
    reconciled: bool = True,
) -> CollaboratorUniverseManifestV1:
    collaborator = CollaboratorUniverseEntryV1(
        collaborator_id="collaboratorId01",
        source_lineage_ids=("collaboratorLineage001",),
        relationships=(
            CollaboratorProjectRelationshipV1(
                project_id="projectIdentifier01",
                roles=("advisor",),
            ),
        ),
        coverage_disposition="reconciled" if reconciled else "unknown",
        disposition_receipt_refs=("collaborator-receipt",) if reconciled else (),
    )
    return CollaboratorUniverseManifestV1(
        manifest_id="collaboratorManifest001",
        frozen_at=INSTANT,
        frozen_wave_digest=DIGEST,
        source_registry_digest=source_registry.canonical_digest,
        project_universe_manifest_digest=canonical_digest(project_manifest),
        enumeration_complete=True,
        required_source_instance_ids=("sourceInstance001",),
        observed_source_instance_ids=("sourceInstance001",) if source_complete else (),
        missing_source_instance_ids=() if source_complete else ("sourceInstance001",),
        unexpected_source_instance_ids=(),
        project_ids=("projectIdentifier01",),
        required_collaborator_ids=("collaboratorId01",),
        missing_collaborator_ids=(),
        unexpected_collaborator_ids=(),
        collaborators=(collaborator,),
    )


def _github_plan(
    source_registry: UniverseSourceRegistryV1,
    project_manifest: ProjectUniverseManifestV1,
    collaborator_manifest: CollaboratorUniverseManifestV1,
    *,
    observed_at: datetime = INSTANT,
    change_count: int = 0,
    privacy_findings_count: int = 0,
) -> GitHubProjectionPlanV1:
    return GitHubProjectionPlanV1(
        observed_at=observed_at,
        frozen_wave_sha256=DIGEST,
        installed_runtime_sha=RUNTIME_SHA,
        source_registry_sha256=source_registry.canonical_digest,
        project_manifest_sha256=canonical_digest(project_manifest),
        collaborator_manifest_sha256=canonical_digest(collaborator_manifest),
        project_owner="4444J99",
        project_marker="organvm-universe:v1",
        change_count=change_count,
        duplicate_project_ids=(),
        unbound_card_ids=(),
        privacy_findings_count=privacy_findings_count,
        github_read_receipt_sha256=DIGEST,
        privacy_receipt_sha256=DIGEST,
    )


def _inputs(**plan_overrides):
    source_registry = _source_registry()
    project_manifest = _project_manifest(source_registry)
    collaborator_manifest = _collaborator_manifest(source_registry, project_manifest)
    plan = _github_plan(
        source_registry,
        project_manifest,
        collaborator_manifest,
        **plan_overrides,
    )
    return source_registry, project_manifest, collaborator_manifest, plan


def _evaluate(
    check: str,
    source_registry: UniverseSourceRegistryV1,
    project_manifest: ProjectUniverseManifestV1,
    collaborator_manifest: CollaboratorUniverseManifestV1,
    plan: GitHubProjectionPlanV1 | None,
    *,
    runtime_sha: str = RUNTIME_SHA,
) -> dict:
    return evaluate_universe_check(
        check=check,
        frozen_wave_sha256=DIGEST,
        installed_runtime_sha=RUNTIME_SHA,
        runtime_status={"receipt": {"sha": runtime_sha}},
        source_registry=source_registry,
        project_manifest=project_manifest,
        collaborator_manifest=collaborator_manifest,
        github_plan=plan,
        observed_at=INSTANT,
    )


def test_complete_bound_universe_passes_all_six_predicates() -> None:
    source_registry, project_manifest, collaborator_manifest, plan = _inputs()

    assert all(
        _evaluate(
            check,
            source_registry,
            project_manifest,
            collaborator_manifest,
            plan,
        )["passed"]
        for check in CHECKS
    )


def test_incomplete_sources_projects_builds_and_collaborators_fail_closed() -> None:
    source_registry = _source_registry()
    incomplete_project = _project_manifest(source_registry, source_complete=False)
    incomplete_collaborator = _collaborator_manifest(
        source_registry,
        incomplete_project,
        source_complete=False,
    )
    plan = _github_plan(source_registry, incomplete_project, incomplete_collaborator)
    assert not _evaluate(
        "source-coverage-complete",
        source_registry,
        incomplete_project,
        incomplete_collaborator,
        plan,
    )["passed"]

    partial_project = _project_manifest(source_registry, project_complete=False)
    partial_collaborator = _collaborator_manifest(source_registry, partial_project)
    partial_plan = _github_plan(source_registry, partial_project, partial_collaborator)
    assert not _evaluate(
        "canonical-project-coverage-complete",
        source_registry,
        partial_project,
        partial_collaborator,
        partial_plan,
    )["passed"]

    failed_build = _project_manifest(source_registry, build_status="failed")
    failed_collaborator = _collaborator_manifest(source_registry, failed_build)
    failed_plan = _github_plan(source_registry, failed_build, failed_collaborator)
    assert not _evaluate(
        "all-canonical-projects-built",
        source_registry,
        failed_build,
        failed_collaborator,
        failed_plan,
    )["passed"]

    project_manifest = _project_manifest(source_registry)
    unknown_collaborator = _collaborator_manifest(
        source_registry,
        project_manifest,
        reconciled=False,
    )
    unknown_plan = _github_plan(source_registry, project_manifest, unknown_collaborator)
    assert not _evaluate(
        "collaborator-universe-reconciled",
        source_registry,
        project_manifest,
        unknown_collaborator,
        unknown_plan,
    )["passed"]


def test_wrong_runtime_stale_plan_privacy_findings_and_changes_fail_closed() -> None:
    source_registry, project_manifest, collaborator_manifest, plan = _inputs()
    assert not _evaluate(
        "source-coverage-complete",
        source_registry,
        project_manifest,
        collaborator_manifest,
        plan,
        runtime_sha="c" * 40,
    )["passed"]

    stale_plan = _github_plan(
        source_registry,
        project_manifest,
        collaborator_manifest,
        observed_at=INSTANT - timedelta(days=2),
    )
    assert not _evaluate(
        "privacy-safe-projection",
        source_registry,
        project_manifest,
        collaborator_manifest,
        stale_plan,
    )["passed"]

    privacy_plan = _github_plan(
        source_registry,
        project_manifest,
        collaborator_manifest,
        privacy_findings_count=1,
    )
    assert not _evaluate(
        "privacy-safe-projection",
        source_registry,
        project_manifest,
        collaborator_manifest,
        privacy_plan,
    )["passed"]

    changed_plan = _github_plan(
        source_registry,
        project_manifest,
        collaborator_manifest,
        change_count=1,
    )
    assert not _evaluate(
        "github-projection-idempotent",
        source_registry,
        project_manifest,
        collaborator_manifest,
        changed_plan,
    )["passed"]


def test_projection_plan_rejects_booleans_and_private_extra_fields() -> None:
    source_registry, project_manifest, collaborator_manifest, plan = _inputs()
    payload = plan.model_dump(mode="json", by_alias=True)
    with pytest.raises(ValueError):
        GitHubProjectionPlanV1.model_validate({**payload, "change_count": True})
    with pytest.raises(ValueError):
        GitHubProjectionPlanV1.model_validate({**payload, "private_name": "must-not-project"})

    assert not _evaluate(
        "privacy-safe-projection",
        source_registry,
        project_manifest,
        collaborator_manifest,
        None,
    )["passed"]


def test_cli_is_read_only_and_returns_one_for_a_non_idempotent_plan(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    source_registry, project_manifest, collaborator_manifest, plan = _inputs(change_count=1)
    inputs = {
        "source-registry.json": source_registry.model_dump(mode="json"),
        "project.json": project_manifest.model_dump(mode="json"),
        "collaborator.json": collaborator_manifest.model_dump(mode="json"),
        "plan.json": plan.model_dump(mode="json", by_alias=True),
        "runtime.json": {"receipt": {"sha": RUNTIME_SHA}},
    }
    for name, payload in inputs.items():
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")

    before = sorted(path.name for path in tmp_path.iterdir())
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "prima-materia-universe-audit.py"),
            "--check",
            "github-projection-idempotent",
            "--frozen-wave-sha",
            DIGEST,
            "--installed-runtime-sha",
            RUNTIME_SHA,
            "--source-registry",
            str(tmp_path / "source-registry.json"),
            "--project-manifest",
            str(tmp_path / "project.json"),
            "--collaborator-manifest",
            str(tmp_path / "collaborator.json"),
            "--github-plan",
            str(tmp_path / "plan.json"),
            "--runtime-status-file",
            str(tmp_path / "runtime.json"),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 1
    assert json.loads(result.stdout)["passed"] is False
    assert sorted(path.name for path in tmp_path.iterdir()) == before
