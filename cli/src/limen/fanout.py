"""Board-independent, receipt-backed fanout over the conduct keeper."""

from __future__ import annotations

import importlib.metadata
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol

import yaml
from pydantic import Field, field_validator, model_validator

from limen.conduct.client import HttpConductClient, LocalConductClient, client_from_env
from limen.conduct.models import (
    AgentIdentityV1,
    AuthorityEnvelopeV1,
    FanoutBoundsV1,
    ProtocolModel,
    ResourceClaimV1,
    RetryPolicyV1,
    SpendEnvelopeV1,
    WorkPacketV1,
    canonical_hash,
)
from limen.conduct.resources import parse_resource


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40,64}$")
_FORBIDDEN_KEYS = {
    "prompt",
    "prompt_text",
    "raw_prompt",
    "plan",
    "plan_text",
    "raw_plan",
    "model",
    "model_id",
    "provider",
    "provider_id",
    "tier",
}
_CODE_RECEIPT_CAPABILITIES = frozenset(
    {
        "exact-base-receipt",
        "exact-diff-receipt",
        "exact-head-receipt",
        "predicate-receipt",
        "pull-request-receipt",
    }
)
_READ_RECEIPT_CAPABILITIES = frozenset(
    {
        "exact-base-receipt",
        "exact-head-receipt",
        "predicate-receipt",
        "read-verifier",
    }
)


def _bounded_text(value: str, field_name: str) -> str:
    value = value.strip()
    if not value or "\x00" in value or len(value) > 8192:
        raise ValueError(f"{field_name} must be a non-empty bounded string")
    return value


def _hash(value: str, field_name: str) -> str:
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def _path(value: str) -> str:
    if not value or value.startswith("/") or "\x00" in value:
        raise ValueError("allowed paths must be non-empty repository-relative paths")
    normalized = str(PurePosixPath(value))
    if normalized == ".." or normalized.startswith("../"):
        raise ValueError("allowed paths may not escape the repository")
    return normalized.rstrip("/") or "."


class FanoutLeafV1(ProtocolModel):
    """One independently receiptable leaf with no provider/model coupling."""

    schema_version: Literal["limen.fanout_leaf.v1"] = "limen.fanout_leaf.v1"
    work_id: str
    idempotency_key: str
    owner_repository: str
    exact_base: str
    topic_branch: str
    allowed_paths: tuple[str, ...]
    resource_claims: tuple[ResourceClaimV1, ...]
    dependencies: tuple[str, ...] = ()
    required_capabilities: frozenset[str] = Field(default_factory=frozenset)
    intended_effect: str
    effect: Literal["read", "write"] = "write"
    predicate: str
    receipt_target: str
    deadline: datetime
    retry: RetryPolicyV1 = Field(default_factory=RetryPolicyV1)
    spend: SpendEnvelopeV1 = Field(default_factory=SpendEnvelopeV1)
    prompt_hash: str
    plan_hash: str

    @field_validator(
        "work_id",
        "idempotency_key",
        "owner_repository",
        "topic_branch",
        "intended_effect",
        "predicate",
        "receipt_target",
    )
    @classmethod
    def validate_text(cls, value: str, info) -> str:
        return _bounded_text(value, info.field_name)

    @field_validator("exact_base")
    @classmethod
    def validate_base(cls, value: str) -> str:
        if not _GIT_SHA_RE.fullmatch(value):
            raise ValueError("exact_base must be a lowercase 40-64 character Git object id")
        return value

    @field_validator("prompt_hash", "plan_hash")
    @classmethod
    def validate_hash(cls, value: str, info) -> str:
        return _hash(value, info.field_name)

    @field_validator("allowed_paths")
    @classmethod
    def validate_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        paths = tuple(sorted({_path(item) for item in value}))
        if not paths:
            raise ValueError("every fanout leaf needs at least one allowed path")
        return paths

    @field_validator("dependencies")
    @classmethod
    def validate_dependencies(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(value))

    @field_validator("required_capabilities")
    @classmethod
    def validate_provider_neutral_capabilities(cls, value: frozenset[str]) -> frozenset[str]:
        forbidden = {"model:", "provider:", "tier:"}
        if any(capability.casefold().startswith(tuple(forbidden)) for capability in value):
            raise ValueError("required capabilities may not name a provider, model, or tier")
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> "FanoutLeafV1":
        if self.work_id in self.dependencies:
            raise ValueError("a leaf cannot depend on itself")
        if self.deadline <= datetime.now(timezone.utc):
            raise ValueError("leaf deadline must be in the future")
        if self.effect == "write" and not self.topic_branch:
            raise ValueError("write leaves require a topic branch")
        claimed_repositories = {
            resource.repo for resource in (parse_resource(claim.key) for claim in self.resource_claims) if resource.repo
        }
        if claimed_repositories - {self.owner_repository}:
            raise ValueError("resource claims may not exceed the owner repository")
        if self.effect == "write" and self.owner_repository not in claimed_repositories:
            raise ValueError("write leaves require a repository-bound resource claim")
        if self.spend.unit != "runs":
            raise ValueError("fanout execution spend must use the runs unit")
        if self.spend.limit < self.retry.max_attempts:
            raise ValueError("fanout spend limit must cover every permitted attempt")
        return self


