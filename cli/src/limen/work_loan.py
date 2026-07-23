"""Shared work-capacity underwriting for task and conduct admission.

``WorkLoanV1`` is the one provider-neutral statement that scarce execution
capacity is buying a bounded, owned, receiptable outcome. Historical task
rows remain readable; the shared readiness result supplies the deterministic
denial used when the separately reviewed enforcement layer is activated.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from limen.intake import is_durable_receipt_target, is_executable_predicate

WORK_LOAN_SCHEMA: Literal["limen.work_loan.v1"] = "limen.work_loan.v1"
WORK_LOAN_MISSING_ORDER = (
    "source_origin",
    "horizon",
    "value_case",
    "budget_cost",
    "owner_surface",
    "predicate",
    "receipt_target",
    "due_at",
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$")

_ORIGIN_ALIASES = {
    "ask": "human_prompt",
    "human": "human_prompt",
    "human_ask": "human_prompt",
    "prompt": "human_prompt",
    "human_prompt": "human_prompt",
    "due": "obligation",
    "external": "obligation",
    "obligation": "obligation",
    "agent": "agent_recommendation",
    "agent_recommendation": "agent_recommendation",
    "recommendation": "agent_recommendation",
    "system": "system_debt",
    "debt": "system_debt",
    "system_debt": "system_debt",
}
_HORIZON_ALIASES = {
    "past": "past",
    "recovery": "past",
    "present": "present",
    "now": "present",
    "current": "present",
    "next": "future",
    "future": "future",
    "later": "future",
}


class WorkLoanV1(BaseModel):
    """The collateral required before one bounded run may consume capacity."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"external_deadline": {"const": True}},
                        "required": ["external_deadline"],
                    },
                    "then": {
                        "properties": {"due_at": {"not": {"type": "null"}}},
                        "required": ["due_at"],
                    },
                }
            ]
        },
    )

    schema_version: Literal["limen.work_loan.v1"] = WORK_LOAN_SCHEMA
    source_origin: Literal["obligation", "human_prompt", "agent_recommendation", "system_debt"]
    horizon: Literal["past", "present", "future"]
    value_case: str = Field(
        min_length=1,
        max_length=8192,
        json_schema_extra={"pattern": r"^[^\x00]*[^\s\x00][^\x00]*$"},
    )
    budget_cost: int = Field(gt=0, le=1_000_000)
    owner_surface: str = Field(
        min_length=1,
        max_length=8192,
        json_schema_extra={"pattern": r"^[^\x00]*[^\s\x00][^\x00]*$"},
    )
    external_deadline: bool = False
    due_at: date | datetime | None = None

    @field_validator("value_case", "owner_surface")
    @classmethod
    def validate_bounded_text(cls, value: str, info) -> str:
        normalized = value.strip()
        if not normalized or "\x00" in normalized or len(normalized) > 8192:
            raise ValueError(f"{info.field_name} must be a non-empty bounded string")
        return normalized

    @field_validator("due_at", mode="before")
    @classmethod
    def validate_due_at(cls, value: Any) -> date | datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                raise ValueError("due_at datetime must include a timezone")
            return value
        if isinstance(value, date):
            return value
        text = str(value).strip()
        try:
            if _DATE_RE.fullmatch(text):
                return date.fromisoformat(text)
            if _DATETIME_RE.fullmatch(text):
                return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("due_at must be a valid ISO date or timezone-aware datetime") from exc
        raise ValueError("due_at must be a valid ISO date or timezone-aware datetime")

    @model_validator(mode="after")
    def external_deadline_has_due_at(self) -> WorkLoanV1:
        if self.external_deadline and self.due_at is None:
            raise ValueError("due_at is required when external_deadline is true")
        return self


@dataclass(frozen=True)
class WorkLoanReadiness:
    loan: WorkLoanV1 | None
    missing_fields: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.missing_fields and self.loan is not None

    @property
    def reason_code(self) -> str | None:
        if self.ready:
            return None
        return work_loan_denial(self.missing_fields)


def _value(subject: Mapping[str, Any] | object, field: str, default: Any = None) -> Any:
    if isinstance(subject, Mapping):
        return subject.get(field, default)
    return getattr(subject, field, default)


def _slug(value: Any) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    return normalized or None


