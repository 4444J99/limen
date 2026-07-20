import os
import re
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
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
WORKSTREAM_SUCCESSOR_REQUIRED_LABEL = "workstream:successor-required"


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

mcp = FastMCP("Limen")

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
    capability_token: str,
    observed_heads: Optional[Dict[str, str]] = None,
) -> dict:
    """Renew a lease while fencing any moved exact Git heads."""

    _check_circuit_breaker()
    return _conduct_client().heartbeat(lease, capability_token, observed_heads=observed_heads or {})


@mcp.tool()
def conduct_report(lease: str, capability_token: str, receipt: Dict[str, Any]) -> dict:
    """Submit a schema-validated terminal receipt; late results remain evidence-only."""

    _check_circuit_breaker()
    return _conduct_client().report(lease, capability_token, RunReceiptV1.model_validate(receipt))


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
    agent: str = "jules",
    priority: str = "medium",
    budget_cost: int = 1,
) -> str:
    """Add a new task to the pipeline."""
    title = _validate_text(title, "title", 512)
    repo = _validate_text(repo, "repo", 256)
    agent = _validate_optional_enum(agent, VALID_AGENTS, "agent") or "jules"
    priority = _validate_optional_enum(priority, VALID_PRIORITIES, "priority") or "medium"
    if type(budget_cost) is not int or budget_cost < 1 or budget_cost > 100:
        raise ValueError("budget_cost must be an integer between 1 and 100")
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
    mcp.run()
