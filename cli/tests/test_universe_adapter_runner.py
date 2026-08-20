from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from limen.prima_materia import (
    CollaboratorProjectRelationshipV1,
    CollaboratorUniverseEntryV1,
    ProjectUniverseEntryV1,
    UniverseSourceAdapterV1,
    UniverseSourceRegistryV1,
)
from limen.universe_adapter_runner import (
    UniverseCensusFragmentV1,
    UniverseCollaboratorFragmentV1,
    UniverseCollaboratorInstanceFragmentV1,
    UniverseEnumeratorRegistryV1,
    UniverseEnumeratorSpecV1,
    UniverseProjectFragmentV1,
    UniverseProjectInstanceFragmentV1,
    _bounded_command,
    command_digest,
    run_universe_adapters,
)
from limen.universe_freezer import (
    SourceCollaboratorObservationV1,
    SourceProjectObservationV1,
    UniverseSourceInstanceExpectationV1,
    freeze_universe,
)

WAVE = "a" * 64
FROZEN_AT = datetime(2026, 7, 28, 20, tzinfo=UTC)
SOURCE_INSTANCE = "sourceInstanceA01"
PROJECT_ID = "projectIdentifierA1"
COLLABORATOR_ID = "collaboratorIdA01"


def _source_registry() -> UniverseSourceRegistryV1:
    return UniverseSourceRegistryV1(
        registry_id="universeSources001",
        adapters=(
            UniverseSourceAdapterV1(
                adapter_id="fixture-adapter",
                source_kind="fixture_source",
                owner_ref="fixture-owner",
                census_enumerator_ref="fixture-census",
                project_enumerator_ref="fixture-projects",
                collaborator_enumerator_ref="fixture-collaborators",
                completeness_predicate="every fixture row is classified",
                privacy_projection_ref="fixture-privacy",
            ),
        ),
    )


def _fragments() -> dict[str, object]:
    project = ProjectUniverseEntryV1(
        project_id=PROJECT_ID,
        source_lineage_ids=("fixture-project-lineage",),
        repository_ids=("repository-a", "repository-b"),
        child_task_ids=("task-row-001",),
        artifact_refs=("artifact-project-a",),
        collaborator_ids=(COLLABORATOR_ID,),
        lifecycle_stage="live",
        predicate_refs=("build-project-a",),
        receipt_refs=("receipt-project-a",),
        coverage_disposition="complete",
        build_status="passed",
    )
    collaborator = CollaboratorUniverseEntryV1(
        collaborator_id=COLLABORATOR_ID,
        source_lineage_ids=("fixture-collaborator-lineage",),
        relationships=(
            CollaboratorProjectRelationshipV1(
                project_id=PROJECT_ID,
                roles=("advisor",),
            ),
        ),
        coverage_disposition="reconciled",
        disposition_receipt_refs=("collaborator-disposition",),
    )
    return {
        "census": UniverseCensusFragmentV1(
            source_kind="fixture_source",
            observed_at=FROZEN_AT,
            enumeration_complete=True,
            receipt_ref="fixture-census-receipt",
            source_instances=(
                UniverseSourceInstanceExpectationV1(
                    source_instance_id=SOURCE_INSTANCE,
                    source_kind="fixture_source",
                    owner_receipt_ref="fixture-source-owner-receipt",
                ),
            ),
        ),
        "project": UniverseProjectFragmentV1(
            source_kind="fixture_source",
            observed_at=FROZEN_AT,
            enumeration_complete=True,
            receipt_ref="fixture-project-receipt",
            instances=(
                UniverseProjectInstanceFragmentV1(
                    source_instance_id=SOURCE_INSTANCE,
                    required_project_ids=(PROJECT_ID,),
                    projects=(
                        SourceProjectObservationV1(
                            canonical_project_id=PROJECT_ID,
                            project=project,
                        ),
                    ),
                    non_project_row_ids=("ledger-task-classified-row",),
                ),
            ),
        ),
        "collaborator": UniverseCollaboratorFragmentV1(
            source_kind="fixture_source",
            observed_at=FROZEN_AT,
            enumeration_complete=True,
            receipt_ref="fixture-collaborator-receipt",
            instances=(
                UniverseCollaboratorInstanceFragmentV1(
                    source_instance_id=SOURCE_INSTANCE,
                    required_collaborator_ids=(COLLABORATOR_ID,),
                    collaborators=(
                        SourceCollaboratorObservationV1(
                            canonical_collaborator_id=COLLABORATOR_ID,
                            collaborator=collaborator,
                        ),
                    ),
                    reference_only_identity_ids=("referenceIdentity01",),
                ),
            ),
        ),
    }


