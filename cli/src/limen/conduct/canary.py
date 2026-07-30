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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from limen.conduct.broker import ConductError
from limen.conduct.client import HttpConductClient
from limen.conduct.models import (
    AgentIdentityV1,
    AuthorityEnvelopeV1,
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
_EDGE_DEADLINE = timedelta(minutes=15)
_PREDICATE = "limen conduct canary full-mesh --receipt canary.json"


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
        raise ConductCanaryError(
            f"{RUNTIME_IDENTITY_ENV} must contain only schema_version, git_sha, and deployment_id"
        )
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
        raise ConductCanaryError(
            f"{CREDENTIAL_REFS_ENV} must contain only schema_version and credentials"
        )
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
            raise ConductCanaryError(
                "credential references must contain only session_id, role, and token_env"
            )
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
        session = dict(raw)
        session["identity"] = identity.model_dump(mode="json")
        sessions[session_id] = session
        if _eligible_session(session, "conduct"):
            conductor_agents.add(identity.agent)
        if _eligible_session(session, "execute"):
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
            raise ConductCanaryError(
                f"credential reference names a session ineligible for the {ref.role} role"
            )
        agent = str(session["identity"]["agent"])
        key = (agent, ref.role)
        if key in selected:
            raise ConductCanaryError("each native lane must have exactly one credential per role")
        selected[key] = (session, ref)

    configured_agents = {agent for agent, _role in selected}
    if configured_agents != denominator:
        raise ConductCanaryError(
            "credential references must cover every complete live native lane and no others"
        )

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
        receipt_target=(
            "git:organvm/limen:docs/receipts/conduct-full-mesh.json"
            f"#{canary_id[:20]}-{edge_id[:20]}"
        ),
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


def _verify_harvest(
    harvest: dict[str, Any],
    *,
    run_id: str,
    runtime_git_sha: str,
) -> dict[str, Any]:
    if harvest.get("root_run_id") != run_id or harvest.get("unharvested"):
        raise ConductCanaryError("conductor harvest did not return one settled root")
    nodes = harvest.get("nodes")
    if not isinstance(nodes, list) or len(nodes) != 1:
        raise ConductCanaryError("conductor harvest returned an unexpected graph")
    node = nodes[0]
    receipts = node.get("receipts") if isinstance(node, dict) else None
    if node.get("status") != "succeeded" or not isinstance(receipts, list) or len(receipts) != 1:
        raise ConductCanaryError("conductor harvest did not return one successful receipt")
    receipt = receipts[0]
    if (
        receipt.get("mutation_authorized") is not True
        or receipt.get("changed_paths") != []
        or receipt.get("observed_heads_before") != {"runtime": runtime_git_sha}
        or receipt.get("observed_heads_after") != {"runtime": runtime_git_sha}
        or receipt.get("outcome") != "succeeded"
    ):
        raise ConductCanaryError("harvested read-effect receipt violates the canary contract")
    return receipt


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
    edge_id = canonical_hash(
        {
            "canary_id": canary_id,
            "conductor_lane": conductor.name,
            "executor_lane": executor.name,
            "conductor_session": conductor.conductor_session["session_id"],
            "executor_session": executor.executor_session["session_id"],
        }
    )
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
    reserved = conductor_client.submit(packet)
    if reserved.get("status") != "reserved":
        raise ConductCanaryError("fresh canary edge did not receive a reservation")
    if reserved.get("executor_session_id") != executor.executor_session["session_id"]:
        raise ConductCanaryError("keeper reserved the canary edge for the wrong executor session")
    lease = reserved.get("lease")
    if not isinstance(lease, dict) or lease.get("state") != "reserved":
        raise ConductCanaryError("keeper returned an invalid canary lease")
    if "capability_token" in reserved or "capability_token_hash" in lease:
        raise ConductCanaryError("reservation disclosed executor-only capability material")

    rejection_digest: str
    try:
        conductor_client.claim(lease["lease_id"], lease["generation"])
    except ConductError as exc:
        if not _executor_only_rejection(exc):
            raise ConductCanaryError("conductor claim failed for an unexpected reason") from exc
        rejection_digest = _sha256_text(str(exc))
    else:
        raise ConductCanaryError("conductor principal claimed an executor-only lease")

    claim = executor_client.claim(lease["lease_id"], lease["generation"])
    capability_token = str(claim.get("capability_token") or "")
    if (
        claim.get("lease_id") != lease["lease_id"]
        or claim.get("run_id") != reserved["run_id"]
        or claim.get("generation") != lease["generation"]
        or not capability_token
    ):
        raise ConductCanaryError("executor claim returned an invalid capability")
    capability_sha256 = _sha256_text(capability_token)

    heartbeat = executor_client.heartbeat(
        lease["lease_id"],
        capability_token,
        generation=lease["generation"],
        observed_heads={"runtime": runtime_git_sha},
    )
    if heartbeat.get("status") != "active":
        raise ConductCanaryError("executor heartbeat did not activate the lease")

    receipt = RunReceiptV1(
        receipt_id=f"receipt-{packet.work_id}",
        run_id=reserved["run_id"],
        lease_id=lease["lease_id"],
        lease_generation=lease["generation"],
        executor=AgentIdentityV1.model_validate(lease["executor"]),
        observed_heads_before={"runtime": runtime_git_sha},
        observed_heads_after={"runtime": runtime_git_sha},
        changed_paths=(),
        predicate=PredicateEvidenceV1(
            command=packet.predicate,
            exit_code=0,
            summary="bounded authenticated read-effect canary edge",
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
    harvested = conductor_client.harvest(reserved["run_id"])
    accepted = _verify_harvest(
        harvested,
        run_id=reserved["run_id"],
        runtime_git_sha=runtime_git_sha,
    )
    return {
        "edge_id": edge_id,
        "conductor_lane": conductor.name,
        "executor_lane": executor.name,
        "run_id": reserved["run_id"],
        "lease_id_sha256": _sha256_text(lease["lease_id"]),
        "conductor_claim_rejection_sha256": rejection_digest,
        "capability_sha256": capability_sha256,
        "accepted_receipt_sha256": canonical_hash(accepted),
        "reservation": True,
        "executor_only_claim": True,
        "heartbeat": True,
        "unchanged_heads": True,
        "empty_changed_paths": True,
        "conductor_harvest": True,
    }


def _write_receipt(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
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
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConductCanaryError("existing canary receipt is unreadable") from exc
    if not isinstance(value, dict) or value.get("schema_version") != CANARY_SCHEMA:
        raise ConductCanaryError("existing receipt is not a conduct full-mesh canary receipt")
    return value


def _reuse_existing(
    existing: dict[str, Any],
    *,
    canary_id: str,
    lanes: tuple[_Lane, ...],
    runtime_git_sha: str,
    client_factory: Callable[..., HttpConductClient],
    endpoint: str,
    timeout: int,
) -> dict[str, Any]:
    if existing.get("canary_id") != canary_id:
        raise ConductCanaryError("receipt path already belongs to another canary identity")
    if existing.get("status") != "passed":
        raise ConductCanaryError("existing receipt is not a passing fixed-point receipt")
    edges = existing.get("edges")
    required = len(lanes) * len(lanes)
    if not isinstance(edges, list) or len(edges) != required:
        raise ConductCanaryError("existing receipt does not cover the current full mesh")
    lane_by_name = {lane.name: lane for lane in lanes}
    expected = {(left.name, right.name) for left in lanes for right in lanes}
    observed = {
        (str(edge.get("conductor_lane")), str(edge.get("executor_lane")))
        for edge in edges
        if isinstance(edge, dict)
    }
    if observed != expected:
        raise ConductCanaryError("existing receipt edge denominator does not match live capabilities")
    for edge in edges:
        conductor = lane_by_name[str(edge["conductor_lane"])]
        client = client_factory(
            endpoint,
            conductor.conductor_credential.token,
            timeout=timeout,
        )
        _verify_harvest(
            client.harvest(str(edge["run_id"])),
            run_id=str(edge["run_id"]),
            runtime_git_sha=runtime_git_sha,
        )
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
    existing = _existing_receipt(receipt_path)
    if existing is not None:
        return _reuse_existing(
            existing,
            canary_id=canary_id,
            lanes=lanes,
            runtime_git_sha=runtime["git_sha"],
            client_factory=client_factory,
            endpoint=client.endpoint,
            timeout=client.timeout,
        )

    observed_at = now or datetime.now(timezone.utc)
    edges: list[dict[str, Any]] = []
    for conductor in lanes:
        for executor in lanes:
            edges.append(
                _execute_edge(
                    canary_id=canary_id,
                    conductor=conductor,
                    executor=executor,
                    runtime_git_sha=runtime["git_sha"],
                    now=observed_at,
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
        "observed_at": observed_at.isoformat(),
        "runtime_identity": public_runtime,
        "capabilities_evidence_sha256": canonical_hash(capabilities),
        "lane_count": len(lanes),
        "edge_count_required": required,
        "edge_count_succeeded": len(edges),
        "all_edges_required": True,
        "lanes": [_public_lane(lane) for lane in lanes],
        "edges": edges,
        "status": "passed",
    }
    _write_receipt(receipt_path, payload)
    return payload
