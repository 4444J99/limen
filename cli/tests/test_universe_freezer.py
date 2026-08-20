from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from limen.prima_materia import (
    CollaboratorProjectRelationshipV1,
    CollaboratorUniverseEntryV1,
    ProjectUniverseEntryV1,
    UniverseSourceAdapterV1,
    UniverseSourceRegistryV1,
)
from limen.universe_freezer import (
    SourceCollaboratorObservationV1,
    SourceProjectObservationV1,
    UniverseSourceCensusV1,
    UniverseSourceInstanceExpectationV1,
    UniverseSourceObservationV1,
    freeze_universe,
)

WAVE = "a" * 64
FROZEN_AT = datetime(2026, 7, 28, 20, tzinfo=UTC)
PROJECT_A = "projectIdentifierA1"
PROJECT_B = "projectIdentifierB2"
PROJECT_ALIAS = "projectLegacyAlias1"
COLLABORATOR = "collaboratorIdA01"
COLLABORATOR_ALIAS = "collaboratorAlias01"
REFERENCE_ONLY = "referenceIdentity01"
SOURCE_A = "sourceInstanceA01"
SOURCE_B = "sourceInstanceB02"


def _registry(reverse: bool = False) -> UniverseSourceRegistryV1:
    adapters = (
        UniverseSourceAdapterV1(
            adapter_id="adapter-a",
            source_kind="source_a",
            owner_ref="owner-a",
            census_enumerator_ref="census-a",
            project_enumerator_ref="projects-a",
            collaborator_enumerator_ref="collaborators-a",
            completeness_predicate="all source A rows are classified",
            privacy_projection_ref="privacy-a",
        ),
        UniverseSourceAdapterV1(
            adapter_id="adapter-b",
            source_kind="source_b",
            owner_ref="owner-b",
            census_enumerator_ref="census-b",
            project_enumerator_ref="projects-b",
            collaborator_enumerator_ref="collaborators-b",
            completeness_predicate="all source B rows are classified",
            privacy_projection_ref="privacy-b",
        ),
    )
    return UniverseSourceRegistryV1(
        registry_id="universeSources001",
        adapters=tuple(reversed(adapters)) if reverse else adapters,
    )


def _census(registry: UniverseSourceRegistryV1, reverse: bool = False) -> UniverseSourceCensusV1:
    instances = (
        UniverseSourceInstanceExpectationV1(
            source_instance_id=SOURCE_A,
            source_kind="source_a",
            owner_receipt_ref="source-a-census-receipt",
        ),
        UniverseSourceInstanceExpectationV1(
            source_instance_id=SOURCE_B,
            source_kind="source_b",
            owner_receipt_ref="source-b-census-receipt",
        ),
    )
    return UniverseSourceCensusV1(
        census_id="universeCensus001",
        frozen_at=FROZEN_AT,
        frozen_wave_sha256=WAVE,
        source_registry_sha256=registry.canonical_digest,
        enumeration_complete=True,
        census_receipt_ref="universe-census-receipt",
        source_instances=tuple(reversed(instances)) if reverse else instances,
    )


def _project(
    project_id: str,
    *,
    lineage: str,
    repositories: tuple[str, ...] = (),
    tasks: tuple[str, ...] = (),
    collaborators: tuple[str, ...] = (),
) -> ProjectUniverseEntryV1:
    return ProjectUniverseEntryV1(
        project_id=project_id,
        source_lineage_ids=(lineage,),
        repository_ids=repositories,
        child_task_ids=tasks,
        artifact_refs=(f"artifact-{lineage}",),
        collaborator_ids=collaborators,
        lifecycle_stage="live",
        predicate_refs=(f"predicate-{lineage}",),
        receipt_refs=(f"receipt-{lineage}",),
        coverage_disposition="complete",
        build_status="passed",
    )


def _collaborator(*, lineage: str, project_id: str) -> CollaboratorUniverseEntryV1:
    return CollaboratorUniverseEntryV1(
        collaborator_id=COLLABORATOR,
        source_lineage_ids=(lineage,),
        relationships=(
            CollaboratorProjectRelationshipV1(
                project_id=project_id,
                roles=("advisor",),
            ),
        ),
        coverage_disposition="reconciled",
        disposition_receipt_refs=(f"disposition-{lineage}",),
    )


