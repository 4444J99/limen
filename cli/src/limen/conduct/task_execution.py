"""Broker-reserved execution for one canonical task projection.

The task board is remote-owned.  This seam consumes the keeper's exact task
receipt, discovers currently reachable execution adapters, registers each with
its own credential-bound principal, reserves one direct ``fanout-leaf`` packet,
and wakes only the executor selected by the keeper.  It never falls back to a
provider CLI launch outside conduct.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from typing import Any

from limen.conduct.client import HttpConductClient, LocalConductClient, client_from_env
from limen.conduct.models import (
    AgentIdentityV1,
    AuthorityEnvelopeV1,
    ConductorSessionV1,
    FanoutBoundsV1,
    ResourceClaimV1,
    RetryPolicyV1,
    SpendEnvelopeV1,
    WorkPacketV1,
    canonical_hash,
)
from limen.execution_contract import execution_contract_hash
from limen.fanout_executor import (
    CODE_RECEIPT_CAPABILITIES,
    ExecutionLane,
    discover_execution_adapters,
    launch_ready_nodes,
    remote_default_head,
    wake_executor_workers,
)
from limen.models import Task
from limen.work_loan import task_work_loan_readiness

_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_GIT_RECEIPT_RE = re.compile(r"^git:(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+):(?P<path>[^#\s]+)(?:#.*)?$")


class TaskExecutionError(RuntimeError):
    """The canonical task could not be safely reserved or woken."""


_ACTIVE_CONDUCT_RUN_STATUSES = frozenset({"waiting", "reserved", "running", "stop_requested"})


def _existing_task_execution(task: Task, keeper: Any) -> dict[str, Any] | None:
    """Reuse broker-owned execution for an already-active canonical task."""

    if task.status not in {"dispatched", "in_progress"}:
        return None
    lookup = getattr(keeper, "task_run", None)
    if not callable(lookup):
        raise TaskExecutionError("conduct client cannot prove the canonical task's active run")
    existing = lookup(task.id)
    if not existing.get("found"):
        raise TaskExecutionError(f"canonical task {task.id} is active without a conduct run")
    status = str(existing.get("status") or "")
    if status in _ACTIVE_CONDUCT_RUN_STATUSES:
        result_status = "already_running"
    elif status == "succeeded":
        result_status = "result_pending_harvest"
    else:
        raise TaskExecutionError(f"canonical task conduct run is terminal ({status or 'unknown'})")
    return {
        "schema_version": "limen.task_execution_start.v1",
        "status": result_status,
        "run_id": str(existing.get("run_id") or ""),
        "root_run_id": str(existing.get("root_run_id") or ""),
        "executor_session_id": str(existing.get("executor_session_id") or ""),
        "targeted_launch_count": 0,
        "executor_wakes": [],
        "unavailable_adapters": [],
        "idempotent": True,
    }


def _registered_session(response: Any) -> ConductorSessionV1:
    payload = response.get("session", response) if isinstance(response, dict) else response
    if not isinstance(payload, dict):
        raise TaskExecutionError("conduct registration returned no canonical session")
    fields = set(ConductorSessionV1.model_fields)
    try:
        return ConductorSessionV1.model_validate({key: value for key, value in payload.items() if key in fields})
    except ValueError as exc:
        raise TaskExecutionError("conduct registration returned an invalid canonical session") from exc


def _normalize_path(value: str) -> str:
    if not value or value.startswith("/") or "\x00" in value:
        raise TaskExecutionError("task execution paths must be repository-relative")
    normalized = str(PurePosixPath(value)).rstrip("/") or "."
    if normalized == ".." or normalized.startswith("../"):
        raise TaskExecutionError("task execution path escapes its owner repository")
    if normalized == "tasks.yaml" or normalized.startswith("tasks.yaml/"):
        raise TaskExecutionError("executor authority may not include the keeper-owned tasks.yaml projection")
    return normalized


def task_execution_paths(task: Task) -> tuple[str, ...]:
    """Derive bounded write authority from typed task state and its receipt target."""

    values: list[str] = []
    extras = task.model_extra or {}
    raw_paths = extras.get("allowed_paths")
    if isinstance(raw_paths, (list, tuple)):
        values.extend(str(value) for value in raw_paths if str(value).strip())
    raw_contract = task.workstream_contract
    contract: dict[str, Any] = raw_contract if isinstance(raw_contract, dict) else {}
    raw_authority = contract.get("authority")
    authority: dict[str, Any] = raw_authority if isinstance(raw_authority, dict) else {}
    contract_paths = authority.get("path_prefixes")
    if isinstance(contract_paths, (list, tuple)):
        values.extend(str(value) for value in contract_paths if str(value).strip())
    receipt = _GIT_RECEIPT_RE.fullmatch(str(task.receipt_target or "").strip())
    if receipt:
        if receipt.group("repository").casefold() != str(task.repo or "").casefold():
            raise TaskExecutionError("task receipt repository does not match its owner repository")
        values.append(receipt.group("path"))
    paths = tuple(sorted({_normalize_path(value) for value in values}))
    if not paths:
        raise TaskExecutionError("canonical task has no bounded repository path authority")
    return paths


def _task_deadline(now: datetime) -> datetime:
    deadline = now + timedelta(hours=6)
    raw_parent = os.environ.get("LIMEN_WORKSTREAM_DEADLINE_EPOCH", "").strip()
    if raw_parent:
        try:
            parent = datetime.fromtimestamp(int(raw_parent), tz=UTC) - timedelta(minutes=30)
        except (ValueError, OSError, OverflowError) as exc:
            raise TaskExecutionError("parent workstream deadline is malformed") from exc
        deadline = min(deadline, parent)
    if deadline <= now + timedelta(minutes=1):
        raise TaskExecutionError("insufficient finite workstream runway remains for executor reservation")
    return deadline


def _topic_branch(task: Task, contract_hash: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", task.id.casefold()).strip("-._") or "owner-task"
    return f"work/{slug[:80]}-{contract_hash[:10]}"


def build_task_execution_packet(
    task: Task,
    *,
    conductor: AgentIdentityV1,
    executor_session_id: str,
    exact_base: str,
    deadline: datetime,
) -> WorkPacketV1:
    """Compile one remote task receipt into a deterministic direct conduct packet."""

    repository = str(task.repo or "").strip()
    if not _REPOSITORY_RE.fullmatch(repository):
        raise TaskExecutionError("canonical task has no exact owner/repository")
    if task.status not in {"open", "dispatched", "in_progress"}:
        raise TaskExecutionError(
            f"canonical task is {task.status}; only an open or already-active task may be reserved"
        )
    if not task.predicate or not task.receipt_target:
        raise TaskExecutionError("canonical task has no executable predicate and durable receipt target")
    underwriting = task_work_loan_readiness(task)
    if not underwriting.ready or underwriting.loan is None:
        raise TaskExecutionError(str(underwriting.reason_code or "task-not-underwritten"))
    paths = task_execution_paths(task)
    contract_hash = execution_contract_hash(task)
    topic_branch = _topic_branch(task, contract_hash)
    seed = canonical_hash({"task_id": task.id, "contract": contract_hash, "exact_base": exact_base})
    owner, repo = repository.split("/", 1)
    claims = tuple(
        [ResourceClaimV1(key=f"branch/{owner}/{repo}/{topic_branch}")]
        + [ResourceClaimV1(key=f"path/{owner}/{repo}/{exact_base}/{path}") for path in paths]
    )
    return WorkPacketV1(
        work_id=f"owner-task-{seed[:32]}",
        work_key=f"owner-task:{seed}",
        intent={
            "kind": "fanout-leaf",
            "intended_effect": str(task.context or task.description or task.title)[:8192],
            "task_id": task.id,
            "execution_contract_hash": contract_hash,
        },
        execution={
            "adapter": "fanout",
            "owner_repository": repository,
            "exact_base": exact_base,
            "topic_branch": topic_branch,
            "dependencies": [],
            "local_heavy_allowed": False,
            "executor_session_id": executor_session_id,
            "observed_heads": {repository: exact_base},
        },
        initiator=conductor,
        conductor=conductor,
        preferred_agent=task.target_agent,
        required_capabilities=CODE_RECEIPT_CAPABILITIES,
        resource_claims=claims,
        predicate=task.predicate,
        receipt_target=task.receipt_target,
        work_loan=underwriting.loan,
        authority=AuthorityEnvelopeV1(
            actions=frozenset({"read", "write"}),
            repositories=frozenset({repository}),
            path_prefixes=frozenset(paths),
            may_delegate=False,
        ),
        deadline=deadline,
        spend=SpendEnvelopeV1(unit="runs", limit=task.budget_cost),
        retry=RetryPolicyV1(max_attempts=1, transient_only=True),
        fanout=FanoutBoundsV1(max_children=0, max_depth=0),
        effect="write",
        task_id=task.id,
    )


def _executor_client(conductor_client: Any, adapter: Any) -> Any:
    if not isinstance(conductor_client, HttpConductClient):
        return conductor_client
    token_env = str(getattr(adapter, "conduct_token_env", "LIMEN_CONDUCT_EXECUTOR_TOKEN"))
    token = os.environ.get(token_env, "").strip()  # allow-secret: environment reference only
    if not token:
        raise TaskExecutionError(f"live adapter {adapter.name} needs its registered credential {token_env}")
    if token == conductor_client.token:  # allow-secret: compare references, never values
        raise TaskExecutionError(f"live adapter {adapter.name} needs a distinct registered credential in {token_env}")
    return HttpConductClient(conductor_client.endpoint, token, timeout=conductor_client.timeout)


def start_task_execution(
    task: Task,
    *,
    client: Any | None = None,
    execution_adapters: tuple[Any, ...] | None = None,
    exact_base: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Reserve and wake one exact task through distinct conductor/executor principals."""

    now = now or datetime.now(UTC)
    keeper = client or client_from_env()
    repository = str(task.repo or "").strip()
    if not _REPOSITORY_RE.fullmatch(repository):
        raise TaskExecutionError("canonical task has no exact owner/repository")
    existing = _existing_task_execution(task, keeper)
    if existing is not None:
        return existing
    base = exact_base or remote_default_head(repository)
    deadline = _task_deadline(now)
    conductor_session_id = f"overnight-owner-conductor-{canonical_hash(repository)[:12]}"
    requested_conductor = AgentIdentityV1(
        agent=os.environ.get("LIMEN_AGENT", "github_actions") or "github_actions",
        surface="overnight-producer",
        session_id=conductor_session_id,
    )
    conductor = _registered_session(
        keeper.register(
            ConductorSessionV1(
                session_id=conductor_session_id,
                identity=requested_conductor,
                origin="relay",
                capabilities=frozenset({"conduct"}),
                transport="native",
                concurrency=1,
                human_protected=False,
            )
        )
    )
    if "conduct" not in conductor.capabilities:
        raise TaskExecutionError("authenticated producer session lacks conduct capability")

    discovered = (
        execution_adapters if execution_adapters is not None else discover_execution_adapters(frozenset({repository}))
    )
    if not discovered:
        raise TaskExecutionError("no live execution adapter can reach the task owner repository")
    lanes: dict[str, ExecutionLane] = {}
    registered_sessions: dict[str, ConductorSessionV1] = {}
    unavailable: list[dict[str, str]] = []
    for adapter in discovered:
        probe_packet = {
            "effect": "write",
            "execution": {"owner_repository": repository},
            "authority": {"path_prefixes": list(task_execution_paths(task))},
        }
        try:
            if not adapter.eligible(probe_packet):
                unavailable.append({"adapter": adapter.name, "reason": "owner repository is not reachable"})
                continue
            adapter_client = _executor_client(keeper, adapter)
            session_id = f"overnight-{adapter.name}-{canonical_hash(repository)[:12]}"
            requested_executor = AgentIdentityV1(
                agent=task.target_agent,
                surface="remote",
                session_id=session_id,
            )
            registered = _registered_session(
                adapter_client.register(
                    ConductorSessionV1(
                        session_id=session_id,
                        identity=requested_executor,
                        origin="relay",
                        capabilities=adapter.capabilities,
                        transport=adapter.transport,
                        harvest_method="provider-attempt-receipt",
                        concurrency=adapter.concurrency,
                        quota_remaining=adapter.quota_remaining,
                        cost_per_run=adapter.cost_per_run,
                        receipt_quality=adapter.receipt_quality,
                        accepting_work=True,
                    )
                )
            )
            if CODE_RECEIPT_CAPABILITIES - registered.capabilities:
                raise TaskExecutionError("credential-bound executor omitted required receipt capabilities")
            registered_sessions[session_id] = registered
            lanes[session_id] = ExecutionLane(primary=adapter, adapters=(adapter,), client=adapter_client)
        except Exception as exc:
            unavailable.append({"adapter": adapter.name, "reason": str(exc)[:300]})
    if not lanes:
        detail = "; ".join(f"{row['adapter']}: {row['reason']}" for row in unavailable)
        raise TaskExecutionError(f"no credential-bound execution adapter is healthy: {detail}")

    def lane_key(session_id: str) -> tuple[Any, ...]:
        session = registered_sessions[session_id]
        return (
            0 if session.identity.agent == task.target_agent else 1,
            -session.receipt_quality,
            session.cost_per_run if session.cost_per_run is not None else float("inf"),
            session.identity.agent,
            session_id,
        )

    executor_session_id = min(lanes, key=lane_key)
    packet = build_task_execution_packet(
        task,
        conductor=conductor.identity,
        executor_session_id=executor_session_id,
        exact_base=base,
        deadline=deadline,
    )
    result = keeper.submit(packet)
    if result.get("status") == "busy":
        raise TaskExecutionError(
            f"conduct resources are busy for canonical task {task.id} ({len(result.get('conflicts') or [])} conflict(s))"
        )
    if result.get("status") not in {"reserved", "duplicate"}:
        raise TaskExecutionError(f"conduct did not reserve canonical task {task.id}: {result.get('status')}")
    root_run_id = str(result.get("root_run_id") or result.get("run_id") or "")
    graph = keeper.graph(root_run_id)
    node = next((row for row in graph.get("nodes", []) if row.get("run_id") == result.get("run_id")), None)
    if not isinstance(node, dict):
        raise TaskExecutionError("conduct reservation graph omitted the canonical task run")
    node_status = str(node.get("status") or "")
    if node_status in {"succeeded"}:
        return {
            "schema_version": "limen.task_execution_start.v1",
            "status": "result_pending_harvest",
            "run_id": result["run_id"],
            "root_run_id": root_run_id,
            "executor_session_id": str(node.get("executor_session_id") or executor_session_id),
            "targeted_launch_count": 0,
            "executor_wakes": [],
            "unavailable_adapters": unavailable,
            "idempotent": True,
        }
    if node_status not in {"reserved", "running"}:
        raise TaskExecutionError(f"canonical task conduct run is terminal ({node_status})")
    selected_session_id = str(node.get("executor_session_id") or "")
    selected_lane = lanes.get(selected_session_id)
    if selected_lane is None:
        raise TaskExecutionError("keeper selected an executor outside the credential-bound wake set")
    selected = {selected_session_id: selected_lane}
    if isinstance(keeper, LocalConductClient):
        attempts = launch_ready_nodes(root_run_id, client=keeper, adapters_by_session=selected)
        wakes: list[dict[str, str]] = []
        launched = len(attempts)
        if result.get("status") == "duplicate" and not attempts:
            return {
                "schema_version": "limen.task_execution_start.v1",
                "status": "already_running",
                "run_id": result["run_id"],
                "root_run_id": root_run_id,
                "executor_session_id": selected_session_id,
                "targeted_launch_count": 0,
                "executor_wakes": [],
                "attempts": [],
                "unavailable_adapters": unavailable,
                "idempotent": True,
            }
    else:
        attempts = []
        wakes = wake_executor_workers(root_run_id, selected)
        launched = len(wakes)
    if launched != 1:
        raise TaskExecutionError(f"canonical task reserved but executor wake count was {launched}, expected 1")
    return {
        "schema_version": "limen.task_execution_start.v1",
        "status": "already_running" if result.get("status") == "duplicate" else "launched",
        "run_id": result["run_id"],
        "root_run_id": root_run_id,
        "executor_session_id": selected_session_id,
        "targeted_launch_count": 1,
        "executor_wakes": wakes,
        "attempts": attempts,
        "unavailable_adapters": unavailable,
        "idempotent": result.get("status") == "duplicate",
    }
