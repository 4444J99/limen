#!/usr/bin/env python3
"""Compile and safely submit the frozen 2026-07-12 ask-gate migration.

The default is a read-only dry run.  Application is deliberately split across
two invocations with a keeper drain between them::

    python3 scripts/apply-ask-gate-migration.py --phase children
    python3 scripts/apply-ask-gate-migration.py --phase children --apply \
      --timestamp 2026-07-12T18:00:00Z --session-id <session>
    LIMEN_TASKS=... python3 scripts/tabularius-organ.py
    python3 scripts/apply-ask-gate-migration.py --phase parents
    python3 scripts/apply-ask-gate-migration.py --phase parents --apply \
      --timestamp 2026-07-12T18:10:00Z --session-id <session>

The parent phase fails closed unless every child is present on the board with
the exact typed contract, its deterministic ticket is in the keeper archive,
and no migration child ticket remains pending or rejected.  This script never
edits ``tasks.yaml`` directly; ``--apply`` only appends immutable TABVLARIVS
tickets to its inbox.  The keeper remains the sole board writer.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.intake import validate_intake_contract  # noqa: E402
from limen.io import load_limen_file, queue_lock  # noqa: E402
from limen.models import Task  # noqa: E402
from limen.tabularius import (  # noqa: E402
    INTENT_UPSERT,
    Ticket,
    submit_ticket,
    task_state_sha256,
    tickets_root,
)


DEFAULT_RECEIPT = ROOT / "docs" / "ask-gate-migration-2026-07-12.json"
CANONICAL_CHECKER = ROOT / "scripts" / "check-ask-gate-migration.py"
DEFAULT_BOARD = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
MIGRATION_ID = "ask-gate-migration-2026-07-12"
PHASE_CHILDREN = "children"
PHASE_PARENTS = "parents"
PHASE_VERIFY = "verify"
APPLY_PHASES = (PHASE_CHILDREN, PHASE_PARENTS)
# The keeper archive seals the exact creation packet.  After admission, the
# live purpose router owns target_agent and may legitimately rebalance it.
CHILD_ROUTING_VOLATILE_FIELDS = ("updated", "dispatch_log", "target_agent")
RunPredicate = Callable[[str], subprocess.CompletedProcess[str]]


class MigrationError(RuntimeError):
    """The migration cannot advance without violating a gate."""


def _canonical_payload(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def manifest_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_payload(payload)).hexdigest()


@lru_cache(maxsize=1)
def _canonical_verifier() -> Any:
    spec = importlib.util.spec_from_file_location("check_ask_gate_migration_canonical", CANONICAL_CHECKER)
    if spec is None or spec.loader is None:
        raise MigrationError(f"cannot load canonical migration verifier: {CANONICAL_CHECKER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_canonical_payload(payload: dict[str, Any]) -> str:
    """Bind compilation to the tracked receipt and its owner verifier.

    A caller cannot mutate a predicate, phase, or manifest-derived namespace in
    memory and still compile tickets: the bytes must equal the canonical receipt
    and that receipt must pass ``check-ask-gate-migration.py`` first.
    """

    try:
        canonical = json.loads(DEFAULT_RECEIPT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationError(f"cannot read canonical migration receipt: {exc}") from exc
    if _canonical_payload(payload) != _canonical_payload(canonical):
        raise MigrationError("payload differs from the canonical verified migration receipt")
    errors = _canonical_verifier().verify_receipt(canonical)
    if errors:
        raise MigrationError(f"canonical migration receipt failed verification: {errors[0]}")
    return manifest_digest(canonical)


def parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MigrationError(f"invalid ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise MigrationError("timestamp must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def deterministic_ticket_id(payload: dict[str, Any], phase: str, task_id: str) -> str:
    seed = f"{manifest_digest(payload)}\0{phase}\0{task_id}".encode("utf-8")
    suffix = hashlib.sha256(seed).hexdigest()[:24]
    return f"{MIGRATION_ID}-{phase}-{suffix}"


def _default_predicate_runner(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-lc", command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


_TASK_PR_RECEIPT_RE = re.compile(
    r"^github:(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+):pull-request:(?P<task>[A-Za-z0-9_.-]+)$"
)


def task_pr_body_pattern(task_id: str) -> str:
    return rf"(^|[^A-Za-z0-9_.-]){re.escape(task_id)}([^A-Za-z0-9_.-]|$)"


def effective_parent_predicate(task_id: str, row: dict[str, Any]) -> str:
    """Compile exact task-keyed PR custody without changing the frozen manifest digest."""

    predicate = str(row.get("predicate") or "").strip()
    receipt_target = str(row.get("receipt_target") or "")
    match = _TASK_PR_RECEIPT_RE.fullmatch(receipt_target)
    if match is None:
        return predicate
    if match.group("task") != task_id:
        raise MigrationError(f"parent {task_id!r} task-keyed PR receipt names a different task")
    repo = match.group("repo")
    jq_filter = f'([.[] | select((.body // "") | test({json.dumps(task_pr_body_pattern(task_id))}))] | length)'
    exact_search = shlex.join(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "merged",
            "--search",
            f"{task_id} in:body",
            "--json",
            "body",
            "--jq",
            jq_filter,
        ]
    )
    exact_receipt = f'test "$({exact_search})" -gt 0'
    if "scripts/ship-gate.py --check" in predicate:
        ship_gate = shlex.join(["python3", "scripts/ship-gate.py", "--check", "--task", task_id])
        return f"{ship_gate} && {exact_receipt}"
    if "gh api" in predicate and "gh run list" in predicate:
        workflow_match = re.search(r"--workflow\s+([A-Za-z0-9_.-]+)", predicate)
        if workflow_match is None:
            raise MigrationError(f"parent {task_id!r} main-green predicate has no bounded workflow")
        main_head = shlex.join(["gh", "api", f"repos/{repo}/commits/main", "--jq", ".sha"])
        green_head = shlex.join(
            [
                "gh",
                "run",
                "list",
                "--repo",
                repo,
                "--workflow",
                workflow_match.group(1),
                "--branch",
                "main",
                "--event",
                "push",
                "--status",
                "success",
                "--limit",
                "1",
                "--json",
                "headSha",
                "--jq",
                ".[0].headSha",
            ]
        )
        return f'{exact_receipt} && test "$({main_head})" = "$({green_head})"'
    if "bash -lc" in predicate or "&&" in predicate or "||" in predicate:
        raise MigrationError(f"parent {task_id!r} has an unrecognized compound task-PR predicate")
    return exact_receipt


def check_live_prerequisites(
    payload: dict[str, Any],
    *,
    runner: RunPredicate = _default_predicate_runner,
) -> list[str]:
    """Execute every declared prerequisite and fail on the first non-merged gate."""

    verify_canonical_payload(payload)
    checked: list[str] = []
    prerequisites = payload.get("prerequisites")
    if not isinstance(prerequisites, dict) or not prerequisites:
        raise MigrationError("manifest has no executable prerequisites")
    order = (payload.get("application_contract") or {}).get("live_prerequisites")
    if not isinstance(order, list) or set(order) != set(prerequisites):
        raise MigrationError("application prerequisite order does not cover the declared gates")
    for name in order:
        row = prerequisites[name]
        if not isinstance(row, dict) or row.get("required_state") != "MERGED":
            raise MigrationError(f"prerequisite {name!r} is not a MERGED gate")
        predicate = str(row.get("predicate") or "").strip()
        if not predicate:
            raise MigrationError(f"prerequisite {name!r} has no predicate")
        try:
            result = runner(predicate)
        except (OSError, subprocess.SubprocessError) as exc:
            raise MigrationError(f"prerequisite {name!r} could not be executed: {exc}") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "predicate returned nonzero").strip().replace("\n", " ")
            raise MigrationError(f"prerequisite {name!r} is not satisfied: {detail[:240]}")
        checked.append(name)
    return checked


def _ticket(
    payload: dict[str, Any],
    *,
    phase: str,
    task_id: str,
    patch: dict[str, Any],
    status: str,
    action: str,
    timestamp: datetime,
    agent: str,
    session_id: str,
    precondition: dict[str, Any],
) -> Ticket:
    return Ticket(
        ticket_id=deterministic_ticket_id(payload, phase, task_id),
        timestamp=timestamp,
        agent=agent,
        session_id=session_id,
        intent=INTENT_UPSERT,
        task_id=task_id,
        patch=patch,
        log={
            "status": status,
            "output": f"{MIGRATION_ID}: {phase}:{action}; receipt={patch['receipt_target']}",
        },
        precondition=precondition,
    )


def compile_child_tickets(
    payload: dict[str, Any],
    *,
    timestamp: datetime,
    agent: str,
    session_id: str,
) -> list[Ticket]:
    verify_canonical_payload(payload)
    tickets: list[Ticket] = []
    children = payload.get("children")
    if not isinstance(children, list):
        raise MigrationError("manifest children must be a list")
    for row in sorted(
        children,
        key=lambda item: (
            bool(item.get("depends_on")) if isinstance(item, dict) else True,
            str(item.get("id") if isinstance(item, dict) else ""),
        ),
    ):
        if not isinstance(row, dict):
            raise MigrationError("manifest contains a non-object child")
        child = Task.model_validate(row)
        validate_intake_contract(child, is_new=True)
        patch = child.model_dump(mode="json", exclude_none=True)
        tickets.append(
            _ticket(
                payload,
                phase=PHASE_CHILDREN,
                task_id=child.id,
                patch=patch,
                status=child.status,
                action="create",
                timestamp=timestamp,
                agent=agent,
                session_id=session_id,
                precondition={"absent": True},
            )
        )
    expected = int((payload.get("counts") or {}).get("children") or 0)
    if len(tickets) != expected:
        raise MigrationError(f"compiled {len(tickets)} children, expected {expected}")
    return tickets


def _board_tasks(board_path: Path) -> dict[str, Task]:
    board = load_limen_file(board_path)
    return {task.id: task for task in board.tasks}


def _parent_resulting_status(parent: Task, row: dict[str, Any]) -> str:
    status_patch = row.get("status_patch") or {}
    status = str(status_patch.get("status") or parent.status)
    return status


def compile_parent_tickets(
    payload: dict[str, Any],
    board_path: Path,
    *,
    timestamp: datetime,
    agent: str,
    session_id: str,
) -> list[Ticket]:
    verify_canonical_payload(payload)
    board = _board_tasks(board_path)
    tasks = payload.get("tasks")
    frozen_ids = payload.get("frozen_ids")
    if not isinstance(tasks, dict) or not isinstance(frozen_ids, list):
        raise MigrationError("manifest parent mapping/frozen IDs are malformed")
    tickets: list[Ticket] = []
    for task_id in frozen_ids:
        row = tasks.get(task_id)
        parent = board.get(task_id)
        if not isinstance(row, dict) or parent is None:
            raise MigrationError(f"parent {task_id!r} is absent from the live board or manifest")
        resulting_status = _parent_resulting_status(parent, row)
        expected_statuses = {str(row.get("source_status") or ""), resulting_status}
        if parent.status not in expected_statuses:
            raise MigrationError(
                f"parent {task_id!r} status drifted to {parent.status!r}; expected one of {sorted(expected_statuses)}"
            )
        patch: dict[str, Any] = {
            "predicate": effective_parent_predicate(task_id, row),
            "receipt_target": row.get("receipt_target"),
            **(row.get("status_patch") or {}),
        }
        merged = parent.model_dump(mode="json", exclude_none=True)
        merged.update(patch)
        validated = Task.model_validate(merged)
        validate_intake_contract(validated, is_new=False)
        tickets.append(
            _ticket(
                payload,
                phase=PHASE_PARENTS,
                task_id=task_id,
                patch=patch,
                status=resulting_status,
                action=str(row.get("action") or "unknown"),
                timestamp=timestamp,
                agent=agent,
                session_id=session_id,
                precondition={
                    "status": parent.status,
                    "task_sha256": task_state_sha256(parent.model_dump(mode="json", exclude_none=True)),
                },
            )
        )
    expected = int((payload.get("counts") or {}).get("frozen_ids") or 0)
    if len(tickets) != expected:
        raise MigrationError(f"compiled {len(tickets)} parents, expected {expected}")
    return tickets


def _ticket_path(board_path: Path, bucket: str, ticket: Ticket) -> Path:
    return tickets_root(board_path) / bucket / f"{ticket.ticket_id}.json"


def _read_ticket(path: Path) -> Ticket:
    try:
        return Ticket.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - fail closed with the custody path
        raise MigrationError(f"cannot validate migration ticket receipt {path}: {exc}") from exc


def _ticket_semantics(ticket: Ticket, *, include_precondition: bool) -> dict[str, Any]:
    semantic = {
        "intent": ticket.intent,
        "task_id": ticket.task_id,
        "patch": ticket.patch,
        "log": ticket.log,
    }
    if include_precondition:
        semantic["precondition"] = ticket.precondition
    return semantic


def _assert_same_ticket(
    expected: Ticket,
    actual: Ticket,
    path: Path,
    *,
    include_precondition: bool,
) -> None:
    """Compare semantic work, not retry-specific event identity.

    A pending ticket must retain the same optimistic precondition.  Once the
    keeper archives it, that precondition has been consumed, so retries compare
    only the immutable patch/log intent and preserve the archive's original
    timestamp, agent, and session as the honest append-only event identity.
    """

    if _ticket_semantics(actual, include_precondition=include_precondition) != _ticket_semantics(
        expected, include_precondition=include_precondition
    ):
        raise MigrationError(f"deterministic ticket collision or drift at {path}")


def submit_compiled_tickets(board_path: Path, tickets: Iterable[Ticket]) -> dict[str, int]:
    """Append tickets idempotently; any rejection or ID/content drift is fatal."""

    tickets = list(tickets)
    with queue_lock(board_path, timeout=20) as locked:
        if not locked:
            raise MigrationError("queue lock held; phase publication made no inbox changes")
        return _submit_compiled_tickets_locked(board_path, tickets)


def _submit_compiled_tickets_locked(board_path: Path, tickets: list[Ticket]) -> dict[str, int]:
    """Publish one precompiled phase while holding the keeper's queue lock."""

    counts = {"submitted": 0, "pending": 0, "archived": 0}
    missing: list[Ticket] = []
    for ticket in tickets:
        rejected = _ticket_path(board_path, "rejected", ticket)
        rejection_reason = rejected.with_name(f"{rejected.name}.reason.txt")
        if rejected.exists() or rejection_reason.exists():
            raise MigrationError(f"migration ticket was rejected: {rejected}")
        archived = _ticket_path(board_path, "archive", ticket)
        if archived.exists():
            _assert_same_ticket(ticket, _read_ticket(archived), archived, include_precondition=False)
            counts["archived"] += 1
            continue
        pending = _ticket_path(board_path, "inbox", ticket)
        if pending.exists():
            _assert_same_ticket(ticket, _read_ticket(pending), pending, include_precondition=True)
            counts["pending"] += 1
            continue
        missing.append(ticket)

    # No inbox write occurs until every ticket in the phase has passed the
    # rejection/collision preflight.  A bad ticket therefore cannot leave an
    # arbitrary prefix of the phase pending.
    created: list[tuple[Path, Ticket]] = []
    try:
        for ticket in missing:
            try:
                submit_ticket(board_path, ticket)
            except FileExistsError:
                # A concurrent identical submit is harmless; a same-ID/different
                # event is a deterministic collision and triggers rollback.
                pending = _ticket_path(board_path, "inbox", ticket)
                if not pending.exists():
                    raise
                _assert_same_ticket(ticket, _read_ticket(pending), pending, include_precondition=True)
                counts["pending"] += 1
                continue
            pending = _ticket_path(board_path, "inbox", ticket)
            created.append((pending, ticket))
            counts["submitted"] += 1
    except Exception as exc:
        rollback_errors: list[str] = []
        removed = 0
        consumed = 0
        for pending, created_ticket in reversed(created):
            if not pending.exists():
                consumed += 1
                continue  # the keeper already consumed it; never rewrite custody
            try:
                _assert_same_ticket(
                    created_ticket,
                    _read_ticket(pending),
                    pending,
                    include_precondition=True,
                )
                pending.unlink()
                removed += 1
            except Exception as rollback_exc:  # noqa: BLE001 - preserve every unsafe path
                rollback_errors.append(f"{pending}: {rollback_exc}")
        if rollback_errors:
            raise MigrationError(
                "phase publication failed and exact-prefix cleanup was incomplete: " + "; ".join(rollback_errors)
            ) from exc
        raise MigrationError(
            f"phase publication failed; removed {removed} exact unconsumed ticket(s) from this invocation; "
            f"{consumed} already consumed and left in keeper custody: {exc}"
        ) from exc
    return counts


