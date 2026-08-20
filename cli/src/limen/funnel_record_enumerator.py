"""Privacy-safe enumeration of source-owned conversion-funnel records."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import rfc8785
from pydantic import Field, field_validator, model_validator

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

SOURCE_KIND: Literal["funnel_records"] = "funnel_records"
OWNER_REF: Literal["institutio/governance/prima-materia-funnel-sources.json"] = "institutio/governance/prima-materia-funnel-sources.json"
CONTEXT_SCHEMA: Literal["limen.universe_enumerator_context.v1"] = "limen.universe_enumerator_context.v1"
MANIFEST_SCHEMA: Literal["limen.funnel_source_manifest.v1"] = "limen.funnel_source_manifest.v1"


def _validate_digest(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("digest must be lowercase SHA-256")
    return value


def _digest_payload(value: Any) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _opaque(prefix: str, value: Any) -> str:
    return f"{prefix}{_digest_payload(value)[:24]}"


def _relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or "\x00" in value
        or path.is_absolute()
        or "." in path.parts
        or ".." in path.parts
        or str(path) != value
    ):
        raise ValueError("funnel source paths must be normalized repository-relative paths")
    return value


class FunnelRecordContextV1(PrimaMateriaModel):
    context_schema: Literal["limen.universe_enumerator_context.v1"] = Field(
        default=CONTEXT_SCHEMA,
        alias="schema",
    )
    dimension: Dimension
    source_kind: Literal["funnel_records"] = SOURCE_KIND
    owner_ref: Literal["institutio/governance/prima-materia-funnel-sources.json"] = OWNER_REF
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


class FunnelSourceSpecV1(PrimaMateriaModel):
    source_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    path: str
    format: Literal["json", "jsonl"]
    owner_ref: str = Field(min_length=1, max_length=256)
    max_bytes: int = Field(ge=1024, le=64 * 1024 * 1024)
    max_rows: int = Field(ge=1, le=100_000)

    _paths = field_validator("path", "owner_ref")(_relative_path)


class FunnelSourceManifestV1(PrimaMateriaModel):
    schema_version: Literal["limen.funnel_source_manifest.v1"] = MANIFEST_SCHEMA
    manifest_id: str = Field(min_length=16, max_length=128)
    sources: tuple[FunnelSourceSpecV1, ...] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def source_identities_are_unique(self) -> FunnelSourceManifestV1:
        source_ids = tuple(source.source_id for source in self.sources)
        paths = tuple(source.path for source in self.sources)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("funnel source identities must be unique")
        if len(paths) != len(set(paths)):
            raise ValueError("funnel source paths must be unique")
        return self


class FunnelSourceClassificationV1(PrimaMateriaModel):
    source_instance_id: str
    source_sha256: str | None = None
    available: bool
    enumeration_complete: bool
    row_count: int = Field(ge=0)
    non_project_row_ids: tuple[str, ...]
    unclassified_row_ids: tuple[str, ...]


class FunnelRecordClassificationV1(PrimaMateriaModel):
    manifest_sha256: str
    source_instances: tuple[FunnelSourceClassificationV1, ...]

    _manifest_digest = field_validator("manifest_sha256")(_validate_digest)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _unavailable_classification(source: FunnelSourceSpecV1, reason: str) -> FunnelSourceClassificationV1:
    source_instance_id = _opaque("sourceInstanceFunnelRecord", {"source_id": source.source_id})
    return FunnelSourceClassificationV1(
        source_instance_id=source_instance_id,
        available=False,
        enumeration_complete=False,
        row_count=0,
        non_project_row_ids=(),
        unclassified_row_ids=(
            _opaque(
                "funnelUnclassifiedRow",
                {"source_id": source.source_id, "reason": reason},
            ),
        ),
    )


def _classify_json_rows(
    source: FunnelSourceSpecV1,
    source_bytes: bytes,
) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    try:
        document = json.loads(source_bytes)
    except (UnicodeError, json.JSONDecodeError):
        return (
            1,
            (),
            (
                _opaque(
                    "funnelUnclassifiedRow",
                    {
                        "source_id": source.source_id,
                        "reason": "unparseable-json",
                        "bytes_sha256": hashlib.sha256(source_bytes).hexdigest(),
                    },
                ),
            ),
        )

    if isinstance(document, dict):
        rows = tuple(sorted(document.items()))
    elif isinstance(document, list):
        rows = tuple(enumerate(document))
    else:
        rows = (("$document", document),)
    if not rows:
        return (
            0,
            (),
            (
                _opaque(
                    "funnelUnclassifiedRow",
                    {"source_id": source.source_id, "reason": "empty-document"},
                ),
            ),
        )
    if len(rows) > source.max_rows:
        return (
            len(rows),
            (),
            (
                _opaque(
                    "funnelUnclassifiedRow",
                    {
                        "source_id": source.source_id,
                        "reason": "row-limit",
                        "row_count": len(rows),
                    },
                ),
            ),
        )

    non_project: list[str] = []
    unclassified: list[str] = []
    for key, value in rows:
        row = {"source_id": source.source_id, "key": key, "value": value}
        if key == "_doc" and isinstance(value, str) and value.strip():
            non_project.append(_opaque("funnelNonProjectRow", row))
        else:
            unclassified.append(_opaque("funnelUnclassifiedRow", row))
    return len(rows), tuple(sorted(non_project)), tuple(sorted(unclassified))


def _classify_jsonl_rows(
    source: FunnelSourceSpecV1,
    source_bytes: bytes,
) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    lines = source_bytes.splitlines()
    if not lines:
        return (
            0,
            (),
            (
                _opaque(
                    "funnelUnclassifiedRow",
                    {"source_id": source.source_id, "reason": "empty-document"},
                ),
            ),
        )
    if len(lines) > source.max_rows:
        return (
            len(lines),
            (),
            (
                _opaque(
                    "funnelUnclassifiedRow",
                    {
                        "source_id": source.source_id,
                        "reason": "row-limit",
                        "row_count": len(lines),
                    },
                ),
            ),
        )

    blank_count = 0
    record_digests: list[str] = []
    for line in lines:
        if not line.strip():
            blank_count += 1
            continue
        try:
            value = json.loads(line)
            record_digests.append(_digest_payload(value))
        except (UnicodeError, json.JSONDecodeError):
            record_digests.append(hashlib.sha256(line).hexdigest())
    non_project = (
        (
            _opaque(
                "funnelNonProjectRow",
                {
                    "source_id": source.source_id,
                    "kind": "blank-line",
                    "count": blank_count,
                },
            ),
        )
        if blank_count
        else ()
    )
    unclassified = tuple(
        sorted(
            _opaque(
                "funnelUnclassifiedRow",
                {
                    "source_id": source.source_id,
                    "record_sha256": row_digest,
                    "duplicate_count": count,
                },
            )
            for row_digest, count in Counter(record_digests).items()
        )
    )
    return len(lines), non_project, unclassified


def _classify_source(
    source: FunnelSourceSpecV1,
    *,
    repository_root: Path,
) -> FunnelSourceClassificationV1:
    source_instance_id = _opaque("sourceInstanceFunnelRecord", {"source_id": source.source_id})
    candidate = repository_root / source.path
    if candidate.is_symlink():
        return _unavailable_classification(source, "symlink")
    resolved = candidate.resolve()
    if resolved.parent != repository_root and repository_root not in resolved.parents:
        return _unavailable_classification(source, "path-escape")
    if not resolved.exists():
        return _unavailable_classification(source, "missing")
    if not resolved.is_file():
        return _unavailable_classification(source, "not-regular-file")

    source_sha256 = _hash_file(resolved)
    size = resolved.stat().st_size
    if size > source.max_bytes:
        return FunnelSourceClassificationV1(
            source_instance_id=source_instance_id,
            source_sha256=source_sha256,
            available=True,
            enumeration_complete=False,
            row_count=0,
            non_project_row_ids=(),
            unclassified_row_ids=(
                _opaque(
                    "funnelUnclassifiedRow",
                    {
                        "source_id": source.source_id,
                        "reason": "byte-limit",
                        "byte_count": size,
                        "source_sha256": source_sha256,
                    },
                ),
            ),
        )

    source_bytes = resolved.read_bytes()
    classifier = _classify_json_rows if source.format == "json" else _classify_jsonl_rows
    row_count, non_project, unclassified = classifier(source, source_bytes)
    return FunnelSourceClassificationV1(
        source_instance_id=source_instance_id,
        source_sha256=source_sha256,
        available=True,
        enumeration_complete=not unclassified,
        row_count=row_count,
        non_project_row_ids=non_project,
        unclassified_row_ids=unclassified,
    )


def classify_funnel_records(
    manifest_path: Path,
    *,
    repository_root: Path,
) -> FunnelRecordClassificationV1:
    manifest_bytes = manifest_path.read_bytes()
    manifest = FunnelSourceManifestV1.model_validate_json(manifest_bytes)
    root = repository_root.resolve()
    classifications = tuple(
        sorted(
            (_classify_source(source, repository_root=root) for source in manifest.sources),
            key=lambda item: item.source_instance_id,
        )
    )
    return FunnelRecordClassificationV1(
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        source_instances=classifications,
    )


def enumerate_funnel_records(
    *,
    dimension: Dimension,
    context: FunnelRecordContextV1,
    manifest_path: Path,
    repository_root: Path,
) -> dict[str, Any]:
    if context.dimension != dimension:
        raise ValueError("requested dimension does not match the enumerator context")
    classification = classify_funnel_records(
        manifest_path,
        repository_root=repository_root,
    )
    receipt_ref = _opaque(
        f"funnelRecords{dimension.title()}Receipt",
        {
            "dimension": dimension,
            "manifest_sha256": classification.manifest_sha256,
            "frozen_wave_sha256": context.frozen_wave_sha256,
            "sources": tuple(
                {
                    "source_instance_id": item.source_instance_id,
                    "source_sha256": item.source_sha256,
                    "available": item.available,
                    "row_count": item.row_count,
                    "non_project_row_ids": item.non_project_row_ids,
                    "unclassified_row_ids": item.unclassified_row_ids,
                }
                for item in classification.source_instances
            ),
        },
    )
    observed_at = context.frozen_at.astimezone(UTC)
    enumeration_complete = all(item.enumeration_complete for item in classification.source_instances)
    fragment: UniverseCensusFragmentV1 | UniverseProjectFragmentV1 | UniverseCollaboratorFragmentV1
    if dimension == "census":
        fragment = UniverseCensusFragmentV1(
            source_kind=SOURCE_KIND,
            observed_at=observed_at,
            enumeration_complete=True,
            receipt_ref=receipt_ref,
            source_instances=tuple(
                UniverseSourceInstanceExpectationV1(
                    source_instance_id=item.source_instance_id,
                    source_kind=SOURCE_KIND,
                    owner_receipt_ref=_opaque(
                        "funnelSourceReceipt",
                        {
                            "source_instance_id": item.source_instance_id,
                            "source_sha256": item.source_sha256,
                            "available": item.available,
                            "manifest_sha256": classification.manifest_sha256,
                        },
                    ),
                )
                for item in classification.source_instances
            ),
        )
    elif dimension == "project":
        fragment = UniverseProjectFragmentV1(
            source_kind=SOURCE_KIND,
            observed_at=observed_at,
            enumeration_complete=enumeration_complete,
            receipt_ref=receipt_ref,
            instances=tuple(
                UniverseProjectInstanceFragmentV1(
                    source_instance_id=item.source_instance_id,
                    required_project_ids=(),
                    projects=(),
                    non_project_row_ids=item.non_project_row_ids,
                    unclassified_row_ids=item.unclassified_row_ids,
                )
                for item in classification.source_instances
            ),
        )
    else:
        fragment = UniverseCollaboratorFragmentV1(
            source_kind=SOURCE_KIND,
            observed_at=observed_at,
            enumeration_complete=enumeration_complete,
            receipt_ref=receipt_ref,
            instances=tuple(
                UniverseCollaboratorInstanceFragmentV1(
                    source_instance_id=item.source_instance_id,
                    required_collaborator_ids=(),
                    collaborators=(),
                    reference_only_identity_ids=(),
                    non_project_row_ids=item.non_project_row_ids,
                    unclassified_row_ids=item.unclassified_row_ids,
                )
                for item in classification.source_instances
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
        context = FunnelRecordContextV1.model_validate_json(raw_context)
        payload = enumerate_funnel_records(
            dimension=arguments.dimension,
            context=context,
            manifest_path=repository_root / OWNER_REF,
            repository_root=repository_root,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(type(exc).__name__, file=sys.stderr)
        return 1
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
