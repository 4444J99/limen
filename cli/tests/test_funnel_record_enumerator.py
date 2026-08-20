from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from limen.funnel_record_enumerator import (
    FunnelRecordContextV1,
    FunnelSourceManifestV1,
    classify_funnel_records,
    enumerate_funnel_records,
)

WAVE = "a" * 64
SOURCE_REGISTRY = "b" * 64
FROZEN_AT = datetime(2026, 7, 28, 20, tzinfo=UTC)
OWNER_REF = "institutio/governance/prima-materia-funnel-sources.json"


def _context(dimension: str) -> FunnelRecordContextV1:
    return FunnelRecordContextV1(
        dimension=dimension,
        source_kind="funnel_records",
        owner_ref=OWNER_REF,
        completeness_predicate="every source-owned funnel record has a disposition",
        privacy_projection_ref="funnel-records-redacted-projection-v1",
        frozen_wave_sha256=WAVE,
        source_registry_sha256=SOURCE_REGISTRY,
        frozen_at=FROZEN_AT,
    )


def _tracked_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _all_strings(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return {item for child in value.values() for item in _all_strings(child)}
    if isinstance(value, (list, tuple)):
        return {item for child in value for item in _all_strings(child)}
    return set()


def _source(
    source_id: str,
    path: str,
    *,
    source_format: str = "json",
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "path": path,
        "format": source_format,
        "owner_ref": "scripts/fixture-owner.py",
        "max_bytes": 8192,
        "max_rows": 100,
    }


def _write_manifest(root: Path, sources: list[dict[str, Any]]) -> Path:
    path = root / OWNER_REF
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "limen.funnel_source_manifest.v1",
                "manifest_id": "fixtureFunnelSourcesV1",
                "sources": sources,
            }
        )
    )
    return path


def test_current_manifest_exposes_three_missing_runtime_sources_as_debt() -> None:
    root = _tracked_root()
    manifest = root / OWNER_REF
    classification = classify_funnel_records(manifest, repository_root=root)
    project = enumerate_funnel_records(
        dimension="project",
        context=_context("project"),
        manifest_path=manifest,
        repository_root=root,
    )
    collaborator = enumerate_funnel_records(
        dimension="collaborator",
        context=_context("collaborator"),
        manifest_path=manifest,
        repository_root=root,
    )

    assert len(classification.source_instances) == 3
    assert all(isinstance(item.available, bool) for item in classification.source_instances)
    assert not project["enumeration_complete"]
    assert not collaborator["enumeration_complete"]
    assert all(not item["projects"] for item in project["instances"])
    assert all(not item["collaborators"] for item in collaborator["instances"])
    emitted = _all_strings((project, collaborator))
    assert not any(value.startswith("logs/") for value in emitted)


def test_present_records_are_count_bound_opaque_and_privacy_safe(tmp_path: Path) -> None:
    private_values = {"Private Person", "Secret Account", "private.example"}
    (tmp_path / "records").mkdir()
    (tmp_path / "records" / "status.json").write_text(
        json.dumps(
            {
                "_doc": "aggregate status",
                "person": "Private Person",
                "account": "Secret Account",
            }
        )
    )
    traffic_rows = [
        {"repo": "private.example", "uniques": 3},
        {"repo": "private.example", "uniques": 3},
        {"repo": "public/example", "uniques": 0},
    ]
    (tmp_path / "records" / "traffic.jsonl").write_text("\n".join(json.dumps(row) for row in traffic_rows) + "\n")
    manifest = _write_manifest(
        tmp_path,
        [
            _source("status-aggregate", "records/status.json"),
            _source(
                "traffic-observations",
                "records/traffic.jsonl",
                source_format="jsonl",
            ),
        ],
    )

    classification = classify_funnel_records(manifest, repository_root=tmp_path)
    project = enumerate_funnel_records(
        dimension="project",
        context=_context("project"),
        manifest_path=manifest,
        repository_root=tmp_path,
    )
    emitted = _all_strings(project)

    assert [item.row_count for item in classification.source_instances] == [3, 3]
    assert sum(len(item.non_project_row_ids) for item in classification.source_instances) == 1
    assert sum(len(item.unclassified_row_ids) for item in classification.source_instances) == 4
    assert not project["enumeration_complete"]
    assert all(not item["required_project_ids"] for item in project["instances"])
    assert all(not item["projects"] for item in project["instances"])
    assert private_values.isdisjoint(emitted)


def test_manifest_add_remove_and_reorder_changes_coverage_without_identity_drift(
    tmp_path: Path,
) -> None:
    (tmp_path / "records").mkdir()
    (tmp_path / "records" / "first.json").write_text('{"_doc":"first"}')
    (tmp_path / "records" / "second.json").write_text('{"_doc":"second"}')
    first_source = _source("first-source", "records/first.json")
    second_source = _source("second-source", "records/second.json")
    manifest = _write_manifest(tmp_path, [first_source, second_source])
    original = classify_funnel_records(manifest, repository_root=tmp_path)

    _write_manifest(tmp_path, [second_source, first_source])
    reordered = classify_funnel_records(manifest, repository_root=tmp_path)
    _write_manifest(
        tmp_path,
        [
            second_source,
            first_source,
            _source("third-source", "records/third.json"),
        ],
    )
    expanded = classify_funnel_records(manifest, repository_root=tmp_path)
    _write_manifest(tmp_path, [second_source])
    reduced = classify_funnel_records(manifest, repository_root=tmp_path)

    original_ids = {item.source_instance_id for item in original.source_instances}
    assert original_ids == {item.source_instance_id for item in reordered.source_instances}
    assert original_ids < {item.source_instance_id for item in expanded.source_instances}
    assert {item.source_instance_id for item in reduced.source_instances} < original_ids
    assert len(expanded.source_instances) == 3
    assert sum(not item.available for item in expanded.source_instances) == 1


def test_manifest_rejects_duplicate_and_escaping_source_paths() -> None:
    with pytest.raises(ValueError, match="must be unique"):
        FunnelSourceManifestV1.model_validate(
            {
                "manifest_id": "fixtureFunnelSourcesV1",
                "sources": [
                    _source("first-source", "records/shared.json"),
                    _source("second-source", "records/shared.json"),
                ],
            }
        )
    with pytest.raises(ValueError, match="repository-relative"):
        FunnelSourceManifestV1.model_validate(
            {
                "manifest_id": "fixtureFunnelSourcesV1",
                "sources": [_source("first-source", "../private.json")],
            }
        )