def _child_manifest_fields(child: dict[str, Any]) -> dict[str, Any]:
    validated = Task.model_validate(child)
    return validated.model_dump(mode="json", exclude_none=True)


def preflight_child_submission(payload: dict[str, Any], board_path: Path, tickets: Iterable[Ticket]) -> None:
    """Refuse to overwrite a same-ID task that did not come from this migration."""

    board = _board_tasks(board_path)
    children = {str(row.get("id")): row for row in payload.get("children", []) if isinstance(row, dict)}
    for ticket in tickets:
        task_id = str(ticket.task_id)
        current = board.get(task_id)
        archived = _ticket_path(board_path, "archive", ticket)
        if current is None:
            if archived.exists():
                raise MigrationError(f"child {task_id!r} has keeper custody but disappeared from the board")
            continue
        if not archived.exists():
            raise MigrationError(f"child {task_id!r} already exists without this migration's keeper receipt")
        actual = current.model_dump(mode="json", exclude_none=True)
        expected = _child_manifest_fields(children[task_id])
        for volatile in CHILD_ROUTING_VOLATILE_FIELDS:
            actual.pop(volatile, None)
            expected.pop(volatile, None)
        if actual != expected:
            raise MigrationError(f"child {task_id!r} already exists with a different task contract")


def check_parent_dispositions(
    payload: dict[str, Any],
    *,
    runner: RunPredicate = _default_predicate_runner,
) -> dict[str, int]:
    """Re-read every owner receipt and reject a stale migration action.

    Terminal/split actions must already satisfy their predicate.  Open and
    human-routed actions must not: if their receipt has become terminal, the
    frozen action is stale and must be re-routed rather than blindly applied.
    """

    verify_canonical_payload(payload)
    tasks = payload.get("tasks") or {}
    counts = {"terminal": 0, "nonterminal": 0}
    for task_id in payload.get("frozen_ids") or []:
        row = tasks.get(task_id)
        if not isinstance(row, dict):
            raise MigrationError(f"parent {task_id!r} has no disposition row")
        action = str(row.get("action") or "")
        predicate = effective_parent_predicate(task_id, row)
        try:
            result = runner(predicate)
        except (OSError, subprocess.SubprocessError) as exc:
            raise MigrationError(f"parent {task_id!r} owner predicate could not be executed: {exc}") from exc
        if result.returncode not in {0, 1}:
            detail = (result.stderr or result.stdout or "predicate evaluation failed").strip().replace("\n", " ")
            raise MigrationError(f"parent {task_id!r} owner predicate could not be evaluated: {detail[:180]}")
        satisfied = result.returncode == 0
        expected_satisfied = action in {"done", "superseded", "split"}
        if satisfied != expected_satisfied:
            observed = "satisfied" if satisfied else "not satisfied"
            expected = "satisfied" if expected_satisfied else "not satisfied"
            detail = (result.stderr or result.stdout or "").strip().replace("\n", " ")
            raise MigrationError(
                f"parent {task_id!r} owner predicate is {observed}, expected {expected} for action {action!r}"
                + (f": {detail[:180]}" if detail else "")
            )
        counts["terminal" if expected_satisfied else "nonterminal"] += 1
    return counts


