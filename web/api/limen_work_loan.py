"""Standalone task-side WorkLoanV1 readiness used by the deployed API image."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Iterable, Mapping

from limen_intake import is_durable_receipt_target, is_executable_predicate


FIELD_ORDER = (
    "source_origin",
    "horizon",
    "value_case",
    "budget_cost",
    "owner_surface",
    "predicate",
    "receipt_target",
    "due_at",
)
ORIGINS = {
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
HORIZONS = {
    "past": "past",
    "recovery": "past",
    "present": "present",
    "now": "present",
    "current": "present",
    "next": "future",
    "future": "future",
    "later": "future",
}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$")


def _value(task: Mapping[str, Any] | object, field: str, default: Any = None) -> Any:
    return task.get(field, default) if isinstance(task, Mapping) else getattr(task, field, default)


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _field_or_label(
    task: Mapping[str, Any] | object,
    fields: Iterable[str],
    prefixes: Iterable[str],
) -> str | None:
    for field in fields:
        value = _value(task, field)
        if value is not None and str(value).strip():
            return str(value).strip()
    markers = tuple(f"{prefix}:" for prefix in prefixes)
    for label in _value(task, "labels", []) or []:
        lowered = str(label).strip().lower()
        for marker in markers:
            if lowered.startswith(marker) and lowered[len(marker) :].strip():
                return lowered[len(marker) :].strip()
    return None


def _valid_due_at(value: Any) -> bool:
    text = str(value or "").strip()
    try:
        if DATE_RE.fullmatch(text):
            date.fromisoformat(text)
            return True
        if DATETIME_RE.fullmatch(text):
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed.tzinfo is not None
    except ValueError:
        return False
    return False


def _bounded_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and "\x00" not in value and len(value) <= 8192


def task_work_loan_missing_fields(task: Mapping[str, Any] | object) -> tuple[str, ...]:
    missing: set[str] = set()
    origin = ORIGINS.get(
        _slug(
            _field_or_label(
                task,
                ("source_origin", "intent_origin", "work_origin", "origin"),
                ("origin", "intent-origin", "work-origin"),
            )
        )
    )
    horizon = HORIZONS.get(_slug(_field_or_label(task, ("time_horizon", "horizon"), ("horizon", "time-horizon"))))
    value_case = _field_or_label(
        task,
        ("value_case", "expected_value", "work_credit"),
        ("value", "value-case", "work-credit"),
    )
    owner = (
        _field_or_label(
            task,
            ("owner_surface", "work_owner"),
            ("owner-surface", "work-owner"),
        )
        or str(_value(task, "repo", "") or "").strip()
    )
    cost = _value(task, "budget_cost")
    if not origin:
        missing.add("source_origin")
    if not horizon:
        missing.add("horizon")
    if not _bounded_text(value_case):
        missing.add("value_case")
    if isinstance(cost, bool) or not isinstance(cost, int) or cost <= 0:
        missing.add("budget_cost")
    if not _bounded_text(owner):
        missing.add("owner_surface")
    if not is_executable_predicate(_value(task, "predicate")):
        missing.add("predicate")
    if not is_durable_receipt_target(_value(task, "receipt_target")):
        missing.add("receipt_target")
    external = _value(task, "external_deadline", False)
    external = external is True or str(external).strip().lower() in {"1", "true", "yes"}
    due = _field_or_label(
        task,
        ("due_at", "due_on", "due_date", "deadline"),
        ("due", "due-at", "due-on", "deadline"),
    )
    if external and not _valid_due_at(due):
        missing.add("due_at")
    return tuple(field for field in FIELD_ORDER if field in missing)


def work_loan_denial(fields: Iterable[str]) -> str:
    selected = set(fields)
    ordered = [field for field in FIELD_ORDER if field in selected]
    return f"task-not-underwritten:{','.join(ordered)}"
