"""Privacy-safe enumeration of the tracked AUG1 engagement ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import rfc8785
from pydantic import Field, field_validator

from limen.prima_materia import PrimaMateriaModel
from limen.universe_adapter_runner import (
    Dimension,
    UniverseCensusFragmentV1,
    UniverseCollaboratorFragmentV1,
    UniverseCollaboratorInstanceFragmentV1,
    UniverseProjectFragmentV1,
    UniverseProjectInstanceFragmentV1,
)
from limen.universe_freezer import UniverseSourceInstanceExpectationV1

SOURCE_KIND: Literal["engagements"] = "engagements"
OWNER_REF: Literal["state/aug1/engagements.json"] = "state/aug1/engagements.json"
CONTEXT_SCHEMA: Literal["limen.universe_enumerator_context.v1"] = "limen.universe_enumerator_context.v1"
EXPECTED_TOP_LEVEL_KEYS = frozenset({"_doc", "engagements"})


def _validate_digest(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("digest must be lowercase SHA-256")
    return value


def _digest_payload(value: Any) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _opaque(prefix: str, value: Any) -> str:
    return f"{prefix}{_digest_payload(value)[:24]}"


class EngagementLedgerContextV1(PrimaMateriaModel):
    context_schema: Literal["limen.universe_enumerator_context.v1"] = Field(
        default=CONTEXT_SCHEMA,
        alias="schema",
    )
    dimension: Dimension
    source_kind: Literal["engagements"] = SOURCE_KIND
    owner_ref: Literal["state/aug1/engagements.json"] = OWNER_REF
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


class EngagementLedgerClassificationV1(PrimaMateriaModel):
    source_instance_id: str
    source_sha256: str
    enumeration_complete: bool
    engagement_row_count: int = Field(ge=0)
    non_project_row_ids: tuple[str, ...]
    unclassified_row_ids: tuple[str, ...]


def classify_engagement_ledger(
    source_path: Path,
    *,
    owner_ref: str = OWNER_REF,
) -> EngagementLedgerClassificationV1:
    """Classify the empty ledger while retaining every unknown future row as debt."""

    source_bytes = source_path.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    source_instance_id = _opaque("sourceInstanceEngagementLedger", {"owner_ref": owner_ref})
    document = json.loads(source_bytes)
    if not isinstance(document, dict):
        return EngagementLedgerClassificationV1(
            source_instance_id=source_instance_id,
            source_sha256=source_sha256,
            enumeration_complete=False,
            engagement_row_count=0,
            non_project_row_ids=(),
            unclassified_row_ids=(_opaque("engagementUnclassifiedRow", {"owner_ref": owner_ref, "kind": "document"}),),
        )

    non_project_row_ids: list[str] = []
    unclassified_row_ids: list[str] = []
    documentation = document.get("_doc")
    if isinstance(documentation, str) and documentation.strip():
        non_project_row_ids.append(_opaque("engagementNonProjectRow", {"owner_ref": owner_ref, "key": "_doc"}))
    else:
        unclassified_row_ids.append(_opaque("engagementUnclassifiedRow", {"owner_ref": owner_ref, "key": "_doc"}))
    for key in sorted(set(document) - EXPECTED_TOP_LEVEL_KEYS):
        unclassified_row_ids.append(
            _opaque(
                "engagementUnclassifiedRow",
                {"owner_ref": owner_ref, "top_level_key": str(key)},
            )
        )

    engagements = document.get("engagements")
    if not isinstance(engagements, list):
        unclassified_row_ids.append(
            _opaque(
                "engagementUnclassifiedRow",
                {"owner_ref": owner_ref, "key": "engagements", "kind": "not-list"},
            )
        )
        engagement_row_count = 0
    else:
        engagement_row_count = len(engagements)
        row_digests = [_digest_payload(row) for row in engagements]
        for row_digest, count in sorted(Counter(row_digests).items()):
            unclassified_row_ids.append(
                _opaque(
                    "engagementUnclassifiedRow",
                    {
                        "owner_ref": owner_ref,
                        "row_sha256": row_digest,
                        "duplicate_count": count,
                        "reason": "engagement-row-schema-unregistered",
                    },
                )
            )

    non_project = tuple(sorted(set(non_project_row_ids)))
    unclassified = tuple(sorted(set(unclassified_row_ids)))
    return EngagementLedgerClassificationV1(
        source_instance_id=source_instance_id,
        source_sha256=source_sha256,
        enumeration_complete=not unclassified,
        engagement_row_count=engagement_row_count,
        non_project_row_ids=non_project,
        unclassified_row_ids=unclassified,
    )


def enumerate_engagement_ledger(
    *,
    dimension: Dimension,
    context: EngagementLedgerContextV1,
    source_path: Path,
) -> dict[str, Any]:
    """Return one strict universe fragment for the requested dimension."""

    if context.dimension != dimension:
        raise ValueError("requested dimension does not match the enumerator context")
    classification = classify_engagement_ledger(source_path, owner_ref=context.owner_ref)
    receipt_ref = _opaque(
        f"engagementLedger{dimension.title()}Receipt",
        {
            "dimension": dimension,
            "source_sha256": classification.source_sha256,
            "frozen_wave_sha256": context.frozen_wave_sha256,
            "engagement_row_count": classification.engagement_row_count,
            "non_project_row_ids": classification.non_project_row_ids,
            "unclassified_row_ids": classification.unclassified_row_ids,
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
                        "engagementLedgerSourceReceipt",
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
                    required_project_ids=(),
                    projects=(),
                    non_project_row_ids=classification.non_project_row_ids,
                    unclassified_row_ids=classification.unclassified_row_ids,
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
                    required_collaborator_ids=(),
                    collaborators=(),
                    reference_only_identity_ids=(),
                    non_project_row_ids=classification.non_project_row_ids,
                    unclassified_row_ids=classification.unclassified_row_ids,
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
        context = EngagementLedgerContextV1.model_validate_json(raw_context)
        payload = enumerate_engagement_ledger(
            dimension=arguments.dimension,
            context=context,
            source_path=repository_root / OWNER_REF,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(type(exc).__name__, file=sys.stderr)
        return 1
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0
