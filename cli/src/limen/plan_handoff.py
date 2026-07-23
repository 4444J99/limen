"""Provider-neutral handoff from a plan-only run to a live builder lane."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from limen import census
from limen.capacity import CapacityRow, canonical_agent, capacity_census
from limen.models import Task

PLAN_RECEIPT_SCHEMA = "limen.plan_receipt.v1"
PLAN_ONLY_LABEL = "mode:plan-only"
BUILD_FROM_PLAN_LABEL = "mode:build-from-plan"
DEFAULT_BUILDER_CAPABILITIES = ("code", "execute", "local-worktree")
MAX_PLAN_CHARS = 262_144
_PLAN_CONTEXT_MARKER = "--- VALIDATED PLAN RECEIPT ---"
_MODEL_PIN_KEYS = frozenset(
    {
        "model",
        "model_id",
        "model_name",
        "selected_model",
        "claude_tier",
        "catalog_hash",
    }
)


class PlanReceiptError(ValueError):
    """A plan receipt is malformed, stale, or carries provider-specific authority."""


@dataclass(frozen=True)
class PlanHandoffResult:
    """Successful planning output awaiting a fresh builder selection."""

    receipt: dict[str, Any]


def is_plan_only(task: object | None) -> bool:
    return PLAN_ONLY_LABEL in (getattr(task, "labels", None) or [])


def is_build_from_plan(task: object | None) -> bool:
    return BUILD_FROM_PLAN_LABEL in (getattr(task, "labels", None) or [])


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _model_neutral_labels(task: Task) -> list[str]:
    return sorted(
        {
            str(label)
            for label in (task.labels or [])
            if str(label) not in {PLAN_ONLY_LABEL, BUILD_FROM_PLAN_LABEL} and not str(label).startswith("tier:")
        }
    )


def _source_context(task: Task) -> str | None:
    context = task.context
    if not context or not is_build_from_plan(task) or task.plan_receipt is None:
        return context
    marker = f"\n\n{_PLAN_CONTEXT_MARKER}"
    if marker in context:
        return context.rsplit(marker, 1)[0].rstrip() or None
    if context.startswith(_PLAN_CONTEXT_MARKER):
        return None
    return context


def task_contract_payload(task: Task) -> dict[str, Any]:
    """Return stable task intent without a planner lane, model hint, or lifecycle state."""

    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "repo": task.repo,
        "type": task.type,
        "workstream": task.workstream,
        "priority": task.priority,
        "budget_cost": task.budget_cost,
        "labels": _model_neutral_labels(task),
        "urls": list(task.urls or []),
        "context": _source_context(task),
        "predicate": task.predicate,
        "receipt_target": task.receipt_target,
        "origin": task.origin,
        "horizon": task.horizon,
        "value_case": task.value_case,
        "owner_surface": task.owner_surface,
        "external_deadline": task.external_deadline,
        "due_at": task.due_at,
        "execution_requirements": [item.model_dump(mode="json") for item in (task.execution_requirements or [])],
        "workstream_contract": task.workstream_contract,
        "depends_on": list(task.depends_on or []),
    }


def task_contract_digest(task: Task) -> str:
    return _digest(task_contract_payload(task))


def _assert_model_neutral(value: object, *, path: str = "receipt") -> None:
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key).strip().lower().replace("-", "_")
            if key in _MODEL_PIN_KEYS or key.endswith("_model"):
                raise PlanReceiptError(f"{path}.{raw_key} may not carry a model or catalog pin")
            _assert_model_neutral(item, path=f"{path}.{raw_key}")
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            _assert_model_neutral(item, path=f"{path}[{index}]")


def _receipt_without_digest(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in receipt.items() if key != "receipt_digest"}


def _builder_capabilities(task: Task) -> tuple[str, ...]:
    raw = getattr(task, "plan_builder_capabilities", None)
    if raw is None:
        return DEFAULT_BUILDER_CAPABILITIES
    if not isinstance(raw, list | tuple) or not raw:
        raise PlanReceiptError("plan_builder_capabilities must be a non-empty list")
    capabilities = tuple(sorted({str(item).strip() for item in raw if str(item).strip()}))
    if not capabilities:
        raise PlanReceiptError("plan_builder_capabilities must contain non-empty values")
    return capabilities


def build_plan_receipt(
    task: Task,
    plan: str,
    *,
    planner_agent: str,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Create a self-verifying, provider-neutral plan receipt."""

    if not is_plan_only(task):
        raise PlanReceiptError("a plan receipt may only be created for mode:plan-only")
    normalized_plan = plan.strip()
    if not normalized_plan:
        raise PlanReceiptError("plan output is empty")
    if len(normalized_plan) > MAX_PLAN_CHARS:
        raise PlanReceiptError(f"plan output exceeds {MAX_PLAN_CHARS} characters")
    timestamp = created_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise PlanReceiptError("created_at must be timezone-aware")
    receipt: dict[str, Any] = {
        "schema": PLAN_RECEIPT_SCHEMA,
        "created_at": timestamp.astimezone(UTC).isoformat(),
        "task_id": task.id,
        "repo": task.repo,
        "task_contract_digest": task_contract_digest(task),
        "planner_agent": canonical_agent(planner_agent),
        "plan": normalized_plan,
        "predicate": task.predicate,
        "receipt_target": task.receipt_target,
        "builder_requirements": {"capabilities": list(_builder_capabilities(task))},
        "execution_profile": {
            "planning_only": True,
            "build_allowed": False,
        },
    }
    _assert_model_neutral(receipt)
    receipt["receipt_digest"] = _digest(receipt)
    return validate_plan_receipt(receipt)


