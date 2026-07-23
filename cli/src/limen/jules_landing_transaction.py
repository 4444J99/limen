"""Crash-resumable task-board transaction for Jules landing.

This module owns durable intent, compare-and-swap validation, retry receipts,
and terminal board state. External Git/worktree/PR mutation belongs to
:mod:`limen.jules_landing_custody`.
"""

from __future__ import annotations

import datetime
import fcntl
import hashlib
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from limen.io import load_limen_file, queue_lock
from limen.jules_landing_custody import land_one, landed_pr_url, landing_branch
from limen.models import (
    JULES_LANDING_HOLD_LABEL,
    DispatchLogEntry,
    Task,
    dispatch_agent,
    dispatch_session_id,
    has_jules_landing_hold,
)
from limen.tabularius import apply_limen_file_sync, task_state_sha256

LANDING_LOCK_TIMEOUT_SECONDS = 2.0
LANDING_LOCK_POLL_SECONDS = 0.05
LANDING_RETRY_LIMIT = 3

LandingOperation = Callable[..., str]


@dataclass(frozen=True)
class LandingSelection:
    """Exact durable landing intent selected before external PR work begins."""

    task_id: str
    session_id: str
    task_state_sha256: str
    intent_token: str
    branch: str
    attempt_count: int


@dataclass(frozen=True)
class LandingPlan:
    """Board snapshot and exact intent token passed to external custody."""

    task: Task
    selection: LandingSelection


def _submit_landing_projection(
    tasks_path: Path,
    before_task: Task,
    desired_task: Task,
    *,
    session_id: str,
) -> Task:
    """Submit one task delta and require its canonical projected task receipt."""

    cached = load_limen_file(tasks_path)
    index = next(
        (position for position, task in enumerate(cached.tasks) if task.id == before_task.id),
        None,
    )
    if index is None:
        raise RuntimeError(f"task {before_task.id} is absent from the local projection")
    before = cached.model_copy(deep=True)
    before.tasks[index] = before_task.model_copy(deep=True)
    desired = before.model_copy(deep=True)
    desired.tasks[index] = desired_task.model_copy(deep=True)
    result = apply_limen_file_sync(
        tasks_path,
        desired,
        agent="jules",
        session_id=session_id,
        before=before,
    )
    projected = result.projected_tasks.get(before_task.id)
    if result.applied != 1 or not isinstance(projected, dict):
        raise RuntimeError(f"conduct keeper omitted the canonical projected task receipt for {before_task.id}")
    acknowledged = Task.model_validate(projected)
    if acknowledged.id != before_task.id:
        raise RuntimeError(f"conduct keeper projected {acknowledged.id}, expected {before_task.id}")
    return acknowledged


def _advance_landing_execution(
    tasks_path: Path,
    task: Task,
    selection: LandingSelection,
) -> Task:
    """Honor dispatched -> in_progress before a terminal landing transition."""

    if task.status != "dispatched":
        return task
    desired = task.model_copy(deep=True)
    now = datetime.datetime.now(datetime.UTC)
    desired.status = "in_progress"
    desired.updated = now
    desired.dispatch_log.append(
        DispatchLogEntry(
            timestamp=now,
            agent="jules",
            session_id=f"jules-land-active:{selection.intent_token[:16]}",
            status="in_progress",
            output=f"jules-land: external custody completed for session {selection.session_id}",
        )
    )
    return _submit_landing_projection(
        tasks_path,
        task,
        desired,
        session_id=f"jules-land-active-{selection.intent_token[:16]}",
    )


def _landing_intent_token(
    task_id: str,
    session_id: str,
    claim_sha256: str,
) -> str:
    raw = f"{task_id}\0{session_id}\0{claim_sha256}".encode()
    return hashlib.sha256(raw).hexdigest()