def _spec(
    *,
    ref: str,
    dimension: str,
    payload: object,
    counter: Path,
    requires_custody: bool = False,
    input_files: tuple[str, ...] = (),
) -> UniverseEnumeratorSpecV1:
    payload_json = json.dumps(payload.model_dump(mode="json"))
    code = (
        "import pathlib,sys\n"
        "sys.stdin.buffer.read()\n"
        f"counter=pathlib.Path({str(counter)!r})\n"
        "value=int(counter.read_text())+1 if counter.exists() else 1\n"
        "counter.write_text(str(value))\n"
        f"print({payload_json!r})\n"
    )
    command = (sys.executable, "-c", code)
    return UniverseEnumeratorSpecV1(
        enumerator_ref=ref,
        dimension=dimension,
        command=command,
        command_sha256=command_digest(command),
        input_files=input_files,
        timeout_seconds=5,
        max_output_bytes=256 * 1024,
        requires_custody_receipt=requires_custody,
    )


def _enumerator_registry(
    tmp_path: Path,
    *,
    reverse: bool = False,
    requires_custody: bool = False,
) -> UniverseEnumeratorRegistryV1:
    fragments = _fragments()
    specs = (
        _spec(
            ref="fixture-census",
            dimension="census",
            payload=fragments["census"],
            counter=tmp_path / "census-count",
            requires_custody=requires_custody,
        ),
        _spec(
            ref="fixture-projects",
            dimension="project",
            payload=fragments["project"],
            counter=tmp_path / "project-count",
            requires_custody=requires_custody,
        ),
        _spec(
            ref="fixture-collaborators",
            dimension="collaborator",
            payload=fragments["collaborator"],
            counter=tmp_path / "collaborator-count",
            requires_custody=requires_custody,
        ),
    )
    return UniverseEnumeratorRegistryV1(
        registry_id="enumeratorRegistry01",
        enumerators=tuple(reversed(specs)) if reverse else specs,
    )


def test_runner_executes_then_reuses_exact_receipts_and_feeds_the_freezer(
    tmp_path: Path,
) -> None:
    source_registry = _source_registry()
    enumerators = _enumerator_registry(tmp_path)
    first = run_universe_adapters(
        source_registry=source_registry,
        enumerator_registry=enumerators,
        frozen_wave_sha256=WAVE,
        frozen_at=FROZEN_AT,
        cache_dir=tmp_path / "cache",
    )
    second = run_universe_adapters(
        source_registry=source_registry,
        enumerator_registry=_enumerator_registry(tmp_path, reverse=True),
        frozen_wave_sha256=WAVE,
        frozen_at=FROZEN_AT,
        cache_dir=tmp_path / "cache",
    )

    assert first.census.enumeration_complete
    assert len(first.observations) == 1
    assert len(first.receipt.executed_enumerator_refs) == 3
    assert second.receipt.executed_enumerator_refs == ()
    assert len(second.receipt.reused_enumerator_refs) == 3
    assert first.receipt.enumerator_registry_sha256 == second.receipt.enumerator_registry_sha256
    assert all(
        (tmp_path / f"{dimension}-count").read_text() == "1" for dimension in ("census", "project", "collaborator")
    )

    frozen = freeze_universe(
        source_registry=source_registry,
        census=second.census,
        observations=second.observations,
    )
    assert frozen.project_manifest.all_canonical_projects_built
    assert frozen.collaborator_manifest.reconciled


def test_missing_enumerator_stays_visible_and_prevents_observation_completion(
    tmp_path: Path,
) -> None:
    source_registry = _source_registry()
    complete_registry = _enumerator_registry(tmp_path)
    missing_registry = complete_registry.model_copy(
        update={
            "enumerators": tuple(item for item in complete_registry.enumerators if item.dimension != "collaborator")
        }
    )
    result = run_universe_adapters(
        source_registry=source_registry,
        enumerator_registry=missing_registry,
        frozen_wave_sha256=WAVE,
        frozen_at=FROZEN_AT,
        cache_dir=tmp_path / "cache",
    )

    assert not result.census.enumeration_complete
    assert result.observations == ()
    assert result.receipt.missing_enumerator_refs == ("fixture-collaborators",)


