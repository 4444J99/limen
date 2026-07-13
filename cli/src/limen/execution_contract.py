"""Canonical fingerprint for the task fields that define one execution.

Task ids identify lifecycle rows, but they do not prove that the executable work
inside a row stayed unchanged between selection and reservation.  Exact-task
dispatchers carry this hash across that seam and recompute it from the board
while holding the queue lock before they spend budget or change task state.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def _value(task: Mapping[str, Any] | object, field: str, default: Any = None) -> Any:
    if isinstance(task, Mapping):
        return task.get(field, default)
    return getattr(task, field, default)


def execution_contract_payload(task: Mapping[str, Any] | object) -> dict[str, Any]:
    """Return the normalized fields that can materially change task execution."""

    workstream = str(_value(task, "workstream") or "").strip()
    task_type = str(_value(task, "type") or "").strip()
    labels = sorted({str(label).strip() for label in (_value(task, "labels", []) or []) if str(label).strip()})
    return {
        "id": str(_value(task, "id") or "").strip(),
        "repo": str(_value(task, "repo") or "").strip(),
        "target_agent": str(_value(task, "target_agent") or "").strip(),
        "workstream_or_type": workstream or task_type,
        "predicate": str(_value(task, "predicate") or "").strip(),
        "receipt_target": str(_value(task, "receipt_target") or "").strip(),
        "context": str(_value(task, "context") or ""),
        "labels": labels,
        "budget_cost": int(_value(task, "budget_cost", 1) or 1),
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
