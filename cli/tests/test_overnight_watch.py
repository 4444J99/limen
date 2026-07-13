"""Tests for scripts/overnight-watch.py.

The monitor is deliberately one-shot by default: launchd can run it cheaply
without keeping an interactive agent conversation open for hours.
"""

from __future__ import annotations

import importlib.util
import json
import datetime as dt
import os
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "overnight-watch.py"


class _CP:
    def __init__(self, args, rc=0, stdout="", stderr=""):
        self.args = args
        self.returncode = rc
        self.stdout = stdout
        self.stderr = stderr


def _fresh_module(tmp_path, monkeypatch, **env):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    for key, value in env.items():
        monkeypatch.setenv(key, str(value))
    (tmp_path / "logs" / "async-runs").mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("overnight_watch_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _launchd_output(*, state="active", async_env="1", lanes="auto"):
    return f"""
state = {state}
pid = 4242
last exit code = (never exited)
environment = {{
    LIMEN_DISPATCH_ASYNC => {async_env}
    LIMEN_DISPATCH_LANES => {lanes}
}}
"""


def _mock_launchd(
    module,
    monkeypatch,
    stdout=None,
    rc=0,
    *,
    handoff_check_rc=0,
    gate_rc=0,
    gate_action="continue_current_work",
    gate_next_command="python3 scripts/session-value-review.py --gate --hours 1.5",
):
    calls = []

    def fake_run(args, timeout=10):
        calls.append(list(args))
        if args[:2] == ["launchctl", "print"]:
            return _CP(args, rc=rc, stdout=stdout if stdout is not None else _launchd_output())
        if str(module.HANDOFF_SCRIPT) in [str(arg) for arg in args]:
            if "--check" in args:
                if handoff_check_rc:
                    return _CP(args, rc=handoff_check_rc, stdout="handoff-relay --check: FAIL - stale")
                return _CP(args, rc=0, stdout="handoff-relay --check: OK - fresh")
            return _CP(args, rc=0, stdout="handoff-relay: wrote handoff.json")
        if str(module.SESSION_VALUE_SCRIPT) in [str(arg) for arg in args]:
            return _CP(
                args,
                rc=gate_rc,
                stdout=json.dumps(
                    {
                        "action": gate_action,
                        "exit_code": gate_rc,
                        "next_commands": [gate_next_command],
                    }
                ),
            )
        return _CP(args, rc=1, stderr="unexpected command")

    monkeypatch.setattr(module, "run", fake_run)
    return calls


def _owner_item(
    *,
    item_id="PRODUCT-OWNER",
    target_agent="codex",
    status="assigned_from_existing_work",
    priority=10,
    predicate="python3 scripts/product-ledger.py --write",
    receipt_target="git:organvm/limen:docs/product-ledger.md",
):
    return {
        "id": item_id,
        "title": f"Own {item_id}",
        "verdict": "current owner receipt proves bounded work remains",
        "workstream": "revenue-value-repos",
        "target_agent": target_agent,
        "priority": priority,
        "status": status,
        "assignment_packet": {
            "repo": "organvm/limen",
            "task": "Refresh the existing product owner receipt.",
            "predicate": predicate,
            "receipt_target": receipt_target,
            "stop_condition": "the owner receipt is current or names its external blocker",
        },
    }


def _prepare_lane_switch(module, monkeypatch, *, items=None, usage=None, admission=None):
    module.TASKS_PATH.write_text(
        json.dumps(
            {
                "version": "1.0",
                "portal": {
                    "budget": {
                        "daily": 100,
                        "per_agent": {"codex": 100, "jules": 100},
                        "track": {
                            "date": dt.date.today().isoformat(),
                            "spent": 0,
                            "per_agent": {},
                        },
                    }
                },
                "tasks": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    module.USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    module.USAGE_PATH.write_text(
        json.dumps(
            usage
            or {
                "generated": module.iso_now(),
                "vendors": {
                    "codex": {
                        "health": "ok",
                        "remaining": 50,
                        "headroom_pct": 50,
                        "effective_reserve_pct": 10,
                    },
                    "jules": {
                        "health": "ok",
                        "remaining": 50,
                        "headroom_pct": 50,
                        "effective_reserve_pct": 10,
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    snapshot = {
        "returncode": 0,
        "output": "",
        "snapshot": {"items": list(items if items is not None else [_owner_item()])},
    }
    monkeypatch.setattr(module, "always_working_snapshot", lambda: snapshot)
    monkeypatch.setattr(
        module,
        "take_admission_snapshot",
        lambda root: dict(
            admission
            or {
                "active": True,
                "block_new_local": False,
                "resource_blocked": False,
                "vitals_shed": False,
                "reaper_blocked": False,
                "reason": "",
            }
        ),
    )


def _write_heartbeat(module, tick="2026-07-01T09:53:57+00:00", open_count=63):
    module.HEARTBEAT_LOG.write_text(
        "\n".join(
            [
                "heartbeat-loop start",
                "──── beat 62 2026-07-01 05:50:29 ────",
                "  dispatch lanes: codex,claude,opencode,agy,gemini,github_actions from selector [auto]",
                "── async: reaped 0 dead · harvested 3 · 1 still running · launched 2 (cap 3) → ['A', 'B']",
                f"tick emitted: {tick} total=1555 open={open_count} spent=152/600",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_healthy_one_shot_writes_receipts(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    _mock_launchd(module, monkeypatch)
    _write_heartbeat(module)

    assert module.run_once(dry_run=False, json_output=False) == 0
    state = json.loads(module.STATE_PATH.read_text())
    assert state["status"] == "ok"
    assert module.RECEIPT_JSONL.exists()
    assert module.RECEIPT_MD.exists()
    assert not module.ALERT_PATH.exists()


def test_repeated_tick_alerts_when_no_workers(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch, LIMEN_OVERNIGHT_WATCH_MAX_STALE_TICKS=2)
    _mock_launchd(module, monkeypatch)
    _write_heartbeat(module)
    module.STATE_PATH.write_text(
        json.dumps({"latest_tick": "2026-07-01T09:53:57+00:00", "stale_tick_count": 1}),
        encoding="utf-8",
    )

    snapshot = module.build_snapshot()
    assert snapshot["status"] == "alert"
    assert {alert["id"] for alert in snapshot["alerts"]} == {"heartbeat-progress-stale"}


def test_active_worker_suppresses_repeated_tick_alert(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch, LIMEN_OVERNIGHT_WATCH_MAX_STALE_TICKS=2)
    _mock_launchd(module, monkeypatch)
    _write_heartbeat(module)
    module.STATE_PATH.write_text(
        json.dumps({"latest_tick": "2026-07-01T09:53:57+00:00", "stale_tick_count": 1}),
        encoding="utf-8",
    )
    (module.ASYNC_RUNS / "GEN-example__codex.running").write_text("{}", encoding="utf-8")

    snapshot = module.build_snapshot()
    assert snapshot["status"] == "ok"
    assert snapshot["worker_count"] == 1


def test_heartbeat_child_suppresses_repeated_tick_alert(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch, LIMEN_OVERNIGHT_WATCH_MAX_STALE_TICKS=2)
    _mock_launchd(module, monkeypatch)
    _write_heartbeat(module)
    module.STATE_PATH.write_text(
        json.dumps({"latest_tick": "2026-07-01T09:53:57+00:00", "stale_tick_count": 1}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module,
        "heartbeat_child_processes",
        lambda pid: [{"pid": "99", "command": "scripts/clone-maintenance.sh"}],
    )

    snapshot = module.build_snapshot()
    assert snapshot["status"] == "ok"
    assert snapshot["heartbeat_child_count"] == 1


def test_expected_env_mismatch_alerts(tmp_path, monkeypatch):
    module = _fresh_module(
        tmp_path,
        monkeypatch,
        LIMEN_OVERNIGHT_WATCH_EXPECT_DISPATCH_ASYNC=1,
        LIMEN_OVERNIGHT_WATCH_EXPECT_DISPATCH_LANES="auto",
    )
    _mock_launchd(module, monkeypatch, stdout=_launchd_output(async_env="0", lanes="codex"))
    _write_heartbeat(module)

    snapshot = module.build_snapshot()
    ids = {alert["id"] for alert in snapshot["alerts"]}
    assert "heartbeat-async-env-mismatch" in ids
    assert "heartbeat-lanes-env-mismatch" in ids


def test_stale_handoff_blocks_new_dispatch(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    _mock_launchd(module, monkeypatch, handoff_check_rc=1)
    _write_heartbeat(module)

    snapshot = module.build_snapshot()

    assert snapshot["status"] == "alert"
    assert snapshot["dispatch_control"]["allow_dispatch"] is False
    assert snapshot["dispatch_control"]["next_command"] == (
        "python3 scripts/handoff-relay.py && python3 scripts/handoff-relay.py --check"
    )
    assert "handoff-relay-stale" in {alert["id"] for alert in snapshot["alerts"]}


def test_value_gate_switch_blocks_generic_dispatch_without_watch_alert(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    calls = _mock_launchd(
        module,
        monkeypatch,
        gate_rc=10,
        gate_action="switch_to_packetization",
        gate_next_command="python3 scripts/prompt-packet-ledger.py --write",
    )
    _prepare_lane_switch(module, monkeypatch)
    _write_heartbeat(module)

    snapshot = module.build_snapshot()

    assert snapshot["status"] == "blocked"
    assert snapshot["alerts"] == []
    assert snapshot["dispatch_control"]["allow_dispatch"] is False
    assert snapshot["dispatch_control"]["exit_code"] == 10
    assert snapshot["lane_switch"]["status"] == "would_submit"
    assert snapshot["lane_switch"]["packet"]["predicate"] == "python3 scripts/product-ledger.py --write"
    assert snapshot["lane_switch"]["packet"]["receipt_target"] == "git:organvm/limen:docs/product-ledger.md"
    assert snapshot["overnight_counts"]["lane_switch_ticket_count"] == 0
    assert not (module.LOGS / "tickets").exists()
    assert not any("dispatch-async" in " ".join(call) for call in calls)


def test_value_gate_stop_switches_to_one_owner_packet_instead_of_alerting(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    _mock_launchd(
        module,
        monkeypatch,
        gate_rc=20,
        gate_action="stop_no_durable_progress",
        gate_next_command="python3 scripts/session-value-review.py --write --hours 12",
    )
    _prepare_lane_switch(
        module,
        monkeypatch,
        items=[_owner_item(item_id="FIRST", priority=10), _owner_item(item_id="SECOND", priority=20)],
    )
    _write_heartbeat(module)

    snapshot = module.build_snapshot()

    assert snapshot["status"] == "blocked"
    assert snapshot["alerts"] == []
    assert snapshot["value_gate"]["returncode"] == 20
    assert snapshot["dispatch_control"]["allow_dispatch"] is False
    assert snapshot["dispatch_control"]["exit_code"] == 10
    assert snapshot["lane_switch"]["status"] == "would_submit"
    assert snapshot["lane_switch"]["packet"]["task_id"].startswith("AW-FIRST-")
    assert "SECOND" not in snapshot["lane_switch"]["packet"]["task_id"]


def test_lane_switch_returns_named_owner_blocker_when_no_alternate_exists(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    _mock_launchd(module, monkeypatch, gate_rc=20, gate_action="stop_no_durable_progress")
    _prepare_lane_switch(module, monkeypatch, items=[_owner_item(status="blocked")])
    _write_heartbeat(module)

    snapshot = module.build_snapshot()

    assert snapshot["status"] == "alert"
    assert snapshot["lane_switch"]["status"] == "blocked"
    assert snapshot["lane_switch"]["blocker"] == {
        "id": "always-working-owner-blocked",
        "owner": "organvm/limen",
        "reason": "always-working owner item PRODUCT-OWNER is externally blocked",
        "failed_predicate": "python3 scripts/always-working.py --json",
        "next_command": "python3 scripts/always-working.py --write",
    }
    assert {alert["id"] for alert in snapshot["alerts"]} == {"overnight-lane-switch-blocked"}


def test_lane_switch_rejects_malformed_owner_packet_without_ticket(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    _prepare_lane_switch(
        module,
        monkeypatch,
        items=[_owner_item(receipt_target="not-durable")],
    )

    result = module.lane_switch_snapshot(
        {"value_gate": {"returncode": 10}, "handoff_relay": {"ok": True}},
        submit=True,
    )

    assert result["status"] == "blocked"
    assert result["blocker"]["id"] == "always-working-invalid-owner-packets"
    assert result["quarantined"][0]["item_id"] == "PRODUCT-OWNER"
    assert result["ticket_count"] == 0
    assert not (module.LOGS / "tickets").exists()


def test_lane_switch_quarantines_bad_first_candidate_and_launches_one_good_second(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    _prepare_lane_switch(
        module,
        monkeypatch,
        items=[
            _owner_item(item_id="BAD-FIRST", priority=1, receipt_target="not-durable"),
            _owner_item(item_id="GOOD-SECOND", priority=2),
        ],
    )
    launched = []

    def fake_dispatch(task, owner_state):
        launched.append((task.id, owner_state))
        return {"status": "launched", "targeted_launch_count": 1, "owner_state": "dispatched"}

    monkeypatch.setattr(module, "_drain_and_dispatch_one_owner_task", fake_dispatch)

    result = module.lane_switch_snapshot(
        {"value_gate": {"returncode": 10}, "handoff_relay": {"ok": True}},
        submit=True,
    )

    tickets = list((module.LOGS / "tickets" / "inbox").glob("*.json"))
    assert result["status"] == "launched"
    assert result["ticket_count"] == 1
    assert result["quarantined"] == [
        {
            "item_id": "BAD-FIRST",
            "gate": "intake",
            "reason": "receipt_target must name a durable GitHub receipt or repository-owned path",
        }
    ]
    assert len(launched) == 1
    assert launched[0][0].startswith("AW-GOOD-SECOND-")
    assert len(tickets) == 1
    payload = json.loads(tickets[0].read_text(encoding="utf-8"))
    assert payload["task_id"].startswith("AW-GOOD-SECOND-")


def test_lane_switch_fails_closed_when_tabularius_rejects_ticket(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    _prepare_lane_switch(module, monkeypatch)
    monkeypatch.setattr(
        module,
        "submit_task_upsert",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("invalid ticket")),
    )

    result = module.lane_switch_snapshot(
        {"value_gate": {"returncode": 10}, "handoff_relay": {"ok": True}},
        submit=True,
    )

    assert result["status"] == "blocked"
    assert result["blocker"]["id"] == "overnight-owner-ticket-rejected"
    assert result["ticket_count"] == 0
    assert list((module.LOGS / "tickets" / "inbox").glob("*.json")) == []


def test_lane_switch_provider_gate_blocks_measured_down_lane(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    _prepare_lane_switch(
        module,
        monkeypatch,
        usage={
            "generated": module.iso_now(),
            "vendors": {
                "codex": {
                    "health": "low",
                    "remaining": 10,
                    "headroom_pct": 5,
                    "effective_reserve_pct": 10,
                }
            },
        },
    )

    result = module.lane_switch_snapshot(
        {"value_gate": {"returncode": 10}, "handoff_relay": {"ok": True}},
        submit=False,
    )

    assert result["status"] == "blocked"
    assert {entry["gate"] for entry in result["skipped"]} == {"provider"}
    assert result["blocker"]["id"] == "overnight-owner-packets-gated"


def test_lane_switch_lifecycle_gate_blocks_new_local_packet(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    _prepare_lane_switch(
        module,
        monkeypatch,
        admission={
            "active": True,
            "block_new_local": True,
            "resource_blocked": False,
            "vitals_shed": False,
            "reaper_blocked": True,
            "reason": "accepted reaper has not reached fixed point",
        },
    )

    result = module.lane_switch_snapshot(
        {"value_gate": {"returncode": 10}, "handoff_relay": {"ok": True}},
        submit=False,
    )

    assert result["status"] == "blocked"
    assert {entry["gate"] for entry in result["skipped"]} == {"lifecycle"}


def test_lane_switch_resource_gate_skips_local_and_selects_remote(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    _prepare_lane_switch(
        module,
        monkeypatch,
        items=[
            _owner_item(item_id="LOCAL", target_agent="codex", priority=10),
            _owner_item(item_id="REMOTE", target_agent="jules", priority=20),
        ],
        admission={
            "active": True,
            "block_new_local": True,
            "resource_blocked": True,
            "vitals_shed": False,
            "reaper_blocked": False,
            "reason": "local free space is below the live floor",
        },
    )

    result = module.lane_switch_snapshot(
        {"value_gate": {"returncode": 20}, "handoff_relay": {"ok": True}},
        submit=False,
    )

    assert result["status"] == "would_submit"
    assert result["packet"]["target_agent"] == "jules"
    assert result["packet"]["task_id"].startswith("AW-REMOTE-")
    assert {entry["gate"] for entry in result["skipped"]} == {"resource"}


def test_lane_switch_drains_launches_exactly_one_and_is_idempotent(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    first_item = _owner_item(item_id="FIRST", priority=1)
    _prepare_lane_switch(
        module,
        monkeypatch,
        items=[first_item, _owner_item(item_id="SECOND", priority=2)],
    )
    snapshot = {"value_gate": {"returncode": 10}, "handoff_relay": {"ok": True}}
    expected = module.owner_task_from_item(first_item)
    calls = []

    def fake_run(args, timeout=10):
        calls.append(list(args))
        if str(module.TABULARIUS_SCRIPT) in [str(arg) for arg in args]:
            from limen.tabularius import drain_once

            result = drain_once(module.TASKS_PATH)
            assert result.applied == 1
            return _CP(args, rc=0, stdout="tabularius: sealed 1 ticket")
        if str(module.DISPATCH_ASYNC_SCRIPT) in [str(arg) for arg in args]:
            from limen.io import load_limen_file, save_limen_file

            board = load_limen_file(module.TASKS_PATH)
            task = next(task for task in board.tasks if task.id == expected.id)
            task.status = "dispatched"
            save_limen_file(module.TASKS_PATH, board)
            marker = module.ASYNC_RUNS / f"exact__{expected.target_agent}.running"
            marker.write_text(
                json.dumps({"task_id": expected.id, "agent": expected.target_agent, "pid": os.getpid()}),
                encoding="utf-8",
            )
            receipt = {
                "schema_version": "limen-targeted-dispatch.v1",
                "targeted_only": True,
                "task_id": expected.id,
                "launched": [[expected.target_agent, expected.id]],
                "launched_count": 1,
                "status": "launched",
            }
            return _CP(args, rc=0, stdout="dispatch detail\n" + json.dumps(receipt))
        return _CP(args, rc=1, stderr="unexpected command")

    monkeypatch.setattr(module, "run", fake_run)

    first = module.lane_switch_snapshot(snapshot, submit=True)
    second = module.lane_switch_snapshot(snapshot, submit=True)

    tickets = list((module.LOGS / "tickets" / "inbox").glob("*.json"))
    assert first["status"] == "launched"
    assert first["ticket_count"] == 1
    assert first["targeted_launch_count"] == 1
    assert second["status"] == "already_running"
    assert second["ticket_count"] == 0
    assert tickets == []
    assert len([call for call in calls if str(module.TABULARIUS_SCRIPT) in map(str, call)]) == 1
    dispatch_calls = [call for call in calls if str(module.DISPATCH_ASYNC_SCRIPT) in map(str, call)]
    assert len(dispatch_calls) == 1
    assert dispatch_calls[0][0] == os.sys.executable
    assert dispatch_calls[0][dispatch_calls[0].index("--task-id") + 1].startswith("AW-FIRST-")
    assert "--targeted-only" in dispatch_calls[0]
    assert "SECOND" not in first["packet"]["task_id"]


def test_lane_switch_zero_launch_is_named_blocker(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    item = _owner_item(item_id="ZERO")
    _prepare_lane_switch(module, monkeypatch, items=[item])

    def fake_run(args, timeout=10):
        if str(module.TABULARIUS_SCRIPT) in [str(arg) for arg in args]:
            from limen.tabularius import drain_once

            assert drain_once(module.TASKS_PATH).applied == 1
            return _CP(args, rc=0)
        if str(module.DISPATCH_ASYNC_SCRIPT) in [str(arg) for arg in args]:
            receipt = {
                "schema_version": "limen-targeted-dispatch.v1",
                "targeted_only": True,
                "task_id": module.owner_task_from_item(item).id,
                "launched": [],
                "launched_count": 0,
                "status": "zero_launch",
            }
            return _CP(args, rc=10, stdout=json.dumps(receipt))
        return _CP(args, rc=1)

    monkeypatch.setattr(module, "run", fake_run)

    result = module.lane_switch_snapshot(
        {"value_gate": {"returncode": 20}, "handoff_relay": {"ok": True}},
        submit=True,
    )

    assert result["status"] == "blocked"
    assert result["blocker"]["id"] == "overnight-owner-targeted-zero-launch"
    assert result["targeted_launch_count"] == 0
    assert result["generic_dispatch_allowed"] is False


def test_lane_switch_surfaces_named_execution_contract_mismatch(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    item = _owner_item(item_id="MISMATCH")
    _prepare_lane_switch(module, monkeypatch, items=[item])

    def fake_run(args, timeout=10):
        if str(module.TABULARIUS_SCRIPT) in [str(arg) for arg in args]:
            from limen.tabularius import drain_once

            assert drain_once(module.TASKS_PATH).applied == 1
            return _CP(args, rc=0)
        if str(module.DISPATCH_ASYNC_SCRIPT) in [str(arg) for arg in args]:
            receipt = {
                "schema_version": "limen-targeted-dispatch.v1",
                "targeted_only": True,
                "task_id": module.owner_task_from_item(item).id,
                "launched": [],
                "launched_count": 0,
                "status": "contract_mismatch",
                "blocker": {
                    "id": "targeted-execution-contract-mismatch",
                    "reason": "exact task changed before queue-locked reservation",
                },
            }
            return _CP(args, rc=10, stdout=json.dumps(receipt))
        return _CP(args, rc=1)

    monkeypatch.setattr(module, "run", fake_run)

    result = module.lane_switch_snapshot(
        {"value_gate": {"returncode": 10}, "handoff_relay": {"ok": True}},
        submit=True,
    )

    assert result["status"] == "blocked"
    assert result["blocker"]["id"] == "overnight-owner-execution-contract-mismatch"
    assert result["targeted_launch_count"] == 0


def test_lane_switch_dispatched_without_worker_receipt_fails_closed(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    item = _owner_item(item_id="ORPHAN")
    _prepare_lane_switch(module, monkeypatch, items=[item])
    from limen.models import DispatchLogEntry

    task = module.owner_task_from_item(item)
    old = module.utc_now() - dt.timedelta(minutes=2)
    task.status = "dispatched"
    task.updated = old
    task.dispatch_log.append(
        DispatchLogEntry(
            timestamp=old,
            agent=task.target_agent,
            session_id="async-reserve",
            status="dispatched",
            output="reserved before detached worker launch",
        )
    )
    board = json.loads(module.TASKS_PATH.read_text(encoding="utf-8"))
    board["tasks"] = [task.model_dump(mode="json", exclude_none=True)]
    module.TASKS_PATH.write_text(json.dumps(board) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        module,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("orphan must not relaunch")),
    )

    result = module.lane_switch_snapshot(
        {"value_gate": {"returncode": 10}, "handoff_relay": {"ok": True}},
        submit=True,
    )

    assert result["status"] == "blocked"
    assert result["blocker"]["id"] == "overnight-owner-claim-orphaned"
    assert result["owner_state"] == "dispatched"
    assert "--recover-task" in result["blocker"]["next_command"]
    assert "--execution-contract-hash" in result["blocker"]["next_command"]


def test_lane_switch_result_receipt_prevents_relaunch(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    item = _owner_item(item_id="RESULT")
    _prepare_lane_switch(module, monkeypatch, items=[item])
    task = module.owner_task_from_item(item)
    task.status = "dispatched"
    board = json.loads(module.TASKS_PATH.read_text(encoding="utf-8"))
    board["tasks"] = [task.model_dump(mode="json", exclude_none=True)]
    module.TASKS_PATH.write_text(json.dumps(board) + "\n", encoding="utf-8")
    (module.ASYNC_RUNS / "exact.result.json").write_text(
        json.dumps({"task_id": task.id, "agent": task.target_agent, "result": True}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("result must not relaunch")),
    )

    result = module.lane_switch_snapshot(
        {"value_gate": {"returncode": 10}, "handoff_relay": {"ok": True}},
        submit=True,
    )

    assert result["status"] == "result_pending_harvest"
    assert result["ticket_count"] == 0
    assert result["generic_dispatch_allowed"] is False


def test_lane_switch_next_command_uses_repo_owned_dispatch_script(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    task = module.owner_task_from_item(_owner_item())

    command = module._exact_task_command(task)
    argv = module._targeted_dispatch_argv(task)

    assert "scripts/dispatch-async.py" in command
    assert "--targeted-only" in command
    assert "--execution-contract-hash" in command
    assert "limen dispatch" not in command
    assert argv[0] == os.sys.executable
    assert argv[1] == str(module.DISPATCH_ASYNC_SCRIPT)
    assert argv[argv.index("--execution-contract-hash") + 1] == module.execution_contract_hash(task)


def test_alert_state_resolves(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch, LIMEN_OVERNIGHT_WATCH_MAX_STALE_TICKS=1)
    _mock_launchd(module, monkeypatch)
    _write_heartbeat(module)
    module.STATE_PATH.write_text(
        json.dumps({"latest_tick": "2026-07-01T09:53:57+00:00", "stale_tick_count": 0}),
        encoding="utf-8",
    )

    assert module.run_once(dry_run=False, json_output=False) == 1
    assert json.loads(module.ALERT_PATH.read_text())["active"] is True

    _write_heartbeat(module, tick="2026-07-01T10:02:43+00:00", open_count=65)
    assert module.run_once(dry_run=False, json_output=False) == 0
    assert json.loads(module.ALERT_PATH.read_text())["active"] is False


def _mock_missing_service(module, monkeypatch, *, bootstrap_rc=0, watchdog_missing=False):
    """launchctl print fails (service booted out); record bootstrap attempts."""
    calls = []

    def fake_run(args, timeout=10):
        calls.append(args)
        if args[:2] == ["launchctl", "print"]:
            missing = "com.limen.watchdog" in args[2] and watchdog_missing
            if "com.limen.heartbeat" in args[2] or missing:
                return _CP(args, rc=1, stderr='Could not find service "x" in domain for user gui: 501')
            return _CP(args, rc=0, stdout=_launchd_output())
        if args[:2] == ["launchctl", "bootstrap"]:
            return _CP(args, rc=bootstrap_rc)
        return _CP(args, rc=1, stderr="unexpected command")

    monkeypatch.setattr(module, "run", fake_run)
    return calls


def _bootstrap_calls(calls):
    return [args for args in calls if args[:2] == ["launchctl", "bootstrap"]]


def test_heal_bootstraps_missing_service(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    calls = _mock_missing_service(module, monkeypatch, watchdog_missing=True)
    _write_heartbeat(module)
    monkeypatch.setattr(module, "governor_mode", lambda: "dispatch")
    plists = tmp_path / "LaunchAgents"
    plists.mkdir()
    (plists / "com.limen.heartbeat.plist").write_text("<plist/>", encoding="utf-8")
    (plists / "com.limen.watchdog.plist").write_text("<plist/>", encoding="utf-8")
    monkeypatch.setattr(module, "LAUNCH_AGENTS", plists)

    assert module.run_once(dry_run=False, json_output=False) == 1
    bootstraps = _bootstrap_calls(calls)
    assert len(bootstraps) == 2
    assert bootstraps[0][3].endswith("com.limen.heartbeat.plist")
    assert bootstraps[1][3].endswith("com.limen.watchdog.plist")
    assert json.loads(module.STATE_PATH.read_text())["last_heal_at"]


def test_heal_respects_governor_pause(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    calls = _mock_missing_service(module, monkeypatch)
    _write_heartbeat(module)
    monkeypatch.setattr(module, "governor_mode", lambda: "paused")

    assert module.run_once(dry_run=False, json_output=False) == 1
    assert not _bootstrap_calls(calls)


def test_heal_respects_cooldown(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    calls = _mock_missing_service(module, monkeypatch)
    _write_heartbeat(module)
    monkeypatch.setattr(module, "governor_mode", lambda: "dispatch")
    module.STATE_PATH.write_text(
        json.dumps({"latest_tick": None, "stale_tick_count": 0, "last_heal_at": module.iso_now()}),
        encoding="utf-8",
    )

    assert module.run_once(dry_run=False, json_output=False) == 1
    assert not _bootstrap_calls(calls)


def test_heal_disabled_by_env(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch, LIMEN_OVERNIGHT_WATCH_HEAL=0)
    calls = _mock_missing_service(module, monkeypatch)
    _write_heartbeat(module)

    assert module.run_once(dry_run=False, json_output=False) == 1
    assert not _bootstrap_calls(calls)


def test_no_heal_when_service_loaded_but_unhealthy(tmp_path, monkeypatch):
    """A loaded-but-wedged daemon is watchdog.py's kickstart lane, not ours."""
    module = _fresh_module(tmp_path, monkeypatch)
    calls = []

    def fake_run(args, timeout=10):
        calls.append(args)
        if args[:2] == ["launchctl", "print"]:
            return _CP(args, rc=0, stdout=_launchd_output(state="waiting"))
        return _CP(args, rc=1, stderr="unexpected command")

    monkeypatch.setattr(module, "run", fake_run)
    _write_heartbeat(module)

    assert module.run_once(dry_run=False, json_output=False) == 1
    assert not _bootstrap_calls(calls)
