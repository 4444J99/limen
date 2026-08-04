import os
import re
import uuid
from urllib.parse import unquote
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import json
from typing import Any, Dict, List, Literal, Optional

import yaml
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, field_validator

from limen.conduct.client import client_from_env
from limen.conduct.models import (
    AgentIdentityV1,
    AuthorityEnvelopeV1,
    ConductorSessionV1,
    ResourceClaimV1,
    RunReceiptV1,
    SpendEnvelopeV1,
    WorkPacketV1,
    canonical_hash,
)
from limen.work_loan import WorkLoanV1, task_work_loan_readiness
from limen_mcp import runtime_requirements
from limen_mcp.intake import normalize_selected_legacy_task, validate_intake_contract

VALID_STATUSES = {"open", "dispatched", "in_progress", "done", "failed", "failed_blocked", "needs_human", "archived"}
VALID_PRIORITIES = {"critical", "high", "medium", "low", "backlog"}
VALID_AGENTS = {
    "jules",
    "claude",
    "gemini",
    "opencode",
    "codex",
    "copilot",
    "agy",
    "warp",
    "oz",
    "github_actions",
    "any",
}
CLAIMABLE_AGENTS = VALID_AGENTS - {"any"}
VALID_WORK_ORIGINS = {"obligation", "human_prompt", "agent_recommendation", "system_debt"}
VALID_WORK_HORIZONS = {"past", "present", "future"}
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
WORKSTREAM_SUCCESSOR_REQUIRED_LABEL = "workstream:successor-required"
mcp = FastMCP("Limen")

# -- NU-01 MCP surface (policy-scoped, read-only) ---------------------------

NU01_POLICY_VERSION = "nu-01-policy-v1"
NU01_CAPABILITY_BY_RESOURCE = {
    "search": "search.read",
    "entities": "entities.read",
    "timelines": "timelines.read",
    "commitments": "commitments.read",
    "decisions": "decisions.read",
    "source_receipts": "source_receipts.read",
}
NU01_ROLE_POLICY: dict[str, set[str]] = {
    "owner": {"search", "entities", "timelines", "commitments", "decisions", "source_receipts"},
    "collaborator": {"search", "entities", "timelines", "commitments", "decisions"},
    "auditor": {"search", "source_receipts"},
}

NU01_PRINCIPAL_DIRECTORY: dict[str, dict[str, Any]] = {
    "owner:arya@partition-a": {"role": "owner", "partitions": {"partition-a", "partition-b"}},
    "owner:niko@partition-b": {"role": "owner", "partitions": {"partition-b"}},
    "collab:maya@partition-a": {"role": "collaborator", "partitions": {"partition-a"}},
    "collab:leo@partition-b": {"role": "collaborator", "partitions": {"partition-b"}},
    "auditor:io@partition-a": {"role": "auditor", "partitions": {"partition-a"}},
}

NU01_ENTITIES = [
    {
        "id": "person-arya",
        "partitionId": "partition-a",
        "type": "person",
        "displayName": "Aria Nova",
        "classification": "partner",
        "contactEmail": "aria.nova+demo@example.com",
        "privateNotes": "Potential high-value account; never exposed outside owner role.",
    },
    {
        "id": "org-sigma",
        "partitionId": "partition-a",
        "type": "organization",
        "displayName": "Sigma Group",
        "classification": "client",
        "contactEmail": "owner@sigma.example",
        "privateNotes": "Regulatory NDA requires special handling.",
    },
    {
        "id": "engage-omega",
        "partitionId": "partition-b",
        "type": "engagement",
        "displayName": "Omega Pilot",
        "classification": "internal",
        "contactEmail": "omega@internal.example",
        "privateNotes": "Cross-portfolio exposure risk.",
    },
]

NU01_COMMITMENTS = [
    {
        "id": "commit-11",
        "partitionId": "partition-a",
        "title": "Finalize onboarding packet",
        "owner": "owner:arya@partition-a",
        "status": "open",
        "dueAt": "2026-08-20",
        "riskNotes": "Needs legal signature before escalation.",
    },
    {
        "id": "commit-22",
        "partitionId": "partition-a",
        "title": "Prepare Q3 narrative",
        "owner": "owner:arya@partition-a",
        "status": "in_progress",
        "dueAt": "2026-08-18",
        "riskNotes": "Coordinate with research.",
    },
    {
        "id": "commit-31",
        "partitionId": "partition-b",
        "title": "Archive source receipts",
        "owner": "owner:niko@partition-b",
        "status": "blocked",
        "dueAt": "2026-08-15",
        "riskNotes": "Blocked on third-party export approval.",
    },
]

NU01_DECISIONS = [
    {
        "id": "dec-01",
        "partitionId": "partition-a",
        "summary": "Approve external review window",
        "result": "approved",
        "madeBy": "owner:arya@partition-a",
        "decisionNotes": "Approved if review queue is within SLA.",
        "sourceReceiptRef": "src-rx-101",
    },
    {
        "id": "dec-02",
        "partitionId": "partition-b",
        "summary": "Suspend partner sync",
        "result": "conditional",
        "madeBy": "owner:niko@partition-b",
        "decisionNotes": "Limited to critical records only.",
        "sourceReceiptRef": "src-rx-402",
    },
]

NU01_SOURCE_RECEIPTS = [
    {
        "id": "src-rx-101",
        "partitionId": "partition-a",
        "source": "ingest-email",
        "status": "accepted",
        "correlationId": "corr-1001",
        "rawPayload": "subject=weekly digest; body=<redacted>",
    },
    {
        "id": "src-rx-402",
        "partitionId": "partition-b",
        "source": "connector-webhook",
        "status": "quarantine",
        "correlationId": "corr-2002",
        "rawPayload": "payload=<redacted>",
    },
]

NU01_TIMELINES = {
    "person-arya": [
        {"id": "ev-1", "partitionId": "partition-a", "kind": "engagement_started", "notes": "Initial intake completed"},
        {"id": "ev-2", "partitionId": "partition-a", "kind": "commitment_created", "notes": "Commit-11 created"},
    ],
    "org-sigma": [
        {"id": "ev-3", "partitionId": "partition-a", "kind": "risk_alert", "notes": "NDA clause changed"},
    ],
    "engage-omega": [
        {"id": "ev-4", "partitionId": "partition-b", "kind": "source_sync", "notes": "Source receipts refreshed"},
    ],
}

NU01_REDCTIONS = {
    "owner": set(),
    "collaborator": {"privateNotes", "riskNotes", "decisionNotes", "rawPayload", "contactEmail"},
    "auditor": {"privateNotes", "riskNotes", "decisionNotes", "rawPayload", "contactEmail"},
}

NU02_POLICY_VERSION = "nu-02-policy-v1"
NU02_CAPABILITY_BY_MUTATION = {
    "capture": "capture.write",
    "task": "task.write",
    "decision": "decision.write",
    "note": "note.write",
    "link": "link.write",
    "classification": "classification.write",
}
NU02_ROLE_MUTATION_POLICY: dict[str, set[str]] = {
    "owner": set(NU02_CAPABILITY_BY_MUTATION),
    "collaborator": {"capture", "task", "note", "link", "classification"},
    "auditor": set(),
}
NU02_MUTATION_PROPOSALS: dict[str, list[dict[str, Any]]] = {operation: [] for operation in NU02_CAPABILITY_BY_MUTATION}
NU02_IDEMPOTENCY_INDEX: dict[str, dict[str, Any]] = {}


