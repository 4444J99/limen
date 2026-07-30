"""Authenticated, provider-neutral full-mesh conduct canary.

The canary is deliberately a protocol client, not a provider launcher.  It
discovers the currently registered native lane denominator from the remote
keeper, then exercises every ordered conductor -> executor edge with a
bounded read-effect packet.  Secret values remain process-local; the public
receipt carries only credential reference names and SHA-256 evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from limen.conduct.broker import ConductError
from limen.conduct.client import HttpConductClient
from limen.conduct.models import (
    AgentIdentityV1,
    AuthorityEnvelopeV1,
    CheckEvidenceV1,
    FanoutBoundsV1,
    PredicateEvidenceV1,
    RetryPolicyV1,
    RunReceiptV1,
    SpendEnvelopeV1,
    WorkPacketV1,
    canonical_hash,
)
from limen.work_loan import WorkLoanV1


CANARY_SCHEMA = "limen.conduct_full_mesh_canary.v1"
CREDENTIAL_REFS_ENV = "LIMEN_CONDUCT_CANARY_CREDENTIAL_REFS"
RUNTIME_IDENTITY_ENV = "LIMEN_CONDUCT_CANARY_RUNTIME_IDENTITY"
_CREDENTIAL_REFS_SCHEMA = "limen.conduct_canary_credential_refs.v1"
_RUNTIME_IDENTITY_SCHEMA = "limen.conduct_runtime_identity.v1"
_TOKEN_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")
_GIT_OBJECT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_MAX_LANES = 16
_MAX_RECEIPT_BYTES = 4 * 1024 * 1024
_EDGE_DEADLINE = timedelta(minutes=15)
_MAX_DEADLINE_SKEW = timedelta(minutes=5)
_PATH_LOCK_TIMEOUT_SECONDS = 10.0
_PATH_LOCK_POLL_SECONDS = 0.01
_PREDICATE = "limen conduct canary full-mesh --receipt canary.json"
_PREDICATE_SUMMARY = "bounded authenticated read-effect canary edge"


class ConductCanaryError(ConductError):
    """A public, secret-free canary failure."""


@dataclass(frozen=True)
class _CredentialRef:
    session_id: str
    role: str
    token_env: str
    token: str  # allow-secret: process-local value hydrated from a named environment reference
    token_sha256: str


@dataclass(frozen=True)
class _Lane:
    name: str
    conductor_session: dict[str, Any]
    executor_session: dict[str, Any]
    conductor_credential: _CredentialRef
    executor_credential: _CredentialRef


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_json_env(name: str, environ: Mapping[str, str]) -> dict[str, Any]:
    raw = environ.get(name, "").strip()
    if not raw:
        raise ConductCanaryError(f"{name} is required")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConductCanaryError(f"{name} must contain valid JSON") from exc
    if not isinstance(value, dict):
        raise ConductCanaryError(f"{name} must contain a JSON object")
    return value


def _runtime_identity(environ: Mapping[str, str]) -> dict[str, str]:
    value = _load_json_env(RUNTIME_IDENTITY_ENV, environ)
    if set(value) != {"schema_version", "git_sha", "deployment_id"}:
        raise ConductCanaryError(f"{RUNTIME_IDENTITY_ENV} must contain only schema_version, git_sha, and deployment_id")
    if value.get("schema_version") != _RUNTIME_IDENTITY_SCHEMA:
        raise ConductCanaryError(f"{RUNTIME_IDENTITY_ENV} has an unsupported schema")
    git_sha = str(value.get("git_sha") or "")
    deployment_id = str(value.get("deployment_id") or "")
    if not _GIT_OBJECT_RE.fullmatch(git_sha):
        raise ConductCanaryError("runtime git_sha must be an exact lowercase Git object ID")
    if not deployment_id or "\x00" in deployment_id or len(deployment_id) > 512:
        raise ConductCanaryError("runtime deployment_id must be a non-empty bounded string")
    return {"git_sha": git_sha, "deployment_id": deployment_id}


def _credential_refs(
    environ: Mapping[str, str],
) -> tuple[_CredentialRef, ...]:
    value = _load_json_env(CREDENTIAL_REFS_ENV, environ)
    if set(value) != {"schema_version", "credentials"}:
        raise ConductCanaryError(f"{CREDENTIAL_REFS_ENV} must contain only schema_version and credentials")
    if value.get("schema_version") != _CREDENTIAL_REFS_SCHEMA:
        raise ConductCanaryError(f"{CREDENTIAL_REFS_ENV} has an unsupported schema")
    rows = value.get("credentials")
    if not isinstance(rows, list) or not rows or len(rows) > _MAX_LANES * 2:
        raise ConductCanaryError("credential references must be a bounded non-empty list")

    refs: list[_CredentialRef] = []
    seen_bindings: set[tuple[str, str]] = set()
    seen_envs: set[str] = set()
    seen_hashes: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"session_id", "role", "token_env"}:
            raise ConductCanaryError("credential references must contain only session_id, role, and token_env")
        session_id = str(row.get("session_id") or "")
        role = str(row.get("role") or "")
        token_env = str(row.get("token_env") or "")
        if not _IDENTIFIER_RE.fullmatch(session_id):
            raise ConductCanaryError("credential reference session_id is invalid")
        if role not in {"conductor", "executor"}:
            raise ConductCanaryError("credential reference role must be conductor or executor")
        if not _TOKEN_ENV_RE.fullmatch(token_env):
            raise ConductCanaryError("credential reference token_env is invalid")
        binding = (session_id, role)
        if binding in seen_bindings or token_env in seen_envs:
            raise ConductCanaryError("credential references must be unique")
        token = environ.get(token_env, "").strip()  # allow-secret: environment reference only
        if not token:
            raise ConductCanaryError(f"credential reference {token_env} is not hydrated")
        token_sha256 = _sha256_text(token)
        if token_sha256 in seen_hashes:
            raise ConductCanaryError("every canary role requires a distinct authenticated credential")
        seen_bindings.add(binding)
        seen_envs.add(token_env)
        seen_hashes.add(token_sha256)
        refs.append(
            _CredentialRef(
                session_id=session_id,
                role=role,
                token_env=token_env,
                token=token,  # allow-secret: process-local transport credential, never serialized
                token_sha256=token_sha256,
            )
        )
    return tuple(refs)


def _eligible_session(row: dict[str, Any], capability: str) -> bool:
    capabilities = row.get("capabilities")
    return bool(
        row.get("healthy") is True
        and row.get("accepting_work") is True
        and row.get("human_protected") is not True
        and isinstance(capabilities, list)
        and capability in capabilities
        and (capability != "execute" or row.get("quota_remaining") != 0)
    )


def _discover_lanes(
    capabilities: dict[str, Any],
    refs: tuple[_CredentialRef, ...],
) -> tuple[_Lane, ...]:
    if capabilities.get("schema_version") != "limen.conduct_capabilities.v1":
        raise ConductCanaryError("remote keeper returned an unsupported capabilities schema")
    raw_sessions = capabilities.get("sessions")
    if not isinstance(raw_sessions, list) or len(raw_sessions) > 4096:
        raise ConductCanaryError("remote keeper returned an invalid session catalog")

    sessions: dict[str, dict[str, Any]] = {}
    conductor_agents: set[str] = set()
    executor_agents: set[str] = set()
    for raw in raw_sessions:
        if not isinstance(raw, dict):
            raise ConductCanaryError("remote keeper returned a malformed session")
        session_id = str(raw.get("session_id") or "")
        identity_raw = raw.get("identity")
        try:
            identity = AgentIdentityV1.model_validate(identity_raw)
        except ValueError as exc:
            raise ConductCanaryError("remote keeper returned a malformed session identity") from exc
        if identity.session_id != session_id or session_id in sessions:
            raise ConductCanaryError("remote keeper returned duplicate or mismatched sessions")
        normalized_session: dict[str, Any] = dict(raw)
        normalized_session["identity"] = identity.model_dump(mode="json")
        sessions[session_id] = normalized_session
        if _eligible_session(normalized_session, "conduct"):
            conductor_agents.add(identity.agent)
        if _eligible_session(normalized_session, "execute"):
            executor_agents.add(identity.agent)

    denominator = conductor_agents & executor_agents
    if not denominator:
        raise ConductCanaryError("no complete native conductor/executor lane is live")
    if len(denominator) > _MAX_LANES:
        raise ConductCanaryError(f"live canary denominator exceeds {_MAX_LANES} lanes")

    selected: dict[tuple[str, str], tuple[dict[str, Any], _CredentialRef]] = {}
    for ref in refs:
        session = sessions.get(ref.session_id)
        if session is None:
            raise ConductCanaryError("credential reference names a session absent from live capabilities")
        capability = "conduct" if ref.role == "conductor" else "execute"
        if not _eligible_session(session, capability):
            raise ConductCanaryError(f"credential reference names a session ineligible for the {ref.role} role")
        agent = str(session["identity"]["agent"])
        key = (agent, ref.role)
        if key in selected:
            raise ConductCanaryError("each native lane must have exactly one credential per role")
        selected[key] = (session, ref)

    configured_agents = {agent for agent, _role in selected}
    if configured_agents != denominator:
        raise ConductCanaryError("credential references must cover every complete live native lane and no others")

    lanes: list[_Lane] = []
    for agent in sorted(denominator):
        conductor = selected.get((agent, "conductor"))
        executor = selected.get((agent, "executor"))
        if conductor is None or executor is None:
            raise ConductCanaryError(f"native lane {agent} lacks a distinct conductor/executor credential")
        if conductor[0]["session_id"] == executor[0]["session_id"]:
            raise ConductCanaryError(f"native lane {agent} must use distinct role sessions")
        lanes.append(
            _Lane(
                name=agent,
                conductor_session=conductor[0],
                executor_session=executor[0],
                conductor_credential=conductor[1],
                executor_credential=executor[1],
            )
        )
    return tuple(lanes)


def _stable_session_identity(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": session["session_id"],
        "identity": session["identity"],
        "capabilities": sorted(session.get("capabilities") or []),
        "transport": session.get("transport"),
        "harvest_method": session.get("harvest_method"),
    }


def _public_lane(lane: _Lane) -> dict[str, Any]:
    return {
        "lane": lane.name,
        "conductor_session_sha256": _sha256_text(lane.conductor_session["session_id"]),
        "executor_session_sha256": _sha256_text(lane.executor_session["session_id"]),
        "conductor_credential_ref": lane.conductor_credential.token_env,
        "conductor_credential_sha256": lane.conductor_credential.token_sha256,
        "executor_credential_ref": lane.executor_credential.token_env,
        "executor_credential_sha256": lane.executor_credential.token_sha256,
    }


def _capabilities_evidence_sha256(lanes: tuple[_Lane, ...]) -> str:
    return canonical_hash(
        [
            {
                "lane": lane.name,
                "conductor": _stable_session_identity(lane.conductor_session),
                "executor": _stable_session_identity(lane.executor_session),
            }
            for lane in lanes
        ]
    )


def _canary_identity(
    client: HttpConductClient,
    runtime: dict[str, str],
    lanes: tuple[_Lane, ...],
) -> tuple[str, dict[str, Any]]:
    implementation_sha256 = _sha256_bytes(Path(__file__).read_bytes())
    private_identity = {
        "endpoint": client.endpoint,
        "runtime": runtime,
        "implementation_sha256": implementation_sha256,
        "lanes": [
            {
                "lane": lane.name,
                "conductor": _stable_session_identity(lane.conductor_session),
                "executor": _stable_session_identity(lane.executor_session),
                "conductor_credential_ref": lane.conductor_credential.token_env,
                "conductor_credential_sha256": lane.conductor_credential.token_sha256,
                "executor_credential_ref": lane.executor_credential.token_env,
                "executor_credential_sha256": lane.executor_credential.token_sha256,
            }
            for lane in lanes
        ],
    }
    canary_id = canonical_hash(private_identity)
    public_runtime = {
        "git_sha": runtime["git_sha"],
        "deployment_id_sha256": _sha256_text(runtime["deployment_id"]),
        "endpoint_sha256": _sha256_text(client.endpoint),
        "cli_implementation_sha256": implementation_sha256,
        "identity_sha256": canonical_hash(private_identity),
    }
    return canary_id, public_runtime


def _packet(
    *,
    canary_id: str,
    edge_id: str,
    conductor: _Lane,
    executor: _Lane,
    runtime_git_sha: str,
    now: datetime,
) -> WorkPacketV1:
    work_id = f"canary-{canary_id[:20]}-{edge_id[:20]}"
    identity = AgentIdentityV1.model_validate(conductor.conductor_session["identity"])
    return WorkPacketV1(
        work_id=work_id,
        work_key=f"conduct-canary:{canary_id}:{edge_id}",
        intent={
            "kind": "conduct-full-mesh-canary",
            "canary_id": canary_id,
            "edge_id": edge_id,
            "effect": "bounded-read",
        },
        execution={
            "executor_session_id": executor.executor_session["session_id"],
            "observed_heads": {"runtime": runtime_git_sha},
        },
        initiator=identity,
        conductor=identity,
        preferred_agent=executor.name,
        required_capabilities=frozenset({"execute"}),
        resource_claims=(),
        predicate=_PREDICATE,
        receipt_target=(f"git:organvm/limen:docs/receipts/conduct-full-mesh.json#{canary_id[:20]}-{edge_id[:20]}"),
        work_loan=WorkLoanV1(
            source_origin="human_prompt",
            horizon="present",
            value_case="Prove one bounded authenticated peer-conduct mesh edge",
            budget_cost=1,
            owner_surface="organvm/limen",
        ),
        authority=AuthorityEnvelopeV1(
            actions=frozenset({"read"}),
            repositories=frozenset(),
            path_prefixes=frozenset(),
            external_effects=frozenset(),
            may_delegate=False,
        ),
        deadline=now + _EDGE_DEADLINE,
        spend=SpendEnvelopeV1(unit="runs", limit=1, reserve=0),
        retry=RetryPolicyV1(max_attempts=1, transient_only=True),
        fanout=FanoutBoundsV1(max_children=0, max_depth=0),
        effect="read",
    )


def _executor_only_rejection(exc: ConductError) -> bool:
    detail = str(exc).casefold()
    return (
        "lacks required executor" in detail
        or "another executor principal" in detail
        or ("403" in detail and ("executor" in detail or "principal" in detail))
    )


def _edge_id(canary_id: str, conductor: _Lane, executor: _Lane) -> str:
    return canonical_hash(
        {
            "canary_id": canary_id,
            "conductor_lane": conductor.name,
            "executor_lane": executor.name,
            "conductor_session": conductor.conductor_session["session_id"],
            "executor_session": executor.executor_session["session_id"],
        }
    )


def _expected_run_id(packet: WorkPacketV1) -> str:
    digest = canonical_hash(
        {
            "work_id": packet.work_id,
            "intent_hash": packet.intent_hash,
            "execution_hash": packet.execution_hash,
        }
    )
    return f"run-{digest[:32]}"


def _claim_evidence_sha256(
    *,
    edge_id: str,
    run_id: str,
    lease: dict[str, Any],
    executor_session_id: str,
) -> str:
    return canonical_hash(
        {
            "schema_version": "limen.conduct_canary_executor_claim_evidence.v1",
            "edge_id": edge_id,
            "run_id": run_id,
            "lease_id": lease["lease_id"],
            "lease_generation": lease["generation"],
            "executor_session_id": executor_session_id,
        }
    )


def _heartbeat_evidence_sha256(
    *,
    edge_id: str,
    run_id: str,
    lease: dict[str, Any],
    executor_session_id: str,
    runtime_git_sha: str,
) -> str:
    return canonical_hash(
        {
            "schema_version": "limen.conduct_canary_heartbeat_evidence.v1",
            "edge_id": edge_id,
            "run_id": run_id,
            "lease_id": lease["lease_id"],
            "lease_generation": lease["generation"],
            "executor_session_id": executor_session_id,
            "observed_heads": {"runtime": runtime_git_sha},
        }
    )


def _expected_checks(
    *,
    edge_id: str,
    run_id: str,
    lease: dict[str, Any],
    executor_session_id: str,
    runtime_git_sha: str,
) -> tuple[CheckEvidenceV1, ...]:
    return (
        CheckEvidenceV1(
            name="conduct-canary-executor-claim",
            status="success",
            head=_claim_evidence_sha256(
                edge_id=edge_id,
                run_id=run_id,
                lease=lease,
                executor_session_id=executor_session_id,
            ),
        ),
        CheckEvidenceV1(
            name="conduct-canary-heartbeat",
            status="success",
            head=_heartbeat_evidence_sha256(
                edge_id=edge_id,
                run_id=run_id,
                lease=lease,
                executor_session_id=executor_session_id,
                runtime_git_sha=runtime_git_sha,
            ),
        ),
    )


def _parse_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ConductCanaryError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ConductCanaryError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ConductCanaryError(f"{label} must include a timezone")
    return parsed


def _canonical_timestamp(value: Any, label: str) -> str:
    return _parse_timestamp(value, label).astimezone(timezone.utc).isoformat()


def _canonical_datetime(value: datetime, label: str) -> str:
    if value.tzinfo is None:
        raise ConductCanaryError(f"{label} must include a timezone")
    return value.astimezone(timezone.utc).isoformat()


def _validate_packet_contract(
    raw_packet: Any,
    *,
    expected: WorkPacketV1,
    created_at: Any,
    require_exact_deadline: bool = False,
) -> WorkPacketV1:
    try:
        stored = WorkPacketV1.model_validate(raw_packet)
    except ValueError as exc:
        raise ConductCanaryError("harvested canary packet is malformed") from exc
    compared_fields = tuple(field for field in WorkPacketV1.model_fields if field != "deadline")
    if any(getattr(stored, field) != getattr(expected, field) for field in compared_fields):
        raise ConductCanaryError("harvested canary packet does not match the expected edge contract")
    if require_exact_deadline and stored.deadline != expected.deadline:
        raise ConductCanaryError("harvested canary packet deadline does not match the receipt observation")
    created = _parse_timestamp(created_at, "harvested run created_at")
    if stored.deadline <= created or stored.deadline > created + _EDGE_DEADLINE + _MAX_DEADLINE_SKEW:
        raise ConductCanaryError("harvested canary packet deadline is outside the bounded edge window")
    return stored


def _validate_submit_result(
    result: dict[str, Any],
    *,
    packet: WorkPacketV1,
    executor: _Lane,
) -> tuple[str, dict[str, Any]]:
    expected_keys = {
        "schema_version",
        "status",
        "run_id",
        "root_run_id",
        "executor_session_id",
        "lease",
    }
    if not isinstance(result, dict) or set(result) != expected_keys:
        raise ConductCanaryError("keeper returned a malformed canary submit result")
    if result.get("schema_version") != "limen.conduct_submit_result.v1":
        raise ConductCanaryError("keeper returned an unsupported canary submit schema")
    status = str(result.get("status") or "")
    if status not in {"reserved", "duplicate"}:
        raise ConductCanaryError("canary edge did not receive a reservation or deterministic duplicate")
    run_id = _expected_run_id(packet)
    if result.get("run_id") != run_id or result.get("root_run_id") != run_id:
        raise ConductCanaryError("keeper returned the wrong deterministic canary run")
    executor_session_id = executor.executor_session["session_id"]
    if result.get("executor_session_id") != executor_session_id:
        raise ConductCanaryError("keeper bound the canary edge to the wrong executor session")
    lease = result.get("lease")
    if not isinstance(lease, dict):
        raise ConductCanaryError("keeper returned an invalid canary lease")
    if "capability_token" in result or "capability_token_hash" in lease or "executor_principal_id" in lease:
        raise ConductCanaryError("reservation disclosed executor-only capability material")
    return status, lease


def _validate_harvest_node(
    harvest: dict[str, Any],
    *,
    packet: WorkPacketV1,
    conductor: _Lane,
    executor: _Lane,
    runtime_git_sha: str,
    require_exact_deadline: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], WorkPacketV1]:
    run_id = _expected_run_id(packet)
    if not isinstance(harvest, dict) or harvest.get("schema_version") != "limen.conduct_harvest.v1":
        raise ConductCanaryError("conductor returned an unsupported harvest schema")
    if harvest.get("root_run_id") != run_id or harvest.get("run_count") != 1:
        raise ConductCanaryError("conductor harvest did not return the exact canary root")
    nodes = harvest.get("nodes")
    if not isinstance(nodes, list) or len(nodes) != 1:
        raise ConductCanaryError("conductor harvest returned an unexpected graph")
    node = nodes[0]
    if not isinstance(node, dict):
        raise ConductCanaryError("conductor harvest returned a malformed run")
    executor_session_id = executor.executor_session["session_id"]
    if (
        node.get("run_id") != run_id
        or node.get("root_run_id") != run_id
        or node.get("parent_run_id") is not None
        or node.get("conductor_session_id") != conductor.conductor_session["session_id"]
        or node.get("executor_session_id") != executor_session_id
        or node.get("children") != []
        or node.get("attempts") != []
        or node.get("projection_receipts") != []
        or node.get("compatibility_projection") is not False
    ):
        raise ConductCanaryError("harvested canary run does not match the expected edge")
    stored_packet = _validate_packet_contract(
        node.get("packet"),
        expected=packet,
        created_at=node.get("created_at"),
        require_exact_deadline=require_exact_deadline,
    )
    lease = node.get("lease")
    if not isinstance(lease, dict):
        raise ConductCanaryError("harvested canary run lacks its public lease")
    if "capability_token_hash" in lease or "executor_principal_id" in lease:
        raise ConductCanaryError("harvested canary lease disclosed capability material")
    if (
        node.get("lease_id") != lease.get("lease_id")
        or lease.get("run_id") != run_id
        or lease.get("executor") != executor.executor_session["identity"]
        or lease.get("resources") != []
        or lease.get("observed_heads") != {"runtime": runtime_git_sha}
        or not isinstance(lease.get("generation"), int)
        or isinstance(lease.get("generation"), bool)
        or int(lease["generation"]) < 1
    ):
        raise ConductCanaryError("harvested canary lease does not match the expected executor")
    status_pair = (node.get("status"), lease.get("state"))
    if status_pair not in {
        ("reserved", "reserved"),
        ("running", "active"),
        ("succeeded", "released"),
    }:
        raise ConductCanaryError("canary duplicate is not in a recoverable lifecycle state")
    receipts = node.get("receipts")
    if not isinstance(receipts, list):
        raise ConductCanaryError("harvested canary receipts are malformed")
    terminal = status_pair == ("succeeded", "released")
    expected_receipt_count = 1 if terminal else 0
    expected_unharvested = [] if terminal else [run_id]
    if (
        harvest.get("receipt_count") != expected_receipt_count
        or harvest.get("by_status") != {str(node["status"]): 1}
        or harvest.get("unharvested") != expected_unharvested
        or len(receipts) != expected_receipt_count
    ):
        raise ConductCanaryError("canary harvest counts do not match its lifecycle state")
    return node, lease, stored_packet


def _validate_terminal_receipt(
    node: dict[str, Any],
    lease: dict[str, Any],
    *,
    packet: WorkPacketV1,
    edge_id: str,
    executor: _Lane,
    runtime_git_sha: str,
) -> dict[str, Any]:
    raw_receipt = node["receipts"][0]
    if not isinstance(raw_receipt, dict):
        raise ConductCanaryError("harvested canary receipt is malformed")
    receipt_fields = set(RunReceiptV1.model_fields)
    if set(raw_receipt) != receipt_fields | {"mutation_authorized", "accepted_at"}:
        raise ConductCanaryError("harvested canary receipt has an unexpected schema")
    if raw_receipt.get("mutation_authorized") is not True:
        raise ConductCanaryError("harvested canary receipt was not authorized")
    _parse_timestamp(raw_receipt.get("accepted_at"), "harvested receipt accepted_at")
    try:
        receipt = RunReceiptV1.model_validate({field: raw_receipt[field] for field in receipt_fields})
    except ValueError as exc:
        raise ConductCanaryError("harvested canary receipt violates RunReceiptV1") from exc
    run_id = _expected_run_id(packet)
    expected = RunReceiptV1(
        receipt_id=f"receipt-{packet.work_id}",
        run_id=run_id,
        lease_id=str(lease["lease_id"]),
        lease_generation=int(lease["generation"]),
        executor=AgentIdentityV1.model_validate(executor.executor_session["identity"]),
        observed_heads_before={"runtime": runtime_git_sha},
        observed_heads_after={"runtime": runtime_git_sha},
        changed_paths=(),
        predicate=PredicateEvidenceV1(
            command=packet.predicate,
            exit_code=0,
            summary=_PREDICATE_SUMMARY,
            observed_at=receipt.predicate.observed_at,
        ),
        checks=_expected_checks(
            edge_id=edge_id,
            run_id=run_id,
            lease=lease,
            executor_session_id=executor.executor_session["session_id"],
            runtime_git_sha=runtime_git_sha,
        ),
        spend={"runs": 0},
        child_runs=(),
        outcome="succeeded",
        completed_at=receipt.completed_at,
    )
    if receipt != expected:
        raise ConductCanaryError("harvested canary receipt does not match the exact edge proof")
    return raw_receipt


def _conductor_rejection_sha256(client: HttpConductClient, lease: dict[str, Any]) -> str:
    try:
        client.claim(str(lease["lease_id"]), int(lease["generation"]))
    except ConductError as exc:
        if not _executor_only_rejection(exc):
            raise ConductCanaryError("conductor claim failed for an unexpected reason") from exc
        return _sha256_text(str(exc))
    raise ConductCanaryError("conductor principal claimed an executor-only lease")


def _edge_evidence(
    *,
    packet: WorkPacketV1,
    edge_id: str,
    conductor: _Lane,
    executor: _Lane,
    lease: dict[str, Any],
    rejection_sha256: str,
    accepted_receipt: dict[str, Any],
    runtime_git_sha: str,
    broker_created_at: Any,
) -> dict[str, Any]:
    run_id = _expected_run_id(packet)
    checks = _expected_checks(
        edge_id=edge_id,
        run_id=run_id,
        lease=lease,
        executor_session_id=executor.executor_session["session_id"],
        runtime_git_sha=runtime_git_sha,
    )
    return {
        "edge_id": edge_id,
        "conductor_lane": conductor.name,
        "executor_lane": executor.name,
        "run_id": run_id,
        "broker_created_at": _canonical_timestamp(broker_created_at, "harvested run created_at"),
        "packet_deadline": _canonical_datetime(packet.deadline, "harvested packet deadline"),
        "lease_id_sha256": _sha256_text(str(lease["lease_id"])),
        "work_key_sha256": _sha256_text(packet.work_key),
        "intent_sha256": packet.intent_hash,
        "execution_sha256": packet.execution_hash,
        "conductor_claim_rejection_sha256": rejection_sha256,
        "executor_claim_sha256": str(checks[0].head),
        "heartbeat_sha256": str(checks[1].head),
        "accepted_receipt_sha256": canonical_hash(accepted_receipt),
        "reservation": True,
        "executor_only_claim": True,
        "heartbeat": True,
        "unchanged_heads": True,
        "empty_changed_paths": True,
        "conductor_harvest": True,
    }


def _aggregate_observed_at(edges: list[dict[str, Any]]) -> str:
    if not edges:
        raise ConductCanaryError("canary receipt has no edge observations")
    observations = [_canonical_timestamp(edge.get("broker_created_at"), "edge broker_created_at") for edge in edges]
    return max(observations)


def _execute_edge(
    *,
    canary_id: str,
    conductor: _Lane,
    executor: _Lane,
    runtime_git_sha: str,
    now: datetime,
    client_factory: Callable[..., HttpConductClient],
    endpoint: str,
    timeout: int,
) -> dict[str, Any]:
    edge_id = _edge_id(canary_id, conductor, executor)
    conductor_client = client_factory(
        endpoint,
        conductor.conductor_credential.token,
        timeout=timeout,
    )
    executor_client = client_factory(
        endpoint,
        executor.executor_credential.token,
        timeout=timeout,
    )
    packet = _packet(
        canary_id=canary_id,
        edge_id=edge_id,
        conductor=conductor,
        executor=executor,
        runtime_git_sha=runtime_git_sha,
        now=now,
    )
    submitted = conductor_client.submit(packet)
    submit_status, submitted_lease = _validate_submit_result(
        submitted,
        packet=packet,
        executor=executor,
    )
    run_id = _expected_run_id(packet)
    harvested = conductor_client.harvest(run_id)
    node, lease, stored_packet = _validate_harvest_node(
        harvested,
        packet=packet,
        conductor=conductor,
        executor=executor,
        runtime_git_sha=runtime_git_sha,
    )
    if (
        submitted_lease.get("lease_id") != lease.get("lease_id")
        or submitted_lease.get("generation") != lease.get("generation")
        or submitted_lease.get("state") != lease.get("state")
    ):
        raise ConductCanaryError("submit and harvest disagree about the canary lease")
    rejection_digest = _conductor_rejection_sha256(conductor_client, lease)
    if (node.get("status"), lease.get("state")) == ("succeeded", "released"):
        if submit_status != "duplicate":
            raise ConductCanaryError("fresh reservation unexpectedly resolved to a terminal canary run")
        accepted = _validate_terminal_receipt(
            node,
            lease,
            packet=stored_packet,
            edge_id=edge_id,
            executor=executor,
            runtime_git_sha=runtime_git_sha,
        )
        return _edge_evidence(
            packet=stored_packet,
            edge_id=edge_id,
            conductor=conductor,
            executor=executor,
            lease=lease,
            rejection_sha256=rejection_digest,
            accepted_receipt=accepted,
            runtime_git_sha=runtime_git_sha,
            broker_created_at=node.get("created_at"),
        )

    claim = executor_client.claim(lease["lease_id"], lease["generation"])
    capability_token = str(claim.get("capability_token") or "")
    if (
        claim.get("lease_id") != lease["lease_id"]
        or claim.get("run_id") != run_id
        or claim.get("generation") != lease["generation"]
        or not capability_token
    ):
        raise ConductCanaryError("executor claim returned an invalid capability")

    heartbeat = executor_client.heartbeat(
        lease["lease_id"],
        capability_token,
        generation=lease["generation"],
        observed_heads={"runtime": runtime_git_sha},
    )
    if heartbeat.get("status") != "active":
        raise ConductCanaryError("executor heartbeat did not activate the lease")
    heartbeat_lease = heartbeat.get("lease")
    if (
        not isinstance(heartbeat_lease, dict)
        or heartbeat_lease.get("lease_id") != lease["lease_id"]
        or heartbeat_lease.get("run_id") != run_id
        or heartbeat_lease.get("generation") != lease["generation"]
        or heartbeat_lease.get("executor") != executor.executor_session["identity"]
        or heartbeat_lease.get("observed_heads") != {"runtime": runtime_git_sha}
        or heartbeat_lease.get("state") != "active"
    ):
        raise ConductCanaryError("executor heartbeat returned the wrong canary lease")

    receipt = RunReceiptV1(
        receipt_id=f"receipt-{stored_packet.work_id}",
        run_id=run_id,
        lease_id=lease["lease_id"],
        lease_generation=lease["generation"],
        executor=AgentIdentityV1.model_validate(lease["executor"]),
        observed_heads_before={"runtime": runtime_git_sha},
        observed_heads_after={"runtime": runtime_git_sha},
        changed_paths=(),
        predicate=PredicateEvidenceV1(
            command=stored_packet.predicate,
            exit_code=0,
            summary=_PREDICATE_SUMMARY,
        ),
        checks=_expected_checks(
            edge_id=edge_id,
            run_id=run_id,
            lease=lease,
            executor_session_id=executor.executor_session["session_id"],
            runtime_git_sha=runtime_git_sha,
        ),
        spend={"runs": 0},
        outcome="succeeded",
    )
    report = executor_client.report(
        lease["lease_id"],
        capability_token,
        receipt,
        generation=lease["generation"],
    )
    if report.get("mutation_authorized") is not True or report.get("run_status") != "succeeded":
        raise ConductCanaryError("keeper rejected the unchanged-head read-effect receipt")
    terminal_harvest = conductor_client.harvest(run_id)
    terminal_node, terminal_lease, terminal_packet = _validate_harvest_node(
        terminal_harvest,
        packet=stored_packet,
        conductor=conductor,
        executor=executor,
        runtime_git_sha=runtime_git_sha,
        require_exact_deadline=True,
    )
    accepted = _validate_terminal_receipt(
        terminal_node,
        terminal_lease,
        packet=terminal_packet,
        edge_id=edge_id,
        executor=executor,
        runtime_git_sha=runtime_git_sha,
    )
    return _edge_evidence(
        packet=terminal_packet,
        edge_id=edge_id,
        conductor=conductor,
        executor=executor,
        lease=terminal_lease,
        rejection_sha256=rejection_digest,
        accepted_receipt=accepted,
        runtime_git_sha=runtime_git_sha,
        broker_created_at=terminal_node.get("created_at"),
    )


@contextmanager
def _receipt_path_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_id = _sha256_text(str(path.absolute()))[:24]
    lock_path = path.parent / f".limen-conduct-canary-{lock_id}.lock"
    deadline = time.monotonic() + _PATH_LOCK_TIMEOUT_SECONDS
    while True:
        try:
            os.mkdir(lock_path, 0o700)
            break
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise ConductCanaryError("timed out waiting for the bounded receipt path lock") from exc
            time.sleep(_PATH_LOCK_POLL_SECONDS)
        except OSError as exc:
            raise ConductCanaryError("cannot acquire the receipt path lock") from exc
    try:
        yield
    finally:
        try:
            lock_path.rmdir()
        except OSError as exc:
            raise ConductCanaryError("cannot release the receipt path lock") from exc


def _write_receipt(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    encoded = rendered.encode("utf-8")
    if len(encoded) > _MAX_RECEIPT_BYTES:
        raise ConductCanaryError("canary receipt exceeds its bounded size")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.monotonic_ns()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _existing_receipt(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        if path.stat().st_size > _MAX_RECEIPT_BYTES:
            raise ConductCanaryError("existing canary receipt exceeds its bounded size")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConductCanaryError("existing canary receipt is unreadable") from exc
    if not isinstance(value, dict) or value.get("schema_version") != CANARY_SCHEMA:
        raise ConductCanaryError("existing receipt is not a conduct full-mesh canary receipt")
    return value


def _read_existing_receipt(path: Path) -> dict[str, Any] | None:
    with _receipt_path_lock(path):
        return _existing_receipt(path)


def _commit_receipt(path: Path, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    with _receipt_path_lock(path):
        existing = _existing_receipt(path)
        if existing is not None:
            if existing.get("canary_id") != payload["canary_id"]:
                raise ConductCanaryError("receipt path already belongs to another canary identity")
            return existing, False
        _write_receipt(path, payload)
        return payload, True


def _reuse_existing(
    existing: dict[str, Any],
    *,
    canary_id: str,
    public_runtime: dict[str, Any],
    lanes: tuple[_Lane, ...],
    runtime_git_sha: str,
    client_factory: Callable[..., HttpConductClient],
    endpoint: str,
    timeout: int,
) -> dict[str, Any]:
    expected_keys = {
        "schema_version",
        "canary_id",
        "observed_at",
        "runtime_identity",
        "capabilities_evidence_sha256",
        "lane_count",
        "edge_count_required",
        "edge_count_succeeded",
        "all_edges_required",
        "lanes",
        "edges",
        "status",
    }
    if set(existing) != expected_keys or existing.get("schema_version") != CANARY_SCHEMA:
        raise ConductCanaryError("existing canary receipt has an unexpected schema")
    if existing.get("canary_id") != canary_id:
        raise ConductCanaryError("receipt path already belongs to another canary identity")
    required = len(lanes) * len(lanes)
    if (
        existing.get("status") != "passed"
        or existing.get("runtime_identity") != public_runtime
        or existing.get("capabilities_evidence_sha256") != _capabilities_evidence_sha256(lanes)
        or existing.get("lane_count") != len(lanes)
        or existing.get("edge_count_required") != required
        or existing.get("edge_count_succeeded") != required
        or existing.get("all_edges_required") is not True
        or existing.get("lanes") != [_public_lane(lane) for lane in lanes]
    ):
        raise ConductCanaryError("existing receipt is not a passing fixed-point receipt")
    edges = existing.get("edges")
    if not isinstance(edges, list) or len(edges) != required:
        raise ConductCanaryError("existing receipt does not cover the current full mesh")
    expected_edges = [(conductor, executor) for conductor in lanes for executor in lanes]
    observed_pairs = [
        (edge.get("conductor_lane"), edge.get("executor_lane")) if isinstance(edge, dict) else (None, None)
        for edge in edges
    ]
    expected_pairs = [(conductor.name, executor.name) for conductor, executor in expected_edges]
    edge_ids = [edge.get("edge_id") if isinstance(edge, dict) else None for edge in edges]
    run_ids = [edge.get("run_id") if isinstance(edge, dict) else None for edge in edges]
    if observed_pairs != expected_pairs:
        raise ConductCanaryError("existing receipt edge denominator does not match live capabilities")
    if len(set(edge_ids)) != required or len(set(run_ids)) != required:
        raise ConductCanaryError("existing receipt reuses an edge or run identity")
    verified_edges: list[dict[str, Any]] = []
    for edge, (conductor, executor) in zip(edges, expected_edges, strict=True):
        if not isinstance(edge, dict):
            raise ConductCanaryError("existing receipt contains malformed edge evidence")
        packet_deadline = _parse_timestamp(
            edge.get("packet_deadline"),
            "existing edge packet_deadline",
        )
        if edge["packet_deadline"] != _canonical_datetime(
            packet_deadline,
            "existing edge packet_deadline",
        ):
            raise ConductCanaryError("existing edge packet_deadline is not canonical")
        edge_id = _edge_id(canary_id, conductor, executor)
        packet = _packet(
            canary_id=canary_id,
            edge_id=edge_id,
            conductor=conductor,
            executor=executor,
            runtime_git_sha=runtime_git_sha,
            now=packet_deadline - _EDGE_DEADLINE,
        )
        client = client_factory(
            endpoint,
            conductor.conductor_credential.token,
            timeout=timeout,
        )
        run_id = _expected_run_id(packet)
        node, lease, stored_packet = _validate_harvest_node(
            client.harvest(run_id),
            packet=packet,
            conductor=conductor,
            executor=executor,
            runtime_git_sha=runtime_git_sha,
            require_exact_deadline=True,
        )
        if (node.get("status"), lease.get("state")) != ("succeeded", "released"):
            raise ConductCanaryError("existing receipt references an unsettled canary edge")
        accepted = _validate_terminal_receipt(
            node,
            lease,
            packet=stored_packet,
            edge_id=edge_id,
            executor=executor,
            runtime_git_sha=runtime_git_sha,
        )
        expected_edge = _edge_evidence(
            packet=stored_packet,
            edge_id=edge_id,
            conductor=conductor,
            executor=executor,
            lease=lease,
            rejection_sha256=_conductor_rejection_sha256(client, lease),
            accepted_receipt=accepted,
            runtime_git_sha=runtime_git_sha,
            broker_created_at=node.get("created_at"),
        )
        if edge != expected_edge:
            raise ConductCanaryError("existing receipt edge evidence was altered")
        verified_edges.append(expected_edge)
    if existing.get("observed_at") != _aggregate_observed_at(verified_edges):
        raise ConductCanaryError("existing receipt observed_at does not match immutable edge evidence")
    return existing


def run_full_mesh_canary(
    *,
    client: Any,
    receipt_path: Path,
    environ: Mapping[str, str] | None = None,
    client_factory: Callable[..., HttpConductClient] = HttpConductClient,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run, or read-only re-verify, one exact authenticated full mesh."""

    if not isinstance(client, HttpConductClient):
        raise ConductCanaryError(
            "full-mesh canary requires authenticated remote HttpConductClient; local SQLite is rejected"
        )
    environment = os.environ if environ is None else environ
    runtime = _runtime_identity(environment)
    refs = _credential_refs(environment)
    capabilities = client.capabilities()
    lanes = _discover_lanes(capabilities, refs)
    canary_id, public_runtime = _canary_identity(client, runtime, lanes)
    existing = _read_existing_receipt(receipt_path)
    if existing is not None:
        return _reuse_existing(
            existing,
            canary_id=canary_id,
            public_runtime=public_runtime,
            lanes=lanes,
            runtime_git_sha=runtime["git_sha"],
            client_factory=client_factory,
            endpoint=client.endpoint,
            timeout=client.timeout,
        )

    submission_time = now or datetime.now(timezone.utc)
    edges: list[dict[str, Any]] = []
    for conductor in lanes:
        for executor in lanes:
            edges.append(
                _execute_edge(
                    canary_id=canary_id,
                    conductor=conductor,
                    executor=executor,
                    runtime_git_sha=runtime["git_sha"],
                    now=submission_time,
                    client_factory=client_factory,
                    endpoint=client.endpoint,
                    timeout=client.timeout,
                )
            )
    required = len(lanes) * len(lanes)
    if len(edges) != required:
        raise ConductCanaryError("full-mesh canary did not complete every ordered edge")
    payload = {
        "schema_version": CANARY_SCHEMA,
        "canary_id": canary_id,
        "observed_at": _aggregate_observed_at(edges),
        "runtime_identity": public_runtime,
        "capabilities_evidence_sha256": _capabilities_evidence_sha256(lanes),
        "lane_count": len(lanes),
        "edge_count_required": required,
        "edge_count_succeeded": len(edges),
        "all_edges_required": True,
        "lanes": [_public_lane(lane) for lane in lanes],
        "edges": edges,
        "status": "passed",
    }
    committed, created = _commit_receipt(receipt_path, payload)
    if created:
        return payload
    return _reuse_existing(
        committed,
        canary_id=canary_id,
        public_runtime=public_runtime,
        lanes=lanes,
        runtime_git_sha=runtime["git_sha"],
        client_factory=client_factory,
        endpoint=client.endpoint,
        timeout=client.timeout,
    )
