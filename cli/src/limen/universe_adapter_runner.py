"""Bounded, resumable execution of dynamically registered universe enumerators."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import selectors
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import rfc8785
from pydantic import Field, field_validator, model_validator

from limen.prima_materia import PrimaMateriaModel, UniverseSourceRegistryV1
from limen.universe_freezer import (
    SourceCollaboratorObservationV1,
    SourceProjectObservationV1,
    UniverseSourceCensusV1,
    UniverseSourceInstanceExpectationV1,
    UniverseSourceObservationV1,
)

RUN_SCHEMA: Literal["limen.prima_materia_universe_adapter_run.v1"] = "limen.prima_materia_universe_adapter_run.v1"
ENUMERATOR_REGISTRY_SCHEMA: Literal["limen.universe_enumerator_registry.v1"] = "limen.universe_enumerator_registry.v1"
MAX_CONTEXT_BYTES = 64 * 1024
Dimension = Literal["census", "project", "collaborator"]


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


def _digest_payload(value: Any) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def command_digest(command: tuple[str, ...]) -> str:
    return _digest_payload(list(command))


class UniverseEnumeratorSpecV1(PrimaMateriaModel):
    enumerator_ref: str
    dimension: Dimension
    command: tuple[str, ...] = Field(min_length=1, max_length=64)
    command_sha256: str
    input_files: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    optional_input_files: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    timeout_seconds: int = Field(ge=1, le=900)
    max_output_bytes: int = Field(ge=1024, le=16 * 1024 * 1024)
    requires_custody_receipt: bool = False

    _ref = field_validator("enumerator_ref")(_validate_key)
    _command_digest = field_validator("command_sha256")(_validate_digest)

    @model_validator(mode="after")
    def command_is_exact_and_shell_free(self) -> UniverseEnumeratorSpecV1:
        if any(not value or "\x00" in value for value in self.command):
            raise ValueError("enumerator command arguments must be nonempty and NUL-free")
        if self.command_sha256 != command_digest(self.command):
            raise ValueError("enumerator command digest does not match its exact argv")
        for label, values in (
            ("enumerator input files", self.input_files),
            ("enumerator optional input files", self.optional_input_files),
        ):
            if values != tuple(sorted(set(values))):
                raise ValueError(f"{label} must be sorted and unique")
        if set(self.input_files) & set(self.optional_input_files):
            raise ValueError("required and optional enumerator input files must not overlap")
        for value in (*self.input_files, *self.optional_input_files):
            path = PurePosixPath(value)
            if (
                not value
                or "\x00" in value
                or path.is_absolute()
                or "." in path.parts
                or ".." in path.parts
                or str(path) != value
            ):
                raise ValueError("enumerator input files must be normalized repository-relative paths")
        return self


class UniverseEnumeratorRegistryV1(PrimaMateriaModel):
    schema_version: Literal["limen.universe_enumerator_registry.v1"] = ENUMERATOR_REGISTRY_SCHEMA
    registry_id: str
    enumerators: tuple[UniverseEnumeratorSpecV1, ...] = Field(max_length=12_288)

    _registry = field_validator("registry_id")(_validate_opaque)

    @model_validator(mode="after")
    def references_are_unique(self) -> UniverseEnumeratorRegistryV1:
        references = tuple(item.enumerator_ref for item in self.enumerators)
        if len(references) != len(set(references)):
            raise ValueError("enumerator references must be unique")
        return self

    @property
    def by_ref(self) -> dict[str, UniverseEnumeratorSpecV1]:
        return {item.enumerator_ref: item for item in self.enumerators}

    @property
    def canonical_digest(self) -> str:
        payload = self.model_dump(mode="json")
        payload["enumerators"] = sorted(
            payload["enumerators"],
            key=lambda item: item["enumerator_ref"],
        )
        return _digest_payload(payload)


class UniverseCensusFragmentV1(PrimaMateriaModel):
    dimension: Literal["census"] = "census"
    source_kind: str
    observed_at: datetime
    enumeration_complete: bool
    receipt_ref: str
    source_instances: tuple[UniverseSourceInstanceExpectationV1, ...] = Field(
        min_length=1,
        max_length=100_000,
    )

    _kind = field_validator("source_kind")(_validate_key)
    _observed = field_validator("observed_at")(_validate_aware)
    _receipt = field_validator("receipt_ref")(_validate_key)

    @model_validator(mode="after")
    def instances_are_unique(self) -> UniverseCensusFragmentV1:
        identities = tuple(item.source_instance_id for item in self.source_instances)
        if len(identities) != len(set(identities)):
            raise ValueError("census fragment source instances must be unique")
        if any(item.source_kind != self.source_kind for item in self.source_instances):
            raise ValueError("census fragment instances must match its source kind")
        return self


class UniverseProjectInstanceFragmentV1(PrimaMateriaModel):
    source_instance_id: str
    required_project_ids: tuple[str, ...] = Field(max_length=100_000)
    projects: tuple[SourceProjectObservationV1, ...] = Field(max_length=100_000)
    non_project_row_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=1_000_000)
    unclassified_row_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=1_000_000)

    _instance = field_validator("source_instance_id")(_validate_opaque)

    @model_validator(mode="after")
    def row_dispositions_are_distinct(self) -> UniverseProjectInstanceFragmentV1:
        for label, values in (
            ("non-project rows", self.non_project_row_ids),
            ("unclassified rows", self.unclassified_row_ids),
        ):
            if values != tuple(sorted(values)) or len(values) != len(set(values)):
                raise ValueError(f"{label} must be sorted and unique")
        if set(self.non_project_row_ids) & set(self.unclassified_row_ids):
            raise ValueError("classified and unclassified row identities must not overlap")
        return self


class UniverseProjectFragmentV1(PrimaMateriaModel):
    dimension: Literal["project"] = "project"
    source_kind: str
    observed_at: datetime
    enumeration_complete: bool
    receipt_ref: str
    instances: tuple[UniverseProjectInstanceFragmentV1, ...] = Field(max_length=100_000)

    _kind = field_validator("source_kind")(_validate_key)
    _observed = field_validator("observed_at")(_validate_aware)
    _receipt = field_validator("receipt_ref")(_validate_key)

    @model_validator(mode="after")
    def instances_are_unique(self) -> UniverseProjectFragmentV1:
        identities = tuple(item.source_instance_id for item in self.instances)
        if len(identities) != len(set(identities)):
            raise ValueError("project fragment source instances must be unique")
        if self.enumeration_complete and any(item.unclassified_row_ids for item in self.instances):
            raise ValueError("complete project enumeration cannot retain unclassified rows")
        return self


class UniverseCollaboratorInstanceFragmentV1(PrimaMateriaModel):
    source_instance_id: str
    required_collaborator_ids: tuple[str, ...] = Field(max_length=100_000)
    collaborators: tuple[SourceCollaboratorObservationV1, ...] = Field(max_length=100_000)
    reference_only_identity_ids: tuple[str, ...] = Field(
        default_factory=tuple,
        max_length=100_000,
    )
    non_project_row_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=1_000_000)
    unclassified_row_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=1_000_000)

    _instance = field_validator("source_instance_id")(_validate_opaque)

    @model_validator(mode="after")
    def row_dispositions_are_distinct(self) -> UniverseCollaboratorInstanceFragmentV1:
        for label, values in (
            ("non-project rows", self.non_project_row_ids),
            ("unclassified rows", self.unclassified_row_ids),
        ):
            if values != tuple(sorted(values)) or len(values) != len(set(values)):
                raise ValueError(f"{label} must be sorted and unique")
        if set(self.non_project_row_ids) & set(self.unclassified_row_ids):
            raise ValueError("classified and unclassified row identities must not overlap")
        return self


class UniverseCollaboratorFragmentV1(PrimaMateriaModel):
    dimension: Literal["collaborator"] = "collaborator"
    source_kind: str
    observed_at: datetime
    enumeration_complete: bool
    receipt_ref: str
    instances: tuple[UniverseCollaboratorInstanceFragmentV1, ...] = Field(max_length=100_000)

    _kind = field_validator("source_kind")(_validate_key)
    _observed = field_validator("observed_at")(_validate_aware)
    _receipt = field_validator("receipt_ref")(_validate_key)

    @model_validator(mode="after")
    def instances_are_unique(self) -> UniverseCollaboratorFragmentV1:
        identities = tuple(item.source_instance_id for item in self.instances)
        if len(identities) != len(set(identities)):
            raise ValueError("collaborator fragment source instances must be unique")
        if self.enumeration_complete and any(item.unclassified_row_ids for item in self.instances):
            raise ValueError("complete collaborator enumeration cannot retain unclassified rows")
        return self


class EnumeratorCacheReceiptV1(PrimaMateriaModel):
    schema_version: Literal["limen.universe_enumerator_cache_receipt.v1"] = "limen.universe_enumerator_cache_receipt.v1"
    enumerator_ref: str
    input_sha256: str
    output_sha256: str
    output_payload: dict[str, Any]

    _ref = field_validator("enumerator_ref")(_validate_key)
    _digests = field_validator("input_sha256", "output_sha256")(_validate_digest)


class UniverseAdapterRunReceiptV1(PrimaMateriaModel):
    schema_version: Literal["limen.prima_materia_universe_adapter_run.v1"] = RUN_SCHEMA
    frozen_wave_sha256: str
    source_registry_sha256: str
    enumerator_registry_sha256: str
    census_sha256: str
    observation_sha256: tuple[str, ...]
    executed_enumerator_refs: tuple[str, ...]
    reused_enumerator_refs: tuple[str, ...]
    missing_enumerator_refs: tuple[str, ...]
    failed_enumerator_refs: tuple[str, ...]
    placeholder_source_instance_ids: tuple[str, ...]

    _digests = field_validator(
        "frozen_wave_sha256",
        "source_registry_sha256",
        "enumerator_registry_sha256",
        "census_sha256",
    )(_validate_digest)

    @model_validator(mode="after")
    def evidence_is_canonical(self) -> UniverseAdapterRunReceiptV1:
        for value in self.observation_sha256:
            _validate_digest(value)
        for label, values in (
            ("observation digests", self.observation_sha256),
            ("executed enumerators", self.executed_enumerator_refs),
            ("reused enumerators", self.reused_enumerator_refs),
            ("missing enumerators", self.missing_enumerator_refs),
            ("failed enumerators", self.failed_enumerator_refs),
            ("placeholder source instances", self.placeholder_source_instance_ids),
        ):
            if values != tuple(sorted(values)) or len(values) != len(set(values)):
                raise ValueError(f"{label} must be sorted and unique")
        return self


class UniverseAdapterRunV1(PrimaMateriaModel):
    census: UniverseSourceCensusV1
    observations: tuple[UniverseSourceObservationV1, ...]
    receipt: UniverseAdapterRunReceiptV1


def _kill_process(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()
    process.wait(timeout=5)


def _bounded_command(
    command: tuple[str, ...],
    context: bytes,
    *,
    timeout_seconds: int,
    max_output_bytes: int,
    cwd: Path | None = None,
) -> bytes:
    if len(context) > MAX_CONTEXT_BYTES:
        raise ValueError("enumerator input context exceeds the bounded protocol")
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        cwd=cwd,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    try:
        process.stdin.write(context)
        process.stdin.close()
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        stdout = bytearray()
        stderr_size = 0
        deadline = time.monotonic() + timeout_seconds
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _kill_process(process)
                raise TimeoutError("enumerator exceeded its timeout")
            events = selector.select(min(remaining, 0.25))
            if not events and process.poll() is not None:
                events = [(key, selectors.EVENT_READ) for key in tuple(selector.get_map().values())]
            for key, _ in events:
                chunk = os.read(key.fd, 65_536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if key.data == "stdout":
                    stdout.extend(chunk)
                else:
                    stderr_size += len(chunk)
                if len(stdout) + stderr_size > max_output_bytes:
                    _kill_process(process)
                    raise ValueError("enumerator exceeded its combined output limit")
        return_code = process.wait(timeout=max(1, int(deadline - time.monotonic()) + 1))
        if return_code != 0:
            raise ValueError("enumerator exited unsuccessfully")
        return bytes(stdout)
    finally:
        if process.poll() is None:
            _kill_process(process)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _input_file_digests(
    spec: UniverseEnumeratorSpecV1,
    *,
    root: Path,
) -> dict[str, str | None]:
    input_file_sha256: dict[str, str | None] = {}
    for relative, required in (
        *((value, True) for value in spec.input_files),
        *((value, False) for value in spec.optional_input_files),
    ):
        candidate = root / relative
        if candidate.is_symlink():
            raise ValueError("enumerator input files cannot be symlinks")
        resolved = candidate.resolve()
        if resolved.parent != root and root not in resolved.parents:
            raise ValueError("enumerator input file escaped the repository root")
        if not resolved.is_file():
            if required or resolved.exists():
                raise ValueError("enumerator input file is unavailable")
            input_file_sha256[relative] = None
        else:
            input_file_sha256[relative] = hashlib.sha256(resolved.read_bytes()).hexdigest()
    return input_file_sha256


def _run_one(
    *,
    spec: UniverseEnumeratorSpecV1,
    context: dict[str, Any],
    cache_dir: Path,
    repository_root: Path,
) -> tuple[dict[str, Any], bool]:
    root = repository_root.resolve()
    input_file_sha256 = _input_file_digests(spec, root=root)
    input_sha256 = _digest_payload(
        {
            "spec": spec.model_dump(mode="json"),
            "context": context,
            "input_file_sha256": input_file_sha256,
        }
    )
    cache_path = cache_dir / f"{hashlib.sha256(spec.enumerator_ref.encode()).hexdigest()}.json"
    if cache_path.is_file():
        try:
            cached = EnumeratorCacheReceiptV1.model_validate_json(cache_path.read_text(encoding="utf-8"))
            if (
                cached.enumerator_ref == spec.enumerator_ref
                and cached.input_sha256 == input_sha256
                and cached.output_sha256 == _digest_payload(cached.output_payload)
            ):
                if _input_file_digests(spec, root=root) != input_file_sha256:
                    raise ValueError("enumerator input files drifted during cache validation")
                return cached.output_payload, True
        except (OSError, UnicodeError, ValueError):
            pass
    output = _bounded_command(
        spec.command,
        json.dumps(context, separators=(",", ":"), sort_keys=True).encode(),
        timeout_seconds=spec.timeout_seconds,
        max_output_bytes=spec.max_output_bytes,
        cwd=root,
    )
    payload = json.loads(output)
    if not isinstance(payload, dict):
        raise TypeError("enumerator output must be one JSON object")
    if _input_file_digests(spec, root=root) != input_file_sha256:
        raise ValueError("enumerator input files drifted during execution")
    receipt = EnumeratorCacheReceiptV1(
        enumerator_ref=spec.enumerator_ref,
        input_sha256=input_sha256,
        output_sha256=_digest_payload(payload),
        output_payload=payload,
    )
    _atomic_json(cache_path, receipt.model_dump(mode="json"))
    return payload, False


def _placeholder(adapter_kind: str, enumerator_ref: str) -> UniverseSourceInstanceExpectationV1:
    digest = hashlib.sha256(f"{adapter_kind}:{enumerator_ref}".encode()).hexdigest()
    return UniverseSourceInstanceExpectationV1(
        source_instance_id=f"sourceInstanceMissing{digest[:24]}",
        source_kind=adapter_kind,
        owner_receipt_ref=f"missing-enumerator-{digest[:24]}",
    )


def run_universe_adapters(
    *,
    source_registry: UniverseSourceRegistryV1,
    enumerator_registry: UniverseEnumeratorRegistryV1,
    frozen_wave_sha256: str,
    frozen_at: datetime,
    cache_dir: Path,
    custody_receipt_sha256: str | None = None,
    repository_root: Path | None = None,
) -> UniverseAdapterRunV1:
    """Execute each registered dimension once and merge only census-bound pairs."""

    _validate_digest(frozen_wave_sha256)
    frozen_at = _validate_aware(frozen_at)
    repository_root = (repository_root or Path.cwd()).resolve()
    if custody_receipt_sha256 is not None:
        _validate_digest(custody_receipt_sha256)
    source_registry_sha256 = source_registry.canonical_digest
    enumerator_registry_sha256 = enumerator_registry.canonical_digest
    specs = enumerator_registry.by_ref
    executed: set[str] = set()
    reused: set[str] = set()
    missing: set[str] = set()
    failed: set[str] = set()
    placeholders: list[str] = []
    census_fragments: dict[str, UniverseCensusFragmentV1] = {}
    project_fragments: dict[str, UniverseProjectFragmentV1] = {}
    collaborator_fragments: dict[str, UniverseCollaboratorFragmentV1] = {}

    for adapter in sorted(source_registry.adapters, key=lambda item: item.source_kind):
        dimensions = (
            ("census", adapter.census_enumerator_ref, UniverseCensusFragmentV1),
            ("project", adapter.project_enumerator_ref, UniverseProjectFragmentV1),
            (
                "collaborator",
                adapter.collaborator_enumerator_ref,
                UniverseCollaboratorFragmentV1,
            ),
        )
        for dimension, enumerator_ref, fragment_model in dimensions:
            spec = specs.get(enumerator_ref)
            if spec is None or spec.dimension != dimension:
                missing.add(enumerator_ref)
                continue
            if spec.requires_custody_receipt and custody_receipt_sha256 is None:
                missing.add(enumerator_ref)
                continue
            context = {
                "schema": "limen.universe_enumerator_context.v1",
                "dimension": dimension,
                "source_kind": adapter.source_kind,
                "owner_ref": adapter.owner_ref,
                "completeness_predicate": adapter.completeness_predicate,
                "privacy_projection_ref": adapter.privacy_projection_ref,
                "frozen_wave_sha256": frozen_wave_sha256,
                "source_registry_sha256": source_registry_sha256,
                "frozen_at": frozen_at.isoformat(),
                "custody_receipt_sha256": custody_receipt_sha256,
            }
            try:
                payload, was_reused = _run_one(
                    spec=spec,
                    context=context,
                    cache_dir=cache_dir,
                    repository_root=repository_root,
                )
                fragment = fragment_model.model_validate(payload)
                if fragment.source_kind != adapter.source_kind:
                    raise ValueError("enumerator returned the wrong source kind")
                if fragment.observed_at > frozen_at:
                    raise ValueError("enumerator observation is newer than the frozen boundary")
                (reused if was_reused else executed).add(enumerator_ref)
                if dimension == "census":
                    assert isinstance(fragment, UniverseCensusFragmentV1)
                    census_fragments[adapter.source_kind] = fragment
                elif dimension == "project":
                    assert isinstance(fragment, UniverseProjectFragmentV1)
                    project_fragments[adapter.source_kind] = fragment
                else:
                    assert isinstance(fragment, UniverseCollaboratorFragmentV1)
                    collaborator_fragments[adapter.source_kind] = fragment
            except (
                AssertionError,
                Exception,
                OSError,
                RuntimeError,
                TimeoutError,
                TypeError,
                ValueError,
            ):
                failed.add(enumerator_ref)

    expectations: list[UniverseSourceInstanceExpectationV1] = []
    census_receipt_refs: list[str] = []
    census_complete = True
    for adapter in sorted(source_registry.adapters, key=lambda item: item.source_kind):
        fragment_census = census_fragments.get(adapter.source_kind)
        if fragment_census is None:
            placeholder = _placeholder(adapter.source_kind, adapter.census_enumerator_ref)
            expectations.append(placeholder)
            placeholders.append(placeholder.source_instance_id)
            census_complete = False
        else:
            expectations.extend(fragment_census.source_instances)
            census_receipt_refs.append(fragment_census.receipt_ref)
            census_complete = census_complete and fragment_census.enumeration_complete
    census_receipt_ref = (
        "censusReceipt"
        + hashlib.sha256(
            rfc8785.dumps(
                {
                    "receipts": sorted(census_receipt_refs),
                    "missing": sorted(missing | failed),
                }
            )
        ).hexdigest()[:24]
    )
    census = UniverseSourceCensusV1(
        census_id=f"universeCensus{hashlib.sha256(frozen_wave_sha256.encode()).hexdigest()[:24]}",
        frozen_at=frozen_at,
        frozen_wave_sha256=frozen_wave_sha256,
        source_registry_sha256=source_registry_sha256,
        enumeration_complete=(census_complete and not missing and not failed and not placeholders),
        census_receipt_ref=census_receipt_ref,
        source_instances=tuple(sorted(expectations, key=lambda item: item.source_instance_id)),
    )

    observations = []
    expected_by_kind: dict[str, set[str]] = {}
    for expectation in census.source_instances:
        expected_by_kind.setdefault(expectation.source_kind, set()).add(expectation.source_instance_id)
    for adapter in sorted(source_registry.adapters, key=lambda item: item.source_kind):
        project_fragment = project_fragments.get(adapter.source_kind)
        collaborator_fragment = collaborator_fragments.get(adapter.source_kind)
        if project_fragment is None or collaborator_fragment is None:
            continue
        projects = {item.source_instance_id: item for item in project_fragment.instances}
        collaborators = {item.source_instance_id: item for item in collaborator_fragment.instances}
        expected = expected_by_kind.get(adapter.source_kind, set())
        exact_instance_coverage = set(projects) == expected == set(collaborators)
        for source_instance_id in sorted(expected & set(projects) & set(collaborators)):
            project = projects[source_instance_id]
            collaborator = collaborators[source_instance_id]
            receipt_ref = (
                "enumerationReceipt"
                + hashlib.sha256(
                    f"{project_fragment.receipt_ref}:{collaborator_fragment.receipt_ref}".encode()
                ).hexdigest()[:24]
            )
            observations.append(
                UniverseSourceObservationV1(
                    source_instance_id=source_instance_id,
                    source_kind=adapter.source_kind,
                    frozen_wave_sha256=frozen_wave_sha256,
                    source_registry_sha256=source_registry_sha256,
                    observed_at=max(
                        project_fragment.observed_at,
                        collaborator_fragment.observed_at,
                    ),
                    enumeration_complete=(
                        exact_instance_coverage
                        and project_fragment.enumeration_complete
                        and collaborator_fragment.enumeration_complete
                    ),
                    enumeration_receipt_ref=receipt_ref,
                    required_project_ids=project.required_project_ids,
                    projects=project.projects,
                    required_collaborator_ids=collaborator.required_collaborator_ids,
                    collaborators=collaborator.collaborators,
                    reference_only_identity_ids=collaborator.reference_only_identity_ids,
                    non_project_row_ids=tuple(
                        sorted(set(project.non_project_row_ids) | set(collaborator.non_project_row_ids))
                    ),
                    unclassified_row_ids=tuple(
                        sorted(set(project.unclassified_row_ids) | set(collaborator.unclassified_row_ids))
                    ),
                )
            )
    observations_tuple = tuple(sorted(observations, key=lambda item: item.source_instance_id))
    observation_sha256 = tuple(sorted(_digest_payload(item.model_dump(mode="json")) for item in observations_tuple))
    receipt = UniverseAdapterRunReceiptV1(
        frozen_wave_sha256=frozen_wave_sha256,
        source_registry_sha256=source_registry_sha256,
        enumerator_registry_sha256=enumerator_registry_sha256,
        census_sha256=_digest_payload(census.model_dump(mode="json")),
        observation_sha256=observation_sha256,
        executed_enumerator_refs=tuple(sorted(executed)),
        reused_enumerator_refs=tuple(sorted(reused)),
        missing_enumerator_refs=tuple(sorted(missing)),
        failed_enumerator_refs=tuple(sorted(failed)),
        placeholder_source_instance_ids=tuple(sorted(placeholders)),
    )
    return UniverseAdapterRunV1(
        census=census,
        observations=observations_tuple,
        receipt=receipt,
    )


def _write_run(output_dir: Path, result: UniverseAdapterRunV1) -> None:
    _atomic_json(output_dir / "census.json", result.census.model_dump(mode="json"))
    for observation in result.observations:
        _atomic_json(
            output_dir / "observations" / f"{observation.source_instance_id}.json",
            observation.model_dump(mode="json"),
        )
    _atomic_json(
        output_dir / "run-receipt.json",
        result.receipt.model_dump(mode="json"),
    )


def parser(root: Path) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--source-registry",
        type=Path,
        default=root / "institutio" / "governance" / "prima-materia-universe-sources.json",
    )
    result.add_argument("--enumerator-registry", type=Path, required=True)
    result.add_argument("--frozen-wave-sha", required=True)
    result.add_argument("--frozen-at", required=True)
    result.add_argument("--cache-dir", type=Path, required=True)
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--custody-receipt-sha")
    return result


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    repository_root = root or Path(__file__).resolve().parents[3]
    arguments = parser(repository_root).parse_args(argv)
    try:
        source_registry = UniverseSourceRegistryV1.model_validate_json(
            arguments.source_registry.read_text(encoding="utf-8")
        )
        enumerator_registry = UniverseEnumeratorRegistryV1.model_validate_json(
            arguments.enumerator_registry.read_text(encoding="utf-8")
        )
        result = run_universe_adapters(
            source_registry=source_registry,
            enumerator_registry=enumerator_registry,
            frozen_wave_sha256=arguments.frozen_wave_sha,
            frozen_at=datetime.fromisoformat(arguments.frozen_at),
            cache_dir=arguments.cache_dir,
            custody_receipt_sha256=arguments.custody_receipt_sha,
            repository_root=repository_root,
        )
        _write_run(arguments.output_dir, result)
        passed = (
            result.census.enumeration_complete
            and not result.receipt.missing_enumerator_refs
            and not result.receipt.failed_enumerator_refs
            and len(result.observations) == len(result.census.source_instances)
            and all(item.enumeration_complete for item in result.observations)
        )
        summary = {
            "schema": RUN_SCHEMA,
            "passed": passed,
            "source_instance_count": len(result.census.source_instances),
            "observation_count": len(result.observations),
            "executed_count": len(result.receipt.executed_enumerator_refs),
            "reused_count": len(result.receipt.reused_enumerator_refs),
            "missing_enumerator_count": len(result.receipt.missing_enumerator_refs),
            "failed_enumerator_count": len(result.receipt.failed_enumerator_refs),
            "placeholder_count": len(result.receipt.placeholder_source_instance_ids),
            "census_sha256": result.receipt.census_sha256,
        }
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        summary = {
            "schema": RUN_SCHEMA,
            "passed": False,
            "reason": type(exc).__name__,
        }
    print(json.dumps(summary, separators=(",", ":"), sort_keys=True))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
