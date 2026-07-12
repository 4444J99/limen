from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from limen.io import load_limen_file, save_limen_file
from limen.models import LimenFile
from limen.tabularius import drain_once, tickets_root


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "apply-ask-gate-migration.py"
RECEIPT = ROOT / "docs" / "ask-gate-migration-2026-07-12.json"
BOARD = ROOT / "tasks.yaml"


def _module():
    spec = importlib.util.spec_from_file_location("apply_ask_gate_migration", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload() -> dict:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def test_non_merged_live_prerequisite_fails_closed() -> None:
    compiler = _module()
    payload = _payload()
    seen: list[str] = []

    def runner(command: str):
        seen.append(command)
        return SimpleNamespace(
            returncode=1 if "982" in command else 0,
            stdout="",
            stderr="PR #982 is OPEN" if "982" in command else "",
        )

    with pytest.raises(compiler.MigrationError, match="terminal_discovery_dispositions.*not satisfied"):
        compiler.check_live_prerequisites(payload, runner=runner)
    assert any("978" in command for command in seen)
    assert any("982" in command for command in seen)


def test_compiler_rejects_payload_that_differs_from_canonical_receipt() -> None:
    compiler = _module()
    broken = copy.deepcopy(_payload())
    broken["tasks"]["GH-organvm-limen-793"]["predicate"] = "true"

    with pytest.raises(compiler.MigrationError, match="differs from the canonical verified"):
        compiler.compile_child_tickets(
            broken,
            timestamp=compiler.parse_timestamp("2026-07-12T18:00:00Z"),
            agent="codex",
            session_id="mutated-manifest",
        )


def test_compilers_are_deterministic_typed_and_append_only() -> None:
    compiler = _module()
    payload = _payload()
    timestamp = compiler.parse_timestamp("2026-07-12T18:00:00Z")
    kwargs = {"timestamp": timestamp, "agent": "codex", "session_id": "test-session"}

    children_a = compiler.compile_child_tickets(payload, **kwargs)
    children_b = compiler.compile_child_tickets(payload, **kwargs)
    assert [ticket.model_dump(mode="json") for ticket in children_a] == [
        ticket.model_dump(mode="json") for ticket in children_b
    ]
    assert len(children_a) == 29
    assert len({ticket.ticket_id for ticket in children_a}) == 29
    assert all(ticket.intent == "task.upsert" and ticket.log for ticket in children_a)
    assert all(ticket.precondition == {"absent": True} for ticket in children_a)
    assert all(
        ticket.patch and ticket.patch.get("predicate") and ticket.patch.get("receipt_target") for ticket in children_a
    )

    parents_a = compiler.compile_parent_tickets(payload, BOARD, **kwargs)
    parents_b = compiler.compile_parent_tickets(payload, BOARD, **kwargs)
    assert [ticket.model_dump(mode="json") for ticket in parents_a] == [
        ticket.model_dump(mode="json") for ticket in parents_b
    ]
    assert len(parents_a) == 52
    assert len({ticket.ticket_id for ticket in parents_a}) == 52
    assert all(ticket.intent == "task.upsert" and ticket.log for ticket in parents_a)
    assert all(ticket.precondition and ticket.precondition.get("task_sha256") for ticket in parents_a)
    assert all(
        set(ticket.patch or {}) <= {"predicate", "receipt_target", "status"}
        and {"predicate", "receipt_target"} <= set(ticket.patch or {})
        for ticket in parents_a
    )
    assert all(ticket.log["status"] for ticket in parents_a if ticket.log)
    assert all(compiler.MIGRATION_ID in ticket.log["output"] for ticket in parents_a if ticket.log)


def test_parent_phase_refuses_before_children_cross_keeper(tmp_path: Path) -> None:
    compiler = _module()
    board = tmp_path / "tasks.yaml"
    save_limen_file(board, LimenFile())
    with pytest.raises(compiler.MigrationError, match="is not admitted on the board"):
        compiler.verify_children_admitted(_payload(), board)


def test_child_preflight_refuses_same_id_without_migration_custody(tmp_path: Path) -> None:
    compiler = _module()
    payload = _payload()
    board = tmp_path / "tasks.yaml"
    first_child = payload["children"][0]
    save_limen_file(board, LimenFile(tasks=[first_child]))
    tickets = compiler.compile_child_tickets(
        payload,
        timestamp=compiler.parse_timestamp("2026-07-12T18:00:00Z"),
        agent="codex",
        session_id="preflight",
    )
    with pytest.raises(compiler.MigrationError, match="already exists without.*keeper receipt"):
        compiler.preflight_child_submission(payload, board, tickets)


def test_parent_owner_state_gate_rejects_newly_terminal_open_work() -> None:
    compiler = _module()
    payload = _payload()
    by_predicate = {
        compiler.effective_parent_predicate(task_id, row): row["action"] for task_id, row in payload["tasks"].items()
    }
    stale_predicate = compiler.effective_parent_predicate(
        "GH-organvm-limen-685",
        payload["tasks"]["GH-organvm-limen-685"],
    )

    def runner(command: str):
        action = by_predicate[command]
        satisfied = action in {"done", "superseded", "split"} or command == stale_predicate
        return SimpleNamespace(returncode=0 if satisfied else 1, stdout="", stderr="")

    with pytest.raises(compiler.MigrationError, match="GH-organvm-limen-685.*expected not satisfied"):
        compiler.check_parent_dispositions(payload, runner=runner)


def test_parent_owner_state_gate_accepts_reasoned_false_and_rejects_evaluation_error() -> None:
    compiler = _module()
    payload = _payload()
    actions = {
        compiler.effective_parent_predicate(task_id, row): row["action"] for task_id, row in payload["tasks"].items()
    }

    def reasoned_false(command: str):
        satisfied = actions[command] in {"done", "superseded", "split"}
        return SimpleNamespace(
            returncode=0 if satisfied else 1,
            stdout="",
            stderr="owner predicate is not satisfied yet" if not satisfied else "",
        )

    assert compiler.check_parent_dispositions(payload, runner=reasoned_false) == {
        "terminal": 19,
        "nonterminal": 33,
    }

    def evaluation_error(command: str):
        return SimpleNamespace(returncode=2, stdout="", stderr="synthetic evaluator failure")

    with pytest.raises(compiler.MigrationError, match="could not be evaluated.*synthetic evaluator failure"):
        compiler.check_parent_dispositions(payload, runner=evaluation_error)


def test_task_keyed_pr_predicates_require_exact_body_and_preserve_extra_gates() -> None:
    compiler = _module()
    payload = _payload()

    simple = compiler.effective_parent_predicate(
        "RETRO-0708-HEAL-GATE",
        payload["tasks"]["RETRO-0708-HEAL-GATE"],
    )
    assert "--json body" in simple
    assert "test(" in simple
    assert "RETRO-0708-HEAL-GATE" in simple
    assert "--json number --jq length" not in simple
    token_pattern = compiler.task_pr_body_pattern("RETRO-0708-HEAL-GATE")
    assert compiler.re.search(token_pattern, "Closes `RETRO-0708-HEAL-GATE`.")
    assert not compiler.re.search(token_pattern, "Closes RETRO-0708-HEAL-GATE-FOLLOWUP.")
    assert not compiler.re.search(token_pattern, "Closes PREFIX-RETRO-0708-HEAL-GATE.")

    main_green = compiler.effective_parent_predicate(
        "GEN-organvm-manumissio-ci-green-0709",
        payload["tasks"]["GEN-organvm-manumissio-ci-green-0709"],
    )
    assert "GEN-organvm-manumissio-ci-green-0709" in main_green
    assert "repos/organvm/manumissio/commits/main" in main_green
    assert "--workflow ci.yml" in main_green

    ship = compiler.effective_parent_predicate(
        "REV-organvm-limen-revenue-ship-0708",
        payload["tasks"]["REV-organvm-limen-revenue-ship-0708"],
    )
    assert "scripts/ship-gate.py --check --task REV-organvm-limen-revenue-ship-0708" in ship
    assert "REV-organvm-limen-revenue-ship-0708" in ship


def test_keeper_archive_proves_children_and_rejection_fails_closed(tmp_path: Path) -> None:
    compiler = _module()
    payload = _payload()
    board = tmp_path / "tasks.yaml"
    save_limen_file(board, LimenFile())
    tickets = compiler.compile_child_tickets(
        payload,
        timestamp=compiler.parse_timestamp("2026-07-12T18:00:00Z"),
        agent="codex",
        session_id="test-session",
    )
    submission = compiler.submit_compiled_tickets(board, tickets)
    assert submission == {"submitted": 29, "pending": 0, "archived": 0}
    drained = drain_once(board)
    assert drained.applied == 29
    assert drained.rejected == 0
    assert compiler.verify_children_admitted(payload, board) == {"admitted": 29, "rejected": 0, "pending": 0}

    routed = load_limen_file(board)
    routed.tasks[0] = routed.tasks[0].model_copy(update={"target_agent": "claude"})
    save_limen_file(board, routed)
    assert compiler.verify_children_admitted(payload, board) == {"admitted": 29, "rejected": 0, "pending": 0}

    rejected = tickets_root(board) / "rejected" / f"{tickets[0].ticket_id}.json.reason.txt"
    rejected.parent.mkdir(parents=True, exist_ok=True)
    rejected.write_text("synthetic rejection evidence", encoding="utf-8")
    with pytest.raises(compiler.MigrationError, match="rejected keeper ticket"):
        compiler.verify_children_admitted(payload, board)


def test_phase_rejection_preflight_submits_no_prefix(tmp_path: Path) -> None:
    compiler = _module()
    payload = _payload()
    board = tmp_path / "tasks.yaml"
    save_limen_file(board, LimenFile())
    tickets = compiler.compile_child_tickets(
        payload,
        timestamp=compiler.parse_timestamp("2026-07-12T18:00:00Z"),
        agent="codex",
        session_id="reject-before-write",
    )
    rejected = tickets_root(board) / "rejected" / f"{tickets[-1].ticket_id}.json.reason.txt"
    rejected.parent.mkdir(parents=True, exist_ok=True)
    rejected.write_text("synthetic rejection evidence", encoding="utf-8")

    with pytest.raises(compiler.MigrationError, match="was rejected"):
        compiler.submit_compiled_tickets(board, tickets)
    assert not list((tickets_root(board) / "inbox").glob("*.json"))


def test_mid_publication_failure_rolls_back_only_this_exact_prefix(tmp_path: Path, monkeypatch) -> None:
    compiler = _module()
    payload = _payload()
    board = tmp_path / "tasks.yaml"
    save_limen_file(board, LimenFile())
    tickets = compiler.compile_child_tickets(
        payload,
        timestamp=compiler.parse_timestamp("2026-07-12T18:00:00Z"),
        agent="codex",
        session_id="rollback-prefix",
    )
    real_submit = compiler.submit_ticket
    calls = 0

    def flaky_submit(board_path, ticket):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("synthetic disk fault")
        return real_submit(board_path, ticket)

    monkeypatch.setattr(compiler, "submit_ticket", flaky_submit)
    with pytest.raises(compiler.MigrationError, match="removed 2 exact unconsumed ticket"):
        compiler.submit_compiled_tickets(board, tickets)
    assert not list((tickets_root(board) / "inbox").glob("*.json"))


def test_two_phase_keeper_round_trip_supports_raw_parent_tickets(tmp_path: Path) -> None:
    compiler = _module()
    payload = _payload()
    source = load_limen_file(BOARD)
    frozen = set(payload["frozen_ids"])
    board = tmp_path / "tasks.yaml"
    save_limen_file(board, LimenFile(tasks=[task for task in source.tasks if task.id in frozen]))
    timestamp = compiler.parse_timestamp("2026-07-12T18:00:00Z")
    kwargs = {"timestamp": timestamp, "agent": "codex", "session_id": "round-trip"}

    children = compiler.compile_child_tickets(payload, **kwargs)
    compiler.submit_compiled_tickets(board, children)
    child_drain = drain_once(board)
    assert (child_drain.applied, child_drain.rejected) == (29, 0)
    compiler.verify_children_admitted(payload, board)

    parents = compiler.compile_parent_tickets(payload, board, **kwargs)
    compiler.submit_compiled_tickets(board, parents)
    parent_drain = drain_once(board)
    assert (parent_drain.applied, parent_drain.rejected) == (52, 0)
    assert compiler.verify_parents_applied(payload, board) == {"verified": 52}

    retry_kwargs = {
        "timestamp": timestamp + timedelta(minutes=30),
        "agent": "agy",
        "session_id": "round-trip-retry",
    }
    parent_retry = compiler.compile_parent_tickets(payload, board, **retry_kwargs)
    assert [ticket.ticket_id for ticket in parent_retry] == [ticket.ticket_id for ticket in parents]
    assert compiler.submit_compiled_tickets(board, parent_retry) == {
        "submitted": 0,
        "pending": 0,
        "archived": 52,
    }
    assert compiler.verify_parents_applied(payload, board) == {"verified": 52}

    rejected = tickets_root(board) / "rejected" / f"{parents[0].ticket_id}.json.reason.txt"
    rejected.parent.mkdir(parents=True, exist_ok=True)
    rejected.write_text("synthetic parent rejection evidence", encoding="utf-8")
    with pytest.raises(compiler.MigrationError, match="rejected keeper ticket"):
        compiler.verify_parents_applied(payload, board)


def test_retry_identity_uses_first_honest_child_event_without_collision(tmp_path: Path) -> None:
    compiler = _module()
    payload = _payload()
    board = tmp_path / "tasks.yaml"
    save_limen_file(board, LimenFile())
    first = compiler.compile_child_tickets(
        payload,
        timestamp=compiler.parse_timestamp("2026-07-12T18:00:00Z"),
        agent="codex",
        session_id="first-invocation",
    )
    retry = compiler.compile_child_tickets(
        payload,
        timestamp=compiler.parse_timestamp("2026-07-12T19:00:00Z"),
        agent="agy",
        session_id="retry-invocation",
    )
    assert [ticket.ticket_id for ticket in first] == [ticket.ticket_id for ticket in retry]
    assert compiler.submit_compiled_tickets(board, first)["submitted"] == 29
    assert compiler.submit_compiled_tickets(board, retry) == {"submitted": 0, "pending": 29, "archived": 0}
    assert drain_once(board).applied == 29
    compiler.preflight_child_submission(payload, board, retry)
    assert compiler.submit_compiled_tickets(board, retry) == {"submitted": 0, "pending": 0, "archived": 29}

    child = {task.id: task for task in load_limen_file(board).tasks}[str(first[0].task_id)]
    assert len(child.dispatch_log) == 1
    assert child.dispatch_log[0].agent == "codex"
    assert child.dispatch_log[0].session_id == "first-invocation"


def test_concurrent_claim_invalidates_parent_exact_state_and_verification(tmp_path: Path) -> None:
    compiler = _module()
    payload = _payload()
    source = load_limen_file(BOARD)
    frozen = set(payload["frozen_ids"])
    board = tmp_path / "tasks.yaml"
    save_limen_file(board, LimenFile(tasks=[task for task in source.tasks if task.id in frozen]))
    timestamp = compiler.parse_timestamp("2026-07-12T18:00:00Z")
    kwargs = {"timestamp": timestamp, "agent": "codex", "session_id": "concurrent-parent"}
    children = compiler.compile_child_tickets(payload, **kwargs)
    compiler.submit_compiled_tickets(board, children)
    assert drain_once(board).applied == 29
    parents = compiler.compile_parent_tickets(payload, board, **kwargs)

    task_id = "DISCOVER-organvm-arca"
    row = payload["tasks"][task_id]
    claim = compiler.Ticket(
        ticket_id="concurrent-claim-before-parent",
        timestamp=timestamp - timedelta(seconds=1),
        agent="jules",
        session_id="concurrent-claim",
        intent="task.upsert",
        task_id=task_id,
        patch={
            "predicate": row["predicate"],
            "receipt_target": row["receipt_target"],
            "status": "dispatched",
        },
        log={"status": "dispatched", "output": "concurrent claim"},
    )
    compiler.submit_ticket(board, claim)
    compiler.submit_compiled_tickets(board, parents)
    drained = drain_once(board)
    assert drained.rejected == 1
    current = {task.id: task for task in load_limen_file(board).tasks}[task_id]
    assert current.status == "dispatched"
    with pytest.raises(compiler.MigrationError, match="rejected keeper ticket"):
        compiler.verify_parents_applied(payload, board)


@pytest.mark.parametrize("claim_status", ["dispatched", "in_progress"])
def test_later_same_batch_claim_rejects_parent_archive_and_verification(tmp_path: Path, claim_status: str) -> None:
    compiler = _module()
    payload = _payload()
    source = load_limen_file(BOARD)
    frozen = set(payload["frozen_ids"])
    board = tmp_path / "tasks.yaml"
    save_limen_file(board, LimenFile(tasks=[task for task in source.tasks if task.id in frozen]))
    timestamp = compiler.parse_timestamp("2026-07-12T18:00:00Z")
    kwargs = {"timestamp": timestamp, "agent": "codex", "session_id": f"later-{claim_status}"}
    children = compiler.compile_child_tickets(payload, **kwargs)
    compiler.submit_compiled_tickets(board, children)
    assert drain_once(board).applied == 29
    parents = compiler.compile_parent_tickets(payload, board, **kwargs)
    compiler.submit_compiled_tickets(board, parents)

    task_id = "DISCOVER-organvm-arca"
    row = payload["tasks"][task_id]
    later_claim = compiler.Ticket(
        ticket_id=f"later-{claim_status}-claim",
        timestamp=timestamp + timedelta(seconds=1),
        agent="jules",
        session_id=f"later-{claim_status}",
        intent="task.upsert",
        task_id=task_id,
        patch={
            "predicate": row["predicate"],
            "receipt_target": row["receipt_target"],
            "status": claim_status,
        },
        log={"status": claim_status, "output": "later same-batch claim"},
    )
    compiler.submit_ticket(board, later_claim)
    drained = drain_once(board)

    assert (drained.applied, drained.rejected) == (52, 1)
    current = {task.id: task for task in load_limen_file(board).tasks}[task_id]
    assert current.status == claim_status
    assert "archived" not in [entry.status for entry in current.dispatch_log]
    parent = next(ticket for ticket in parents if ticket.task_id == task_id)
    reason = (tickets_root(board) / "rejected" / f"{parent.ticket_id}.json.reason.txt").read_text()
    assert "invalidated regardless of timestamp order" in reason
    with pytest.raises(compiler.MigrationError, match="rejected keeper ticket"):
        compiler.verify_parents_applied(payload, board)


def test_apply_requires_explicit_timestamp_and_session_identity() -> None:
    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--phase",
            "children",
            "--apply",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "requires explicit --timestamp and --session-id" in result.stderr
