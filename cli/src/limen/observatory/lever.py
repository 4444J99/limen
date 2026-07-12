"""Emit the day's experiment as a human-gated proposal — never an auto-applied change.

OBSERVATORY proposes exactly one reversible experiment per day; a human approves it.
This module shapes that experiment into a ``his-hand-levers.json`` lever (the decision)
and a ``tasks.yaml``-style task (the reversible preparation), and records the proposal.

Safety posture (the default beat is read-only against every contended/live file):
  * ``propose(apply=False)`` — the beat default — appends the proposal to the
    organ-owned ``logs/observatory/proposals.jsonl`` and writes **nothing else**.
  * ``propose(apply=True)`` — the explicit arm — additionally appends the lever to
    ``his-hand-levers.json`` **idempotently by id** (atomic temp+rename) AND promotes the
    reversible-preparation task onto the board through the tabularius single-writer (P-PROMOTE):
    a ticket dropped in ``logs/tickets/inbox/`` that the keeper folds onto ``tasks.yaml`` next
    beat — **never a direct board write**. Both writes are fail-open and gated behind
    ``OBSERVATORY_APPLY``; the merge/publish decision stays behind the human lever.
"""

from __future__ import annotations

import json
import os
from datetime import date

from . import config, ledger


def to_lever(experiment: dict, hero: str | None) -> dict:
    """Shape the experiment as a his-hand-levers.json lever (the irreducible human act)."""
    return {
        "id": experiment.get("id", "L-OBS-EXP"),
        "label": (
            f"OBSERVATORY experiment on {hero or 'the hero repo'}: {experiment.get('change', '')} "
            f"Reversible ({experiment.get('revert', 'git revert')}). "
            f"Measure: {experiment.get('measure_hint', 'activation proxy over the window vs baseline')}."
        ),
        "owner": "yours",
        "cost": experiment.get("cost", "~20 min, reversible"),
        "unlocks": experiment.get("unlocks", "a measured activation lift on the hero repo"),
        "source_task": experiment.get("task_id", "OBS-EXP"),
        "issue": None,
    }


def _today() -> str:
    """A seam — the task's created date (tests may monkeypatch for determinism)."""
    return date.today().isoformat()


def to_task(experiment: dict, hero: str | None) -> dict:
    """Shape the reversible preparation as a VALID tasks.yaml Task (fleet may draft; human publishes).

    Validates as ``limen.models.Task`` so P-PROMOTE can submit it verbatim: ``target_agent='any'``
    (any lane may draft the reversible diff), the measurement contract serialized into the free-text
    ``context``, and a ``created`` date the model requires."""
    return {
        "id": experiment.get("task_id", "OBS-EXP"),
        "title": f"Prepare OBSERVATORY experiment: {experiment.get('change', '')}",
        "repo": hero,
        "type": "activation-experiment",
        "target_agent": "any",
        "priority": "high",
        "status": "open",
        "labels": ["human-gated", "observatory"],
        "context": json.dumps(experiment.get("measurement_contract", {}), sort_keys=True),
        "created": _today(),
    }


def _append_lever_idempotent(lever: dict) -> bool:
    """Append the lever to his-hand-levers.json if its id isn't already present. Atomic. Returns
    True iff a write occurred. Fail-open (a contended/unreadable registry → no write, no crash)."""
    path = config.repo_root() / "his-hand-levers.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(doc, dict) or not isinstance(doc.get("levers"), list):
        return False
    if any(isinstance(existing, dict) and existing.get("id") == lever["id"] for existing in doc["levers"]):
        return False  # already homed — idempotent
    doc["levers"].append(lever)
    try:
        tmp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
        tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _promote_task(task: dict) -> bool:
    """P-PROMOTE — submit the reversible-prep task to the board via the tabularius single-writer.

    Drops an upsert ticket in ``logs/tickets/inbox/`` that the keeper folds onto ``tasks.yaml`` next
    beat — it NEVER writes the board directly (the single-writer invariant). Fail-open: an invalid
    task / unwritable inbox / missing keeper → no ticket, no crash. Returns True iff a ticket landed."""
    try:
        from limen.tabularius import submit_task_upsert

        board = config.repo_root() / "tasks.yaml"
        submit_task_upsert(
            board,
            task,
            agent="observatory",
            session_id=os.environ.get("LIMEN_SESSION_ID", "observatory"),
        )
        return True
    except Exception:
        return False


def propose(brief: dict, *, apply: bool = False) -> dict:
    """Record (and, when armed, home) the day's experiment proposal. Never touches a public surface."""
    experiment = brief.get("experiment")
    hero = brief.get("hero")
    if not experiment:
        result = {"proposed": False, "reason": "no experiment (no gap today)", "armed": bool(apply)}
        ledger.append_jsonl("proposals.jsonl", result)
        return result

    lever = to_lever(experiment, hero)
    task = to_task(experiment, hero)
    homed = _append_lever_idempotent(lever) if apply else False
    task_promoted = _promote_task(task) if apply else False
    result = {
        "proposed": True,
        "armed": bool(apply),
        "lever_homed": homed,  # True only if apply and the id was newly written to the registry
        "task_promoted": task_promoted,  # True only if apply and a board ticket was submitted
        "lever": lever,
        "task": task,
    }
    ledger.append_jsonl("proposals.jsonl", result)
    return result
