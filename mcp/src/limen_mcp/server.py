import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional, List, Dict

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

# ── Server ─────────────────────────────────────────────────────────────────

mcp = FastMCP("Limen")

def _get_tasks_path() -> Path:
    p = os.environ.get("LIMEN_TASKS")
    if p:
        return Path(p)
    # Default to ~/Workspace/limen/tasks.yaml
    default_path = Path.home() / "Workspace" / "limen" / "tasks.yaml"
    if default_path.exists():
        return default_path
    # Fallback to local tasks.yaml
    return Path("tasks.yaml")

def _load_data() -> LimenFile:
    path = _get_tasks_path()
    if not path.exists():
        return LimenFile()
    with open(path) as f:
        data = yaml.safe_load(f)
    return LimenFile(**data)

def _save_data(data: LimenFile):
    path = _get_tasks_path()
    with open(path, "w") as f:
        yaml.dump(data.model_dump(mode="json"), f, default_flow_style=False, sort_keys=False)

@mcp.tool()
def list_tasks(status: Optional[str] = None, agent: Optional[str] = None) -> List[dict]:
    """List tasks in the pipeline, optionally filtered by status or agent."""
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
    data = _load_data()
    for t in data.tasks:
        if t.id == task_id:
            return t.model_dump()
    raise ValueError(f"Task {task_id} not found")

@mcp.tool()
def add_task(title: str, repo: str, agent: str = "jules", priority: str = "medium", budget_cost: int = 1) -> str:
    """Add a new task to the pipeline."""
    data = _load_data()
    # Generate ID
    last_num = 0
    for t in data.tasks:
        if t.id.startswith("LIMEN-"):
            try:
                num = int(t.id.split("-")[1])
                if num > last_num:
                    last_num = num
            except:
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
    _save_data(data)
    return f"Created task {new_id}"

@mcp.tool()
def update_task_status(task_id: str, status: str, context: Optional[str] = None) -> str:
    """Update the status and context of a task."""
    data = _load_data()
    for t in data.tasks:
        if t.id == task_id:
            t.status = status
            if context:
                t.context = context
            t.updated = datetime.now()
            _save_data(data)
            return f"Updated {task_id} to {status}"
    raise ValueError(f"Task {task_id} not found")

@mcp.tool()
def get_budget_status() -> dict:
    """Get current budget tracking information."""
    data = _load_data()
    return data.portal.budget.model_dump()

if __name__ == "__main__":
    mcp.run()