@contextmanager
def landing_lock(
    tasks_path: Path,
    task_id: str,
    session_id: str,
    *,
    timeout_seconds: float = LANDING_LOCK_TIMEOUT_SECONDS,
) -> Iterator[bool]:
    """Hold one finite process-level lease across select, custody, and commit."""
    lock_root = tasks_path.parent / "logs" / "jules-land-locks"
    lock_root.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha256(f"{task_id}\0{session_id}".encode()).hexdigest()
    with (lock_root / f"{name}.lock").open("a+", encoding="utf-8") as handle:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        got = False
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                got = True
                break
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(LANDING_LOCK_POLL_SECONDS, remaining))
        try:
            yield got
        finally:
            if got:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def session_has_pr(task: Task, session_id: str) -> bool:
    """Return whether this exact Jules session owns a durable PR receipt."""
    entries = list(task.dispatch_log or [])
    dispatch_index = max(
        (index for index, entry in enumerate(entries) if dispatch_session_id(entry) == str(session_id)),
        default=None,
    )
    next_dispatch_index = (
        min(
            (
                index
                for index, entry in enumerate(entries)
                if dispatch_index is not None and index > dispatch_index and dispatch_session_id(entry).isdigit()
            ),
            default=len(entries),
        )
        if dispatch_index is not None
        else None
    )
    named_session = re.compile(r"\bsession\s+([0-9]+)\b", re.IGNORECASE)
    for index, entry in enumerate(entries):
        if "/pull/" not in dispatch_session_id(entry):
            continue
        named = named_session.search(str(entry.output or ""))
        if named is not None:
            if named.group(1) == str(session_id):
                return True
            continue
        if (
            dispatch_index is not None
            and next_dispatch_index is not None
            and dispatch_index <= index < next_dispatch_index
        ):
            return True
    return False


def _jules_claim_is_current(task: Task, session_id: str) -> bool:
    numeric_claims = [
        (
            dispatch_session_id(entry),
            dispatch_agent(entry),
            str(entry.status or ""),
        )
        for entry in (task.dispatch_log or [])
        if dispatch_session_id(entry).isdigit()
    ]
    return not (
        task.target_agent not in {"jules", "any"}
        or task.status not in {"dispatched", "failed", "done"}
        or not numeric_claims
        or numeric_claims[-1][:2] != (str(session_id), "jules")
        or numeric_claims[-1][2] not in {"dispatched", "failed", "done"}
    )


def _landing_intents(
    task: Task,
    session_id: str,
) -> list[tuple[int, DispatchLogEntry]]:
    return [
        (index, entry)
        for index, entry in enumerate(task.dispatch_log or [])
        if str(getattr(entry, "landing_session_id", "")) == str(session_id)
        and str(getattr(entry, "landing_intent_token", ""))
        and str(getattr(entry, "landing_event", "")) == "intent"
    ]


def _terminal_landing_outcome(
    task: Task,
    session_id: str,
) -> DispatchLogEntry | None:
    for entry in reversed(task.dispatch_log or []):
        token = str(getattr(entry, "landing_intent_token", ""))
        if (
            str(getattr(entry, "landing_session_id", "")) == str(session_id)
            and str(getattr(entry, "landing_event", "")) == "terminal"
            and getattr(entry, "landing_terminal", False) is True
            and str(getattr(entry, "landing_branch", "")) == landing_branch(task.id, str(session_id))
            and token
            and any(
                str(getattr(intent, "landing_intent_token", "")) == token
                for _, intent in _landing_intents(task, session_id)
            )
        ):
            return entry
    return None


def _persisted_landing_selection(
    task: Task,
    session_id: str,
) -> LandingSelection | None:
    """Validate and reconstruct the exact claim behind one durable intent."""
    intents = _landing_intents(task, session_id)
    if len(intents) != 1:
        return None
    index, intent = intents[0]
    entries = list(task.dispatch_log or [])
    prior_status = str(getattr(intent, "landing_prior_status", ""))
    if (
        task.target_agent not in {"jules", "any"}
        or task.status != prior_status
        or not has_jules_landing_hold(task)
        or not _jules_claim_is_current(task, session_id)
        or intent.agent != "jules"
        or dispatch_agent(intent) != "jules"
        or intent.status != prior_status
    ):
        return None
    claim_sha256 = str(getattr(intent, "landing_claim_sha256", ""))
    token = str(getattr(intent, "landing_intent_token", ""))
    branch = str(getattr(intent, "landing_branch", ""))
    prior_updated = getattr(intent, "landing_prior_updated", None)
    if (
        len(claim_sha256) != 64
        or token != _landing_intent_token(task.id, str(session_id), claim_sha256)
        or branch != landing_branch(task.id, str(session_id))
        or dispatch_session_id(intent) != f"jules-land-intent:{token}"
        or prior_status not in {"dispatched", "failed", "done"}
    ):
        return None
    attempt_count = 0
    for entry in entries[index + 1 :]:
        attempt_count += 1
        if (
            str(getattr(entry, "landing_session_id", "")) != str(session_id)
            or str(getattr(entry, "landing_intent_token", "")) != token
            or str(getattr(entry, "landing_event", "")) != "attempt"
            or getattr(entry, "landing_terminal", False) is not False
            or getattr(entry, "landing_attempt", None) != attempt_count
            or entry.status != prior_status
        ):
            return None
    before = task.model_dump(mode="json")
    before["dispatch_log"] = before["dispatch_log"][:index]
    before["labels"] = [label for label in before.get("labels", []) if label != JULES_LANDING_HOLD_LABEL]
    before["status"] = prior_status
    before["updated"] = prior_updated
    if task_state_sha256(before) != claim_sha256:
        return None
    current_sha256 = task_state_sha256(task.model_dump(mode="json"))
    return LandingSelection(
        task_id=task.id,
        session_id=str(session_id),
        task_state_sha256=current_sha256,
        intent_token=token,
        branch=branch,
        attempt_count=attempt_count,
    )


