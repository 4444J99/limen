"""Jules supply expansion: derive loan-complete packets from the declared template registry.

Pure logic only — the sensor/effector wrapper is ``scripts/jules-supply.py``. The registry
(``docs/jules-supply-templates.yaml``) declares renewable ``<id_prefix>-NNN`` series; this
module counts current dispatchable supply, derives the next unused index per series, and
expands templates into upsert-ready task patches mirroring the canary packet format Jules
completes successfully.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from limen.work_loan import task_work_loan_readiness

_SERIES_RE = re.compile(r"^(?P<prefix>.+)-(?P<index>\d{3})$")


@dataclass(frozen=True)
class SupplyRegistry:
    floor_env: str
    per_run_cap: int
    repos: tuple[dict[str, Any], ...]


def load_supply_registry(path: Path) -> SupplyRegistry:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if document.get("schema_version") != "limen.jules_supply.v1":
        raise ValueError(f"unsupported jules supply registry schema in {path}")
    repos = tuple(document.get("repos") or ())
    for repo in repos:
        if not repo.get("repo") or not repo.get("templates"):
            raise ValueError("jules supply registry repos need repo + templates")
    return SupplyRegistry(
        floor_env=str(document.get("floor_env") or "LIMEN_JULES_SUPPLY_FLOOR"),
        per_run_cap=int(document.get("per_run_cap") or 25),
        repos=repos,
    )


def dispatchable_supply(board: Any) -> int:
    """Count open, loan-ready jules work on the board — the honest supply gauge."""
    supply = 0
    for task in getattr(board, "tasks", None) or []:
        if str(getattr(task, "status", "")) != "open":
            continue
        if str(getattr(task, "target_agent", "")) not in {"jules", "any"}:
            continue
        readiness = task_work_loan_readiness(task)
        if not readiness.missing_fields:
            supply += 1
    return supply


def next_indices(existing_ids: set[str]) -> dict[str, int]:
    """Highest used NNN per series prefix among ``existing_ids``."""
    highest: dict[str, int] = {}
    for task_id in existing_ids:
        match = _SERIES_RE.match(task_id)
        if match:
            prefix = match.group("prefix")
            highest[prefix] = max(highest.get(prefix, 0), int(match.group("index")))
    return highest


def _context_for(repo_entry: dict[str, Any], template: dict[str, Any], task_id: str, title: str) -> str:
    repo = str(repo_entry["repo"])
    behavior = str(template["behavior"]).strip()
    predicate = str(template["predicate"]).strip()
    return (
        "Do not ask for feedback or approval. Complete only this bounded packet.\n\n"
        f"Task: {task_id} — {title}.\n"
        f"Repository: {repo}\n"
        f"Owner: {repo_entry.get('owner_surface', repo)}\n"
        f"Allowed paths: {template['allowed']}\n"
        f"Forbidden paths: {repo_entry.get('forbidden_paths', 'tasks.yaml')}\n"
        f"Required behavior: {behavior}\n"
        f"Authority boundary: {str(repo_entry.get('authority', '')).strip()}\n"
        f"Predicate: {predicate}\n"
        f"Receipt: github:{repo}:pull-request:{task_id}\n\n"
        "Return a bounded patch, tests, documentation, and the exact predicate result. "
        "Stop with a precise blocker if required authority or source is missing."
    )


def expand_supply(
    registry: SupplyRegistry,
    existing_ids: set[str],
    deficit: int,
    *,
    created: str,
) -> list[dict[str, Any]]:
    """Round-robin templates into up to ``min(deficit, per_run_cap)`` new task patches."""
    budget = min(max(deficit, 0), registry.per_run_cap)
    if budget <= 0:
        return []
    highest = next_indices(existing_ids)
    series: list[tuple[dict[str, Any], dict[str, Any]]] = [
        (repo_entry, template) for repo_entry in registry.repos for template in repo_entry.get("templates") or ()
    ]
    patches: list[dict[str, Any]] = []
    cursor = 0
    while len(patches) < budget and series:
        repo_entry, template = series[cursor % len(series)]
        cursor += 1
        prefix = str(template["id_prefix"])
        index = highest.get(prefix, 0) + 1
        highest[prefix] = index
        task_id = f"{prefix}-{index:03d}"
        title = str(template["title"]).replace("{n}", str(index))
        behavior = str(template["behavior"]).replace("{n}", str(index)).strip()
        patches.append(
            {
                "id": task_id,
                "title": title,
                "description": behavior[:300],
                "repo": str(repo_entry["repo"]),
                "type": "code",
                "target_agent": str(repo_entry.get("target_agent", "jules")),
                "workstream": str(repo_entry.get("workstream", "governance")),
                "priority": "medium",
                "budget_cost": int(template.get("budget_cost") or 1),
                "status": "open",
                "labels": ["jules-supply", "generated"],
                "context": _context_for(repo_entry, {**template, "behavior": behavior}, task_id, title),
                "predicate": str(template["predicate"]).strip(),
                "receipt_target": f"github:{repo_entry['repo']}:pull-request:{task_id}",
                "source_origin": "agent_recommendation",
                "horizon": "present",
                "value_case": str(template.get("value_case") or f"Bounded deepening round for {prefix}."),
                "owner_surface": str(repo_entry.get("owner_surface") or repo_entry["repo"]),
                "created": created,
            }
        )
    return patches