def verify_children_admitted(payload: dict[str, Any], board_path: Path) -> dict[str, int]:
    """Prove all children crossed the keeper seam before parents may be submitted."""

    verify_canonical_payload(payload)
    board = _board_tasks(board_path)
    timestamp = parse_timestamp(str(payload.get("generated_at")))
    probe_tickets = compile_child_tickets(
        payload,
        timestamp=timestamp,
        agent="receipt-probe",
        session_id="receipt-probe",
    )
    children = {str(row.get("id")): row for row in payload.get("children", []) if isinstance(row, dict)}
    for ticket in probe_tickets:
        task_id = str(ticket.task_id)
        child = board.get(task_id)
        if child is None:
            raise MigrationError(f"child {task_id!r} is not admitted on the board")
        validate_intake_contract(child, is_new=True)
        actual = child.model_dump(mode="json", exclude_none=True)
        expected = _child_manifest_fields(children[task_id])
        for volatile in CHILD_ROUTING_VOLATILE_FIELDS:
            actual.pop(volatile, None)
            expected.pop(volatile, None)
        if actual != expected:
            raise MigrationError(f"child {task_id!r} does not match the frozen typed packet")

        # The deterministic ID ignores timestamp/session identity, so the probe
        # locates the real application ticket without knowing its runtime fields.
        rejected = _ticket_path(board_path, "rejected", ticket)
        rejection_reason = rejected.with_name(f"{rejected.name}.reason.txt")
        pending = _ticket_path(board_path, "inbox", ticket)
        archived = _ticket_path(board_path, "archive", ticket)
        if rejected.exists() or rejection_reason.exists():
            raise MigrationError(f"child {task_id!r} has a rejected keeper ticket")
        if pending.exists():
            raise MigrationError(f"child {task_id!r} is still pending keeper admission")
        if not archived.exists():
            raise MigrationError(f"child {task_id!r} lacks a keeper archive receipt")
        archived_ticket = _read_ticket(archived)
        if archived_ticket.task_id != task_id or archived_ticket.intent != INTENT_UPSERT:
            raise MigrationError(f"child {task_id!r} archive receipt has the wrong owner/intent")
        if archived_ticket.patch != ticket.patch:
            raise MigrationError(f"child {task_id!r} archive receipt does not carry the frozen packet")
        if archived_ticket.precondition != {"absent": True}:
            raise MigrationError(f"child {task_id!r} archive receipt lacks the absent-state precondition")
        if not archived_ticket.log or archived_ticket.log.get("status") != child.status:
            raise MigrationError(f"child {task_id!r} archive receipt lacks its append-only creation log")
        matching_log = any(
            entry.timestamp == archived_ticket.timestamp
            and entry.agent == archived_ticket.agent
            and entry.session_id == archived_ticket.session_id
            and entry.status == archived_ticket.log.get("status")
            and entry.output == archived_ticket.log.get("output")
            for entry in child.dispatch_log
        )
        if not matching_log:
            raise MigrationError(f"child {task_id!r} board log does not match its honest archive identity")
    return {"admitted": len(probe_tickets), "rejected": 0, "pending": 0}


