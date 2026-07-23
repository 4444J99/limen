"""Compatibility import for the lane-neutral action-admission policy."""

from limen.action_admission import (
    Action,
    AdmissionInputError,
    action_denial_supported,
    classify_action,
    classify_bash,
    mutation_build_allowed,
    path_within,
    resolve_effective_cwd,
    target_paths,
)

__all__ = [
    "Action",
    "AdmissionInputError",
    "action_denial_supported",
    "classify_action",
    "classify_bash",
    "mutation_build_allowed",
    "path_within",
    "resolve_effective_cwd",
    "target_paths",
]
