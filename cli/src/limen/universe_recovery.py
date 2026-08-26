"""Typed, effect-free contracts for universe recovery and remote-ref reaping.

Collectors own observations and effectors own mutations.  This module only
validates the receipts that connect them, so a census, an old branch name, or
prose metadata can never mint landing or deletion authority.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any, Literal

import rfc8785
from pydantic import Field, field_validator, model_validator

from limen.conduct.models import ProtocolModel
from limen.repository_identity import RepositoryIdentityV1


_HEX = frozenset("0123456789abcdef")


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

    _surface = field_validator("surface")(_nonblank)

    @model_validator(mode="after")
    def completeness_is_exact(self) -> "CursorReceiptV1":
        exact = self.total_count == self.observed_count and not self.errors
        if self.complete != exact:
            raise ValueError("cursor completeness must match counts and errors")
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


class RecoveryStableObservationV1(ProtocolModel):
    """A separately persisted first observation for the two-census fixed point."""

    schema_version: Literal["limen.universe_recovery_stable_observation.v1"] = (
        "limen.universe_recovery_stable_observation.v1"
    )
    stable_digest: str
    observed_at: datetime
    manifest_receipt: str

    _stable_digest = field_validator("stable_digest")(_digest)
    _observed = field_validator("observed_at")(_aware)
    _receipt = field_validator("manifest_receipt")(_nonblank)


def _pull_request_disposition_identity(
    row: RecoveryDispositionReceiptV1,
) -> tuple[str, int, str] | None:
    """Parse the exact repository/PR/head identity carried by a PR denominator."""

    if row.item_kind != "pull_request":
        return None
    repository, marker, remainder = row.item_key.partition(":pull-request:")
    number, at, head_sha = remainder.partition("@")
    if marker != ":pull-request:" or not repository or at != "@" or not number.isdigit():
        return None
    try:
        return repository, int(number), _git_oid(head_sha)
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
        repository, pull_request, head_sha = identity
        if not any(
            closure.terminal
            and closure.pull_request == pull_request
            and closure.head_sha == head_sha
            and closure.repository_identity.accepts(repository)
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