def verify_parents_applied(payload: dict[str, Any], board_path: Path) -> dict[str, int]:
    verify_canonical_payload(payload)
    board = _board_tasks(board_path)
    tasks = payload.get("tasks") or {}
    verified = 0
    for task_id in payload.get("frozen_ids") or []:
        row = tasks.get(task_id)
        parent = board.get(task_id)
        if not isinstance(row, dict) or parent is None:
            raise MigrationError(f"parent {task_id!r} is missing after application")
        ticket_id = deterministic_ticket_id(payload, PHASE_PARENTS, task_id)
        filename = f"{ticket_id}.json"
        root = tickets_root(board_path)
        rejected = root / "rejected" / filename
        rejection_reason = rejected.with_name(f"{rejected.name}.reason.txt")
        pending = root / "inbox" / filename
        archived = root / "archive" / filename
        if rejected.exists() or rejection_reason.exists():
            raise MigrationError(f"parent {task_id!r} has a rejected keeper ticket")
        if pending.exists():
            raise MigrationError(f"parent {task_id!r} is still pending keeper admission")
        if not archived.exists():
            raise MigrationError(f"parent {task_id!r} lacks a keeper archive receipt")
        archived_ticket = _read_ticket(archived)
        expected_status = str((row.get("status_patch") or {}).get("status") or parent.status)
        if parent.status != expected_status:
            raise MigrationError(f"parent {task_id!r} has status {parent.status!r}, expected {expected_status!r}")
        effective_predicate = effective_parent_predicate(task_id, row)
        if parent.predicate != effective_predicate or parent.receipt_target != row.get("receipt_target"):
            raise MigrationError(f"parent {task_id!r} lacks the frozen typed contract")
        expected_patch = {
            "predicate": effective_predicate,
            "receipt_target": row.get("receipt_target"),
            **(row.get("status_patch") or {}),
        }
        if (
            archived_ticket.task_id != task_id
            or archived_ticket.intent != INTENT_UPSERT
            or archived_ticket.patch != expected_patch
            or not archived_ticket.log
            or archived_ticket.log.get("status") != expected_status
        ):
            raise MigrationError(f"parent {task_id!r} archive receipt has wrong patch/log/intent")
        precondition = archived_ticket.precondition or {}
        allowed_precondition_statuses = {str(row.get("source_status") or ""), expected_status}
        if precondition.get("status") not in allowed_precondition_statuses or not isinstance(
            precondition.get("task_sha256"), str
        ):
            raise MigrationError(f"parent {task_id!r} archive receipt lacks its exact source-state precondition")
        matching_log = any(
            entry.timestamp == archived_ticket.timestamp
            and entry.agent == archived_ticket.agent
            and entry.session_id == archived_ticket.session_id
            and entry.status == archived_ticket.log.get("status")
            and entry.output == archived_ticket.log.get("output")
            for entry in parent.dispatch_log
        )
        if not matching_log:
            raise MigrationError(f"parent {task_id!r} board log does not match its honest archive identity")
        verified += 1
    return {"verified": verified}


