import os
import re
import tempfile
from datetime import date, datetime
from pathlib import Path
import json
from typing import Any, Dict, List, Literal, Optional

import yaml
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class BoardMutationDeferred(RuntimeError):
    """Repository board writes must enter through the TABVLARIVS keeper."""

    code = "board_mutation_deferred"
    retryable = True
    owner = "tabularius"

    def __init__(self, action: str):
        self.action = action
        super().__init__(
            f"{self.code}: retryable=true owner={self.owner} action={action}; "
            "repository-backed tasks.yaml is keeper-owned; submit a TABVLARIVS ticket "
            "and let its projection PR publish the change"
        )


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


def _serialized_data(data: LimenFile) -> Dict[str, Any]:
    """Serialize without materializing the new optional field on legacy task rows.

    Other optional fields keep the MCP server's established explicit-null behavior.  An explicit
    ``execution_requirements: null`` also remains explicit; only a field that was absent when the
    model was loaded remains absent when saved.
    """

    payload = data.model_dump(mode="json")
    raw_tasks = payload.get("tasks")
    if not isinstance(raw_tasks, list):
        return payload
    for task, raw_task in zip(data.tasks, raw_tasks, strict=True):
        if (
            isinstance(raw_task, dict)
            and task.execution_requirements is None
            and "execution_requirements" not in task.model_fields_set
        ):
            raw_task.pop("execution_requirements", None)
    return payload


def _inside_git_checkout(path: Path) -> bool:
    """Detect a repository without invoking git or manipulating checkout state."""

    directory = path.resolve().parent
    return any((candidate / ".git").exists() for candidate in (directory, *directory.parents))


def _save_data(data: LimenFile, commit_msg: str = "chore: mcp task update"):
    path = _get_tasks_path()
    if _inside_git_checkout(path):
        raise BoardMutationDeferred(commit_msg)

    # Standalone boards used by isolated/test runtimes remain writable, but still
    # use an atomic replace so a reader cannot observe half-written YAML.
    payload = _serialized_data(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            yaml.dump(payload, f, default_flow_style=False, sort_keys=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


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
    data.tasks.append(new_task)
    _save_data(data, commit_msg=f"feat: add task {new_id}")
    return f"Created task {new_id}"


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
            if WORKSTREAM_SUCCESSOR_REQUIRED_LABEL in (t.labels or []) and status not in {"failed", "done", "archived"}:
                return (
                    f"Task {task_id} requires a separately admitted successor; "
                    f"cannot transition expired row to {status}"
                )
            # Layer 1: Dynamic Costing - Double budget cost on failure
            if status in ["failed", "failed_blocked", "needs_human"] and t.status == "in_progress":
                t.budget_cost = min(t.budget_cost * 2, 8)

            t.status = status
            if context:
                t.context = context
            if predicate is not None:
                t.predicate = predicate
            if receipt_target is not None:
                t.receipt_target = receipt_target
            t.updated = datetime.now()

            validate_intake_contract(t)

            _save_data(data, commit_msg=f"chore: update {task_id} to {status}")
            return f"Updated {task_id} to {status}. New budget cost: {t.budget_cost}"

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
    """Proactively claim a task from the pipeline. Agent writes its ID to the
    task's target_agent and updates its own presence beacon. Prevents double-claim
    by checking the task is still open. Returns confirmation or error."""
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

            now = datetime.now()
            t.status = "dispatched"
            t.target_agent = agent_name
            t.updated = now
            track = data.portal.budget.track
            track.spent += t.budget_cost
            track.per_agent[agent_name] = track.per_agent.get(agent_name, 0) + t.budget_cost

            entry = DispatchLogEntry(
                timestamp=now,
                agent=agent_name,
                session_id="mcp-agent-claim",
                status="dispatched",
                output=f"Claimed by {agent_name} via MCP",
            )
            t.dispatch_log.append(entry)

            _save_data(data, commit_msg=f"feat: {agent_name} claim task {task_id}")
            return f"{agent_name} claimed task {task_id} (status=dispatched)"

    raise ValueError(f"Task {task_id} not found")


if __name__ == "__main__":
    mcp.run()