def test_custody_gated_enumerators_do_not_run_without_a_restore_receipt(
    tmp_path: Path,
) -> None:
    source_registry = _source_registry()
    enumerators = _enumerator_registry(tmp_path, requires_custody=True)
    blocked = run_universe_adapters(
        source_registry=source_registry,
        enumerator_registry=enumerators,
        frozen_wave_sha256=WAVE,
        frozen_at=FROZEN_AT,
        cache_dir=tmp_path / "cache",
    )
    assert not blocked.census.enumeration_complete
    assert len(blocked.receipt.missing_enumerator_refs) == 3
    assert len(blocked.receipt.placeholder_source_instance_ids) == 1
    assert not any((tmp_path / f"{dimension}-count").exists() for dimension in ("census", "project", "collaborator"))

    admitted = run_universe_adapters(
        source_registry=source_registry,
        enumerator_registry=enumerators,
        frozen_wave_sha256=WAVE,
        frozen_at=FROZEN_AT,
        cache_dir=tmp_path / "cache",
        custody_receipt_sha256="b" * 64,
    )
    assert admitted.census.enumeration_complete
    assert len(admitted.observations) == 1


def test_bounded_runner_stops_timeout_and_excess_output() -> None:
    timeout_command = (
        sys.executable,
        "-c",
        "import sys,time;sys.stdin.buffer.read();time.sleep(2)",
    )
    with pytest.raises(TimeoutError):
        _bounded_command(
            timeout_command,
            b"{}",
            timeout_seconds=1,
            max_output_bytes=1024,
        )

    excessive_command = (
        sys.executable,
        "-c",
        "import sys;sys.stdin.buffer.read();sys.stdout.write('x'*2048)",
    )
    with pytest.raises(ValueError, match="output limit"):
        _bounded_command(
            excessive_command,
            b"{}",
            timeout_seconds=2,
            max_output_bytes=1024,
        )


def test_cache_input_binds_tracked_file_bytes(tmp_path: Path) -> None:
    tracked_input = tmp_path / "source.txt"
    tracked_input.write_text("first\n")
    registry = _enumerator_registry(tmp_path)
    registry = registry.model_copy(
        update={
            "enumerators": tuple(
                item.model_copy(update={"input_files": ("source.txt",)}) if item.dimension == "census" else item
                for item in registry.enumerators
            )
        }
    )
    first = run_universe_adapters(
        source_registry=_source_registry(),
        enumerator_registry=registry,
        frozen_wave_sha256=WAVE,
        frozen_at=FROZEN_AT,
        cache_dir=tmp_path / "cache",
        repository_root=tmp_path,
    )
    tracked_input.write_text("second\n")
    second = run_universe_adapters(
        source_registry=_source_registry(),
        enumerator_registry=registry,
        frozen_wave_sha256=WAVE,
        frozen_at=FROZEN_AT,
        cache_dir=tmp_path / "cache",
        repository_root=tmp_path,
    )

    assert len(first.receipt.executed_enumerator_refs) == 3
    assert second.receipt.executed_enumerator_refs == ("fixture-census",)
    assert second.receipt.reused_enumerator_refs == (
        "fixture-collaborators",
        "fixture-projects",
    )
    assert (tmp_path / "census-count").read_text() == "2"


def test_cache_input_binds_optional_file_absence_and_appearance(tmp_path: Path) -> None:
    registry = _enumerator_registry(tmp_path)
    registry = registry.model_copy(
        update={
            "enumerators": tuple(
                item.model_copy(update={"optional_input_files": ("runtime-state.json",)})
                if item.dimension == "census"
                else item
                for item in registry.enumerators
            )
        }
    )
    first = run_universe_adapters(
        source_registry=_source_registry(),
        enumerator_registry=registry,
        frozen_wave_sha256=WAVE,
        frozen_at=FROZEN_AT,
        cache_dir=tmp_path / "cache",
        repository_root=tmp_path,
    )
    second = run_universe_adapters(
        source_registry=_source_registry(),
        enumerator_registry=registry,
        frozen_wave_sha256=WAVE,
        frozen_at=FROZEN_AT,
        cache_dir=tmp_path / "cache",
        repository_root=tmp_path,
    )
    (tmp_path / "runtime-state.json").write_text("{}\n")
    third = run_universe_adapters(
        source_registry=_source_registry(),
        enumerator_registry=registry,
        frozen_wave_sha256=WAVE,
        frozen_at=FROZEN_AT,
        cache_dir=tmp_path / "cache",
        repository_root=tmp_path,
    )

    assert len(first.receipt.executed_enumerator_refs) == 3
    assert second.receipt.executed_enumerator_refs == ()
    assert third.receipt.executed_enumerator_refs == ("fixture-census",)
    assert (tmp_path / "census-count").read_text() == "2"