def _summary(
    *,
    phase: str,
    payload: dict[str, Any],
    gates: list[str],
    tickets: list[Ticket],
    applied: bool,
    submission: dict[str, int] | None = None,
    owner_state: dict[str, int] | None = None,
) -> dict[str, Any]:
    result = {
        "schema_version": "limen.ask_gate_migration.compile.v1",
        "migration": MIGRATION_ID,
        "manifest_sha256": manifest_digest(payload),
        "mode": "apply" if applied else "dry-run",
        "phase": phase,
        "live_prerequisites": gates,
        "compiled": len(tickets),
        "ticket_ids": [ticket.ticket_id for ticket in tickets],
        "submission": submission or {"submitted": 0, "pending": 0, "archived": 0},
        "requested_event_identity": (
            {
                "timestamp": tickets[0].timestamp.isoformat(),
                "agent": tickets[0].agent,
                "session_id": tickets[0].session_id,
            }
            if tickets
            else None
        ),
    }
    if owner_state is not None:
        result["parent_owner_state"] = owner_state
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="compile the two-phase ask-gate migration")
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--tasks", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--phase", choices=(*APPLY_PHASES, PHASE_VERIFY), default=PHASE_CHILDREN)
    parser.add_argument("--apply", action="store_true", help="submit this phase's tickets; never edits tasks.yaml")
    parser.add_argument("--timestamp", help="explicit ISO-8601 event time (required with --apply)")
    parser.add_argument("--agent", default="codex")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--show-tickets", action="store_true", help="include full compiled tickets in JSON output")
    args = parser.parse_args(argv)

    try:
        payload = json.loads(args.receipt.read_text(encoding="utf-8"))
        if args.apply and args.phase == PHASE_VERIFY:
            raise MigrationError("--phase verify is read-only; remove --apply")
        if args.apply and (not args.timestamp or not args.session_id.strip()):
            raise MigrationError("--apply requires explicit --timestamp and --session-id")
        gates = check_live_prerequisites(payload)
        timestamp = parse_timestamp(args.timestamp or str(payload.get("generated_at")))
        session_id = args.session_id.strip() or "dry-run"

        if args.phase == PHASE_VERIFY:
            children = verify_children_admitted(payload, args.tasks)
            owner_state = check_parent_dispositions(payload)
            parents = verify_parents_applied(payload, args.tasks)
            result: dict[str, Any] = {
                "schema_version": "limen.ask_gate_migration.verify.v1",
                "migration": MIGRATION_ID,
                "mode": "verify",
                "live_prerequisites": gates,
                "children": children,
                "parent_owner_state": owner_state,
                "parents": parents,
            }
            print(json.dumps(result, sort_keys=True))
            return 0

        owner_state = None
        if args.phase == PHASE_CHILDREN:
            tickets = compile_child_tickets(
                payload,
                timestamp=timestamp,
                agent=args.agent,
                session_id=session_id,
            )
            preflight_child_submission(payload, args.tasks, tickets)
        else:
            # This is the hard phase seam: even a parent dry run refuses to
            # compile against children that have not crossed the keeper.
            verify_children_admitted(payload, args.tasks)
            owner_state = check_parent_dispositions(payload)
            tickets = compile_parent_tickets(
                payload,
                args.tasks,
                timestamp=timestamp,
                agent=args.agent,
                session_id=session_id,
            )
        submission = submit_compiled_tickets(args.tasks, tickets) if args.apply else None
        result = _summary(
            phase=args.phase,
            payload=payload,
            gates=gates,
            tickets=tickets,
            applied=args.apply,
            submission=submission,
            owner_state=owner_state,
        )
        if args.show_tickets:
            result["tickets"] = [ticket.model_dump(mode="json") for ticket in tickets]
        print(json.dumps(result, sort_keys=True))
        return 0
    except (MigrationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ask-gate-migration-apply: BLOCKED - {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
