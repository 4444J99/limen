"""Authenticated, provider-neutral full-mesh conduct canary.

The canary is deliberately a protocol client, not a provider launcher.  It
discovers the currently registered native lane denominator from the remote
keeper, then exercises every ordered conductor -> executor edge with a
bounded read-effect packet.  Secret values remain process-local; the public
receipt carries only credential reference names and SHA-256 evidence.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from limen.conduct.broker import ConductError
from limen.conduct.canary_executor import (
    NativeCanaryEdgeAck,
    NativeCanaryEdgeRequest,
    NativeCanaryExecutorError,
    resolve_native_canary_bridge,
    validate_executor_credential_reference,
    wake_native_canary_edge,
)
from limen.conduct.client import HttpConductClient
from limen.conduct.models import (
    AgentIdentityV1,
    AuthorityEnvelopeV1,
    CheckEvidenceV1,
    ConductPrincipalV1,
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
_LOCK_ROOT_ENV = "LIMEN_CONDUCT_CANARY_LOCK_ROOT"
_MAX_EDGE_RETRY_GENERATION = 1
_PREDICATE_SUMMARY = "observed active heartbeat with unchanged runtime head for one authenticated canary edge"
_GITHUB_ORIGIN_RE = re.compile(
    r"^(?:https?://github\.com/|ssh://git@github\.com/|git@github\.com:)"
    r"(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)


class ConductCanaryError(ConductError):
    """A public, secret-free canary failure."""


@dataclass(frozen=True)
class _CredentialRef:
    session_id: str
    role: str
    token_env: str
    token: str  # allow-secret: process-local value hydrated from a named environment reference
    principal: dict[str, Any] | None = None


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


def _git_probe(
    cwd: Path,
    *args: str,
    runner: Callable[..., Any],
) -> str:
    try:
        result = runner(
            ("git", "-C", str(cwd), *args),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ConductCanaryError("cannot resolve the canary receipt repository") from exc
    if (
        getattr(result, "returncode", None) != 0
        or not isinstance(getattr(result, "stdout", None), str)
        or not result.stdout.strip()
    ):
        raise ConductCanaryError("cannot resolve the canary receipt repository")
    return result.stdout.strip()


def _repo_receipt_target(
    path: Path,
    *,
    git_runner: Callable[..., Any] = subprocess.run,
) -> tuple[Path, str]:
    """Return a canonical local path and its exact repo-owned Git target."""

    canonical = path.expanduser().resolve(strict=False)
    probe = canonical.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if not probe.is_dir():
        probe = probe.parent
    root = Path(
        _git_probe(
            probe,
            "rev-parse",
            "--show-toplevel",
            runner=git_runner,
        )
    ).resolve(strict=True)
    origin = _git_probe(
        root,
        "remote",
        "get-url",
        "origin",
        runner=git_runner,
    )
    match = _GITHUB_ORIGIN_RE.fullmatch(origin)
    if match is None:
        raise ConductCanaryError("canary receipt repository must have an exact GitHub origin")
    repository = match.group("repository")
    try:
        relative = canonical.relative_to(root)
    except ValueError as exc:
        raise ConductCanaryError("canary receipt must remain inside its Git repository") from exc
    if (
        not relative.parts
        or ".git" in relative.parts
        or relative.suffix != ".json"
        or any("#" in part or "\x00" in part for part in relative.parts)
    ):
        raise ConductCanaryError("canary receipt must be a valid repository-owned JSON target")
    return canonical, f"git:{repository}:{relative.as_posix()}"


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


def _validated_runtime_identity(value: dict[str, Any], label: str) -> dict[str, str]:
    if set(value) != {"schema_version", "git_sha", "deployment_id"}:
        raise ConductCanaryError(f"{label} must contain only schema_version, git_sha, and deployment_id")
    if value.get("schema_version") != _RUNTIME_IDENTITY_SCHEMA:
        raise ConductCanaryError(f"{label} has an unsupported schema")
    git_sha = str(value.get("git_sha") or "")
    deployment_id = str(value.get("deployment_id") or "")
    if not _GIT_OBJECT_RE.fullmatch(git_sha):
        raise ConductCanaryError(f"{label} git_sha must be an exact lowercase Git object ID")
    if not deployment_id or "\x00" in deployment_id or len(deployment_id) > 512:
        raise ConductCanaryError(f"{label} deployment_id must be a non-empty bounded string")
    return {"git_sha": git_sha, "deployment_id": deployment_id}


def _runtime_identity(environ: Mapping[str, str]) -> dict[str, str]:
    return _validated_runtime_identity(
        _load_json_env(RUNTIME_IDENTITY_ENV, environ),
        RUNTIME_IDENTITY_ENV,
    )


def _require_remote_runtime_identity(
    capabilities: dict[str, Any],
    installed: dict[str, str],
) -> dict[str, str]:
    raw = capabilities.get("runtime_identity")
    if not isinstance(raw, dict):
        raise ConductCanaryError("remote keeper did not authenticate its runtime identity")
    remote = _validated_runtime_identity(raw, "remote keeper runtime_identity")
    if remote != installed:
        raise ConductCanaryError("installed and remote keeper runtime identities do not match")
    return remote


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
    seen_tokens: set[str] = set()
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
        if role == "executor":
            try:
                validate_executor_credential_reference(token_env)
            except NativeCanaryExecutorError as exc:
                raise ConductCanaryError("executor credential reference token_env is reserved") from exc
        binding = (session_id, role)
        if binding in seen_bindings or token_env in seen_envs:
            raise ConductCanaryError("credential references must be unique")
        token = environ.get(token_env, "").strip()  # allow-secret: environment reference only
        if not token:
            raise ConductCanaryError(f"credential reference {token_env} is not hydrated")
        if token in seen_tokens:
            raise ConductCanaryError("every canary role requires a distinct authenticated credential")
        seen_bindings.add(binding)
        seen_envs.add(token_env)
        seen_tokens.add(token)
        refs.append(
            _CredentialRef(
                session_id=session_id,
                role=role,
                token_env=token_env,
                token=token,  # allow-secret: process-local transport credential, never serialized
            )
        )
    return tuple(refs)


def _authenticate_credential_refs(
    capabilities: dict[str, Any],
    refs: tuple[_CredentialRef, ...],
    *,
    installed_runtime: dict[str, str],
    client_factory: Callable[..., HttpConductClient],
    endpoint: str,
    timeout: int,
) -> tuple[_CredentialRef, ...]:
    initial_sessions = {
        str(row.get("session_id") or ""): row for row in capabilities.get("sessions", []) if isinstance(row, dict)
    }
    authenticated: list[_CredentialRef] = []
    seen_principal_ids: set[str] = set()
    principal_fields = set(ConductPrincipalV1.model_fields)
    for ref in refs:
        response = client_factory(endpoint, ref.token, timeout=timeout).capabilities()
        if response.get("schema_version") != "limen.conduct_capabilities.v1":
            raise ConductCanaryError("credential authentication returned an unsupported capabilities schema")
        _require_remote_runtime_identity(response, installed_runtime)
        raw_principal = response.get("authenticated_principal")
        if not isinstance(raw_principal, dict) or set(raw_principal) != principal_fields:
            raise ConductCanaryError("credential did not return exact authenticated principal evidence")
        try:
            principal = ConductPrincipalV1.model_validate(raw_principal)
        except ValueError as exc:
            raise ConductCanaryError("credential returned malformed authenticated principal evidence") from exc
        expected_roles = frozenset({"observer", ref.role})
        if principal.roles != expected_roles:
            raise ConductCanaryError(f"{ref.role} credential has overprivileged or incomplete principal roles")
        bound_sessions = response.get("authenticated_session_ids")
        if (
            not isinstance(bound_sessions, list)
            or any(not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value) for value in bound_sessions)
            or bound_sessions != sorted(set(bound_sessions))
            or ref.session_id not in bound_sessions
        ):
            raise ConductCanaryError("credential is not authenticated for its declared canary session")
        if principal.principal_id in seen_principal_ids:
            raise ConductCanaryError("every canary role requires a distinct authenticated principal")
        seen_principal_ids.add(principal.principal_id)
        response_sessions = response.get("sessions")
        if not isinstance(response_sessions, list):
            raise ConductCanaryError("credential authentication returned a malformed session catalog")
        authenticated_session = next(
            (row for row in response_sessions if isinstance(row, dict) and row.get("session_id") == ref.session_id),
            None,
        )
        initial_session = initial_sessions.get(ref.session_id)
        if authenticated_session is None or initial_session is None:
            raise ConductCanaryError("credential-bound session is absent from remote capabilities")
        if _stable_session_identity(authenticated_session) != _stable_session_identity(initial_session):
            raise ConductCanaryError("credential-bound session identity changed across authenticated reads")
        identity = authenticated_session.get("identity")
        if not isinstance(identity, dict) or (
            principal.agent != identity.get("agent") or principal.surface != identity.get("surface")
        ):
            raise ConductCanaryError("authenticated principal does not match its bound session identity")
        authenticated.append(
            replace(
                ref,
                principal={
                    **principal.model_dump(mode="json"),
                    "roles": sorted(principal.roles),
                },
            )
        )
    return tuple(authenticated)


def _eligible_session(row: dict[str, Any], capability: str) -> bool:
    capabilities = row.get("capabilities")
    active_leases = row.get("active_leases")
    concurrency = row.get("concurrency")
    return bool(
        row.get("healthy") is True
        and row.get("accepting_work") is True
        and row.get("human_protected") is not True
        and isinstance(capabilities, list)
        and capability in capabilities
        and (capability != "execute" or row.get("quota_remaining") != 0)
        and isinstance(active_leases, int)
        and not isinstance(active_leases, bool)
        and active_leases >= 0
        and isinstance(concurrency, int)
        and not isinstance(concurrency, bool)
        and concurrency >= 1
        and (capability != "execute" or active_leases < concurrency)
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
    native_session_id = session.get("native_session_id")
    if not isinstance(native_session_id, str) or not _IDENTIFIER_RE.fullmatch(native_session_id):
        raise ConductCanaryError("live canary session lacks a bounded native_session_id")
    native_run_id = session.get("native_run_id")
    identity_native_run_id = (session.get("identity") or {}).get("native_run_id")
    if (
        not isinstance(native_run_id, str)
        or not _IDENTIFIER_RE.fullmatch(native_run_id)
        or identity_native_run_id != native_run_id
    ):
        raise ConductCanaryError("live canary session lacks an exact bounded native_run_id")
    return {
        "session_id": session["session_id"],
        "native_session_id": native_session_id,
        "native_run_id": native_run_id,
        "identity": session["identity"],
        "capabilities": sorted(session.get("capabilities") or []),
        "transport": session.get("transport"),
        "harvest_method": session.get("harvest_method"),
    }


def _credential_binding_sha256(ref: _CredentialRef, session: dict[str, Any]) -> str:
    if ref.principal is None:
        raise ConductCanaryError("credential lacks authenticated principal evidence")
    return canonical_hash(
        {
            "schema_version": "limen.conduct_canary_credential_binding.v1",
            "credential_ref": ref.token_env,
            "role": ref.role,
            "session": _stable_session_identity(session),
            "principal": ref.principal,
        }
    )


def _credential_principal_id(ref: _CredentialRef) -> str:
    principal_id = (ref.principal or {}).get("principal_id")
    if not isinstance(principal_id, str) or not _IDENTIFIER_RE.fullmatch(principal_id):
        raise ConductCanaryError("credential lacks a valid authenticated principal identity")
    return principal_id


def _public_lane(lane: _Lane) -> dict[str, Any]:
    return {
        "lane": lane.name,
        "conductor_session_sha256": _sha256_text(lane.conductor_session["session_id"]),
        "conductor_native_session_sha256": _sha256_text(
            _stable_session_identity(lane.conductor_session)["native_session_id"]
        ),
        "conductor_native_run_sha256": _sha256_text(_stable_session_identity(lane.conductor_session)["native_run_id"]),
        "executor_session_sha256": _sha256_text(lane.executor_session["session_id"]),
        "executor_native_session_sha256": _sha256_text(
            _stable_session_identity(lane.executor_session)["native_session_id"]
        ),
        "executor_native_run_sha256": _sha256_text(_stable_session_identity(lane.executor_session)["native_run_id"]),
        "conductor_credential_ref": lane.conductor_credential.token_env,
        "conductor_credential_binding_sha256": _credential_binding_sha256(
            lane.conductor_credential,
            lane.conductor_session,
        ),
        "executor_credential_ref": lane.executor_credential.token_env,
        "executor_credential_binding_sha256": _credential_binding_sha256(
            lane.executor_credential,
            lane.executor_session,
        ),
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
    receipt_target: str,
) -> tuple[str, dict[str, Any]]:
    implementation_sha256 = _sha256_bytes(Path(__file__).read_bytes())
    executor_implementation_sha256 = _sha256_bytes(Path(__file__).with_name("canary_executor.py").read_bytes())
    private_identity = {
        "endpoint": client.endpoint,
        "runtime": runtime,
        "receipt_target": receipt_target,
        "implementation_sha256": implementation_sha256,
        "executor_implementation_sha256": executor_implementation_sha256,
        "lanes": [
            {
                "lane": lane.name,
                "conductor": _stable_session_identity(lane.conductor_session),
                "executor": _stable_session_identity(lane.executor_session),
                "conductor_credential_ref": lane.conductor_credential.token_env,
                "conductor_credential_binding_sha256": _credential_binding_sha256(
                    lane.conductor_credential,
                    lane.conductor_session,
                ),
                "executor_credential_ref": lane.executor_credential.token_env,
                "executor_credential_binding_sha256": _credential_binding_sha256(
                    lane.executor_credential,
                    lane.executor_session,
                ),
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
        "executor_implementation_sha256": executor_implementation_sha256,
        "keeper_runtime_identity_sha256": canonical_hash(
            {
                "schema_version": _RUNTIME_IDENTITY_SCHEMA,
                **runtime,
            }
        ),
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
    receipt_target: str,
    now: datetime,
    retry_generation: int = 0,
) -> WorkPacketV1:
    if retry_generation not in range(_MAX_EDGE_RETRY_GENERATION + 1):
        raise ConductCanaryError("canary edge retry generation exceeds its fixed bound")
    work_id = f"canary-{canary_id[:20]}-{edge_id[:20]}-r{retry_generation}"
    identity = AgentIdentityV1.model_validate(conductor.conductor_session["identity"])
    edge_predicate = shlex.join(("/bin/test", runtime_git_sha, "=", runtime_git_sha))
    return WorkPacketV1(
        work_id=work_id,
        work_key=f"conduct-canary:{canary_id}:{edge_id}:retry:{retry_generation}",
        intent={
            "kind": "conduct-full-mesh-canary",
            "canary_id": canary_id,
            "edge_id": edge_id,
            "retry_generation": retry_generation,
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
        predicate=edge_predicate,
        receipt_target=f"{receipt_target}#{canary_id[:20]}-{edge_id[:20]}-r{retry_generation}",
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
    return "lacks required executor" in detail


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
    executor_principal_id: str,
) -> str:
    return canonical_hash(
        {
            "schema_version": "limen.conduct_canary_executor_claim_evidence.v1",
            "edge_id": edge_id,
            "run_id": run_id,
            "lease_id": lease["lease_id"],
            "lease_generation": lease["generation"],
            "executor_session_id": executor_session_id,
            "executor_principal_id": executor_principal_id,
        }
    )


def _conductor_rejection_evidence_sha256(
    *,
    edge_id: str,
    run_id: str,
    lease: dict[str, Any],
    conductor_session_id: str,
    conductor_principal_id: str,
    executor_session_id: str,
    executor_principal_id: str,
) -> str:
    return canonical_hash(
        {
            "schema_version": "limen.conduct_canary_conductor_rejection_evidence.v1",
            "result": "executor_only_claim_rejected",
            "edge_id": edge_id,
            "run_id": run_id,
            "lease_id": lease["lease_id"],
            "lease_generation": lease["generation"],
            "conductor_session_id": conductor_session_id,
            "conductor_principal_id": conductor_principal_id,
            "executor_session_id": executor_session_id,
            "executor_principal_id": executor_principal_id,
        }
    )


def _heartbeat_evidence_sha256(
    *,
    edge_id: str,
    run_id: str,
    lease: dict[str, Any],
    executor_session_id: str,
    executor_principal_id: str,
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
            "executor_principal_id": executor_principal_id,
            "observed_heads": {"runtime": runtime_git_sha},
        }
    )


def _expected_checks(
    *,
    edge_id: str,
    run_id: str,
    lease: dict[str, Any],
    conductor_session_id: str,
    conductor_principal_id: str,
    executor_session_id: str,
    executor_principal_id: str,
    runtime_git_sha: str,
) -> tuple[CheckEvidenceV1, ...]:
    return (
        CheckEvidenceV1(
            name="conduct-canary-conductor-claim-rejected",
            status="success",
            head=_conductor_rejection_evidence_sha256(
                edge_id=edge_id,
                run_id=run_id,
                lease=lease,
                conductor_session_id=conductor_session_id,
                conductor_principal_id=conductor_principal_id,
                executor_session_id=executor_session_id,
                executor_principal_id=executor_principal_id,
            ),
        ),
        CheckEvidenceV1(
            name="conduct-canary-executor-claim",
            status="success",
            head=_claim_evidence_sha256(
                edge_id=edge_id,
                run_id=run_id,
                lease=lease,
                executor_session_id=executor_session_id,
                executor_principal_id=executor_principal_id,
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
                executor_principal_id=executor_principal_id,
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
    return _parse_timestamp(value, label).astimezone(UTC).isoformat()


def _canonical_datetime(value: datetime, label: str) -> str:
    if value.tzinfo is None:
        raise ConductCanaryError(f"{label} must include a timezone")
    return value.astimezone(UTC).isoformat()


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


def _contains_forbidden_lease_material(value: Any) -> bool:
    forbidden = {"capability_token", "capability_token_hash", "executor_principal_id"}
    if isinstance(value, dict):
        return bool(forbidden & set(value)) or any(
            _contains_forbidden_lease_material(child) for child in value.values()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_lease_material(child) for child in value)
    return False


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
    if "capability_token" in result or _contains_forbidden_lease_material(lease):
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
    if _contains_forbidden_lease_material(lease):
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
        ("expired", "expired"),
    }:
        raise ConductCanaryError("canary duplicate is not in a recoverable lifecycle state")
    receipts = node.get("receipts")
    if not isinstance(receipts, list):
        raise ConductCanaryError("harvested canary receipts are malformed")
    terminal = status_pair == ("succeeded", "released")
    expected_receipt_count = 1 if terminal else 0
    expected_unharvested = [run_id] if status_pair in {("reserved", "reserved"), ("running", "active")} else []
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
    conductor: _Lane,
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
        provider_identity=_stable_session_identity(executor.executor_session)["native_session_id"],
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
            conductor_session_id=conductor.conductor_session["session_id"],
            conductor_principal_id=_credential_principal_id(conductor.conductor_credential),
            executor_session_id=executor.executor_session["session_id"],
            executor_principal_id=_credential_principal_id(executor.executor_credential),
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


def _prove_conductor_rejection(
    client: HttpConductClient,
    *,
    edge_id: str,
    run_id: str,
    lease: dict[str, Any],
    conductor: _Lane,
    executor: _Lane,
) -> str:
    try:
        client.claim(str(lease["lease_id"]), int(lease["generation"]))
    except ConductError as exc:
        if not _executor_only_rejection(exc):
            raise ConductCanaryError("conductor claim failed for an unexpected reason") from exc
        return _conductor_rejection_evidence_sha256(
            edge_id=edge_id,
            run_id=run_id,
            lease=lease,
            conductor_session_id=conductor.conductor_session["session_id"],
            conductor_principal_id=_credential_principal_id(conductor.conductor_credential),
            executor_session_id=executor.executor_session["session_id"],
            executor_principal_id=_credential_principal_id(executor.executor_credential),
        )
    raise ConductCanaryError("conductor principal claimed an executor-only lease")


def _native_edge_request(
    *,
    canary_id: str,
    packet: WorkPacketV1,
    edge_id: str,
    conductor: _Lane,
    executor: _Lane,
    lease: dict[str, Any],
    runtime_git_sha: str,
) -> NativeCanaryEdgeRequest:
    run_id = _expected_run_id(packet)
    stable_executor = _stable_session_identity(executor.executor_session)
    checks = _expected_checks(
        edge_id=edge_id,
        run_id=run_id,
        lease=lease,
        conductor_session_id=conductor.conductor_session["session_id"],
        conductor_principal_id=_credential_principal_id(conductor.conductor_credential),
        executor_session_id=executor.executor_session["session_id"],
        executor_principal_id=_credential_principal_id(executor.executor_credential),
        runtime_git_sha=runtime_git_sha,
    )
    return NativeCanaryEdgeRequest(
        canary_id=canary_id,
        edge_id=edge_id,
        run_id=run_id,
        lease_id=str(lease["lease_id"]),
        generation=int(lease["generation"]),
        packet_deadline=_canonical_datetime(packet.deadline, "canary packet deadline"),
        packet_predicate=packet.predicate,
        receipt_id=f"receipt-{packet.work_id}",
        runtime_git_sha=runtime_git_sha,
        executor_session_id=executor.executor_session["session_id"],
        executor_native_session_id=stable_executor["native_session_id"],
        executor_native_run_id=stable_executor["native_run_id"],
        executor_credential_ref=executor.executor_credential.token_env,
        executor_identity=dict(executor.executor_session["identity"]),
        expected_checks=tuple(check.model_dump(mode="json") for check in checks),
    )


def _edge_evidence(
    *,
    packet: WorkPacketV1,
    edge_id: str,
    conductor: _Lane,
    executor: _Lane,
    lease: dict[str, Any],
    accepted_receipt: dict[str, Any],
    runtime_git_sha: str,
    broker_created_at: Any,
    canary_id: str,
) -> dict[str, Any]:
    run_id = _expected_run_id(packet)
    checks = _expected_checks(
        edge_id=edge_id,
        run_id=run_id,
        lease=lease,
        conductor_session_id=conductor.conductor_session["session_id"],
        conductor_principal_id=_credential_principal_id(conductor.conductor_credential),
        executor_session_id=executor.executor_session["session_id"],
        executor_principal_id=_credential_principal_id(executor.executor_credential),
        runtime_git_sha=runtime_git_sha,
    )
    callback_ack = NativeCanaryEdgeAck.expected(
        _native_edge_request(
            canary_id=canary_id,
            packet=packet,
            edge_id=edge_id,
            conductor=conductor,
            executor=executor,
            lease=lease,
            runtime_git_sha=runtime_git_sha,
        )
    )
    return {
        "edge_id": edge_id,
        "conductor_lane": conductor.name,
        "executor_lane": executor.name,
        "retry_generation": int(packet.intent["retry_generation"]),
        "run_id": run_id,
        "broker_created_at": _canonical_timestamp(broker_created_at, "harvested run created_at"),
        "packet_deadline": _canonical_datetime(packet.deadline, "harvested packet deadline"),
        "lease_id_sha256": _sha256_text(str(lease["lease_id"])),
        "work_key_sha256": _sha256_text(packet.work_key),
        "intent_sha256": packet.intent_hash,
        "execution_sha256": packet.execution_hash,
        "conductor_claim_rejection_sha256": str(checks[0].head),
        "executor_claim_sha256": str(checks[1].head),
        "heartbeat_sha256": str(checks[2].head),
        "native_executor_callback_sha256": callback_ack.sha256,
        "accepted_receipt_sha256": canonical_hash(accepted_receipt),
        "reservation": True,
        "executor_only_claim": True,
        "heartbeat": True,
        "native_executor_callback": True,
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
    receipt_target: str,
    clock: Callable[[], datetime],
    client_factory: Callable[..., HttpConductClient],
    endpoint: str,
    timeout: int,
    executor_waker: Callable[[NativeCanaryEdgeRequest], NativeCanaryEdgeAck],
    retry_generation: int = 0,
) -> dict[str, Any]:
    edge_id = _edge_id(canary_id, conductor, executor)
    conductor_client = client_factory(
        endpoint,
        conductor.conductor_credential.token,
        timeout=timeout,
    )
    packet = _packet(
        canary_id=canary_id,
        edge_id=edge_id,
        conductor=conductor,
        executor=executor,
        runtime_git_sha=runtime_git_sha,
        receipt_target=receipt_target,
        now=clock(),
        retry_generation=retry_generation,
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
    status_pair = (node.get("status"), lease.get("state"))
    if status_pair == ("expired", "expired"):
        if submit_status != "duplicate":
            raise ConductCanaryError("fresh canary reservation was already expired")
        if retry_generation >= _MAX_EDGE_RETRY_GENERATION:
            raise ConductCanaryError("canary edge exhausted its single bounded retry generation")
        return _execute_edge(
            canary_id=canary_id,
            conductor=conductor,
            executor=executor,
            runtime_git_sha=runtime_git_sha,
            receipt_target=receipt_target,
            clock=clock,
            client_factory=client_factory,
            endpoint=endpoint,
            timeout=timeout,
            executor_waker=executor_waker,
            retry_generation=retry_generation + 1,
        )
    if status_pair == ("succeeded", "released"):
        if submit_status != "duplicate":
            raise ConductCanaryError("fresh reservation unexpectedly resolved to a terminal canary run")
        accepted = _validate_terminal_receipt(
            node,
            lease,
            packet=stored_packet,
            edge_id=edge_id,
            conductor=conductor,
            executor=executor,
            runtime_git_sha=runtime_git_sha,
        )
        return _edge_evidence(
            packet=stored_packet,
            edge_id=edge_id,
            conductor=conductor,
            executor=executor,
            lease=lease,
            accepted_receipt=accepted,
            runtime_git_sha=runtime_git_sha,
            broker_created_at=node.get("created_at"),
            canary_id=canary_id,
        )

    rejection_digest = _prove_conductor_rejection(
        conductor_client,
        edge_id=edge_id,
        run_id=run_id,
        lease=lease,
        conductor=conductor,
        executor=executor,
    )
    expected_rejection = _expected_checks(
        edge_id=edge_id,
        run_id=run_id,
        lease=lease,
        conductor_session_id=conductor.conductor_session["session_id"],
        conductor_principal_id=_credential_principal_id(conductor.conductor_credential),
        executor_session_id=executor.executor_session["session_id"],
        executor_principal_id=_credential_principal_id(executor.executor_credential),
        runtime_git_sha=runtime_git_sha,
    )[0].head
    if rejection_digest != expected_rejection:
        raise ConductCanaryError("conductor rejection proof does not match the authenticated edge")

    callback_request = _native_edge_request(
        canary_id=canary_id,
        packet=stored_packet,
        edge_id=edge_id,
        conductor=conductor,
        executor=executor,
        lease=lease,
        runtime_git_sha=runtime_git_sha,
    )
    try:
        acknowledgement = executor_waker(callback_request)
    except NativeCanaryExecutorError as exc:
        raise ConductCanaryError(str(exc)) from exc
    expected_acknowledgement = NativeCanaryEdgeAck.expected(callback_request)
    if acknowledgement != expected_acknowledgement:
        raise ConductCanaryError("native executor callback acknowledged a different canary edge")
    terminal_harvest = conductor_client.harvest(run_id)
    terminal_node, terminal_lease, terminal_packet = _validate_harvest_node(
        terminal_harvest,
        packet=stored_packet,
        conductor=conductor,
        executor=executor,
        runtime_git_sha=runtime_git_sha,
        require_exact_deadline=True,
    )
    if (terminal_node.get("status"), terminal_lease.get("state")) != (
        "succeeded",
        "released",
    ):
        raise ConductCanaryError("native executor callback returned without a terminal accepted receipt")
    accepted = _validate_terminal_receipt(
        terminal_node,
        terminal_lease,
        packet=terminal_packet,
        edge_id=edge_id,
        conductor=conductor,
        executor=executor,
        runtime_git_sha=runtime_git_sha,
    )
    return _edge_evidence(
        packet=terminal_packet,
        edge_id=edge_id,
        conductor=conductor,
        executor=executor,
        lease=terminal_lease,
        accepted_receipt=accepted,
        runtime_git_sha=runtime_git_sha,
        broker_created_at=terminal_node.get("created_at"),
        canary_id=canary_id,
    )


def _canonical_receipt_path(path: Path) -> Path:
    expanded = path.expanduser()
    expanded.parent.mkdir(parents=True, exist_ok=True)
    canonical = expanded.resolve(strict=False)
    canonical.parent.mkdir(parents=True, exist_ok=True)
    return canonical


def _runtime_lock_root() -> Path:
    configured = os.environ.get(_LOCK_ROOT_ENV, "").strip()
    if configured:
        root = Path(configured).expanduser()
    else:
        xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", "").strip()
        base = Path(xdg_runtime).expanduser() if xdg_runtime else Path(tempfile.gettempdir()) / f"limen-{os.getuid()}"
        root = base / "conduct-canary-locks"
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if root.is_symlink():
            raise ConductCanaryError("canary runtime lock root must not be a symlink")
        canonical = root.resolve(strict=True)
        metadata = canonical.stat()
        if not stat.S_ISDIR(metadata.st_mode):
            raise ConductCanaryError("canary runtime lock root is not a directory")
        os.chmod(canonical, 0o700)
    except ConductCanaryError:
        raise
    except OSError as exc:
        raise ConductCanaryError("cannot prepare the canary runtime lock root") from exc
    return canonical


@contextmanager
def _receipt_path_lock(path: Path) -> Iterator[Path]:
    canonical = _canonical_receipt_path(path)
    lock_id = _sha256_text(str(canonical))[:24]
    lock_path = _runtime_lock_root() / f"{lock_id}.lock"
    flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ConductCanaryError("receipt path lock is not a regular file")
        os.fchmod(descriptor, 0o600)
    except (OSError, ConductCanaryError) as exc:
        if "descriptor" in locals():
            os.close(descriptor)
        if isinstance(exc, ConductCanaryError):
            raise
        raise ConductCanaryError("cannot open the receipt path lock") from exc
    deadline = time.monotonic() + _PATH_LOCK_TIMEOUT_SECONDS
    while True:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError as exc:
            if time.monotonic() >= deadline:
                os.close(descriptor)
                raise ConductCanaryError("timed out waiting for the bounded receipt path lock") from exc
            time.sleep(_PATH_LOCK_POLL_SECONDS)
        except OSError as exc:
            os.close(descriptor)
            raise ConductCanaryError("cannot acquire the receipt path lock") from exc
    try:
        yield canonical
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        except OSError as exc:
            raise ConductCanaryError("cannot release the receipt path lock") from exc
        finally:
            os.close(descriptor)


def _write_receipt(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    encoded = rendered.encode("utf-8")
    if len(encoded) > _MAX_RECEIPT_BYTES:
        raise ConductCanaryError("canary receipt exceeds its bounded size")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.monotonic_ns()}")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(
            path.parent,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _existing_receipt(path: Path) -> dict[str, Any] | None:
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ConductCanaryError("existing canary receipt is unreadable") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ConductCanaryError("existing canary receipt is not a regular file")
        if before.st_size > _MAX_RECEIPT_BYTES:
            raise ConductCanaryError("existing canary receipt exceeds its bounded size")
        chunks: list[bytes] = []
        consumed = 0
        while consumed <= _MAX_RECEIPT_BYTES:
            chunk = os.read(descriptor, min(65_536, _MAX_RECEIPT_BYTES + 1 - consumed))
            if not chunk:
                break
            chunks.append(chunk)
            consumed += len(chunk)
        after = os.fstat(descriptor)
        if consumed > _MAX_RECEIPT_BYTES or after.st_size > _MAX_RECEIPT_BYTES:
            raise ConductCanaryError("existing canary receipt exceeds its bounded size")
        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or consumed != after.st_size
        ):
            raise ConductCanaryError("existing canary receipt changed while it was read")
        value = json.loads(b"".join(chunks).decode("utf-8"))
    except ConductCanaryError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConductCanaryError("existing canary receipt is unreadable") from exc
    finally:
        os.close(descriptor)
    if not isinstance(value, dict) or value.get("schema_version") != CANARY_SCHEMA:
        raise ConductCanaryError("existing receipt is not a conduct full-mesh canary receipt")
    return value


def _read_existing_receipt(path: Path) -> dict[str, Any] | None:
    with _receipt_path_lock(path) as canonical:
        return _existing_receipt(canonical)


def _commit_receipt(path: Path, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    with _receipt_path_lock(path) as canonical:
        existing = _existing_receipt(canonical)
        if existing is not None:
            if existing.get("canary_id") != payload["canary_id"]:
                raise ConductCanaryError("receipt path already belongs to another canary identity")
            return existing, False
        _write_receipt(canonical, payload)
        return payload, True


def _reuse_existing(
    existing: dict[str, Any],
    *,
    canary_id: str,
    public_runtime: dict[str, Any],
    lanes: tuple[_Lane, ...],
    runtime_git_sha: str,
    receipt_target: str,
    client_factory: Callable[..., HttpConductClient],
    endpoint: str,
    timeout: int,
) -> dict[str, Any]:
    expected_keys = {
        "schema_version",
        "canary_id",
        "receipt_target",
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
        or existing.get("receipt_target") != receipt_target
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
        retry_generation = edge.get("retry_generation")
        if (
            not isinstance(retry_generation, int)
            or isinstance(retry_generation, bool)
            or retry_generation not in range(_MAX_EDGE_RETRY_GENERATION + 1)
        ):
            raise ConductCanaryError("existing edge retry generation is invalid")
        edge_id = _edge_id(canary_id, conductor, executor)
        packet = _packet(
            canary_id=canary_id,
            edge_id=edge_id,
            conductor=conductor,
            executor=executor,
            runtime_git_sha=runtime_git_sha,
            receipt_target=receipt_target,
            now=packet_deadline - _EDGE_DEADLINE,
            retry_generation=retry_generation,
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
            conductor=conductor,
            executor=executor,
            runtime_git_sha=runtime_git_sha,
        )
        expected_edge = _edge_evidence(
            packet=stored_packet,
            edge_id=edge_id,
            conductor=conductor,
            executor=executor,
            lease=lease,
            accepted_receipt=accepted,
            runtime_git_sha=runtime_git_sha,
            broker_created_at=node.get("created_at"),
            canary_id=canary_id,
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
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Run, or read-only re-verify, one exact authenticated full mesh."""

    if not isinstance(client, HttpConductClient):
        raise ConductCanaryError(
            "full-mesh canary requires authenticated remote HttpConductClient; local SQLite is rejected"
        )
    if now is not None and clock is not None:
        raise ConductCanaryError("full-mesh canary accepts either now or clock, not both")
    canonical_receipt_path, receipt_target = _repo_receipt_target(receipt_path)
    edge_clock = clock or ((lambda: now) if now is not None else lambda: datetime.now(UTC))
    environment = os.environ if environ is None else environ
    runtime = _runtime_identity(environment)
    refs = _credential_refs(environment)
    capabilities = client.capabilities()
    _require_remote_runtime_identity(capabilities, runtime)
    refs = _authenticate_credential_refs(
        capabilities,
        refs,
        installed_runtime=runtime,
        client_factory=client_factory,
        endpoint=client.endpoint,
        timeout=client.timeout,
    )
    lanes = _discover_lanes(capabilities, refs)
    canary_id, public_runtime = _canary_identity(client, runtime, lanes, receipt_target)
    existing = _read_existing_receipt(canonical_receipt_path)
    if existing is not None:
        return _reuse_existing(
            existing,
            canary_id=canary_id,
            public_runtime=public_runtime,
            lanes=lanes,
            runtime_git_sha=runtime["git_sha"],
            receipt_target=receipt_target,
            client_factory=client_factory,
            endpoint=client.endpoint,
            timeout=client.timeout,
        )

    try:
        resolved_bridge = resolve_native_canary_bridge(environment)
    except NativeCanaryExecutorError as exc:
        raise ConductCanaryError(str(exc)) from exc

    def resolved_executor_waker(
        request: NativeCanaryEdgeRequest,
    ) -> NativeCanaryEdgeAck:
        return wake_native_canary_edge(
            request,
            environ=environment,
            resolved_bridge=resolved_bridge,
        )

    edges: list[dict[str, Any]] = []
    for conductor in lanes:
        for executor in lanes:
            edges.append(
                _execute_edge(
                    canary_id=canary_id,
                    conductor=conductor,
                    executor=executor,
                    runtime_git_sha=runtime["git_sha"],
                    receipt_target=receipt_target,
                    clock=edge_clock,
                    client_factory=client_factory,
                    endpoint=client.endpoint,
                    timeout=client.timeout,
                    executor_waker=resolved_executor_waker,
                )
            )
    required = len(lanes) * len(lanes)
    if len(edges) != required:
        raise ConductCanaryError("full-mesh canary did not complete every ordered edge")
    payload = {
        "schema_version": CANARY_SCHEMA,
        "canary_id": canary_id,
        "receipt_target": receipt_target,
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
    committed, created = _commit_receipt(canonical_receipt_path, payload)
    if created:
        return payload
    return _reuse_existing(
        committed,
        canary_id=canary_id,
        public_runtime=public_runtime,
        lanes=lanes,
        runtime_git_sha=runtime["git_sha"],
        receipt_target=receipt_target,
        client_factory=client_factory,
        endpoint=client.endpoint,
        timeout=client.timeout,
    )
