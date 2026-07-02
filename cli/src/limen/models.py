from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


VALID_STATUSES = {
    "open",
    "dispatched",
    "in_progress",
    "done",
    "failed",
    "failed_blocked",
    "needs_human",
    "archived",
}


class DispatchLogEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: datetime
    agent: str
    session_id: str
    status: str
    output: str | None = None


class Task(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    description: str | None = None
    repo: str | None = None
    type: str = "code"
    target_agent: str
    priority: str = "medium"
    budget_cost: int = 1
    status: str = "open"
    labels: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    context: str | None = None
    # Optional per-task Claude tier pin ("haiku"|"sonnet"|"opus"|"fable") — an escape hatch that
    # overrides the earned-tier ladder's class-based derivation for THIS task (the env
    # LIMEN_CLAUDE_MODEL still wins above it). Fable still requires LIMEN_FABLE_ACCEPTANCE.
    # None → derive the tier. See dispatch._claude_model.
    claude_tier: str | None = None
    # task ids that must have a MERGED PR before this task is eligible to dispatch. Lets a
    # dependent increment be seeded NOW and auto-build only once its predecessor lands in the
    # base branch (avoids parallel-built PRs that conflict / reference not-yet-created code).
    depends_on: list[str] = Field(default_factory=list)
    created: date
    updated: datetime | None = None
    dispatch_log: list[DispatchLogEntry] = Field(default_factory=list)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in VALID_STATUSES:
            raise ValueError(f"status must be one of {', '.join(sorted(VALID_STATUSES))}")
        return value


class BudgetTrack(BaseModel):
    model_config = ConfigDict(extra="allow")

    date: str
    spent: int = 0
    per_agent: dict[str, int] = Field(default_factory=dict)
    # agent -> ISO timestamp of last budget-window reset; lets each vendor refill on its
    # OWN cadence (codex/claude ~5h, jules/gemini/etc daily) instead of one daily reset.
    per_agent_reset: dict[str, str] = Field(default_factory=dict)


class Budget(BaseModel):
    model_config = ConfigDict(extra="allow")

    daily: int = 100
    unit: str = "runs"
    per_agent: dict[str, int] = Field(default_factory=dict)
    track: BudgetTrack = Field(default_factory=lambda: BudgetTrack(date=""))


class Portal(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = "Universal Task Intake"
    description: str = ""
    budget: Budget = Field(default_factory=Budget)
    agents: dict[str, dict[str, Any]] = Field(default_factory=dict)


class LimenFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str = "1.0"
    portal: Portal = Field(default_factory=Portal)
    tasks: list[Task] = Field(default_factory=list)
