"""Privacy-safe enumeration of the tracked ORGANVM organ registry."""

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
import yaml
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

SOURCE_KIND: Literal["curated_registry"] = "curated_registry"
OWNER_REF: Literal["institutio/registry/organs.yaml"] = "institutio/registry/organs.yaml"
CONTEXT_SCHEMA: Literal["limen.universe_enumerator_context.v1"] = "limen.universe_enumerator_context.v1"
EXPECTED_TOP_LEVEL_KEYS = frozenset({"schema_version", "seeded_from", "organs", "officers"})


def _validate_digest(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("digest must be lowercase SHA-256")
    return value


def _digest_payload(value: Any) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _opaque(prefix: str, value: Any) -> str:
    return f"{prefix}{_digest_payload(value)[:24]}"


class CuratedRegistryContextV1(PrimaMateriaModel):
    context_schema: Literal["limen.universe_enumerator_context.v1"] = Field(
        default=CONTEXT_SCHEMA,
        alias="schema",
    )
    dimension: Dimension
    source_kind: Literal["curated_registry"] = SOURCE_KIND
    owner_ref: Literal["institutio/registry/organs.yaml"] = OWNER_REF
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


class CuratedRegistryClassificationV1(PrimaMateriaModel):
    source_instance_id: str
    source_sha256: str
    enumeration_complete: bool
    non_project_row_ids: tuple[str, ...]
    row_count: int = Field(ge=0)
    debt_count: int = Field(ge=0)


def _valid_name(value: Any) -> str | None:
    if isinstance(value, str) and value and value.strip() == value and "\x00" not in value:
        return value
    return None


def classify_curated_registry(source_path: Path, *, owner_ref: str = OWNER_REF) -> CuratedRegistryClassificationV1:
    """Classify organ and officer rows without exposing their names."""

    source_bytes = source_path.read_bytes()
    document = yaml.safe_load(source_bytes)
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    source_instance_id = _opaque("sourceInstanceCuratedRegistry", {"owner_ref": owner_ref})
    if not isinstance(document, dict):
        return CuratedRegistryClassificationV1(
            source_instance_id=source_instance_id,
            source_sha256=source_sha256,
            enumeration_complete=False,
            non_project_row_ids=(),
            row_count=0,
            debt_count=1,
        )

    debt_count = len(set(document) - EXPECTED_TOP_LEVEL_KEYS)
    row_ids: list[str] = []

    organs = document.get("organs")
    organ_names: list[str] = []
    if not isinstance(organs, list):
        debt_count += 1
        organs = []
    for row in organs:
        if not isinstance(row, dict):
            debt_count += 1
            continue
        name = _valid_name(row.get("name"))
        if name is None:
            debt_count += 1
            continue
        organ_names.append(name)
    duplicate_organs = {name for name, count in Counter(organ_names).items() if count > 1}
    debt_count += len(duplicate_organs)
    for name in sorted(set(organ_names) - duplicate_organs):
        row_ids.append(_opaque("curatedNonProjectRow", {"kind": "organ", "key": name}))

    officers = document.get("officers")
    if not isinstance(officers, dict):
        debt_count += 1
        officers = {}
    known_organs = set(organ_names) - duplicate_organs
    for raw_name, row in officers.items():
        name = _valid_name(raw_name)
        if name is None or not isinstance(row, dict):
            debt_count += 1
            continue
        memberships = row.get("organs")
        if (
            not isinstance(memberships, list)
            or any(_valid_name(member) is None for member in memberships)
            or len(memberships) != len(set(memberships))
            or not set(memberships).issubset(known_organs)
        ):
            debt_count += 1
            continue
        row_ids.append(_opaque("curatedNonProjectRow", {"kind": "officer", "key": name}))

    row_ids_tuple = tuple(sorted(row_ids))
    return CuratedRegistryClassificationV1(
        source_instance_id=source_instance_id,
        source_sha256=source_sha256,
        enumeration_complete=debt_count == 0,
        non_project_row_ids=row_ids_tuple,
        row_count=len(row_ids_tuple),
        debt_count=debt_count,
    )


def enumerate_curated_registry(
    *,
    dimension: Dimension,
    context: CuratedRegistryContextV1,
    source_path: Path,
) -> dict[str, Any]:
    """Return one strict universe fragment for the requested dimension."""

    if context.dimension != dimension:
        raise ValueError("requested dimension does not match the enumerator context")
    classification = classify_curated_registry(source_path, owner_ref=context.owner_ref)
    receipt_ref = _opaque(
        f"curatedRegistry{dimension.title()}Receipt",
        {
            "dimension": dimension,
            "source_sha256": classification.source_sha256,
            "frozen_wave_sha256": context.frozen_wave_sha256,
            "row_ids": classification.non_project_row_ids,
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
                        "curatedRegistrySourceReceipt",
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
        context = CuratedRegistryContextV1.model_validate_json(raw_context)
        payload = enumerate_curated_registry(
            dimension=arguments.dimension,
            context=context,
            source_path=repository_root / OWNER_REF,
        )
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        print(type(exc).__name__, file=sys.stderr)
        return 1
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0
