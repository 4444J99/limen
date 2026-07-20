"""Versioned records shared by every Limen conductor and executor lane."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import rfc8785


_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")
_RESOURCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@*+-]{0,1023}$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_hash(value: Any) -> str:
    """Return the RFC 8785 SHA-256 used across Python and JavaScript."""

    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _identifier(value: str, field_name: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a bounded protocol identifier")
    return value


class ProtocolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentIdentityV1(ProtocolModel):
    schema_version: Literal["limen.agent_identity.v1"] = "limen.agent_identity.v1"
    agent: str
    surface: str
    session_id: str
    native_run_id: str | None = None
    provider_identity: str | None = None

    @field_validator("agent", "surface", "session_id")
    @classmethod
    def validate_identifiers(cls, value: str, info) -> str:
        return _identifier(value, info.field_name)


class ConductPrincipalV1(ProtocolModel):
    """Server-derived authority attached to one credential-wall bearer."""

    schema_version: Literal["limen.conduct_principal.v1"] = "limen.conduct_principal.v1"
    principal_id: str
    agent: str
    surface: str
    roles: frozenset[Literal["observer", "conductor", "executor", "compatibility"]]

    @field_validator("principal_id", "agent", "surface")
    @classmethod
    def validate_identifiers(cls, value: str, info) -> str:
        return _identifier(value, info.field_name)

    @model_validator(mode="after")
    def has_roles(self) -> "ConductPrincipalV1":
        if not self.roles:
            raise ValueError("conduct principal must have at least one role")
        return self


class ConductorSessionV1(ProtocolModel):
    schema_version: Literal["limen.conductor_session.v1"] = "limen.conductor_session.v1"
    session_id: str
    identity: AgentIdentityV1
    origin: Literal["direct", "dispatched", "relay"]
    native_session_id: str | None = None
    native_run_id: str | None = None
    worktree: str | None = None
    capabilities: frozenset[str] = Field(default_factory=frozenset)
    transport: str = "native"
    native_fanout: bool = False
    harvest_method: str = "receipt"
    concurrency: int = Field(default=1, ge=1, le=1024)
    meter: str | None = None
    quota_remaining: float | None = Field(default=None, ge=0)
    cost_per_run: float | None = Field(default=None, ge=0)
    receipt_quality: float = Field(default=0, ge=0, le=1)
    registered_at: datetime = Field(default_factory=utc_now)
    heartbeat_at: datetime = Field(default_factory=utc_now)
    human_protected: bool = False
    accepting_work: bool = True

    @field_validator("session_id", "transport", "harvest_method")
    @classmethod
    def validate_identifiers(cls, value: str, info) -> str:
        return _identifier(value, info.field_name)

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, value: frozenset[str]) -> frozenset[str]:
        for capability in value:
            _identifier(capability, "capability")
        return value

    @model_validator(mode="after")
    def identity_matches_session(self) -> "ConductorSessionV1":
        if self.identity.session_id != self.session_id:
            raise ValueError("identity.session_id must equal session_id")
        return self


class ResourceClaimV1(ProtocolModel):
    schema_version: Literal["limen.resource_claim.v1"] = "limen.resource_claim.v1"
    key: str
    mode: Literal["shared", "exclusive"] = "exclusive"

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if not _RESOURCE_RE.fullmatch(value):
            raise ValueError("resource key contains unsupported characters or is too long")
        return value.rstrip("/") or value


class AuthorityEnvelopeV1(ProtocolModel):
    schema_version: Literal["limen.authority_envelope.v1"] = "limen.authority_envelope.v1"
    actions: frozenset[str] = Field(default_factory=frozenset)
    repositories: frozenset[str] = Field(default_factory=frozenset)
    path_prefixes: frozenset[str] = Field(default_factory=frozenset)
    external_effects: frozenset[str] = Field(default_factory=frozenset)
    may_delegate: bool = True

    @field_validator("actions", "repositories", "external_effects")
    @classmethod
    def validate_atoms(cls, value: frozenset[str], info) -> frozenset[str]:
        for atom in value:
            if atom != "*":
                _identifier(atom, info.field_name)
        return value

    @field_validator("path_prefixes")
    @classmethod
    def validate_paths(cls, value: frozenset[str]) -> frozenset[str]:
        if any("\x00" in path or len(path) > 4096 for path in value):
            raise ValueError("path prefixes must be bounded and contain no NUL")
        return value


class SpendEnvelopeV1(ProtocolModel):
    schema_version: Literal["limen.spend_envelope.v1"] = "limen.spend_envelope.v1"
    unit: str = "runs"
    limit: int = Field(default=1, ge=0)
    reserve: int = Field(default=0, ge=0)

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        return _identifier(value, "unit")

    @model_validator(mode="after")
    def reserve_fits(self) -> "SpendEnvelopeV1":
        if self.reserve > self.limit:
            raise ValueError("spend reserve cannot exceed limit")
        return self


class RetryPolicyV1(ProtocolModel):
    schema_version: Literal["limen.retry_policy.v1"] = "limen.retry_policy.v1"
    max_attempts: int = Field(default=1, ge=1, le=100)
    transient_only: bool = True


class FanoutBoundsV1(ProtocolModel):
    schema_version: Literal["limen.fanout_bounds.v1"] = "limen.fanout_bounds.v1"
    max_children: int = Field(default=0, ge=0, le=10000)
    max_depth: int = Field(default=0, ge=0, le=64)


class WorkPacketV1(ProtocolModel):
    schema_version: Literal["limen.work_packet.v1"] = "limen.work_packet.v1"
    root_run_id: str | None = None
    parent_run_id: str | None = None
    work_id: str
    work_key: str
    intent: dict[str, Any]
    execution: dict[str, Any] = Field(default_factory=dict)
    intent_hash: str = ""
    execution_hash: str = ""
    initiator: AgentIdentityV1
    conductor: AgentIdentityV1
    preferred_agent: str | None = None
    required_capabilities: frozenset[str] = Field(default_factory=frozenset)
    resource_claims: tuple[ResourceClaimV1, ...] = ()
    predicate: str
    receipt_target: str
    authority: AuthorityEnvelopeV1
    deadline: datetime
    spend: SpendEnvelopeV1 = Field(default_factory=SpendEnvelopeV1)
    retry: RetryPolicyV1 = Field(default_factory=RetryPolicyV1)
    depth: int = Field(default=0, ge=0, le=64)
    fanout: FanoutBoundsV1 = Field(default_factory=FanoutBoundsV1)
    effect: Literal["read", "write", "external"] = "write"
    task_id: str | None = None

    @field_validator("work_id", "work_key")
    @classmethod
    def validate_work_identifiers(cls, value: str, info) -> str:
        return _identifier(value, info.field_name)

    @field_validator("preferred_agent")
    @classmethod
    def validate_preferred_agent(cls, value: str | None) -> str | None:
        return _identifier(value, "preferred_agent") if value else None

    @field_validator("required_capabilities")
    @classmethod
    def validate_required_capabilities(cls, value: frozenset[str]) -> frozenset[str]:
        for capability in value:
            _identifier(capability, "required_capability")
        return value

    @field_validator("predicate", "receipt_target")
    @classmethod
    def validate_contract_text(cls, value: str, info) -> str:
        if not value.strip() or len(value) > 8192 or "\x00" in value:
            raise ValueError(f"{info.field_name} must be a non-empty bounded string")
        return value

    @model_validator(mode="after")
    def validate_hashes_and_shape(self) -> "WorkPacketV1":
        expected_intent = canonical_hash(self.intent)
        expected_execution = canonical_hash(self.execution)
        if self.intent_hash and self.intent_hash != expected_intent:
            raise ValueError("intent_hash does not match canonical intent")
        if self.execution_hash and self.execution_hash != expected_execution:
            raise ValueError("execution_hash does not match canonical execution")
        object.__setattr__(self, "intent_hash", expected_intent)
        object.__setattr__(self, "execution_hash", expected_execution)
        if self.parent_run_id is None and self.depth != 0:
            raise ValueError("root work packet depth must be zero")
        if self.parent_run_id is not None and self.depth == 0:
            raise ValueError("child work packet depth must be positive")
        if self.effect == "external" and not self.authority.external_effects:
            raise ValueError("external work requires an explicit external-effect authority")
        return self


class LeaseV1(ProtocolModel):
    schema_version: Literal["limen.lease.v1"] = "limen.lease.v1"
    lease_id: str
    run_id: str
    executor: AgentIdentityV1
    executor_principal_id: str | None = None
    resources: tuple[ResourceClaimV1, ...]
    observed_heads: dict[str, str] = Field(default_factory=dict)
    generation: int = Field(ge=1)
    resource_generations: dict[str, int] = Field(default_factory=dict)
    capability_token_hash: str
    acquired_at: datetime
    heartbeat_at: datetime
    hard_deadline: datetime
    state: Literal["reserved", "active", "released", "expired", "fenced"] = "reserved"

    @field_validator("executor_principal_id")
    @classmethod
    def validate_executor_principal(cls, value: str | None) -> str | None:
        return _identifier(value, "executor_principal_id") if value else None


class ExecutorAttemptV1(ProtocolModel):
    """Keeper-owned identity and lifecycle for one provider launch attempt."""

    schema_version: Literal["limen.executor_attempt.v1"] = "limen.executor_attempt.v1"
    attempt_id: str
    run_id: str
    lease_id: str
    lease_generation: int = Field(ge=1)
    executor: AgentIdentityV1
    adapter: str
    provider_run_id: str | None = None
    provider_run_url: str | None = None
    status: Literal["launching", "submitted", "running", "succeeded", "failed", "blocked"]
    failure_class: Literal["transient", "permanent"] | None = None
    submitted_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    detail: str = ""

    @field_validator("attempt_id", "run_id", "lease_id", "adapter")
    @classmethod
    def validate_identifiers(cls, value: str, info) -> str:
        return _identifier(value, info.field_name)

    @field_validator("provider_run_id")
    @classmethod
    def validate_provider_run_id(cls, value: str | None) -> str | None:
        return _identifier(value, "provider_run_id") if value else None

    @field_validator("provider_run_url", "detail")
    @classmethod
    def validate_bounded_text(cls, value: str | None, info) -> str | None:
        if value is not None and ("\x00" in value or len(value) > 4096):
            raise ValueError(f"{info.field_name} must be bounded and contain no NUL")
        return value


class PredicateEvidenceV1(ProtocolModel):
    command: str
    exit_code: int
    summary: str = ""
    observed_at: datetime = Field(default_factory=utc_now)


class CheckEvidenceV1(ProtocolModel):
    name: str
    status: Literal["success", "failure", "pending", "skipped"]
    url: str | None = None
    head: str | None = None


class ReviewEvidenceV1(ProtocolModel):
    provider: str
    head: str
    disposition: Literal["approved", "commented", "changes_requested", "none"]
    unresolved_threads: int = Field(default=0, ge=0)
    fully_paginated: bool = False
    url: str | None = None


class RunReceiptV1(ProtocolModel):
    schema_version: Literal["limen.run_receipt.v1"] = "limen.run_receipt.v1"
    receipt_id: str
    run_id: str
    lease_id: str
    lease_generation: int = Field(ge=1)
    executor: AgentIdentityV1
    provider_identity: str | None = None
    observed_heads_before: dict[str, str] = Field(default_factory=dict)
    observed_heads_after: dict[str, str] = Field(default_factory=dict)
    changed_paths: tuple[str, ...] = ()
    provider_run_url: str | None = None
    predicate: PredicateEvidenceV1
    checks: tuple[CheckEvidenceV1, ...] = ()
    reviews: tuple[ReviewEvidenceV1, ...] = ()
    spend: dict[str, int | float | str] = Field(default_factory=dict)
    child_runs: tuple[str, ...] = ()
    outcome: Literal["succeeded", "failed", "blocked", "cancelled", "partial"]
    completed_at: datetime = Field(default_factory=utc_now)

    @field_validator("receipt_id", "run_id", "lease_id")
    @classmethod
    def validate_identifiers(cls, value: str, info) -> str:
        return _identifier(value, info.field_name)