def _nu02_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _nu02_make_policy_receipt(
    principal_id: str,
    partition_id: str,
    operation: str,
    capability: str,
    correlation_id: str,
    allowed: bool,
    reason_code: str,
    reason: str,
    role: str,
) -> dict[str, Any]:
    signature = canonical_hash(
        {
            "operation": operation,
            "capability": capability,
            "correlationId": correlation_id,
            "partitionId": partition_id,
            "policyVersion": NU02_POLICY_VERSION,
            "principalId": principal_id,
            "timestamp": "nu-02",
            "role": role,
        }
    )[:20]
    return {
        "policyVersion": NU02_POLICY_VERSION,
        "receiptId": signature,
        "principalId": principal_id,
        "principalRole": role,
        "partitionId": partition_id,
        "operation": operation,
        "capability": capability,
        "correlationId": correlation_id,
        "allowed": allowed,
        "reasonCode": reason_code,
        "reason": reason,
    }


def _nu02_apply_policy(
    principal_id: str,
    partition_id: str,
    operation: str,
    capability: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    principal = NU01_PRINCIPAL_DIRECTORY.get(_nu01_normalize_principal(principal_id))
    if principal is None:
        return _nu02_make_policy_receipt(
            principal_id=principal_id,
            partition_id=partition_id,
            operation=operation,
            capability=capability or NU02_CAPABILITY_BY_MUTATION.get(operation, "mutate.unknown"),
            correlation_id=correlation_id or str(uuid.uuid4()),
            allowed=False,
            reason_code="DENY_UNKNOWN_PRINCIPAL",
            reason=f"principal {principal_id} is not declared",
            role="unknown",
        )

    role = principal.get("role", "unknown")
    allowed_operations = NU02_ROLE_MUTATION_POLICY.get(role, set())
    partitions = principal.get("partitions", set())
    expected_capability = NU02_CAPABILITY_BY_MUTATION.get(operation, "mutate.unknown")
    if capability != expected_capability:
        return _nu02_make_policy_receipt(
            principal_id=principal_id,
            partition_id=partition_id,
            operation=operation,
            capability=capability or expected_capability,
            correlation_id=correlation_id or str(uuid.uuid4()),
            allowed=False,
            reason_code="DENY_CAPABILITY_MISMATCH",
            reason=f"capability {capability} cannot be used for {operation}",
            role=role,
        )

    if partition_id not in partitions and "*" not in partitions:
        return _nu02_make_policy_receipt(
            principal_id=principal_id,
            partition_id=partition_id,
            operation=operation,
            capability=capability or expected_capability,
            correlation_id=correlation_id or str(uuid.uuid4()),
            allowed=False,
            reason_code="DENY_PARTITION_MISMATCH",
            reason=f"principal {principal_id} is not scoped to partition {partition_id}",
            role=role,
        )

    if operation not in allowed_operations:
        return _nu02_make_policy_receipt(
            principal_id=principal_id,
            partition_id=partition_id,
            operation=operation,
            capability=capability or expected_capability,
            correlation_id=correlation_id or str(uuid.uuid4()),
            allowed=False,
            reason_code="DENY_OPERATION_SCOPE",
            reason=f"role {role} cannot perform {operation}",
            role=role,
        )

    return _nu02_make_policy_receipt(
        principal_id=principal_id,
        partition_id=partition_id,
        operation=operation,
        capability=capability or expected_capability,
        correlation_id=correlation_id or str(uuid.uuid4()),
        allowed=True,
        reason_code="ALLOW_SCOPE",
        reason=f"principal {principal_id} as {role} on partition {partition_id} is allowed to perform {operation}",
        role=role,
    )


def _nu02_check_partition_references(references: list[str], partition_id: str) -> list[str]:
    return [reference for reference in references if reference and reference != partition_id]


def _nu02_make_mutation_payload(
    operation: str,
    principal_id: str,
    partition_id: str,
    payload: dict[str, Any],
    idempotency_key: str,
    capability: str,
    correlation_id: str,
    status: str,
) -> dict[str, Any]:
    return {
        "mutationId": canonical_hash(
            {
                "capability": capability,
                "correlationId": correlation_id,
                "idempotencyKey": idempotency_key,
                "operation": operation,
                "partitionId": partition_id,
                "payload": payload,
                "principalId": principal_id,
                "requestedAt": "nu-02",
            }
        )[:20],
        "operation": operation,
        "status": status,
        "partitionId": partition_id,
        "principalId": principal_id,
        "capability": capability,
        "idempotencyKey": idempotency_key,
        "correlationId": correlation_id,
        "requestedAt": _nu02_now(),
    }


def _nu02_mutation_response(
    *,
    principal_id: str,
    partition_id: str,
    operation: str,
    capability: str,
    payload: dict[str, Any],
    idempotency_key: str,
    correlation_id: str | None = None,
    partition_refs: list[str] | None = None,
) -> dict[str, Any]:
    if not correlation_id:
        correlation_id = str(uuid.uuid4())

    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        return {
            "allowed": False,
            "principalId": principal_id,
            "partitionId": partition_id,
            "operation": operation,
            "capability": capability,
            "correlationId": correlation_id,
            "policyReceipt": _nu02_make_policy_receipt(
                principal_id=principal_id,
                partition_id=partition_id,
                operation=operation,
                capability=capability,
                correlation_id=correlation_id,
                allowed=False,
                reason_code="DENY_MISSING_IDEMPOTENCY_KEY",
                reason="idempotency_key is required for mutation proposals",
                role="unknown",
            ),
            "mutationReceipt": {
                "mutationId": None,
                "status": "denied",
                "operation": operation,
                "idempotencyKey": idempotency_key,
                "reasonCode": "DENY_MISSING_IDEMPOTENCY_KEY",
            },
        }

    partition_refs = partition_refs or []
    policy_decision = _nu02_apply_policy(
        principal_id=principal_id,
        partition_id=partition_id,
        operation=operation,
        capability=capability,
        correlation_id=correlation_id,
    )
    policy_decision["correlationId"] = correlation_id

    if not policy_decision["allowed"]:
        return {
            "allowed": False,
            "principalId": principal_id,
            "partitionId": partition_id,
            "operation": operation,
            "capability": capability,
            "correlationId": correlation_id,
            "policyReceipt": policy_decision,
            "mutationReceipt": {
                "mutationId": None,
                "status": "denied",
                "operation": operation,
                "idempotencyKey": idempotency_key,
                "reasonCode": policy_decision["reasonCode"],
            },
        }

    off_partition_refs = _nu02_check_partition_references(partition_refs, partition_id)
    if off_partition_refs:
        return {
            "allowed": False,
            "principalId": principal_id,
            "partitionId": partition_id,
            "operation": operation,
            "capability": capability,
            "correlationId": correlation_id,
            "policyReceipt": policy_decision,
            "mutationReceipt": {
                "mutationId": None,
                "status": "denied",
                "operation": operation,
                "idempotencyKey": idempotency_key,
                "reasonCode": "DENY_CROSS_PARTITION_REFERENCE",
                "offPartitionRefs": off_partition_refs,
            },
        }

    proposal_key = f"{principal_id}:{partition_id}:{operation}:{idempotency_key}"
    existing = NU02_IDEMPOTENCY_INDEX.get(proposal_key)
    if existing is not None:
        existing = dict(existing)
        replay_receipt = dict(existing["mutationReceipt"])
        replay_receipt["status"] = "replayed"
        existing["correlationId"] = correlation_id
        existing["policyReceipt"] = policy_decision
        existing["mutationReceipt"] = replay_receipt
        return existing

    proposal_payload = dict(payload)
    mutation_record = _nu02_make_mutation_payload(
        operation=operation,
        principal_id=principal_id,
        partition_id=partition_id,
        payload=proposal_payload,
        idempotency_key=idempotency_key,
        capability=capability,
        correlation_id=correlation_id,
        status="proposed",
    )
    mutation_record["payload"] = proposal_payload
    NU02_MUTATION_PROPOSALS[operation].append(mutation_record)

    receipt = {
        "mutationReceipt": mutation_record,
    }
    response = {
        "allowed": True,
        "principalId": principal_id,
        "partitionId": partition_id,
        "operation": operation,
        "capability": capability,
        "correlationId": correlation_id,
        "policyReceipt": policy_decision,
        "mutationReceipt": receipt["mutationReceipt"],
    }
    NU02_IDEMPOTENCY_INDEX[proposal_key] = dict(response)
    return response


def _nu02_create_note_payload(
    target_id: str,
    target_partition_id: str,
    summary: str,
    body: str | None = None,
) -> dict[str, Any]:
    return {
        "targetId": target_id,
        "targetPartitionId": target_partition_id,
        "summary": summary,
        "body": body or "",
    }


def _nu01_normalize_partition(partition_id: str) -> str:
    return partition_id.strip()


def _nu01_normalize_principal(principal_id: str) -> str:
    return principal_id.strip()


def _nu01_make_receipt(
    principal_id: str,
    partition_id: str,
    resource: str,
    capability: str,
    correlation_id: str,
    allowed: bool,
    reason_code: str,
    reason: str,
    role: str,
) -> dict[str, Any]:
    signature = canonical_hash(
        {
            "capability": capability,
            "correlationId": correlation_id,
            "partitionId": partition_id,
            "policyVersion": NU01_POLICY_VERSION,
            "principalId": principal_id,
            "resource": resource,
            "role": role,
            "timestamp": "nu-01",
        }
    )[:20]
    return {
        "policyVersion": NU01_POLICY_VERSION,
        "receiptId": signature,
        "principalId": principal_id,
        "principalRole": role,
        "partitionId": partition_id,
        "resource": resource,
        "capability": capability,
        "correlationId": correlation_id,
        "allowed": allowed,
        "reasonCode": reason_code,
        "reason": reason,
    }


def _nu01_apply_policy(
    principal_id: str,
    partition_id: str,
    resource: str,
    correlation_id: str | None = None,
    capability: str | None = None,
) -> dict[str, Any]:
    principal = NU01_PRINCIPAL_DIRECTORY.get(_nu01_normalize_principal(principal_id))
    if principal is None:
        return _nu01_make_receipt(
            principal_id=principal_id,
            partition_id=partition_id,
            resource=resource,
            capability=capability or NU01_CAPABILITY_BY_RESOURCE.get(resource, "read.unknown"),
            correlation_id=correlation_id or str(uuid.uuid4()),
            allowed=False,
            reason_code="DENY_UNKNOWN_PRINCIPAL",
            reason=f"principal {principal_id} is not declared",
            role="unknown",
        )

    role = principal.get("role", "unknown")
    allowed_resources = NU01_ROLE_POLICY.get(role, set())
    partitions = principal.get("partitions", set())
    can_partition = partition_id in partitions or "*" in partitions
    can_resource = resource in allowed_resources

    if not can_partition:
        return _nu01_make_receipt(
            principal_id=principal_id,
            partition_id=partition_id,
            resource=resource,
            capability=capability or NU01_CAPABILITY_BY_RESOURCE.get(resource, "read.unknown"),
            correlation_id=correlation_id or str(uuid.uuid4()),
            allowed=False,
            reason_code="DENY_PARTITION_MISMATCH",
            reason=f"principal {principal_id} is not scoped to partition {partition_id}",
            role=role,
        )

    if not can_resource:
        return _nu01_make_receipt(
            principal_id=principal_id,
            partition_id=partition_id,
            resource=resource,
            capability=capability or NU01_CAPABILITY_BY_RESOURCE.get(resource, "read.unknown"),
            correlation_id=correlation_id or str(uuid.uuid4()),
            allowed=False,
            reason_code="DENY_RESOURCE_SCOPE",
            reason=f"role {role} cannot read {resource}",
            role=role,
        )

    return _nu01_make_receipt(
        principal_id=principal_id,
        partition_id=partition_id,
        resource=resource,
        capability=capability or NU01_CAPABILITY_BY_RESOURCE.get(resource, "read.unknown"),
        correlation_id=correlation_id or str(uuid.uuid4()),
        allowed=True,
        reason_code="ALLOW_SCOPE",
        reason=f"principal {principal_id} as {role} on partition {partition_id} is allowed to read {resource}",
        role=role,
    )


def _nu01_redact_row(role: str, row: dict[str, Any]) -> dict[str, Any]:
    deny_fields = NU01_REDCTIONS.get(role, set())
    return {key: value for key, value in row.items() if key not in deny_fields}


def _nu01_filter_partition(rows: List[dict[str, Any]], partition_id: str) -> List[dict[str, Any]]:
    return [row for row in rows if row.get("partitionId") == partition_id]


def _nu01_search(partition_id: str, query: str, limit: int = 25) -> list[dict[str, Any]]:
    normalized = (query or "").strip().lower()
    docs = []
    for row in (
        _nu01_filter_partition(NU01_ENTITIES, partition_id)
        + _nu01_filter_partition(NU01_COMMITMENTS, partition_id)
        + _nu01_filter_partition(NU01_DECISIONS, partition_id)
    ):
        text = " ".join(str(value).lower() for value in row.values())
        if not normalized or normalized in text:
            docs.append(
                {
                    "documentId": row["id"],
                    "resource": row.get("type") or "resource",
                    "excerpt": " ".join(str(value) for key, value in row.items() if key not in {"privateNotes", "riskNotes", "decisionNotes"}),
                }
            )
            if len(docs) >= limit:
                break
    return docs


def _nu01_handle_read(
    *, principal_id: str, partition_id: str, resource: str, capability: str, payload: dict[str, Any], correlation_id: str | None = None
) -> dict[str, Any]:
    if not correlation_id or not isinstance(correlation_id, str):
        correlation_id = str(uuid.uuid4())
    decision = _nu01_apply_policy(
        principal_id=principal_id,
        partition_id=partition_id,
        resource=resource,
        capability=capability,
        correlation_id=correlation_id,
    )
    decision["correlationId"] = correlation_id
    role = decision["principalRole"] if decision["allowed"] else "unknown"
    if not decision["allowed"]:
        return {
            "allowed": False,
            "principalId": principal_id,
            "partitionId": partition_id,
            "capability": capability,
            "correlationId": correlation_id,
            "policyReceipt": decision,
            "data": None,
        }
    visible_data = _nu01_redact_row(role, payload.get("data", {}))
    if isinstance(payload.get("items"), list):
        visible_data = [_nu01_redact_row(role, item) for item in payload["items"]]
    return {
        "allowed": True,
        "principalId": principal_id,
        "partitionId": partition_id,
        "capability": capability,
        "correlationId": correlation_id,
        "policyReceipt": decision,
        "data": visible_data if payload.get("items") is not None else visible_data,
    }


def _nu01_entities_payload(partition_id: str) -> list[dict[str, Any]]:
    return _nu01_filter_partition(NU01_ENTITIES, partition_id)


def _nu01_timeline_payload(partition_id: str, entity_id: str) -> list[dict[str, Any]]:
    events = [event for event in NU01_TIMELINES.get(entity_id, []) if event.get("partitionId") == partition_id]
    events = sorted(events, key=lambda event: event.get("id"))
    if not events:
        return []
    return events


def _nu01_commitments_payload(partition_id: str) -> list[dict[str, Any]]:
    return _nu01_filter_partition(NU01_COMMITMENTS, partition_id)


def _nu01_decisions_payload(partition_id: str) -> list[dict[str, Any]]:
    return _nu01_filter_partition(NU01_DECISIONS, partition_id)


def _nu01_source_receipts_payload(partition_id: str) -> list[dict[str, Any]]:
    return _nu01_filter_partition(NU01_SOURCE_RECEIPTS, partition_id)


# -- NU-01 MCP resources and read tools ----------------------------------


@mcp.resource("mcp://nu/{principal_id}/{partition_id}/search/{query}")
def nu01_resource_search(
    principal_id: str,
    partition_id: str,
    query: str,
) -> dict[str, Any]:
    return _nu01_handle_read(
        principal_id=principal_id,
        partition_id=_nu01_normalize_partition(partition_id),
        resource="search",
        capability=NU01_CAPABILITY_BY_RESOURCE["search"],
        payload={"items": _nu01_search(partition_id, unquote(query))},
    )


@mcp.tool()
def nu01_search(
    principal_id: str,
    partition_id: str,
    query: str,
    capability: str = NU01_CAPABILITY_BY_RESOURCE["search"],
    limit: int = 25,
    correlation_id: str = "",
) -> dict[str, Any]:
    docs = _nu01_search(partition_id, query, limit=limit)
    return _nu01_handle_read(
        principal_id=principal_id,
        partition_id=_nu01_normalize_partition(partition_id),
        resource="search",
        capability=capability,
        correlation_id=correlation_id,
        payload={"items": docs},
    )


@mcp.resource("mcp://nu/{principal_id}/{partition_id}/entities")
def nu01_resource_entities(
    principal_id: str,
    partition_id: str,
) -> dict[str, Any]:
    return _nu01_handle_read(
        principal_id=principal_id,
        partition_id=_nu01_normalize_partition(partition_id),
        resource="entities",
        capability=NU01_CAPABILITY_BY_RESOURCE["entities"],
        payload={"items": _nu01_entities_payload(partition_id)},
    )


@mcp.tool()
def nu01_entities(
    principal_id: str,
    partition_id: str,
    capability: str = NU01_CAPABILITY_BY_RESOURCE["entities"],
    correlation_id: str = "",
) -> dict[str, Any]:
    return _nu01_handle_read(
        principal_id=principal_id,
        partition_id=_nu01_normalize_partition(partition_id),
        resource="entities",
        capability=capability,
        correlation_id=correlation_id,
        payload={"items": _nu01_entities_payload(partition_id)},
    )


@mcp.resource("mcp://nu/{principal_id}/{partition_id}/timeline/{entity_id}")
def nu01_resource_timeline(
    principal_id: str,
    partition_id: str,
    entity_id: str,
) -> dict[str, Any]:
    return _nu01_handle_read(
        principal_id=principal_id,
        partition_id=_nu01_normalize_partition(partition_id),
        resource="timelines",
        capability=NU01_CAPABILITY_BY_RESOURCE["timelines"],
        payload={"items": _nu01_timeline_payload(partition_id, entity_id)},
    )


@mcp.tool()
def nu01_timeline(
    principal_id: str,
    partition_id: str,
    entity_id: str,
    capability: str = NU01_CAPABILITY_BY_RESOURCE["timelines"],
    correlation_id: str = "",
) -> dict[str, Any]:
    return _nu01_handle_read(
        principal_id=principal_id,
        partition_id=_nu01_normalize_partition(partition_id),
        resource="timelines",
        capability=capability,
        correlation_id=correlation_id,
        payload={"items": _nu01_timeline_payload(partition_id, entity_id)},
    )


@mcp.resource("mcp://nu/{principal_id}/{partition_id}/commitments")
def nu01_resource_commitments(
    principal_id: str,
    partition_id: str,
) -> dict[str, Any]:
    return _nu01_handle_read(
        principal_id=principal_id,
        partition_id=_nu01_normalize_partition(partition_id),
        resource="commitments",
        capability=NU01_CAPABILITY_BY_RESOURCE["commitments"],
        payload={"items": _nu01_commitments_payload(partition_id)},
    )


@mcp.tool()
def nu01_commitments(
    principal_id: str,
    partition_id: str,
    capability: str = NU01_CAPABILITY_BY_RESOURCE["commitments"],
    correlation_id: str = "",
) -> dict[str, Any]:
    return _nu01_handle_read(
        principal_id=principal_id,
        partition_id=_nu01_normalize_partition(partition_id),
        resource="commitments",
        capability=capability,
        correlation_id=correlation_id,
        payload={"items": _nu01_commitments_payload(partition_id)},
    )


@mcp.resource("mcp://nu/{principal_id}/{partition_id}/decisions")
def nu01_resource_decisions(
    principal_id: str,
    partition_id: str,
) -> dict[str, Any]:
    return _nu01_handle_read(
        principal_id=principal_id,
        partition_id=_nu01_normalize_partition(partition_id),
        resource="decisions",
        capability=NU01_CAPABILITY_BY_RESOURCE["decisions"],
        payload={"items": _nu01_decisions_payload(partition_id)},
    )


@mcp.tool()
def nu01_decisions(
    principal_id: str,
    partition_id: str,
    capability: str = NU01_CAPABILITY_BY_RESOURCE["decisions"],
    correlation_id: str = "",
) -> dict[str, Any]:
    return _nu01_handle_read(
        principal_id=principal_id,
        partition_id=_nu01_normalize_partition(partition_id),
        resource="decisions",
        capability=capability,
        correlation_id=correlation_id,
        payload={"items": _nu01_decisions_payload(partition_id)},
    )


@mcp.resource("mcp://nu/{principal_id}/{partition_id}/source-receipts")
def nu01_resource_source_receipts(
    principal_id: str,
    partition_id: str,
) -> dict[str, Any]:
    return _nu01_handle_read(
        principal_id=principal_id,
        partition_id=_nu01_normalize_partition(partition_id),
        resource="source_receipts",
        capability=NU01_CAPABILITY_BY_RESOURCE["source_receipts"],
        payload={"items": _nu01_source_receipts_payload(partition_id)},
    )


@mcp.tool()
def nu01_source_receipts(
    principal_id: str,
    partition_id: str,
    capability: str = NU01_CAPABILITY_BY_RESOURCE["source_receipts"],
    correlation_id: str = "",
) -> dict[str, Any]:
    return _nu01_handle_read(
        principal_id=principal_id,
        partition_id=_nu01_normalize_partition(partition_id),
        resource="source_receipts",
        capability=capability,
        correlation_id=correlation_id,
        payload={"items": _nu01_source_receipts_payload(partition_id)},
    )


# -- NU-02 MCP tools (mutation commands with proposals + idempotency) ------


@mcp.tool()
def nu02_capture(
    principal_id: str,
    partition_id: str,
    capture_type: str,
    title: str,
    body: str,
    idempotency_key: str,
    source_partition_id: str = "",
    capability: str = NU02_CAPABILITY_BY_MUTATION["capture"],
    correlation_id: str = "",
) -> dict[str, Any]:
    return _nu02_mutation_response(
        principal_id=principal_id,
        partition_id=_nu01_normalize_partition(partition_id),
        operation="capture",
        capability=capability,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        partition_refs=[source_partition_id],
        payload={
            "captureType": _validate_text(capture_type, "capture_type", 120),
            "title": _validate_text(title, "title", 240),
            "body": _validate_text(body, "body", 2_000),
            "sourcePartitionId": source_partition_id,
        },
    )


@mcp.tool()
def nu02_task(
    principal_id: str,
    partition_id: str,
    title: str,
    owner: str,
    due_at: str,
    idempotency_key: str,
    source_partition_id: str = "",
    capability: str = NU02_CAPABILITY_BY_MUTATION["task"],
    correlation_id: str = "",
) -> dict[str, Any]:
    return _nu02_mutation_response(
        principal_id=principal_id,
        partition_id=_nu01_normalize_partition(partition_id),
        operation="task",
        capability=capability,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        partition_refs=[source_partition_id],
        payload={
            "title": _validate_text(title, "title", 240),
            "owner": _validate_text(owner, "owner", 240),
            "dueAt": _validate_text(due_at, "due_at", 80),
            "sourcePartitionId": source_partition_id,
        },
    )


@mcp.tool()
def nu02_decision(
    principal_id: str,
    partition_id: str,
    summary: str,
    result: str,
    idempotency_key: str,
    target_partition_id: str = "",
    capability: str = NU02_CAPABILITY_BY_MUTATION["decision"],
    correlation_id: str = "",
) -> dict[str, Any]:
    return _nu02_mutation_response(
        principal_id=principal_id,
        partition_id=_nu01_normalize_partition(partition_id),
        operation="decision",
        capability=capability,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        partition_refs=[target_partition_id],
        payload={
            "summary": _validate_text(summary, "summary", 640),
            "result": _validate_text(result, "result", 120),
            "targetPartitionId": target_partition_id,
        },
    )


@mcp.tool()
def nu02_note(
    principal_id: str,
    partition_id: str,
    target_id: str,
    summary: str,
    body: str,
    idempotency_key: str,
    target_partition_id: str = "",
    capability: str = NU02_CAPABILITY_BY_MUTATION["note"],
    correlation_id: str = "",
) -> dict[str, Any]:
    return _nu02_mutation_response(
        principal_id=principal_id,
        partition_id=_nu01_normalize_partition(partition_id),
        operation="note",
        capability=capability,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        partition_refs=[target_partition_id],
        payload=_nu02_create_note_payload(
            target_id=_validate_text(target_id, "target_id", 240),
            target_partition_id=target_partition_id,
            summary=_validate_text(summary, "summary", 640),
            body=body,
        ),
    )


@mcp.tool()
def nu02_link(
    principal_id: str,
    partition_id: str,
    left_entity_id: str,
    right_entity_id: str,
    left_entity_partition_id: str,
    right_entity_partition_id: str,
    idempotency_key: str,
    capability: str = NU02_CAPABILITY_BY_MUTATION["link"],
    correlation_id: str = "",
) -> dict[str, Any]:
    return _nu02_mutation_response(
        principal_id=principal_id,
        partition_id=_nu01_normalize_partition(partition_id),
        operation="link",
        capability=capability,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        partition_refs=[left_entity_partition_id, right_entity_partition_id],
        payload={
            "leftEntityId": _validate_text(left_entity_id, "left_entity_id", 240),
            "rightEntityId": _validate_text(right_entity_id, "right_entity_id", 240),
            "leftEntityPartitionId": left_entity_partition_id,
            "rightEntityPartitionId": right_entity_partition_id,
        },
    )


@mcp.tool()
def nu02_classification(
    principal_id: str,
    partition_id: str,
    target_id: str,
    classification: str,
    idempotency_key: str,
    rationale: str = "",
    target_partition_id: str = "",
    capability: str = NU02_CAPABILITY_BY_MUTATION["classification"],
    correlation_id: str = "",
) -> dict[str, Any]:
    return _nu02_mutation_response(
        principal_id=principal_id,
        partition_id=_nu01_normalize_partition(partition_id),
        operation="classification",
        capability=capability,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        partition_refs=[target_partition_id],
        payload={
            "targetId": _validate_text(target_id, "target_id", 240),
            "targetPartitionId": target_partition_id,
            "classification": _validate_text(classification, "classification", 120),
            "rationale": _validate_text(rationale, "rationale", 640),
        },
    )


# -- Server State -----------------------------------------------------------

def _reject_control_chars(value: str, field_name: str) -> str:
    if any((ord(ch) < 32 and ch not in "\t\n\r") or ord(ch) == 127 for ch in value):
        raise ValueError(f"{field_name} must not contain control characters")
    return value


def _validate_task_id(task_id: str) -> str:
    if not isinstance(task_id, str) or len(task_id) < 1 or len(task_id) > 128 or not TASK_ID_RE.match(task_id):
        raise ValueError("task_id must be 1-128 characters and contain only letters, numbers, '.', '_', '-', or '/'")
    return task_id


def _validate_text(value: str, field_name: str, max_len: int) -> str:
    if not isinstance(value, str) or len(value) > max_len:
        raise ValueError(f"{field_name} must be a string up to {max_len} characters")
    return _reject_control_chars(value, field_name)


def _validate_optional_enum(value: Optional[str], allowed: set[str], field_name: str) -> Optional[str]:
    if value is not None and value not in allowed:
        raise ValueError(f"{field_name} must be one of {', '.join(sorted(allowed))}")
    return value


# -- Models -----------------------------------------------------------------


class DispatchLogEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: datetime
    agent: str
    session_id: str
    status: str
    route_to: Optional[str] = None
    execution_profile: Optional[Dict[str, Any]] = None
    selected_model: Optional[str] = None
    selection_source: Optional[str] = None
    catalog_hash: Optional[str] = None
    health_snapshot_hash: Optional[str] = None
    provider_terminal_class: Optional[str] = None
    provider_retry_count: Optional[int] = None
    provider_cooldown_until: Optional[datetime] = None
    provider_health_evidence: Optional[Dict[str, Any]] = None
    output: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_event_status(cls, v: str) -> str:
        if v in VALID_STATUSES or v in {"noop", "pr_open"} or "->" in v:
            return v
        raise ValueError("dispatch event status must be canonical (legacy composite rows are read-only)")


class ExecutionRequirement(BaseModel):
    """A live control-host prerequisite that must clear before dispatch."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["mount"]
    path: str = Field(min_length=1, max_length=4096)

    @field_validator("path")
    @classmethod
    def validate_absolute_path(cls, value: str) -> str:
        if "\x00" in value or not os.path.isabs(value):
            raise ValueError("execution requirement path must be absolute")
        return value


class Task(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    description: Optional[str] = None
    repo: Optional[str] = None
    type: str = "code"
    target_agent: str
    priority: str = "medium"
    budget_cost: int = Field(default=1, ge=1)
    status: str = "open"
    labels: List[str] = Field(default_factory=list)
    urls: List[str] = Field(default_factory=list)
    context: Optional[str] = None
    predicate: Optional[str] = None
    receipt_target: Optional[str] = None
    origin: Optional[str] = None
    horizon: Optional[str] = None
    value_case: Optional[str] = None
    owner_surface: Optional[str] = None
    external_deadline: bool = False
    due_at: Optional[str] = None
    receipt_verified: Optional[bool] = None
    execution_requirements: Optional[List[ExecutionRequirement]] = None
    claude_tier: Optional[str] = None
    depends_on: List[str] = Field(default_factory=list)
    created: date
    updated: Optional[datetime] = None
    dispatch_log: List[DispatchLogEntry] = Field(default_factory=list)

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of {', '.join(sorted(VALID_PRIORITIES))}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {', '.join(sorted(VALID_STATUSES))}")
        return v

    @field_validator("target_agent")
    @classmethod
    def validate_target_agent(cls, v: str) -> str:
        if v not in VALID_AGENTS:
            raise ValueError(f"target_agent must be one of {', '.join(sorted(VALID_AGENTS))}")
        return v


class BudgetTrack(BaseModel):
    model_config = ConfigDict(extra="allow")

    date: str
    spent: int = 0
    per_agent: Dict[str, int] = Field(default_factory=dict)
    per_agent_reset: Dict[str, str] = Field(default_factory=dict)


class Budget(BaseModel):
    model_config = ConfigDict(extra="allow")

    daily: int = 100
    unit: str = "runs"
    per_agent: Dict[str, int] = Field(default_factory=dict)
    track: BudgetTrack = Field(default_factory=lambda: BudgetTrack(date=""))


class Portal(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = "Universal Task Intake"
    description: str = ""
    budget: Budget = Field(default_factory=Budget)
    agents: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class LimenFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str = "1.0"
    portal: Portal = Field(default_factory=Portal)
    tasks: List[Task] = Field(default_factory=list)


# -- Server State -----------------------------------------------------------

CIRCUIT_BREAKER_TRIPPED = False
TASK_LOOP_TRACKER: Dict[str, int] = {}
STATE_FILE = Path.home() / "Workspace" / "limen" / ".mcp_state.json"


def _load_state():
    global CIRCUIT_BREAKER_TRIPPED, TASK_LOOP_TRACKER
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
                CIRCUIT_BREAKER_TRIPPED = state.get("circuit_breaker", False)
                TASK_LOOP_TRACKER = state.get("task_loops", {})
        except Exception:
            pass


def _save_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"circuit_breaker": CIRCUIT_BREAKER_TRIPPED, "task_loops": TASK_LOOP_TRACKER}, f)
    except Exception:
        pass


_load_state()


def _check_circuit_breaker():
    if CIRCUIT_BREAKER_TRIPPED:
        raise RuntimeError(
            "SYSTEM OFFLINE - GO TO SLEEP. Circuit breaker is tripped due to API rate limits or severance."
        )


def _get_tasks_path() -> Path:
    p = os.environ.get("LIMEN_TASKS")
    if p:
        return Path(p)
    default_path = Path.home() / "Workspace" / "limen" / "tasks.yaml"
    if default_path.exists():
        return default_path
    return Path("tasks.yaml")


def _load_data() -> LimenFile:
    path = _get_tasks_path()
    if not path.exists():
        return LimenFile()
    with open(path) as f:
        data = yaml.safe_load(f) or {}  # empty / comment-only file → None; avoid LimenFile(**None) TypeError
    return LimenFile(**data)


def _conduct_client():
    """Resolve the authenticated broker for each call; never cache credentials in process state."""

    return client_from_env()


def _mcp_identity(agent: str | None = None, *, session_suffix: str = "mcp") -> AgentIdentityV1:
    resolved_agent = os.environ.get("LIMEN_AGENT") or agent or "opencode"
    session_id = os.environ.get("LIMEN_SESSION_ID") or f"{session_suffix}-{resolved_agent}"
    return AgentIdentityV1(
        agent=resolved_agent,
        surface="mcp",
        session_id=session_id,
        native_run_id=os.environ.get("LIMEN_RUN_ID"),
    )


def _register_submitter(client, identity: AgentIdentityV1) -> None:
    client.register(
        ConductorSessionV1(
            session_id=identity.session_id,
            identity=identity,
            origin="relay",
            native_session_id=os.environ.get("LIMEN_NATIVE_SESSION_ID"),
            native_run_id=identity.native_run_id,
            worktree=os.environ.get("LIMEN_WORKTREE"),
            capabilities=frozenset({"task-submit"}),
            transport="mcp",
            heartbeat_at=datetime.now(timezone.utc),
        )
    )


def _board_owner() -> str:
    repo = os.environ.get("LIMEN_GITHUB_REPO", "organvm/limen").strip()
    return repo if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) else "organvm/limen"


def _task_packet(
    *,
    action: str,
    task_id: str,
    payload: dict[str, Any],
    identity: AgentIdentityV1,
    work_discriminator: dict[str, Any],
) -> WorkPacketV1:
    digest = canonical_hash(work_discriminator)[:20]
    owner = _board_owner()
    work_id = f"mcp-{action.replace('.', '-')}-{task_id}-{digest}"
    return WorkPacketV1(
        work_id=work_id,
        work_key=work_id,
        intent={"kind": action, "task_id": task_id, **payload},
        execution={
            "adapter": "tabularius",
            "projection": "tasks.yaml",
            "observed_heads": {},
        },
        initiator=identity,
        conductor=identity,
        preferred_agent="tabularius",
        required_capabilities=frozenset({"board-write"}),
        resource_claims=(ResourceClaimV1(key=f"task/{task_id}", mode="exclusive"),),
        predicate="python3 scripts/validate-task-board.py --tasks tasks.yaml",
        receipt_target=f"git:{owner}:tasks.yaml#{task_id}",
        authority=AuthorityEnvelopeV1(
            actions=frozenset({action}),
            repositories=frozenset({owner}),
            path_prefixes=frozenset({"tasks.yaml"}),
            may_delegate=False,
        ),
        deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
        spend=SpendEnvelopeV1(limit=0),
        effect="write",
        task_id=task_id,
    )


def _task_revision(task: Task) -> str:
    value: Any = task.updated
    if value is None and task.dispatch_log:
        value = task.dispatch_log[-1].timestamp
    if value is None:
        value = task.created or task.status
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value.isoformat() if isinstance(value, date) else str(value)


def _submit_task_event(packet: WorkPacketV1) -> dict[str, Any]:
    client = _conduct_client()
    _register_submitter(client, packet.conductor)
    return client.submit(packet)


def _submission_message(action: str, task_id: str, result: dict[str, Any]) -> str:
    status = str(result.get("status") or "unknown")
    receipt = result.get("run_id") or result.get("busy_receipt_id") or "unavailable"
    return f"{action} {task_id} via conduct broker (status={status}, receipt={receipt})"


@mcp.tool()
def trip_circuit_breaker() -> str:
    """Manually trip the circuit breaker to offline the swarm and protect from API bans."""
    global CIRCUIT_BREAKER_TRIPPED
    CIRCUIT_BREAKER_TRIPPED = True
    _save_state()
    return "Circuit breaker TRIPPED. System offline."


@mcp.tool()
def reset_circuit_breaker() -> str:
    """Reset the circuit breaker to bring the swarm back online."""
    global CIRCUIT_BREAKER_TRIPPED
    CIRCUIT_BREAKER_TRIPPED = False
    _save_state()
    return "Circuit breaker RESET. System online."


# -- Symmetric conduct protocol ---------------------------------------------------------------


@mcp.tool()
def conduct_capabilities() -> dict:
    """Return live broker-derived lane capabilities and health."""

    _check_circuit_breaker()
    return _conduct_client().capabilities()


@mcp.tool()
def conduct_register(session: Dict[str, Any]) -> dict:
    """Register a direct, dispatched, or relay conductor session."""

    _check_circuit_breaker()
    return _conduct_client().register(ConductorSessionV1.model_validate(session))


@mcp.tool()
def conduct_submit(packet: Dict[str, Any]) -> dict:
    """Submit one bounded root work packet to the shared keeper."""

    _check_circuit_breaker()
    return _conduct_client().submit(WorkPacketV1.model_validate(packet))


@mcp.tool()
def conduct_split(parent_run: str, packet: Dict[str, Any]) -> dict:
    """Submit one authority-attenuated child packet under an existing run."""

    _check_circuit_breaker()
    return _conduct_client().split(parent_run, WorkPacketV1.model_validate(packet))


@mcp.tool()
def conduct_graph(root_run: str) -> dict:
    """Inspect the bounded delegation DAG for one root run."""

    _check_circuit_breaker()
    return _conduct_client().graph(root_run)


@mcp.tool()
def conduct_heartbeat(
    lease: str,
    generation: int,
    capability_token: str,
    observed_heads: Optional[Dict[str, str]] = None,
) -> dict:
    """Renew a lease while fencing any moved exact Git heads."""

    _check_circuit_breaker()
    return _conduct_client().heartbeat(
        lease,
        capability_token,
        generation=generation,
        observed_heads=observed_heads or {},
    )


@mcp.tool()
def conduct_report(
    lease: str,
    generation: int,
    capability_token: str,
    receipt: Dict[str, Any],
) -> dict:
    """Submit a schema-validated terminal receipt; late results remain evidence-only."""

    _check_circuit_breaker()
    return _conduct_client().report(
        lease,
        capability_token,
        RunReceiptV1.model_validate(receipt),
        generation=generation,
    )


@mcp.tool()
def conduct_harvest(root_run: str) -> dict:
    """Collect graph outcomes and unharvested children for a root run."""

    _check_circuit_breaker()
    return _conduct_client().harvest(root_run)


@mcp.tool()
def conduct_adopt(run: str, session_id: str) -> dict:
    """Adopt a graph only after the broker proves the prior conductor absent."""

    _check_circuit_breaker()
    return _conduct_client().adopt(run, session_id)


@mcp.tool()
def conduct_cancel(run: str, session_id: str) -> dict:
    """Cancel only reserved, not-started work."""

    _check_circuit_breaker()
    return _conduct_client().cancel(run, session_id)


@mcp.tool()
def conduct_request_stop(run: str, session_id: str) -> dict:
    """Request cooperative stop for started work; this never signals a peer process."""

    _check_circuit_breaker()
    return _conduct_client().request_stop(run, session_id)


@mcp.tool()
def list_tasks(status: Optional[str] = None, agent: Optional[str] = None) -> List[dict]:
    """List tasks in the pipeline, optionally filtered by status or agent."""
    status = _validate_optional_enum(status, VALID_STATUSES, "status")
    agent = _validate_optional_enum(agent, VALID_AGENTS, "agent")
    _check_circuit_breaker()
    data = _load_data()
    tasks = [t.model_dump() for t in data.tasks]
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    if agent:
        tasks = [t for t in tasks if t["target_agent"] == agent]
    return tasks


@mcp.tool()
def get_task(task_id: str) -> dict:
    """Get details for a specific task by ID."""
    task_id = _validate_task_id(task_id)
    _check_circuit_breaker()

    # Layer 3: Hard Loop Limits
    TASK_LOOP_TRACKER[task_id] = TASK_LOOP_TRACKER.get(task_id, 0) + 1
    _save_state()
    if TASK_LOOP_TRACKER[task_id] > 3:
        raise ValueError(
            f"HARD LOOP LIMIT REACHED: Task {task_id} requested >3 times today. Moving to 'needs_human'. Abandon task immediately."
        )

    data = _load_data()
    for t in data.tasks:
        if t.id == task_id:
            return t.model_dump()
    raise ValueError(f"Task {task_id} not found")


@mcp.tool()
def add_task(
    title: str,
    repo: str,
    predicate: str,
    receipt_target: str,
    value_case: str,
    agent: str = "jules",
    priority: str = "medium",
    budget_cost: int = 1,
    origin: str = "human_prompt",
    horizon: str = "present",
    owner_surface: str | None = None,
    external_deadline: bool = False,
    due_at: str | None = None,
) -> str:
    """Add a new task to the pipeline."""
    title = _validate_text(title, "title", 512)
    repo = _validate_text(repo, "repo", 256)
    value_case = _validate_text(value_case, "value_case", 8192)
    agent = _validate_optional_enum(agent, VALID_AGENTS, "agent") or "jules"
    priority = _validate_optional_enum(priority, VALID_PRIORITIES, "priority") or "medium"
    origin = _validate_optional_enum(origin, VALID_WORK_ORIGINS, "origin") or "human_prompt"
    horizon = _validate_optional_enum(horizon, VALID_WORK_HORIZONS, "horizon") or "present"
    if owner_surface is not None:
        owner_surface = _validate_text(owner_surface, "owner_surface", 8192)
    if due_at is not None:
        due_at = _validate_text(due_at, "due_at", 128)
    if type(external_deadline) is not bool:
        raise ValueError("external_deadline must be a boolean")
    if type(budget_cost) is not int or budget_cost < 1 or budget_cost > 100:
        raise ValueError("budget_cost must be an integer between 1 and 100")
    WorkLoanV1(
        source_origin=origin,
        horizon=horizon,
        value_case=value_case,
        budget_cost=budget_cost,
        owner_surface=owner_surface or repo,
        external_deadline=external_deadline,
        due_at=due_at,
    )
    _check_circuit_breaker()
    data = _load_data()

    last_num = 0
    for t in data.tasks:
        if t.id.startswith("LIMEN-"):
            try:
                num = int(t.id.split("-")[1])
                if num > last_num:
                    last_num = num
            except ValueError:
                pass
    new_id = f"LIMEN-{last_num + 1:03d}"

    new_task = Task(
        id=new_id,
        title=title,
        repo=repo,
        target_agent=agent,
        priority=priority,
        budget_cost=budget_cost,
        status="open",
        predicate=predicate,
        receipt_target=receipt_target,
        origin=origin,
        horizon=horizon,
        value_case=value_case,
        owner_surface=owner_surface,
        external_deadline=external_deadline,
        due_at=due_at,
        created=date.today(),
    )
    validate_intake_contract(new_task, is_new=True)
    identity = _mcp_identity(agent, session_suffix="mcp-add")
    fields = new_task.model_dump(mode="json", exclude_none=True)
    packet = _task_packet(
        action="task.upsert",
        task_id=new_id,
        payload={"task": fields, "expected_absent": True},
        identity=identity,
        work_discriminator=fields,
    )
    result = _submit_task_event(packet)
    return _submission_message("submitted task upsert", new_id, result)


@mcp.tool()
def update_task_status(
    task_id: str,
    status: str,
    context: Optional[str] = None,
    predicate: Optional[str] = None,
    receipt_target: Optional[str] = None,
) -> str:
    """Update the status and context of a task. Allows 'failed_blocked' to evict dependencies."""
    task_id = _validate_task_id(task_id)
    status = _validate_optional_enum(status, VALID_STATUSES, "status") or status
    if context is not None:
        context = _validate_text(context, "context", 10000)
    _check_circuit_breaker()
    data = _load_data()

    for t in data.tasks:
        if t.id == task_id:
            prior_fields = t.model_dump(mode="json", exclude_none=True)
            updated_fields: dict[str, Any] = {"status": status}
            if WORKSTREAM_SUCCESSOR_REQUIRED_LABEL in (t.labels or []) and status not in {"failed", "done", "archived"}:
                return (
                    f"Task {task_id} requires a separately admitted successor; "
                    f"cannot transition expired row to {status}"
                )
            # Layer 1: Dynamic Costing - Double budget cost on failure
            if status in ["failed", "failed_blocked", "needs_human"] and t.status == "in_progress":
                updated_fields["budget_cost"] = min(t.budget_cost * 2, 8)
            if context:
                updated_fields["context"] = context
            if predicate is not None:
                updated_fields["predicate"] = predicate
            if receipt_target is not None:
                updated_fields["receipt_target"] = receipt_target
            prospective = t.model_copy(update=updated_fields)
            validate_intake_contract(prospective)
            identity = _mcp_identity(session_suffix="mcp-status")
            packet = _task_packet(
                action="task.status",
                task_id=task_id,
                payload={
                    "expected_status": t.status,
                    "expected_revision": _task_revision(t),
                    "patch": updated_fields,
                    "log": {
                        "status": status,
                        "agent": identity.agent,
                        "session_id": identity.session_id,
                        "output": context,
                    },
                },
                identity=identity,
                work_discriminator={"prior": prior_fields, "patch": updated_fields},
            )
            result = _submit_task_event(packet)
            return _submission_message(f"submitted status {status} for", task_id, result)

    raise ValueError(f"Task {task_id} not found")


@mcp.tool()
def get_budget_status() -> dict:
    """Get current budget tracking information."""
    _check_circuit_breaker()
    data = _load_data()
    return data.portal.budget.model_dump()


# -- Agent Presence / Coordination Tools ------------------------------------


def _agents_dir() -> Path:
    return _get_tasks_path().parent / "logs" / "agents"


@mcp.tool()
def agent_available(agent: Optional[str] = None) -> List[dict]:
    """Query agent presence beacons. Returns status of all agents or a specific agent.
    Each beacon contains: status (idle|working|throttled), accepting_tasks,
    available_tokens, token_usage_pct, clock_health, heartbeat."""
    agent = _validate_optional_enum(agent, CLAIMABLE_AGENTS, "agent")
    _check_circuit_breaker()
    agents_dir = _agents_dir()
    if not agents_dir.exists():
        return []
    results = []
    try:
        for f in agents_dir.glob("*.json"):
            name = f.stem
            if agent is not None and name != agent:
                continue
            try:
                data = json.loads(f.read_text())
                data["_source"] = str(f)
                results.append(data)
            except Exception:
                pass
    except Exception:
        pass
    return results


@mcp.tool()
def agent_claim(task_id: str, agent_name: str = "opencode") -> str:
    """Submit one atomically leased task claim through the shared broker."""
    task_id = _validate_task_id(task_id)
    agent_name = _validate_optional_enum(agent_name, CLAIMABLE_AGENTS, "agent_name") or agent_name
    _check_circuit_breaker()
    data = _load_data()

    for t in data.tasks:
        if t.id == task_id:
            if t.status != "open":
                return f"Task {task_id} is not open (current status: {t.status}) - cannot claim"
            if WORKSTREAM_SUCCESSOR_REQUIRED_LABEL in (t.labels or []):
                return f"Task {task_id} requires a separately admitted successor - cannot claim expired row"
            if t.target_agent not in (agent_name, "any"):
                return f"Task {task_id} targets {t.target_agent}, not {agent_name} - cannot claim"

            underwriting = task_work_loan_readiness(t)
            if not underwriting.ready:
                return f"{underwriting.reason_code} - cannot claim"

            readiness = runtime_requirements.evaluate_execution_requirements(t)
            if not readiness.ready:
                reason = "; ".join(readiness.blockers)
                return f"Task {task_id} runtime requirements unavailable: {reason} - cannot claim"

            normalize_selected_legacy_task(t)
            identity = _mcp_identity(agent_name, session_suffix="mcp-claim")
            prior_fields = t.model_dump(mode="json", exclude_none=True)
            patch = {
                "status": "dispatched",
                "target_agent": agent_name,
                "predicate": t.predicate,
                "receipt_target": t.receipt_target,
            }
            packet = _task_packet(
                action="task.claim",
                task_id=task_id,
                payload={
                    "expected_status": "open",
                    "expected_revision": _task_revision(t),
                    "patch": patch,
                    "log": {
                        "status": "dispatched",
                        "agent": agent_name,
                        "session_id": identity.session_id,
                        "output": f"Claimed by {agent_name} via MCP conduct broker",
                    },
                },
                identity=identity,
                work_discriminator={"prior": prior_fields, "patch": patch},
            )
            result = _submit_task_event(packet)
            return _submission_message(f"submitted claim for {agent_name} on", task_id, result)

    raise ValueError(f"Task {task_id} not found")


if __name__ == "__main__":
    transport = os.environ.get("LIMEN_MCP_TRANSPORT", "stdio")
    mount_path = os.environ.get("LIMEN_MCP_MOUNT_PATH", "/mcp")
    if transport == "streamable-http":
        mcp.run(transport="streamable-http", mount_path=mount_path)
    else:
        mcp.run()
