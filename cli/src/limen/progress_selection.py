"""Dynamic next-work ranking from live value, capacity, and host facts."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from hashlib import sha256
from typing import Any

from limen.capacity import canonical_agent
from limen.work_loan import task_work_loan_readiness

SELECTION_SCHEMA = "limen.progress-selection.v1"
DEFAULT_WEIGHTS = {
    "value": 3.0,
    "cost_of_delay": 2.5,
    "dependency_impact": 1.5,
    "confidence": 1.0,
    "provider_headroom": 1.0,
    "deadline_urgency": 2.0,
    "capacity_cost": -0.5,
}
TERMINAL_STATES = frozenset({"done", "archived"})
HOLD_LABELS = frozenset({"operator-paused", "needs-human", "workstream:successor-required"})


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _value(subject: Mapping[str, Any] | object, field: str, default: Any = None) -> Any:
    if isinstance(subject, Mapping):
        return subject.get(field, default)
    return getattr(subject, field, default)


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _first_number(task: Mapping[str, Any] | object, fields: Sequence[str]) -> float | None:
    for field in fields:
        value = _finite_number(_value(task, field))
        if value is not None:
            return value
    return None


def _due(task: Mapping[str, Any] | object) -> datetime | None:
    value = _value(task, "due_at") or _value(task, "due_on") or _value(task, "deadline")
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else None
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed_date = date.fromisoformat(str(value))
        except ValueError:
            return None
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=UTC)
    return parsed.astimezone(UTC) if parsed.tzinfo else None


def _headroom(row: Mapping[str, Any]) -> tuple[float, bool]:
    if row.get("reachable") is not True:
        return 0.0, False
    remaining = _finite_number(row.get("remaining"))
    limit = _finite_number(row.get("limit"))
    if remaining is None:
        return 1.0, False
    if limit is None or limit <= 0:
        return (1.0 if remaining > 0 else 0.0), False
    return max(0.0, min(1.0, remaining / limit)), True


def _candidate_capacity(
    task: Mapping[str, Any] | object,
    capacity_rows: Sequence[Mapping[str, Any]],
    host_pressure_reasons: Sequence[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    target = canonical_agent(str(_value(task, "target_agent") or "any"))
    rows = [row for row in capacity_rows if row.get("reachable") is True]
    if target != "any":
        rows = [row for row in rows if canonical_agent(str(row.get("agent") or "")) == target]
    debts: list[str] = []
    if host_pressure_reasons:
        remote = [row for row in rows if row.get("local") is False]
        if remote:
            rows = remote
        elif rows:
            debts.append("host-pressure-denies-only-eligible-local-capacity")
            rows = []
    normalized: list[dict[str, Any]] = []
    for row in rows:
        headroom, measured = _headroom(row)
        if not measured:
            debts.append(f"{row.get('agent')}:provider-headroom-unmeasured")
        normalized.append(
            {
                "agent": str(row.get("agent") or "unknown"),
                "kind": str(row.get("kind") or "unknown"),
                "local": row.get("local") is True,
                "headroom": round(headroom, 6),
                "headroom_measured": measured,
            }
        )
    return sorted(normalized, key=lambda row: str(row["agent"])), sorted(set(debts))


def _dependency_counts(tasks: Sequence[Mapping[str, Any] | object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for task in tasks:
        if str(_value(task, "status") or "") in TERMINAL_STATES:
            continue
        for dependency in _value(task, "depends_on", []) or []:
            key = str(dependency)
            counts[key] = counts.get(key, 0) + 1
    return counts


def _deadline_urgency(due: datetime | None, now: datetime) -> float:
    if due is None:
        return 0.0
    remaining_days = (due - now).total_seconds() / 86400
    if remaining_days <= 0:
        return 1.0
    return round(1.0 / (1.0 + remaining_days / 7.0), 6)


def rank_next_work(
    tasks: Sequence[Mapping[str, Any] | object],
    capacity_rows: Sequence[Mapping[str, Any]],
    host_pressure: Mapping[str, Any],
    *,
    now: datetime | None = None,
    weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Rank; never claim or dispatch. Provider/model catalogs stay live inputs."""

    observed = (now or datetime.now(UTC)).astimezone(UTC)
    effective_weights = dict(DEFAULT_WEIGHTS)
    if weights is not None:
        for field in DEFAULT_WEIGHTS:
            value = _finite_number(weights.get(field))
            if value is None:
                raise ValueError(f"selection weight {field} must be finite")
            effective_weights[field] = value
    dependency_counts = _dependency_counts(tasks)
    status_by_id = {str(_value(task, "id") or ""): str(_value(task, "status") or "") for task in tasks}
    pressure_reasons = sorted({str(value) for value in host_pressure.get("reasons") or [] if str(value)})
    candidates: list[dict[str, Any]] = []
    ineligible: list[dict[str, Any]] = []
    for task in tasks:
        task_id = str(_value(task, "id") or "")
        if str(_value(task, "status") or "") != "open":
            continue
        labels = {str(label).lower() for label in _value(task, "labels", []) or []}
        if labels & HOLD_LABELS:
            ineligible.append(
                {
                    "task_id": task_id,
                    "reason": "task-held-by-durable-label",
                    "metric_debt": sorted(labels & HOLD_LABELS),
                }
            )
            continue
        readiness = task_work_loan_readiness(task)
        if not readiness.ready:
            ineligible.append(
                {
                    "task_id": task_id,
                    "reason": readiness.reason_code or "task-not-underwritten",
                    "metric_debt": [],
                }
            )
            continue
        unmet = sorted(
            str(dependency)
            for dependency in _value(task, "depends_on", []) or []
            if status_by_id.get(str(dependency)) not in TERMINAL_STATES
        )
        if unmet:
            ineligible.append(
                {
                    "task_id": task_id,
                    "reason": "dependencies-unmet",
                    "metric_debt": [f"dependency:{dependency}" for dependency in unmet],
                }
            )
            continue
        providers, provider_debt = _candidate_capacity(task, capacity_rows, pressure_reasons)
        if not providers:
            ineligible.append(
                {
                    "task_id": task_id,
                    "reason": "no-live-eligible-capacity",
                    "metric_debt": provider_debt,
                }
            )
            continue
        missing: list[str] = list(provider_debt)
        value = _first_number(task, ("verified_value_score", "expected_value_score", "value_score"))
        if value is None:
            value = 0.0
            missing.append("value-score-missing")
        delay = _first_number(task, ("cost_of_delay_score", "cost_of_delay"))
        if delay is None:
            delay = 0.0
            missing.append("cost-of-delay-missing")
        confidence = _first_number(task, ("confidence", "confidence_score"))
        if confidence is None:
            confidence = 0.0
            missing.append("confidence-missing")
        confidence = max(0.0, min(1.0, confidence))
        dependency_impact = float(dependency_counts.get(task_id, 0))
        provider_headroom = max(float(row["headroom"]) for row in providers)
        capacity_cost = max(0.0, float(_finite_number(_value(task, "budget_cost")) or 0.0))
        due = _due(task)
        urgency = _deadline_urgency(due, observed)
        factors = {
            "value": value,
            "cost_of_delay": delay,
            "dependency_impact": dependency_impact,
            "confidence": confidence,
            "provider_headroom": provider_headroom,
            "deadline_urgency": urgency,
            "capacity_cost": capacity_cost,
        }
        score = round(sum(factors[field] * effective_weights[field] for field in effective_weights), 8)
        candidates.append(
            {
                "task_id": task_id,
                "score": score,
                "factors": factors,
                "due_at": due.isoformat().replace("+00:00", "Z") if due else None,
                "eligible_capacity": providers,
                "metric_debt": sorted(set(missing)),
            }
        )
    candidates.sort(
        key=lambda row: (
            -float(row["score"]),
            str(row["due_at"] or "9999-12-31T23:59:59Z"),
            str(row["task_id"]),
        )
    )
    for rank, candidate in enumerate(candidates, start=1):
        candidate["rank"] = rank
    material = {
        "schema": SELECTION_SCHEMA,
        "generated_at": observed.isoformat().replace("+00:00", "Z"),
        "weights": effective_weights,
        "capacity_content_sha256": _canonical_sha256(list(capacity_rows)),
        "host_pressure_content_sha256": _canonical_sha256(dict(host_pressure)),
        "host_pressure_reasons": pressure_reasons,
        "open_task_count": sum(str(_value(task, "status") or "") == "open" for task in tasks),
        "eligible_task_count": len(candidates),
        "ineligible_task_count": len(ineligible),
        "zero_launch_proven": not candidates and not ineligible,
        "candidates": candidates,
        "ineligible": sorted(ineligible, key=lambda row: str(row["task_id"])),
    }
    return {**material, "content_sha256": _canonical_sha256(material)}
