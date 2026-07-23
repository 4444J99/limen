"""Non-model keeper for symmetric peer delegation, leases, fencing, and receipts."""

from __future__ import annotations

import copy
import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from pathlib import PurePath
from typing import Any, Callable

from limen.conduct.models import (
    AgentIdentityV1,
    AuthorityEnvelopeV1,
    ConductorSessionV1,
    ConductPrincipalV1,
    LeaseV1,
    ExecutorAttemptV1,
    ResourceClaimV1,
    RunReceiptV1,
    WorkPacketV1,
    canonical_hash,
    utc_now,
)
from limen.conduct.resources import conflicting_keys, parse_resource, sorted_claims
from limen.conduct.store import MemoryStateStore, StateStore
from limen.work_loan import packet_is_non_capacity_projection, packet_work_loan_missing, work_loan_denial


class ConductError(RuntimeError):
    pass


class ConductConflict(ConductError):
    pass


def _dump(model) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _load_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _event(state: dict[str, Any], kind: str, **payload: Any) -> None:
    state["events"].append(
        {
            "sequence": len(state["events"]) + 1,
            "timestamp": utc_now().isoformat(),
            "kind": kind,
            **payload,
        }
    )


def _covered_atoms(child: frozenset[str], parent: frozenset[str]) -> bool:
    return "*" in parent or child.issubset(parent)


def _covered_paths(child: frozenset[str], parent: frozenset[str]) -> bool:
    if "*" in parent or "." in parent:
        return True
    for path in child:
        if not any(path == base or path.startswith(base.rstrip("/") + "/") for base in parent):
            return False
    return True


def authority_attenuates(child: AuthorityEnvelopeV1, parent: AuthorityEnvelopeV1) -> bool:
    return (
        _covered_atoms(child.actions, parent.actions)
        and _covered_atoms(child.repositories, parent.repositories)
        and _covered_paths(child.path_prefixes, parent.path_prefixes)
        and _covered_atoms(child.external_effects, parent.external_effects)
        and (parent.may_delegate or not child.may_delegate)
    )


def _is_task_compatibility_packet(packet: WorkPacketV1) -> bool:
    return packet_is_non_capacity_projection(packet)


def _require_work_loan(packet: WorkPacketV1) -> None:
    """Admit only underwritten execution or the exact zero-run task projection."""

    missing = packet_work_loan_missing(packet)
    if missing:
        raise ConductConflict(work_loan_denial(missing))


