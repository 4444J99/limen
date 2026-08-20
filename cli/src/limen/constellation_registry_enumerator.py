"""Privacy-safe enumeration of the public collaborator constellation registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import rfc8785
import yaml
from pydantic import Field, field_validator

from limen.prima_materia import (
    CollaboratorProjectRelationshipV1,
    CollaboratorUniverseEntryV1,
    PrimaMateriaModel,
    ProjectUniverseEntryV1,
)
from limen.universe_adapter_runner import (
    Dimension,
    UniverseCensusFragmentV1,
    UniverseCollaboratorFragmentV1,
    UniverseCollaboratorInstanceFragmentV1,
    UniverseProjectFragmentV1,
    UniverseProjectInstanceFragmentV1,
)
from limen.universe_freezer import (
    SourceCollaboratorObservationV1,
    SourceProjectObservationV1,
    UniverseSourceInstanceExpectationV1,
)

SOURCE_KIND: Literal["constellation"] = "constellation"
OWNER_REF: Literal["organs/consulting/constellation/registry.yaml"] = "organs/consulting/constellation/registry.yaml"
CONTEXT_SCHEMA: Literal["limen.universe_enumerator_context.v1"] = "limen.universe_enumerator_context.v1"
EXPECTED_TOP_LEVEL_KEYS = frozenset({"version", "owner", "people"})
EXPECTED_PERSON_KEYS = frozenset(
    {
        "slug",
        "tier",
        "engagement_ref",
        "funnel_instance_ref",
        "projects",
    }
)
EXPECTED_PROJECT_KEYS = frozenset(
    {
        "name",
        "repo",
        "related_repos",
        "keywords",
        "stage",
        "public_face_state",
        "dossier",
        "notes",
    }
)
TIERS = frozenset({"T1", "T2", "T3"})
STAGES = frozenset({"idea", "dossier", "building", "mvp", "live", "funnelized"})
FACES = frozenset({"none", "pending-split", "readme", "portal", "funnelized"})
SLUG_RE = re.compile(r"^[a-z]+(?:-[a-z])?$")
PROJECT_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REPOSITORY_RE = re.compile(r"^organvm/[a-z0-9][a-z0-9._-]*$")


def _validate_digest(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("digest must be lowercase SHA-256")
    return value


def _digest_payload(value: Any) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _opaque(prefix: str, value: Any) -> str:
    return f"{prefix}{_digest_payload(value)[:24]}"


def _normalized_ref(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or value.strip() != value or "\x00" in value:
        raise ValueError("reference must be a normalized repository-relative path")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or "." in parsed.parts or ".." in parsed.parts or str(parsed) != value:
        raise ValueError("reference must be a normalized repository-relative path")
    return value


class ConstellationContextV1(PrimaMateriaModel):
    context_schema: Literal["limen.universe_enumerator_context.v1"] = Field(
        default=CONTEXT_SCHEMA,
        alias="schema",
    )
    dimension: Dimension
    source_kind: Literal["constellation"] = SOURCE_KIND
    owner_ref: Literal["organs/consulting/constellation/registry.yaml"] = OWNER_REF
    completeness_predicate: str = Field(min_length=1, max_length=4096)
    privacy_projection_ref: str = Field(min_length=1, max_length=256)
    frozen_wave_sha256: str
    source_registry_sha256: str
    frozen_at: datetime
    custody_receipt_sha256: str | None = None

    _digests = field_validator(
        "frozen_wave_sha256",
        "source_registry_sha256",
    )(_validate_digest)
    _custody = field_validator("custody_receipt_sha256")(
        lambda value: _validate_digest(value) if value is not None else None
    )

    @field_validator("frozen_at")
    @classmethod
    def frozen_at_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("frozen_at must include an explicit UTC offset")
        return value.astimezone(UTC)


class ConstellationClassificationV1(PrimaMateriaModel):
    source_instance_id: str
    source_sha256: str
    enumeration_complete: bool
    project_row_count: int = Field(ge=0)
    debt_count: int = Field(ge=0)
    required_project_ids: tuple[str, ...]
    projects: tuple[SourceProjectObservationV1, ...]
    required_collaborator_ids: tuple[str, ...]
    collaborators: tuple[SourceCollaboratorObservationV1, ...]


def _empty_classification(source_sha256: str, source_instance_id: str) -> ConstellationClassificationV1:
    return ConstellationClassificationV1(
        source_instance_id=source_instance_id,
        source_sha256=source_sha256,
        enumeration_complete=False,
        project_row_count=0,
        debt_count=1,
        required_project_ids=(),
        projects=(),
        required_collaborator_ids=(),
        collaborators=(),
    )


def _project_identity(name: str) -> str:
    return _opaque("projectConstellation", {"source_kind": SOURCE_KIND, "project_key": name})


def _collaborator_identity(slug: str) -> str:
    return _opaque("collaboratorConstellation", {"source_kind": SOURCE_KIND, "person_key": slug})


def _repository_identity(repository: str) -> str:
    return _opaque("repositoryIdentifier", {"repository": repository})


def classify_constellation_registry(
    source_path: Path,
    *,
    owner_ref: str = OWNER_REF,
) -> ConstellationClassificationV1:
    """Classify public project lanes and relationships without emitting names."""

    source_bytes = source_path.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    source_instance_id = _opaque("sourceInstanceConstellation", {"owner_ref": owner_ref})
    document = yaml.safe_load(source_bytes)
    if not isinstance(document, dict):
        return _empty_classification(source_sha256, source_instance_id)

    debt_count = len(set(document) - EXPECTED_TOP_LEVEL_KEYS)
    if document.get("version") != "constellation.v1":
        debt_count += 1
    if document.get("owner") != "consulting":
        debt_count += 1
    raw_people = document.get("people")
    if not isinstance(raw_people, list) or not raw_people:
        return _empty_classification(source_sha256, source_instance_id)

    raw_slugs = [
        person.get("slug") for person in raw_people if isinstance(person, dict) and isinstance(person.get("slug"), str)
    ]
    duplicate_slugs = {slug for slug, count in Counter(raw_slugs).items() if count > 1}
    debt_count += len(duplicate_slugs)
    normalized_people: list[dict[str, Any]] = []
    project_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    project_row_count = 0

    for person in raw_people:
        if not isinstance(person, dict):
            debt_count += 1
            continue
        debt_count += len(set(person) - EXPECTED_PERSON_KEYS)
        slug = person.get("slug")
        if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug) or slug in duplicate_slugs:
            debt_count += 1
            continue
        if person.get("tier") not in TIERS:
            debt_count += 1
        try:
            engagement_ref = _normalized_ref(person.get("engagement_ref"))
            _normalized_ref(person.get("funnel_instance_ref"))
        except ValueError:
            debt_count += 1
            engagement_ref = None
        raw_projects = person.get("projects")
        if not isinstance(raw_projects, list) or not raw_projects:
            debt_count += 1
            continue

        seen_project_names: set[str] = set()
        person_project_names: list[str] = []
        for project in raw_projects:
            project_row_count += 1
            if not isinstance(project, dict):
                debt_count += 1
                continue
            debt_count += len(set(project) - EXPECTED_PROJECT_KEYS)
            name = project.get("name")
            if not isinstance(name, str) or not PROJECT_RE.fullmatch(name) or name in seen_project_names:
                debt_count += 1
                continue
            seen_project_names.add(name)
            if project.get("stage") not in STAGES or project.get("public_face_state") not in FACES:
                debt_count += 1
                continue
            keywords = project.get("keywords")
            if (
                not isinstance(keywords, list)
                or not keywords
                or any(not isinstance(keyword, str) or not keyword.strip() for keyword in keywords)
            ):
                debt_count += 1
                continue
            repository = project.get("repo")
            if repository is not None and (not isinstance(repository, str) or not REPOSITORY_RE.fullmatch(repository)):
                debt_count += 1
                continue
            related_repositories = project.get("related_repos", [])
            if (
                not isinstance(related_repositories, list)
                or any(not isinstance(item, str) or not REPOSITORY_RE.fullmatch(item) for item in related_repositories)
                or len(related_repositories) != len(set(related_repositories))
                or repository in related_repositories
            ):
                debt_count += 1
                continue
            try:
                _normalized_ref(project.get("dossier"))
            except ValueError:
                debt_count += 1
                continue
            if project.get("notes") is not None and not isinstance(project.get("notes"), str):
                debt_count += 1
                continue
            normalized = {
                "name": name,
                "stage": project["stage"],
                "public_face_state": project["public_face_state"],
                "repository": repository,
                "related_repositories": tuple(related_repositories),
                "slug": slug,
            }
            project_groups[name].append(normalized)
            person_project_names.append(name)
        if not person_project_names:
            debt_count += 1
            continue
        normalized_people.append(
            {
                "slug": slug,
                "relationship_role": "client" if engagement_ref is not None else "prospect",
                "project_names": tuple(sorted(person_project_names)),
            }
        )

    required_project_ids = tuple(sorted(_project_identity(name) for name in project_groups))
    project_observations: list[SourceProjectObservationV1] = []
    valid_project_names: set[str] = set()
    for name, rows in sorted(project_groups.items()):
        stages = {row["stage"] for row in rows}
        faces = {row["public_face_state"] for row in rows}
        primary_repositories = {row["repository"] for row in rows if row["repository"] is not None}
        if len(stages) != 1 or len(faces) != 1 or len(primary_repositories) > 1:
            debt_count += 1
            continue
        project_id = _project_identity(name)
        repository_ids = tuple(
            sorted(
                {
                    _repository_identity(repository)
                    for row in rows
                    for repository in (
                        *((row["repository"],) if row["repository"] is not None else ()),
                        *row["related_repositories"],
                    )
                }
            )
        )
        source_lineage_ids = tuple(
            sorted(
                _opaque(
                    "constellationProjectLineage",
                    {
                        "owner_ref": owner_ref,
                        "person_key": row["slug"],
                        "project_key": name,
                    },
                )
                for row in rows
            )
        )
        collaborator_ids = tuple(sorted({_collaborator_identity(row["slug"]) for row in rows}))
        project_observations.append(
            SourceProjectObservationV1(
                canonical_project_id=project_id,
                project=ProjectUniverseEntryV1(
                    project_id=project_id,
                    source_lineage_ids=source_lineage_ids,
                    repository_ids=repository_ids,
                    collaborator_ids=collaborator_ids,
                    lifecycle_stage=next(iter(stages)),
                    predicate_refs=(_opaque("constellationProjectBuildPredicate", {"project_id": project_id}),),
                    coverage_disposition="partial",
                    build_status="unknown",
                ),
            )
        )
        valid_project_names.add(name)

    required_collaborator_ids = tuple(sorted(_collaborator_identity(person["slug"]) for person in normalized_people))
    collaborator_observations: list[SourceCollaboratorObservationV1] = []
    for person in sorted(normalized_people, key=lambda item: item["slug"]):
        if not set(person["project_names"]).issubset(valid_project_names):
            debt_count += 1
            continue
        collaborator_id = _collaborator_identity(person["slug"])
        relationships = tuple(
            CollaboratorProjectRelationshipV1(
                project_id=_project_identity(name),
                roles=(person["relationship_role"],),
            )
            for name in sorted(person["project_names"], key=_project_identity)
        )
        collaborator_observations.append(
            SourceCollaboratorObservationV1(
                canonical_collaborator_id=collaborator_id,
                collaborator=CollaboratorUniverseEntryV1(
                    collaborator_id=collaborator_id,
                    source_lineage_ids=(
                        _opaque(
                            "constellationPersonLineage",
                            {"owner_ref": owner_ref, "person_key": person["slug"]},
                        ),
                    ),
                    relationships=relationships,
                    coverage_disposition="identity_unresolved",
                    disposition_receipt_refs=(
                        _opaque(
                            "constellationCollaboratorDispositionReceipt",
                            {
                                "source_sha256": source_sha256,
                                "person_key": person["slug"],
                                "disposition": "identity_unresolved",
                            },
                        ),
                    ),
                ),
            )
        )

    project_observations_tuple = tuple(sorted(project_observations, key=lambda item: item.canonical_project_id))
    collaborator_observations_tuple = tuple(
        sorted(
            collaborator_observations,
            key=lambda item: item.canonical_collaborator_id,
        )
    )
    complete = (
        debt_count == 0
        and len(project_observations_tuple) == len(required_project_ids)
        and len(collaborator_observations_tuple) == len(required_collaborator_ids)
    )
    return ConstellationClassificationV1(
        source_instance_id=source_instance_id,
        source_sha256=source_sha256,
        enumeration_complete=complete,
        project_row_count=project_row_count,
        debt_count=debt_count,
        required_project_ids=required_project_ids,
        projects=project_observations_tuple,
        required_collaborator_ids=required_collaborator_ids,
        collaborators=collaborator_observations_tuple,
    )


def enumerate_constellation_registry(
    *,
    dimension: Dimension,
    context: ConstellationContextV1,
    source_path: Path,
) -> dict[str, Any]:
    """Return one strict universe fragment for the requested dimension."""

    if context.dimension != dimension:
        raise ValueError("requested dimension does not match the enumerator context")
    classification = classify_constellation_registry(source_path, owner_ref=context.owner_ref)
    receipt_ref = _opaque(
        f"constellation{dimension.title()}Receipt",
        {
            "dimension": dimension,
            "source_sha256": classification.source_sha256,
            "frozen_wave_sha256": context.frozen_wave_sha256,
            "required_project_ids": classification.required_project_ids,
            "required_collaborator_ids": classification.required_collaborator_ids,
            "debt_count": classification.debt_count,
        },
    )
    observed_at = context.frozen_at.astimezone(UTC)
    fragment: UniverseCensusFragmentV1 | UniverseProjectFragmentV1 | UniverseCollaboratorFragmentV1
    if dimension == "census":
        fragment = UniverseCensusFragmentV1(
            source_kind=SOURCE_KIND,
            observed_at=observed_at,
            enumeration_complete=True,
            receipt_ref=receipt_ref,
            source_instances=(
                UniverseSourceInstanceExpectationV1(
                    source_instance_id=classification.source_instance_id,
                    source_kind=SOURCE_KIND,
                    owner_receipt_ref=_opaque(
                        "constellationSourceReceipt",
                        {
                            "owner_ref": context.owner_ref,
                            "source_sha256": classification.source_sha256,
                        },
                    ),
                ),
            ),
        )
    elif dimension == "project":
        fragment = UniverseProjectFragmentV1(
            source_kind=SOURCE_KIND,
            observed_at=observed_at,
            enumeration_complete=classification.enumeration_complete,
            receipt_ref=receipt_ref,
            instances=(
                UniverseProjectInstanceFragmentV1(
                    source_instance_id=classification.source_instance_id,
                    required_project_ids=classification.required_project_ids,
                    projects=classification.projects,
                    non_project_row_ids=(),
                ),
            ),
        )
    else:
        fragment = UniverseCollaboratorFragmentV1(
            source_kind=SOURCE_KIND,
            observed_at=observed_at,
            enumeration_complete=classification.enumeration_complete,
            receipt_ref=receipt_ref,
            instances=(
                UniverseCollaboratorInstanceFragmentV1(
                    source_instance_id=classification.source_instance_id,
                    required_collaborator_ids=classification.required_collaborator_ids,
                    collaborators=classification.collaborators,
                    reference_only_identity_ids=(),
                    non_project_row_ids=(),
                ),
            ),
        )
    return fragment.model_dump(mode="json")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--dimension", choices=("census", "project", "collaborator"), required=True)
    return result


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    arguments = parser().parse_args(argv)
    repository_root = (root or Path(__file__).resolve().parents[3]).resolve()
    try:
        raw_context = sys.stdin.buffer.read(64 * 1024 + 1)
        if len(raw_context) > 64 * 1024:
            raise ValueError("enumerator context exceeds the bounded protocol")
        context = ConstellationContextV1.model_validate_json(raw_context)
        payload = enumerate_constellation_registry(
            dimension=arguments.dimension,
            context=context,
            source_path=repository_root / OWNER_REF,
        )
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        print(type(exc).__name__, file=sys.stderr)
        return 1
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0
