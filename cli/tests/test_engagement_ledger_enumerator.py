from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from limen.engagement_ledger_enumerator import (
    EngagementLedgerContextV1,
    classify_engagement_ledger,
    enumerate_engagement_ledger,
)

WAVE = "a" * 64
SOURCE_REGISTRY = "b" * 64
FROZEN_AT = datetime(2026, 7, 28, 20, tzinfo=UTC)


def _context(dimension: str) -> EngagementLedgerContextV1:
    return EngagementLedgerContextV1(
        dimension=dimension,
        source_kind="engagements",
        owner_ref="state/aug1/engagements.json",
        completeness_predicate="every engagement row has a project and collaborator disposition",
        privacy_projection_ref="engagements-redacted-projection-v1",
        frozen_wave_sha256=WAVE,
        source_registry_sha256=SOURCE_REGISTRY,
        frozen_at=FROZEN_AT,
    )


def _tracked_source() -> Path:
    return Path(__file__).resolve().parents[2] / "state" / "aug1" / "engagements.json"


def _all_strings(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return {item for child in value.values() for item in _all_strings(child)}
    if isinstance(value, (list, tuple)):
        return {item for child in value for item in _all_strings(child)}
    return set()


def test_current_empty_ledger_is_complete_zero_shape_with_classified_metadata() -> None:
    source = _tracked_source()
    classification = classify_engagement_ledger(source)
    project = enumerate_engagement_ledger(
        dimension="project",
        context=_context("project"),
        source_path=source,
    )
    collaborator = enumerate_engagement_ledger(
        dimension="collaborator",
        context=_context("collaborator"),
        source_path=source,
    )

    assert classification.enumeration_complete
    assert classification.engagement_row_count == 0
    assert len(classification.non_project_row_ids) == 1
    assert classification.unclassified_row_ids == ()
    assert project["instances"][0]["required_project_ids"] == []
    assert project["instances"][0]["projects"] == []
    assert collaborator["instances"][0]["required_collaborator_ids"] == []
    assert collaborator["instances"][0]["collaborators"] == []
    assert project["instances"][0]["non_project_row_ids"] == collaborator["instances"][0]["non_project_row_ids"]


def test_unknown_future_row_is_opaque_incomplete_debt_not_a_false_project(tmp_path: Path) -> None:
    private_values = {"person": "Private Person", "project": "Secret Project"}
    source = tmp_path / "engagements.json"
    source.write_text(
        json.dumps(
            {
                "_doc": "fixture",
                "engagements": [
                    {
                        **private_values,
                        "status": "signed",
                        "deposit_cleared": True,
                    }
                ],
            }
        )
    )

    classification = classify_engagement_ledger(source)
    project = enumerate_engagement_ledger(
        dimension="project",
        context=_context("project"),
        source_path=source,
    )
    collaborator = enumerate_engagement_ledger(
        dimension="collaborator",
        context=_context("collaborator"),
        source_path=source,
    )
    emitted = _all_strings((project, collaborator))

    assert not classification.enumeration_complete
    assert classification.engagement_row_count == 1
    assert len(classification.unclassified_row_ids) == 1
    assert not project["enumeration_complete"]
    assert not collaborator["enumeration_complete"]
    assert project["instances"][0]["projects"] == []
    assert collaborator["instances"][0]["collaborators"] == []
    assert project["instances"][0]["unclassified_row_ids"] == collaborator["instances"][0]["unclassified_row_ids"]
    assert set(private_values.values()).isdisjoint(emitted)


def test_unclassified_row_identities_are_order_independent_and_count_duplicates(
    tmp_path: Path,
) -> None:
    rows = [{"status": "lead"}, {"status": "sent"}, {"status": "lead"}]
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps({"_doc": "fixture", "engagements": rows}))
    second.write_text(json.dumps({"_doc": "fixture", "engagements": list(reversed(rows))}))

    original = classify_engagement_ledger(first)
    reordered = classify_engagement_ledger(second)

    assert original.engagement_row_count == 3
    assert len(original.unclassified_row_ids) == 2
    assert original.source_instance_id == reordered.source_instance_id
    assert original.unclassified_row_ids == reordered.unclassified_row_ids