def _field_or_label(
    task: Mapping[str, Any] | object,
    fields: Iterable[str],
    label_prefixes: Iterable[str],
) -> str | None:
    for field in fields:
        value = _value(task, field)
        if value is not None and str(value).strip():
            return str(value).strip()
    prefixes = tuple(f"{prefix}:" for prefix in label_prefixes)
    for label in _value(task, "labels", []) or []:
        lowered = str(label).strip().lower()
        for prefix in prefixes:
            if lowered.startswith(prefix) and lowered[len(prefix) :].strip():
                return lowered[len(prefix) :].strip()
    return None


def task_origin(task: Mapping[str, Any] | object) -> str:
    raw = _field_or_label(
        task,
        ("source_origin", "intent_origin", "work_origin", "origin"),
        ("origin", "intent-origin", "work-origin"),
    )
    value = _slug(raw)
    return _ORIGIN_ALIASES.get(value or "", value or "unknown")


def task_horizon(task: Mapping[str, Any] | object) -> str:
    raw = _field_or_label(task, ("time_horizon", "horizon"), ("horizon", "time-horizon"))
    value = _slug(raw)
    return _HORIZON_ALIASES.get(value or "", value or "unknown")


def task_due(task: Mapping[str, Any] | object) -> str | None:
    return _field_or_label(
        task,
        ("due_at", "due_on", "due_date", "deadline"),
        ("due", "due-at", "due-on", "deadline"),
    )


def task_value_case(task: Mapping[str, Any] | object) -> str | None:
    return _field_or_label(
        task,
        ("value_case", "expected_value", "work_credit"),
        ("value", "value-case", "work-credit"),
    )


def task_source_lineage(task: Mapping[str, Any] | object) -> str:
    """Return only an explicit source/cohort lineage; absence stays visible."""

    return (
        _field_or_label(
            task,
            ("source_lineage", "lineage_id", "source_id", "source_event_id"),
            ("source-lineage", "lineage", "source-id", "source-event"),
        )
        or "unknown"
    )


def task_owner_surface(task: Mapping[str, Any] | object) -> str | None:
    explicit = _field_or_label(
        task,
        ("owner_surface", "work_owner"),
        ("owner-surface", "work-owner"),
    )
    if explicit:
        return explicit
    repo = str(_value(task, "repo", "") or "").strip()
    return repo or None


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _external_deadline(task: Mapping[str, Any] | object) -> bool:
    value = _value(task, "external_deadline", False)
    return value is True or (isinstance(value, str) and value.strip().lower() in {"1", "true", "yes"})


def _ordered_missing(fields: Iterable[str]) -> tuple[str, ...]:
    selected = set(fields)
    return tuple(field for field in WORK_LOAN_MISSING_ORDER if field in selected)


def _valid_due_at(value: Any) -> bool:
    if isinstance(value, datetime):
        return value.tzinfo is not None
    if isinstance(value, date):
        return True
    text = str(value or "").strip()
    try:
        if _DATE_RE.fullmatch(text):
            date.fromisoformat(text)
            return True
        if _DATETIME_RE.fullmatch(text):
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed.tzinfo is not None
    except ValueError:
        return False
    return False


def task_work_loan_readiness(task: Mapping[str, Any] | object) -> WorkLoanReadiness:
    """Derive only explicit task-owned metadata; never infer from title prose."""

    origin = task_origin(task)
    horizon = task_horizon(task)
    value_case = task_value_case(task)
    budget_cost = _positive_int(_value(task, "budget_cost"))
    owner_surface = task_owner_surface(task)
    predicate = _value(task, "predicate")
    receipt_target = _value(task, "receipt_target")
    external_deadline = _external_deadline(task)
    due_at = task_due(task)
    missing: list[str] = []
    if origin not in _ORIGIN_ALIASES.values():
        missing.append("source_origin")
    if horizon not in _HORIZON_ALIASES.values():
        missing.append("horizon")
    if not value_case:
        missing.append("value_case")
    if budget_cost is None:
        missing.append("budget_cost")
    if not owner_surface:
        missing.append("owner_surface")
    if not is_executable_predicate(predicate):
        missing.append("predicate")
    if not is_durable_receipt_target(receipt_target):
        missing.append("receipt_target")
    if external_deadline and not _valid_due_at(due_at):
        missing.append("due_at")
    ordered = _ordered_missing(missing)
    if ordered:
        return WorkLoanReadiness(loan=None, missing_fields=ordered)
    try:
        loan = WorkLoanV1.model_validate(
            {
                "source_origin": origin,
                "horizon": horizon,
                "value_case": value_case,
                "budget_cost": budget_cost,
                "owner_surface": owner_surface,
                "external_deadline": external_deadline,
                "due_at": due_at,
            }
        )
    except ValidationError as exc:
        fields = []
        for error in exc.errors():
            location = error.get("loc") or ()
            field = str(location[0]) if location else ""
            if field in WORK_LOAN_MISSING_ORDER:
                fields.append(field)
        if not fields:
            fields.append("due_at" if external_deadline else "value_case")
        return WorkLoanReadiness(loan=None, missing_fields=_ordered_missing(fields))
    return WorkLoanReadiness(loan=loan, missing_fields=())


