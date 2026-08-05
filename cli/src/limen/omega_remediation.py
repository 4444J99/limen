"""Typed remediation contracts for every strict-Omega rung."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from limen.conduct.models import AuthorityEnvelopeV1
from limen.intake import is_durable_receipt_target, is_executable_predicate
from limen.work_loan import WorkLoanV1

REGISTRY_SCHEMA = "limen.omega_remediation_registry.v1"
REMEDIATION_SCHEMA: Literal["limen.omega_remediation.v1"] = "limen.omega_remediation.v1"
CORE_SCHEMA = "limen.omega_rung_registry.v1"
SENSOR_SCHEMA = "limen.omega_sensor_rungs.v1"
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")


class OmegaRemediationError(ValueError):
    """Raised when a rung cannot be compiled to a complete remediation contract."""


def _bounded(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized or "\x00" in normalized or len(normalized) > 8192:
        raise ValueError(f"{field} must be a non-empty bounded string")
    return normalized


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class OmegaRungContractV1(_FrozenModel):
    id: str
    label: str
    tier: Literal["det", "live"]
    predicate: str

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _IDENTIFIER_RE.fullmatch(value):
            raise ValueError("rung id must be a bounded protocol identifier")
        return value

    @field_validator("label")
    @classmethod
    def validate_text(cls, value: str, info) -> str:
        return _bounded(value, info.field_name)

    @field_validator("predicate")
    @classmethod
    def validate_predicate(cls, value: str) -> str:
        normalized = _bounded(value, "predicate")
        if not is_executable_predicate(normalized):
            raise ValueError("predicate must be an executable command")
        return normalized


class OmegaRemediationDefaultsV1(_FrozenModel):
    authority: AuthorityEnvelopeV1
    effect: Literal["read", "write", "external"]
    output_ceiling_bytes: int = Field(gt=0, le=10_485_760)
    receipt_target: str
    required_capabilities: frozenset[str]
    work_loan: WorkLoanV1

    @field_validator("receipt_target")
    @classmethod
    def validate_receipt_target(cls, value: str) -> str:
        normalized = _bounded(value, "receipt_target")
        if not is_durable_receipt_target(normalized):
            raise ValueError("receipt_target must name a durable GitHub receipt or tracked Git path")
        return normalized

    @field_validator("required_capabilities")
    @classmethod
    def validate_capabilities(cls, value: frozenset[str]) -> frozenset[str]:
        if not value:
            raise ValueError("required_capabilities must not be empty")
        if any(not _IDENTIFIER_RE.fullmatch(capability) for capability in value):
            raise ValueError("required_capabilities contain an invalid identifier")
        return value

    @model_validator(mode="after")
    def authority_fits_effect(self) -> OmegaRemediationDefaultsV1:
        if self.effect not in self.authority.actions:
            raise ValueError("remediation effect must be present in authority.actions")
        if self.effect == "external" and not self.authority.external_effects:
            raise ValueError("external remediation requires explicit external-effect authority")
        if self.authority.may_delegate:
            raise ValueError("Omega remediation defaults must not delegate implicitly")
        return self


class OmegaRemediationEntryV1(_FrozenModel):
    id: str
    owner: str
    next_action: str

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _IDENTIFIER_RE.fullmatch(value):
            raise ValueError("rung id must be a bounded protocol identifier")
        return value

    @field_validator("owner", "next_action")
    @classmethod
    def validate_text(cls, value: str, info) -> str:
        return _bounded(value, info.field_name)


class OmegaRemediationRegistryV1(_FrozenModel):
    registry_schema: Literal["limen.omega_remediation_registry.v1"] = Field(alias="schema")
    defaults: OmegaRemediationDefaultsV1
    rungs: tuple[OmegaRemediationEntryV1, ...]

    @model_validator(mode="after")
    def unique_rungs(self) -> OmegaRemediationRegistryV1:
        ids = [rung.id for rung in self.rungs]
        if not ids:
            raise ValueError("Omega remediation registry is empty")
        if len(ids) != len(set(ids)):
            raise ValueError("Omega remediation registry contains duplicate rung ids")
        return self


class OmegaRemediationV1(_FrozenModel):
    schema_version: Literal["limen.omega_remediation.v1"] = REMEDIATION_SCHEMA
    id: str
    owner: str
    next_action: str
    predicate: str
    required_capabilities: frozenset[str]
    authority: AuthorityEnvelopeV1
    effect: Literal["read", "write", "external"]
    output_ceiling_bytes: int = Field(gt=0, le=10_485_760)
    receipt_target: str
    work_loan: WorkLoanV1

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _IDENTIFIER_RE.fullmatch(value):
            raise ValueError("rung id must be a bounded protocol identifier")
        return value

    @field_validator("owner", "next_action", "predicate", "receipt_target")
    @classmethod
    def validate_text(cls, value: str, info) -> str:
        return _bounded(value, info.field_name)

    @field_validator("predicate")
    @classmethod
    def validate_predicate(cls, value: str) -> str:
        if not is_executable_predicate(value):
            raise ValueError("predicate must be an executable command")
        return value

    @field_validator("receipt_target")
    @classmethod
    def validate_receipt_target(cls, value: str) -> str:
        if not is_durable_receipt_target(value):
            raise ValueError("receipt_target must name a durable GitHub receipt or tracked Git path")
        return value

    @field_validator("required_capabilities")
    @classmethod
    def validate_capabilities(cls, value: frozenset[str]) -> frozenset[str]:
        if not value or any(not _IDENTIFIER_RE.fullmatch(capability) for capability in value):
            raise ValueError("required_capabilities must contain bounded protocol identifiers")
        return value

    @model_validator(mode="after")
    def authority_is_attenuated(self) -> OmegaRemediationV1:
        if self.effect not in self.authority.actions:
            raise ValueError("remediation effect must be present in authority.actions")
        if self.effect == "external" and not self.authority.external_effects:
            raise ValueError("external remediation requires explicit external-effect authority")
        if self.authority.may_delegate:
            raise ValueError("Omega remediation must not delegate implicitly")
        if self.work_loan.owner_surface != self.owner:
            raise ValueError("work-loan owner_surface must equal the remediation owner")
        return self


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OmegaRemediationError(f"cannot read Omega remediation input {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise OmegaRemediationError(f"Omega remediation input must be an object: {path}")
    return payload


def _rung_contracts(payload: dict[str, Any], *, schema: str, predicate_field: str) -> tuple[OmegaRungContractV1, ...]:
    if payload.get("schema") != schema:
        raise OmegaRemediationError(f"unknown Omega rung schema: {payload.get('schema')!r}")
    raw_rungs = payload.get("rungs")
    if not isinstance(raw_rungs, list) or not raw_rungs:
        raise OmegaRemediationError("Omega rung registry is empty")
    try:
        rungs = tuple(
            OmegaRungContractV1(
                id=raw["id"],
                label=raw["label"],
                tier=raw["tier"],
                predicate=raw[predicate_field],
            )
            for raw in raw_rungs
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise OmegaRemediationError(f"invalid Omega rung contract: {exc}") from exc
    ids = [rung.id for rung in rungs]
    if len(ids) != len(set(ids)):
        raise OmegaRemediationError("duplicate Omega rung identity")
    return rungs


def discover_omega_rungs(
    root: Path,
    *,
    sensor_payload: dict[str, Any] | None = None,
) -> tuple[OmegaRungContractV1, ...]:
    root = root.resolve()
    core = _rung_contracts(
        _load_json(root / "institutio" / "governance" / "omega-core-rungs.json"),
        schema=CORE_SCHEMA,
        predicate_field="predicate",
    )
    if sensor_payload is None:
        result = subprocess.run(
            [sys.executable, str(root / "scripts" / "beat-sensors.py"), "--list-omega-json"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise OmegaRemediationError(
                f"Omega sensor discovery failed with exit {result.returncode}: {result.stderr[:1000]}"
            )
        try:
            sensor_payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise OmegaRemediationError(f"Omega sensor discovery returned invalid JSON: {exc}") from exc
    sensors = _rung_contracts(sensor_payload, schema=SENSOR_SCHEMA, predicate_field="command")
    combined = (*core, *sensors)
    ids = [rung.id for rung in combined]
    if len(ids) != len(set(ids)):
        raise OmegaRemediationError("duplicate Omega rung identity across core and sensor registries")
    return combined


def materialize_remediations(
    registry_payload: dict[str, Any],
    rungs: tuple[OmegaRungContractV1, ...],
) -> dict[str, OmegaRemediationV1]:
    try:
        registry = OmegaRemediationRegistryV1.model_validate(registry_payload)
    except ValueError as exc:
        raise OmegaRemediationError(f"invalid Omega remediation registry: {exc}") from exc
    expected = {rung.id for rung in rungs}
    actual = {entry.id for entry in registry.rungs}
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        raise OmegaRemediationError(
            f"Omega remediation registry identity mismatch: missing={missing}, unknown={unknown}"
        )
    entries = {entry.id: entry for entry in registry.rungs}
    defaults = registry.defaults
    materialized: dict[str, OmegaRemediationV1] = {}
    for rung in rungs:
        entry = entries[rung.id]
        loan_payload = defaults.work_loan.model_dump(mode="json")
        loan_payload["owner_surface"] = entry.owner
        materialized[rung.id] = OmegaRemediationV1(
            id=rung.id,
            owner=entry.owner,
            next_action=entry.next_action,
            predicate=rung.predicate,
            required_capabilities=defaults.required_capabilities,
            authority=defaults.authority,
            effect=defaults.effect,
            output_ceiling_bytes=defaults.output_ceiling_bytes,
            receipt_target=defaults.receipt_target,
            work_loan=WorkLoanV1.model_validate(loan_payload),
        )
    return materialized


def load_omega_remediations(
    root: Path,
    *,
    sensor_payload: dict[str, Any] | None = None,
) -> tuple[tuple[OmegaRungContractV1, ...], dict[str, OmegaRemediationV1]]:
    root = root.resolve()
    rungs = discover_omega_rungs(root, sensor_payload=sensor_payload)
    registry = _load_json(root / "institutio" / "governance" / "omega-remediations.json")
    return rungs, materialize_remediations(registry, rungs)


def remediation_payload(remediation: OmegaRemediationV1) -> dict[str, Any]:
    """Return stable JSON material even when registry sets contain multiple values."""

    payload = remediation.model_dump(mode="json")
    payload["required_capabilities"] = sorted(remediation.required_capabilities)
    authority = payload["authority"]
    authority["actions"] = sorted(remediation.authority.actions)
    authority["repositories"] = sorted(remediation.authority.repositories)
    authority["path_prefixes"] = sorted(remediation.authority.path_prefixes)
    authority["external_effects"] = sorted(remediation.authority.external_effects)
    return payload


def annotate_omega_stamp(
    payload: dict[str, Any],
    rungs: tuple[OmegaRungContractV1, ...],
    remediations: dict[str, OmegaRemediationV1],
) -> dict[str, Any]:
    rows = payload.get("rungs")
    if not isinstance(rows, list):
        raise OmegaRemediationError("Omega stamp rungs must be a list")
    expected_ids = [rung.id for rung in rungs]
    observed_ids = [str(row.get("id") or "") for row in rows if isinstance(row, dict)]
    if len(observed_ids) != len(rows) or observed_ids != expected_ids:
        raise OmegaRemediationError("Omega stamp rung identity differs from the remediation registry")
    annotated_rows = []
    for row in rows:
        if row.get("status") not in {"PASS", "FAIL", "SKIP"}:
            raise OmegaRemediationError(f"Omega stamp has an invalid status for {row.get('id')}")
        rung_id = str(row["id"])
        annotated_rows.append(
            {
                **row,
                "remediation": remediation_payload(remediations[rung_id]),
            }
        )
    return {**payload, "schema_version": 3, "rungs": annotated_rows}


def normalized_registry_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return order-independent registry material for Omega contract hashing."""

    registry = OmegaRemediationRegistryV1.model_validate(payload)
    defaults = registry.defaults.model_dump(mode="json")
    defaults["required_capabilities"] = sorted(registry.defaults.required_capabilities)
    authority = defaults["authority"]
    authority["actions"] = sorted(registry.defaults.authority.actions)
    authority["repositories"] = sorted(registry.defaults.authority.repositories)
    authority["path_prefixes"] = sorted(registry.defaults.authority.path_prefixes)
    authority["external_effects"] = sorted(registry.defaults.authority.external_effects)
    return {
        "schema": registry.registry_schema,
        "defaults": defaults,
        "rungs": [
            entry.model_dump(mode="json") for entry in sorted(registry.rungs, key=lambda candidate: candidate.id)
        ],
    }