class FanoutManifestV1(ProtocolModel):
    """Canonical direct-session graph; it never contains task-board state."""

    schema_version: Literal["limen.fanout_manifest.v1"] = "limen.fanout_manifest.v1"
    root_work_id: str
    idempotency_key: str
    initiator: AgentIdentityV1
    conductor: AgentIdentityV1
    predicate: str
    receipt_target: str
    deadline: datetime
    leaves: tuple[FanoutLeafV1, ...]

    @field_validator("root_work_id", "idempotency_key", "predicate", "receipt_target")
    @classmethod
    def validate_text(cls, value: str, info) -> str:
        return _bounded_text(value, info.field_name)

    @model_validator(mode="before")
    @classmethod
    def reject_private_or_static_routing(cls, value: Any) -> Any:
        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for key, child in node.items():
                    if str(key).lower() in _FORBIDDEN_KEYS:
                        raise ValueError(f"fanout manifests may not contain {key}")
                    walk(child)
            elif isinstance(node, (list, tuple)):
                for child in node:
                    walk(child)

        walk(value)
        return value

    @model_validator(mode="after")
    def validate_graph(self) -> "FanoutManifestV1":
        if self.deadline <= datetime.now(timezone.utc):
            raise ValueError("manifest deadline must be in the future")
        if not self.leaves:
            raise ValueError("fanout manifest needs at least one leaf")
        ids = [leaf.work_id for leaf in self.leaves]
        keys = [leaf.idempotency_key for leaf in self.leaves]
        if len(ids) != len(set(ids)):
            raise ValueError("fanout leaf work IDs must be unique")
        if len(keys) != len(set(keys)):
            raise ValueError("fanout leaf idempotency keys must be unique")
        known = set(ids)
        for leaf in self.leaves:
            missing = set(leaf.dependencies) - known
            if missing:
                raise ValueError(f"{leaf.work_id} has unknown dependencies: {sorted(missing)}")
            if leaf.deadline > self.deadline:
                raise ValueError(f"{leaf.work_id} exceeds the manifest deadline")
        _topological_order(self.leaves)
        return self

    @property
    def manifest_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


class FanoutError(RuntimeError):
    """A fail-closed manifest, route, or receipt error."""


