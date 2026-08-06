"""work_loan_backfill — mechanical WorkLoanV1 underwriting for loan-less board tasks.

738 of 829 open tasks (89%) fail :func:`limen.work_loan.task_work_loan_readiness` and are
therefore structurally undispatchable — the candidate-starvation cut of the 2026-07-19
starvation. This module derives the missing loan fields from data the task and the
registries already own, and REFUSES with a counted reason whenever an honest derivation
does not exist: a garbage loan wastes a quota slot, so refusal is the default.

The quality bar is declarative: ``docs/repo-predicates.yaml`` membership (seeded from the
value tier) is the permission to underwrite. Derivations:

  source_origin   id-prefix / label mapping; board debt defaults to ``system_debt``.
  horizon         ``horizon:*`` label else ``present``.
  budget_cost     1.
  owner_surface   registry ``owner_surface`` else the repo slug.
  receipt_target  ``github:{repo}:pull-request:{task_id}`` (the jules-supply convention).
  predicate       a PR URL the task already carries -> the board's merged-PR probe;
                  else the registry's predicate template. NEVER invented otherwise.
  value_case      mechanical template — honest only inside the value tier, which registry
                  membership already guarantees.

Pure functions over the task + registry — no gh, no filesystem writes — so the refusal
matrix is exhaustively testable. The effector (scripts/work-loan-backfill.py) owns board
iteration, the chronic/needs-human exclusions that need dispatch-module context, ticket
submission, and receipts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from limen.intake import is_durable_receipt_target, is_executable_predicate
from limen.work_loan import task_work_loan_readiness

_PR_URL_RE = re.compile(r"github\.com/([^/\s]+/[^/\s]+)/pull/(\d+)")

_SYSTEM_DEBT_PREFIXES = ("HEAL-", "GITVS-", "GH-", "LIMEN-", "IRF-", "DEBT-")
_AGENT_LABELS = {"generated", "mined", "build-out"}


@dataclass(frozen=True)
class RepoPredicates:
    default_template: str
    repos: dict[str, dict[str, Any]]


def load_repo_predicates(path: Path) -> RepoPredicates:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    repos = document.get("repos") or {}
    if not isinstance(repos, dict):
        repos = {}
    return RepoPredicates(
        default_template=str(document.get("default_predicate_template") or "").strip(),
        repos={str(k): (v if isinstance(v, dict) else {}) for k, v in repos.items()},
    )


def _value(task: Mapping[str, Any] | object, key: str, default: Any = None) -> Any:
    if isinstance(task, Mapping):
        return task.get(key, default)
    return getattr(task, key, default)


def _labels(task: Mapping[str, Any] | object) -> set[str]:
    return {str(label).strip().lower() for label in (_value(task, "labels") or [])}


def _pr_url(task: Mapping[str, Any] | object) -> tuple[str, str] | None:
    fields: list[str] = [str(url) for url in (_value(task, "urls") or [])]
    for key in ("context", "description", "title"):
        raw = _value(task, key)
        if raw:
            fields.append(str(raw))
    for text in fields:
        match = _PR_URL_RE.search(text)
        if match:
            return match.group(1), match.group(2)
    return None


def derive_source_origin(task: Mapping[str, Any] | object) -> str:
    labels = _labels(task)
    for label in labels:
        if label.startswith("origin:"):
            tail = label.removeprefix("origin:")
            if tail in {"human_prompt", "obligation", "agent_recommendation", "system_debt"}:
                return tail
    if labels & _AGENT_LABELS:
        return "agent_recommendation"
    task_id = str(_value(task, "id") or "")
    if task_id.startswith(_SYSTEM_DEBT_PREFIXES):
        return "system_debt"
    return "system_debt"


def derive_horizon(task: Mapping[str, Any] | object) -> str:
    for label in _labels(task):
        if label.startswith("horizon:"):
            tail = label.removeprefix("horizon:")
            if tail in {"past", "present", "future"}:
                return tail
    return "present"


def derive_loan_patch(
    task: Mapping[str, Any] | object,
    registry: RepoPredicates,
) -> tuple[dict[str, Any] | None, str]:
    """(patch, reason). patch is None on refusal; reason is 'minted' or a counted refusal code.

    The patch carries ONLY the fields readiness reports missing — a targeted edit, never a
    rewrite of fields the task already owns.
    """
    if str(_value(task, "status") or "") != "open":
        return None, "excluded:not-open"
    readiness = task_work_loan_readiness(task)
    if readiness.ready:
        return None, "already-ready"
    missing = set(readiness.missing_fields)
    if "due_at" in missing:
        # An external deadline the task failed to date is human context, not mechanics.
        return None, "unmintable:external-deadline-needs-due-at"

    repo = str(_value(task, "repo") or "").strip()
    if not repo:
        return None, "unmintable:no-repo"
    entry = registry.repos.get(repo)
    if entry is None:
        return None, "unmintable:repo-not-in-predicate-registry"

    task_id = str(_value(task, "id") or "").strip()
    if not task_id:
        return None, "unmintable:no-task-id"

    patch: dict[str, Any] = {}
    if "source_origin" in missing:
        patch["source_origin"] = derive_source_origin(task)
    if "horizon" in missing:
        patch["horizon"] = derive_horizon(task)
    if "budget_cost" in missing:
        patch["budget_cost"] = 1
    if "owner_surface" in missing:
        patch["owner_surface"] = str(entry.get("owner_surface") or repo)
    if "receipt_target" in missing:
        target = f"github:{repo}:pull-request:{task_id}"
        if not is_durable_receipt_target(target):
            return None, "unmintable:receipt-target-shape"
        patch["receipt_target"] = target
    if "predicate" in missing:
        pr = _pr_url(task)
        if pr is not None:
            pr_repo, pr_number = pr
            predicate = f'test "$(gh pr view {pr_number} --repo {pr_repo} --json state --jq .state)" = MERGED'
        else:
            template = str(entry.get("predicate_template") or registry.default_template).strip()
            if not template:
                return None, "unmintable:no-repo-predicate"
            predicate = template.format(repo=repo, task_id=task_id)
        if not is_executable_predicate(predicate):
            return None, "unmintable:predicate-shape"
        patch["predicate"] = predicate
    if "value_case" in missing:
        title = str(_value(task, "title") or "").strip() or task_id
        patch["value_case"] = (
            f"Board-debt conversion on the value tier: {title}. Landing this closes {task_id} "
            f"on {repo} with a merged-PR receipt instead of leaving it structurally undispatchable."
        )
    if not patch:
        return None, "unmintable:nothing-derivable"
    return patch, "minted"
