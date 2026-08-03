"""Versioned records shared by every Limen conductor and executor lane."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Literal

import rfc8785
from pydantic import BaseModel, ValidationInfo, ConfigDict, Field, field_validator, model_validator

from limen.work_loan import WorkLoanV1


_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")
_RESOURCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@*+-]{0,1023}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_OBJECT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_hash(value: Any) -> str:
    """Return the RFC 8785 SHA-256 used across Python and JavaScript."""

    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _identifier(value: str, field_name: str | None) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a bounded protocol identifier")
    return value


def _bounded_text(value: str, field_name: str | None) -> str:
    normalized = value.strip()
    if not normalized or "\x00" in normalized or len(normalized) > 8192:
        raise ValueError(f"{field_name} must be a non-empty bounded string")
    return normalized


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
    def validate_identifiers(cls, value: str, info: ValidationInfo) -> str:
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
    def validate_identifiers(cls, value: str, info: ValidationInfo) -> str:
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
    # Registration-time succession hint, never stored: names the exact session_id of a dead
    # predecessor whose worktree this session claims. The broker honors it only when the named
    # session currently owns the claimed worktree and the claimant's protection level is at
    # least the owner's; the client asserts it only after proving no foreign process is live
    # in the worktree (limen.conduct.liveness, fail-closed).
    supersedes: str | None = None

    @field_validator("session_id", "transport", "harvest_method")
    @classmethod
    def validate_identifiers(cls, value: str, info: ValidationInfo) -> str:
        return _identifier(value, info.field_name)

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, value: frozenset[str]) -> frozenset[str]:
        for capability in value:
            _identifier(capability, "capability")
        return value

    @field_validator("supersedes")
    @classmethod
    def validate_supersedes(cls, value: str | None, info: ValidationInfo) -> str | None:
        return None if value is None else _identifier(value, info.field_name)

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
    def validate_atoms(cls, value: frozenset[str], info: ValidationInfo) -> frozenset[str]:
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


class CampaignPacketV1(ProtocolModel):
    """Typed remediation context carried only by institutional campaigns."""

    schema_version: Literal["limen.campaign_packet.v1"] = "limen.campaign_packet.v1"
    campaign_id: str
    failed_predicate: str
    owner: str
    next_action: str
    output_ceiling_bytes: int = Field(gt=0, le=10_485_760)

    @field_validator("campaign_id")
    @classmethod
    def validate_campaign_id(cls, value: str) -> str:
        return _identifier(value, "campaign_id")

    @field_validator("failed_predicate", "owner", "next_action")
    @classmethod
    def validate_bounded_text(cls, value: str, info: ValidationInfo) -> str:
        return _bounded_text(value, info.field_name)


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
    # Optional at the schema boundary so old stored runs remain inspectable.
    # Admission is activated separately after producer adoption.
    work_loan: WorkLoanV1 | None = None
    campaign: CampaignPacketV1 | None = None
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
    def validate_work_identifiers(cls, value: str, info: ValidationInfo) -> str:
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
    def validate_contract_text(cls, value: str, info: ValidationInfo) -> str:
        return _bounded_text(value, info.field_name)

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
        if self.campaign is not None:
            if self.work_loan is None:
                raise ValueError("campaign work packets require a value/cost work loan")
            if not self.authority.actions:
                raise ValueError("campaign work packets require an explicit authority scope")
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
    def validate_identifiers(cls, value: str, info: ValidationInfo) -> str:
        return _identifier(value, info.field_name)

    @field_validator("provider_run_id")
    @classmethod
    def validate_provider_run_id(cls, value: str | None) -> str | None:
        return _identifier(value, "provider_run_id") if value else None

    @field_validator("provider_run_url", "detail")
    @classmethod
    def validate_bounded_text(cls, value: str | None, info: ValidationInfo) -> str | None:
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


class CampaignOutputEvidenceV1(ProtocolModel):
    """Content-free proof that one campaign result respected its output ceiling."""

    schema_version: Literal["limen.campaign_output_evidence.v1"] = "limen.campaign_output_evidence.v1"
    output_ceiling_bytes: int = Field(gt=0, le=10_485_760)
    bytes_emitted: int = Field(ge=0, le=10_485_760)
    lines_emitted: int = Field(default=0, ge=0, le=10_000_000)
    sha256: str
    truncated: bool = False

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("sha256 must be a lowercase SHA-256 digest")
        return value

    @model_validator(mode="after")
    def emitted_output_fits(self) -> "CampaignOutputEvidenceV1":
        if self.bytes_emitted > self.output_ceiling_bytes:
            raise ValueError("campaign output exceeds its declared ceiling")
        return self


class CampaignBlockerV1(ProtocolModel):
    """Owner-routable evidence for an exact campaign blocker."""

    schema_version: Literal["limen.campaign_blocker.v1"] = "limen.campaign_blocker.v1"
    owner: str
    failed_predicate: str
    next_action: str

    @field_validator("owner", "failed_predicate", "next_action")
    @classmethod
    def validate_bounded_text(cls, value: str, info: ValidationInfo) -> str:
        return _bounded_text(value, info.field_name)


class CampaignRelayReceiptV1(ProtocolModel):
    """One finite predecessor-to-successor launch stored in the Git common dir."""

    schema_version: Literal["limen.campaign_relay_receipt.v1"] = "limen.campaign_relay_receipt.v1"
    relay_id: str
    workstream: str
    predecessor_receipt_blob: str
    predecessor_contract_digest: str
    predecessor_deadline_epoch: int = Field(gt=0)
    exact_remote_main: str
    successor_slug: str
    successor_branch: str
    successor_session_id: str
    state: Literal[
        "reserved",
        "launching",
        "registered",
        "published",
        "ready",
        "failed",
        "indeterminate",
    ] = "reserved"
    attempts: Literal[0, 1] = 0
    controller_pid: int | None = Field(default=None, ge=1)
    controller_process_started: str | None = None
    remote_attempt_commit: str | None = None
    remote_attempt_token: str | None = None
    selected_agent: str | None = None
    selected_capabilities: tuple[str, ...] = ()
    launch_pid: int | None = Field(default=None, ge=1)
    launch_process_started: str | None = None
    registration_response_sha256: str | None = None
    activation_response_sha256: str | None = None
    publication_commit: str | None = None
    publication_parent: str | None = None
    publication_receipt_blob: str | None = None
    startup_stdout_sha256: str | None = None
    startup_stdout_bytes: int | None = Field(default=None, ge=0, le=65_537)
    startup_stdout_truncated: bool = False
    startup_stderr_sha256: str | None = None
    startup_stderr_bytes: int | None = Field(default=None, ge=0, le=65_537)
    startup_stderr_truncated: bool = False
    terminal_code: str | None = None

    @field_validator(
        "relay_id",
        "predecessor_contract_digest",
        "registration_response_sha256",
        "activation_response_sha256",
        "remote_attempt_token",
        "startup_stdout_sha256",
        "startup_stderr_sha256",
    )
    @classmethod
    def validate_digests(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is not None and not _SHA256_RE.fullmatch(value):
            raise ValueError(f"{info.field_name} must be a lowercase SHA-256 digest")
        return value

    @field_validator(
        "predecessor_receipt_blob",
        "exact_remote_main",
        "remote_attempt_commit",
        "publication_commit",
        "publication_parent",
        "publication_receipt_blob",
    )
    @classmethod
    def validate_git_objects(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is not None and not _GIT_OBJECT_RE.fullmatch(value):
            raise ValueError(f"{info.field_name} must be a lowercase Git object id")
        return value

    @field_validator(
        "workstream",
        "successor_slug",
        "successor_branch",
        "successor_session_id",
        "selected_agent",
        "terminal_code",
    )
    @classmethod
    def validate_identifiers(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _identifier(value, info.field_name) if value is not None else None

    @field_validator("selected_capabilities")
    @classmethod
    def validate_selected_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_identifier(capability, "selected_capability") for capability in value)
        if normalized != tuple(sorted(set(normalized))):
            raise ValueError("selected_capabilities must be sorted and unique")
        return normalized

    @field_validator("controller_process_started", "launch_process_started")
    @classmethod
    def validate_process_started(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized or len(normalized) > 256 or "\x00" in normalized:
            raise ValueError("process-start evidence must be bounded identity text")
        return normalized

    @model_validator(mode="after")
    def validate_lifecycle(self) -> CampaignRelayReceiptV1:
        proof_fields = (
            self.selected_agent,
            self.controller_pid,
            self.controller_process_started,
            self.remote_attempt_commit,
            self.remote_attempt_token,
            self.launch_pid,
            self.launch_process_started,
            self.registration_response_sha256,
            self.activation_response_sha256,
            self.publication_commit,
            self.publication_parent,
            self.publication_receipt_blob,
            self.startup_stdout_sha256,
            self.startup_stdout_bytes,
            self.startup_stderr_sha256,
            self.startup_stderr_bytes,
            self.terminal_code,
        )
        if self.state == "reserved":
            if self.attempts != 0 or self.selected_capabilities or any(value is not None for value in proof_fields):
                raise ValueError("reserved campaign relays cannot carry launch evidence")
            if self.startup_stdout_truncated or self.startup_stderr_truncated:
                raise ValueError("reserved campaign relays cannot carry output evidence")
            return self
        if self.attempts != 1:
            raise ValueError("a launched campaign relay must consume its sole attempt")
        if self.controller_pid is None or self.controller_process_started is None:
            raise ValueError("a launched campaign relay requires exact controller identity")
        if (self.remote_attempt_commit is None) != (self.remote_attempt_token is None):
            raise ValueError("campaign relay remote attempt evidence must be complete")
        if (
            self.launch_pid is not None or self.state in {"registered", "published", "ready"}
        ) and self.remote_attempt_commit is None:
            raise ValueError("provider launch evidence requires one durable remote attempt")
        if self.state in {"registered", "published", "ready"} and (
            self.selected_agent is None
            or self.launch_pid is None
            or self.launch_process_started is None
            or self.registration_response_sha256 is None
        ):
            raise ValueError("registered campaign relays require exact session and process evidence")
        if self.state in {"published", "ready"} and any(
            value is None
            for value in (
                self.publication_commit,
                self.publication_parent,
                self.publication_receipt_blob,
            )
        ):
            raise ValueError("published campaign relays require exact receipt commit evidence")
        if self.state == "ready" and any(
            value is None
            for value in (
                self.activation_response_sha256,
                self.startup_stdout_sha256,
                self.startup_stdout_bytes,
                self.startup_stderr_sha256,
                self.startup_stderr_bytes,
            )
        ):
            raise ValueError("ready campaign relays require bounded startup-output evidence")
        if self.state == "ready" and (self.startup_stdout_truncated or self.startup_stderr_truncated):
            raise ValueError("ready campaign relays require complete startup-output evidence")
        if self.state in {"failed", "indeterminate"}:
            if self.terminal_code is None:
                raise ValueError("terminal campaign relays require a stable terminal code")
        elif self.terminal_code is not None:
            raise ValueError("non-terminal campaign relays cannot carry a terminal code")
        return self


class CampaignReceiptV1(ProtocolModel):
    """Campaign-only value, output, blocker, and succession evidence."""

    schema_version: Literal["limen.campaign_receipt.v1"] = "limen.campaign_receipt.v1"
    campaign_id: str
    actual_value: float = Field(ge=0, le=1_000_000_000_000)
    value_unit: str
    output: CampaignOutputEvidenceV1
    blocker: CampaignBlockerV1 | None = None
    successor_capsule: str | None = None
    boundary: Literal["continue", "switch", "wait_relay", "settled", "invalid"]

    @field_validator("campaign_id", "value_unit")
    @classmethod
    def validate_identifiers(cls, value: str, info: ValidationInfo) -> str:
        return _identifier(value, info.field_name)

    @field_validator("actual_value", mode="before")
    @classmethod
    def reject_boolean_value(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("actual_value must be numeric, not boolean")
        return value

    @field_validator("successor_capsule")
    @classmethod
    def validate_successor_capsule(cls, value: str | None) -> str | None:
        return _bounded_text(value, "successor_capsule") if value is not None else None

    @model_validator(mode="after")
    def validate_boundary(self) -> "CampaignReceiptV1":
        if self.boundary in {"switch", "wait_relay"} and self.successor_capsule is None:
            raise ValueError(f"{self.boundary} campaign receipts require a successor capsule")
        if self.boundary == "settled" and self.successor_capsule is not None:
            raise ValueError("settled campaign receipts cannot name a successor capsule")
        return self


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
    campaign: CampaignReceiptV1 | None = None
    outcome: Literal["succeeded", "failed", "blocked", "cancelled", "partial"]
    completed_at: datetime = Field(default_factory=utc_now)

    @field_validator("receipt_id", "run_id", "lease_id")
    @classmethod
    def validate_identifiers(cls, value: str, info: ValidationInfo) -> str:
        return _identifier(value, info.field_name)

    @model_validator(mode="after")
    def validate_campaign_outcome(self) -> "RunReceiptV1":
        if (
            self.campaign is not None
            and self.campaign.boundary == "settled"
            and (self.outcome != "succeeded" or self.predicate.exit_code != 0)
        ):
            raise ValueError("settled campaign receipts require a successful outcome and predicate")
        if self.campaign is not None and self.outcome == "blocked" and self.campaign.blocker is None:
            raise ValueError("blocked campaign receipts require precise blocker ownership")
        return self