def _new_landing_selection(
    task: Task,
    session_id: str,
) -> LandingSelection | None:
    """Capture one current Jules claim for dry-run or durable intent."""
    if not _jules_claim_is_current(task, session_id):
        return None
    claim_sha256 = task_state_sha256(task.model_dump(mode="json"))
    return LandingSelection(
        task_id=task.id,
        session_id=str(session_id),
        task_state_sha256=claim_sha256,
        intent_token=_landing_intent_token(task.id, str(session_id), claim_sha256),
        branch=landing_branch(task.id, str(session_id)),
        attempt_count=0,
    )


def _current_landing_task(
    tasks_path: Path,
    selection: LandingSelection,
) -> Task | None:
    """Reload the keeper projection and require the exact selected row."""

    fresh = load_limen_file(tasks_path)
    task = next(
        (candidate for candidate in fresh.tasks if candidate.id == selection.task_id),
        None,
    )
    if task is None or _persisted_landing_selection(task, selection.session_id) != selection:
        return None
    return task


def prepare_landing_intent(
    tasks_path: Path,
    task_id: str,
    session_id: str,
    *,
    apply: bool,
    recover: bool,
) -> tuple[LandingPlan | None, str]:
    """Fresh-select one exact claim and durably record intent before custody."""
    with queue_lock(tasks_path) as got:
        if not got:
            return None, f"FENCE {task_id}: queue busy before landing intent"
        fresh = load_limen_file(tasks_path)
        task = next(
            (candidate for candidate in fresh.tasks if candidate.id == task_id),
            None,
        )
        if task is None:
            return None, f"SKIP {task_id}: task no longer exists"
        terminal = _terminal_landing_outcome(task, session_id)
        if terminal is not None:
            outcome = str(getattr(terminal, "landing_outcome", "terminal"))
            return None, (f"SKIP {task_id}: Jules session {session_id} already has terminal landing outcome {outcome}")
        if session_has_pr(task, session_id):
            return None, (f"SKIP {task_id}: Jules session {session_id} already has a PR receipt")
        intents = _landing_intents(task, session_id)
        if intents:
            selection = _persisted_landing_selection(task, session_id)
            if selection is None:
                return None, (f"FENCE {task_id}: durable landing intent or owner changed")
            return LandingPlan(task.model_copy(deep=True), selection), (
                f"RESUME {task_id}: durable landing intent {selection.intent_token[:12]}"
            )
        if has_jules_landing_hold(task):
            return None, (f"FENCE {task_id}: another Jules landing transaction holds the row")
        if task.status == "done" and not recover:
            return None, f"SKIP {task_id}: done task requires --recover"
        selection = _new_landing_selection(task, session_id)
        if selection is None:
            return None, (f"SKIP {task_id}: Jules session {session_id} no longer owns the current task claim")
        if not apply:
            return LandingPlan(task.model_copy(deep=True), selection), ""

        before_task = task.model_copy(deep=True)
        before = before_task.model_dump(mode="json")
        now = datetime.datetime.now(datetime.UTC)
        task.labels = list(task.labels or []) + [JULES_LANDING_HOLD_LABEL]
        task.updated = now
        task.dispatch_log.append(
            DispatchLogEntry(
                timestamp=now,
                agent="jules",
                session_id=f"jules-land-intent:{selection.intent_token}",
                status=str(before["status"]),
                output=(f"jules-land: reserved session {session_id} on deterministic branch {selection.branch}"),
                landing_event="intent",
                landing_session_id=str(session_id),
                landing_branch=selection.branch,
                landing_intent_token=selection.intent_token,
                landing_claim_sha256=task_state_sha256(before),
                landing_prior_status=before["status"],
                landing_prior_updated=before["updated"],
            )
        )
        persisted_task = _submit_landing_projection(
            tasks_path,
            before_task,
            task,
            session_id=f"jules-land-intent-{selection.intent_token[:16]}",
        )
        persisted = _persisted_landing_selection(persisted_task, session_id)
        if persisted is None:
            raise RuntimeError(f"conduct keeper returned no valid landing intent for {task_id}")
        return LandingPlan(persisted_task.model_copy(deep=True), persisted), ""


