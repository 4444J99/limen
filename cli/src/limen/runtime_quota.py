"""Quota observations become intake requests, never retirement authority."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from limen.intake import validate_intake_contract
from limen.models import Task
from limen.tabularius import INTENT_UPSERT, Ticket, submit_ticket, tickets_root
from limen.work_loan import task_work_loan_readiness


def maintenance_requests(observation: dict, board_path: Path) -> list[str]:
    if (
        not isinstance(observation, dict)
        or not isinstance(observation.get("runtime_root"), str)
        or not isinstance(observation.get("agents"), dict)
    ):
        raise ValueError("quota_observation_invalid")  # noqa: TRY004 - stable observation contract
    requests = []
    shared = observation.get("schema") == "domus.agent_runtime.v2"
    rows = {} if shared else dict(observation["agents"])
    if "total_size_bytes" in observation:
        rows["total"] = {
            "size_bytes": observation["total_size_bytes"],
            "quota_bytes": observation.get("total_quota_bytes"),
        }
    for agent, row in rows.items():
        if agent not in {"codex", "claude", "gemini", "opencode", "total"}:
            continue
        if not isinstance(row, dict):
            raise ValueError("quota_observation_invalid")  # noqa: TRY004 - stable observation contract
        size, quota = row.get("size_bytes"), row.get("quota_bytes")
        if type(size) is not int or type(quota) is not int or quota <= 0 or size < 0:
            raise ValueError("quota_observation_invalid")
        if size * 100 < quota * 80:
            continue
        identity = hashlib.sha256((observation["runtime_root"] + ":" + agent).encode()).hexdigest()[:16]
        task_id = f"RUNTIME-QUOTA-{agent.upper()}-{identity}"
        ticket_id = f"runtime-quota-{identity}"
        root = tickets_root(board_path)
        # The immutable ticket and create-only task predicate deduplicate both
        # concurrent launches and later launches after owner acknowledgement.
        if any((root / folder / f"{ticket_id}.json").exists() for folder in ("inbox", "archive")):
            requests.append(task_id)
            continue
        now = datetime.now(UTC)
        task = {
            "id": task_id,
            "title": "Restore shared runtime growth headroom" if shared else f"Restore {agent} runtime quota below 70%",
            "repo": "4444J99/domus-genoma",
            "target_agent": "codex",
            "type": "maintenance",
            "created": now.date().isoformat(),
            "priority": "high",
            "budget_cost": 1,
            "origin": "system_debt",
            "horizon": "present",
            "value_case": "Prevent recurring native launch admission failure",
            "owner_surface": "4444J99/domus-genoma",
            "receipt_target": f"github:4444J99/domus-genoma:issue:{task_id}",
            "predicate": f"limen runtime-quota --target-percent 70 --agent {agent}",
            "description": "Shared pool uses one reserve and no vendor slices. Target <=70% aggregate pressure. Verify inactive releases first. History retirement requires native restoration, replica acceptance, fresh source comparison and active-session protection. Preserve SQLite, sidecars and interrupted transfers. Request grants no deletion or execution authority.",
        }
        validated = Task.model_validate(task)
        validate_intake_contract(validated, is_new=True)
        readiness = task_work_loan_readiness(validated)
        if not readiness.ready:
            raise ValueError(readiness.reason_code)
        ticket = Ticket(
            ticket_id=ticket_id,
            timestamp=now,
            agent="codex",
            session_id="runtime-quota",
            intent=INTENT_UPSERT,
            task_id=task_id,
            patch=task,
            precondition={"absent": True},
        )
        try:
            submit_ticket(board_path, ticket)
        except FileExistsError:
            pass
        requests.append(task_id)
    return requests
