"""Chronic fleet-debt — the shared label and log-evidence predicate.

A task is CHRONIC when the fleet reopened it >=3x and never produced a PR
(``verify-dispatch.py`` surfaces the live set). Chronic churn is the FLEET's
inability, not a human atom: ``heal-dispatch.py`` parks it in ``failed_blocked``
(which nothing recycles — ``recover.py`` reopens ``failed``, and
``verify-dispatch``'s chronic scan never reads ``failed_blocked``), so
``needs_human`` stays the truthful human surface. ``reclassify-needs-human.py``
uses the same predicate to keep chronic tasks out of its FLIP bucket — the two
halves of the oscillation this module closes.
"""

from __future__ import annotations

import re

CHRONIC_FLEET_DEBT_LABEL = "chronic-fleet-debt"

# Matches every machine chronic-escalation evidence string ever written to a dispatch_log:
#   current: "heal-dispatch: chronic (reopened ≥3×, never a PR) → escalated, stop re-looping"
#            "heal-dispatch: dispatched with no PR and chronic (reopened ≥3×) → escalated, …"
#   legacy:  "chronic (reopened >=3x, never a PR, fails all lanes) -> escalated out of dispatch loop"
# Deliberately does NOT match the his-hand opt-out write ("→ needs_human (kept: needs-human label)"),
# which contains no "escalat" — a labeled task must never be re-homed off the human surface.
CHRONIC_ESCALATION_RE = re.compile(r"chronic.*escalat", re.IGNORECASE | re.DOTALL)


def _entry_field(entry, name: str):
    if isinstance(entry, dict):
        return entry.get(name)
    return getattr(entry, name, None)


def chronic_escalated_to_needs_human(task) -> bool:
    """True iff the task's LAST transition into ``needs_human`` was a machine chronic escalation.

    Walks the dispatch_log backwards to the newest ``needs_human`` entry: if a human (or any
    non-chronic writer) parked the task there afterwards, that decision wins and this returns
    False. Accepts model objects or plain dicts.
    """
    log = _entry_field(task, "dispatch_log") or []
    for entry in reversed(log):
        if str(_entry_field(entry, "status") or "") == "needs_human":
            return bool(CHRONIC_ESCALATION_RE.search(str(_entry_field(entry, "output") or "")))
    return False