def _append_terminal_outcome(
    task: Task,
    selection: LandingSelection,
    *,
    status: str,
    outcome: str,
    output: str,
    session_id: str,
    now: datetime.datetime,
    attempt_count: int | None = None,
) -> None:
    task.status = status
    task.labels = [label for label in (task.labels or []) if label != JULES_LANDING_HOLD_LABEL]
    task.updated = now
    task.dispatch_log.append(
        DispatchLogEntry(
            timestamp=now,
            agent="jules",
            session_id=session_id,
            status=status,
            output=output,
            landing_event="terminal",
            landing_terminal=True,
            landing_outcome=outcome,
            landing_session_id=selection.session_id,
            landing_branch=selection.branch,
            landing_intent_token=selection.intent_token,
            landing_attempt_count=(selection.attempt_count if attempt_count is None else attempt_count),
        )
    )


def commit_landing_receipt(
    tasks_path: Path,
    selection: LandingSelection,
    pr_url: str,
    *,
    base_task: Task,
) -> bool:
    """Commit one PR receipt iff the exact selected claim still owns the row."""
    with queue_lock(tasks_path) as got:
        if not got:
            print(f"  FENCE {selection.task_id}: queue busy after PR creation; left {pr_url} for reconciliation")
            return False
        if _persisted_landing_selection(base_task, selection.session_id) != selection:
            print(
                f"  FENCE {selection.task_id}: Jules claim changed while PR work ran; left {pr_url} for reconciliation"
            )
            return False
        task = _current_landing_task(tasks_path, selection)
        if task is None:
            print(
                f"  FENCE {selection.task_id}: Jules claim changed while PR work ran; left {pr_url} for reconciliation"
            )
            return False
        task = _advance_landing_execution(tasks_path, task, selection)
        desired = task.model_copy(deep=True)
        now = datetime.datetime.now(datetime.UTC)
        _append_terminal_outcome(
            desired,
            selection,
            status="done",
            outcome="pr",
            output=f"jules-land: landed session {selection.session_id} as PR",
            session_id=pr_url,
            now=now,
        )
        _submit_landing_projection(
            tasks_path,
            task,
            desired,
            session_id=f"jules-land-pr-{selection.intent_token[:16]}",
        )
        return True


def commit_terminal_landing_outcome(
    tasks_path: Path,
    selection: LandingSelection,
    *,
    status: str,
    outcome: str,
    output: str,
    base_task: Task,
) -> bool:
    """Commit a non-PR terminal receipt and release the landing hold."""
    with queue_lock(tasks_path) as got:
        if not got:
            print(f"  FENCE {selection.task_id}: queue busy while recording {outcome}")
            return False
        if _persisted_landing_selection(base_task, selection.session_id) != selection:
            print(f"  FENCE {selection.task_id}: owner changed while recording {outcome}")
            return False
        task = _current_landing_task(tasks_path, selection)
        if task is None:
            print(f"  FENCE {selection.task_id}: owner changed while recording {outcome}")
            return False
        task = _advance_landing_execution(tasks_path, task, selection)
        desired = task.model_copy(deep=True)
        now = datetime.datetime.now(datetime.UTC)
        _append_terminal_outcome(
            desired,
            selection,
            status=status,
            outcome=outcome,
            output=output,
            session_id=f"jules-land-{outcome}:{selection.intent_token[:16]}",
            now=now,
        )
        _submit_landing_projection(
            tasks_path,
            task,
            desired,
            session_id=f"jules-land-{outcome}-{selection.intent_token[:16]}",
        )
        return True


