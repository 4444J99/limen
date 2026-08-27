"""Typed, effect-free contracts for universe recovery and remote-ref reaping.

Collectors own observations and effectors own mutations.  This module only
validates the receipts that connect them, so a census, an old branch name, or
prose metadata can never mint landing or deletion authority.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import UTC, datetime
from typing import Any, Literal

import rfc8785
from pydantic import Field, field_validator, model_validator

from limen.conduct.models import ProtocolModel
from limen.repository_identity import RepositoryIdentityV1


_HEX = frozenset("0123456789abcdef")
_PULL_REQUEST_KEY = re.compile(
    r"^github-repository:(?P<repository_id>[1-9][0-9]*)/"
    r"pull-request:(?P<pull_request>[1-9][0-9]*)@(?P<head_sha>[0-9a-f]{40}|[0-9a-f]{64})$"
)


def canonical_digest(value: Any) -> str:
    """Return the repository-wide RFC 8785 SHA-256 digest."""

    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", exclude={"signature"})
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _digest(value: str) -> str:
    if len(value) != 64 or any(character not in _HEX for character in value):
        raise ValueError("digest must be a lowercase SHA-256")
    return value


def _git_oid(value: str) -> str:
    if len(value) not in {40, 64} or any(character not in _HEX for character in value):
        raise ValueError("Git object identity must be a full lowercase SHA")
    return value


def _nonblank(value: str) -> str:
    normalized = value.strip()
    if not normalized or "\x00" in normalized or len(normalized) > 8192:
        raise ValueError("value must be bounded nonblank text")
    return normalized


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(UTC)


class CursorReceiptV1(ProtocolModel):
    schema_version: Literal["limen.universe_cursor_receipt.v1"] = "limen.universe_cursor_receipt.v1"
    surface: str
    total_count: int = Field(ge=0)
    observed_count: int = Field(ge=0)
    page_count: int = Field(ge=1)
    complete: bool
    errors: tuple[str, ...] = ()
    repository_identity: RepositoryIdentityV1 | None = None
    repository: str | None = None
    connection_kind: str | None = None
    page_cursor: str | None = None
    expected_total: int | None = Field(default=None, ge=0)
    observed_total: int | None = Field(default=None, ge=0)
    retry_class: Literal["none", "transient", "permanent", "corrupt"] = "none"
    attempt: int = Field(default=1, ge=1)
    source_generation: str | None = None

    _surface = field_validator("surface")(_nonblank)
    _optional_text = field_validator("repository", "connection_kind", "page_cursor")(
        lambda value: _nonblank(value) if value is not None else None
    )
    _source_generation = field_validator("source_generation")(
        lambda value: _digest(value) if value is not None else None
    )

    @model_validator(mode="after")
    def completeness_is_exact(self) -> "CursorReceiptV1":
        expected = self.total_count if self.expected_total is None else self.expected_total
        observed = self.observed_count if self.observed_total is None else self.observed_total
        if self.expected_total is not None and self.expected_total != self.total_count:
            raise ValueError("expected_total must match total_count")
        if self.observed_total is not None and self.observed_total != self.observed_count:
            raise ValueError("observed_total must match observed_count")
        if self.connection_kind is not None and self.connection_kind != self.surface:
            raise ValueError("connection_kind must match surface")
        if self.repository_identity is not None:
            if self.repository is None or not self.repository_identity.accepts(self.repository):
                raise ValueError("cursor repository must match its stable identity")
        elif self.repository is not None:
            raise ValueError("cursor repository requires a stable repository identity")
        exact = expected == observed and not self.errors
        if self.complete != exact:
            raise ValueError("cursor completeness must match counts and errors")
        if self.complete and self.page_cursor is not None:
            raise ValueError("complete cursor receipt cannot retain a page cursor")
        if self.retry_class in {"permanent", "corrupt"} and self.complete:
            raise ValueError("terminal cursor failure cannot claim completeness")
        return self


CustodyDisposition = Literal["paired_verified", "not_required_landed", "retained_source", "blocked"]
DeliveryDisposition = Literal[
    "exact_landed",
    "equivalent_landed",
    "restored_preserved",
    "superseded",
    "blocked",
    "open_pr",
    "livework",
    "active_human",
    "protected",
    "advanced_after_merge",
    "unknown",
]


class RefDispositionV2(ProtocolModel):
    """One repository-qualified ref observation bound to its exact tip."""

    schema_version: Literal["limen.ref_disposition.v2"] = "limen.ref_disposition.v2"
    key: str
    repository_identity: RepositoryIdentityV1
    repository: str
    ref: str
    tip: str
    default_ref: str
    default_tip: str
    default_generation: str
    commit_digest: str
    tree_digest: str | None = None
    patch_digest: str | None = None
    pull_requests: tuple[int, ...] = ()
    merge_shas: tuple[str, ...] = ()
    lane_protection: tuple[str, ...] = ()
    custody_disposition: CustodyDisposition
    custody_proof_digest: str
    delivery_disposition: DeliveryDisposition
    owner: str
    predicate: str
    receipt: str
    census_digest: str
    grace_satisfied_at: datetime | None = None
    expires_at: datetime | None = None

    _oids = field_validator("tip", "default_tip")(_git_oid)
    _digests = field_validator("default_generation", "commit_digest", "custody_proof_digest", "census_digest")(_digest)
    _optional_digests = field_validator("tree_digest", "patch_digest")(
        lambda value: _digest(value) if value is not None else None
    )
    _merge_shas = field_validator("merge_shas")(lambda values: tuple(_git_oid(value) for value in values))
    _text = field_validator("repository", "ref", "default_ref", "owner", "predicate", "receipt")(_nonblank)
    _expiry = field_validator("expires_at")(lambda value: _aware(value) if value is not None else None)
    _grace = field_validator("grace_satisfied_at")(lambda value: _aware(value) if value is not None else None)

    @model_validator(mode="after")
    def identity_and_proof_are_bound(self) -> "RefDispositionV2":
        expected_key = self.repository_identity.stable_key(f"{self.ref}@{self.tip}")
        if self.key != expected_key:
            raise ValueError("ref disposition key must be stable repository ID/ref@tip")
        if not self.repository_identity.accepts(self.repository):
            raise ValueError("repository coordinate is not canonical or a historical alias")
        if not self.ref.startswith("refs/") or not self.default_ref.startswith("refs/"):
            raise ValueError("ref names must be fully qualified")
        if self.ref == self.default_ref:
            raise ValueError("the repository default ref is never reap eligible")
        if self.delivery_disposition == "equivalent_landed" and not (self.tree_digest or self.patch_digest):
            raise ValueError("equivalent landing requires a tree or patch digest")
        if self.delivery_disposition in {"exact_landed", "equivalent_landed"} and self.grace_satisfied_at is None:
            raise ValueError("landed disposition requires an explicit grace-satisfied timestamp")
        if self.reap_eligible and not self.pull_requests:
            raise ValueError("reap-eligible disposition requires a named review lineage")
        return self

    @property
    def reap_eligible(self) -> bool:
        return bool(
            self.delivery_disposition == "exact_landed"
            and self.custody_disposition in {"paired_verified", "not_required_landed"}
            and not set(self.lane_protection) & {"active-human", "protected", "livework"}
        )

    @property
    def repository_id(self) -> int:
        """Compatibility accessor backed by the stable identity envelope."""

        return self.repository_identity.repository_id


class CustodyCopyV1(ProtocolModel):
    device_id_digest: str
    content_digest: str

    _digests = field_validator("device_id_digest", "content_digest")(_digest)


class CustodyProofV1(ProtocolModel):
    schema_version: Literal["limen.remote_reap_custody_proof.v1"] = "limen.remote_reap_custody_proof.v1"
    repository: str
    ref: str
    tip: str
    disposition: CustodyDisposition
    source_digest: str
    copies: tuple[CustodyCopyV1, ...] = ()
    restore_tested: bool
    verified_at: datetime
    predicate: str

    _text = field_validator("repository", "ref", "predicate")(_nonblank)
    _tip = field_validator("tip")(_git_oid)
    _source = field_validator("source_digest")(_digest)
    _verified = field_validator("verified_at")(_aware)

    @model_validator(mode="after")
    def proof_is_sufficient(self) -> "CustodyProofV1":
        if self.disposition == "paired_verified":
            devices = {copy.device_id_digest for copy in self.copies}
            contents = {copy.content_digest for copy in self.copies}
            if len(self.copies) < 2 or len(devices) < 2 or contents != {self.source_digest}:
                raise ValueError("paired custody requires two devices with identical verified content")
            if not self.restore_tested:
                raise ValueError("paired custody requires a successful restore test")
        elif self.disposition == "not_required_landed" and self.copies:
            raise ValueError("not-required landing custody cannot claim external copies")
        return self


ThreadDisposition = Literal["corrected", "rejected", "superseded", "pending"]


class ReviewThreadClosureV2(ProtocolModel):
    schema_version: Literal["limen.review_thread_closure.v2"] = "limen.review_thread_closure.v2"
    thread_id: str
    resolved: bool
    outdated: bool
    disposition: ThreadDisposition
    receipt: str | None = None
    comment_ids: tuple[str, ...] = ()

    _thread = field_validator("thread_id")(_nonblank)
    _receipt = field_validator("receipt")(lambda value: _nonblank(value) if value is not None else None)

    @model_validator(mode="after")
    def terminal_threads_have_evidence(self) -> "ReviewThreadClosureV2":
        if self.resolved:
            if self.disposition == "pending" or self.receipt is None:
                raise ValueError("resolved review thread requires a terminal disposition receipt")
        elif self.disposition != "pending":
            raise ValueError("unresolved review thread cannot claim a terminal disposition")
        return self


class ReviewLineageClosureV2(ProtocolModel):
    schema_version: Literal["limen.review_lineage_closure.v2"] = "limen.review_lineage_closure.v2"
    repository_identity: RepositoryIdentityV1
    repository: str
    pull_request: int = Field(gt=0)
    observed_at: datetime
    head_sha: str
    base_ref: str
    base_sha: str
    merge_sha: str | None = None
    review_decision: str | None = None
    checks_digest: str
    cursor_receipts: tuple[CursorReceiptV1, ...] = Field(min_length=1)
    threads: tuple[ReviewThreadClosureV2, ...] = ()
    unresolved_current: int = Field(ge=0)
    unresolved_outdated: int = Field(ge=0)
    lifecycle_stage: Literal[
        "open",
        "exact_head_verified",
        "review_clear",
        "merge_ready",
        "merged",
        "main_verified",
        "runtime_verified",
        "terminal",
    ]
    corrective_owner: str | None = None
    terminal: bool

    _repository = field_validator("repository", "base_ref")(_nonblank)
    _observed = field_validator("observed_at")(_aware)
    _oids = field_validator("head_sha", "base_sha")(_git_oid)
    _merge = field_validator("merge_sha")(lambda value: _git_oid(value) if value is not None else None)
    _checks = field_validator("checks_digest")(_digest)
    _owner = field_validator("corrective_owner")(lambda value: _nonblank(value) if value is not None else None)

    @model_validator(mode="after")
    def closure_matches_threads(self) -> "ReviewLineageClosureV2":
        if not self.repository_identity.accepts(self.repository):
            raise ValueError("repository coordinate is not canonical or a historical alias")
        current = sum(not thread.resolved and not thread.outdated for thread in self.threads)
        outdated = sum(not thread.resolved and thread.outdated for thread in self.threads)
        if (current, outdated) != (self.unresolved_current, self.unresolved_outdated):
            raise ValueError("unresolved review counts must match the complete thread set")
        complete = all(receipt.complete for receipt in self.cursor_receipts)
        expected = (
            complete
            and current == 0
            and outdated == 0
            and self.review_decision not in {"CHANGES_REQUESTED", "REVIEW_REQUIRED"}
        )
        if self.terminal != expected:
            raise ValueError("terminal review state requires complete cursors and zero unresolved threads")
        if self.lifecycle_stage in {"merged", "main_verified", "runtime_verified", "terminal"} and not expected:
            if not self.corrective_owner:
                raise ValueError("post-merge review debt requires a corrective owner")
        return self


class RecoveryDispositionReceiptV1(ProtocolModel):
    schema_version: Literal["limen.recovery_disposition_receipt.v1"] = "limen.recovery_disposition_receipt.v1"
    item_key: str
    item_kind: Literal["repository", "ref", "pull_request", "review_thread", "source_instance"]
    source_digest: str
    owner: str
    predicate: str
    receipt: str
    terminal_class: Literal[
        "exact_landed",
        "equivalent_landed",
        "restored_preserved",
        "superseded",
        "blocked",
        "owned_active",
        "unknown",
    ]

    _key = field_validator("item_key", "owner", "predicate", "receipt")(_nonblank)
    _source = field_validator("source_digest")(_digest)

    @model_validator(mode="after")
    def pull_request_keys_use_stable_repository_identity(self) -> "RecoveryDispositionReceiptV1":
        if self.item_kind == "pull_request" and _PULL_REQUEST_KEY.fullmatch(self.item_key) is None:
            raise ValueError("pull-request recovery keys must use github-repository:<id>/pull-request:<number>@<head>")
        return self


class SourceCoverageV1(ProtocolModel):
    schema_version: Literal["limen.recovery_source_coverage.v1"] = "limen.recovery_source_coverage.v1"
    source_instance_id: str
    source_kind: str
    enumeration_complete: bool
    owner: str
    predicate: str
    receipt: str
    blocker: str | None = None

    _required = field_validator("source_instance_id", "source_kind", "owner", "predicate", "receipt")(_nonblank)
    _blocker = field_validator("blocker")(lambda value: _nonblank(value) if value is not None else None)

    @model_validator(mode="after")
    def incomplete_source_is_owned(self) -> "SourceCoverageV1":
        if not self.enumeration_complete and not self.blocker:
            raise ValueError("incomplete source coverage requires a durable blocker")
        return self


ReapJournalState = Literal["planned", "verified", "applying", "completed", "crashed"]


class ReapJournalV1(ProtocolModel):
    schema_version: Literal["limen.remote_reap_journal.v1"] = "limen.remote_reap_journal.v1"
    effect_id: str
    capability_id: str | None = None
    repository: str
    ref: str
    expected_tip: str
    state: ReapJournalState
    updated_at: datetime
    detail: str

    _text = field_validator("effect_id", "repository", "ref", "detail")(_nonblank)
    _capability = field_validator("capability_id")(lambda value: _nonblank(value) if value is not None else None)
    _tip = field_validator("expected_tip")(_git_oid)
    _updated = field_validator("updated_at")(_aware)


class ReapPlanV1(ProtocolModel):
    schema_version: Literal["limen.remote_reap_plan.v1"] = "limen.remote_reap_plan.v1"
    plan_id: str
    repository: str
    repository_id: int | None = Field(default=None, gt=0)
    remote_url_digest: str
    ref: str
    live_tip: str
    disposition_digest: str
    custody_receipt_digest: str
    review_closure_digest: str
    grace_satisfied_at: datetime
    planned_at: datetime
    expires_at: datetime

    _text = field_validator("plan_id", "repository", "ref")(_nonblank)
    _digests = field_validator(
        "remote_url_digest", "disposition_digest", "custody_receipt_digest", "review_closure_digest"
    )(_digest)
    _tip = field_validator("live_tip")(_git_oid)
    _times = field_validator("grace_satisfied_at", "planned_at", "expires_at")(_aware)

    @model_validator(mode="after")
    def lifetime_is_ordered(self) -> "ReapPlanV1":
        if not self.grace_satisfied_at <= self.planned_at < self.expires_at:
            raise ValueError("reap plan timestamps are not ordered")
        if not self.ref.startswith("refs/heads/"):
            raise ValueError("remote reap plan requires a full branch ref")
        return self


class ReapCapabilityV1(ProtocolModel):
    schema_version: Literal["limen.remote_reap_capability.v1"] = "limen.remote_reap_capability.v1"
    capability_id: str
    plan_digest: str
    repository: str
    repository_id: int | None = Field(default=None, gt=0)
    remote_url_digest: str
    ref: str
    live_tip: str
    disposition_digest: str
    custody_receipt_digest: str
    review_closure_digest: str
    issued_at: datetime
    expires_at: datetime
    issued_by: str
    signature: str

    _text = field_validator("capability_id", "repository", "ref", "issued_by")(_nonblank)
    _digests = field_validator(
        "plan_digest", "remote_url_digest", "disposition_digest", "custody_receipt_digest", "review_closure_digest"
    )(_digest)
    _tip = field_validator("live_tip")(_git_oid)
    _times = field_validator("issued_at", "expires_at")(_aware)
    _signature = field_validator("signature")(_digest)

    @model_validator(mode="after")
    def lifetime_is_ordered(self) -> "ReapCapabilityV1":
        if self.issued_at >= self.expires_at:
            raise ValueError("reap capability must expire after issuance")
        return self


def issue_reap_capability(
    plan: ReapPlanV1,
    *,
    capability_id: str,
    issued_by: str,
    signing_material: bytes,
    issued_at: datetime,
) -> ReapCapabilityV1:
    """Issue a plan-bound capability; signing material remains keeper-owned."""

    signing_material = require_reap_capability_key(signing_material)

    unsigned = {
        "schema_version": "limen.remote_reap_capability.v1",
        "capability_id": capability_id,
        "plan_digest": canonical_digest(plan),
        "repository": plan.repository,
        "repository_id": plan.repository_id,
        "remote_url_digest": plan.remote_url_digest,
        "ref": plan.ref,
        "live_tip": plan.live_tip,
        "disposition_digest": plan.disposition_digest,
        "custody_receipt_digest": plan.custody_receipt_digest,
        "review_closure_digest": plan.review_closure_digest,
        "issued_at": _aware(issued_at).isoformat().replace("+00:00", "Z"),
        "expires_at": plan.expires_at.isoformat().replace("+00:00", "Z"),
        "issued_by": issued_by,
    }
    signature = hmac.new(signing_material, rfc8785.dumps(unsigned), hashlib.sha256).hexdigest()
    return ReapCapabilityV1.model_validate({**unsigned, "signature": signature})


def verify_reap_capability(
    capability: ReapCapabilityV1,
    *,
    plan: ReapPlanV1,
    signing_material: bytes,
    observed_at: datetime,
) -> None:
    signing_material = require_reap_capability_key(signing_material)
    payload = capability.model_dump(mode="json", exclude={"signature"})
    expected_signature = hmac.new(signing_material, rfc8785.dumps(payload), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, capability.signature):
        raise ValueError("reap capability signature is invalid")
    if canonical_digest(plan) != capability.plan_digest:
        raise ValueError("reap capability does not bind the supplied plan")
    for field in (
        "repository",
        "repository_id",
        "remote_url_digest",
        "ref",
        "live_tip",
        "disposition_digest",
        "custody_receipt_digest",
        "review_closure_digest",
    ):
        if getattr(capability, field) != getattr(plan, field):
            raise ValueError(f"reap capability {field} does not match the plan")
    if _aware(observed_at) >= capability.expires_at:
        raise ValueError("reap capability has expired")


def cas_delete_command(capability: ReapCapabilityV1) -> tuple[str, ...]:
    """The sole allowed delete shape: exact server-side force-with-lease CAS."""

    branch = capability.ref.removeprefix("refs/heads/")
    return (
        "git",
        "push",
        f"--force-with-lease={capability.ref}:{capability.live_tip}",
        "origin",
        f":refs/heads/{branch}",
    )


def require_reap_capability_key(signing_material: bytes) -> bytes:
    """Reject capability keys with less than 256 bits of encoded key material."""

    if not isinstance(signing_material, bytes) or len(signing_material) < 32:
        raise ValueError("reap capability key must contain at least 32 encoded bytes")
    return signing_material


def bound_reap_expiry(requested_expiry: datetime, evidence_expiry: datetime | None) -> datetime:
    """Clamp one capability plan to the lifetime of its underlying evidence."""

    requested = _aware(requested_expiry)
    if evidence_expiry is None:
        return requested
    return min(requested, _aware(evidence_expiry))


class UniverseRecoveryManifestV1(ProtocolModel):
    schema_version: Literal["limen.universe_recovery_manifest.v1"] = "limen.universe_recovery_manifest.v1"
    generated_at: datetime
    launch_digest: str
    census_digest: str
    cursor_receipts: tuple[CursorReceiptV1, ...] = Field(min_length=1)
    sources: tuple[SourceCoverageV1, ...] = Field(min_length=1)
    baseline_keys: tuple[str, ...] = Field(min_length=1)
    newcomer_keys: tuple[str, ...] = ()
    dispositions: tuple[RecoveryDispositionReceiptV1, ...]
    review_closures: tuple[ReviewLineageClosureV2, ...] = ()
    reap_journals: tuple[ReapJournalV1, ...] = ()

    _generated = field_validator("generated_at")(_aware)
    _digests = field_validator("launch_digest", "census_digest")(_digest)

    @model_validator(mode="after")
    def denominators_are_unique(self) -> "UniverseRecoveryManifestV1":
        expected = (*self.baseline_keys, *self.newcomer_keys)
        if len(expected) != len(set(expected)):
            raise ValueError("baseline and newcomer denominators must be unique")
        disposition_keys = tuple(row.item_key for row in self.dispositions)
        if len(disposition_keys) != len(set(disposition_keys)):
            raise ValueError("recovery dispositions must be unique")
        source_ids = tuple(row.source_instance_id for row in self.sources)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source instances must be unique")
        return self


class RecoveryEvaluationV1(ProtocolModel):
    schema_version: Literal["limen.universe_recovery_evaluation.v1"] = "limen.universe_recovery_evaluation.v1"
    ok: bool
    stable_digest: str
    expected_items: int = Field(ge=0)
    disposed_items: int = Field(ge=0)
    errors: tuple[str, ...]


UniversePartitionKind = Literal[
    "repositories",
    "pull_requests",
    "branches",
    "local_roots",
    "worktrees",
    "protections",
    "terminal_dispositions",
]
UNIVERSE_PARTITION_KINDS: tuple[UniversePartitionKind, ...] = (
    "repositories",
    "pull_requests",
    "branches",
    "local_roots",
    "worktrees",
    "protections",
    "terminal_dispositions",
)


class UniversePartitionV1(ProtocolModel):
    """An explicit denominator whose every member is accounted for exactly once."""

    schema_version: Literal["limen.universe_partition.v1"] = "limen.universe_partition.v1"
    kind: UniversePartitionKind
    total: int = Field(ge=0)
    terminal: int = Field(ge=0)
    protected: int = Field(ge=0)
    blocked: int = Field(ge=0)
    unaccounted: int = Field(ge=0)
    complete: bool

    @model_validator(mode="after")
    def partition_is_exact(self) -> "UniversePartitionV1":
        accounted = self.terminal + self.protected + self.blocked + self.unaccounted
        if accounted != self.total:
            raise ValueError("partition total must equal terminal + protected + blocked + unaccounted")
        if self.complete != (self.unaccounted == 0):
            raise ValueError("partition completeness must match its unaccounted count")
        return self


class RecoveryStableObservationV1(ProtocolModel):
    """A separately persisted first observation for the two-census fixed point."""

    schema_version: Literal["limen.universe_recovery_stable_observation.v1"] = (
        "limen.universe_recovery_stable_observation.v1"
    )
    stable_digest: str
    observed_at: datetime
    manifest_receipt: str
    repository_identity: RepositoryIdentityV1 | None = None
    repository: str | None = None
    default_ref: str | None = None
    default_sha: str | None = None
    default_check_status: Literal["green", "no_required_checks", "red", "pending", "unknown"] | None = None
    partitions: tuple[UniversePartitionV1, ...] = ()
    unaccounted: int = Field(default=0, ge=0)
    complete: bool | None = None

    _stable_digest = field_validator("stable_digest")(_digest)
    _observed = field_validator("observed_at")(_aware)
    _receipt = field_validator("manifest_receipt")(_nonblank)
    _repository = field_validator("repository", "default_ref")(
        lambda value: _nonblank(value) if value is not None else None
    )
    _default_sha = field_validator("default_sha")(lambda value: _git_oid(value) if value is not None else None)

    @model_validator(mode="after")
    def extended_observation_is_exact(self) -> "RecoveryStableObservationV1":
        extended = any(
            value is not None
            for value in (
                self.repository_identity,
                self.repository,
                self.default_ref,
                self.default_sha,
                self.default_check_status,
                self.complete,
            )
        ) or bool(self.partitions)
        if not extended:
            if self.unaccounted:
                raise ValueError("legacy stable observation cannot claim unaccounted extended state")
            return self
        if None in (
            self.repository_identity,
            self.repository,
            self.default_ref,
            self.default_sha,
            self.default_check_status,
            self.complete,
        ):
            raise ValueError("extended stable observation requires repository, default, and completeness fields")
        assert self.repository_identity is not None
        assert self.repository is not None
        assert self.default_ref is not None
        assert self.default_check_status is not None
        assert self.complete is not None
        if not self.repository_identity.accepts(self.repository):
            raise ValueError("stable observation repository must match its stable identity")
        if not self.default_ref.startswith("refs/heads/"):
            raise ValueError("stable observation default ref must be fully qualified")
        kinds = tuple(row.kind for row in self.partitions)
        required = set(UNIVERSE_PARTITION_KINDS)
        if len(kinds) != len(set(kinds)) or set(kinds) != required:
            raise ValueError("extended stable observation requires each universe partition exactly once")
        observed_unaccounted = sum(row.unaccounted for row in self.partitions)
        if observed_unaccounted != self.unaccounted:
            raise ValueError("stable observation unaccounted count must match its partitions")
        stable_default = self.default_check_status in {"green", "no_required_checks"}
        expected_complete = stable_default and all(row.complete for row in self.partitions) and self.unaccounted == 0
        if self.complete != expected_complete:
            raise ValueError("stable observation completeness must match default checks and partitions")
        return self


class UniverseBaselineReceiptV1(ProtocolModel):
    """Aggregate receipt for the frozen universe generation and no other source."""

    schema_version: Literal["limen.universe_baseline_receipt.v1"] = "limen.universe_baseline_receipt.v1"
    observed_at: datetime
    source_generation: str
    census_digest: str
    repository_denominator: int = Field(ge=0)
    stable_count: int = Field(ge=0)
    partitions: tuple[UniversePartitionV1, ...] = Field(min_length=1)
    failure_count: int = Field(ge=0)
    unaccounted: int = Field(ge=0)
    complete: bool

    _observed = field_validator("observed_at")(_aware)
    _digests = field_validator("source_generation", "census_digest")(_digest)

    @model_validator(mode="after")
    def aggregate_is_exact(self) -> "UniverseBaselineReceiptV1":
        if self.stable_count > self.repository_denominator:
            raise ValueError("stable repository count cannot exceed the frozen denominator")
        kinds = tuple(row.kind for row in self.partitions)
        required = set(UNIVERSE_PARTITION_KINDS)
        if len(kinds) != len(set(kinds)) or set(kinds) != required:
            raise ValueError("universe baseline requires each universe partition exactly once")
        repositories = next(row for row in self.partitions if row.kind == "repositories")
        if repositories.total != self.repository_denominator or repositories.terminal != self.stable_count:
            raise ValueError("repository partition must match denominator and stable count")
        observed_unaccounted = sum(row.unaccounted for row in self.partitions)
        if observed_unaccounted != self.unaccounted:
            raise ValueError("aggregate unaccounted count must match its partitions")
        expected_complete = (
            self.stable_count == self.repository_denominator
            and self.failure_count == 0
            and self.unaccounted == 0
            and all(row.complete for row in self.partitions)
        )
        if self.complete != expected_complete:
            raise ValueError("aggregate completeness must match stable, failure, and partition evidence")
        return self


def _pull_request_disposition_identity(
    row: RecoveryDispositionReceiptV1,
) -> tuple[int, int, str] | None:
    """Parse the exact repository/PR/head identity carried by a PR denominator."""

    if row.item_kind != "pull_request":
        return None
    match = _PULL_REQUEST_KEY.fullmatch(row.item_key)
    if match is None:
        return None
    try:
        return (
            int(match.group("repository_id")),
            int(match.group("pull_request")),
            _git_oid(match.group("head_sha")),
        )
    except ValueError:
        return None


def evaluate_recovery(manifest: UniverseRecoveryManifestV1) -> RecoveryEvaluationV1:
    errors: list[str] = []
    expected = set((*manifest.baseline_keys, *manifest.newcomer_keys))
    dispositions = {row.item_key: row for row in manifest.dispositions}
    missing = sorted(expected - dispositions.keys())
    unexpected = sorted(dispositions.keys() - expected)
    if missing:
        errors.append(f"missing-dispositions:{len(missing)}")
    if unexpected:
        errors.append(f"unexpected-dispositions:{len(unexpected)}")
    unknown = sum(row.terminal_class == "unknown" for row in manifest.dispositions)
    if unknown:
        errors.append(f"unknown-dispositions:{unknown}")
    incomplete_cursors = sum(not row.complete for row in manifest.cursor_receipts)
    if incomplete_cursors:
        errors.append(f"incomplete-cursors:{incomplete_cursors}")
    incomplete_sources = sum(not row.enumeration_complete for row in manifest.sources)
    if incomplete_sources:
        errors.append(f"incomplete-sources:{incomplete_sources}")
    open_reviews = sum(not row.terminal for row in manifest.review_closures)
    if open_reviews:
        errors.append(f"nonterminal-review-lineages:{open_reviews}")
    landed_pull_requests = [
        row
        for row in manifest.dispositions
        if row.item_kind == "pull_request" and row.terminal_class in {"exact_landed", "equivalent_landed"}
    ]
    invalid_landed_pull_keys = 0
    missing_review_lineages = 0
    for disposition in landed_pull_requests:
        identity = _pull_request_disposition_identity(disposition)
        if identity is None:
            invalid_landed_pull_keys += 1
            continue
        repository_id, pull_request, head_sha = identity
        if not any(
            closure.terminal
            and closure.pull_request == pull_request
            and closure.head_sha == head_sha
            and closure.repository_identity.repository_id == repository_id
            for closure in manifest.review_closures
        ):
            missing_review_lineages += 1
    if invalid_landed_pull_keys:
        errors.append(f"invalid-landed-pull-request-keys:{invalid_landed_pull_keys}")
    if missing_review_lineages:
        errors.append(f"missing-terminal-review-lineages:{missing_review_lineages}")
    unreconciled = sum(row.state != "completed" for row in manifest.reap_journals)
    if unreconciled:
        errors.append(f"unreconciled-reap-effects:{unreconciled}")
    stable_payload = manifest.model_dump(
        mode="json",
        exclude={
            "generated_at": True,
            "review_closures": {"__all__": {"observed_at"}},
        },
    )
    return RecoveryEvaluationV1(
        ok=not errors,
        stable_digest=canonical_digest(stable_payload),
        expected_items=len(expected),
        disposed_items=len(dispositions),
        errors=tuple(errors),
    )
