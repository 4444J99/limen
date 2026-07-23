"""Typed ownership guards for dispatch lifecycle reconciliation.

Task IDs and labels are useful routing hints, but they are not durable ownership.
For a GitHub pull request, the exact receipt identity plus a valid active task
contract is the authority.  This module keeps that rule shared by the read-only
dispatch verifier and the lock-protected healer.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlsplit

from limen.intake import is_durable_receipt_target, is_executable_predicate

ACTIVE_OWNER_STATUSES = frozenset({"open", "dispatched", "in_progress", "needs_human", "failed_blocked"})
_GITHUB_PR_URL_PATH_RE = re.compile(r"^/(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/pull/(?P<number>[1-9][0-9]*)/?$")
_GITHUB_PR_DECLARED_RE = re.compile(
    r"^github:(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+):pull-request:(?P<number>[1-9][0-9]*)$"
)


def _value(task: Mapping[str, Any] | object, field: str, default: Any = None) -> Any:
    if isinstance(task, Mapping):
        return task.get(field, default)
    return getattr(task, field, default)


def github_pr_receipt_identity(value: Any) -> tuple[str, str] | None:
    """Return a case-normalized ``(owner/repo, number)`` for an exact PR receipt.

    Both public GitHub URLs and Limen's declared typed target are accepted.  No
    task-ID naming convention or provider-specific metadata participates in the
    identity.
    """

    target = str(value or "").strip()
    declared = _GITHUB_PR_DECLARED_RE.fullmatch(target)
    if declared:
        return declared.group("repo").casefold(), str(int(declared.group("number")))

    parsed = urlsplit(target)
    if parsed.scheme.casefold() != "https" or parsed.netloc.casefold() != "github.com":
        return None
    match = _GITHUB_PR_URL_PATH_RE.fullmatch(parsed.path)
    if not match:
        return None
    return match.group("repo").casefold(), str(int(match.group("number")))


def active_typed_pr_owner_id(
    terminal_attempt: Mapping[str, Any] | object,
    all_tasks: Iterable[Mapping[str, Any] | object],
) -> str | None:
    """Find the active typed task that owns a terminal failed attempt's PR.

    A failed row is historical when another distinct task actively owns the same
    exact pull-request receipt and carries a valid intake contract.  Active state
    is the successor ordering signal: IDs, labels, provider names, and prose are
    deliberately ignored.  A terminal or malformed sibling is not an owner.
    """

    if str(_value(terminal_attempt, "status", "open") or "open") != "failed":
        return None
    receipt = github_pr_receipt_identity(_value(terminal_attempt, "receipt_target"))
    if receipt is None:
        return None
    attempt_id = str(_value(terminal_attempt, "id", "") or "")

    for candidate in all_tasks:
        candidate_id = str(_value(candidate, "id", "") or "")
        if not candidate_id or candidate_id == attempt_id:
            continue
        if str(_value(candidate, "status", "") or "") not in ACTIVE_OWNER_STATUSES:
            continue
        if not str(_value(candidate, "target_agent", "") or "").strip():
            continue
        predicate = _value(candidate, "predicate")
        candidate_target = _value(candidate, "receipt_target")
        if not is_executable_predicate(predicate) or not is_durable_receipt_target(candidate_target):
            continue
        if github_pr_receipt_identity(candidate_target) == receipt:
            return candidate_id
    return None
