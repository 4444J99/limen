#!/usr/bin/env python3
"""Type the frozen 2026-07-19 GitHub-issue intake cohort through TABVLARIVS.

The tracked receipt binds every legacy task to its exact source issue and
pre-migration task hash.  The default mode is a read-only compile.  ``--apply``
only appends immutable keeper tickets; it never edits ``tasks.yaml``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.intake import github_issue_contract, validate_intake_contract
from limen.io import load_limen_file, queue_lock
from limen.models import Task, dispatch_agent, dispatch_session_id
from limen.tabularius import (
    INTENT_UPSERT,
    Ticket,
    submit_ticket,
    task_state_sha256,
    tickets_root,
)

SCHEMA = "limen.ask_gate_owner_contracts.v1"
COMPILE_SCHEMA = "limen.ask_gate_owner_contracts.compile.v1"
VERIFY_SCHEMA = "limen.ask_gate_owner_contracts.verify.v1"
MIGRATION_ID = "ask-gate-owner-contracts-20260725"
SOURCE_REPO = "organvm/peer-audited--behavioral-blockchain"
SOURCE_CONTEXT = "Ingested via script"
SOURCE_CREATED = "2026-07-19"
SOURCE_STATUS = "open"
EXPECTED_COUNT = 297
BASELINE_INTAKE_COUNT = 404
BASELINE_SPLIT_COUNT = 297
OWNER_ISSUE = "https://github.com/organvm/limen/issues/1359"
DEFAULT_RECEIPT = ROOT / "docs" / "ask-gate-owner-contracts-2026-07-25.json"
DEFAULT_BOARD = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
ASK_GATE_SCRIPT = ROOT / "scripts" / "ask-gate.py"
SOURCE_URL_RE = re.compile(rf"^https://github\.com/{re.escape(SOURCE_REPO)}/issues/(?P<number>[1-9][0-9]*)$")


class MigrationError(RuntimeError):
    """The migration cannot advance without violating an owner or custody gate."""


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise MigrationError(f"invalid ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise MigrationError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _task_fields(task: Task) -> dict[str, Any]:
    return task.model_dump(mode="json", exclude_none=True)


def _source_url(task: Task) -> str:
    if len(task.urls) != 1:
        raise MigrationError(f"task {task.id!r} must carry exactly one source URL")
    url = task.urls[0]
    if SOURCE_URL_RE.fullmatch(url) is None:
        raise MigrationError(f"task {task.id!r} has a non-canonical source issue URL")
    return url


def _source_candidates(board_path: Path) -> list[Task]:
    board = load_limen_file(board_path)
    return sorted(
        (
            task
            for task in board.tasks
            if task.repo == SOURCE_REPO
            and task.context == SOURCE_CONTEXT
            and task.created.isoformat() == SOURCE_CREATED
            and task.status == SOURCE_STATUS
        ),
        key=lambda task: task.id,
    )


def _contract_for_url(url: str):
    match = SOURCE_URL_RE.fullmatch(url)
    if match is None:
        raise MigrationError(f"not a canonical source issue URL: {url!r}")
    return github_issue_contract(SOURCE_REPO, match.group("number"))


@lru_cache(maxsize=1)
def _ask_gate():
    spec = importlib.util.spec_from_file_location("ask_gate_owner_contracts_canonical", ASK_GATE_SCRIPT)
    if spec is None or spec.loader is None:
        raise MigrationError(f"cannot load canonical ask gate: {ASK_GATE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_receipt(
    board_path: Path,
    *,
    generated_at: str,
    expected_count: int | None = None,
) -> dict[str, Any]:
    """Freeze the exact untyped cohort and its source-state preconditions."""

    expected_count = EXPECTED_COUNT if expected_count is None else expected_count
    stamp = parse_timestamp(generated_at).isoformat().replace("+00:00", "Z")
    candidates = _source_candidates(board_path)
    rows: list[dict[str, str]] = []
    for task in candidates:
        url = _source_url(task)
        finding = _ask_gate().assess(_task_fields(task))
        if finding.get("verdict") != "SPLIT":
            continue
        predicate = str(task.predicate or "").strip()
        receipt_target = str(task.receipt_target or "").strip()
        if predicate or receipt_target:
            if not predicate or not receipt_target:
                raise MigrationError(f"task {task.id!r} has a partial owner contract")
            validate_intake_contract(task)
            continue
        contract = _contract_for_url(url)
        prospective = task.model_copy(
            update={"predicate": contract.predicate, "receipt_target": contract.receipt_target}
        )
        validate_intake_contract(prospective)
        if _ask_gate().assess(_task_fields(prospective)).get("verdict") == "SPLIT":
            raise MigrationError(f"task {task.id!r} remains SPLIT after adding its exact issue contract")
        rows.append(
            {
                "task_id": task.id,
                "source_url": url,
                "predicate": contract.predicate,
                "receipt_target": contract.receipt_target,
                "task_sha256": task_state_sha256(_task_fields(task)),
            }
        )
    if len(rows) != expected_count:
        raise MigrationError(f"untyped source cohort contains {len(rows)} tasks, expected {expected_count}")
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "migration": MIGRATION_ID,
        "generated_at": stamp,
        "owner_issue": OWNER_ISSUE,
        "source": {
            "repo": SOURCE_REPO,
            "context": SOURCE_CONTEXT,
            "created": SOURCE_CREATED,
            "status": SOURCE_STATUS,
        },
        "baseline": {
            "intake_window_tasks": BASELINE_INTAKE_COUNT,
            "split_tasks": BASELINE_SPLIT_COUNT,
        },
        "expected_count": expected_count,
        "source_candidate_count": len(candidates),
        "rows": rows,
        "cohort_sha256": _sha256(rows),
    }
    verify_receipt(payload, expected_count=expected_count)
    return payload


def verify_receipt(payload: dict[str, Any], *, expected_count: int | None = None) -> str:
    expected_count = EXPECTED_COUNT if expected_count is None else expected_count
    if payload.get("schema") != SCHEMA or payload.get("migration") != MIGRATION_ID:
        raise MigrationError("receipt schema or migration identity is invalid")
    parse_timestamp(str(payload.get("generated_at") or ""))
    if payload.get("owner_issue") != OWNER_ISSUE:
        raise MigrationError("receipt owner issue drifted")
    expected_source = {
        "repo": SOURCE_REPO,
        "context": SOURCE_CONTEXT,
        "created": SOURCE_CREATED,
        "status": SOURCE_STATUS,
    }
    if payload.get("source") != expected_source:
        raise MigrationError("receipt source cohort contract drifted")
    if payload.get("baseline") != {
        "intake_window_tasks": BASELINE_INTAKE_COUNT,
        "split_tasks": BASELINE_SPLIT_COUNT,
    }:
        raise MigrationError("receipt no longer preserves the 404/297 baseline")
    if payload.get("expected_count") != expected_count:
        raise MigrationError("receipt expected count drifted")
    candidate_count = payload.get("source_candidate_count")
    if not isinstance(candidate_count, int) or candidate_count < expected_count:
        raise MigrationError("receipt source candidate count is invalid")
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != expected_count:
        raise MigrationError(f"receipt contains {len(rows) if isinstance(rows, list) else 0} rows")
    task_ids: list[str] = []
    urls: list[str] = []
    allowed = {"task_id", "source_url", "predicate", "receipt_target", "task_sha256"}
    for row in rows:
        if not isinstance(row, dict) or set(row) != allowed:
            raise MigrationError("receipt row shape is invalid")
        task_id = str(row["task_id"])
        url = str(row["source_url"])
        contract = _contract_for_url(url)
        if row["predicate"] != contract.predicate or row["receipt_target"] != contract.receipt_target:
            raise MigrationError(f"receipt row {task_id!r} does not match its source issue contract")
        if re.fullmatch(r"[0-9a-f]{64}", str(row["task_sha256"])) is None:
            raise MigrationError(f"receipt row {task_id!r} has an invalid task hash")
        task_ids.append(task_id)
        urls.append(url)
    if task_ids != sorted(task_ids) or len(set(task_ids)) != expected_count:
        raise MigrationError("receipt task IDs are not unique and canonically ordered")
    if len(set(urls)) != expected_count:
        raise MigrationError("receipt source URLs are not unique")
    digest = _sha256(rows)
    if payload.get("cohort_sha256") != digest:
        raise MigrationError("receipt cohort digest is invalid")
    return digest


def load_canonical_receipt() -> dict[str, Any]:
    try:
        payload = json.loads(DEFAULT_RECEIPT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationError(f"cannot read canonical owner-contract receipt: {exc}") from exc
    verify_receipt(payload)
    return payload


def _assert_canonical(payload: dict[str, Any]) -> str:
    canonical = load_canonical_receipt()
    if _canonical_bytes(payload) != _canonical_bytes(canonical):
        raise MigrationError("payload differs from the canonical owner-contract receipt")
    return verify_receipt(canonical)


def deterministic_ticket_id(payload: dict[str, Any], task_id: str) -> str:
    digest = _assert_canonical(payload)
    return _ticket_id_from_digest(digest, task_id)


def _ticket_id_from_digest(digest: str, task_id: str) -> str:
    suffix = hashlib.sha256(f"{digest}\0{task_id}".encode()).hexdigest()[:24]
    return f"{MIGRATION_ID}-upsert-{suffix}"


def _board_tasks(board_path: Path) -> dict[str, Task]:
    return {task.id: task for task in load_limen_file(board_path).tasks}


def _assert_current_source(task: Task, row: dict[str, Any]) -> str:
    if (
        task.repo != SOURCE_REPO
        or task.context != SOURCE_CONTEXT
        or task.created.isoformat() != SOURCE_CREATED
        or task.status != SOURCE_STATUS
    ):
        raise MigrationError(f"task {task.id!r} drifted outside the frozen source cohort")
    if _source_url(task) != row["source_url"]:
        raise MigrationError(f"task {task.id!r} source URL drifted")
    predicate = str(task.predicate or "").strip()
    receipt_target = str(task.receipt_target or "").strip()
    expected = (row["predicate"], row["receipt_target"])
    if not predicate and not receipt_target:
        if task_state_sha256(_task_fields(task)) != row["task_sha256"]:
            raise MigrationError(f"task {task.id!r} source state drifted before owner-contract admission")
        return "pending"
    if (predicate, receipt_target) == expected:
        validate_intake_contract(task)
        return "present"
    raise MigrationError(f"task {task.id!r} has a partial or different owner contract")


def compile_tickets(
    payload: dict[str, Any],
    board_path: Path,
    *,
    timestamp: datetime,
    agent: str,
    session_id: str,
) -> tuple[list[Ticket], dict[str, int]]:
    digest = _assert_canonical(payload)
    board = _board_tasks(board_path)
    tickets: list[Ticket] = []
    state = {"pending": 0, "present": 0}
    for row in payload["rows"]:
        task_id = row["task_id"]
        task = board.get(task_id)
        if task is None:
            raise MigrationError(f"task {task_id!r} disappeared from the board")
        state[_assert_current_source(task, row)] += 1
        prospective = task.model_copy(update={"predicate": row["predicate"], "receipt_target": row["receipt_target"]})
        validate_intake_contract(prospective)
        tickets.append(
            Ticket(
                ticket_id=_ticket_id_from_digest(digest, task_id),
                timestamp=timestamp,
                agent=agent,
                session_id=session_id,
                intent=INTENT_UPSERT,
                task_id=task_id,
                patch={"predicate": row["predicate"], "receipt_target": row["receipt_target"]},
                log={
                    "status": SOURCE_STATUS,
                    "output": f"{MIGRATION_ID}: typed exact GitHub issue owner contract; receipt={row['source_url']}",
                },
                precondition={"status": SOURCE_STATUS, "task_sha256": row["task_sha256"]},
            )
        )
    if len(tickets) != EXPECTED_COUNT or len({ticket.ticket_id for ticket in tickets}) != EXPECTED_COUNT:
        raise MigrationError("compiled ticket count or identity set is incomplete")
    return tickets, state


def _ticket_path(board_path: Path, bucket: str, ticket: Ticket) -> Path:
    return tickets_root(board_path) / bucket / f"{ticket.ticket_id}.json"


def _read_ticket(path: Path) -> Ticket:
    try:
        return Ticket.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise MigrationError(f"cannot validate keeper ticket {path}: {exc}") from exc


def _ticket_semantics(ticket: Ticket) -> dict[str, Any]:
    return {
        "intent": ticket.intent,
        "task_id": ticket.task_id,
        "patch": ticket.patch,
        "log": ticket.log,
        "precondition": ticket.precondition,
    }


def _assert_same_ticket(expected: Ticket, actual: Ticket, path: Path) -> None:
    if _ticket_semantics(expected) != _ticket_semantics(actual):
        raise MigrationError(f"deterministic ticket collision or drift at {path}")


def submit_compiled_tickets(board_path: Path, tickets: Iterable[Ticket]) -> dict[str, int]:
    tickets = list(tickets)
    with queue_lock(board_path, timeout=20) as locked:
        if not locked:
            raise MigrationError("queue lock held; publication made no inbox changes")
        counts = {"submitted": 0, "pending": 0, "archived": 0}
        missing: list[Ticket] = []
        for ticket in tickets:
            rejected = _ticket_path(board_path, "rejected", ticket)
            reason = rejected.with_name(f"{rejected.name}.reason.txt")
            if rejected.exists() or reason.exists():
                raise MigrationError(f"migration ticket was rejected: {rejected}")
            archived = _ticket_path(board_path, "archive", ticket)
            if archived.exists():
                _assert_same_ticket(ticket, _read_ticket(archived), archived)
                counts["archived"] += 1
                continue
            pending = _ticket_path(board_path, "inbox", ticket)
            if pending.exists():
                _assert_same_ticket(ticket, _read_ticket(pending), pending)
                counts["pending"] += 1
                continue
            missing.append(ticket)
        created: list[tuple[Path, Ticket]] = []
        try:
            for ticket in missing:
                try:
                    submit_ticket(board_path, ticket)
                except FileExistsError:
                    pending = _ticket_path(board_path, "inbox", ticket)
                    if not pending.exists():
                        raise
                    _assert_same_ticket(ticket, _read_ticket(pending), pending)
                    counts["pending"] += 1
                    continue
                pending = _ticket_path(board_path, "inbox", ticket)
                created.append((pending, ticket))
                counts["submitted"] += 1
        except Exception as exc:
            removed = 0
            rollback_errors: list[str] = []
            for pending, ticket in reversed(created):
                if not pending.exists():
                    continue
                try:
                    _assert_same_ticket(ticket, _read_ticket(pending), pending)
                    pending.unlink()
                    removed += 1
                except Exception as rollback_exc:  # noqa: BLE001
                    rollback_errors.append(f"{pending}: {rollback_exc}")
            if rollback_errors:
                raise MigrationError(
                    "publication failed and exact-prefix cleanup was incomplete: " + "; ".join(rollback_errors)
                ) from exc
            raise MigrationError(f"publication failed; removed {removed} exact unconsumed ticket(s): {exc}") from exc
        return counts


def verify_applied(payload: dict[str, Any], board_path: Path) -> dict[str, int]:
    _assert_canonical(payload)
    board = _board_tasks(board_path)
    timestamp = parse_timestamp(payload["generated_at"])
    probes, _ = compile_tickets(
        payload,
        board_path,
        timestamp=timestamp,
        agent="receipt-probe",
        session_id="receipt-probe",
    )
    rows = {row["task_id"]: row for row in payload["rows"]}
    for probe in probes:
        task_id = str(probe.task_id)
        task = board[task_id]
        if _assert_current_source(task, rows[task_id]) != "present":
            raise MigrationError(f"task {task_id!r} still lacks its owner contract")
        rejected = _ticket_path(board_path, "rejected", probe)
        reason = rejected.with_name(f"{rejected.name}.reason.txt")
        pending = _ticket_path(board_path, "inbox", probe)
        archived = _ticket_path(board_path, "archive", probe)
        if rejected.exists() or reason.exists():
            raise MigrationError(f"task {task_id!r} has a rejected keeper ticket")
        if pending.exists():
            raise MigrationError(f"task {task_id!r} still has a pending keeper ticket")
        if not archived.exists():
            raise MigrationError(f"task {task_id!r} lacks an archived keeper ticket")
        actual = _read_ticket(archived)
        _assert_same_ticket(probe, actual, archived)
        matching_log = any(
            dispatch_agent(entry) == actual.agent
            and dispatch_session_id(entry) == actual.session_id
            and entry.status == actual.log["status"]
            and entry.output == actual.log["output"]
            and (
                entry.timestamp == actual.timestamp
                or all(
                    getattr(entry, field, None)
                    for field in (
                        "conduct_event_id",
                        "conduct_run_id",
                        "conduct_lease_id",
                        "conduct_generation",
                    )
                )
            )
            for entry in task.dispatch_log
        )
        if not matching_log:
            raise MigrationError(f"task {task_id!r} board log does not match its keeper receipt")
    return {"verified": len(probes), "pending": 0, "rejected": 0}


def _summary(payload: dict[str, Any], *, mode: str, state: dict[str, int], **extra: Any) -> dict[str, Any]:
    result = {
        "schema": VERIFY_SCHEMA if mode == "verify" else COMPILE_SCHEMA,
        "migration": MIGRATION_ID,
        "mode": mode,
        "cohort_sha256": payload["cohort_sha256"],
        "baseline": payload["baseline"],
        "compiled": EXPECTED_COUNT,
        "owner_contracts": state,
    }
    result.update(extra)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="apply the frozen ask-gate GitHub issue owner contracts")
    parser.add_argument("--tasks", type=Path, default=DEFAULT_BOARD)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--render-receipt", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--timestamp", help="explicit ISO-8601 event time")
    parser.add_argument("--agent", default="codex")
    parser.add_argument("--session-id", default="")
    args = parser.parse_args(argv)

    try:
        if args.render_receipt:
            if not args.timestamp:
                raise MigrationError("--render-receipt requires --timestamp")
            payload = build_receipt(args.tasks, generated_at=args.timestamp)
            DEFAULT_RECEIPT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            result = {
                "schema": SCHEMA,
                "mode": "render-receipt",
                "path": str(DEFAULT_RECEIPT),
                "rows": len(payload["rows"]),
                "cohort_sha256": payload["cohort_sha256"],
            }
        else:
            payload = load_canonical_receipt()
            timestamp = parse_timestamp(args.timestamp or payload["generated_at"])
            session_id = args.session_id.strip() or "dry-run"
            tickets, state = compile_tickets(
                payload,
                args.tasks,
                timestamp=timestamp,
                agent=args.agent,
                session_id=session_id,
            )
            if args.verify:
                verified = verify_applied(payload, args.tasks)
                result = _summary(payload, mode="verify", state=state, verification=verified)
            elif args.apply:
                if not args.timestamp or not args.session_id.strip():
                    raise MigrationError("--apply requires explicit --timestamp and --session-id")
                submission = submit_compiled_tickets(args.tasks, tickets)
                result = _summary(payload, mode="apply", state=state, submission=submission)
            else:
                result = _summary(
                    payload,
                    mode="dry-run",
                    state=state,
                    first_ticket=tickets[0].ticket_id,
                    last_ticket=tickets[-1].ticket_id,
                )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (MigrationError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ask-gate-owner-contracts: BLOCKED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
