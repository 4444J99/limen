"""TABVLARIVS compatibility relay for the authenticated conduct keeper.

The historical implementation made this process a local ``tasks.yaml`` writer. That still allowed
the laptop cache to diverge from the GitHub-backed owner and gave local Git plumbing an independent
authority path. The conduct broker is now the sole logical record keeper: producers may append
immutable outbound tickets locally, but this module can only translate them into bounded conduct
packets and archive a ticket after the remote projection receipt is acknowledged.

Ticket lifecycle::

    logs/tickets/inbox/<id>.json  --relay-->  acknowledged → archive/
                                              invalid      → rejected/ (+ <id>.reason.txt)
                                              unavailable  → remains in inbox

The local board is read only as an optimistic cache for exact revision guards. A stale cache is
fenced by the remote owner. Broker absence leaves valid tickets pending and acknowledges no
transition. Unsupported metadata, ordering, removal, and server-owned field mutations fail closed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from limen.conduct.broker import ConductError
from limen.conduct.client import BrokerUnavailable, LocalConductClient, client_from_env
from limen.conduct.models import (
    AgentIdentityV1,
    AuthorityEnvelopeV1,
    ConductorSessionV1,
    FanoutBoundsV1,
    ResourceClaimV1,
    RetryPolicyV1,
    SpendEnvelopeV1,
    WorkPacketV1,
    canonical_hash,
)
from limen.intake import validate_intake_contract
from limen.io import (
    load_limen_file,
    local_conduct_projection_lock,
    queue_lock,
    save_local_conduct_projection,
)
from limen.materialize import (
    EV_BOARD_META,
    EV_BOARD_ORDER,
    EV_TASK_REMOVE,
    EV_TASK_UPSERT,
    Event,
    diff_boards,
)
from limen.models import VALID_STATUSES, LimenFile, Task
from limen.workstream_contract import WORKSTREAM_SUCCESSOR_REQUIRED_LABEL

# --- ticket intents (a superset of materialize's Event tags, plus the status convenience) --------
INTENT_UPSERT = "task.upsert"  # create-or-merge a task field-set (patch may be full or partial)
INTENT_STATUS = "task.status"  # the common worker ticket: set status + append a dispatch_log entry
INTENT_REMOVE = "task.remove"  # drop a task id (prune/archive-out)
INTENT_ORDER = "board.order"  # set the task display order (patch = {"ids": [...]})
INTENT_META = "board.meta"  # set board version/portal (patch = {"version":..,"portal":..})
_INTENTS = frozenset({INTENT_UPSERT, INTENT_STATUS, INTENT_REMOVE, INTENT_ORDER, INTENT_META})
BOARD_PUBLICATION_BRANCH = "tabularius/board-projection"
BOARD_PUBLICATION_TITLE = "tabularius: publish board projection"
_PATCHABLE_TASK_FIELDS = frozenset(
    {
        "title",
        "description",
        "repo",
        "type",
        "target_agent",
        "workstream",
        "priority",
        "budget_cost",
        "status",
        "labels",
        "urls",
        "context",
        "predicate",
        "receipt_target",
        "execution_requirements",
        "workstream_contract",
        "claude_tier",
        "depends_on",
    }
)
_STRUCTURED_LOG_FIELDS = frozenset(
    {
        "route_to",
        "execution_profile",
        "selected_model",
        "selection_source",
        "catalog_hash",
        "provider_run_id",
        "provider_url",
        "base_sha",
        "control_repo",
        "control_ref",
        "control_ref_kind",
        "control_sha",
        "workflow_id",
        "workflow_path",
        "workflow_event",
        "verification_context_digest",
        "remote_state",
        "remote_request_id",
        "remote_receipt",
        "landing_event",
        "landing_terminal",
        "landing_outcome",
        "landing_session_id",
        "landing_branch",
        "landing_intent_token",
        "landing_claim_sha256",
        "landing_prior_status",
        "landing_prior_updated",
        "landing_attempt_count",
        "landing_attempt",
        "lifecycle_repair",
        "fleet_debt_source",
        "fleet_debt_count",
        "pr_observed_state",
        "pr_observed_ref",
        "routine_name",
        "routine_observed_state",
        "execution_started",
        "execution_contract_hash",
        "execution_reservation_id",
        "execution_result_kind",
        "liveness_evidence",
        "liveness_reservation_id",
        "liveness_pid",
        "liveness_age_seconds",
        "recurrence_source",
        "recurrence_head_sha",
    }
)
_CANONICAL_TRANSITIONS = {
    "open": frozenset({"open", "dispatched"}),
    "dispatched": frozenset({"open", "dispatched", "in_progress"}),
    "in_progress": frozenset({"in_progress", "done", "failed", "failed_blocked", "needs_human"}),
    "failed": frozenset({"failed", "open"}),
    "failed_blocked": frozenset({"failed_blocked", "open"}),
    "needs_human": frozenset({"needs_human", "open"}),
    "done": frozenset({"done", "archived"}),
    "archived": frozenset({"archived"}),
}


class Ticket(BaseModel):
    """One immutable unit of board work a worker hands to the record-keeper.

    A worker builds a Ticket describing the transition it performed ("here's the work I did") and
    drops it into the inbox via `submit_ticket`. It is an Event with provenance — the `patch` is a
    *field-level delta*, never a whole-board rewrite, so a torn ticket can at worst be quarantined
    and never corrupts the SSOT.
    """

    ticket_id: str
    timestamp: datetime
    agent: str
    session_id: str = "unknown"
    intent: str
    task_id: str | None = None
    # field-level delta: for upsert/status the task field-patch; for board.order {"ids": [...]};
    # for board.meta {"version": .., "portal": ..}.
    patch: dict[str, Any] | None = None
    # optional dispatch_log payload appended to the task's log — {"status": .., "output"?: ..}.
    log: dict[str, Any] | None = None
    # Optional optimistic concurrency guard, evaluated by the keeper against
    # the exact current task immediately before this ticket is folded.  A
    # migration can therefore never archive a task that another ticket claimed
    # after compilation.
    precondition: dict[str, Any] | None = None


def task_state_sha256(fields: dict[str, Any]) -> str:
    """Content hash for one JSON-mode task state, including its append-only log."""

    encoded = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def new_ticket_id(session_id: str = "unknown", now: datetime | None = None) -> str:
    """A sortable, collision-free ticket id: `<utc-timestamp>-<session>-<rand>`. The timestamp
    prefix makes a plain filename sort chronological (the keeper's drain order), and the random
    tail guarantees two tickets from the same session in the same microsecond never collide."""
    now = now or datetime.now(timezone.utc)
    safe_session = "".join(c if c.isalnum() or c in "._-" else "_" for c in session_id)[:40]
    return f"{now.strftime('%Y%m%dT%H%M%S_%f')}Z-{safe_session}-{uuid.uuid4().hex[:8]}"


# --- inbox geometry ------------------------------------------------------------------------------
def tickets_root(board_path: Path) -> Path:
    return Path(board_path).parent / "logs" / "tickets"


def _inbox(board_path: Path) -> Path:
    return tickets_root(board_path) / "inbox"


def _archive(board_path: Path) -> Path:
    return tickets_root(board_path) / "archive"


def _rejected(board_path: Path) -> Path:
    return tickets_root(board_path) / "rejected"


def submit_ticket(board_path: Path, ticket: Ticket) -> Path:
    """Append a ticket to the inbox — the worker's *only* board-write surface.

    Exclusive + atomic: write to a temp file, fsync, then `os.link` it into place. `os.link` fails
    if the destination exists, so a duplicate `ticket_id` raises instead of clobbering, and a reader
    can never observe a half-written ticket. No lock, no board read — many workers submit
    concurrently without contending.
    """
    if ticket.intent not in _INTENTS:
        raise ValueError(f"unknown ticket intent: {ticket.intent!r}")
    inbox = _inbox(board_path)
    inbox.mkdir(parents=True, exist_ok=True)
    dest = inbox / f"{ticket.ticket_id}.json"
    fd, tmp = tempfile.mkstemp(dir=inbox, prefix=f".{ticket.ticket_id}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(ticket.model_dump_json())
            f.flush()
            os.fsync(f.fileno())
        os.link(tmp, dest)  # atomic exclusive create — raises FileExistsError on a duplicate id
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return dest


def submit_task_upsert(
    board_path: Path,
    task: "Task | dict[str, Any]",
    *,
    agent: str,
    session_id: str = "unknown",
    now: datetime | None = None,
) -> Path:
    """One-line producer: hand the keeper a whole task field-set as an upsert ticket.

    This is the conversion target for every writer that used to `load → extend → save_limen_file`.
    A generator/miner drops the ``save_limen_file`` and instead calls this once per NEW task; the
    keeper folds it onto the board on the next beat. The full field-set becomes the ticket ``patch``.

    The task is validated HERE (fail-fast, exactly like the old ``Task(**t)`` before a direct write),
    so a producer never emits an invalid task — the keeper's per-ticket validation stays a second
    line of defense, not the first. The emitted absent precondition makes this a create-only producer
    seam: a duplicate/stale generator ticket is quarantined instead of merging over a live lifecycle
    row. Owners use ``submit_task_status`` or an explicitly preconditioned raw ticket for updates.
    """
    validated = task if isinstance(task, Task) else Task.model_validate(task)
    validate_intake_contract(validated, is_new=True)
    fields = validated.model_dump(mode="json", exclude_none=True)
    tid = fields.get("id")
    if not tid:
        raise ValueError("task upsert requires an 'id'")
    now = now or datetime.now(timezone.utc)
    ticket = Ticket(
        ticket_id=new_ticket_id(session_id, now),
        timestamp=now,
        agent=agent,
        session_id=session_id,
        intent=INTENT_UPSERT,
        task_id=tid,
        patch=fields,
        precondition={"absent": True},
    )
    return submit_ticket(board_path, ticket)


def submit_task_status(
    board_path: Path,
    task_id: str,
    *,
    status: str,
    agent: str,
    session_id: str = "unknown",
    output: str | None = None,
    patch: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> Path:
    """One-line producer for status/result writers.

    A dispatcher/harvester that used to mutate ``task.status`` and append a dispatch log can hand
    the transition to TABVLARIVS instead. The optional ``patch`` is a field-level delta folded with
    the status; it must not carry a conflicting status.
    """
    if not task_id:
        raise ValueError("task status requires a task_id")
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {', '.join(sorted(VALID_STATUSES))}")
    fields = dict(patch or {})
    if "status" in fields and fields["status"] != status:
        raise ValueError("status patch conflicts with status argument")
    fields["status"] = status
    now = now or datetime.now(timezone.utc)
    ticket = Ticket(
        ticket_id=new_ticket_id(session_id, now),
        timestamp=now,
        agent=agent,
        session_id=session_id,
        intent=INTENT_STATUS,
        task_id=task_id,
        patch=fields,
        log={"status": status, "output": output},
    )
    return submit_ticket(board_path, ticket)


@dataclass
class DrainResult:
    """The outcome of one drain pass — counts only (safe to log)."""

    pending: int = 0
    applied: int = 0
    rejected: int = 0
    wrote: bool = False
    deferred: bool = False
    note: str = ""
    applied_ids: list[str] = field(default_factory=list)
    rejected_ids: list[str] = field(default_factory=list)
    projected_tasks: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class PreserveResult:
    changed: bool = False
    pushed: bool = False
    published: bool = False
    deferred: bool = False
    skipped: bool = False
    reason: str = ""
    commit: str = ""
    branch: str = ""
    pr_number: int = 0


def pending_count(board_path: Path) -> int:
    inbox = _inbox(board_path)
    return len(list(inbox.glob("*.json"))) if inbox.is_dir() else 0


def pending_upsert_patches(board_path: Path) -> list[dict[str, Any]]:
    """Return valid pending upsert patches without mutating the board.

    Producers use this as a read-side dedup hint: a task can be absent from the board but already
    waiting in the keeper inbox. Malformed tickets are ignored here; the drain pass owns quarantine.
    """
    inbox = _inbox(board_path)
    if not inbox.is_dir():
        return []
    patches: list[dict[str, Any]] = []
    for path in sorted(inbox.glob("*.json")):
        try:
            ticket = Ticket.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if ticket.intent == INTENT_UPSERT and isinstance(ticket.patch, dict):
            patches.append(ticket.patch)
    return patches


def pending_task_ids(board_path: Path) -> set[str]:
    ids: set[str] = set()
    for patch in pending_upsert_patches(board_path):
        tid = patch.get("id")
        if isinstance(tid, str) and tid:
            ids.add(tid)
    return ids


def _gh(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run the legacy publication check dispatcher without granting board-write authority."""

    return subprocess.run(
        ["gh", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=120,
    )


def _short_output(proc: subprocess.CompletedProcess[str]) -> str:
    return (proc.stderr or proc.stdout or "").strip().replace("\n", " ")[:220]


def _dispatch_pr_gate(repo: Path, slug: str, publication_branch: str) -> str:
    """Compatibility helper for an already-created publication PR.

    The conduct broker remains the only board writer. This helper can only ask
    GitHub to evaluate an existing exact branch; it cannot create, push, or
    advance a board projection.
    """

    if os.environ.get("GITHUB_ACTIONS", "").lower() != "true":
        return ""
    result = _gh(
        repo,
        ["workflow", "run", "pr-gate.yml", "--repo", slug, "--ref", publication_branch],
    )
    return "" if result.returncode == 0 else f"pr-gate-dispatch-failed:{_short_output(result)}"


def _ticket_from_event(event: Event, *, agent: str, session_id: str, now: datetime) -> Ticket:
    """Translate one pure projection delta into its immutable keeper receipt."""

    event_type = str(event.get("type") or "")
    ticket_id = new_ticket_id(session_id, now)
    if event_type == EV_BOARD_META:
        return Ticket(
            ticket_id=ticket_id,
            timestamp=now,
            agent=agent,
            session_id=session_id,
            intent=INTENT_META,
            patch=dict(event.get("data") or {}),
        )
    if event_type == EV_BOARD_ORDER:
        return Ticket(
            ticket_id=ticket_id,
            timestamp=now,
            agent=agent,
            session_id=session_id,
            intent=INTENT_ORDER,
            patch=dict(event.get("data") or {}),
        )
    if event_type == EV_TASK_UPSERT:
        return Ticket(
            ticket_id=ticket_id,
            timestamp=now,
            agent=agent,
            session_id=session_id,
            intent=INTENT_UPSERT,
            task_id=str(event["task_id"]),
            patch=dict(event.get("data") or {}),
        )
    if event_type == EV_TASK_REMOVE:
        return Ticket(
            ticket_id=ticket_id,
            timestamp=now,
            agent=agent,
            session_id=session_id,
            intent=INTENT_REMOVE,
            task_id=str(event["task_id"]),
        )
    raise ValueError(f"unknown event type: {event_type!r}")


def _safe_identifier(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._:/@+-]+", "-", str(value)).strip("-")
    if not cleaned or not cleaned[0].isalnum():
        cleaned = fallback
    return cleaned[:256]


def _canonical_revision(fields: dict[str, Any]) -> str:
    value: Any = fields.get("updated")
    if value is None and fields.get("dispatch_log"):
        value = fields["dispatch_log"][-1].get("timestamp")
    if value is None:
        value = fields.get("created") or fields.get("status")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    rendered = str(value)
    if re.match(r"^\d{4}-\d{2}-\d{2}T", rendered):
        try:
            parsed = datetime.fromisoformat(rendered.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        except ValueError:
            pass
    return rendered


def _compatibility_intent(ticket: Ticket, base: dict[str, Any] | None) -> dict[str, Any]:
    log = dict(ticket.log or {})
    # ``agent``/``session_id`` in the packet log are untrusted workflow
    # correlation. The keeper projects them under logical names while deriving
    # canonical dispatch-log identity from the authenticated conductor event.
    log.setdefault("agent", ticket.agent)
    log.setdefault("session_id", ticket.session_id)
    if ticket.intent in {INTENT_REMOVE, INTENT_META, INTENT_ORDER}:
        raise ValueError(
            f"{ticket.intent} has no authenticated remote compatibility transition; "
            "file a bounded broker protocol extension instead of mutating the local projection"
        )
    if not ticket.task_id:
        raise ValueError(f"{ticket.intent} requires task_id")
    patch = dict(ticket.patch or {})
    if base is None:
        if ticket.intent != INTENT_UPSERT:
            raise ValueError(f"task {ticket.task_id} is absent from the hot projection")
        supplied = {**patch, "id": ticket.task_id}
        return {
            "kind": "task.upsert",
            "task_id": ticket.task_id,
            "expected_absent": True,
            "task": supplied,
            "log": log,
        }

    precondition = ticket.precondition or {}
    if precondition.get("absent") is True:
        raise ValueError(f"task precondition failed: {ticket.task_id} is no longer absent")
    if "status" in precondition and base.get("status") != precondition["status"]:
        raise ValueError(
            f"task precondition failed: {ticket.task_id} status is {base.get('status')!r}, "
            f"expected {precondition['status']!r}"
        )
    if "task_sha256" in precondition and task_state_sha256(base) != precondition["task_sha256"]:
        raise ValueError(f"task precondition failed: {ticket.task_id} exact state changed")

    desired = {**base, **patch}
    changed = {key: value for key, value in desired.items() if key in _PATCHABLE_TASK_FIELDS and base.get(key) != value}
    unsupported = sorted(
        key
        for key, value in desired.items()
        if key not in _PATCHABLE_TASK_FIELDS | {"id", "created", "updated", "dispatch_log"} and base.get(key) != value
    )
    if unsupported:
        raise ValueError(f"task {ticket.task_id} changes unsupported remote fields: {', '.join(unsupported)}")
    prior_status = str(base.get("status") or "")
    next_status = str(desired.get("status") or prior_status)
    if prior_status == "open" and next_status == "dispatched":
        kind = "task.claim"
    elif next_status != prior_status:
        kind = "task.status"
    else:
        kind = "task.mutate"
    return {
        "kind": kind,
        "task_id": ticket.task_id,
        "expected_status": prior_status,
        "expected_revision": _canonical_revision(base),
        "patch": changed,
        "log": log,
    }


def _local_conduct_log(event: dict[str, Any], status: str, fallback_output: str) -> dict[str, Any]:
    log = dict((event.get("intent") or {}).get("log") or {})
    structured = {key: value for key, value in log.items() if key in _STRUCTURED_LOG_FIELDS and value is not None}
    return {
        "timestamp": str(event["timestamp"]),
        "agent": str(event["agent"]),
        "session_id": str(event["session_id"]),
        "logical_agent": str(log.get("agent") or event["agent"]),
        "logical_session_id": str(log.get("session_id") or event["session_id"]),
        "status": status,
        "output": str(log.get("output") if log.get("output") is not None else fallback_output),
        **structured,
        "conduct_event_id": str(event["event_id"]),
        "conduct_run_id": str(event["run_id"]),
        "conduct_lease_id": str(event["lease_id"]),
        "conduct_generation": int(event["generation"]),
    }


def _reset_local_budget_window(budget: dict[str, Any], timestamp: str) -> None:
    track = budget.setdefault("track", {"date": "", "spent": 0, "per_agent": {}})
    current_date = timestamp[:10]
    if str(track.get("date") or "") == current_date:
        return
    track["date"] = current_date
    track["spent"] = 0
    track["per_agent"] = {str(agent): 0 for agent in (budget.get("per_agent") or {})}


def _local_budget_debit(
    board: dict[str, Any], task: dict[str, Any], event: dict[str, Any], patch: dict[str, Any]
) -> None:
    amount = task.get("budget_cost", 0)
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise ValueError(f"task {task['id']} has invalid canonical budget_cost")
    agent = str(patch.get("target_agent") or task.get("target_agent") or "")
    if not agent or agent == "any":
        raise ValueError(f"task {task['id']} claim requires one concrete target_agent")
    if task.get("target_agent") not in {None, "", "any", agent}:
        raise ValueError(f"task {task['id']} targets {task.get('target_agent')}, not claim agent {agent}")
    budget = (board.get("portal") or {}).get("budget") or {}
    if not budget or not amount:
        return
    _reset_local_budget_window(budget, str(event["timestamp"]))
    track = budget["track"]
    track.setdefault("per_agent", {})
    prior_total = int(track.get("spent") or 0)
    prior_agent = int(track["per_agent"].get(agent) or 0)
    daily_limit = int(budget.get("daily", 2**63 - 1))
    agent_limit = int((budget.get("per_agent") or {}).get(agent, daily_limit))
    if prior_total + amount > daily_limit or prior_agent + amount > agent_limit:
        raise ValueError(f"task {task['id']} exceeds live {agent} compatibility budget")
    track["spent"] = prior_total + amount
    track["per_agent"][agent] = prior_agent + amount


def _local_budget_refund(board: dict[str, Any], task: dict[str, Any], event: dict[str, Any]) -> None:
    amount = task.get("budget_cost", 0)
    agent = str(task.get("target_agent") or "")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0 or not agent or agent == "any":
        raise ValueError(f"task {task['id']} cannot derive a canonical budget refund")
    budget = (board.get("portal") or {}).get("budget") or {}
    if not budget or not amount:
        return
    _reset_local_budget_window(budget, str(event["timestamp"]))
    track = budget["track"]
    track.setdefault("per_agent", {})
    track["spent"] = max(0, int(track.get("spent") or 0) - amount)
    track["per_agent"][agent] = max(0, int(track["per_agent"].get(agent) or 0) - amount)


def _held_jules_landing_recovery(task: dict[str, Any], next_status: str, log: dict[str, Any]) -> bool:
    return bool(
        task.get("status") == "failed"
        and "jules:landing-held" in (task.get("labels") or [])
        and log.get("landing_event") == "terminal"
        and log.get("landing_terminal") is True
        and log.get("landing_intent_token")
        and next_status in {"done", "failed", "failed_blocked"}
    )


def _logical_log_session(entry: dict[str, Any]) -> str:
    return str(entry.get("logical_session_id") or entry.get("session_id") or "")


def _prior_chronic_evidence(task: dict[str, Any]) -> bool:
    from limen.chronic import CHRONIC_ESCALATION_RE

    for entry in reversed(task.get("dispatch_log") or []):
        if str(entry.get("status") or "") != "needs_human":
            continue
        return bool(CHRONIC_ESCALATION_RE.search(str(entry.get("output") or "")))
    return False


def _repeated_noop_evidence(task: dict[str, Any]) -> int:
    return sum(
        1
        for entry in (task.get("dispatch_log") or [])
        if str(entry.get("status") or "") == "failed"
        and ("no-op" in str(entry.get("output") or "").lower() or "noop" in str(entry.get("output") or "").lower())
    )


def _lifecycle_repair_authorized(
    task: dict[str, Any],
    next_status: str,
    log: dict[str, Any],
    patch: dict[str, Any],
) -> bool:
    """Validate one explicit exceptional transition against its exact evidence."""

    marker = str(log.get("lifecycle_repair") or "")
    prior_status = str(task.get("status") or "")
    labels = {str(label) for label in patch.get("labels", task.get("labels") or [])}

    if marker == "prior-done":
        return bool(
            next_status == "done"
            and prior_status != "archived"
            and any(entry.get("status") == "done" for entry in (task.get("dispatch_log") or []))
        )
    if marker == "human-gate-reconcile":
        return bool(
            prior_status in {"open", "dispatched", "failed"}
            and next_status == "needs_human"
            and "needs-human" in labels
        )
    if marker == "fleet-debt-park":
        source = str(log.get("fleet_debt_source") or "")
        count = log.get("fleet_debt_count")
        evidence_ok = bool(
            isinstance(count, int)
            and not isinstance(count, bool)
            and (
                (source == "dispatch-verify" and count >= 3)
                or (source == "prior-chronic-log" and count >= 1 and _prior_chronic_evidence(task))
                or (source == "repeated-noop" and count >= 2 and _repeated_noop_evidence(task) >= count)
            )
        )
        return bool(
            prior_status in {"open", "dispatched", "failed", "needs_human"}
            and next_status == "failed_blocked"
            and "chronic-fleet-debt" in labels
            and evidence_ok
        )
    if marker == "pr-observed-terminal":
        ref = str(log.get("pr_observed_ref") or "")
        observed = str(log.get("pr_observed_state") or "")
        ref_match = re.fullmatch(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#([1-9][0-9]*)", ref)
        task_repo = str(patch.get("repo", task.get("repo")) or "")
        return bool(
            prior_status == "dispatched"
            and next_status == "done"
            and observed in {"open", "merged"}
            and ref_match
            and (not task_repo or ref_match.group(1) == task_repo)
        )
    if marker == "routine-recovered":
        name = str(log.get("routine_name") or "")
        return bool(
            prior_status == "needs_human"
            and next_status == "done"
            and "routine-freshness" in labels
            and log.get("routine_observed_state") == "recovered"
            and name
            and task.get("id") == f"ASK-routine-{name}"
        )
    prior_log = (task.get("dispatch_log") or [])[-1:] or [{}]
    prior_entry = prior_log[0]
    prior_reservation = _logical_log_session(prior_entry)
    if marker == "provider-terminal":
        contract_hash = str(log.get("execution_contract_hash") or "")
        return bool(
            prior_status == "dispatched"
            and next_status in {"done", "failed", "failed_blocked"}
            and log.get("execution_started") is True
            and log.get("execution_result_kind") == next_status
            and re.fullmatch(r"[0-9a-f]{64}", contract_hash)
            and contract_hash == str(prior_entry.get("execution_contract_hash") or "")
            and str(log.get("execution_reservation_id") or "") == prior_reservation
            and prior_reservation
            and prior_entry.get("status") == "dispatched"
        )
    if marker == "stale-successor-hold":
        evidence = str(log.get("liveness_evidence") or "")
        pid = log.get("liveness_pid")
        return bool(
            prior_status == "dispatched"
            and next_status == "failed"
            and "workstream:successor-required" in labels
            and str(log.get("liveness_reservation_id") or "") == prior_reservation
            and prior_reservation
            and prior_entry.get("status") == "dispatched"
            and evidence in {"dead-process", "defunct-process", "markerless-expired", "launch-failed"}
            and isinstance(log.get("liveness_age_seconds"), (int, float))
            and not isinstance(log.get("liveness_age_seconds"), bool)
            and float(log["liveness_age_seconds"]) >= 0
            and (
                (
                    evidence in {"dead-process", "defunct-process"}
                    and isinstance(pid, int)
                    and not isinstance(pid, bool)
                    and pid > 0
                )
                or (evidence in {"markerless-expired", "launch-failed"} and pid is None)
            )
        )
    if marker == "recurrence-reopen":
        head = str(log.get("recurrence_head_sha") or "")
        predicate = str(patch.get("predicate", task.get("predicate")) or "")
        title = str(patch.get("title", task.get("title")) or "")
        return bool(
            prior_status in {"done", "archived"}
            and next_status == "open"
            and log.get("recurrence_source") == "main-green"
            and re.fullmatch(r"[0-9a-f]{40}", head)
            and str(task.get("id") or "").startswith("HEAL-mainred-")
            and {"ci", "mainred"}.issubset(labels)
            and head in predicate
            and head[:8] in title
        )
    return False


def _project_local_task_event(board: LimenFile, event: dict[str, Any]) -> tuple[LimenFile, dict[str, Any]]:
    """Apply the keeper event in memory; serialization happens only after broker commit."""

    data = board.model_dump(mode="json", exclude_none=True)
    tasks = data.setdefault("tasks", [])
    intent = dict(event.get("intent") or {})
    kind = str(intent.get("kind") or "")
    task_id = str(intent.get("task_id") or event.get("task_id") or "")
    if not task_id:
        raise ValueError("compatibility event requires task_id")
    existing = next((task for task in tasks if task.get("id") == task_id), None)
    event_id = str(event["event_id"])
    if existing and any(entry.get("conduct_event_id") == event_id for entry in (existing.get("dispatch_log") or [])):
        return board, {
            "status": "duplicate",
            "mode": "local-sqlite",
            "task": dict(existing),
            "event_id": event_id,
        }

    if kind == "task.upsert":
        if intent.get("expected_absent") and existing:
            raise ValueError(f"task {task_id} already exists")
        supplied = dict(intent.get("task") or {})
        if supplied.get("id") != task_id:
            raise ValueError(f"task projection id {supplied.get('id')} does not match {task_id}")
        task = dict(supplied)
        is_new = existing is None
        if existing:
            if supplied.get("status") != existing.get("status"):
                raise ValueError(f"task {task_id} upsert cannot change lifecycle status; submit task.status")
            history = list(existing.get("dispatch_log") or [])
            created = existing.get("created")
            task = {**existing, **{key: value for key, value in supplied.items() if key in _PATCHABLE_TASK_FIELDS}}
            task["dispatch_log"] = history
            if created is not None:
                task["created"] = created
        else:
            tasks.append(task)
        task["updated"] = str(event["timestamp"])
        task.setdefault("dispatch_log", [])
        task["dispatch_log"].append(
            _local_conduct_log(
                event,
                str(task.get("status") or "open"),
                f"Created by {event['agent']} through the conduct keeper",
            )
        )
        validated = Task.model_validate(task)
        validate_intake_contract(validated, is_new=is_new)
    else:
        if kind not in {"task.status", "task.claim", "task.mutate"}:
            raise ValueError(f"unsupported task compatibility intent: {kind}")
        if existing is None:
            raise ValueError(f"task {task_id} not found in canonical board")
        if "expected_revision" in intent and str(intent["expected_revision"]) != _canonical_revision(existing):
            raise ValueError(f"task {task_id} exact revision moved")
        expected = intent.get("expected_status")
        expected_statuses = expected if isinstance(expected, list) else [expected]
        if existing.get("status") not in expected_statuses:
            raise ValueError(
                f"task {task_id} is {existing.get('status')}; "
                f"compatibility event requires {' or '.join(map(str, expected_statuses))}"
            )
        patch = dict(intent.get("patch") or {})
        forbidden = sorted(set(patch) - _PATCHABLE_TASK_FIELDS)
        if forbidden:
            raise ValueError(
                f"task {task_id} compatibility patch contains server-owned or unsupported fields: "
                f"{', '.join(forbidden)}"
            )
        if kind == "task.status" and "status" not in patch:
            raise ValueError(f"task {task_id} status intent requires a status patch")
        prior_status = str(existing.get("status") or "")
        next_status = str(patch.get("status") or prior_status)
        log = dict(intent.get("log") or {})
        recovery = _held_jules_landing_recovery(existing, next_status, log)
        repair = kind == "task.status" and _lifecycle_repair_authorized(existing, next_status, log, patch)
        if not recovery and not repair:
            if kind == "task.claim" and (prior_status != "open" or next_status != "dispatched"):
                raise ValueError(f"task {task_id} claim requires open -> dispatched")
            if next_status not in _CANONICAL_TRANSITIONS.get(prior_status, frozenset()):
                raise ValueError(f"task {task_id} cannot transition from {prior_status} to {next_status}")
        if kind == "task.claim":
            _local_budget_debit(data, existing, event, patch)
        if kind == "task.status" and prior_status == "dispatched" and next_status == "open":
            _local_budget_refund(data, existing, event)
        existing.update(patch)
        existing["updated"] = str(event["timestamp"])
        existing.setdefault("dispatch_log", [])
        existing["dispatch_log"].append(
            _local_conduct_log(
                event,
                str(existing.get("status") or ""),
                str(log.get("session_id") or f"{kind} applied through the conduct keeper"),
            )
        )
        Task.model_validate(existing)
        task = existing

    projected = LimenFile.model_validate(data)
    canonical = next(item for item in projected.tasks if item.id == task_id).model_dump(mode="json", exclude_none=True)
    return projected, {
        "status": "committed",
        "mode": "local-sqlite",
        "task": canonical,
        "event_id": event_id,
    }


def _materialize_local_result(
    board_path: Path,
    ticket: Ticket,
    result: dict[str, Any],
    *,
    conduct_state: Path,
) -> dict[str, Any]:
    receipts = result.get("projection_receipts")
    receipt = receipts[-1] if isinstance(receipts, list) and receipts else None
    if not isinstance(receipt, dict) or not isinstance(receipt.get("task"), dict):
        raise RuntimeError(
            f"local conduct broker did not acknowledge canonical projection for {ticket.task_id}; "
            f"status={result.get('status')}"
        )
    projection = result.get("board_projection")
    if not isinstance(projection, dict):
        raise RuntimeError("local conduct broker returned no full canonical board projection")
    board = LimenFile.model_validate(projection)
    canonical = next(
        (task.model_dump(mode="json", exclude_none=True) for task in board.tasks if task.id == str(ticket.task_id)),
        None,
    )
    if canonical is None:
        raise RuntimeError(f"local conduct board projection omitted task {ticket.task_id}")
    try:
        save_local_conduct_projection(board_path, board, conduct_state=conduct_state)
    except OSError as exc:
        raise BrokerUnavailable(f"local conduct projection cache refresh failed: {exc}") from exc
    return canonical


def _submit_compatibility_ticket(
    ticket: Ticket,
    intent: dict[str, Any],
    remote: Any,
    work_id: str,
    *,
    board_path: Path | None = None,
    local_board: LimenFile | None = None,
) -> dict[str, Any]:
    identity = AgentIdentityV1(
        agent=_safe_identifier(ticket.agent, "tabularius-relay"),
        surface="tabularius-relay",
        session_id=_safe_identifier(
            f"{ticket.agent}-{ticket.session_id}",
            "tabularius-relay-session",
        ),
        provider_identity="limen-cli",
    )
    registration_now = datetime.now(timezone.utc)
    session = ConductorSessionV1(
        session_id=identity.session_id,
        identity=identity,
        origin="relay",
        capabilities=frozenset({"task-submit"}),
        transport="ianva",
        harvest_method="receipt",
        registered_at=registration_now,
        heartbeat_at=registration_now,
    )
    owner = os.environ.get("LIMEN_GITHUB_REPO", "").strip() or "organvm/limen"
    execution = {"adapter": "tabularius", "projection": "tasks.yaml", "observed_heads": {}}
    work_key = f"task-compat-{canonical_hash({'intent': intent, 'execution': execution})}"
    packet = WorkPacketV1(
        work_id=work_id,
        work_key=work_key,
        intent=intent,
        execution=execution,
        initiator=identity,
        conductor=identity,
        preferred_agent="tabularius",
        required_capabilities=frozenset({"board-write"}),
        resource_claims=(ResourceClaimV1(key=f"task/{ticket.task_id}", mode="exclusive"),),
        predicate="python3 scripts/validate-task-board.py --tasks tasks.yaml",
        receipt_target=f"git:{owner}:tasks.yaml#{ticket.task_id}",
        authority=AuthorityEnvelopeV1(
            actions=frozenset({str(intent["kind"])}),
            repositories=frozenset({owner}),
            path_prefixes=frozenset({"tasks.yaml"}),
            may_delegate=False,
        ),
        deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
        spend=SpendEnvelopeV1(limit=0),
        retry=RetryPolicyV1(max_attempts=1, transient_only=True),
        fanout=FanoutBoundsV1(max_children=0, max_depth=0),
        effect="write",
        task_id=ticket.task_id,
    )
    remote.register(session)

    if isinstance(remote, LocalConductClient):
        if board_path is None or local_board is None:
            raise RuntimeError("local conduct submission lost its temporary projection")

        def project_local(event: dict[str, Any]) -> dict[str, Any]:
            stored_projection = event.get("board_projection")
            current = (
                LimenFile.model_validate(stored_projection) if isinstance(stored_projection, dict) else local_board
            )
            projected_board, receipt = _project_local_task_event(current, event)
            receipt["board_projection"] = projected_board.model_dump(mode="json", exclude_none=True)
            return receipt

        result = remote.submit_projection(packet, project_local)
        return _materialize_local_result(board_path, ticket, result, conduct_state=remote.path)

    result = remote.submit(packet)
    receipts = result.get("projection_receipts")
    receipt = receipts[-1] if isinstance(receipts, list) and receipts else None
    projected = receipt.get("task") if isinstance(receipt, dict) else None
    if not isinstance(projected, dict):
        raise RuntimeError(
            f"conduct broker did not acknowledge canonical projection for {ticket.task_id}; "
            f"status={result.get('status')}"
        )
    return projected


def _relay_ticket(
    ticket: Ticket,
    base: dict[str, Any] | None,
    *,
    client=None,
    board_path: Path | None = None,
) -> dict[str, Any]:
    remote = client or client_from_env()
    # Bind replay identity to the entire immutable ticket, not its display ID.
    # Sanitizing/truncating ticket_id alone can collide, and an ID reused with
    # different intent must never receive an unrelated stored projection.
    work_id = f"ticket-{canonical_hash(ticket.model_dump(mode='json'))}"
    if isinstance(remote, LocalConductClient):
        if board_path is None:
            raise RuntimeError("local conduct projection requires an explicit temporary board path")
        with local_conduct_projection_lock(remote.path) as locked:
            if not locked:
                raise BrokerUnavailable("local conduct projection lock is held")
            replay = remote.replay_projection(work_id)
            if replay is not None:
                return _materialize_local_result(board_path, ticket, replay, conduct_state=remote.path)
            stored_projection = remote.local_board_projection()
            local_board = (
                LimenFile.model_validate(stored_projection)
                if isinstance(stored_projection, dict)
                else load_limen_file(board_path)
            )
            local_base = next(
                (
                    task.model_dump(mode="json", exclude_none=True)
                    for task in local_board.tasks
                    if task.id == str(ticket.task_id)
                ),
                None,
            )
            intent = _compatibility_intent(ticket, local_base)
            return _submit_compatibility_ticket(
                ticket,
                intent,
                remote,
                work_id,
                board_path=board_path,
                local_board=local_board,
            )
    intent = _compatibility_intent(ticket, base)
    return _submit_compatibility_ticket(ticket, intent, remote, work_id)


def apply_limen_file_sync(
    board_path: Path,
    limen: LimenFile,
    *,
    agent: str,
    session_id: str = "unknown",
    allow_shrink: bool = False,
    before: LimenFile | None = None,
    now: datetime | None = None,
) -> DrainResult:
    """Submit a legacy in-memory delta to the authenticated conduct keeper.

    ``tasks.yaml`` is only a hot local projection. This compatibility seam
    derives bounded per-task packets and waits for remote projection receipts;
    it never writes, commits, pushes, or refreshes the local file. Unsupported
    board metadata, ordering, removal, or field mutations fail closed.
    """

    board_path = Path(board_path)
    del allow_shrink
    previous = before
    if previous is None and board_path.exists():
        previous = load_limen_file(board_path)
    events = diff_boards(previous, limen)
    if not events:
        return DrainResult(note="no board change")

    timestamp = now or datetime.now(timezone.utc)
    previous_data = (
        previous.model_dump(mode="json", exclude_none=True)
        if previous is not None
        else {"version": "1.0", "portal": None, "tasks": []}
    )
    desired_data = limen.model_dump(mode="json", exclude_none=True)
    prior_portal = dict(previous_data.get("portal") or {})
    desired_portal = dict(desired_data.get("portal") or {})
    for portal in (prior_portal, desired_portal):
        budget = portal.get("budget")
        if isinstance(budget, dict):
            budget = dict(budget)
            budget.pop("track", None)
            portal["budget"] = budget
    if prior_portal != desired_portal or previous_data.get("version") != desired_data.get("version"):
        raise RuntimeError("board metadata mutation has no authenticated remote compatibility transition")

    prior_by_id = {str(task["id"]): task for task in previous_data.get("tasks", [])}
    tickets = []
    for event in events:
        event_type = str(event.get("type") or "")
        if event_type == EV_BOARD_META:
            continue
        if event_type in {EV_BOARD_ORDER, EV_TASK_REMOVE}:
            raise RuntimeError(f"{event_type} has no authenticated remote compatibility transition")
        ticket = _ticket_from_event(event, agent=agent, session_id=session_id, now=timestamp)
        if event_type == EV_TASK_UPSERT:
            task_id = str(event["task_id"])
            prior = prior_by_id.get(task_id)
            desired = dict(event.get("data") or {})
            ticket = ticket.model_copy(
                update={
                    "precondition": (
                        {"task_sha256": task_state_sha256(prior)} if prior is not None else {"absent": True}
                    )
                }
            )
            if prior is not None:
                prior_log = list(prior.get("dispatch_log") or [])
                desired_log = list(desired.get("dispatch_log") or [])
                if desired_log != prior_log:
                    if len(desired_log) != len(prior_log) + 1 or desired_log[:-1] != prior_log:
                        raise RuntimeError(
                            f"task {task_id} compatibility transition must append exactly one dispatch receipt"
                        )
                    ticket = ticket.model_copy(update={"log": dict(desired_log[-1])})
        tickets.append(ticket)
    if not tickets:
        return DrainResult(note="no task transition; budget-window metadata is derived by the remote keeper")
    remote = client_from_env()
    projected_tasks: dict[str, dict[str, Any]] = {}
    for ticket in tickets:
        task = _relay_ticket(
            ticket,
            prior_by_id.get(str(ticket.task_id)),
            client=remote,
            board_path=board_path,
        )
        prior_by_id[str(ticket.task_id)] = task
        projected_tasks[str(ticket.task_id)] = task
    return DrainResult(
        pending=len(tickets),
        applied=len(tickets),
        wrote=isinstance(remote, LocalConductClient),
        note="broker-committed",
        applied_ids=[ticket.ticket_id for ticket in tickets],
        projected_tasks=projected_tasks,
    )


def restore_limen_projection_text(
    board_path: Path,
    text: str,
    *,
    agent: str,
    session_id: str,
    now: datetime | None = None,
) -> DrainResult:
    """Reject local cache replacement; refetch the canonical remote projection."""

    del board_path, text, agent, session_id, now
    raise RuntimeError(
        "local tasks.yaml recovery is retired; refetch the GitHub-backed projection "
        "through the authenticated conduct owner"
    )


def preserve_board_projection(
    board_path: Path,
    *,
    branch: str = "main",
    remote: str = "origin",
    publication_branch: str = BOARD_PUBLICATION_BRANCH,
    manage_pr: bool = True,
    dry_run: bool = False,
    lock_timeout: int = 2,
) -> PreserveResult:
    """Retired local Git bridge.

    The authenticated remote projection performs GitHub SHA compare-and-swap before acknowledging
    a transition. A local process must never commit, push, reset, or advance the canonical board.
    """

    del board_path, branch, remote, manage_pr, dry_run, lock_timeout
    return PreserveResult(
        skipped=True,
        reason="remote-keeper-owns-projection",
        branch=publication_branch,
    )


def board_publication_preflight(
    board_path: Path,
    *,
    branch: str = "main",
    remote: str = "origin",
    publication_branch: str = BOARD_PUBLICATION_BRANCH,
) -> PreserveResult:
    """Fail closed rather than revive the retired local publication writer."""

    del board_path, branch, remote
    return PreserveResult(
        skipped=True,
        reason="remote-keeper-preflight-required",
        branch=publication_branch,
    )


def _parse_pending(inbox: Path) -> tuple[list[tuple[Path, Ticket]], list[tuple[Path, str]]]:
    """Load every inbox ticket, splitting parseable from garbage, then order the good ones by
    (timestamp, id) so concurrent submissions replay in a single deterministic total order."""
    good: list[tuple[Path, Ticket]] = []
    bad: list[tuple[Path, str]] = []
    for p in sorted(inbox.glob("*.json")):
        try:
            good.append((p, Ticket.model_validate_json(p.read_text())))
        except Exception as exc:  # a torn/invalid ticket is quarantined, never fatal
            bad.append((p, f"unparseable/invalid ticket: {exc}"))
    good.sort(key=lambda pt: (pt[1].timestamp, pt[1].ticket_id))
    return good, bad


def _admit_exact_preconditions(
    pending: list[tuple[Path, Ticket]],
) -> tuple[list[tuple[Path, Ticket]], list[tuple[Path, str]]]:
    """Reject exact-state tickets that conflict anywhere in the captured batch.

    Sequential optimistic checks are insufficient: an archive ticket at T can
    satisfy its precondition and then a same-task claim at T+1 can reopen it in
    the same keeper drain.  Admission therefore inspects the entire
    lock-captured batch before folding any task.  Any other pending state event
    for the same task invalidates a ``task_sha256`` precondition regardless of
    timestamp order.  Only the guarded ticket is rejected; unrelated tickets
    and the conflicting owner event retain their normal append-only custody.
    """

    task_mutations = {INTENT_UPSERT, INTENT_STATUS, INTENT_REMOVE}
    by_task: dict[str, list[tuple[Path, Ticket]]] = {}
    for path, ticket in pending:
        if ticket.task_id and ticket.intent in task_mutations:
            by_task.setdefault(ticket.task_id, []).append((path, ticket))

    rejected: list[tuple[Path, str]] = []
    rejected_paths: set[Path] = set()
    for path, ticket in pending:
        if not ticket.task_id or "task_sha256" not in (ticket.precondition or {}):
            continue
        peers = [(peer_path, peer) for peer_path, peer in by_task.get(ticket.task_id, []) if peer_path != path]
        if not peers:
            continue
        peer_ids = sorted(peer.ticket_id for _, peer in peers)
        rejected_paths.add(path)
        rejected.append(
            (
                path,
                f"batch precondition failed: {ticket.task_id} has {len(peers)} other pending state event(s) "
                f"{peer_ids}; exact task state is invalidated regardless of timestamp order",
            )
        )
    return [(path, ticket) for path, ticket in pending if path not in rejected_paths], rejected


def _apply(ticket: Ticket, tasks: OrderedDict[str, dict[str, Any]], meta: dict[str, Any]) -> None:
    """Fold one ticket onto the in-memory board state (mutates `tasks`/`meta` in place).

    Validates the resulting single task so a malformed ticket raises HERE and is quarantined alone,
    rather than failing the whole-board validation at seal time and taking good tickets down with it.
    """
    if ticket.intent == INTENT_REMOVE:
        if not ticket.task_id:
            raise ValueError("task.remove requires task_id")
        existing = tasks.get(ticket.task_id)
        if (
            existing
            and WORKSTREAM_SUCCESSOR_REQUIRED_LABEL in (existing.get("labels") or [])
            and existing.get("status") != "archived"
        ):
            raise ValueError(f"successor-required task {ticket.task_id} cannot be removed before explicit archival")
        tasks.pop(ticket.task_id, None)
        return

    if ticket.intent in (INTENT_UPSERT, INTENT_STATUS):
        if not ticket.task_id:
            raise ValueError(f"{ticket.intent} requires task_id")
        is_new = ticket.task_id not in tasks
        base = dict(tasks.get(ticket.task_id, {}))
        precondition = ticket.precondition or {}
        unknown_preconditions = set(precondition) - {"absent", "status", "task_sha256"}
        if unknown_preconditions:
            raise ValueError(f"unknown task preconditions: {sorted(unknown_preconditions)}")
        if precondition.get("absent") is True and not is_new:
            raise ValueError(f"task precondition failed: {ticket.task_id} is no longer absent")
        if "task_sha256" in precondition:
            if is_new:
                raise ValueError(f"task precondition failed: {ticket.task_id} is absent")
            actual_hash = task_state_sha256(base)
            if actual_hash != precondition["task_sha256"]:
                raise ValueError(
                    f"task precondition failed: {ticket.task_id} exact state changed "
                    f"({actual_hash[:12]} != {str(precondition['task_sha256'])[:12]})"
                )
        if "status" in precondition and base.get("status") != precondition["status"]:
            raise ValueError(
                f"task precondition failed: {ticket.task_id} status is {base.get('status')!r}, "
                f"expected {precondition['status']!r}"
            )
        merged = {**base, **(ticket.patch or {})}
        merged["id"] = ticket.task_id
        merged["updated"] = ticket.timestamp.isoformat()
        if ticket.log:
            status = ticket.log.get("status") or merged.get("status")
            entry = {
                "timestamp": ticket.timestamp.isoformat(),
                "agent": ticket.agent,
                "session_id": ticket.session_id,
                "status": status,
                "output": ticket.log.get("output"),
            }
            merged["dispatch_log"] = list(base.get("dispatch_log", [])) + [entry]
            # a task.status ticket carries the transition in its log payload; honor it as the status
            if ticket.intent == INTENT_STATUS and "status" not in (ticket.patch or {}) and status:
                merged["status"] = status
        if not is_new and WORKSTREAM_SUCCESSOR_REQUIRED_LABEL in (base.get("labels") or []):
            next_status = str(merged.get("status") or "")
            if next_status not in {"failed", "done", "archived"}:
                raise ValueError(
                    f"successor-required task {ticket.task_id} is terminal; create a new successor task "
                    f"instead of transitioning it to {next_status!r}"
                )
            if WORKSTREAM_SUCCESSOR_REQUIRED_LABEL not in (merged.get("labels") or []):
                raise ValueError(f"successor-required task {ticket.task_id} cannot drop its terminal hold label")
        validated = Task.model_validate(merged)  # reject a bad ticket individually
        # A caller can bypass ``submit_task_upsert`` by constructing a raw Ticket.
        # The keeper repeats admission independently so that ticket is quarantined
        # alone while valid siblings still land.
        validate_intake_contract(validated, is_new=is_new)
        tasks[ticket.task_id] = merged  # dict update keeps first-seen position; new id appends
        return

    if ticket.intent == INTENT_META:
        p = ticket.patch or {}
        candidate = dict(meta)
        if "version" in p:
            candidate["version"] = p["version"]
        if "portal" in p:
            if p["portal"] is not None and not isinstance(p["portal"], dict):
                raise ValueError("board.meta portal must be a mapping")
            candidate["portal"] = p["portal"]
        LimenFile.model_validate(
            {
                "version": candidate.get("version", "1.0"),
                "portal": candidate.get("portal"),
                "tasks": list(tasks.values()),
            }
        )
        meta.clear()
        meta.update(candidate)
        return

    if ticket.intent == INTENT_ORDER:
        ids = (ticket.patch or {}).get("ids", [])
        if not isinstance(ids, list) or any(not isinstance(tid, str) for tid in ids):
            raise ValueError("board.order ids must be a list of task id strings")
        meta["order"] = list(ids)
        return

    raise ValueError(f"unknown ticket intent: {ticket.intent!r}")


def _move(paths: list[Path], dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for p in paths:
        try:
            p.rename(dest_dir / p.name)
        except OSError:
            pass


def _quarantine(rejected: list[tuple[Path, str]], dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for p, reason in rejected:
        try:
            (dest_dir / f"{p.name}.reason.txt").write_text(reason)
            p.rename(dest_dir / p.name)
        except OSError:
            pass


def drain_once(board_path: Path, *, dry_run: bool = False, lock_timeout: int = 20) -> DrainResult:
    """Relay one inbox snapshot to the authenticated keeper.

    The queue lock serializes only local ticket custody. ``tasks.yaml`` is read as an optimistic
    cache and remains byte-identical. A ticket moves to ``archive`` only after a projection receipt
    names the canonical task. Invalid tickets are quarantined; broker unavailability leaves the
    current ticket and every unattempted suffix in the inbox for an idempotent retry.
    """
    board_path = Path(board_path)
    inbox = _inbox(board_path)
    if not inbox.is_dir():
        return DrainResult(note="inbox empty")

    pending_hint = len(list(inbox.glob("*.json")))
    if pending_hint == 0:
        return DrainResult(note="inbox empty")

    if dry_run:
        good, bad = _parse_pending(inbox)
        admitted, precondition_rejections = _admit_exact_preconditions(good)
        dry_tasks: dict[str, dict[str, Any]] = {}
        if board_path.exists():
            board = load_limen_file(board_path)
            dry_tasks = {task.id: task.model_dump(mode="json", exclude_none=True) for task in board.tasks}
        applicable: list[tuple[Path, Ticket]] = []
        dry_rejected: list[tuple[Path, str]] = [*bad, *precondition_rejections]
        for path, ticket in admitted:
            try:
                intent = _compatibility_intent(ticket, dry_tasks.get(str(ticket.task_id)))
                if intent["kind"] == "task.upsert":
                    dry_tasks[str(ticket.task_id)] = dict(intent["task"])
                else:
                    dry_tasks[str(ticket.task_id)] = {
                        **dry_tasks[str(ticket.task_id)],
                        **dict(intent.get("patch") or {}),
                    }
                applicable.append((path, ticket))
            except Exception as exc:
                dry_rejected.append((path, f"compatibility validation failed: {exc}"))
        pending = len(good) + len(bad)
        return DrainResult(
            pending=pending,
            applied=len(applicable),
            rejected=len(dry_rejected),
            note=(f"dry-run: {len(applicable)} broker-compatible, {len(dry_rejected)} invalid/conflicting"),
            applied_ids=[ticket.ticket_id for _, ticket in applicable],
            rejected_ids=[path.stem for path, _ in dry_rejected],
        )

    with queue_lock(board_path, timeout=lock_timeout) as locked:
        if not locked:
            return DrainResult(pending=pending_hint, deferred=True, note="queue lock held; deferred to next beat")

        # Parse only after taking the same lock used by phase publishers.  A
        # keeper can therefore observe either the complete published phase or
        # none of it, never an in-flight prefix captured before the lock.
        good, bad = _parse_pending(inbox)
        pending = len(good) + len(bad)
        if pending == 0:
            return DrainResult(note="inbox empty")

        tasks: dict[str, dict[str, Any]] = {}
        if board_path.exists():
            board = load_limen_file(board_path)
            tasks = {task.id: task.model_dump(mode="json", exclude_none=True) for task in board.tasks}
        applied: list[tuple[Path, Ticket]] = []
        admitted, precondition_rejections = _admit_exact_preconditions(good)
        rejected: list[tuple[Path, str]] = [*bad, *precondition_rejections]
        try:
            remote = client_from_env()
        except BrokerUnavailable as exc:
            _quarantine(rejected, _rejected(board_path))
            return DrainResult(
                pending=pending,
                rejected=len(rejected),
                deferred=True,
                note=f"conduct broker unavailable; valid tickets remain pending: {exc}",
                rejected_ids=[path.stem for path, _ in rejected],
            )

        deferred_reason = ""
        for path, ticket in admitted:
            try:
                projected = _relay_ticket(
                    ticket,
                    tasks.get(str(ticket.task_id)),
                    client=remote,
                    board_path=board_path,
                )
                tasks[str(ticket.task_id)] = projected
                applied.append((path, ticket))
            except BrokerUnavailable as exc:
                deferred_reason = str(exc)
                break
            except (ConductError, RuntimeError, ValueError) as exc:
                rejected.append((path, f"broker rejected compatibility ticket: {exc}"))
            except Exception as exc:
                rejected.append((path, f"unexpected compatibility relay failure: {exc}"))

        _move([p for p, _ in applied], _archive(board_path))
        _quarantine(rejected, _rejected(board_path))

    return DrainResult(
        pending=pending,
        applied=len(applied),
        rejected=len(rejected),
        wrote=isinstance(remote, LocalConductClient),
        deferred=bool(deferred_reason),
        note=(
            f"conduct broker unavailable after {len(applied)} acknowledgment(s); unacknowledged tickets remain pending"
            if deferred_reason
            else ("broker-committed" if applied else "no remote projection")
        ),
        applied_ids=[t.ticket_id for _, t in applied],
        rejected_ids=[p.stem for p, _ in rejected],
    )