class ConductBroker:
    """Serialize all coordination state through one transactional keeper."""

    def __init__(
        self,
        store: StateStore,
        *,
        session_ttl: timedelta = timedelta(minutes=5),
        adoption_after: timedelta = timedelta(minutes=10),
        lease_ttl: timedelta = timedelta(minutes=15),
        capability_secret: str | bytes | None = None,
    ):
        self.store = store
        self.session_ttl = session_ttl
        self.adoption_after = adoption_after
        self.lease_ttl = lease_ttl
        secret = capability_secret or secrets.token_bytes(32)
        self.capability_secret = secret.encode("utf-8") if isinstance(secret, str) else secret

    def register(
        self,
        session: ConductorSessionV1,
        *,
        principal: ConductPrincipalV1 | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or utc_now()
        principal, principal_enforced = self._principal_for_session(session, principal)
        self._require_role(principal, "conductor", "executor")
        session = self._bind_session_identity(session, principal)
        with self.store.transaction() as state:
            state.setdefault("receipt_index", {})
            state.setdefault("session_principals", {})
            current = state["sessions"].get(session.session_id)
            if current:
                prior = ConductorSessionV1.model_validate(current)
                if prior.identity != session.identity:
                    raise ConductConflict("session_id is already registered to another identity")
                session = session.model_copy(
                    update={
                        "registered_at": prior.registered_at,
                        "heartbeat_at": now,
                        # A protected direct session cannot be downgraded by re-registration.
                        "human_protected": prior.human_protected or session.human_protected,
                    }
                )
            else:
                session = session.model_copy(update={"registered_at": now, "heartbeat_at": now})
            prior_principal = state["session_principals"].get(session.session_id)
            if prior_principal and prior_principal != principal.principal_id:
                raise ConductConflict("session_id is already bound to another principal")
            if session.worktree:
                claimed = str(PurePath(session.worktree))
                for raw in state["sessions"].values():
                    owner = ConductorSessionV1.model_validate(raw)
                    if owner.session_id == session.session_id or not owner.worktree:
                        continue
                    if str(PurePath(owner.worktree)) == claimed and now - owner.heartbeat_at <= self.session_ttl:
                        raise ConductConflict(f"worktree is already owned by healthy session {owner.session_id}")
            state["sessions"][session.session_id] = _dump(session)
            state["session_principals"][session.session_id] = principal.principal_id
            _event(
                state,
                "session.registered",
                session_id=session.session_id,
                agent=session.identity.agent,
                principal_id=principal.principal_id if principal_enforced else "local-development",
            )
            return _dump(session)

    def capabilities(self, *, now: datetime | None = None) -> dict[str, Any]:
        now = now or utc_now()
        with self.store.transaction() as state:
            active_load = self._active_load(state, now)
            sessions = []
            for raw in state["sessions"].values():
                session = ConductorSessionV1.model_validate(raw)
                sessions.append(
                    {
                        **_dump(session),
                        "healthy": now - session.heartbeat_at <= self.session_ttl,
                        "active_leases": active_load.get(session.session_id, 0),
                    }
                )
            sessions.sort(key=lambda row: (row["identity"]["agent"], row["session_id"]))
            return {
                "schema_version": "limen.conduct_capabilities.v1",
                "generated_at": now.isoformat(),
                "sessions": sessions,
            }

    def submit(
        self,
        packet: WorkPacketV1,
        *,
        principal: ConductPrincipalV1 | None = None,
        now: datetime | None = None,
        project_task_event: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        now = now or utc_now()
        principal, principal_enforced = self._principal_for_identity(packet.conductor, principal)
        self._require_role(principal, "conductor", "compatibility")
        _require_work_loan(packet)
        if packet.deadline <= now:
            raise ConductError("work packet deadline has already passed")
        with self.store.transaction() as state:
            state.setdefault("receipt_index", {})
            state.setdefault("work_key_index", {})
            state.setdefault("session_principals", {})
            self._expire_leases(state, now)
            conductor_raw = state["sessions"].get(packet.conductor.session_id)
            if not conductor_raw:
                raise ConductConflict("packet conductor must be a registered session")
            conductor = ConductorSessionV1.model_validate(conductor_raw)
            if conductor.identity != self._bind_conductor_identity(packet.conductor, principal):
                raise ConductConflict("packet conductor identity does not match its registered session")
            if now - conductor.heartbeat_at > self.session_ttl:
                raise ConductConflict("packet conductor session is not healthy")
            if state["session_principals"].get(conductor.session_id) != principal.principal_id:
                raise ConductConflict("packet conductor is not bound to the authenticated principal")
            adapter = str(packet.execution.get("adapter") or "")
            needed_capability = "task-submit" if adapter == "tabularius" else "conduct"
            if needed_capability not in conductor.capabilities:
                raise ConductConflict(f"packet conductor lacks required {needed_capability} capability")
            by_id = state["work_index"].get(packet.work_id)
            by_key = state["work_key_index"].get(packet.work_key)
            if by_id and by_key and by_id != by_key:
                raise ConductConflict("work id/key indexes disagree")
            if packet.parent_run_id and by_key:
                cursor = state["runs"].get(packet.parent_run_id)
                while cursor:
                    ancestor = WorkPacketV1.model_validate(cursor["packet"])
                    if packet.work_key == ancestor.work_key:
                        raise ConductConflict("repeated ancestry work_key/cycle rejected")
                    cursor = state["runs"].get(cursor.get("parent_run_id"))
            duplicate = by_id or by_key
            if duplicate:
                run = state["runs"][duplicate]
                stored = WorkPacketV1.model_validate(run["packet"])
                if stored.intent_hash != packet.intent_hash or stored.execution_hash != packet.execution_hash:
                    raise ConductConflict("work id/key was reused with different immutable hashes")
                if (
                    stored.work_key != packet.work_key
                    or stored.initiator != packet.initiator
                    or stored.conductor != packet.conductor
                    or stored.authority != packet.authority
                    or stored.resource_claims != packet.resource_claims
                    or stored.predicate != packet.predicate
                    or stored.receipt_target != packet.receipt_target
                    or stored.work_loan != packet.work_loan
                ):
                    raise ConductConflict("duplicate work changed its identity, authority, or contract")
                state["work_index"][packet.work_id] = duplicate
                return self._submit_result(state, run, duplicate=True)

            parent = self._validate_lineage(
                state,
                packet,
                principal_id=principal.principal_id if principal_enforced else None,
            )
            executor = self._select_executor(state, packet, now)
            claims = self._effective_claims(packet)
            conflicts: list[dict[str, Any]] = []
            for lease_raw in state["leases"].values():
                lease = LeaseV1.model_validate(lease_raw)
                if lease.state not in {"reserved", "active"}:
                    continue
                pairs = conflicting_keys(claims, lease.resources)
                if pairs:
                    conflicts.append({"lease_id": lease.lease_id, "run_id": lease.run_id, "keys": pairs})
            if conflicts:
                busy_id = (
                    "busy-"
                    + canonical_hash(
                        {
                            "work_id": packet.work_id,
                            "intent_hash": packet.intent_hash,
                            "execution_hash": packet.execution_hash,
                            "conflicts": conflicts,
                        }
                    )[:24]
                )
                return {
                    "schema_version": "limen.conduct_submit_result.v1",
                    "status": "busy",
                    "busy_receipt_id": busy_id,
                    "work_id": packet.work_id,
                    "conflicts": conflicts,
                }

            run_id = self._run_id(packet)
            if packet.root_run_id and packet.root_run_id != (parent["root_run_id"] if parent else run_id):
                raise ConductConflict("root_run_id does not match the broker-owned lineage root")
            root_run_id = parent["root_run_id"] if parent else run_id
            generation = int(state.get("next_generation", 0)) + 1
            state["next_generation"] = generation
            resource_generations: dict[str, int] = {}
            for claim in claims:
                prior = int(state["resource_generations"].get(claim.key, 0))
                resource_generations[claim.key] = prior + 1
                state["resource_generations"][claim.key] = prior + 1
            lease_id = f"lease-{generation}-{run_id.removeprefix('run-')[:16]}"
            executor_principal_id = state["session_principals"].get(executor.session_id)
            if _is_task_compatibility_packet(packet):
                executor_principal_id = principal.principal_id
            if not executor_principal_id:
                raise ConductConflict("selected executor session has no authenticated principal binding")
            token = self._capability_token(lease_id, generation, executor_principal_id)
            observed_heads = {
                str(key): str(value)
                for key, value in (packet.execution.get("observed_heads") or {}).items()
                if key and value
            }
            hard_deadline = min(packet.deadline, now + self.lease_ttl)
            lease = LeaseV1(
                lease_id=lease_id,
                run_id=run_id,
                executor=executor.identity,
                executor_principal_id=executor_principal_id,
                resources=claims,
                observed_heads=observed_heads,
                generation=generation,
                resource_generations=resource_generations,
                capability_token_hash=self._token_hash(token),
                acquired_at=now,
                heartbeat_at=now,
                hard_deadline=hard_deadline,
            )
            run = {
                "run_id": run_id,
                "root_run_id": root_run_id,
                "parent_run_id": packet.parent_run_id,
                "packet": _dump(packet),
                "conductor_session_id": packet.conductor.session_id,
                "conductor_principal_id": principal.principal_id,
                "executor_session_id": executor.session_id,
                "lease_id": lease_id,
                "status": "reserved",
                "children": [],
                "receipts": [],
                "attempts": [],
                "projection_receipts": [],
                "compatibility_projection": _is_task_compatibility_packet(packet),
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
            state["runs"][run_id] = run
            state["leases"][lease_id] = _dump(lease)
            state["work_index"][packet.work_id] = run_id
            state["work_key_index"][packet.work_key] = run_id
            if parent:
                parent["children"].append(run_id)
                parent["updated_at"] = now.isoformat()
            _event(
                state,
                "run.reserved",
                run_id=run_id,
                root_run_id=root_run_id,
                executor_session_id=executor.session_id,
                lease_id=lease_id,
                generation=generation,
            )
            if run["compatibility_projection"]:
                if project_task_event is None:
                    raise ConductConflict("task compatibility submission requires the keeper projection handler")
                projection_event: dict[str, Any] = {
                    "schema_version": "limen.task_packet_projection_event.v1",
                    "event_id": f"conduct:{run_id}:{generation}:compatibility",
                    "kind": packet.intent["kind"],
                    "timestamp": now.isoformat(),
                    "task_id": packet.task_id,
                    "run_id": run_id,
                    "lease_id": lease_id,
                    "generation": generation,
                    "agent": packet.conductor.agent,
                    "session_id": packet.conductor.session_id,
                    "lease_executor": _dump(lease.executor),
                    "intent": packet.intent,
                }
                prior_projection = state.get("local_board_projection")
                if isinstance(prior_projection, dict):
                    projection_event["board_projection"] = copy.deepcopy(prior_projection)
                receipt = dict(project_task_event(projection_event))
                if not isinstance(receipt, dict) or not isinstance(receipt.get("task"), dict):
                    raise ConductError("task compatibility projection handler returned no canonical task receipt")
                board_projection = receipt.pop("board_projection", None)
                if not isinstance(board_projection, dict) or not isinstance(board_projection.get("tasks"), list):
                    raise ConductError("task compatibility projection handler returned no canonical board projection")
                state["local_board_projection"] = copy.deepcopy(board_projection)
                run["projection_receipts"] = [receipt]
                run["status"] = "succeeded"
                run["updated_at"] = now.isoformat()
                lease = lease.model_copy(update={"state": "released", "heartbeat_at": now})
                state["leases"][lease_id] = _dump(lease)
                _event(
                    state,
                    "task.compatibility_applied",
                    run_id=run_id,
                    task_id=packet.task_id,
                    intent_kind=packet.intent["kind"],
                    lease_id=lease_id,
                    generation=generation,
                )
            result = self._submit_result(state, run)
            return result

    def submit_graph(
        self,
        packets: tuple[WorkPacketV1, ...],
        *,
        principal: ConductPrincipalV1 | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Reserve a complete graph or leave the keeper byte-for-byte unchanged."""

        if not packets:
            raise ConductError("conduct graph submission requires at least one packet")
        if any(_is_task_compatibility_packet(packet) or packet.task_id for packet in packets):
            raise ConductConflict("task-board packets are not accepted in graph submissions")
        for packet in packets:
            _require_work_loan(packet)
        now = now or utc_now()
        resolved, _ = self._principal_for_identity(packets[0].conductor, principal)
        self._require_role(resolved, "conductor")
        if any(packet.conductor.session_id != packets[0].conductor.session_id for packet in packets):
            raise ConductConflict("atomic graph packets must share one owning conductor session")
        with self.store.transaction() as state:
            staged_store = MemoryStateStore(state)
            staged = ConductBroker(
                staged_store,
                session_ttl=self.session_ttl,
                adoption_after=self.adoption_after,
                lease_ttl=self.lease_ttl,
                capability_secret=self.capability_secret,
            )
            results = []
            for index, packet in enumerate(packets):
                dependencies = packet.execution.get("dependencies") or []
                if dependencies:
                    result = staged._defer_dependency_packet(
                        packet,
                        principal=resolved,
                        now=now,
                    )
                else:
                    result = staged.submit(packet, principal=resolved, now=now)
                if result["status"] == "busy":
                    return {
                        "schema_version": "limen.conduct_graph_submit_result.v1",
                        "status": "busy",
                        "work_id": result["work_id"],
                        "conflicts": result["conflicts"],
                    }
                results.append(result)
                if index == 0 and packet.intent.get("kind") == "fanout-root" and result["status"] != "duplicate":
                    staged._start_fanout_root(result["run_id"], now=now)
            committed = staged_store.snapshot()
            state.clear()
            state.update(committed)
            return {
                "schema_version": "limen.conduct_graph_submit_result.v1",
                "status": "reserved",
                "root_run_id": results[0]["root_run_id"],
                "runs": results,
            }

    def _start_fanout_root(self, run_id: str, *, now: datetime) -> None:
        """Turn a fanout root into a keeper-owned campaign, not an executor job."""

        with self.store.transaction() as state:
            run = state["runs"][run_id]
            lease = LeaseV1.model_validate(state["leases"][run["lease_id"]])
            state["leases"][lease.lease_id] = _dump(lease.model_copy(update={"state": "released", "heartbeat_at": now}))
            run["status"] = "running"
            run["executor_session_id"] = None
            run["updated_at"] = now.isoformat()
            _event(state, "fanout.campaign_started", run_id=run_id)

    def _defer_dependency_packet(
        self,
        packet: WorkPacketV1,
        *,
        principal: ConductPrincipalV1,
        now: datetime,
    ) -> dict[str, Any]:
        """Atomically register a dependent node without leasing its resources early."""

        _require_work_loan(packet)
        if packet.deadline <= now:
            raise ConductError("work packet deadline has already passed")
        dependencies = tuple(str(item) for item in packet.execution.get("dependencies") or ())
        if not dependencies:
            raise ConductError("dependency deferral requires at least one dependency")
        with self.store.transaction() as state:
            conductor_raw = state["sessions"].get(packet.conductor.session_id)
            if not conductor_raw:
                raise ConductConflict("packet conductor must be a registered session")
            conductor = ConductorSessionV1.model_validate(conductor_raw)
            if conductor.identity != self._bind_conductor_identity(packet.conductor, principal):
                raise ConductConflict("packet conductor identity does not match its registered session")
            if state["session_principals"].get(conductor.session_id) != principal.principal_id:
                raise ConductConflict("packet conductor is not bound to the authenticated principal")
            by_id = state["work_index"].get(packet.work_id)
            by_key = state["work_key_index"].get(packet.work_key)
            if by_id or by_key:
                duplicate = by_id or by_key
                run = state["runs"][duplicate]
                stored = WorkPacketV1.model_validate(run["packet"])
                if (
                    stored.intent_hash != packet.intent_hash
                    or stored.execution_hash != packet.execution_hash
                    or stored.work_key != packet.work_key
                ):
                    raise ConductConflict("work id/key was reused with different immutable hashes")
                if run["status"] == "waiting":
                    return {
                        "schema_version": "limen.conduct_submit_result.v1",
                        "status": "duplicate",
                        "duplicate": True,
                        "work_id": packet.work_id,
                        "run_id": run["run_id"],
                        "root_run_id": run["root_run_id"],
                        "executor_session_id": None,
                        "lease": None,
                    }
                return self._submit_result(state, run, duplicate=True)
            parent = self._validate_lineage(state, packet, principal_id=principal.principal_id)
            if parent is None:
                raise ConductConflict("dependent fanout node requires a parent run")
            dependency_runs = []
            for dependency in dependencies:
                dependency_id = state["work_index"].get(dependency)
                if not dependency_id:
                    raise ConductConflict(f"fanout dependency is not registered: {dependency}")
                dependency_run = state["runs"][dependency_id]
                if dependency_run["root_run_id"] != parent["root_run_id"]:
                    raise ConductConflict("fanout dependency belongs to another graph")
                dependency_runs.append(dependency_id)
            run_id = self._run_id(packet)
            run = {
                "run_id": run_id,
                "root_run_id": parent["root_run_id"],
                "parent_run_id": packet.parent_run_id,
                "packet": _dump(packet),
                "conductor_session_id": packet.conductor.session_id,
                "conductor_principal_id": principal.principal_id,
                "executor_session_id": None,
                "lease_id": None,
                "status": "waiting",
                "children": [],
                "receipts": [],
                "attempts": [],
                "projection_receipts": [],
                "compatibility_projection": False,
                "dependency_run_ids": dependency_runs,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
            state["runs"][run_id] = run
            state["work_index"][packet.work_id] = run_id
            state["work_key_index"][packet.work_key] = run_id
            parent["children"].append(run_id)
            parent["updated_at"] = now.isoformat()
            _event(
                state,
                "fanout.run_waiting",
                run_id=run_id,
                root_run_id=parent["root_run_id"],
                dependencies=dependency_runs,
            )
            return {
                "schema_version": "limen.conduct_submit_result.v1",
                "status": "waiting",
                "duplicate": False,
                "work_id": packet.work_id,
                "run_id": run_id,
                "root_run_id": parent["root_run_id"],
                "executor_session_id": None,
                "lease": None,
            }

    def split(
        self,
        parent_run_id: str,
        packet: WorkPacketV1,
        *,
        principal: ConductPrincipalV1 | None = None,
        now: datetime | None = None,
        project_task_event: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if packet.parent_run_id != parent_run_id:
            raise ConductConflict("split packet parent_run_id must match the requested parent")
        return self.submit(
            packet,
            principal=principal,
            now=now,
            project_task_event=project_task_event,
        )

    def replay_work(self, work_id: str) -> dict[str, Any] | None:
        """Return an already-owned work result without recomputing its packet."""

        with self.store.transaction() as state:
            run_id = state["work_index"].get(work_id)
            if not run_id:
                return None
            run = state["runs"].get(run_id)
            if not run:
                raise ConductError(f"work index points to missing run: {work_id}")
            return self._submit_result(state, run, duplicate=True)

    def local_board_projection(self) -> dict[str, Any] | None:
        """Read the explicit local keeper's latest full canonical projection."""

        with self.store.transaction() as state:
            projection = state.get("local_board_projection")
            return copy.deepcopy(projection) if isinstance(projection, dict) else None

    def graph(self, root_run_id: str) -> dict[str, Any]:
        with self.store.transaction() as state:
            if root_run_id not in state["runs"]:
                raise ConductError(f"unknown run: {root_run_id}")
            root = state["runs"][root_run_id]
            canonical_root = root["root_run_id"]
            nodes = []
            for run in state["runs"].values():
                if run["root_run_id"] != canonical_root:
                    continue
                node = {key: value for key, value in run.items() if key != "packet"} | {"packet": run["packet"]}
                if run.get("lease_id") and run["lease_id"] in state["leases"]:
                    node["lease"] = self._public_lease(LeaseV1.model_validate(state["leases"][run["lease_id"]]))
                nodes.append(node)
            nodes.sort(key=lambda row: (row["created_at"], row["run_id"]))
            return {
                "schema_version": "limen.conduct_graph.v1",
                "root_run_id": canonical_root,
                "nodes": nodes,
            }

    def claim(
        self,
        lease_id: str,
        generation: int,
        *,
        principal: ConductPrincipalV1 | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Deliver a recoverable capability only to the selected executor principal."""

        now = now or utc_now()
        with self.store.transaction() as state:
            self._expire_leases(state, now)
            raw = state["leases"].get(lease_id)
            if not raw:
                raise ConductError(f"unknown lease: {lease_id}")
            lease = LeaseV1.model_validate(raw)
            resolved, enforced = self._principal_for_identity(lease.executor, principal)
            self._require_role(resolved, "executor", "compatibility")
            if generation != lease.generation:
                raise ConductConflict("lease generation does not match the claim")
            if enforced and lease.executor_principal_id != resolved.principal_id:
                raise ConductConflict("lease belongs to another executor principal")
            if lease.state not in {"reserved", "active"}:
                raise ConductConflict(f"lease is not active: {lease.state}")
            run = state["runs"].get(lease.run_id)
            if not run:
                raise ConductError(f"lease points to missing run: {lease.run_id}")
            _require_work_loan(WorkPacketV1.model_validate(run["packet"]))
            principal_id = lease.executor_principal_id or resolved.principal_id
            token = self._capability_token(lease.lease_id, lease.generation, principal_id)
            if not hmac.compare_digest(lease.capability_token_hash, self._token_hash(token)):
                raise ConductConflict("lease capability binding is invalid")
            _event(
                state,
                "lease.claimed",
                lease_id=lease_id,
                run_id=lease.run_id,
                generation=lease.generation,
                executor_principal_id=principal_id,
            )
            return {
                "schema_version": "limen.conduct_lease_claim.v1",
                "lease_id": lease_id,
                "run_id": lease.run_id,
                "generation": lease.generation,
                "capability_token": token,
            }

    def heartbeat(
        self,
        lease_id: str,
        capability_token: str,
        *,
        generation: int | None = None,
        principal: ConductPrincipalV1 | None = None,
        observed_heads: dict[str, str] | None = None,
        attempt: ExecutorAttemptV1 | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or utc_now()
        with self.store.transaction() as state:
            self._expire_leases(state, now)
            lease = self._authorized_lease(
                state,
                lease_id,
                capability_token,
                generation=generation,
                principal=principal,
            )
            if lease.state not in {"reserved", "active"}:
                raise ConductConflict(f"lease is not active: {lease.state}")
            for resource, expected in lease.observed_heads.items():
                actual = (observed_heads or {}).get(resource)
                if actual is None:
                    return self._fence(
                        state,
                        lease,
                        f"required observed head omitted for {resource}",
                        now,
                        observed_heads=observed_heads or {},
                    )
                if actual != expected:
                    return self._fence(
                        state,
                        lease,
                        f"observed head moved for {resource}",
                        now,
                        observed_heads=observed_heads or {},
                    )
            run = state["runs"][lease.run_id]
            packet = WorkPacketV1.model_validate(run["packet"])
            lease = lease.model_copy(
                update={
                    "heartbeat_at": now,
                    "hard_deadline": min(packet.deadline, now + self.lease_ttl),
                    "state": "active",
                }
            )
            state["leases"][lease_id] = _dump(lease)
            attempt_created = False
            if attempt is not None:
                attempt_created = self._record_attempt(run, lease, attempt)
                rerouted = self._reroute_after_attempt(
                    state,
                    run,
                    lease,
                    attempt,
                    now=now,
                )
                if rerouted is not None:
                    return {
                        "status": "rerouted",
                        "lease": self._public_lease(rerouted),
                        "attempt_created": attempt_created,
                    }
            run["status"] = "running"
            run["updated_at"] = now.isoformat()
            session_raw = state["sessions"].get(run["executor_session_id"])
            if session_raw:
                session = ConductorSessionV1.model_validate(session_raw)
                state["sessions"][session.session_id] = _dump(session.model_copy(update={"heartbeat_at": now}))
            _event(state, "lease.heartbeat", lease_id=lease_id, run_id=lease.run_id)
            return {
                "status": "active",
                "lease": self._public_lease(lease),
                "attempt_created": attempt_created,
            }

    @staticmethod
    def _record_attempt(run: dict[str, Any], lease: LeaseV1, attempt: ExecutorAttemptV1) -> bool:
        if (
            attempt.run_id != run["run_id"]
            or attempt.lease_id != lease.lease_id
            or attempt.lease_generation != lease.generation
            or attempt.executor != lease.executor
        ):
            raise ConductConflict("executor attempt does not belong to the lease/run")
        attempts = run.setdefault("attempts", [])
        prior = next((row for row in attempts if row.get("attempt_id") == attempt.attempt_id), None)
        encoded = _dump(attempt)
        if prior is None:
            packet = WorkPacketV1.model_validate(run["packet"])
            if len(attempts) >= packet.retry.max_attempts:
                raise ConductConflict("executor attempt limit exhausted")
            if len(attempts) >= packet.spend.limit:
                raise ConductConflict("executor spend limit exhausted")
            if any(row.get("status") not in {"failed", "blocked"} for row in attempts):
                raise ConductConflict("a prior executor attempt is still live")
            attempts.append(encoded)
            return True
        immutable = (
            "run_id",
            "lease_id",
            "lease_generation",
            "executor",
            "adapter",
            "submitted_at",
        )
        if any(prior.get(field) != encoded.get(field) for field in immutable):
            raise ConductConflict("executor attempt identity changed")
        for field in ("provider_run_id", "provider_run_url"):
            if prior.get(field) and encoded.get(field) != prior.get(field):
                raise ConductConflict("executor provider receipt identity changed")
        transitions = {
            "launching": {"launching", "submitted", "running", "succeeded", "failed", "blocked"},
            "submitted": {"submitted", "running", "succeeded", "failed", "blocked"},
            "running": {"running", "succeeded", "failed", "blocked"},
            # Landing is a separate receipt phase. A provider may report success
            # before exact-base, predicate, or PR validation fails.
            "succeeded": {"succeeded", "failed", "blocked"},
            "failed": {"failed"},
            "blocked": {"blocked"},
        }
        if encoded["status"] not in transitions.get(str(prior.get("status")), set()):
            raise ConductConflict("executor attempt status regressed")
        prior.update(encoded)
        return False

    def _reroute_after_attempt(
        self,
        state: dict[str, Any],
        run: dict[str, Any],
        lease: LeaseV1,
        attempt: ExecutorAttemptV1,
        *,
        now: datetime,
    ) -> LeaseV1 | None:
        if attempt.status not in {"failed", "blocked"}:
            return None
        packet = WorkPacketV1.model_validate(run["packet"])
        attempts = run.get("attempts", [])
        if len(attempts) >= packet.retry.max_attempts or len(attempts) >= packet.spend.limit:
            return None
        if packet.retry.transient_only and attempt.failure_class != "transient":
            return None
        try:
            executor = self._select_executor(
                state,
                packet,
                now,
                exclude_sessions=frozenset({run["executor_session_id"]}),
                ignore_required_session=True,
            )
        except ConductConflict:
            return None
        generation = int(state.get("next_generation", 0)) + 1
        state["next_generation"] = generation
        resource_generations: dict[str, int] = {}
        for claim in lease.resources:
            prior = int(state["resource_generations"].get(claim.key, 0))
            resource_generations[claim.key] = prior + 1
            state["resource_generations"][claim.key] = prior + 1
        lease_id = f"lease-{generation}-{run['run_id'].removeprefix('run-')[:16]}"
        executor_principal_id = state["session_principals"].get(executor.session_id)
        if not executor_principal_id:
            raise ConductConflict("reroute executor has no authenticated principal binding")
        token = self._capability_token(lease_id, generation, executor_principal_id)
        replacement = LeaseV1(
            lease_id=lease_id,
            run_id=run["run_id"],
            executor=executor.identity,
            executor_principal_id=executor_principal_id,
            resources=lease.resources,
            observed_heads=lease.observed_heads,
            generation=generation,
            resource_generations=resource_generations,
            capability_token_hash=self._token_hash(token),
            acquired_at=now,
            heartbeat_at=now,
            hard_deadline=min(packet.deadline, now + self.lease_ttl),
        )
        state["leases"][lease.lease_id] = _dump(lease.model_copy(update={"state": "released", "heartbeat_at": now}))
        state["leases"][lease_id] = _dump(replacement)
        prior_session = run["executor_session_id"]
        run["executor_session_id"] = executor.session_id
        run["lease_id"] = lease_id
        run["status"] = "reserved"
        run["updated_at"] = now.isoformat()
        _event(
            state,
            "run.rerouted",
            run_id=run["run_id"],
            prior_executor_session_id=prior_session,
            executor_session_id=executor.session_id,
            lease_id=lease_id,
            generation=generation,
        )
        return replacement

    def report(
        self,
        lease_id: str,
        capability_token: str,
        receipt: RunReceiptV1,
        *,
        generation: int | None = None,
        principal: ConductPrincipalV1 | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or utc_now()
        with self.store.transaction() as state:
            state.setdefault("receipt_index", {})
            self._expire_leases(state, now)
            lease = self._authorized_lease(
                state,
                lease_id,
                capability_token,
                generation=generation,
                principal=principal,
                allow_terminal=True,
            )
            if receipt.lease_id != lease_id or receipt.run_id != lease.run_id:
                raise ConductConflict("receipt does not belong to the lease/run")
            indexed = state["receipt_index"].get(receipt.receipt_id)
            if indexed:
                if indexed["lease_id"] != lease_id or indexed["run_id"] != receipt.run_id:
                    raise ConductConflict("receipt_id was reused for another lease/run")
                return dict(indexed["result"])
            run = state["runs"][lease.run_id]
            packet = WorkPacketV1.model_validate(run["packet"])
            changed_paths_authorized = _covered_paths(
                frozenset(receipt.changed_paths),
                packet.authority.path_prefixes,
            )
            read_only_authorized = packet.effect != "read" or (
                not receipt.changed_paths and receipt.observed_heads_after == receipt.observed_heads_before
            )
            spend_value = receipt.spend.get(packet.spend.unit, 0)
            spend_authorized = (
                isinstance(spend_value, (int, float))
                and not isinstance(spend_value, bool)
                and 0 <= spend_value <= packet.spend.limit
            )
            child_runs_authorized = set(receipt.child_runs) == set(run["children"])
            mutation_authorized = (
                lease.state in {"reserved", "active"}
                and receipt.lease_generation == lease.generation
                and receipt.executor == lease.executor
                and all(receipt.observed_heads_before.get(key) == value for key, value in lease.observed_heads.items())
                and changed_paths_authorized
                and read_only_authorized
                and spend_authorized
                and child_runs_authorized
                and receipt.predicate.command == packet.predicate
                and (receipt.outcome != "succeeded" or receipt.predicate.exit_code == 0)
            )
            stored_receipt = _dump(receipt) | {
                "mutation_authorized": mutation_authorized,
                "accepted_at": now.isoformat(),
            }
            run["receipts"].append(stored_receipt)
            run["updated_at"] = now.isoformat()
            if mutation_authorized:
                terminal = {
                    "succeeded": "succeeded",
                    "failed": "failed",
                    "blocked": "blocked",
                    "cancelled": "cancelled",
                    "partial": "failed",
                }[receipt.outcome]
                run["status"] = terminal
                released = lease.model_copy(update={"state": "released", "heartbeat_at": now})
                state["leases"][lease_id] = _dump(released)
                _event(
                    state, "run.reported", run_id=lease.run_id, outcome=receipt.outcome, receipt_id=receipt.receipt_id
                )
                self._advance_fanout_graph(state, run["root_run_id"], now=now)
            else:
                _event(
                    state,
                    "run.late_evidence",
                    run_id=lease.run_id,
                    receipt_id=receipt.receipt_id,
                    lease_state=lease.state,
                )
            result = {
                "schema_version": "limen.conduct_report_result.v1",
                "run_id": lease.run_id,
                "receipt_id": receipt.receipt_id,
                "mutation_authorized": mutation_authorized,
                "run_status": run["status"],
            }
            state["receipt_index"][receipt.receipt_id] = {
                "lease_id": lease_id,
                "run_id": receipt.run_id,
                "result": result,
            }
            return result

    def _advance_fanout_graph(self, state: dict[str, Any], root_run_id: str, *, now: datetime) -> None:
        """Promote dependency-ready leaves and settle the keeper-owned root."""

        progress = True
        while progress:
            progress = False
            waiting = [
                copy.deepcopy(run)
                for run in state["runs"].values()
                if run["root_run_id"] == root_run_id and run["status"] == "waiting"
            ]
            for waiting_run in waiting:
                dependency_states = [
                    state["runs"][run_id]["status"] for run_id in waiting_run.get("dependency_run_ids", [])
                ]
                if any(
                    status in {"failed", "blocked", "cancelled", "fenced", "expired"} for status in dependency_states
                ):
                    current = state["runs"][waiting_run["run_id"]]
                    current["status"] = "blocked"
                    current["updated_at"] = now.isoformat()
                    current["receipts"].append(
                        {
                            "schema_version": "limen.fanout_dependency_receipt.v1",
                            "receipt_id": f"dependency-{current['run_id']}",
                            "run_id": current["run_id"],
                            "outcome": "blocked",
                            "mutation_authorized": True,
                            "accepted_at": now.isoformat(),
                        }
                    )
                    _event(state, "fanout.run_dependency_blocked", run_id=current["run_id"])
                    progress = True
                    continue
                if not dependency_states or any(status != "succeeded" for status in dependency_states):
                    continue
                trial = copy.deepcopy(state)
                run_id = waiting_run["run_id"]
                packet = WorkPacketV1.model_validate(waiting_run["packet"])
                trial["runs"].pop(run_id)
                trial["work_index"].pop(packet.work_id, None)
                trial["work_key_index"].pop(packet.work_key, None)
                parent = trial["runs"][packet.parent_run_id]
                parent["children"] = [child for child in parent["children"] if child != run_id]
                session = ConductorSessionV1.model_validate(trial["sessions"][packet.conductor.session_id])
                principal = ConductPrincipalV1(
                    principal_id=waiting_run["conductor_principal_id"],
                    agent=session.identity.agent,
                    surface=session.identity.surface,
                    roles=frozenset({"conductor"}),
                )
                staged_store = MemoryStateStore(trial)
                staged = ConductBroker(
                    staged_store,
                    session_ttl=self.session_ttl,
                    adoption_after=self.adoption_after,
                    lease_ttl=self.lease_ttl,
                    capability_secret=self.capability_secret,
                )
                try:
                    promoted = staged.submit(packet, principal=principal, now=now)
                except ConductError:
                    continue
                if promoted["status"] == "busy":
                    continue
                committed = staged_store.snapshot()
                state.clear()
                state.update(committed)
                _event(state, "fanout.run_promoted", run_id=run_id)
                progress = True
        root = state["runs"].get(root_run_id)
        if not root or root["packet"].get("intent", {}).get("kind") != "fanout-root":
            return
        children = [state["runs"][child] for child in root["children"]]
        if not children or any(
            child["status"] in {"waiting", "reserved", "running", "stop_requested"} for child in children
        ):
            return
        outcome = "succeeded" if all(child["status"] == "succeeded" for child in children) else "blocked"
        root["status"] = outcome
        root["updated_at"] = now.isoformat()
        root["receipts"] = [
            {
                "schema_version": "limen.fanout_campaign_receipt.v1",
                "receipt_id": f"campaign-{root_run_id}",
                "run_id": root_run_id,
                "outcome": outcome,
                "child_runs": list(root["children"]),
                "mutation_authorized": True,
                "accepted_at": now.isoformat(),
            }
        ]
        _event(state, "fanout.campaign_settled", run_id=root_run_id, outcome=outcome)

    def harvest(self, root_run_id: str) -> dict[str, Any]:
        graph = self.graph(root_run_id)
        by_status: dict[str, int] = {}
        receipts = 0
        for node in graph["nodes"]:
            by_status[node["status"]] = by_status.get(node["status"], 0) + 1
            receipts += len(node["receipts"])
        return {
            "schema_version": "limen.conduct_harvest.v1",
            "root_run_id": graph["root_run_id"],
            "run_count": len(graph["nodes"]),
            "receipt_count": receipts,
            "by_status": dict(sorted(by_status.items())),
            "unharvested": [
                node["run_id"]
                for node in graph["nodes"]
                if node["status"] in {"waiting", "reserved", "running", "stop_requested"}
            ],
            "nodes": graph["nodes"],
        }

    def adopt(
        self,
        run_id: str,
        adopter_session_id: str,
        *,
        principal: ConductPrincipalV1 | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or utc_now()
        with self.store.transaction() as state:
            run = state["runs"].get(run_id)
            adopter_raw = state["sessions"].get(adopter_session_id)
            if not run or not adopter_raw:
                raise ConductError("run or adopter session not found")
            adopter = ConductorSessionV1.model_validate(adopter_raw)
            resolved, enforced = self._principal_for_session(adopter, principal)
            self._require_role(resolved, "conductor")
            bound = state.get("session_principals", {}).get(adopter_session_id)
            if bound != resolved.principal_id:
                raise ConductConflict("adopter session is not bound to the authenticated principal")
            if enforced and run.get("conductor_principal_id") != resolved.principal_id:
                raise ConductConflict("only the owning conductor principal may recover a run")
            old_raw = state["sessions"].get(run["conductor_session_id"])
            if old_raw:
                old = ConductorSessionV1.model_validate(old_raw)
                if old.human_protected:
                    raise ConductConflict("protected human session cannot be adopted")
                if now - old.heartbeat_at <= self.adoption_after:
                    raise ConductConflict("conductor absence has not been proven")
            if now - adopter.heartbeat_at > self.session_ttl or not adopter.accepting_work:
                raise ConductConflict("adopter is not a healthy accepting session")
            prior = run["conductor_session_id"]
            run["conductor_session_id"] = adopter_session_id
            run["conductor_principal_id"] = resolved.principal_id
            run["updated_at"] = now.isoformat()
            _event(state, "run.adopted", run_id=run_id, prior_session_id=prior, adopter_session_id=adopter_session_id)
            return {"status": "adopted", "run_id": run_id, "conductor_session_id": adopter_session_id}

    def cancel(
        self,
        run_id: str,
        requester_session_id: str,
        *,
        principal: ConductPrincipalV1 | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or utc_now()
        with self.store.transaction() as state:
            run = state["runs"].get(run_id)
            if not run:
                raise ConductError(f"unknown run: {run_id}")
            requester_raw = state["sessions"].get(requester_session_id)
            if not requester_raw:
                raise ConductConflict("requester session is not registered")
            requester_model = ConductorSessionV1.model_validate(requester_raw)
            resolved, enforced = self._principal_for_session(requester_model, principal)
            self._require_role(resolved, "conductor")
            if run["conductor_session_id"] != requester_session_id:
                raise ConductConflict("only the current conductor may cancel a reservation")
            if state.get("session_principals", {}).get(requester_session_id) != resolved.principal_id:
                raise ConductConflict("requester session is not bound to the authenticated principal")
            if enforced and run.get("conductor_principal_id") != resolved.principal_id:
                raise ConductConflict("only the owning conductor principal may cancel a reservation")
            if requester_model.human_protected:
                raise ConductConflict("protected human session cannot be cancelled through autonomous conduct")
            if run["status"] != "reserved":
                raise ConductConflict("only reserved, not-started work may be cancelled")
            lease = LeaseV1.model_validate(state["leases"][run["lease_id"]])
            state["leases"][lease.lease_id] = _dump(lease.model_copy(update={"state": "released"}))
            run["status"] = "cancelled"
            run["updated_at"] = now.isoformat()
            _event(state, "run.cancelled", run_id=run_id, requester_session_id=requester_session_id)
            return {"status": "cancelled", "run_id": run_id}

    def request_stop(
        self,
        run_id: str,
        requester_session_id: str,
        *,
        principal: ConductPrincipalV1 | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or utc_now()
        with self.store.transaction() as state:
            run = state["runs"].get(run_id)
            if not run:
                raise ConductError(f"unknown run: {run_id}")
            requester_raw = state["sessions"].get(requester_session_id)
            if not requester_raw:
                raise ConductConflict("requester session is not registered")
            requester_model = ConductorSessionV1.model_validate(requester_raw)
            resolved, enforced = self._principal_for_session(requester_model, principal)
            self._require_role(resolved, "conductor")
            if run["conductor_session_id"] != requester_session_id:
                raise ConductConflict("only the current conductor may request stop")
            if state.get("session_principals", {}).get(requester_session_id) != resolved.principal_id:
                raise ConductConflict("requester session is not bound to the authenticated principal")
            if enforced and run.get("conductor_principal_id") != resolved.principal_id:
                raise ConductConflict("only the owning conductor principal may request stop")
            if requester_model.human_protected:
                raise ConductConflict("protected human session cannot be signalled through autonomous conduct")
            if run["status"] not in {"running", "reserved"}:
                raise ConductConflict("terminal work cannot receive a stop request")
            run["status"] = "stop_requested"
            run["updated_at"] = now.isoformat()
            _event(state, "run.stop_requested", run_id=run_id, requester_session_id=requester_session_id)
            return {"status": "stop_requested", "run_id": run_id, "cooperative": True}

    def _validate_lineage(
        self,
        state: dict[str, Any],
        packet: WorkPacketV1,
        *,
        principal_id: str | None = None,
    ) -> dict[str, Any] | None:
        if packet.parent_run_id is None:
            return None
        parent = state["runs"].get(packet.parent_run_id)
        if not parent:
            raise ConductError(f"parent run not found: {packet.parent_run_id}")
        parent_packet = WorkPacketV1.model_validate(parent["packet"])
        if parent["status"] not in {"reserved", "running"}:
            raise ConductConflict("terminal or stopping work cannot create children")
        if packet.conductor.session_id not in {
            parent["conductor_session_id"],
            parent["executor_session_id"],
        }:
            raise ConductConflict("only the parent conductor or executor may submit a child")
        if principal_id is not None and (
            parent["conductor_session_id"] != packet.conductor.session_id
            or parent.get("conductor_principal_id") != principal_id
        ):
            raise ConductConflict("only the owning conductor principal may submit a child")
        if packet.initiator != parent_packet.initiator:
            raise ConductConflict("child initiator must preserve the root initiator identity")
        if not parent_packet.authority.may_delegate:
            raise ConductConflict("parent authority does not permit delegation")
        if packet.depth != parent_packet.depth + 1 or packet.depth > parent_packet.fanout.max_depth:
            raise ConductConflict("child depth exceeds the parent fanout envelope")
        if len(parent["children"]) >= parent_packet.fanout.max_children:
            raise ConductConflict("parent fanout limit is exhausted")
        if not authority_attenuates(packet.authority, parent_packet.authority):
            raise ConductConflict("child authority does not attenuate the parent")
        if packet.spend.limit > parent_packet.spend.limit or packet.spend.reserve > parent_packet.spend.reserve:
            raise ConductConflict("child spend does not attenuate the parent")
        child_reserved_spend = sum(
            WorkPacketV1.model_validate(state["runs"][child_id]["packet"]).spend.limit
            for child_id in parent["children"]
        )
        if child_reserved_spend + packet.spend.limit > (parent_packet.spend.limit - parent_packet.spend.reserve):
            raise ConductConflict("aggregate child spend exceeds the parent envelope")
        if packet.spend.unit != parent_packet.spend.unit:
            raise ConductConflict("child spend unit does not match the parent")
        if (
            packet.retry.max_attempts > parent_packet.retry.max_attempts
            or parent_packet.retry.transient_only
            and not packet.retry.transient_only
        ):
            raise ConductConflict("child retry policy does not attenuate the parent")
        if packet.deadline > parent_packet.deadline:
            raise ConductConflict("child deadline does not attenuate the parent")
        if (
            packet.fanout.max_children > parent_packet.fanout.max_children
            or packet.fanout.max_depth > parent_packet.fanout.max_depth
        ):
            raise ConductConflict("child fanout does not attenuate the parent")
        ancestry_keys: set[str] = set()
        cursor = parent
        while cursor:
            ancestor_packet = WorkPacketV1.model_validate(cursor["packet"])
            ancestry_keys.add(ancestor_packet.work_key)
            parent_id = cursor.get("parent_run_id")
            cursor = state["runs"].get(parent_id) if parent_id else None
        if packet.work_key in ancestry_keys:
            raise ConductConflict("repeated ancestry work_key/cycle rejected")
        return parent

    def _select_executor(
        self,
        state: dict[str, Any],
        packet: WorkPacketV1,
        now: datetime,
        *,
        exclude_sessions: frozenset[str] = frozenset(),
        ignore_required_session: bool = False,
    ) -> ConductorSessionV1:
        if _is_task_compatibility_packet(packet):
            identity = AgentIdentityV1(
                agent="tabularius",
                surface="keeper",
                session_id="tabularius-conduct-keeper",
                provider_identity="tabularius",
            )
            return ConductorSessionV1(
                session_id=identity.session_id,
                identity=identity,
                origin="relay",
                capabilities=frozenset({"board-write"}),
                transport="keeper",
                harvest_method="projection-receipt",
                concurrency=1024,
            )
        active_load = self._active_load(state, now)
        candidates: list[ConductorSessionV1] = []
        required_session_id = "" if ignore_required_session else str(packet.execution.get("executor_session_id") or "")
        for raw in state["sessions"].values():
            session = ConductorSessionV1.model_validate(raw)
            if session.session_id in exclude_sessions:
                continue
            if required_session_id and session.session_id != required_session_id:
                continue
            if not session.accepting_work or now - session.heartbeat_at > self.session_ttl:
                continue
            if session.quota_remaining == 0:
                continue
            if packet.required_capabilities - session.capabilities:
                continue
            if (
                packet.execution.get("local_heavy_allowed") is False
                and {"local-heavy", "local-worktree"} & session.capabilities
            ):
                continue
            if session.human_protected and session.session_id != packet.conductor.session_id:
                continue
            if active_load.get(session.session_id, 0) >= session.concurrency:
                continue
            candidates.append(session)
        if not candidates:
            suffix = f" for executor session {required_session_id}" if required_session_id else ""
            raise ConductConflict(f"no healthy native lane satisfies the packet capabilities and bounds{suffix}")
        candidates.sort(
            key=lambda session: (
                0 if packet.preferred_agent and session.identity.agent == packet.preferred_agent else 1,
                -session.receipt_quality,
                session.cost_per_run if session.cost_per_run is not None else float("inf"),
                active_load.get(session.session_id, 0) / session.concurrency,
                session.identity.agent,
                session.session_id,
            )
        )
        return candidates[0]

    def _effective_claims(self, packet: WorkPacketV1) -> tuple[ResourceClaimV1, ...]:
        claims: list[ResourceClaimV1] = []
        always_exclusive = {
            "task",
            "pr-write",
            "branch",
            "worktree",
            "repo-plumbing",
            "base-integrate",
            "agy-scratch",
            "external",
            "repo-write",
        }
        for claim in packet.resource_claims:
            resource = parse_resource(claim.key)
            mode = claim.mode
            if resource.kind in always_exclusive or (
                packet.effect in {"write", "external"} and resource.kind != "pr-review"
            ):
                mode = "exclusive"
            claims.append(ResourceClaimV1(key=claim.key, mode=mode))
            if resource.repo and not _covered_atoms(
                frozenset({resource.repo}),
                packet.authority.repositories,
            ):
                raise ConductConflict(f"resource repository {resource.repo} exceeds packet authority")
            if (
                resource.kind == "path"
                and resource.prefix
                and not _covered_paths(
                    frozenset({resource.prefix.lstrip("/")}),
                    packet.authority.path_prefixes,
                )
            ):
                raise ConductConflict("path resource exceeds packet path authority")
            if resource.kind == "external":
                effect = resource.identity[0]
                if packet.effect != "external" or not _covered_atoms(
                    frozenset({effect}),
                    packet.authority.external_effects,
                ):
                    raise ConductConflict("external resource requires matching external effect authority")
        code_write_scope_kinds = {
            "branch",
            "path",
            "base-integrate",
            "repo-write",
        }
        has_code_write_scope = any(parse_resource(claim.key).kind in code_write_scope_kinds for claim in claims)
        if packet.effect == "write" and not has_code_write_scope:
            repositories = sorted(packet.authority.repositories)
            if not repositories or "*" in repositories:
                claims.append(ResourceClaimV1(key="repo/*/*/write", mode="exclusive"))
            else:
                claims.extend(ResourceClaimV1(key=f"repo/{repo}/write", mode="exclusive") for repo in repositories)
        if packet.task_id:
            claims.append(ResourceClaimV1(key=f"task/{packet.task_id}", mode="exclusive"))
        if packet.effect == "external":
            claims.extend(
                ResourceClaimV1(key=f"external/{effect}", mode="exclusive")
                for effect in sorted(packet.authority.external_effects)
            )
        return sorted_claims(claims)

    def _active_load(self, state: dict[str, Any], now: datetime) -> dict[str, int]:
        load: dict[str, int] = {}
        for raw in state["leases"].values():
            lease = LeaseV1.model_validate(raw)
            if lease.state in {"reserved", "active"} and lease.hard_deadline > now:
                run = state["runs"].get(lease.run_id)
                if run:
                    session_id = run["executor_session_id"]
                    load[session_id] = load.get(session_id, 0) + 1
        return load

    def _expire_leases(self, state: dict[str, Any], now: datetime) -> None:
        roots_to_advance: set[str] = set()
        for lease_id, raw in list(state["leases"].items()):
            lease = LeaseV1.model_validate(raw)
            if lease.state in {"reserved", "active"} and lease.hard_deadline <= now:
                state["leases"][lease_id] = _dump(lease.model_copy(update={"state": "expired"}))
                run = state["runs"].get(lease.run_id)
                if run and run["status"] in {"reserved", "running", "stop_requested"}:
                    run["status"] = "expired"
                    run["updated_at"] = now.isoformat()
                    if run.get("packet", {}).get("intent", {}).get("kind") == "fanout-leaf":
                        run["receipts"] = [
                            {
                                "schema_version": "limen.fanout_expiry_receipt.v1",
                                "receipt_id": f"expiry-{run['run_id']}",
                                "run_id": run["run_id"],
                                "outcome": "blocked",
                                "expected_heads": dict(lease.observed_heads),
                                "observed_heads": {},
                                "reason": "executor lease expired without a timely authenticated heartbeat",
                                "mutation_authorized": True,
                                "accepted_at": now.isoformat(),
                            }
                        ]
                        roots_to_advance.add(run["root_run_id"])
                _event(state, "lease.expired", lease_id=lease_id, run_id=lease.run_id)
        for root_run_id in roots_to_advance:
            self._advance_fanout_graph(state, root_run_id, now=now)

    def _authorized_lease(
        self,
        state: dict[str, Any],
        lease_id: str,
        capability_token: str,
        *,
        generation: int | None = None,
        principal: ConductPrincipalV1 | None = None,
        allow_terminal: bool = False,
    ) -> LeaseV1:
        raw = state["leases"].get(lease_id)
        if not raw:
            raise ConductError(f"unknown lease: {lease_id}")
        lease = LeaseV1.model_validate(raw)
        resolved, enforced = self._principal_for_identity(lease.executor, principal)
        self._require_role(resolved, "executor", "compatibility")
        if generation is not None and generation != lease.generation:
            raise ConductConflict("lease generation does not match the request")
        if enforced and lease.executor_principal_id != resolved.principal_id:
            raise ConductConflict("lease belongs to another executor principal")
        if not hmac.compare_digest(lease.capability_token_hash, self._token_hash(capability_token)):
            raise ConductConflict("invalid lease capability token")
        if not allow_terminal and lease.state not in {"reserved", "active"}:
            raise ConductConflict(f"lease is not active: {lease.state}")
        return lease

    def _fence(
        self,
        state: dict[str, Any],
        lease: LeaseV1,
        reason: str,
        now: datetime,
        *,
        observed_heads: dict[str, str],
    ) -> dict[str, Any]:
        state["leases"][lease.lease_id] = _dump(lease.model_copy(update={"state": "fenced", "heartbeat_at": now}))
        run = state["runs"][lease.run_id]
        run["status"] = "fenced"
        run["updated_at"] = now.isoformat()
        if run.get("packet", {}).get("intent", {}).get("kind") == "fanout-leaf":
            run["receipts"] = [
                {
                    "schema_version": "limen.fanout_fence_receipt.v1",
                    "receipt_id": f"fence-{run['run_id']}",
                    "run_id": run["run_id"],
                    "outcome": "blocked",
                    "expected_heads": dict(lease.observed_heads),
                    "observed_heads": dict(observed_heads),
                    "reason": reason,
                    "mutation_authorized": True,
                    "accepted_at": now.isoformat(),
                }
            ]
        _event(state, "lease.fenced", lease_id=lease.lease_id, run_id=lease.run_id, reason=reason)
        self._advance_fanout_graph(state, run["root_run_id"], now=now)
        return {"status": "fenced", "lease_id": lease.lease_id, "run_id": lease.run_id, "reason": reason}

    def _submit_result(self, state: dict[str, Any], run: dict[str, Any], *, duplicate: bool = False) -> dict[str, Any]:
        lease = LeaseV1.model_validate(state["leases"][run["lease_id"]])
        result = {
            "schema_version": "limen.conduct_submit_result.v1",
            "status": "duplicate" if duplicate else ("applied" if run.get("compatibility_projection") else "reserved"),
            "run_id": run["run_id"],
            "root_run_id": run["root_run_id"],
            "executor_session_id": run["executor_session_id"],
            "lease": self._public_lease(lease),
        }
        if run.get("projection_receipts"):
            result["projection_receipts"] = list(run["projection_receipts"])
        projection = state.get("local_board_projection")
        if isinstance(projection, dict):
            result["board_projection"] = copy.deepcopy(projection)
        return result

    @staticmethod
    def _run_id(packet: WorkPacketV1) -> str:
        digest = canonical_hash(
            {
                "work_id": packet.work_id,
                "intent_hash": packet.intent_hash,
                "execution_hash": packet.execution_hash,
            }
        )
        return f"run-{digest[:32]}"

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _capability_token(self, lease_id: str, generation: int, principal_id: str) -> str:
        binding = f"limen.lease-capability.v1\0{lease_id}\0{generation}\0{principal_id}".encode()
        digest = hmac.new(self.capability_secret, binding, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    @staticmethod
    def _public_lease(lease: LeaseV1) -> dict[str, Any]:
        return {
            key: value
            for key, value in _dump(lease).items()
            if key not in {"capability_token_hash", "executor_principal_id"}
        }

    @staticmethod
    def _require_role(principal: ConductPrincipalV1, *roles: str) -> None:
        if principal.roles.isdisjoint(roles):
            raise ConductConflict(f"authenticated principal lacks required {'/'.join(roles)} role")

    @staticmethod
    def _local_principal(identity: AgentIdentityV1) -> ConductPrincipalV1:
        return ConductPrincipalV1(
            principal_id=f"local:{identity.agent}:{identity.surface}",
            agent=identity.agent,
            surface=identity.surface,
            roles=frozenset({"observer", "conductor", "executor", "compatibility"}),
        )

    def _principal_for_identity(
        self,
        identity: AgentIdentityV1,
        principal: ConductPrincipalV1 | None,
    ) -> tuple[ConductPrincipalV1, bool]:
        return (principal, True) if principal else (self._local_principal(identity), False)

    def _principal_for_session(
        self,
        session: ConductorSessionV1,
        principal: ConductPrincipalV1 | None,
    ) -> tuple[ConductPrincipalV1, bool]:
        return self._principal_for_identity(session.identity, principal)

    @staticmethod
    def _bind_session_identity(
        session: ConductorSessionV1,
        principal: ConductPrincipalV1,
    ) -> ConductorSessionV1:
        identity = session.identity.model_copy(
            update={
                "agent": principal.agent,
                "surface": principal.surface,
                "session_id": session.session_id,
            }
        )
        return session.model_copy(update={"identity": identity})

    @staticmethod
    def _bind_conductor_identity(
        identity: AgentIdentityV1,
        principal: ConductPrincipalV1,
    ) -> AgentIdentityV1:
        # register() stores token-bound agent/surface; comparisons against the
        # stored session must apply the same binding or a client that declares
        # its own surface can never match (the #1408 relay freeze).
        return identity.model_copy(update={"agent": principal.agent, "surface": principal.surface})
