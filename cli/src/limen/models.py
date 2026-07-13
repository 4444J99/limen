import re
from datetime import date, datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator


TASK_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._/-]*$"
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
    # A status is lifecycle state; a destination is routing metadata.  Historical
    # boards contain composite values such as ``failed->jules``.  Readers preserve
    # those rows, while every new writer emits a canonical status plus route_to and
    # heal-board appends a corrective head without rewriting history.
    route_to: str | None = None
    execution_profile: dict[str, Any] | None = None
    selected_model: str | None = None
    selection_source: str | None = None
    catalog_hash: str | None = None
    # Provider-neutral remote lifecycle.  Submission is only ``dispatched``; these fields make the
    # exact off-box run recoverable without interpreting a provider-shaped session string.
    provider_run_id: str | None = None
    provider_url: str | None = None
    base_sha: str | None = None
    control_repo: str | None = None
    control_ref: str | None = None
    control_ref_kind: str | None = None
    control_sha: str | None = None
    workflow_id: int | None = None
    workflow_path: str | None = None
    workflow_event: str | None = None
    verification_context_digest: str | None = None
    remote_state: str | None = None
    remote_request_id: str | None = None
    remote_receipt: str | None = None
    output: str | None = None

    @field_validator("status")
    @classmethod
    def validate_event_status(cls, value: str) -> str:
        if value in VALID_STATUSES or value in {"noop", "pr_open"} or "->" in value:
            return value
        raise ValueError("dispatch event status must be canonical (legacy composite rows are read-only)")


class Task(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=128, pattern=TASK_ID_PATTERN)
    title: str
    description: str | None = None
    repo: str | None = None
    type: str = "code"
    target_agent: str
    # PURPOSE partition — the durable, single-purpose channel this task belongs to ("contributions",
    # "correspondence", "financial", …): the axis ABOVE the vendor `target_agent` lane. The derived
    # roster + alias resolution live in limen.workstream (a new organ in organ-ladder.json IS a new
    # channel, no code edit). A worker session draws OPEN tasks from ONE workstream only — the cure
    # for mixed-purpose PR pileup. None → unassigned. See docs/lanes/.
    workstream: str | None = None
    priority: str = "medium"
    budget_cost: int = Field(default=1, ge=1, le=1000)
    status: str = "open"
    labels: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    context: str | None = None
    # Typed intake evidence. Optional here so historical boards remain loadable;
    # every new/open submission is enforced by ``limen.intake`` at the writer
    # and keeper seams, and selected legacy work is normalized before dispatch.
    predicate: str | None = None
    receipt_target: str | None = None
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

    @field_validator("budget_cost", mode="before")
    @classmethod
    def validate_budget_cost(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("budget_cost must be an integer, not a boolean")
        return value

    @field_validator("workstream")
    @classmethod
    def normalize_workstream(cls, value: str | None) -> str | None:
        """Surface-normalize to a kebab handle (lowercase, runs of non-alphanumerics → '-'). Alias→
        canonical resolution (e.g. 'revenue' → 'financial') is a read-time concern in limen.workstream
        so the model stays pure — no file I/O in a validator. Empty/whitespace → None (unassigned)."""
        if value is None:
            return None
        handle = re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")
        return handle or None


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
    agents: dict[str, dict[str, object]] = Field(default_factory=dict)


class LimenFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str = "1.0"
    portal: Portal = Field(default_factory=Portal)
    tasks: list[Task] = Field(default_factory=list)
