"""Typed cloud-routine outcome receipts and idempotent task planning."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import field_validator, model_validator

from limen.conduct.models import ProtocolModel
from limen.intake import is_executable_predicate
from limen.models import Task


_ROUTINE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_FINDING_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_MAX_FUTURE_SKEW_SECONDS = 300


def _valid_repo_ref(value: str) -> bool:
    if not _REPO_RE.fullmatch(value):
        return False
    owner, repository = value.split("/", 1)
    return owner not in {".", ".."} and repository not in {".", ".."}


_LEVER_REF_RE = re.compile(r"^lever:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_DURABLE_OWNER_RE = re.compile(
    r"^(?:lever:[A-Za-z0-9][A-Za-z0-9._-]{0,127}|"
    r"irf:[A-Za-z0-9][A-Za-z0-9._:-]{0,127}|"
    r"https://github\.com/(?!\.\.?/)(?![A-Za-z0-9_.-]+/\.\.?/)"
    r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/"
    r"(?:issues|pull|actions/runs)/[0-9]+)$"
)
_OCCURRENCE_TASK_RE = re.compile(r"^(CLOUD-[0-9A-F]{20})(?:-[0-9]{8}T[0-9]{6}(?:\.[0-9]{6})?Z)?$")
_PREDICATE_SCHEMA_RE = re.compile(
    r"^(?!.*(?:<[^>]+>|\b(?:tbd|todo|fixme|replace[-_ ]me)\b))"
    r"(?=(?:[^']*'[^']*')*[^']*$)"
    r'(?=(?:[^"]*"[^"]*")*[^"]*$)'
    r"""(?=(?:(?:[^'";|&])|'[^']*'|"[^"]*")*$)"""
    r"(?!.*`)"
    r"(?!.*\\$).+$",
    re.IGNORECASE,
)


_MAX_SUBSTITUTION_DEPTH = 32


def _substitution_end(
    command: str,
    start: int,
    depth: int = 0,
) -> int | None:
    """Find a command substitution's closing parenthesis with nested quote contexts."""
    if depth > _MAX_SUBSTITUTION_DEPTH:
        return None
    quote: str | None = None
    escaped = False
    index = start
    while index < len(command):
        char = command[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == chr(92):
            escaped = True
            index += 1
            continue
        if quote == "'":
            if char == "'":
                quote = None
            index += 1
            continue
        if quote == '"':
            if char == '"':
                quote = None
                index += 1
                continue
            if char == "$" and index + 1 < len(command) and command[index + 1] == "(":
                nested_end = _substitution_end(command, index + 2, depth + 1)
                if nested_end is None:
                    return None
                index = nested_end + 1
                continue
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char == "$" and index + 1 < len(command) and command[index + 1] == "(":
            nested_end = _substitution_end(command, index + 2, depth + 1)
            if nested_end is None:
                return None
            index = nested_end + 1
            continue
        if char == ")":
            return index
        index += 1
    return None


def _contains_shell_composition(command: str) -> bool:
    # Return whether shell composition occurs outside quoted literals.
    quote: str | None = None
    escaped = False
    for char in command:
        if escaped:
            escaped = False
            continue
        if char == chr(92):
            escaped = True
            continue
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char in {";", "|", "&"}:
            return True
    return False


def _has_unsafe_command_substitution(command: str, depth: int = 0) -> bool:
    # Reject legacy backticks and composition hidden inside a command substitution.
    if depth > _MAX_SUBSTITUTION_DEPTH:
        return True
    if "`" in command:
        return True
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(command):
        char = command[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == chr(92):
            escaped = True
            index += 1
            continue
        if quote == "'":
            if char == "'":
                quote = None
            index += 1
            continue
        if quote == '"':
            if char == '"':
                quote = None
                index += 1
                continue
            if char == "$" and index + 1 < len(command) and command[index + 1] == "(":
                end = _substitution_end(command, index + 2, depth + 1)
                if end is None:
                    return True
                body = command[index + 2 : end]
                if _contains_shell_composition(body) or _has_unsafe_command_substitution(body, depth + 1):
                    return True
                index = end + 1
                continue
            index += 1
            continue
        if char == "'":
            quote = "'"
            index += 1
            continue
        if char == '"':
            quote = '"'
            index += 1
            continue
        if char == "$" and index + 1 < len(command) and command[index + 1] == "(":
            end = _substitution_end(command, index + 2, depth + 1)
            if end is None:
                return True
            body = command[index + 2 : end]
            if _contains_shell_composition(body) or _has_unsafe_command_substitution(body, depth + 1):
                return True
            index = end + 1
            continue
        index += 1
    return False


CloudRoutineStatus = Literal["ok", "finding", "failed"]
CloudRoutineDisposition = Literal[
    "no_change",
    "superseded",
    "owned",
    "new_work",
    "human_gate",
]


class CloudRoutineReceiptV1(ProtocolModel):
    """One routine observation with stable ownership and executable closure truth."""

    schema_version: Literal["limen.cloud_routine_receipt.v1"] = "limen.cloud_routine_receipt.v1"
    routine_id: str
    observed_at: datetime
    status: CloudRoutineStatus
    stable_finding_key: str
    disposition: CloudRoutineDisposition
    owner_ref: str | None
    predicate: str

    @field_validator("routine_id")
    @classmethod
    def validate_routine_id(cls, value: str) -> str:
        if not _ROUTINE_ID_RE.fullmatch(value):
            raise ValueError("routine_id must be a bounded protocol identifier")
        return value

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        if value.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(seconds=_MAX_FUTURE_SKEW_SECONDS):
            raise ValueError(f"observed_at cannot be more than {_MAX_FUTURE_SKEW_SECONDS} seconds in the future")
        return value

    @field_validator("stable_finding_key")
    @classmethod
    def validate_finding_key(cls, value: str) -> str:
        if not _FINDING_KEY_RE.fullmatch(value):
            raise ValueError("stable_finding_key must be a bounded protocol identifier")
        return value

    @field_validator("owner_ref")
    @classmethod
    def validate_owner_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized or "\x00" in normalized or len(normalized) > 1024:
            raise ValueError("owner_ref must be a non-empty bounded reference")
        return normalized

    @field_validator("predicate")
    @classmethod
    def validate_predicate(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) > 8192:
            raise ValueError("predicate must be at most 8192 characters")
        if _has_unsafe_command_substitution(normalized) or not _PREDICATE_SCHEMA_RE.fullmatch(normalized):
            raise ValueError("predicate must match the published bounded shell grammar")
        if not is_executable_predicate(normalized):
            raise ValueError("predicate must be one executable command")
        return normalized

    @model_validator(mode="after")
    def validate_material_ownership(self) -> "CloudRoutineReceiptV1":
        material = self.status in {"finding", "failed"}
        if self.disposition == "human_gate" and not material:
            raise ValueError("human_gate is only valid for a material finding")
        if (material or self.disposition == "human_gate") and not self.owner_ref:
            raise ValueError("material cloud-routine findings require owner_ref")
        if self.disposition == "human_gate" and not _LEVER_REF_RE.fullmatch(self.owner_ref or ""):
            raise ValueError("human_gate owner_ref must be a lever:<id> reference")
        if (
            material
            and self.disposition not in {"new_work", "human_gate"}
            and not _DURABLE_OWNER_RE.fullmatch(self.owner_ref or "")
        ):
            raise ValueError("material cloud-routine findings require a durable owner_ref")
        if self.disposition == "new_work":
            if not material:
                raise ValueError("new_work is only valid for a material finding")
            if not self.owner_ref or not _valid_repo_ref(self.owner_ref):
                raise ValueError("new_work owner_ref must be an exact owner/repo")
        return self


def task_id_for(receipt: CloudRoutineReceiptV1) -> str:
    """Return the stable TABVLARIVS task identity for one finding lineage."""
    lineage = f"{receipt.routine_id}\x00{receipt.stable_finding_key}".encode()
    digest = hashlib.sha256(lineage).hexdigest()[:20].upper()
    return f"CLOUD-{digest}"


def task_for(
    receipt: CloudRoutineReceiptV1,
    *,
    task_id: str | None = None,
) -> Task:
    """Translate one new-work disposition into the provider-neutral intake model."""
    if receipt.disposition != "new_work" or not receipt.owner_ref:
        raise ValueError("only new_work receipts can become tasks")
    task_id = task_id or task_id_for(receipt)
    return Task(
        id=task_id,
        title=f"Cloud routine finding: {receipt.stable_finding_key}",
        description=(
            f"Resolve finding {receipt.stable_finding_key} from "
            f"{receipt.routine_id} observed at {receipt.observed_at.isoformat()}."
        ),
        repo=receipt.owner_ref,
        type="code",
        target_agent="any",
        priority="medium",
        budget_cost=1,
        status="open",
        created=receipt.observed_at.date(),
        predicate=receipt.predicate,
        receipt_target=f"github:{receipt.owner_ref}:pull-request:{task_id}",
        origin="system_debt",
        horizon="present",
        value_case=("Convert a material recurring cloud observation into one owned, predicate-bound correction."),
        owner_surface=receipt.owner_ref,
        context=(
            f"CloudRoutineReceiptV1 {receipt.schema_version}; "
            f"disposition={receipt.disposition}; "
            f"stable_finding_key={receipt.stable_finding_key}; "
            f"observed_at={receipt.observed_at.isoformat()}"
        ),
    )


@dataclass(frozen=True)
class CloudRoutineIngestPlan:
    tasks: tuple[Task, ...]
    classified: int
    duplicates: int


def plan_task_upserts(
    receipts: Iterable[CloudRoutineReceiptV1],
    *,
    existing_ids: Iterable[str] = (),
    pending_ids: Iterable[str] = (),
    historical_ids: Iterable[str] = (),
    historical_observed_at: dict[str, datetime] | None = None,
) -> CloudRoutineIngestPlan:
    """Plan only novel live work while allowing a terminal lineage to recur.

    A delivery can contain retries or delayed observations for the same stable
    lineage. Keep only the newest observation before classifying it, so a later
    owned/superseded receipt can never be resurrected by an older new_work row.
    """
    receipt_rows = tuple(receipts)
    latest_by_lineage: dict[str, CloudRoutineReceiptV1] = {}
    receipts_by_timestamp: dict[str, dict[datetime, CloudRoutineReceiptV1]] = {}
    collapsed = 0
    for receipt in receipt_rows:
        lineage_id = task_id_for(receipt)
        by_timestamp = receipts_by_timestamp.setdefault(lineage_id, {})
        previous_at_timestamp = by_timestamp.get(receipt.observed_at)
        if previous_at_timestamp is not None:
            collapsed += 1
            if previous_at_timestamp != receipt:
                raise ValueError(f"conflicting cloud-routine observations share the same timestamp for {lineage_id}")
            continue
        by_timestamp[receipt.observed_at] = receipt
        previous = latest_by_lineage.get(lineage_id)
        if previous is None:
            latest_by_lineage[lineage_id] = receipt
            continue
        collapsed += 1
        if receipt.observed_at > previous.observed_at:
            latest_by_lineage[lineage_id] = receipt

    active = set(existing_ids) | set(pending_ids)
    historical = set(historical_ids) | active
    observed_history = historical_observed_at or {}

    def lineage_for(task_id: str) -> str:
        match = _OCCURRENCE_TASK_RE.fullmatch(task_id)
        return match.group(1) if match else task_id

    latest_historical_observed_at: dict[str, datetime] = {}
    for historical_id in historical:
        observed_at = observed_history.get(historical_id)
        if observed_at is None:
            continue
        lineage_id = lineage_for(historical_id)
        previous_observed_at = latest_historical_observed_at.get(lineage_id)
        if previous_observed_at is None or observed_at > previous_observed_at:
            latest_historical_observed_at[lineage_id] = observed_at
    active_lineages = {lineage_for(task_id) for task_id in active}
    seen_lineages: set[str] = set()
    tasks: list[Task] = []
    # Every terminal observation is classified even when a later receipt for the
    # same lineage controls task emission. This preserves the audit denominator
    # without allowing an older new_work receipt to resurrect superseded work.
    classified = sum(receipt.disposition != "new_work" for receipt in receipt_rows)
    duplicates = collapsed

    for receipt in latest_by_lineage.values():
        lineage_id = task_id_for(receipt)
        if receipt.disposition != "new_work":
            continue
        if lineage_id in active_lineages or lineage_id in seen_lineages:
            duplicates += 1
            continue
        task_id = lineage_id
        if lineage_id in historical:
            previous_observed_at = latest_historical_observed_at.get(lineage_id)
            if previous_observed_at is None or receipt.observed_at <= previous_observed_at:
                duplicates += 1
                continue
            observed_utc = receipt.observed_at.astimezone(timezone.utc)
            occurrence = observed_utc.strftime("%Y%m%dT%H%M%S")
            if observed_utc.microsecond:
                occurrence += f".{observed_utc.microsecond:06d}"
            task_id = f"{lineage_id}-{occurrence}Z"
        if task_id in active or task_id in historical or task_id in seen_lineages:
            duplicates += 1
            continue
        task = task_for(receipt, task_id=task_id)
        tasks.append(task)
        seen_lineages.add(lineage_id)
        seen_lineages.add(task_id)

    return CloudRoutineIngestPlan(
        tasks=tuple(tasks),
        classified=classified,
        duplicates=duplicates,
    )
