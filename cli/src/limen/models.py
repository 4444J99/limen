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
    labels: list[str] = []
    urls: list[str] = []
    context: Optional[str] = None
    created: date
    updated: Optional[datetime] = None
    dispatch_log: list[DispatchLogEntry] = []


class BudgetTrack(BaseModel):
    date: str
    spent: int = 0
    per_agent: dict[str, int] = {}


class Budget(BaseModel):
    daily: int = 100
    unit: str = "runs"
    per_agent: dict[str, int] = {}
    track: BudgetTrack = BudgetTrack(date="")


class Portal(BaseModel):
    name: str = "Universal Task Intake"
    description: str = ""
    budget: Budget = Budget()


class LimenFile(BaseModel):
    version: str = "1.0"
    portal: Portal = Portal()
    tasks: list[Task] = []