def packet_is_non_capacity_projection(packet: Any) -> bool:
    """Recognize the exact broker-authenticated task projection that consumes no run capacity."""

    execution = _value(packet, "execution", {}) or {}
    intent = _value(packet, "intent", {}) or {}
    spend = _value(packet, "spend", {}) or {}
    authority = _value(packet, "authority", {}) or {}
    task_id = _value(packet, "task_id")
    kind = _value(intent, "kind")
    required_capabilities = set(_value(packet, "required_capabilities", ()) or ())
    actions = set(_value(authority, "actions", ()) or ())
    path_prefixes = set(_value(authority, "path_prefixes", ()) or ())
    external_effects = set(_value(authority, "external_effects", ()) or ())
    claims = tuple(_value(packet, "resource_claims", ()) or ())
    receipt_target = str(_value(packet, "receipt_target", "") or "")
    claim_matches = len(claims) == 1 and _value(claims[0], "key") == f"task/{task_id}"
    claim_matches = claim_matches and _value(claims[0], "mode") == "exclusive"
    return bool(
        _value(execution, "adapter") == "tabularius"
        and _value(execution, "projection") == "tasks.yaml"
        and kind in {"task.upsert", "task.status", "task.claim", "task.mutate"}
        and task_id
        and _value(intent, "task_id") == task_id
        and _value(packet, "preferred_agent") == "tabularius"
        and required_capabilities == {"board-write"}
        and claim_matches
        and _value(packet, "predicate") == "python3 scripts/validate-task-board.py --tasks tasks.yaml"
        and re.fullmatch(rf"git:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+:tasks\.yaml#{re.escape(str(task_id))}", receipt_target)
        and actions == {kind}
        and path_prefixes == {"tasks.yaml"}
        and not external_effects
        and _value(authority, "may_delegate") is False
        and _value(packet, "effect") == "write"
        and _value(spend, "unit", "runs") == "runs"
        and _value(spend, "limit") == 0
        and _value(spend, "reserve", 0) == 0
    )


def packet_work_loan_missing(packet: Any) -> tuple[str, ...]:
    """Return stable broker denial fields for a validated conduct packet."""

    if packet_is_non_capacity_projection(packet):
        return ()

    loan = _value(packet, "work_loan")
    missing: list[str] = []
    if loan is None:
        missing.extend(("source_origin", "horizon", "value_case", "budget_cost", "owner_surface"))
    else:
        for field in ("value_case", "owner_surface"):
            if not str(_value(loan, field, "") or "").strip():
                missing.append(field)
        if _value(loan, "source_origin") not in set(_ORIGIN_ALIASES.values()):
            missing.append("source_origin")
        if _value(loan, "horizon") not in set(_HORIZON_ALIASES.values()):
            missing.append("horizon")
        cost = _positive_int(_value(loan, "budget_cost"))
        spend = _value(packet, "spend")
        if cost is None or cost != _positive_int(_value(spend, "limit")):
            missing.append("budget_cost")
        if _value(loan, "external_deadline", False) and not _valid_due_at(_value(loan, "due_at")):
            missing.append("due_at")
    if not is_executable_predicate(_value(packet, "predicate")):
        missing.append("predicate")
    if not is_durable_receipt_target(_value(packet, "receipt_target")):
        missing.append("receipt_target")
    return _ordered_missing(missing)


def work_loan_denial(missing_fields: Iterable[str]) -> str:
    fields = _ordered_missing(missing_fields)
    return f"task-not-underwritten:{','.join(fields)}"