def _observations(registry: UniverseSourceRegistryV1) -> tuple[UniverseSourceObservationV1, ...]:
    common = {
        "frozen_wave_sha256": WAVE,
        "source_registry_sha256": registry.canonical_digest,
        "observed_at": FROZEN_AT,
        "enumeration_complete": True,
    }
    source_a = UniverseSourceObservationV1(
        **common,
        source_instance_id=SOURCE_A,
        source_kind="source_a",
        enumeration_receipt_ref="source-a-enumeration-receipt",
        required_project_ids=(PROJECT_ALIAS,),
        projects=(
            SourceProjectObservationV1(
                canonical_project_id=PROJECT_A,
                alias_ids=(PROJECT_ALIAS,),
                project=_project(
                    PROJECT_A,
                    lineage="lineage-project-a-source-a",
                    repositories=("repository-a",),
                    tasks=("task-row-001",),
                    collaborators=(COLLABORATOR_ALIAS,),
                ),
            ),
        ),
        required_collaborator_ids=(COLLABORATOR_ALIAS,),
        collaborators=(
            SourceCollaboratorObservationV1(
                canonical_collaborator_id=COLLABORATOR,
                alias_ids=(COLLABORATOR_ALIAS,),
                collaborator=_collaborator(
                    lineage="lineage-collaborator-source-a",
                    project_id=PROJECT_ALIAS,
                ),
            ),
        ),
        reference_only_identity_ids=(REFERENCE_ONLY,),
        non_project_row_ids=("ledger-task-row-001",),
    )
    source_b = UniverseSourceObservationV1(
        **common,
        source_instance_id=SOURCE_B,
        source_kind="source_b",
        enumeration_receipt_ref="source-b-enumeration-receipt",
        required_project_ids=(PROJECT_A, PROJECT_B),
        projects=(
            SourceProjectObservationV1(
                canonical_project_id=PROJECT_B,
                project=_project(
                    PROJECT_B,
                    lineage="lineage-project-b-source-b",
                ),
            ),
            SourceProjectObservationV1(
                canonical_project_id=PROJECT_A,
                alias_ids=(PROJECT_ALIAS,),
                project=_project(
                    PROJECT_A,
                    lineage="lineage-project-a-source-b",
                    repositories=("repository-b",),
                    tasks=("task-row-002",),
                    collaborators=(COLLABORATOR,),
                ),
            ),
        ),
        required_collaborator_ids=(COLLABORATOR,),
        collaborators=(
            SourceCollaboratorObservationV1(
                canonical_collaborator_id=COLLABORATOR,
                alias_ids=(COLLABORATOR_ALIAS,),
                collaborator=_collaborator(
                    lineage="lineage-collaborator-source-b",
                    project_id=PROJECT_A,
                ),
            ),
        ),
        reference_only_identity_ids=(REFERENCE_ONLY,),
        non_project_row_ids=("ledger-repository-row-001",),
    )
    return source_a, source_b


def test_freeze_is_order_independent_and_preserves_aliases_and_project_shapes() -> None:
    registry = _registry()
    pair = freeze_universe(
        source_registry=registry,
        census=_census(registry),
        observations=_observations(registry),
    )
    reversed_registry = _registry(reverse=True)
    reordered = freeze_universe(
        source_registry=reversed_registry,
        census=_census(reversed_registry, reverse=True),
        observations=tuple(reversed(_observations(reversed_registry))),
    )

    assert pair == reordered
    assert pair.project_manifest.source_coverage_complete
    assert pair.project_manifest.all_canonical_projects_built
    assert pair.collaborator_manifest.reconciled
    project_a, project_b = pair.project_manifest.projects
    assert project_a.alias_ids == (PROJECT_ALIAS,)
    assert project_a.repository_ids == ("repository-a", "repository-b")
    assert project_a.child_task_ids == ("task-row-001", "task-row-002")
    assert project_a.collaborator_ids == (COLLABORATOR,)
    assert project_b.repository_ids == ()
    assert pair.collaborator_manifest.collaborators[0].alias_ids == (COLLABORATOR_ALIAS,)


def test_missing_and_unexpected_sources_remain_visible_coverage_debt() -> None:
    registry = _registry()
    source_a, source_b = _observations(registry)
    missing = freeze_universe(
        source_registry=registry,
        census=_census(registry),
        observations=(source_a,),
    )
    assert missing.project_manifest.missing_source_instance_ids == (SOURCE_B,)
    assert not missing.project_manifest.source_coverage_complete

    unexpected_observation = source_b.model_copy(update={"source_instance_id": "sourceInstanceC03"})
    unexpected = freeze_universe(
        source_registry=registry,
        census=_census(registry),
        observations=(source_a, source_b, unexpected_observation),
    )
    assert unexpected.project_manifest.unexpected_source_instance_ids == ("sourceInstanceC03",)
    assert not unexpected.collaborator_manifest.source_coverage_complete

    wrong_kind = source_a.model_copy(update={"source_kind": "source_b"})
    mismatched = freeze_universe(
        source_registry=registry,
        census=_census(registry),
        observations=(wrong_kind, source_b),
    )
    assert not mismatched.project_manifest.source_coverage_complete


