"""Deterministically freeze source-owned project and collaborator observations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypeVar, cast

import rfc8785
from pydantic import Field, field_validator, model_validator

from limen.prima_materia import (
    CollaboratorProjectRelationshipV1,
    CollaboratorRepositoryAccessV1,
    CollaboratorUniverseEntryV1,
    CollaboratorUniverseManifestV1,
    PrimaMateriaModel,
    ProjectUniverseEntryV1,
    ProjectUniverseManifestV1,
    UniverseSourceRegistryV1,
)

FREEZE_SCHEMA: Literal["limen.prima_materia_universe_freeze.v1"] = "limen.prima_materia_universe_freeze.v1"
_T = TypeVar("_T")
_ModelT = TypeVar("_ModelT", bound=PrimaMateriaModel)
CollaboratorRole = Literal[
    "reference",
    "research",
    "audience",
    "prospect",
    "client",
    "advisor",
    "contributor",
    "co_builder",
]
ProjectCoverageDisposition = Literal["complete", "partial", "unknown", "blocked", "superseded"]
ProjectBuildStatus = Literal["not_started", "passed", "failed", "blocked", "unknown"]
CollaboratorCoverageDisposition = Literal["reconciled", "pending", "declined", "identity_unresolved", "unknown"]


def _validate_digest(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("digest must be lowercase SHA-256")
    return value


def _validate_opaque(value: str) -> str:
    if not 16 <= len(value) <= 128 or any(
        character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for character in value
    ):
        raise ValueError("identity must be a bounded base64url-style identifier")
    return value


def _validate_key(value: str) -> str:
    if not 1 <= len(value) <= 256 or "\x00" in value or value.strip() != value:
        raise ValueError("reference must be a bounded nonblank string")
    return value


def _validate_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include an explicit UTC offset")
    return value.astimezone(UTC)


def _unique(values: tuple[str, ...], label: str, validator=_validate_opaque) -> tuple[str, ...]:
    normalized = tuple(validator(value) for value in values)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} must contain unique identities")
    return normalized


def _sorted_union(groups: Any) -> tuple[str, ...]:
    return tuple(sorted({value for group in groups for value in group}))


def _canonical_digest(value: PrimaMateriaModel) -> str:
    return hashlib.sha256(rfc8785.dumps(value.model_dump(mode="json"))).hexdigest()


class UniverseSourceInstanceExpectationV1(PrimaMateriaModel):
    """One source instance independently declared by the frozen source census."""

    schema_version: Literal["limen.universe_source_instance_expectation.v1"] = (
        "limen.universe_source_instance_expectation.v1"
    )
    source_instance_id: str
    source_kind: str
    owner_receipt_ref: str

    _instance = field_validator("source_instance_id")(_validate_opaque)
    _keys = field_validator("source_kind", "owner_receipt_ref")(_validate_key)


class UniverseSourceCensusV1(PrimaMateriaModel):
    """Source-owned denominator kept separate from the observations it judges."""

    schema_version: Literal["limen.universe_source_census.v1"] = "limen.universe_source_census.v1"
    census_id: str
    frozen_at: datetime
    frozen_wave_sha256: str
    source_registry_sha256: str
    enumeration_complete: bool
    census_receipt_ref: str
    source_instances: tuple[UniverseSourceInstanceExpectationV1, ...] = Field(
        min_length=1,
        max_length=100_000,
    )

    _census = field_validator("census_id")(_validate_opaque)
    _frozen = field_validator("frozen_at")(_validate_aware)
    _digests = field_validator("frozen_wave_sha256", "source_registry_sha256")(_validate_digest)
    _receipt = field_validator("census_receipt_ref")(_validate_key)

    @model_validator(mode="after")
    def instances_are_distinct(self) -> UniverseSourceCensusV1:
        instance_ids = tuple(instance.source_instance_id for instance in self.source_instances)
        if len(instance_ids) != len(set(instance_ids)):
            raise ValueError("source census instance identities must be unique")
        return self


class SourceProjectObservationV1(PrimaMateriaModel):
    canonical_project_id: str
    alias_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=4096)
    project: ProjectUniverseEntryV1

    _canonical = field_validator("canonical_project_id")(_validate_opaque)

    @model_validator(mode="after")
    def identity_matches_payload(self) -> SourceProjectObservationV1:
        _unique(self.alias_ids, "project aliases", _validate_key)
        if self.project.project_id != self.canonical_project_id:
            raise ValueError("project observation identity must match its project payload")
        if self.canonical_project_id in self.alias_ids:
            raise ValueError("project aliases must not repeat the canonical identity")
        if self.project.alias_ids and self.project.alias_ids != tuple(sorted(self.alias_ids)):
            raise ValueError("project payload aliases must match the observation aliases")
        return self


class SourceCollaboratorObservationV1(PrimaMateriaModel):
    canonical_collaborator_id: str
    alias_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=4096)
    collaborator: CollaboratorUniverseEntryV1

    _canonical = field_validator("canonical_collaborator_id")(_validate_opaque)

    @model_validator(mode="after")
    def identity_matches_payload(self) -> SourceCollaboratorObservationV1:
        _unique(self.alias_ids, "collaborator aliases", _validate_key)
        if self.collaborator.collaborator_id != self.canonical_collaborator_id:
            raise ValueError("collaborator observation identity must match its payload")
        if self.canonical_collaborator_id in self.alias_ids:
            raise ValueError("collaborator aliases must not repeat the canonical identity")
        if self.collaborator.alias_ids and self.collaborator.alias_ids != tuple(sorted(self.alias_ids)):
            raise ValueError("collaborator payload aliases must match the observation aliases")
        return self


class UniverseSourceObservationV1(PrimaMateriaModel):
    """One privacy-safe, source-owned observation packet."""

    schema_version: Literal["limen.universe_source_observation.v1"] = "limen.universe_source_observation.v1"
    source_instance_id: str
    source_kind: str
    frozen_wave_sha256: str
    source_registry_sha256: str
    observed_at: datetime
    enumeration_complete: bool
    enumeration_receipt_ref: str
    required_project_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=100_000)
    projects: tuple[SourceProjectObservationV1, ...] = Field(default_factory=tuple, max_length=100_000)
    required_collaborator_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=100_000)
    collaborators: tuple[SourceCollaboratorObservationV1, ...] = Field(
        default_factory=tuple,
        max_length=100_000,
    )
    reference_only_identity_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=100_000)
    non_project_row_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=1_000_000)
    unclassified_row_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=1_000_000)

    _instance = field_validator("source_instance_id")(_validate_opaque)
    _kind = field_validator("source_kind")(_validate_key)
    _digests = field_validator("frozen_wave_sha256", "source_registry_sha256")(_validate_digest)
    _observed = field_validator("observed_at")(_validate_aware)
    _receipt = field_validator("enumeration_receipt_ref")(_validate_key)

    @model_validator(mode="after")
    def packet_denominators_are_distinct(self) -> UniverseSourceObservationV1:
        _unique(self.required_project_ids, "required projects")
        _unique(self.required_collaborator_ids, "required collaborators")
        _unique(self.reference_only_identity_ids, "reference-only identities")
        _unique(self.non_project_row_ids, "non-project rows", _validate_key)
        _unique(self.unclassified_row_ids, "unclassified rows", _validate_key)
        if set(self.non_project_row_ids) & set(self.unclassified_row_ids):
            raise ValueError("classified and unclassified row identities must not overlap")
        if self.enumeration_complete and self.unclassified_row_ids:
            raise ValueError("complete source observation cannot retain unclassified rows")
        project_ids = tuple(record.canonical_project_id for record in self.projects)
        collaborator_ids = tuple(record.canonical_collaborator_id for record in self.collaborators)
        if len(project_ids) != len(set(project_ids)):
            raise ValueError("one source packet cannot repeat a canonical project")
        if len(collaborator_ids) != len(set(collaborator_ids)):
            raise ValueError("one source packet cannot repeat a canonical collaborator")
        collaborator_names = {
            identity
            for record in self.collaborators
            for identity in (record.canonical_collaborator_id, *record.alias_ids)
        }
        overlap = collaborator_names & set(self.reference_only_identity_ids)
        if overlap:
            raise ValueError("reference-only identities must stay outside collaborator observations")
        return self


class FrozenUniversePairV1(PrimaMateriaModel):
    project_manifest: ProjectUniverseManifestV1
    collaborator_manifest: CollaboratorUniverseManifestV1


def _identity_map(records: Any, *, identity_attribute: str, alias_attribute: str, label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for record in records:
        canonical = getattr(record, identity_attribute)
        for identity in (canonical, *getattr(record, alias_attribute)):
            existing = result.get(identity)
            if existing is not None and existing != canonical:
                raise ValueError(f"{label} alias maps to multiple canonical identities")
            result[identity] = canonical
    return result


def _canonicalize(identity: str, aliases: dict[str, str]) -> str:
    return aliases.get(identity, identity)


def _single(values: set[_T], label: str) -> _T:
    if len(values) != 1:
        raise ValueError(f"conflicting {label} observations require a source-owned disposition")
    return next(iter(values))


def _merge_project_disposition(values: set[str]) -> ProjectCoverageDisposition:
    order = ("unknown", "blocked", "partial", "superseded", "complete")
    return cast(ProjectCoverageDisposition, min(values, key=order.index))


def _merge_build_status(values: set[str]) -> ProjectBuildStatus:
    if values == {"passed"}:
        return "passed"
    for status in ("failed", "blocked", "not_started", "unknown"):
        if status in values:
            return cast(ProjectBuildStatus, status)
    return "unknown"


def _merge_collaborator_disposition(values: set[str]) -> CollaboratorCoverageDisposition:
    order = ("unknown", "identity_unresolved", "pending", "declined", "reconciled")
    return cast(CollaboratorCoverageDisposition, min(values, key=order.index))


def _merge_repository_accesses(
    accesses: list[CollaboratorRepositoryAccessV1],
) -> tuple[CollaboratorRepositoryAccessV1, ...]:
    grouped: dict[str, list[CollaboratorRepositoryAccessV1]] = defaultdict(list)
    for access in accesses:
        grouped[access.repository_id].append(access)
    merged = []
    for repository_id, observations in sorted(grouped.items()):
        merged.append(
            CollaboratorRepositoryAccessV1(
                repository_id=repository_id,
                access_level=_single({item.access_level for item in observations}, "repository access level"),
                status=_single({item.status for item in observations}, "repository access status"),
                authority_ref=_single({item.authority_ref for item in observations}, "repository access authority"),
                receipt_refs=_sorted_union(item.receipt_refs for item in observations),
            )
        )
    return tuple(merged)


def _merge_relationships(
    relationships: list[CollaboratorProjectRelationshipV1],
    project_aliases: dict[str, str],
) -> tuple[CollaboratorProjectRelationshipV1, ...]:
    grouped: dict[str, list[CollaboratorProjectRelationshipV1]] = defaultdict(list)
    for relationship in relationships:
        grouped[_canonicalize(relationship.project_id, project_aliases)].append(relationship)
    merged = []
    for project_id, observations in sorted(grouped.items()):
        merged.append(
            CollaboratorProjectRelationshipV1(
                project_id=project_id,
                roles=cast(tuple[CollaboratorRole, ...], _sorted_union(item.roles for item in observations)),
                project_access_level=_single(
                    {item.project_access_level for item in observations},
                    "Project access level",
                ),
                project_access_status=_single(
                    {item.project_access_status for item in observations},
                    "Project access status",
                ),
                project_authority_ref=_single(
                    {item.project_authority_ref for item in observations},
                    "Project access authority",
                ),
                project_access_receipt_refs=_sorted_union(item.project_access_receipt_refs for item in observations),
                repository_accesses=_merge_repository_accesses(
                    [access for relationship in observations for access in relationship.repository_accesses]
                ),
            )
        )
    return tuple(merged)


def freeze_universe(
    *,
    source_registry: UniverseSourceRegistryV1,
    census: UniverseSourceCensusV1,
    observations: tuple[UniverseSourceObservationV1, ...],
) -> FrozenUniversePairV1:
    """Return canonically ordered manifests without hiding source or identity debt."""

    source_registry_sha256 = source_registry.canonical_digest
    if census.source_registry_sha256 != source_registry_sha256:
        raise ValueError("source census does not bind the loaded source registry")
    observation_ids = tuple(observation.source_instance_id for observation in observations)
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError("source observation instance identities must be unique")
    for observation in observations:
        if observation.frozen_wave_sha256 != census.frozen_wave_sha256:
            raise ValueError("source observation does not bind the frozen wave")
        if observation.source_registry_sha256 != source_registry_sha256:
            raise ValueError("source observation does not bind the source registry")
        if observation.observed_at > census.frozen_at:
            raise ValueError("source observation is newer than the frozen census")

    project_records: list[SourceProjectObservationV1] = [record for observation in observations for record in observation.projects]
    collaborator_records: list[SourceCollaboratorObservationV1] = [record for observation in observations for record in observation.collaborators]
    project_aliases = _identity_map(
        project_records,
        identity_attribute="canonical_project_id",
        alias_attribute="alias_ids",
        label="project",
    )
    collaborator_aliases = _identity_map(
        collaborator_records,
        identity_attribute="canonical_collaborator_id",
        alias_attribute="alias_ids",
        label="collaborator",
    )
    reference_only = {identity for observation in observations for identity in observation.reference_only_identity_ids}
    if reference_only & set(collaborator_aliases):
        raise ValueError("reference-only identities must stay outside the collaborator universe")

    grouped_projects: dict[str, list[SourceProjectObservationV1]] = defaultdict(list)
    for record in project_records:
        grouped_projects[record.canonical_project_id].append(record)
    projects: list[ProjectUniverseEntryV1] = []
    for project_id, records in sorted(grouped_projects.items()):
        entries = [record.project for record in records]
        project_collaborators = tuple(
            sorted(
                {
                    _canonicalize(identity, collaborator_aliases)
                    for entry in entries
                    for identity in entry.collaborator_ids
                }
            )
        )
        if reference_only & set(project_collaborators):
            raise ValueError("reference-only identities cannot become project collaborators")
        projects.append(
            ProjectUniverseEntryV1(
                project_id=project_id,
                alias_ids=tuple(sorted({alias for record in records for alias in record.alias_ids})),
                source_lineage_ids=_sorted_union(entry.source_lineage_ids for entry in entries),
                repository_ids=_sorted_union(entry.repository_ids for entry in entries),
                child_task_ids=_sorted_union(entry.child_task_ids for entry in entries),
                artifact_refs=_sorted_union(entry.artifact_refs for entry in entries),
                collaborator_ids=project_collaborators,
                lifecycle_stage=_single({entry.lifecycle_stage for entry in entries}, "project lifecycle"),
                predicate_refs=_sorted_union(entry.predicate_refs for entry in entries),
                receipt_refs=_sorted_union(entry.receipt_refs for entry in entries),
                coverage_disposition=_merge_project_disposition({entry.coverage_disposition for entry in entries}),
                build_status=_merge_build_status({entry.build_status for entry in entries}),
            )
        )
    task_ids = {task_id for project in projects for task_id in project.child_task_ids}
    if task_ids & set(project_aliases):
        raise ValueError("project identities and child task identities must remain distinct, including aliases")
    non_project_rows = {row_id for observation in observations for row_id in observation.non_project_row_ids}
    classified_identities = set(project_aliases) | set(collaborator_aliases) | task_ids
    if non_project_rows & classified_identities:
        raise ValueError("non-project rows cannot reuse project, task, or collaborator identities")

    expected_source_ids = tuple(sorted(instance.source_instance_id for instance in census.source_instances))
    observed_source_ids = tuple(sorted(observation_ids))
    expected_instances = {instance.source_instance_id: instance.source_kind for instance in census.source_instances}
    expected_source_kinds = {instance.source_kind for instance in census.source_instances}
    observed_source_kinds = {observation.source_kind for observation in observations}
    registered_source_kinds = set(source_registry.source_kinds)
    source_enumeration_complete = (
        census.enumeration_complete
        and expected_source_kinds == registered_source_kinds
        and observed_source_kinds <= registered_source_kinds
        and all(
            expected_instances.get(observation.source_instance_id) == observation.source_kind
            for observation in observations
            if observation.source_instance_id in expected_instances
        )
        and all(observation.enumeration_complete for observation in observations)
    )
    required_project_ids = tuple(
        sorted(
            {
                _canonicalize(identity, project_aliases)
                for observation in observations
                for identity in observation.required_project_ids
            }
        )
    )
    observed_project_ids = tuple(project.project_id for project in projects)
    project_manifest = ProjectUniverseManifestV1(
        manifest_id=f"projectManifest{hashlib.sha256(census.census_id.encode()).hexdigest()[:24]}",
        frozen_at=census.frozen_at,
        frozen_wave_digest=census.frozen_wave_sha256,
        source_registry_digest=source_registry_sha256,
        enumeration_complete=source_enumeration_complete,
        required_source_instance_ids=expected_source_ids,
        observed_source_instance_ids=observed_source_ids,
        missing_source_instance_ids=tuple(sorted(set(expected_source_ids) - set(observed_source_ids))),
        unexpected_source_instance_ids=tuple(sorted(set(observed_source_ids) - set(expected_source_ids))),
        required_project_ids=required_project_ids,
        missing_project_ids=tuple(sorted(set(required_project_ids) - set(observed_project_ids))),
        unexpected_project_ids=tuple(sorted(set(observed_project_ids) - set(required_project_ids))),
        projects=tuple(projects),
    )

    grouped_collaborators: dict[str, list[SourceCollaboratorObservationV1]] = defaultdict(list)
    for record in collaborator_records:
        grouped_collaborators[record.canonical_collaborator_id].append(record)
    collaborators: list[CollaboratorUniverseEntryV1] = []
    for collaborator_id, records in sorted(grouped_collaborators.items()):
        entries = [record.collaborator for record in records]
        github_digests = {entry.github_login_sha256 for entry in entries if entry.github_login_sha256}
        github_receipts = {entry.github_identity_receipt_ref for entry in entries if entry.github_identity_receipt_ref}
        if len(github_digests) > 1 or len(github_receipts) > 1:
            raise ValueError("conflicting proven GitHub identities require a source-owned disposition")
        collaborators.append(
            CollaboratorUniverseEntryV1(
                collaborator_id=collaborator_id,
                alias_ids=tuple(sorted({alias for record in records for alias in record.alias_ids})),
                source_lineage_ids=_sorted_union(entry.source_lineage_ids for entry in entries),
                github_login_sha256=next(iter(github_digests), None),
                github_identity_receipt_ref=next(iter(github_receipts), None),
                relationships=_merge_relationships(
                    [relationship for entry in entries for relationship in entry.relationships],
                    project_aliases,
                ),
                coverage_disposition=_merge_collaborator_disposition({entry.coverage_disposition for entry in entries}),
                disposition_receipt_refs=_sorted_union(entry.disposition_receipt_refs for entry in entries),
            )
        )

    required_collaborator_ids = tuple(
        sorted(
            {
                _canonicalize(identity, collaborator_aliases)
                for observation in observations
                for identity in observation.required_collaborator_ids
            }
            | {identity for project in projects for identity in project.collaborator_ids}
        )
    )
    observed_collaborator_ids = tuple(collaborator.collaborator_id for collaborator in collaborators)
    collaborator_manifest = CollaboratorUniverseManifestV1(
        manifest_id=f"collaboratorManifest{hashlib.sha256(census.census_id.encode()).hexdigest()[:24]}",
        frozen_at=census.frozen_at,
        frozen_wave_digest=census.frozen_wave_sha256,
        source_registry_digest=source_registry_sha256,
        project_universe_manifest_digest=_canonical_digest(project_manifest),
        enumeration_complete=source_enumeration_complete,
        required_source_instance_ids=expected_source_ids,
        observed_source_instance_ids=observed_source_ids,
        missing_source_instance_ids=tuple(sorted(set(expected_source_ids) - set(observed_source_ids))),
        unexpected_source_instance_ids=tuple(sorted(set(observed_source_ids) - set(expected_source_ids))),
        project_ids=observed_project_ids,
        required_collaborator_ids=required_collaborator_ids,
        missing_collaborator_ids=tuple(sorted(set(required_collaborator_ids) - set(observed_collaborator_ids))),
        unexpected_collaborator_ids=tuple(sorted(set(observed_collaborator_ids) - set(required_collaborator_ids))),
        collaborators=tuple(collaborators),
    )
    return FrozenUniversePairV1(
        project_manifest=project_manifest,
        collaborator_manifest=collaborator_manifest,
    )


def _read_model(path: Path, model: type[_ModelT]) -> _ModelT:
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def _json_bytes(value: PrimaMateriaModel) -> bytes:
    return (json.dumps(value.model_dump(mode="json"), indent=2, sort_keys=True) + "\n").encode()


def _write_pair(
    project_output: Path,
    collaborator_output: Path,
    pair: FrozenUniversePairV1,
) -> None:
    if project_output.resolve() == collaborator_output.resolve():
        raise ValueError("project and collaborator outputs must be distinct")
    prepared = (
        (project_output, _json_bytes(pair.project_manifest)),
        (collaborator_output, _json_bytes(pair.collaborator_manifest)),
    )
    temporary_paths = []
    try:
        for output, content in prepared:
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
            temporary.write_bytes(content)
            temporary_paths.append(temporary)
        for (output, _), temporary in zip(prepared, temporary_paths, strict=True):
            os.replace(temporary, output)
    finally:
        for temporary in temporary_paths:
            temporary.unlink(missing_ok=True)


def parser(root: Path) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--source-registry",
        type=Path,
        default=root / "institutio" / "governance" / "prima-materia-universe-sources.json",
    )
    result.add_argument("--census", type=Path, required=True)
    result.add_argument("--observation", type=Path, action="append", required=True)
    result.add_argument("--project-output", type=Path, required=True)
    result.add_argument("--collaborator-output", type=Path, required=True)
    result.add_argument("--check", action="store_true", help="Compare exact bytes without writing.")
    return result


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    repository_root = root or Path(__file__).resolve().parents[3]
    arguments = parser(repository_root).parse_args(argv)
    try:
        source_registry = _read_model(arguments.source_registry, UniverseSourceRegistryV1)
        census = _read_model(arguments.census, UniverseSourceCensusV1)
        observations = tuple(
            _read_model(observation, UniverseSourceObservationV1) for observation in arguments.observation
        )
        pair = freeze_universe(
            source_registry=source_registry,
            census=census,
            observations=observations,
        )
        project_bytes = _json_bytes(pair.project_manifest)
        collaborator_bytes = _json_bytes(pair.collaborator_manifest)
        changed = (
            not arguments.project_output.is_file()
            or arguments.project_output.read_bytes() != project_bytes
            or not arguments.collaborator_output.is_file()
            or arguments.collaborator_output.read_bytes() != collaborator_bytes
        )
        if not arguments.check:
            _write_pair(arguments.project_output, arguments.collaborator_output, pair)
        result = {
            "schema": FREEZE_SCHEMA,
            "passed": not arguments.check or not changed,
            "changed": changed,
            "project_count": len(pair.project_manifest.projects),
            "collaborator_count": len(pair.collaborator_manifest.collaborators),
            "missing_source_count": len(pair.project_manifest.missing_source_instance_ids),
            "missing_project_count": len(pair.project_manifest.missing_project_ids),
            "missing_collaborator_count": len(pair.collaborator_manifest.missing_collaborator_ids),
            "project_manifest_sha256": _canonical_digest(pair.project_manifest),
            "collaborator_manifest_sha256": _canonical_digest(pair.collaborator_manifest),
        }
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        result = {
            "schema": FREEZE_SCHEMA,
            "passed": False,
            "changed": False,
            "reason": type(exc).__name__,
        }
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
