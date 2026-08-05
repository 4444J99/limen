#!/usr/bin/env python3
"""_human_signals.py — ONE derived classifier for "does this task need his hand?"

Declared once, imported by both sides of the needs_human truth loop (the `_pr_scan.py` idiom):
  * scripts/reclassify-needs-human.py — the DRAIN: separates real human atoms from mislabeled ones.
  * scripts/heal-dispatch.py — the INFLOW: chronic escalation routes human-gated tasks to
    `needs_human` and everything else to `failed_blocked` (fleet debt, not his).

Signals are DERIVED, never a pinned id list: the lever registry (his-hand-levers.json), explicit
lever tags, structural id prefixes, and the credential/account keyword cluster.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Completing one of these needs something the fleet structurally CANNOT do.
# Substring (not \b) on the credential cluster on purpose: "JWT_SECRET" / "org_id" have no word
# boundary before the keyword, and erring toward KEEP (leaving a task surfaced) is the safe direction.
HUMAN_SIGNALS = re.compile(
    r"secret|credential|token|jwt|oauth|password|api[ _-]?key|org_id|org id|"
    r"branch protection|launchd|launchagent|gh (cli )?auth|merge gate|wrangler|cloudflare|"
    r"container/migrate|cutover|relocate bulky|backup|"
    r"ko-?fi|sponsor|stripe|lemonsqueeze|billing|\bkyc\b|account",
    re.IGNORECASE,
)
# Structural class (not pinned individuals): the *-deploy batch is gated on the Cloudflare credential.
HUMAN_ID_PREFIXES = ("BLD2-",)
# Explicit lever tag on a task — the surest human-atom signal, independent of the credential cluster.
LEVER_MARKER = re.compile(r"needs-human \(L-|\[his-hand\]", re.IGNORECASE)


def lever_ids(root: Path) -> set[str]:
    """The owned human-gate registry — a task naming any of these is his hand BY DEFINITION.

    Derived, never pinned: a task tagged to a lever (`needs-human (L-…)`, `[his-hand]`, or naming
    a registered lever id) is human-gated even absent a credential keyword — else a drain would
    hand a human-gated, sometimes IRREVERSIBLE act to the autonomous fleet. Fail-open empty.
    """
    try:
        raw = json.loads((root / "his-hand-levers.json").read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    levers = raw.get("levers") if isinstance(raw, dict) else raw
    return {lv["id"] for lv in (levers or []) if isinstance(lv, dict) and lv.get("id")}


def task_blob(task) -> str:
    """The searchable text of a limen.models.Task."""
    return " ".join(str(x) for x in (task.id, task.title, task.context, task.description) if x)


def is_human_gated(task, levers: set[str]) -> bool:
    """True iff completing the task needs his hand: lever tag / registered lever id / structural
    prefix / credential-cluster keyword. Absence of every signal means the fleet owns the outcome."""
    blob = task_blob(task)
    if LEVER_MARKER.search(blob) or any(lv in blob for lv in levers):
        return True
    if str(task.id or "").startswith(HUMAN_ID_PREFIXES):
        return True
    return bool(HUMAN_SIGNALS.search(blob))
