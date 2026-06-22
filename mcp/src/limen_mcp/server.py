import os
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Optional, List, Dict
import json

import yaml
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

# ── Models ─────────────────────────────────────────────────────────────────

class DispatchLogEntry(BaseModel):
    timestamp: datetime
    agent: str
    session_id: str
    status: str
    output: Optional[str] = None

class Task(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    repo: Optional[str] = None
    type: str = "code"
    target_agent: str
    priority: str = "medium"
    budget_cost: int = 1
    status: str = "open"
    labels: List[str] = []
    urls: List[str] = []
    context: Optional[str] = None
    created: date
    updated: Optional[datetime] = None
    dispatch_log: List[DispatchLogEntry] = []

class BudgetTrack(BaseModel):
    date: str
    spent: int = 0
    per_agent: Dict[str, int] = {}

class Budget(BaseModel):
    daily: int = 100
    unit: str = "runs"
    per_agent: Dict[str, int] = {}
    track: BudgetTrack = Field(default_factory=lambda: BudgetTrack(date=""))

class Portal(BaseModel):
    name: str = "Universal Task Intake"
    description: str = ""
    budget: Budget = Field(default_factory=Budget)

class LimenFile(BaseModel):
    version: str = "1.0"
    portal: Portal = Field(default_factory=Portal)
    tasks: List[Task] = []

# ── Server State ───────────────────────────────────────────────────────────

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
        raise RuntimeError("SYSTEM OFFLINE - GO TO SLEEP. Circuit breaker is tripped due to API rate limits or severance.")

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
        data = yaml.safe_load(f)
    return LimenFile(**data)

def _save_data(data: LimenFile, commit_msg: str = "chore: mcp task update"):
    path = _get_tasks_path()
    repo_dir = path.parent
    
    # Write file locally first
    with open(path, "w") as f:
        yaml.dump(data.model_dump(mode="json"), f, default_flow_style=False, sort_keys=False)
        
    # Layer 1: Concurrency Sync (Git Pull --Rebase wrapper)
    if (repo_dir / ".git").exists():
        try:
            # 1. Stash any uncommitted changes
            subprocess.run(["git", "stash"], cwd=repo_dir, capture_output=True)
            # 2. Pull rebase to resolve remote conflicts
            subprocess.run(["git", "pull", "--rebase"], cwd=repo_dir, capture_output=True)
            
            # 3. RE-WRITE the file from memory to resolve any conflicts in tasks.yaml automatically
            with open(path, "w") as f:
                yaml.dump(data.model_dump(mode="json"), f, default_flow_style=False, sort_keys=False)
                
            # 4. Commit and Push
            subprocess.run(["git", "add", path.name], cwd=repo_dir, capture_output=True)
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=repo_dir, capture_output=True)
            subprocess.run(["git", "push"], cwd=repo_dir, capture_output=True)
        except Exception as e:
            print(f"Git sync failed: {e}")

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
    _check_circuit_breaker()
    
    # Layer 3: Hard Loop Limits
    TASK_LOOP_TRACKER[task_id] = TASK_LOOP_TRACKER.get(task_id, 0) + 1
    _save_state()
    if TASK_LOOP_TRACKER[task_id] > 3:
        raise ValueError(f"HARD LOOP LIMIT REACHED: Task {task_id} requested >3 times today. Moving to 'needs_human'. Abandon task immediately.")
        
    data = _load_data()
    for t in data.tasks:
        if t.id == task_id:
            return t.model_dump()
    raise ValueError(f"Task {task_id} not found")

@mcp.tool()
def add_task(title: str, repo: str, agent: str = "jules", priority: str = "medium", budget_cost: int = 1) -> str:
    """Add a new task to the pipeline."""
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
        created=date.today(),
    )
    data.tasks.append(new_task)
    _save_data(data, commit_msg=f"feat: add task {new_id}")
    return f"Created task {new_id}"

@mcp.tool()
def update_task_status(task_id: str, status: str, context: Optional[str] = None) -> str:
    """Update the status and context of a task. Allows 'failed_blocked' to evict dependencies."""
    _check_circuit_breaker()
    data = _load_data()
    
    for t in data.tasks:
        if t.id == task_id:
            # Layer 1: Dynamic Costing - Double budget cost on failure
            if status in ["failed", "failed_blocked", "needs_human"] and t.status == "in_progress":
                t.budget_cost = min(t.budget_cost * 2, 8)
                
            t.status = status
            if context:
                t.context = context
            t.updated = datetime.now()
            
            _save_data(data, commit_msg=f"chore: update {task_id} to {status}")
            return f"Updated {task_id} to {status}. New budget cost: {t.budget_cost}"
            
    raise ValueError(f"Task {task_id} not found")

@mcp.tool()
def get_budget_status() -> dict:
    """Get current budget tracking information."""
    _check_circuit_breaker()
    data = _load_data()
    return data.portal.budget.model_dump()

if __name__ == "__main__":
    mcp.run()