def load_manifest(path: Path) -> FanoutManifestV1:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise FanoutError(f"cannot read fanout manifest {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise FanoutError("fanout manifest must contain one object")
    try:
        return FanoutManifestV1.model_validate(raw)
    except ValueError as exc:
        raise FanoutError(str(exc)) from exc


def _claims_overlap(left: FanoutLeafV1, right: FanoutLeafV1) -> bool:
    for a in left.resource_claims:
        for b in right.resource_claims:
            if a.mode == b.mode == "shared":
                continue
            if a.key == b.key or a.key.startswith(f"{b.key}/") or b.key.startswith(f"{a.key}/"):
                return True
    return False


def serialize_resource_conflicts(manifest: FanoutManifestV1) -> FanoutManifestV1:
    """Make overlap ordering explicit and deterministic without provider knowledge."""

    ordered = sorted(manifest.leaves, key=lambda leaf: (leaf.work_id, leaf.idempotency_key))
    rewritten: list[FanoutLeafV1] = []
    for index, leaf in enumerate(ordered):
        dependencies = list(leaf.dependencies)
        for prior in ordered[:index]:
            if _claims_overlap(prior, leaf) and prior.work_id not in dependencies:
                dependencies.append(prior.work_id)
        rewritten.append(leaf.model_copy(update={"dependencies": tuple(sorted(dependencies))}))
    result = manifest.model_copy(update={"leaves": tuple(rewritten)})
    _topological_order(result.leaves)
    return result


def unresolved_resource_conflicts(manifest: FanoutManifestV1) -> list[tuple[str, str]]:
    by_id = {leaf.work_id: leaf for leaf in manifest.leaves}
    ancestors: dict[str, set[str]] = {}

    def visit(work_id: str) -> set[str]:
        if work_id not in ancestors:
            direct = set(by_id[work_id].dependencies)
            ancestors[work_id] = direct | set().union(*(visit(dep) for dep in direct))
        return ancestors[work_id]

    conflicts: list[tuple[str, str]] = []
    for index, left in enumerate(manifest.leaves):
        for right in manifest.leaves[index + 1 :]:
            if not _claims_overlap(left, right):
                continue
            if left.work_id not in visit(right.work_id) and right.work_id not in visit(left.work_id):
                conflicts.append((left.work_id, right.work_id))
    return conflicts


def _topological_order(leaves: tuple[FanoutLeafV1, ...]) -> tuple[str, ...]:
    dependencies = {leaf.work_id: set(leaf.dependencies) for leaf in leaves}
    output: list[str] = []
    while dependencies:
        ready = sorted(work_id for work_id, deps in dependencies.items() if not deps)
        if not ready:
            raise ValueError("fanout dependencies contain a cycle")
        output.extend(ready)
        for work_id in ready:
            dependencies.pop(work_id)
        for deps in dependencies.values():
            deps.difference_update(ready)
    return tuple(output)


def _is_local(session: dict[str, Any]) -> bool:
    transport = str(session.get("transport", "")).lower()
    capabilities = set(session.get("capabilities") or ())
    return transport.startswith("local") or "local-heavy" in capabilities or "local-worktree" in capabilities


def _repository_capability(repository: str) -> str:
    return f"repository:{canonical_hash(repository)[:32]}"


def _metric(value: Any, default: float) -> float:
    if value is None or isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed


def route_manifest(
    manifest: FanoutManifestV1,
    capabilities: dict[str, Any],
    *,
    remote_first: bool = True,
    local_max: int = 1,
    strict: bool = True,
) -> dict[str, Any]:
    """Route from live session facts only; names and providers are never policy."""

    if local_max < 0 or local_max > 1:
        raise FanoutError("local_max must be zero or one")
    sessions = [
        row
        for row in capabilities.get("sessions", [])
        if isinstance(row, dict)
        and row.get("healthy")
        and row.get("accepting_work", True)
        and row.get("quota_available", True) is not False
        and _metric(row.get("quota_remaining"), 1) != 0
        and int(row.get("active_leases", 0)) < int(row.get("concurrency", 1))
    ]
    local_used = 0
    provisional_load = {str(row.get("session_id", "")): int(row.get("active_leases", 0)) for row in sessions}
    routes: list[dict[str, Any]] = []
    for leaf in manifest.leaves:
        dependency_deferred = bool(leaf.dependencies)
        required = set(leaf.required_capabilities)
        if leaf.effect == "write":
            required.update(_CODE_RECEIPT_CAPABILITIES)
        else:
            required.update(_READ_RECEIPT_CAPABILITIES)
        repository_capability = _repository_capability(leaf.owner_repository)
        candidates = []
        for row in sessions:
            advertised = set(row.get("capabilities") or ())
            repository_scopes = {value for value in advertised if str(value).startswith("repository:")}
            if required <= advertised and (not repository_scopes or repository_capability in repository_scopes):
                candidates.append(row)
        candidates.sort(
            key=lambda row: (
                _is_local(row) if remote_first else False,
                -_metric(row.get("receipt_quality"), 0),
                _metric(row.get("cost_per_run"), float("inf")),
                int(row.get("active_leases", 0)) / max(1, int(row.get("concurrency", 1))),
                str(row.get("session_id", "")),
            )
        )
        selected = None
        for row in candidates:
            session_id = str(row.get("session_id", ""))
            if not dependency_deferred and provisional_load.get(session_id, 0) >= int(row.get("concurrency", 1)):
                continue
            if _is_local(row):
                if not dependency_deferred and local_used >= local_max:
                    continue
                if not dependency_deferred:
                    local_used += 1
            selected = row
            break
        if selected is None:
            detail = (
                f"no live executor satisfies {leaf.work_id}: {sorted(required)} "
                f"(remote preferred, local fallback limit {local_max})"
            )
            if strict:
                raise FanoutError(detail)
            routes.append(
                {
                    "work_id": leaf.work_id,
                    "status": "blocked",
                    "detail": detail,
                    "required_capabilities": sorted(required),
                }
            )
            continue
        if not dependency_deferred:
            provisional_load[str(selected["session_id"])] = provisional_load.get(str(selected["session_id"]), 0) + 1
        identity = selected.get("identity") or {}
        routes.append(
            {
                "work_id": leaf.work_id,
                "status": "eligible",
                "session_id": selected["session_id"],
                "agent": identity.get("agent"),
                "transport": selected.get("transport"),
                "local_heavy": _is_local(selected),
                "repository_capability": repository_capability,
                "required_capabilities": sorted(required),
            }
        )
    return {
        "schema_version": "limen.fanout_route.v1",
        "manifest_hash": manifest.manifest_hash,
        "remote_first": remote_first,
        "local_max": local_max,
        "routes": routes,
    }


def plan_manifest(
    manifest: FanoutManifestV1,
    *,
    capabilities: dict[str, Any] | None = None,
    remote_first: bool = True,
    local_max: int = 1,
) -> dict[str, Any]:
    canonical = serialize_resource_conflicts(manifest)
    conflicts = unresolved_resource_conflicts(canonical)
    if conflicts:
        raise FanoutError(f"unresolved resource conflicts: {conflicts}")
    payload: dict[str, Any] = {
        "schema_version": "limen.fanout_plan.v1",
        "manifest_hash": canonical.manifest_hash,
        "root_work_id": canonical.root_work_id,
        "launch": False,
        "topological_order": list(_topological_order(canonical.leaves)),
        "leaves": [
            {
                "work_id": leaf.work_id,
                "dependencies": list(leaf.dependencies),
                "resource_claims": [claim.model_dump(mode="json") for claim in leaf.resource_claims],
            }
            for leaf in canonical.leaves
        ],
    }
    if capabilities is not None:
        payload["routing"] = route_manifest(
            canonical,
            capabilities,
            remote_first=remote_first,
            local_max=local_max,
            strict=False,
        )
    else:
        payload["routing"] = {
            "schema_version": "limen.fanout_route.v1",
            "status": "not-probed",
            "remote_first": remote_first,
            "local_max": local_max,
            "requirements": [
                {
                    "work_id": leaf.work_id,
                    "required_capabilities": sorted(
                        set(leaf.required_capabilities)
                        | (_CODE_RECEIPT_CAPABILITIES if leaf.effect == "write" else _READ_RECEIPT_CAPABILITIES)
                    ),
                }
                for leaf in canonical.leaves
            ],
        }
    return payload


def _run_id(packet: WorkPacketV1) -> str:
    return (
        "run-"
        + canonical_hash(
            {
                "work_id": packet.work_id,
                "intent_hash": packet.intent_hash,
                "execution_hash": packet.execution_hash,
            }
        )[:32]
    )


def compile_packets(
    manifest: FanoutManifestV1,
    routing: dict[str, Any],
) -> tuple[WorkPacketV1, ...]:
    canonical = serialize_resource_conflicts(manifest)
    route_by_work = {row["work_id"]: row for row in routing["routes"]}
    repositories = frozenset(leaf.owner_repository for leaf in canonical.leaves)
    all_paths = frozenset(path for leaf in canonical.leaves for path in leaf.allowed_paths)
    spend_unit = canonical.leaves[0].spend.unit
    if any(leaf.spend.unit != spend_unit for leaf in canonical.leaves):
        raise FanoutError("all leaves in one graph must use the same spend unit")
    root = WorkPacketV1(
        work_id=canonical.root_work_id,
        work_key=canonical.idempotency_key,
        intent={
            "kind": "fanout-root",
            "manifest_hash": canonical.manifest_hash,
            "leaf_count": len(canonical.leaves),
        },
        execution={"adapter": "fanout-keeper", "manifest_hash": canonical.manifest_hash},
        initiator=canonical.initiator,
        conductor=canonical.conductor,
        preferred_agent=canonical.conductor.agent,
        required_capabilities=frozenset({"conduct"}),
        predicate=canonical.predicate,
        receipt_target=canonical.receipt_target,
        authority=AuthorityEnvelopeV1(
            actions=frozenset({"read", "write"}),
            repositories=repositories,
            path_prefixes=all_paths,
        ),
        deadline=canonical.deadline,
        spend=SpendEnvelopeV1(
            unit=spend_unit,
            limit=sum(leaf.spend.limit for leaf in canonical.leaves),
        ),
        retry=RetryPolicyV1(
            max_attempts=max(leaf.retry.max_attempts for leaf in canonical.leaves),
            transient_only=all(leaf.retry.transient_only for leaf in canonical.leaves),
        ),
        effect="read",
        fanout=FanoutBoundsV1(max_children=len(canonical.leaves), max_depth=1),
    )
    root_run_id = _run_id(root)
    packets = [root]
    for leaf in canonical.leaves:
        route = route_by_work[leaf.work_id]
        required = set(leaf.required_capabilities)
        required.add(f"campaign:{canonical.manifest_hash}")
        if leaf.effect == "write":
            required.update(_CODE_RECEIPT_CAPABILITIES)
        else:
            required.update(_READ_RECEIPT_CAPABILITIES)
        packets.append(
            WorkPacketV1(
                root_run_id=root_run_id,
                parent_run_id=root_run_id,
                work_id=leaf.work_id,
                work_key=leaf.idempotency_key,
                intent={
                    "kind": "fanout-leaf",
                    "intended_effect": leaf.intended_effect,
                    "prompt_hash": leaf.prompt_hash,
                    "plan_hash": leaf.plan_hash,
                },
                execution={
                    "adapter": "fanout",
                    "owner_repository": leaf.owner_repository,
                    "exact_base": leaf.exact_base,
                    "topic_branch": leaf.topic_branch,
                    "dependencies": list(leaf.dependencies),
                    "local_heavy_allowed": route["local_heavy"],
                    # Dependency leaves are routed again by the keeper when promoted.
                    "executor_session_id": route["session_id"] if not leaf.dependencies else None,
                    "manifest_hash": canonical.manifest_hash,
                    "observed_heads": {leaf.owner_repository: leaf.exact_base},
                },
                initiator=canonical.initiator,
                conductor=canonical.conductor,
                preferred_agent=route["agent"],
                required_capabilities=frozenset(required),
                resource_claims=leaf.resource_claims,
                predicate=leaf.predicate,
                receipt_target=leaf.receipt_target,
                authority=AuthorityEnvelopeV1(
                    actions=frozenset({"read", "write"} if leaf.effect == "write" else {"read"}),
                    repositories=frozenset({leaf.owner_repository}),
                    path_prefixes=frozenset(leaf.allowed_paths),
                    may_delegate=False,
                ),
                deadline=leaf.deadline,
                spend=leaf.spend,
                retry=leaf.retry,
                depth=1,
                effect=leaf.effect,
            )
        )
    return tuple(packets)


def start_manifest(
    manifest: FanoutManifestV1,
    *,
    client: Any | None = None,
    remote_first: bool = True,
    local_max: int = 1,
    allow_development_keeper: bool = False,
    execution_adapters: tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    from limen.fanout_executor import (
        discover_execution_adapters,
        launch_ready_nodes,
        register_execution_sessions,
        wake_executor_workers,
    )

    keeper = client or client_from_env()
    if isinstance(keeper, LocalConductClient) and not allow_development_keeper:
        raise FanoutError("production fanout start requires the authenticated remote keeper")
    canonical = serialize_resource_conflicts(manifest)
    repositories = frozenset(leaf.owner_repository for leaf in canonical.leaves)
    executors = execution_adapters if execution_adapters is not None else discover_execution_adapters(repositories)
    if not executors:
        raise FanoutError("no live execution adapter can launch this manifest")
    adapter_sessions = register_execution_sessions(canonical, keeper, executors)
    capabilities = keeper.capabilities()
    routing = route_manifest(canonical, capabilities, remote_first=remote_first, local_max=local_max)
    result = keeper.submit_graph(compile_packets(canonical, routing))
    if result.get("status") not in {"reserved", "duplicate"}:
        raise FanoutError(f"atomic graph was not reserved: {result}")
    if isinstance(keeper, HttpConductClient):
        attempts: list[dict[str, Any]] = []
        wakes = wake_executor_workers(result["root_run_id"], adapter_sessions)
    else:
        attempts = launch_ready_nodes(
            result["root_run_id"],
            client=keeper,
            adapters_by_session=adapter_sessions,
        )
        wakes = []
    return {
        "schema_version": "limen.fanout_start.v1",
        "root_run_id": result["root_run_id"],
        "manifest_hash": canonical.manifest_hash,
        "idempotent": any(run.get("duplicate") or run.get("status") == "duplicate" for run in result.get("runs", [])),
        "routing": routing,
        "attempts": attempts,
        "executor_wakes": wakes,
    }


def status_root(
    root_run_id: str,
    *,
    client: Any | None = None,
    execution_adapters: tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    from limen.fanout_executor import (
        discover_execution_adapters,
        resume_execution_sessions,
        wake_executor_workers,
    )

    keeper = client or client_from_env()
    graph = keeper.graph(root_run_id)
    repositories = frozenset(
        str(node.get("packet", {}).get("execution", {}).get("owner_repository"))
        for node in graph.get("nodes", [])
        if node.get("packet", {}).get("intent", {}).get("kind") == "fanout-leaf"
    )
    executors = execution_adapters if execution_adapters is not None else discover_execution_adapters(repositories)
    lanes = resume_execution_sessions(graph, keeper, executors) if executors else {}
    wakes = wake_executor_workers(root_run_id, lanes)
    return {
        "schema_version": "limen.fanout_status.v1",
        "root_run_id": graph["root_run_id"],
        "nodes": graph["nodes"],
        "executor_wakes": wakes,
    }


class LandingAdapter(Protocol):
    name: str

    def can_land(self, node: dict[str, Any], receipt: dict[str, Any]) -> bool: ...

    def land(self, node: dict[str, Any], receipt: dict[str, Any], *, merge: bool) -> dict[str, Any]: ...


class PullRequestReceiptAdapter:
    """Land an already-created exact-head PR receipt without touching the shared checkout."""

    name = "pull-request-receipt"

    def can_land(self, node: dict[str, Any], receipt: dict[str, Any]) -> bool:
        return any(check.get("name") == "pull-request" and check.get("url") for check in receipt.get("checks", []))

    def land(self, node: dict[str, Any], receipt: dict[str, Any], *, merge: bool) -> dict[str, Any]:
        check = next(item for item in receipt["checks"] if item.get("name") == "pull-request")
        result = {"adapter": self.name, "pr": check["url"], "merged": False}
        if not merge:
            return result
        match = re.search(r"github\.com/([^/]+/[^/]+)/pull/(\d+)", str(check["url"]))
        if not match:
            raise FanoutError("pull-request receipt URL is not a canonical GitHub PR")
        root = Path(__file__).resolve().parents[3]
        completed = subprocess.run(
            [
                str(root / "scripts" / "await-pr.sh"),
                match.group(2),
                "--repo",
                match.group(1),
                "--merge",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise FanoutError(
                f"merge queue rejected {check['url']}: {(completed.stdout + completed.stderr).strip()[-1000:]}"
            )
        result["merged"] = True
        return result


def landing_adapters() -> tuple[LandingAdapter, ...]:
    adapters: list[LandingAdapter] = [PullRequestReceiptAdapter()]
    try:
        entries = importlib.metadata.entry_points(group="limen.fanout_landing")
    except TypeError:  # pragma: no cover - Python compatibility
        entries = importlib.metadata.entry_points().select(group="limen.fanout_landing")
    for entry in entries:
        adapter = entry.load()()
        adapters.append(adapter)
    return tuple(adapters)


def _validate_code_receipt(node: dict[str, Any], receipt: dict[str, Any]) -> None:
    packet = node["packet"]
    execution = packet["execution"]
    repository = execution["owner_repository"]
    exact_base = execution["exact_base"]
    before = receipt.get("observed_heads_before", {}).get(repository)
    after = receipt.get("observed_heads_after", {}).get(repository)
    if not receipt.get("mutation_authorized"):
        raise FanoutError(f"{node['run_id']} receipt was not mutation-authorized by the keeper")
    if receipt.get("outcome") != "succeeded" or receipt.get("predicate", {}).get("exit_code") != 0:
        raise FanoutError(f"{node['run_id']} has no successful predicate receipt")
    if before != exact_base:
        raise FanoutError(f"{node['run_id']} exact base receipt does not match {exact_base}")
    if not isinstance(after, str) or not _GIT_SHA_RE.fullmatch(after) or after == before:
        raise FanoutError(f"{node['run_id']} has no distinct exact head receipt")
    if not receipt.get("provider_run_url"):
        raise FanoutError(f"{node['run_id']} has no provider run receipt")
    checks = {item.get("name"): item for item in receipt.get("checks", [])}
    for name in ("exact-diff", "pull-request"):
        check = checks.get(name)
        if not check or check.get("status") != "success" or not check.get("url"):
            raise FanoutError(f"{node['run_id']} has no successful {name} receipt")
    if not _SHA256_RE.fullmatch(str(checks["exact-diff"].get("head") or "")):
        raise FanoutError(f"{node['run_id']} exact diff receipt has no SHA-256")
    if checks["pull-request"].get("head") != after:
        raise FanoutError(f"{node['run_id']} PR head does not match the exact head receipt")
    allowed = tuple(packet["authority"]["path_prefixes"])
    for changed in receipt.get("changed_paths", []):
        if not any(
            prefix == "." or changed == prefix or changed.startswith(prefix.rstrip("/") + "/") for prefix in allowed
        ):
            raise FanoutError(f"{node['run_id']} changed unauthorized path {changed}")


def harvest_root(
    root_run_id: str,
    *,
    client: Any | None = None,
    merge: bool = False,
    adapters: tuple[LandingAdapter, ...] | None = None,
    execution_adapters: tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    """Validate keeper receipts and land each code result independently."""

    from limen.fanout_executor import (
        discover_execution_adapters,
        land_succeeded_attempts,
        launch_ready_nodes,
        refresh_provider_attempts,
        resume_execution_sessions,
        wake_executor_workers,
    )

    keeper = client or client_from_env()
    graph = keeper.graph(root_run_id)
    repositories = frozenset(
        str(node.get("packet", {}).get("execution", {}).get("owner_repository"))
        for node in graph.get("nodes", [])
        if node.get("packet", {}).get("intent", {}).get("kind") == "fanout-leaf"
    )
    executors = execution_adapters if execution_adapters is not None else discover_execution_adapters(repositories)
    executor_sessions = resume_execution_sessions(graph, keeper, executors) if executors else {}
    if isinstance(keeper, HttpConductClient):
        refreshed: list[dict[str, Any]] = []
        provider_landed: list[dict[str, Any]] = []
        launched: list[dict[str, Any]] = []
        wakes = wake_executor_workers(root_run_id, executor_sessions)
    else:
        refreshed = refresh_provider_attempts(root_run_id, client=keeper, adapters=executors) if executors else []
        provider_landed = land_succeeded_attempts(root_run_id, client=keeper, adapters=executors) if executors else []
        launched = (
            launch_ready_nodes(
                root_run_id,
                client=keeper,
                adapters_by_session=executor_sessions,
            )
            if executor_sessions
            else []
        )
        wakes = []
    harvest = keeper.harvest(root_run_id)
    if harvest.get("unharvested"):
        return {
            "schema_version": "limen.fanout_harvest.v1",
            "root_run_id": root_run_id,
            "terminal": False,
            "unharvested": harvest["unharvested"],
            "refreshed_attempts": refreshed,
            "provider_landed": provider_landed,
            "launched": launched,
            "executor_wakes": wakes,
            "landed": [],
            "merge_requested": merge,
        }
    landed: list[dict[str, Any]] = []
    available = adapters or landing_adapters()
    for node in harvest.get("nodes", []):
        packet = node.get("packet") or {}
        if packet.get("intent", {}).get("kind") != "fanout-leaf":
            continue
        receipts = node.get("receipts") or []
        if len(receipts) != 1:
            raise FanoutError(f"{node['run_id']} must have exactly one terminal receipt")
        receipt = receipts[0]
        internal_schema = receipt.get("schema_version")
        if internal_schema in {
            "limen.fanout_fence_receipt.v1",
            "limen.fanout_expiry_receipt.v1",
            "limen.fanout_dependency_receipt.v1",
        }:
            if (
                receipt.get("outcome") != "blocked"
                or not receipt.get("mutation_authorized")
                or receipt.get("run_id") != node["run_id"]
            ):
                raise FanoutError(f"{node['run_id']} internal terminal receipt is not authorized")
            expected = packet.get("execution", {}).get("observed_heads") or {}
            if internal_schema != "limen.fanout_dependency_receipt.v1":
                if (receipt.get("expected_heads") or {}) != expected:
                    raise FanoutError(f"{node['run_id']} terminal receipt has the wrong expected heads")
                observed = receipt.get("observed_heads")
                if not isinstance(observed, dict):
                    raise FanoutError(f"{node['run_id']} terminal receipt has no observed-head evidence")
                if internal_schema == "limen.fanout_fence_receipt.v1" and observed == expected:
                    raise FanoutError(f"{node['run_id']} fence receipt did not observe a moved or omitted head")
                if internal_schema == "limen.fanout_expiry_receipt.v1" and observed:
                    raise FanoutError(f"{node['run_id']} expiry receipt unexpectedly claims observed heads")
            landed.append(
                {
                    "run_id": node["run_id"],
                    "receipt_id": receipt["receipt_id"],
                    "outcome": "blocked",
                    "merged": False,
                }
            )
            continue
        if packet.get("effect") == "write":
            if receipt.get("outcome") != "succeeded":
                if (
                    not receipt.get("mutation_authorized")
                    or receipt.get("changed_paths")
                    or (receipt.get("observed_heads_before") or {}) != (receipt.get("observed_heads_after") or {})
                ):
                    raise FanoutError(f"{node['run_id']} terminal failure receipt is not exact")
                landed.append(
                    {
                        "run_id": node["run_id"],
                        "receipt_id": receipt["receipt_id"],
                        "outcome": receipt.get("outcome"),
                        "merged": False,
                    }
                )
                continue
            _validate_code_receipt(node, receipt)
            adapter = next((candidate for candidate in available if candidate.can_land(node, receipt)), None)
            if adapter is None:
                raise FanoutError(f"{node['run_id']} has no receipt-compatible landing adapter")
            landed.append(
                {
                    "run_id": node["run_id"],
                    "receipt_id": receipt["receipt_id"],
                    **adapter.land(node, receipt, merge=merge),
                }
            )
        else:
            before = receipt.get("observed_heads_before") or {}
            after = receipt.get("observed_heads_after") or {}
            if (
                not receipt.get("mutation_authorized")
                or receipt.get("outcome") != "succeeded"
                or receipt.get("changed_paths")
                or before != after
            ):
                raise FanoutError(f"{node['run_id']} read/verification receipt is not exact and successful")
    return {
        "schema_version": "limen.fanout_harvest.v1",
        "root_run_id": root_run_id,
        "terminal": True,
        "receipt_count": harvest.get("receipt_count", 0),
        "refreshed_attempts": refreshed,
        "provider_landed": provider_landed,
        "launched": launched,
        "executor_wakes": wakes,
        "landed": landed,
        "merge_requested": merge,
    }


def canonical_entry_hash(manifest: FanoutManifestV1, *, entry: str) -> str:
    """Prove automatic, conversational, and CLI routes share one canonical pipeline."""

    if entry not in {"automatic", "conversational", "cli"}:
        raise FanoutError(f"unsupported fanout entry route: {entry}")
    return serialize_resource_conflicts(manifest).manifest_hash


def should_evaluate_fanout(request_text: str, *, reversible_leaf_count: int) -> bool:
    forced = any(
        phrase in request_text.casefold() for phrase in ("multitask", "parallelize", "fan out", "fanout", "use cloud")
    )
    return forced or reversible_leaf_count >= 2