def validate_plan_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate receipt structure, digest, model neutrality, and plan bounds."""

    if not isinstance(value, Mapping):
        raise PlanReceiptError("plan receipt must be an object")
    receipt = {str(key): item for key, item in value.items()}
    expected_keys = {
        "schema",
        "created_at",
        "task_id",
        "repo",
        "task_contract_digest",
        "planner_agent",
        "plan",
        "predicate",
        "receipt_target",
        "builder_requirements",
        "execution_profile",
        "receipt_digest",
    }
    if set(receipt) != expected_keys:
        missing = sorted(expected_keys - set(receipt))
        extra = sorted(set(receipt) - expected_keys)
        raise PlanReceiptError(f"plan receipt keys differ (missing={missing}, extra={extra})")
    if receipt["schema"] != PLAN_RECEIPT_SCHEMA:
        raise PlanReceiptError(f"plan receipt schema must be {PLAN_RECEIPT_SCHEMA}")
    for key in ("task_id", "task_contract_digest", "planner_agent", "plan", "receipt_digest"):
        if not isinstance(receipt[key], str) or not receipt[key]:
            raise PlanReceiptError(f"{key} must be a non-empty string")
    if len(receipt["plan"]) > MAX_PLAN_CHARS:
        raise PlanReceiptError(f"plan output exceeds {MAX_PLAN_CHARS} characters")
    if len(receipt["task_contract_digest"]) != 64 or len(receipt["receipt_digest"]) != 64:
        raise PlanReceiptError("receipt digests must be lowercase SHA-256 values")
    try:
        int(receipt["task_contract_digest"], 16)
        int(receipt["receipt_digest"], 16)
        parsed_at = datetime.fromisoformat(str(receipt["created_at"]))
    except (TypeError, ValueError) as exc:
        raise PlanReceiptError("receipt contains an invalid digest or timestamp") from exc
    if parsed_at.tzinfo is None:
        raise PlanReceiptError("created_at must be timezone-aware")
    requirements = receipt["builder_requirements"]
    if not isinstance(requirements, Mapping):
        raise PlanReceiptError("builder_requirements must be an object")
    capabilities = requirements.get("capabilities")
    if (
        not isinstance(capabilities, list)
        or not capabilities
        or any(not isinstance(item, str) or not item.strip() for item in capabilities)
        or capabilities != sorted(set(capabilities))
    ):
        raise PlanReceiptError("builder capabilities must be a sorted unique non-empty string list")
    profile = receipt["execution_profile"]
    if not isinstance(profile, Mapping) or dict(profile) != {
        "planning_only": True,
        "build_allowed": False,
    }:
        raise PlanReceiptError("execution_profile must be the exact non-building planning profile")
    _assert_model_neutral(receipt)
    if receipt["receipt_digest"] != _digest(_receipt_without_digest(receipt)):
        raise PlanReceiptError("plan receipt digest mismatch")
    return receipt


def validate_receipt_for_task(task: Task, value: Mapping[str, Any]) -> dict[str, Any]:
    receipt = validate_plan_receipt(value)
    if receipt["task_id"] != task.id or receipt["repo"] != task.repo:
        raise PlanReceiptError("plan receipt task identity does not match")
    if receipt["task_contract_digest"] != task_contract_digest(task):
        raise PlanReceiptError("plan receipt task contract is stale")
    return receipt


def select_live_builder(
    receipt_value: Mapping[str, Any],
    *,
    capacity_rows: Sequence[CapacityRow] | None = None,
    execution_profiles: Mapping[str, census.ExecutionProfile] | None = None,
) -> str | None:
    """Select from fresh health and capability evidence; never from a stored model choice."""

    receipt = validate_plan_receipt(receipt_value)
    rows = list(capacity_rows) if capacity_rows is not None else capacity_census()
    profiles = dict(execution_profiles) if execution_profiles is not None else census.execution_profiles()
    required = set(receipt["builder_requirements"]["capabilities"])
    for row in rows:
        agent = canonical_agent(str(row.get("agent") or ""))
        profile = profiles.get(agent)
        if agent and row.get("reachable") is True and profile is not None and required.issubset(profile.capabilities):
            return agent
    return None


def builder_task_from_receipt(task: Task, receipt_value: Mapping[str, Any], *, builder: str) -> Task:
    """Create the executable task view while stripping every inherited model/tier hint."""

    receipt = validate_receipt_for_task(task, receipt_value)
    labels = [
        str(label)
        for label in (task.labels or [])
        if str(label) != PLAN_ONLY_LABEL and str(label) != BUILD_FROM_PLAN_LABEL and not str(label).startswith("tier:")
    ]
    labels.append(BUILD_FROM_PLAN_LABEL)
    source_context = _source_context(task)
    context = source_context.rstrip() if source_context else ""
    plan_context = (
        f"{_PLAN_CONTEXT_MARKER}\n"
        f"schema: {PLAN_RECEIPT_SCHEMA}\n"
        f"receipt_digest: {receipt['receipt_digest']}\n"
        f"{receipt['plan']}\n"
        "--- END VALIDATED PLAN RECEIPT ---"
    )
    return task.model_copy(
        update={
            "target_agent": canonical_agent(builder),
            "labels": labels,
            "context": f"{context}\n\n{plan_context}".strip(),
            "claude_tier": None,
            "plan_receipt": receipt,
            "status": "open",
        },
        deep=True,
    )
