"""Emit the day's experiment as a human-gated proposal — never an auto-applied change.

OBSERVATORY proposes exactly one reversible experiment per day; a human approves it.
This module shapes that experiment into a ``his-hand-levers.json`` lever (the decision)
and a ``tasks.yaml``-style task (the reversible preparation), and records the proposal.

Safety posture (the default beat is read-only against every contended/live file):
  * ``propose(apply=False)`` — the beat default — appends the proposal to the
    organ-owned ``logs/observatory/proposals.jsonl`` and writes **nothing else**.
  * ``propose(apply=True)`` — the explicit arm — additionally appends the lever to
    ``his-hand-levers.json`` **idempotently by id** (atomic temp+rename). It does NOT
    write ``tasks.yaml`` directly: that board is single-writer (tabularius) via a ticket
    inbox, so task promotion is left to the recorded ``P-PROMOTE`` residual — the task
    object is carried in the proposal, ready to promote.
"""

from __future__ import annotations

import json
import os

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


def to_task(experiment: dict, hero: str | None) -> dict:
    """Shape the reversible preparation as a tasks.yaml-style task (fleet may draft; human publishes)."""
    return {
        "id": experiment.get("task_id", "OBS-EXP"),
        "title": f"Prepare OBSERVATORY experiment: {experiment.get('change', '')}",
        "repo": hero,
        "type": "activation-experiment",
        "target_agent": None,
        "priority": "high",
        "status": "open",
        "labels": ["human-gated", "observatory"],
        "context": experiment.get("measurement_contract", {}),
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
    result = {
        "proposed": True,
        "armed": bool(apply),
        "lever_homed": homed,  # True only if apply and the id was newly written to the registry
        "lever": lever,
        "task": task,
    }
    ledger.append_jsonl("proposals.jsonl", result)
    return result
