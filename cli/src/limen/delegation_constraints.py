"""Apply existing packet, retry, plan and reserved-tier bounds during model selection."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from limen.conduct.models import WorkPacketV1
from limen.model_selection import (
    _build_max_tier,
    _claude_fable_acceptance_present,
    _claude_model_is_fable,
    _claude_model_is_opus,
    _fable_or_downgrade,
    _guard_claude_model_pin,
)
from limen.models import Task
from limen.plan_handoff import validate_receipt_for_task
from limen.provider_health import TRANSIENT_TERMINALS, provider_health_policy
from limen.provider_selection import ExecutionProfile


def request_bounds(request: dict[str, Any], now: float) -> tuple[str | None, bool | None]:
    """Validate only; the existing keeper remains the sole spender/reserver."""
    attempt = request.get("attempt", 0)
    limit = provider_health_policy().same_model_retries + 1
    may_build = None
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0:
        return "invalid-attempt", may_build
    raw = request.get("work_packet")
    if raw is not None:
        try:
            packet = WorkPacketV1.model_validate(raw)
        except ValueError:
            return "invalid-work-packet", may_build
        if datetime.fromtimestamp(now, UTC) >= packet.deadline:
            return "parent-deadline-expired", may_build
        if request.get("phase", "delegation") == "delegation" and not packet.authority.may_delegate:
            return "parent-delegation-forbidden", may_build
        if packet.spend.unit == "runs" and packet.spend.limit <= packet.spend.reserve:
            return "parent-spend-exhausted", may_build
        limit = min(limit, packet.retry.max_attempts)
        may_build = packet.effect != "read" and bool({"*", "write"} & packet.authority.actions)
        if (
            attempt
            and packet.retry.transient_only
            and request.get("previous_terminal_class") not in TRANSIENT_TERMINALS
        ):
            return "nontransient-retry-forbidden", may_build
    if attempt >= limit:
        return "retry-budget-exhausted", may_build
    if attempt and request.get("previous_terminal_class") not in TRANSIENT_TERMINALS:
        return "retry-evidence-required", may_build
    return None, may_build


def valid_build_transition(request: dict[str, Any]) -> bool:
    try:
        task = Task.model_validate(request.get("task"))
        validate_receipt_for_task(task, request.get("plan_receipt"))
        return True
    except (ValueError, TypeError):
        return False


def candidate_allowed(model_id: str, profile: ExecutionProfile, *, reserved: bool) -> bool:
    if _claude_model_is_fable(model_id):
        return profile.planning_only and _claude_fable_acceptance_present() and _fable_or_downgrade() == "fable"
    if reserved:
        return False
    if _claude_model_is_opus(model_id):
        return profile.planning_only or (profile.build_allowed and _build_max_tier() == "opus")
    return _guard_claude_model_pin(model_id) == model_id
