"""owner_route_drain — pure verdict logic for the jules owner-route PR drain.

The June-July jules era left 308 open jules-authored PRs, every one classified
``owner_route`` and ``lifecycle:blocked``: launched, landed as a PR, and never routed
to a merge decision — 23.8% of estate PR debt (the debt GITVS-UNCAPPED-PR-DEBT-0715
names). This module decides, for one PR's observed facts, exactly one disposition:

  MERGE           CI-green, mergeable, non-trivial — the effector re-runs merge-policy.sh
                  adjacent to the effect and merges only on its exit 0 (the website
                  guardrail stays merge-policy's verdict, never re-derived here).
  SUPERSEDE       a merged sibling already carries this task's value — close with a
                  pointer, label lifecycle:superseded.
  CLOSE           trivial/empty diff, or aged past the max-age horizon with red CI and
                  no surviving value claim — close with the reason.
  ROUTE_TO_HEAL   mergeable-but-red or conflicting: real value needing repair. This
                  organ does NOTHING — self-heal.py already owns the heal-task writer,
                  and a second writer would race it.
  SKIP            not open, draft, or facts too incomplete to judge (fail toward
                  leaving the PR alone).

Pure functions over a facts dict — no gh calls, no filesystem — so the verdict matrix
is exhaustively testable. The effector (scripts/owner-route-drain.py) owns enumeration,
fact-gathering, the pause posture, receipts, and every outward write.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

MERGE = "merge"
SUPERSEDE = "supersede"
CLOSE = "close"
ROUTE_TO_HEAL = "route-to-heal"
SKIP = "skip"

_RED_STATES = {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"}
_PENDING_STATES = {"PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", ""}

# "[limen jules LIMEN-123]" titles and "jules/LIMEN-123-..." branches both carry the
# board task id; either form identifies the sibling family a merged PR may supersede.
_TASK_ID_RE = re.compile(r"\[limen jules ([A-Za-z0-9._-]+)\]|jules/([A-Za-z0-9._-]+?)(?:-[a-z0-9]{6,})?$")


@dataclass(frozen=True)
class Verdict:
    action: str
    reason: str


def task_family(title: str, head_ref: str) -> str | None:
    """The board-task family this PR belongs to, from its title or branch name."""
    for value in (title or "", head_ref or ""):
        match = _TASK_ID_RE.search(value)
        if match:
            return match.group(1) or match.group(2)
    return None


def _ci_signal(status_check_rollup: object) -> str:
    """'red' | 'pending' | 'green' — green only when every check concluded clean."""
    states = [
        str(check.get("conclusion") or check.get("state") or "")
        for check in (status_check_rollup or [])
        if isinstance(check, dict)
    ]
    if any(state in _RED_STATES for state in states):
        return "red"
    if any(state in _PENDING_STATES for state in states):
        return "pending"
    return "green"


def _age_days(created_at: object, now: datetime) -> float | None:
    if isinstance(created_at, datetime):
        created = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    else:
        try:
            created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
    return (now - created).total_seconds() / 86400.0


def classify(
    facts: dict,
    *,
    now: datetime,
    max_age_days: int = 45,
    merged_sibling: str | None = None,
    is_trivial: bool = False,
) -> Verdict:
    """One disposition for one PR's observed facts.

    ``merged_sibling`` is the URL of an already-merged PR carrying the same task family
    (the effector looks it up); ``is_trivial`` is the effector's diff verdict (empty or
    pure-reformat). Both default to the conservative value.
    """
    if str(facts.get("state") or "") != "OPEN":
        return Verdict(SKIP, "not open")
    if facts.get("isDraft"):
        return Verdict(SKIP, "draft")

    if merged_sibling:
        return Verdict(SUPERSEDE, f"superseded-by: {merged_sibling}")

    if is_trivial:
        return Verdict(CLOSE, "trivial: empty or pure-reformat diff — no value to merge")

    mergeable = str(facts.get("mergeable") or "")
    ci = _ci_signal(facts.get("statusCheckRollup"))

    if mergeable == "CONFLICTING" or ci == "red":
        age = _age_days(facts.get("createdAt"), now)
        if age is not None and age > max_age_days and ci == "red":
            return Verdict(
                CLOSE,
                f"aged out: {age:.0f}d old (max {max_age_days}) with red CI — "
                "reopen from the board if the value still stands",
            )
        return Verdict(ROUTE_TO_HEAL, f"repairable: mergeable={mergeable or 'UNKNOWN'} ci={ci} — self-heal owns it")

    if ci == "pending":
        return Verdict(SKIP, "ci pending — judge next pass")

    if mergeable == "MERGEABLE" and ci == "green":
        head = str(facts.get("headRefOid") or "")
        if not head:
            return Verdict(SKIP, "no head oid — cannot bind an exact-head merge")
        return Verdict(MERGE, "green and mergeable — effector must confirm via merge-policy.sh exit 0")

    return Verdict(SKIP, f"indeterminate: mergeable={mergeable or 'UNKNOWN'} ci={ci}")