def test_input_drift_during_enumeration_fails_closed(tmp_path: Path) -> None:
    tracked_input = tmp_path / "source.txt"
    tracked_input.write_text("before\n")
    registry = _enumerator_registry(tmp_path)
    census = next(item for item in registry.enumerators if item.dimension == "census")
    payload = json.dumps(_fragments()["census"].model_dump(mode="json"))
    command = (
        sys.executable,
        "-c",
        (
            "import pathlib,sys\n"
            "sys.stdin.buffer.read()\n"
            "pathlib.Path('source.txt').write_text('after\\n')\n"
            f"print({payload!r})\n"
        ),
    )
    drifting = census.model_copy(
        update={
            "command": command,
            "command_sha256": command_digest(command),
            "input_files": ("source.txt",),
        }
    )
    registry = registry.model_copy(
        update={"enumerators": tuple(drifting if item.dimension == "census" else item for item in registry.enumerators)}
    )

    result = run_universe_adapters(
        source_registry=_source_registry(),
        enumerator_registry=registry,
        frozen_wave_sha256=WAVE,
        frozen_at=FROZEN_AT,
        cache_dir=tmp_path / "cache",
        repository_root=tmp_path,
    )

    assert result.receipt.failed_enumerator_refs == ("fixture-census",)
    assert len(result.receipt.placeholder_source_instance_ids) == 1


def test_enumerator_input_files_reject_path_escape() -> None:
    command = (sys.executable, "-c", "print('{}')")
    with pytest.raises(ValueError, match="repository-relative"):
        UniverseEnumeratorSpecV1(
            enumerator_ref="fixture-census",
            dimension="census",
            command=command,
            command_sha256=command_digest(command),
            input_files=("../private",),
            timeout_seconds=5,
            max_output_bytes=1024,
        )


def test_enumerator_optional_input_files_reject_overlap_and_path_escape() -> None:
    command = (sys.executable, "-c", "print('{}')")
    common = {
        "enumerator_ref": "fixture-census",
        "dimension": "census",
        "command": command,
        "command_sha256": command_digest(command),
        "timeout_seconds": 5,
        "max_output_bytes": 1024,
    }
    with pytest.raises(ValueError, match="repository-relative"):
        UniverseEnumeratorSpecV1(
            **common,
            optional_input_files=("../runtime-state",),
        )
    with pytest.raises(ValueError, match="must not overlap"):
        UniverseEnumeratorSpecV1(
            **common,
            input_files=("runtime-state.json",),
            optional_input_files=("runtime-state.json",),
        )


def test_fragment_with_raw_private_fields_fails_closed_as_adapter_debt(
    tmp_path: Path,
) -> None:
    source_registry = _source_registry()
    registry = _enumerator_registry(tmp_path)
    census = next(item for item in registry.enumerators if item.dimension == "census")
    payload = _fragments()["census"].model_dump(mode="json")
    payload["raw_private_name"] = "must not cross the adapter"
    bad = _spec(
        ref="fixture-census",
        dimension="census",
        payload=type("Payload", (), {"model_dump": lambda self, mode: payload})(),
        counter=tmp_path / "bad-census-count",
    )
    registry = registry.model_copy(
        update={
            "enumerators": tuple(
                bad if item.enumerator_ref == census.enumerator_ref else item for item in registry.enumerators
            )
        }
    )
    result = run_universe_adapters(
        source_registry=source_registry,
        enumerator_registry=registry,
        frozen_wave_sha256=WAVE,
        frozen_at=FROZEN_AT,
        cache_dir=tmp_path / "cache",
    )

    assert result.receipt.failed_enumerator_refs == ("fixture-census",)
    assert len(result.receipt.placeholder_source_instance_ids) == 1


def test_complete_fragment_cannot_hide_unclassified_source_rows() -> None:
    with pytest.raises(ValueError, match="unclassified rows"):
        UniverseProjectFragmentV1(
            source_kind="fixture_source",
            observed_at=FROZEN_AT,
            enumeration_complete=True,
            receipt_ref="fixture-project-receipt",
            instances=(
                UniverseProjectInstanceFragmentV1(
                    source_instance_id=SOURCE_INSTANCE,
                    required_project_ids=(),
                    projects=(),
                    unclassified_row_ids=("opaque-row-debt",),
                ),
            ),
        )


