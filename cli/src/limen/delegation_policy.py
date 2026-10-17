"""Bounded, stateless selection at native delegation and phase boundaries.

Native adapters own their response schemas. This module returns a receipt using
the existing execution-profile/catalog/health vocabulary, never a model default.
Callers must supply a fresh catalog from their native registry, not tool arguments.
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from limen.delegation_constraints import candidate_allowed, request_bounds, valid_build_transition
from limen.provider_health import ProviderHealthSnapshot
from limen.provider_selection import (
    catalog_hash,
    execution_profile_for,
    parse_opencode_catalog,
    select_opencode_model,
)


def select_delegation(
    request: dict[str, Any],
    *,
    now: float | None = None,
    health: ProviderHealthSnapshot | None = None,
) -> dict[str, Any]:
    current = time.time() if now is None else now
    phase = request.get("phase", "delegation")
    task = request.get("task")
    profile = execution_profile_for(SimpleNamespace(**task) if isinstance(task, dict) else None)
    receipt: dict[str, Any] = {
        "decision": "deny",
        "selected_model": None,
        "selected_provider": None,
        "execution_profile": profile.as_dict(),
        "phase": phase,
        "selection_source": request.get("catalog_source"),
        "catalog_hash": None,
        "catalog_observed_at": request.get("catalog_observed_at"),
        "selection_reason": "catalog-unavailable",
        "observed_child_model": None,
    }
    if phase not in {"launch", "delegation", "plan-to-build"}:
        return receipt | {"selection_reason": "unsupported-phase"}
    reason, may_build = request_bounds(request, current)
    if reason:
        return receipt | {"selection_reason": reason}
    if phase == "plan-to-build":
        if not valid_build_transition(request):
            return receipt | {"selection_reason": "validated-plan-required"}
        profile = replace(profile, planning_only=False, build_allowed=True)
    if may_build is False:
        profile = replace(profile, build_allowed=False)
    receipt["execution_profile"] = profile.as_dict()
    observed = request.get("catalog_observed_at")
    if (
        isinstance(observed, bool)
        or not isinstance(observed, (int, float))
        or not math.isfinite(observed)
        or not 0 <= current - observed <= 300
    ):
        return receipt | {"selection_reason": "catalog-stale-or-unmeasured"}
    rows = request.get("models")
    if not isinstance(rows, list) or not request.get("catalog_source"):
        return receipt
    # Explicitly reserved candidates require their owning acceptance lifecycle;
    # an untrusted request cannot grant itself authority with an allow flag.
    rows = [row for row in rows if isinstance(row, dict)]
    reserved_ids = {
        model.model_id
        for row in rows
        if row.get("reserved") is True
        for model in parse_opencode_catalog(json.dumps(row))
    }
    models = [
        model
        for model in parse_opencode_catalog(json.dumps(rows))
        if candidate_allowed(model.model_id, profile, reserved=model.model_id in reserved_ids)
    ]
    receipt["catalog_hash"] = catalog_hash(models)
    selected = select_opencode_model(models, profile, health)
    if selected is None:
        return receipt | {"selection_reason": "no-known-priced-healthy-capable-model"}
    return receipt | {
        "decision": "allow",
        "selected_model": selected.model_id,
        "selected_provider": selected.model_id.split("/", 1)[0],
        "selection_reason": "fresh-catalog-capability-cost-and-health",
    }


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise TypeError("request must be an object")
        from limen.provider_health import (
            load_provider_outcomes,
            project_provider_health,
            provider_health_policy,
            provider_outcome_ledger_path,
        )

        health = project_provider_health(
            load_provider_outcomes(provider_outcome_ledger_path()),
            provider_health_policy(),
        )
        receipt = select_delegation(request, health=health)
    except (ValueError, TypeError, OverflowError):
        receipt = {"decision": "deny", "selection_reason": "invalid-selection-input"}
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
