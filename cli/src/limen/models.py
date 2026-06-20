from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


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
    labels: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    context: Optional[str] = None
    # task ids that must have a MERGED PR before this task is eligible to dispatch. Lets a
    # dependent increment be seeded NOW and auto-build only once its predecessor lands in the
    # base branch (avoids parallel-built PRs that conflict / reference not-yet-merged code).
    depends_on: list[str] = Field(default_factory=list)
    created: date
    updated: Optional[datetime] = None
    dispatch_log: list[DispatchLogEntry] = Field(default_factory=list)


class BudgetTrack(BaseModel):
    date: str
    spent: int = 0
    per_agent: dict[str, int] = Field(default_factory=dict)
    # agent -> ISO timestamp of last budget-window reset; lets each vendor refill on its
    # OWN cadence (codex/claude ~5h, jules/gemini/etc daily) instead of one daily reset.
    per_agent_reset: dict[str, str] = Field(default_factory=dict)


class Budget(BaseModel):
    daily: int = 100
    unit: str = "runs"
    per_agent: dict[str, int] = Field(default_factory=dict)
    track: BudgetTrack = Field(default_factory=lambda: BudgetTrack(date=""))


class Portal(BaseModel):
    name: str = "Universal Task Intake"
    description: str = ""
    budget: Budget = Field(default_factory=Budget)


class LimenFile(BaseModel):
    version: str = "1.0"
    portal: Portal = Field(default_factory=Portal)
    tasks: list[Task] = Field(default_factory=list)
