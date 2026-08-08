"""Typed cloud-routine outcome receipts and idempotent task planning."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import field_validator, model_validator

from limen.conduct.models import ProtocolModel
from limen.intake import is_executable_predicate
from limen.models import Task


_ROUTINE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_FINDING_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

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

    schema_version: Literal["limen.cloud_routine_receipt.v1"] = (
        "limen.cloud_routine_receipt.v1"
    )
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
        if not is_executable_predicate(value):
            raise ValueError("predicate must be one executable command")
        return value.strip()

    @model_validator(mode="after")
    def validate_material_ownership(self) -> "CloudRoutineReceiptV1":
        material = self.status in {"finding", "failed"}
        if material and not self.owner_ref:
            raise ValueError("material cloud-routine findings require owner_ref")
        if self.disposition == "new_work":
            if not material:
                raise ValueError("new_work is only valid for a material finding")
            if not self.owner_ref or not _REPO_RE.fullmatch(self.owner_ref):
                raise ValueError("new_work owner_ref must be an exact owner/repo")
        return self


def task_id_for(receipt: CloudRoutineReceiptV1) -> str:
    """Return the stable TABVLARIVS task identity for one finding lineage."""
    lineage = f"{receipt.routine_id}\x00{receipt.stable_finding_key}".encode()
    digest = hashlib.sha256(lineage).hexdigest()[:20].upper()
    return f"CLOUD-{digest}"


def task_for(receipt: CloudRoutineReceiptV1) -> Task:
    """Translate one new-work disposition into the provider-neutral intake model."""
    if receipt.disposition != "new_work" or not receipt.owner_ref:
        raise ValueError("only new_work receipts can become tasks")
    task_id = task_id_for(receipt)
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
        predicate=receipt.predicate,
        receipt_target=f"github:{receipt.owner_ref}:pull-request:{task_id}",
        origin="system_debt",
        horizon="present",
        value_case=(
            "Convert a material recurring cloud observation into one owned, "
            "predicate-bound correction."
        ),
        owner_surface=receipt.owner_ref,
        context=(
            f"CloudRoutineReceiptV1 {receipt.schema_version}; "
            f"disposition={receipt.disposition}; "
            f"stable_finding_key={receipt.stable_finding_key}"
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
) -> CloudRoutineIngestPlan:
    """Plan only novel new-work upserts; repeated observations are idempotent."""
    known = set(existing_ids) | set(pending_ids)
    seen_lineages: set[str] = set()
    tasks: list[Task] = []
    classified = 0
    duplicates = 0

    for receipt in receipts:
        task_id = task_id_for(receipt)
        if receipt.disposition != "new_work":
            classified += 1
            continue
        if task_id in known or task_id in seen_lineages:
            duplicates += 1
            continue
        task = task_for(receipt)
        tasks.append(task)
        seen_lineages.add(task_id)

    return CloudRoutineIngestPlan(
        tasks=tuple(tasks),
        classified=classified,
        duplicates=duplicates,
    )