def test_missing_projects_and_collaborators_are_not_manufactured_complete() -> None:
    registry = _registry()
    source_a, source_b = _observations(registry)
    source_b = source_b.model_copy(
        update={
            "required_project_ids": (
                *source_b.required_project_ids,
                "projectIdentifierC3",
            ),
            "required_collaborator_ids": (
                *source_b.required_collaborator_ids,
                "collaboratorIdB02",
            ),
        }
    )
    pair = freeze_universe(
        source_registry=registry,
        census=_census(registry),
        observations=(source_a, source_b),
    )

    assert pair.project_manifest.missing_project_ids == ("projectIdentifierC3",)
    assert pair.collaborator_manifest.missing_collaborator_ids == ("collaboratorIdB02",)
    assert not pair.project_manifest.canonical_project_coverage_complete
    assert not pair.collaborator_manifest.collaborator_coverage_complete


def test_alias_conflicts_and_task_project_conflation_fail_closed() -> None:
    registry = _registry()
    source_a, source_b = _observations(registry)
    conflicting = SourceProjectObservationV1(
        canonical_project_id=PROJECT_B,
        alias_ids=(PROJECT_ALIAS,),
        project=_project(
            PROJECT_B,
            lineage="conflicting-project-alias",
        ),
    )
    source_b_conflict = source_b.model_copy(update={"projects": (*source_b.projects, conflicting)})
    with pytest.raises(ValueError, match="alias maps to multiple"):
        freeze_universe(
            source_registry=registry,
            census=_census(registry),
            observations=(source_a, source_b_conflict),
        )

    conflated_project = source_b.projects[0].model_copy(
        update={
            "project": _project(
                PROJECT_B,
                lineage="lineage-project-b-source-b",
                tasks=(PROJECT_A,),
            )
        }
    )
    source_b_conflated = source_b.model_copy(update={"projects": (conflated_project, source_b.projects[1])})
    with pytest.raises(ValueError, match="project identities and child task identities"):
        freeze_universe(
            source_registry=registry,
            census=_census(registry),
            observations=(source_a, source_b_conflated),
        )

    alias_as_task = source_b.projects[0].model_copy(
        update={
            "project": _project(
                PROJECT_B,
                lineage="lineage-project-b-source-b",
                tasks=(PROJECT_ALIAS,),
            )
        }
    )
    with pytest.raises(ValueError, match="project identities and child task identities"):
        freeze_universe(
            source_registry=registry,
            census=_census(registry),
            observations=(
                source_a,
                source_b.model_copy(update={"projects": (alias_as_task, source_b.projects[1])}),
            ),
        )


def test_reference_only_identities_cannot_enter_collaborator_access_universe() -> None:
    registry = _registry()
    source_a, source_b = _observations(registry)
    project_record = source_a.projects[0]
    project_with_reference = project_record.model_copy(
        update={
            "project": project_record.project.model_copy(
                update={
                    "collaborator_ids": (
                        *project_record.project.collaborator_ids,
                        REFERENCE_ONLY,
                    )
                }
            )
        }
    )
    with pytest.raises(ValueError, match="cannot become project collaborators"):
        freeze_universe(
            source_registry=registry,
            census=_census(registry),
            observations=(
                source_a.model_copy(update={"projects": (project_with_reference,)}),
                source_b,
            ),
        )


def test_cli_writes_a_pair_then_check_is_read_only(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    registry = _registry()
    census = _census(registry)
    observations = _observations(registry)
    inputs = {
        "registry.json": registry,
        "census.json": census,
        "source-a.json": observations[0],
        "source-b.json": observations[1],
    }
    for name, model in inputs.items():
        (tmp_path / name).write_text(
            json.dumps(model.model_dump(mode="json")),
            encoding="utf-8",
        )
    project_output = tmp_path / "project.json"
    collaborator_output = tmp_path / "collaborator.json"
    command = [
        sys.executable,
        str(root / "scripts" / "prima-materia-universe-freeze.py"),
        "--source-registry",
        str(tmp_path / "registry.json"),
        "--census",
        str(tmp_path / "census.json"),
        "--observation",
        str(tmp_path / "source-b.json"),
        "--observation",
        str(tmp_path / "source-a.json"),
        "--project-output",
        str(project_output),
        "--collaborator-output",
        str(collaborator_output),
    ]
    written = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert written.returncode == 0
    assert json.loads(written.stdout)["changed"] is True
    before = {output.name: output.read_bytes() for output in (project_output, collaborator_output)}

    checked = subprocess.run(
        [*command, "--check"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert checked.returncode == 0
    assert json.loads(checked.stdout)["changed"] is False
    assert before == {output.name: output.read_bytes() for output in (project_output, collaborator_output)}
