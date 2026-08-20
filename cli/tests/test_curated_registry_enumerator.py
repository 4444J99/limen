from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from limen.curated_registry_enumerator import (
    CuratedRegistryContextV1,
    classify_curated_registry,
    enumerate_curated_registry,
)

WAVE = "a" * 64
SOURCE_REGISTRY = "b" * 64
FROZEN_AT = datetime(2026, 7, 28, 20, tzinfo=UTC)


def _context(dimension: str) -> CuratedRegistryContextV1:
    return CuratedRegistryContextV1(
        dimension=dimension,
        source_kind="curated_registry",
        owner_ref="institutio/registry/organs.yaml",
        completeness_predicate="every registry row has a disposition",
        privacy_projection_ref="curated-registry-redacted-projection-v1",
        frozen_wave_sha256=WAVE,
        source_registry_sha256=SOURCE_REGISTRY,
        frozen_at=FROZEN_AT,
    )


def test_tracked_registry_classifies_every_organ_and_officer_as_non_project() -> None:
    root = Path(__file__).resolve().parents[2]
    source = root / "institutio" / "registry" / "organs.yaml"

    classification = classify_curated_registry(source)
    project = enumerate_curated_registry(
        dimension="project",
        context=_context("project"),
        source_path=source,
    )
    collaborator = enumerate_curated_registry(
        dimension="collaborator",
        context=_context("collaborator"),
        source_path=source,
    )

    assert classification.enumeration_complete
    assert classification.debt_count == 0
    assert classification.row_count == 26
    assert project["instances"][0]["projects"] == []
    assert project["instances"][0]["required_project_ids"] == []
    assert collaborator["instances"][0]["collaborators"] == []
    assert collaborator["instances"][0]["required_collaborator_ids"] == []
    assert project["instances"][0]["non_project_row_ids"] == collaborator["instances"][0]["non_project_row_ids"]


def test_output_is_stable_under_reorder_and_contains_no_registry_names(tmp_path: Path) -> None:
    first = {
        "schema_version": 0.1,
        "seeded_from": "fixture",
        "organs": [
            {"name": "alpha", "status": "built"},
            {"name": "beta", "status": "partial"},
        ],
        "officers": {
            "CTO": {"mandate": "fixture", "organs": ["alpha", "beta"]},
        },
    }
    second = {
        **first,
        "organs": list(reversed(first["organs"])),
        "officers": dict(reversed(tuple(first["officers"].items()))),
    }
    first_path = tmp_path / "first.yaml"
    second_path = tmp_path / "second.yaml"
    first_path.write_text(yaml.safe_dump(first, sort_keys=False))
    second_path.write_text(yaml.safe_dump(second, sort_keys=False))

    first_classification = classify_curated_registry(first_path)
    second_classification = classify_curated_registry(second_path)
    output = enumerate_curated_registry(
        dimension="project",
        context=_context("project"),
        source_path=first_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert first_classification.source_instance_id == second_classification.source_instance_id
    assert first_classification.non_project_row_ids == second_classification.non_project_row_ids
    assert "alpha" not in serialized
    assert "beta" not in serialized
    assert "CTO" not in serialized


def test_unknown_collection_and_broken_membership_remain_incomplete_debt(tmp_path: Path) -> None:
    source = tmp_path / "ambiguous.yaml"
    source.write_text(
        yaml.safe_dump(
            {
                "schema_version": 0.1,
                "seeded_from": "fixture",
                "organs": [{"name": "alpha"}],
                "officers": {
                    "CTO": {"organs": ["missing-organ"]},
                },
                "unknown_rows": [{"name": "not-silently-classified"}],
            },
            sort_keys=False,
        )
    )

    classification = classify_curated_registry(source)
    output = enumerate_curated_registry(
        dimension="project",
        context=_context("project"),
        source_path=source,
    )

    assert not classification.enumeration_complete
    assert classification.debt_count == 2
    assert not output["enumeration_complete"]
