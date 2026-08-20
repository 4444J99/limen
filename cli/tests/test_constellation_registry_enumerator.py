from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from limen.constellation_registry_enumerator import (
    ConstellationContextV1,
    classify_constellation_registry,
    enumerate_constellation_registry,
)

WAVE = "a" * 64
SOURCE_REGISTRY = "b" * 64
FROZEN_AT = datetime(2026, 7, 28, 20, tzinfo=UTC)


def _context(dimension: str) -> ConstellationContextV1:
    return ConstellationContextV1(
        dimension=dimension,
        source_kind="constellation",
        owner_ref="organs/consulting/constellation/registry.yaml",
        completeness_predicate="every public person and project lane has a disposition",
        privacy_projection_ref="constellation-redacted-projection-v1",
        frozen_wave_sha256=WAVE,
        source_registry_sha256=SOURCE_REGISTRY,
        frozen_at=FROZEN_AT,
    )


def _all_strings(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return {item for child in value.values() for item in _all_strings(child)}
    if isinstance(value, (list, tuple)):
        return {item for child in value for item in _all_strings(child)}
    return set()


def _tracked_source() -> Path:
    return Path(__file__).resolve().parents[2] / "organs" / "consulting" / "constellation" / "registry.yaml"


def test_tracked_constellation_preserves_people_projects_and_repository_shapes() -> None:
    classification = classify_constellation_registry(_tracked_source())

    assert classification.debt_count == 15
    assert classification.project_row_count == 23
    assert len(classification.required_project_ids) == 10
    assert len(classification.projects) == 10
    assert len(classification.required_collaborator_ids) == 11
    assert len(classification.collaborators) == 11

    roles = [
        relationship.roles for item in classification.collaborators for relationship in item.collaborator.relationships
    ]
    assert roles.count(("client",)) == 4
    assert roles.count(("prospect",)) == 8
    assert all(
        relationship.project_access_level == "none"
        and relationship.project_access_status == "not_granted"
        and not relationship.repository_accesses
        for item in classification.collaborators
        for relationship in item.collaborator.relationships
    )


def test_fragments_emit_no_raw_person_project_or_repository_identity() -> None:
    source = _tracked_source()
    document = yaml.safe_load(source.read_text())
    raw_identities = (
        {person["slug"] for person in document["people"]}
        | {project["name"] for person in document["people"] for project in person["projects"]}
        | {
            repository
            for person in document["people"]
            for project in person["projects"]
            for repository in (
                *((project["repo"],) if project.get("repo") else ()),
                *(project.get("related_repos") or ()),
            )
        }
    )
    payloads = [
        enumerate_constellation_registry(
            dimension=dimension,
            context=_context(dimension),
            source_path=source,
        )
        for dimension in ("census", "project", "collaborator")
    ]

    assert raw_identities.isdisjoint({value for payload in payloads for value in _all_strings(payload)})
    assert all(json.dumps(payload, sort_keys=True) for payload in payloads)


def test_reorder_preserves_opaque_identities_and_relationships(tmp_path: Path) -> None:
    document = yaml.safe_load(_tracked_source().read_text())
    reordered = {
        **document,
        "people": [
            {
                **person,
                "projects": list(reversed(person["projects"])),
            }
            for person in reversed(document["people"])
        ],
    }
    reordered_source = tmp_path / "registry.yaml"
    reordered_source.write_text(yaml.safe_dump(reordered, sort_keys=False))

    original = classify_constellation_registry(_tracked_source())
    changed = classify_constellation_registry(reordered_source)

    assert original.source_sha256 != changed.source_sha256
    assert original.source_instance_id == changed.source_instance_id
    assert original.required_project_ids == changed.required_project_ids
    assert original.required_collaborator_ids == changed.required_collaborator_ids
    assert [
        (
            item.canonical_project_id,
            item.project.source_lineage_ids,
            item.project.repository_ids,
            item.project.collaborator_ids,
            item.project.lifecycle_stage,
        )
        for item in original.projects
    ] == [
        (
            item.canonical_project_id,
            item.project.source_lineage_ids,
            item.project.repository_ids,
            item.project.collaborator_ids,
            item.project.lifecycle_stage,
        )
        for item in changed.projects
    ]
    assert [
        (
            item.canonical_collaborator_id,
            item.collaborator.source_lineage_ids,
            item.collaborator.relationships,
        )
        for item in original.collaborators
    ] == [
        (
            item.canonical_collaborator_id,
            item.collaborator.source_lineage_ids,
            item.collaborator.relationships,
        )
        for item in changed.collaborators
    ]


def test_unsupported_field_remains_incomplete_source_debt(tmp_path: Path) -> None:
    document = yaml.safe_load(_tracked_source().read_text())
    document["people"][0]["unknown_relationship_claim"] = "must-not-disappear"
    source = tmp_path / "registry.yaml"
    source.write_text(yaml.safe_dump(document, sort_keys=False))

    classification = classify_constellation_registry(source)
    payload = enumerate_constellation_registry(
        dimension="collaborator",
        context=_context("collaborator"),
        source_path=source,
    )

    base_debts = classify_constellation_registry(_tracked_source()).debt_count
    assert not classification.enumeration_complete
    assert classification.debt_count == base_debts + 1
    assert not payload["enumeration_complete"]
