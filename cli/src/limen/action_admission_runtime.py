"""Shared runtime bridge from pure action policy to the host lease store."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from limen.action_admission import (
    AdmissionInputError,
    classify_action,
    mutation_build_allowed,
    path_within,
    resolve_effective_cwd,
    target_paths,
)
from limen.host_admission import AdmissionController, AdmissionStateError, is_descendant, worktree_scope


@dataclass(frozen=True)
class ToolAdmission:
    allowed: bool
    reason: str = ""


def admit_pre_tool_action(
    payload: dict[str, Any],
    *,
    controller: AdmissionController,
    owner: str | None,
    pid: int,
    surface: str,
    ttl_seconds: int,
) -> ToolAdmission:
    """Apply one lane-neutral action decision and acquire its exact writer scope."""

    action = classify_action(payload)
    if action.category in {"observe", "sanctioned_control"}:
        return ToolAdmission(True)
    if action.category == "deny":
        return ToolAdmission(False, action.reason)
    if action.category == "unguarded_heavy":
        return ToolAdmission(False, f"unguarded-heavy; use {action.equivalent}")
    if action.category == "guarded_heavy":
        status = controller.status(probe=True)
        heavy = next((item for item in status.get("leases") or [] if item.get("kind") == "heavy"), None)
        inherited = bool(heavy and is_descendant(pid, int(heavy["pid"])))
        reasons = list(status.get("reasons") or [])
        if heavy and not inherited:
            reasons.insert(0, "heavy-lease-held")
        return ToolAdmission(not reasons, ",".join(dict.fromkeys(reasons)))

    if owner is None:
        return ToolAdmission(False, "writer-session-identity-unavailable")
    allowed, reason = mutation_build_allowed(payload)
    if not allowed:
        return ToolAdmission(False, reason)
    try:
        cwd = resolve_effective_cwd(payload)
        scope = worktree_scope(cwd)
        targets = target_paths(payload, cwd)
    except (AdmissionInputError, ValueError) as exc:
        return ToolAdmission(False, str(exc))
    tool_name = str(payload.get("tool_name") or payload.get("tool") or "").strip().lower()
    structured_write = tool_name in {"edit", "write", "apply_patch", "applypatch"} or (
        "apply" in tool_name and "patch" in tool_name
    )
    if structured_write and not targets:
        return ToolAdmission(False, "write-target-unavailable")
    if not scope.linked:
        return ToolAdmission(False, "shared-checkout-write")
    if any(not path_within(path, scope.top_level) for path in targets):
        return ToolAdmission(False, "write-target-outside-worktree")
    try:
        decision = controller.acquire(
            scope.lease_kind,
            owner=owner,
            surface=surface,
            pid=pid,
            ttl_seconds=ttl_seconds,
        )
    except (AdmissionStateError, ValueError) as exc:
        return ToolAdmission(False, str(exc))
    if not decision["allowed"]:
        return ToolAdmission(
            False,
            ",".join(decision.get("reasons") or ["workspace-writer-lease-held"]),
        )
    return ToolAdmission(True)


__all__ = ["ToolAdmission", "admit_pre_tool_action"]
