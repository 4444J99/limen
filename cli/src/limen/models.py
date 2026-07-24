import re
import os
from datetime import date, datetime
from typing import Any, Literal
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
JULES_LANDING_HOLD_LABEL = "jules:landing-held"


def has_jules_landing_hold(task: object) -> bool:
    """Whether Jules landing temporarily owns this row without changing lifecycle status."""

    return JULES_LANDING_HOLD_LABEL in (getattr(task, "labels", None) or [])


class DispatchLogEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: datetime
    agent: str
    session_id: str
    # The keeper owns ``agent`` and ``session_id`` as authenticated conduct
    # provenance. Older task workflows used those columns as the logical lane
    # and as a provider run, reservation nonce, landing token, or PR URL.
    # Preserve producer correlation separately; it is metadata and never grants
    # conduct authority.
    logical_agent: str | None = None
    logical_session_id: str | None = None
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
    health_snapshot_hash: str | None = None
    provider_terminal_class: str | None = None
    provider_retry_count: int | None = None
    provider_cooldown_until: datetime | None = None
    provider_health_evidence: dict[str, Any] | None = None
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
    # Crash-resumable Jules landing transaction metadata. These fields are
    # explicit so type checking covers the transaction writer while historical
    # and future extension fields remain readable through ``extra="allow"``.
    landing_event: str | None = None
    landing_terminal: bool | None = None
    landing_outcome: str | None = None
    landing_session_id: str | None = None
    landing_branch: str | None = None
    landing_intent_token: str | None = None
    landing_claim_sha256: str | None = None
    landing_prior_status: str | None = None
    landing_prior_updated: datetime | None = None
    landing_attempt_count: int | None = None
    landing_attempt: int | None = None
    # Exceptional lifecycle transitions remain evidence-bound capabilities,
    # never additions to the normal state graph. Projection owners validate the
    # marker, the exact prior row, and the structured evidence below.
    lifecycle_repair: (
        Literal[
            "prior-done",
            "human-gate-reconcile",
            "fleet-debt-park",
            "pr-observed-terminal",
            "routine-recovered",
            "provider-terminal",
            "stale-successor-hold",
            "recurrence-reopen",
        ]
        | None
    ) = None
    fleet_debt_source: Literal["dispatch-verify", "prior-chronic-log", "repeated-noop"] | None = None
    fleet_debt_count: int | None = Field(default=None, ge=1)
    pr_observed_state: Literal["open", "merged"] | None = None
    pr_observed_ref: str | None = None
    routine_name: str | None = None
    routine_observed_state: Literal["down", "recovered"] | None = None
    execution_started: bool | None = None
    execution_contract_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    execution_reservation_id: str | None = None
    execution_result_kind: Literal["done", "failed", "failed_blocked"] | None = None
    liveness_evidence: Literal["dead-process", "defunct-process", "markerless-expired", "launch-failed"] | None = None
    liveness_reservation_id: str | None = None
    liveness_pid: int | None = Field(default=None, gt=0)
    liveness_age_seconds: float | None = Field(default=None, ge=0)
    recurrence_source: Literal["main-green"] | None = None
    recurrence_head_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    output: str | None = None

    @field_validator("status")
    @classmethod
    def validate_event_status(cls, value: str) -> str:
        if value in VALID_STATUSES or value in {"noop", "pr_open"} or "->" in value:
            return value
        raise ValueError("dispatch event status must be canonical (legacy composite rows are read-only)")


def dispatch_session_id(entry: object) -> str:
    """Return a workflow correlation ID without obscuring keeper provenance.

    Pre-conduct history has only ``session_id``. Broker-projected rows keep the
    authenticated conduct session there and place the producer's logical value
    in ``logical_session_id``.
    """

    if isinstance(entry, dict):
        logical = entry.get("logical_session_id")
        server_owned = entry.get("session_id")
    else:
        logical = getattr(entry, "logical_session_id", None)
        server_owned = getattr(entry, "session_id", None)
    return str(logical if logical not in {None, ""} else server_owned or "")


def dispatch_agent(entry: object) -> str:
    """Return the producer lane while leaving authenticated keeper identity intact."""

    if isinstance(entry, dict):
        logical = entry.get("logical_agent")
        server_owned = entry.get("agent")
    else:
        logical = getattr(entry, "logical_agent", None)
        server_owned = getattr(entry, "agent", None)
    return str(logical if logical not in {None, ""} else server_owned or "")


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
    # WorkLoanV1 source/value collateral. Optional on the storage model so the
    # historical board stays readable while sanctioned producers adopt it.
    origin: str | None = None
    horizon: str | None = None
    value_case: str | None = None
    owner_surface: str | None = None
    external_deadline: bool = False
    due_at: str | None = None
    receipt_verified: bool | None = None
    # Optional live prerequisites. Missing/empty keeps legacy tasks dispatchable; an explicit
    # requirement is evaluated dynamically by handoff and every dispatch selector.
    execution_requirements: list[ExecutionRequirement] | None = None
    # Immutable provider-neutral workstream policy carried from a generated packet into
    # the actual adapter launch seam. Historical tasks omit it.
    workstream_contract: dict[str, Any] | None = None
    # A provider-neutral, digest-bound plan that must select its builder again
    # from live capability and capacity evidence. Historical tasks omit it.
    plan_receipt: dict[str, Any] | None = None
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

    @field_validator("workstream_contract")
    @classmethod
    def validate_workstream_contract(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        from limen.workstream_contract import validate_packet_contract

        return validate_packet_contract(value)

    @field_validator("plan_receipt")
    @classmethod
    def validate_plan_receipt(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        from limen.plan_handoff import validate_plan_receipt

        return validate_plan_receipt(value)

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
