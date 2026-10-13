"""Additive owner-policy reconciliation against an authenticated live fingerprint."""

import copy
import json
from pathlib import Path
from limen.conduct.models import canonical_hash


def native_policy_record(path: Path, line: int) -> dict:
    """Recover private owner JSON without emitting its contents or executing history."""
    try:
        with path.open() as stream:
            record = next(row for number, row in enumerate(stream, 1) if number == line)
        item = json.loads(record)["payload"]["item"]
        if item.get("type") != "CommandExecution" or item.get("exit_code") != 0:
            raise ValueError
        policy = json.loads(item["stdout"])
        if not isinstance(policy, dict) or not isinstance(policy.get("approved_priorities"), list):
            raise ValueError
        return policy
    except (OSError, StopIteration, KeyError, TypeError, ValueError):
        raise ValueError("execution_policy_native_record_invalid") from None


def reconcile_policy(source: dict, live: dict, *, outcome: str, work_key: str, owner: str) -> dict:
    if live.get("schema_version") != "limen.execution_policy_readback.v1" or not live.get("runtime"):
        raise ValueError("execution_policy_generation_unavailable")
    if canonical_hash(source) != live.get("configuration_fingerprint"):
        raise ValueError("execution_policy_source_generation_mismatch")
    if source.get("mode") != "recovery" or source.get("dispatch_enabled") is not False:
        raise ValueError("execution_policy_not_contained")
    result = copy.deepcopy(source)
    priorities = result.get("approved_priorities")
    if not isinstance(priorities, list) or not outcome or not work_key or not owner:
        raise ValueError("execution_policy_invalid")
    matches = [p for p in priorities if p.get("outcome_id") == outcome or work_key in p.get("work_keys", [])]
    if matches:
        if len(matches) != 1 or matches[0].get("outcome_id") != outcome:
            raise ValueError("execution_policy_priority_conflict")
        row = matches[0]
        if (
            row.get("enabled") is not True
            or row.get("recovery") is not True
            or work_key not in row.get("work_keys", [])
        ):
            raise ValueError("execution_policy_existing_priority_requires_owner_review")
        return result
    priorities.append(
        dict(
            outcome_id=outcome,
            work_keys=[work_key],
            owner=owner,
            enabled=True,
            recovery=True,
            deadline_policy="hard_deadline",
            resource_limits={"issue": 0, "branch": 0, "worktree": 0},
        )
    )
    return result
