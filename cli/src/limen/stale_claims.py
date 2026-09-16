"""Bounded, read-only broker evidence for stale-claim maintenance.

Task age selects observations. It never establishes ownership absence. A None
result permits the existing provider-specific route; it is not a release receipt.
The eventual write still goes through the broker's atomic claim and transition.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable

from limen.conduct.client import client_from_env
from limen.census import VENDORS, canonical
from limen.models import Task


def stale_claim_holds(
    tasks: list[Task],
    *,
    client=None,
    clock: Callable[[], float] = time.monotonic,
    now: datetime | None = None,
    resolved_agents: dict[str, str] | None = None,
) -> dict[str, str | None]:
    """Return a hold reason, or terminal ownership evidence, for every task."""
    result: dict[str, str | None] = {task.id: "conduct_unmeasured" for task in tasks}
    if not tasks:
        return result
    deadline = clock() + 20
    try:
        client = client or client_from_env()
        client.timeout = 3
        capabilities = client.capabilities()
        if capabilities.get("schema_version") != "limen.conduct_capabilities.v1":
            return result
        generated = datetime.fromisoformat(capabilities["generated_at"].replace("Z", "+00:00"))
        now = now or datetime.now(timezone.utc)
        if generated.tzinfo is None or not 0 <= (now - generated).total_seconds() <= 30:
            return result
        rows = capabilities["sessions"]
        if not isinstance(rows, list):
            return result
        sessions = {row["session_id"]: row for row in rows}
        if len(sessions) != len(rows):
            return result
    except Exception:
        return result

    graphs = {}
    for task in tasks:
        try:
            remaining = deadline - clock()
            if remaining <= 0:
                break
            client.timeout = min(3, remaining)
            current = client.task_run(task.id)
            if (
                current.get("schema_version") != "limen.conduct_task_run.v1"
                or current.get("found") is not True
                or current.get("task_id") != task.id
            ):
                continue
            root = current["root_run_id"]
            if root not in graphs:
                remaining = deadline - clock()
                if remaining <= 0:
                    break
                client.timeout = min(3, remaining)
                graphs[root] = client.graph(root)
            nodes = [node for node in graphs[root]["nodes"] if node["run_id"] == current["run_id"]]
            if len(nodes) != 1:
                continue
            node = nodes[0]
            if node["packet"]["task_id"] != task.id or node["status"] != current["status"]:
                continue
            owners = [sessions[node[key]] for key in ("conductor_session_id", "executor_session_id")]
            if any(owner.get("human_protected") is True for owner in owners):
                result[task.id] = "conduct_human_protected"
                continue
            if any(owner.get("healthy") is True for owner in owners):
                result[task.id] = "conduct_owner_active"
                continue
            if any(owner.get("human_protected") is not False or owner.get("healthy") is not False for owner in owners):
                continue
            lease = node["lease"]
            if (
                lease.get("run_id") != current["run_id"]
                or lease.get("executor", {}).get("session_id") != node["executor_session_id"]
            ):
                continue
            if current["status"] in {"waiting", "reserved", "running", "stop_requested"}:
                result[task.id] = "conduct_run_active"
                continue
            if current["status"] not in {"succeeded", "failed", "cancelled"}:
                continue
            if lease.get("state") not in {"released", "expired"}:
                result[task.id] = "conduct_lease_unsettled"
                continue
            executor = canonical(lease["executor"].get("agent"))
            if executor not in {vendor.name for vendor in VENDORS}:
                continue
            if resolved_agents is not None:
                resolved_agents[task.id] = executor
            result[task.id] = None
        except Exception:
            # Missing ownership, graph failures and malformed evidence cannot
            # become release permission. Continue within the shared deadline.
            continue
    return result