def test_tracked_executable_registry_runs_public_source_families(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[2]
    source_registry = UniverseSourceRegistryV1.model_validate_json(
        (root / "institutio" / "governance" / "prima-materia-universe-sources.json").read_text()
    )
    enumerators = UniverseEnumeratorRegistryV1.model_validate_json(
        (root / "institutio" / "governance" / "prima-materia-universe-enumerators.json").read_text()
    )
    funnel_manifest = json.loads((root / "institutio" / "governance" / "prima-materia-funnel-sources.json").read_text())
    funnel_paths = tuple(sorted(item["path"] for item in funnel_manifest["sources"]))
    github_snapshot = json.loads((root / "docs" / "github-universe-snapshot.json").read_text())
    frozen_at = datetime.fromisoformat(github_snapshot["observed_at"]) + timedelta(seconds=1)
    funnel_specs = tuple(
        item
        for item in enumerators.enumerators
        if item.enumerator_ref
        in {
            "funnel-records-census-v1",
            "funnel-record-projects-v1",
            "funnel-record-collaborators-v1",
        }
    )
    assert len(funnel_specs) == 3
    assert all(item.optional_input_files == funnel_paths for item in funnel_specs)
    result = run_universe_adapters(
        source_registry=source_registry,
        enumerator_registry=enumerators,
        frozen_wave_sha256=WAVE,
        frozen_at=frozen_at,
        cache_dir=tmp_path / "cache",
        repository_root=root,
    )

    assert not result.census.enumeration_complete
    assert result.receipt.executed_enumerator_refs == (
        "constellation-census-v1",
        "constellation-collaborators-v1",
        "constellation-projects-v1",
        "curated-registry-census-v1",
        "curated-registry-collaborators-v1",
        "curated-registry-projects-v1",
        "engagement-collaborators-v1",
        "engagement-projects-v1",
        "engagements-census-v1",
        "funnel-record-collaborators-v1",
        "funnel-record-projects-v1",
        "funnel-records-census-v1",
        "github-estate-census-v1",
        "github-estate-collaborators-v1",
        "github-estate-projects-v1",
    )
    assert len(result.receipt.missing_enumerator_refs) == 18
    assert result.receipt.failed_enumerator_refs == ()
    assert len(result.receipt.placeholder_source_instance_ids) == 6
    assert len(result.observations) == 9
    observations_by_kind: dict[str, list] = {}
    for observation in result.observations:
        observations_by_kind.setdefault(observation.source_kind, []).append(observation)
    assert set(observations_by_kind) == {
        "constellation",
        "curated_registry",
        "engagements",
        "funnel_records",
        "github_estate",
    }

    curated = observations_by_kind["curated_registry"][0]
    assert curated.enumeration_complete
    assert curated.required_project_ids == ()
    assert curated.projects == ()
    assert curated.required_collaborator_ids == ()
    assert curated.collaborators == ()
    assert len(curated.non_project_row_ids) == 26

    constellation = observations_by_kind["constellation"][0]
    assert len(constellation.required_project_ids) == 10
    assert len(constellation.projects) == 10
    assert len(constellation.required_collaborator_ids) == 11
    assert len(constellation.collaborators) == 11

    engagements = observations_by_kind["engagements"][0]
    assert engagements.enumeration_complete
    assert engagements.required_project_ids == ()
    assert engagements.projects == ()
    assert engagements.required_collaborator_ids == ()
    assert engagements.collaborators == ()
    assert len(engagements.non_project_row_ids) == 1
    assert engagements.unclassified_row_ids == ()

    funnel_records = observations_by_kind["funnel_records"]
    assert len(funnel_records) == 3
    assert all(not item.enumeration_complete for item in funnel_records)
    assert all(not item.required_project_ids for item in funnel_records)
    assert all(not item.projects for item in funnel_records)
    assert all(not item.required_collaborator_ids for item in funnel_records)
    assert all(not item.collaborators for item in funnel_records)
    assert sum(len(item.unclassified_row_ids) for item in funnel_records) >= 3

    github_estate = observations_by_kind["github_estate"]
    assert len(github_estate) == 3
    assert all(not item.enumeration_complete for item in github_estate)
    assert all(not item.required_project_ids for item in github_estate)
    assert all(not item.projects for item in github_estate)
    assert all(not item.required_collaborator_ids for item in github_estate)
    assert all(not item.collaborators for item in github_estate)
    assert sum(len(item.unclassified_row_ids) for item in github_estate) == len(
        github_snapshot["repository_ids"]
    ) + len(github_snapshot["access_rows"]) + len(github_snapshot["project_row_ids"]) + len(
        github_snapshot["repository_debt_ids"]
    ) + len(github_snapshot["collaborator_debt_ids"]) + len(github_snapshot["project_debt_ids"])

    frozen = freeze_universe(
        source_registry=source_registry,
        census=result.census,
        observations=result.observations,
    )
    assert len(frozen.project_manifest.projects) == 10
    assert len(frozen.collaborator_manifest.collaborators) == 11
    assert not frozen.project_manifest.source_coverage_complete
    assert not frozen.project_manifest.all_canonical_projects_built
    assert not frozen.collaborator_manifest.reconciled