def commit_landing_failure(
    tasks_path: Path,
    selection: LandingSelection,
    failure: str,
    *,
    base_task: Task,
) -> str:
    """Append one bounded retry receipt, terminalizing at the finite cap."""
    with queue_lock(tasks_path) as got:
        if not got:
            print(f"  FENCE {selection.task_id}: queue busy while recording failed attempt")
            return "queue_busy"
        if _persisted_landing_selection(base_task, selection.session_id) != selection:
            print(f"  FENCE {selection.task_id}: owner changed while recording failed attempt")
            return "fenced"
        current = _current_landing_task(tasks_path, selection)
        if current is None:
            print(f"  FENCE {selection.task_id}: owner changed while recording failed attempt")
            return "fenced"
        task = current.model_copy(deep=True)
        now = datetime.datetime.now(datetime.UTC)
        attempt = selection.attempt_count + 1
        task.updated = now
        task.dispatch_log.append(
            DispatchLogEntry(
                timestamp=now,
                agent="jules",
                session_id=(f"jules-land-attempt:{selection.intent_token[:16]}:{attempt}"),
                status="failed",
                output=failure,
                landing_event="attempt",
                landing_terminal=False,
                landing_attempt=attempt,
                landing_session_id=selection.session_id,
                landing_branch=selection.branch,
                landing_intent_token=selection.intent_token,
            )
        )
        acknowledged = _submit_landing_projection(
            tasks_path,
            current,
            task,
            session_id=f"jules-land-attempt-{selection.intent_token[:16]}-{attempt}",
        )
        if attempt >= LANDING_RETRY_LIMIT:
            terminal_selection = LandingSelection(
                task_id=selection.task_id,
                session_id=selection.session_id,
                task_state_sha256=selection.task_state_sha256,
                intent_token=selection.intent_token,
                branch=selection.branch,
                attempt_count=attempt,
            )
            acknowledged = _advance_landing_execution(
                tasks_path,
                acknowledged,
                terminal_selection,
            )
            terminal = acknowledged.model_copy(deep=True)
            _append_terminal_outcome(
                terminal,
                terminal_selection,
                status="failed",
                outcome="failed",
                output=(f"jules-land: retry cap {LANDING_RETRY_LIMIT} reached; last outcome: {failure}"),
                session_id=f"jules-land-failed:{selection.intent_token[:16]}",
                now=now,
                attempt_count=attempt,
            )
            _submit_landing_projection(
                tasks_path,
                acknowledged,
                terminal,
                session_id=f"jules-land-failed-{selection.intent_token[:16]}",
            )
            result = "terminal"
        else:
            result = "retry"
        return result


def process_session(
    tasks_path: Path,
    task_id: str,
    session_id: str,
    *,
    apply: bool,
    recover: bool,
    lock_timeout_seconds: float = LANDING_LOCK_TIMEOUT_SECONDS,
    land: LandingOperation | None = None,
) -> bool:
    """Run one crash-resumable task/session landing transaction."""
    land_operation = land or land_one
    with landing_lock(
        tasks_path,
        task_id,
        session_id,
        timeout_seconds=lock_timeout_seconds,
    ) as got_lock:
        if not got_lock:
            print(f"  BUSY {task_id}: Jules landing lock timed out for session {session_id}")
            return False
        plan, note = prepare_landing_intent(
            tasks_path,
            task_id,
            session_id,
            apply=apply,
            recover=recover,
        )
        if plan is None:
            print(f"  {note}")
            return False
        if note:
            print(f"  {note}")
        message = land_operation(
            plan.task,
            session_id,
            apply,
            branch=plan.selection.branch,
        )
        print(f"  {message}")
        if not apply:
            return False
        if message.startswith("BLOCKED"):
            commit_terminal_landing_outcome(
                tasks_path,
                plan.selection,
                status="failed_blocked",
                outcome="blocked",
                output=message,
                base_task=plan.task,
            )
            return False
        if message.startswith("no-op"):
            commit_terminal_landing_outcome(
                tasks_path,
                plan.selection,
                status="failed",
                outcome="noop",
                output=message,
                base_task=plan.task,
            )
            return False
        if not message.startswith("LANDED"):
            commit_landing_failure(
                tasks_path,
                plan.selection,
                message,
                base_task=plan.task,
            )
            return False
        pr_url = landed_pr_url(message, "")
        if "/pull/" not in pr_url:
            commit_landing_failure(
                tasks_path,
                plan.selection,
                f"FAIL {task_id}: landed result had no durable PR URL",
                base_task=plan.task,
            )
            return False
        return commit_landing_receipt(
            tasks_path,
            plan.selection,
            pr_url,
            base_task=plan.task,
        )
