"""Versioned canonical fingerprint for the fields that define one execution.

Task ids identify lifecycle rows, but they do not prove that the executable work
inside a row stayed unchanged between selection and execution. Exact-task
dispatchers carry this hash across that seam and workers verify it again from a
fresh board snapshot before invoking a provider.

The contract intentionally excludes lifecycle-only fields (``status``,
``created``, ``updated``, and ``dispatch_log``). Every other declared ``Task``
field is execution input and is represented without lossy coercion.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from limen.plan_handoff import PlanReceiptError, validate_plan_receipt
from limen.workstream_contract import ContractError as WorkstreamContractError
from limen.workstream_contract import validate_packet_contract

EXECUTION_CONTRACT_SCHEMA_VERSION = "limen-execution-contract.v4"


class ExecutionContractError(ValueError):
    """Raised when raw task data cannot be represented by the canonical schema."""


def _task_mapping(task: Mapping[str, Any] | object) -> Mapping[str, Any]:
    if isinstance(task, Mapping):
        return task
    model_dump = getattr(task, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="python")
        if isinstance(dumped, Mapping):
            return dumped
    raise ExecutionContractError("execution contract input must be a mapping or validated Task model")


def _string(
    data: Mapping[str, Any],
    field: str,
    *,
    default: str | None,
    nullable: bool = False,
) -> str | None:
    value = data.get(field, default)
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        expected = "string or null" if nullable else "string"
        raise ExecutionContractError(f"execution contract field {field!r} must be a {expected}")
    return value


def _string_list(data: Mapping[str, Any], field: str, *, order_insensitive: bool = False) -> list[str]:
    value = data.get(field, [])
    if not isinstance(value, list):
        raise ExecutionContractError(f"execution contract field {field!r} must be a list of strings")
    if any(not isinstance(item, str) for item in value):
        raise ExecutionContractError(f"execution contract field {field!r} must contain only strings")
    # Labels are semantically unordered throughout dispatch. Preserve duplicate multiplicity because
    # execution also consumes len(labels), while making equivalent re-orderings hash identically.
    return sorted(value) if order_insensitive else list(value)


def _budget_cost(data: Mapping[str, Any]) -> int:
    value = data.get("budget_cost", 1)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExecutionContractError("execution contract field 'budget_cost' must be an integer")
    if not 1 <= value <= 1000:
        raise ExecutionContractError("execution contract field 'budget_cost' must be between 1 and 1000")
    return value


def _execution_requirements(data: Mapping[str, Any]) -> list[dict[str, str]]:
    value = data.get("execution_requirements", [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ExecutionContractError("execution contract field 'execution_requirements' must be a list")
    requirements: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"kind", "path"}:
            raise ExecutionContractError(
                "execution contract field 'execution_requirements' must contain kind/path objects"
            )
        kind = item.get("kind")
        path = item.get("path")
        if kind != "mount" or not isinstance(path, str) or not path:
            raise ExecutionContractError("execution contract field 'execution_requirements' is invalid")
        requirements.append({"kind": kind, "path": path})
    return requirements


def _workstream_contract(data: Mapping[str, Any]) -> dict[str, Any] | None:
    value = data.get("workstream_contract")
    if value is None:
        return None
    try:
        return validate_packet_contract(value)
    except WorkstreamContractError as exc:
        raise ExecutionContractError(f"execution contract field 'workstream_contract' is invalid: {exc}") from exc


def _plan_receipt(data: Mapping[str, Any]) -> dict[str, Any] | None:
    value = data.get("plan_receipt")
    if value is None:
        return None
    try:
        return validate_plan_receipt(value)
    except PlanReceiptError as exc:
        raise ExecutionContractError(f"execution contract field 'plan_receipt' is invalid: {exc}") from exc


def execution_contract_payload(task: Mapping[str, Any] | object) -> dict[str, Any]:
    """Return the strict, versioned canonical payload for one task execution."""

    data = _task_mapping(task)
    return {
        "schema_version": EXECUTION_CONTRACT_SCHEMA_VERSION,
        "id": _string(data, "id", default=None),
        "title": _string(data, "title", default=None),
        "description": _string(data, "description", default=None, nullable=True),
        "repo": _string(data, "repo", default=None, nullable=True),
        "type": _string(data, "type", default="code"),
        "target_agent": _string(data, "target_agent", default=None),
        "workstream": _string(data, "workstream", default=None, nullable=True),
        "priority": _string(data, "priority", default="medium"),
        "budget_cost": _budget_cost(data),
        "labels": _string_list(data, "labels", order_insensitive=True),
        "urls": _string_list(data, "urls"),
        "context": _string(data, "context", default=None, nullable=True),
        "predicate": _string(data, "predicate", default=None, nullable=True),
        "receipt_target": _string(data, "receipt_target", default=None, nullable=True),
        "execution_requirements": _execution_requirements(data),
        "workstream_contract": _workstream_contract(data),
        "plan_receipt": _plan_receipt(data),
        "claude_tier": _string(data, "claude_tier", default=None, nullable=True),
        "depends_on": _string_list(data, "depends_on"),
    }


def execution_contract_hash(task: Mapping[str, Any] | object) -> str:
    """Hash the canonical execution payload with stable UTF-8 JSON encoding."""

    encoded = json.dumps(
        execution_contract_payload(task),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
