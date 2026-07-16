"""Tests for the ASYNC dispatch engine (scripts/dispatch-async.py) — the throughput-decoupling
path (fire detached workers + harvest, so a slow agent never gates the beat). Covers the pure
orchestration: concurrency cap, in-flight marker accounting, harvest-applies-results, and the
dead-worker reaper. Agent spawning (subprocess.Popen) is monkeypatched so no real agents run.
"""

import datetime
import contextlib
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest


CLI_SRC = Path(__file__).resolve().parents[1] / "src"
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "dispatch-async.py"
WORKER_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "async-run-one.py"
sys.path.insert(0, str(CLI_SRC))

from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.execution_contract import execution_contract_hash  # noqa: E402
from limen.models import Budget, BudgetTrack, DispatchLogEntry, LimenFile, Portal, Task  # noqa: E402
from limen.provider_selection import execution_profile_for  # noqa: E402
from limen.remote_execution import verification_context_for_task  # noqa: E402
from limen.remote_predicate import (  # noqa: E402
    SCHEMA_VERSION,
    canonical_json,
    digest_bytes,
    digest_text,
    packet_digest as compute_packet_digest,
)
import limen.dispatch as dispatch_module  # noqa: E402


def _load(tmp_path, n_open=6, agent="codex"):
    """Point the engine at an isolated tasks.yaml + build n open tasks, then import it fresh so its
    module-level ROOT/TASKS/RUNS pick up this env."""
    os.environ["LIMEN_ROOT"] = str(tmp_path)
    os.environ["LIMEN_TASKS"] = str(tmp_path / "tasks.yaml")
    os.environ["LIMEN_DISPATCH_ADMISSION"] = "0"
    os.environ["LIMEN_WORKTREE_DEBT_GATE"] = "0"
    today = datetime.date.today()
    lf = LimenFile(
        portal=Portal(budget=Budget(daily=300, per_agent={agent: 50}, track=BudgetTrack(date=today.isoformat()))),
        tasks=[
            Task(id=f"T{i}", title="t", repo="x/y", target_agent=agent, status="open", created=today)
            for i in range(n_open)
        ],
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)
    spec = importlib.util.spec_from_file_location("dispatch_async_under_test", SCRIPT)
    da = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(da)
    da.RUNS.mkdir(parents=True, exist_ok=True)
    return da


def _load_worker(tmp_path):
    os.environ["LIMEN_ROOT"] = str(tmp_path)
    os.environ["LIMEN_TASKS"] = str(tmp_path / "tasks.yaml")
    spec = importlib.util.spec_from_file_location("async_run_one_under_test", WORKER_SCRIPT)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    return worker


def _board(tmp_path):
    return {t.id: t for t in load_limen_file(tmp_path / "tasks.yaml").tasks}


def _remote_harvest_fixture(tmp_path):
    da = _load(tmp_path, n_open=1, agent="github_actions")
    lf = load_limen_file(tmp_path / "tasks.yaml")
    task = lf.tasks[0]
    task.type = "verification"
    task.labels = ["mode:verification-only"]
    task.depends_on = ["PARENT"]
    task.predicate = "python3 scripts/verify.py"
    task.receipt_target = f"artifact:organvm/limen:task:{task.id}"
    task.status = "dispatched"
    reservation_id = f"async-reserve:{'a' * 32}"
    task.dispatch_log.append(
        DispatchLogEntry(
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            agent="github_actions",
            session_id=reservation_id,
            status="dispatched",
        )
    )
    lf.tasks.append(
        Task(
            id="PARENT",
            title="implementation parent",
            repo=str(task.repo),
            type="code",
            target_agent="codex",
            status="done",
            receipt_target="github:x/y:pull-request:9",
            created=datetime.date.today(),
            dispatch_log=[
                DispatchLogEntry(
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                    agent="codex",
                    session_id="https://github.com/x/y/pull/9",
                    status="done",
                    output="merged https://github.com/x/y/pull/9",
                )
            ],
        )
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)

    tasks_by_id = {item.id: item for item in lf.tasks}
    context_digest = digest_bytes(canonical_json(verification_context_for_task(task, tasks_by_id)))
    execution_profile = execution_profile_for(task).as_dict()
    profile_digest = digest_bytes(canonical_json(execution_profile))
    instruction_digest = digest_text(
        f"Verify completed implementation for task {task.id}; do not modify code: {task.title}"
    )
    computed_packet_digest = compute_packet_digest(
        provider="github_actions",
        task_id=task.id,
        repo=str(task.repo),
        base_sha="a" * 40,
        control_repo="organvm/limen",
        control_ref="main",
        control_ref_kind="branch",
        control_sha="b" * 40,
        workflow_id=123,
        workflow_path=".github/workflows/limen-agent.yml",
        workflow_event="workflow_dispatch",
        verification_context_digest=context_digest,
        predicate_digest=digest_text(str(task.predicate).strip()),
        instruction_digest=instruction_digest,
        receipt_target=str(task.receipt_target),
        custody_mode="artifact",
        inputs=[],
        execution_profile=execution_profile,
    )
    request_id = computed_packet_digest.removeprefix("sha256:")[:32]
    metadata: dict[str, object] = {
        "provider": "github_actions",
        "task_id": task.id,
        "repo": task.repo,
        "provider_run_id": "42",
        "provider_url": "https://github.com/organvm/limen/actions/runs/42",
        "base_sha": "a" * 40,
        "control_repo": "organvm/limen",
        "control_ref": "main",
        "control_ref_kind": "branch",
        "control_sha": "b" * 40,
        "workflow_id": 123,
        "workflow_path": ".github/workflows/limen-agent.yml",
        "workflow_event": "workflow_dispatch",
        "verification_context_digest": context_digest,
        "remote_state": "queued",
        "remote_request_id": request_id,
        "packet_digest": computed_packet_digest,
    }
    request = {
        "provider": metadata["provider"],
        "task_id": metadata["task_id"],
        "repo": metadata["repo"],
        "base_sha": metadata["base_sha"],
        "control_repo": metadata["control_repo"],
        "control_ref": metadata["control_ref"],
        "control_ref_kind": metadata["control_ref_kind"],
        "control_sha": metadata["control_sha"],
        "workflow_id": metadata["workflow_id"],
        "workflow_path": metadata["workflow_path"],
        "workflow_event": metadata["workflow_event"],
        "verification_context_digest": metadata["verification_context_digest"],
        "predicate_digest": digest_text(str(task.predicate).strip()),
        "instruction_digest": instruction_digest,
        "receipt_target": task.receipt_target,
        "custody_mode": "artifact",
        "inputs": [],
        "execution_profile_digest": profile_digest,
        "packet_digest": computed_packet_digest,
    }
    run = {
        "provider": metadata["provider"],
        "provider_run_id": metadata["provider_run_id"],
        "url": metadata["provider_url"],
        "base_sha": metadata["base_sha"],
        "control_repo": metadata["control_repo"],
        "control_ref": metadata["control_ref"],
        "control_ref_kind": metadata["control_ref_kind"],
        "control_sha": metadata["control_sha"],
        "workflow_id": metadata["workflow_id"],
        "workflow_path": metadata["workflow_path"],
        "workflow_event": metadata["workflow_event"],
        "verification_context_digest": metadata["verification_context_digest"],
        "state": metadata["remote_state"],
        "request_id": request_id,
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "detail": "submission observed; not completion",
    }
    receipt: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "request": request,
        "run": run,
        "state": metadata["remote_state"],
        "predicate": None,
        "outputs": [],
        "observed_sha": None,
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "detail": "submission observed; not completion",
        "done": False,
    }
    receipt_dir = da.REMOTE_RECEIPT_ROOT / task.id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(canonical_json(receipt)).hexdigest()
    receipt_path = receipt_dir / f"{digest}.json"
    receipt_path.write_bytes(canonical_json(receipt) + b"\n")
    metadata["remote_receipt"] = str(receipt_path.relative_to(tmp_path))
    result = {
        "task_id": task.id,
        "agent": "github_actions",
        "reservation_id": reservation_id,
        "result": "42",
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "err": None,
        "execution_contract_hash": execution_contract_hash(task),
        "actual_execution_contract_hash": execution_contract_hash(task),
        "execution_started": True,
        "remote_submission": metadata,
    }
    return da, result, receipt


def _write_async_result(da, result):
    path = da._result_path(str(result["task_id"]), str(result["reservation_id"]))
    path.write_text(json.dumps(result))
    return path


def _rewrite_remote_receipt(tmp_path, da, result, receipt):
    digest = hashlib.sha256(canonical_json(receipt)).hexdigest()
    path = da.REMOTE_RECEIPT_ROOT / str(result["task_id"]) / f"{digest}.json"
    path.write_bytes(canonical_json(receipt) + b"\n")
    result["remote_submission"]["remote_receipt"] = str(path.relative_to(tmp_path))
    return path


def _assert_remote_harvest_blocked(tmp_path, da, result, *, marker_cleared: bool = True):
    before = (tmp_path / "tasks.yaml").read_bytes()
    da._write_running_marker(
        str(result["task_id"]),
        "github_actions",
        datetime.datetime.now(datetime.timezone.utc),
        os.getpid(),
        0.0,
        str(result["reservation_id"]),
    )
    result_path = _write_async_result(da, result)

    assert da.harvest() == 0
    assert (tmp_path / "tasks.yaml").read_bytes() == before
    assert not result_path.exists()
    markers = list(da.RUNS.glob("*.running"))
    assert (not markers) if marker_cleared else bool(markers)
    archives = sorted(da.RECEIPT_ARCHIVE.rglob("*.result.json"))
    assert archives
    blocker = json.loads(archives[-1].read_text())
    assert blocker["reason"] == "remote-metadata-blocked"
    assert blocker["blocker"]


def _contract_hash(tmp_path, task_id):
    return execution_contract_hash(_board(tmp_path)[task_id])


def _worktree_snapshot(*, blocked: bool, room_gib: float = 40.0) -> dict[str, object]:
    floor = 60.0
    return {
        "active": True,
        "block_new_local": blocked,
        "reason": "local worktree custody unavailable" if blocked else "",
        "resource_blocked": blocked,
        "vitals_shed": False,
        "reaper_blocked": False,
        "free_gib": floor + room_gib,
        "floor_gib": floor,
        "reserved_gib": 0.0,
        "room_gib": 0.0 if blocked else room_gib,
        "targets_present": False,
        "debt": 0,
        "vitals_action": "ok",
    }


def test_concurrency_cap_bounds_reservation(tmp_path):
    da = _load(tmp_path, n_open=6)
    picked = da.reserve_and_launch(["codex"], per_agent=8, cap=4, dry=True)
    assert len(picked) == 4  # cap (4) < open (6) and < per_agent (8)


def test_task_id_limits_async_reservation(tmp_path):
    da = _load(tmp_path, n_open=6)
    picked = da.reserve_and_launch(["codex"], per_agent=8, cap=4, dry=True, task_id="T3")
    assert picked == [("codex", "T3")]


def test_task_id_skips_broad_always_working_producer(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=2)

    def fail_always_working(*_args, **_kwargs):
        raise AssertionError("exact task reservation must not run the broad producer")

    monkeypatch.setattr(da, "run_always_working_before_dispatch", fail_always_working)

    assert da.reserve_and_launch(["codex"], 1, 1, True, task_id="T1") == [("codex", "T1")]


def test_exact_contract_is_revalidated_under_queue_lock_before_reservation(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=1)
    selected_hash = _contract_hash(tmp_path, "T0")
    board = load_limen_file(tmp_path / "tasks.yaml")
    board.tasks[0].context = "changed after owner selection"
    save_limen_file(tmp_path / "tasks.yaml", board)
    blocker = {}
    monkeypatch.setattr(
        da.subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("mismatched task must not spawn")),
    )

    picked = da.reserve_and_launch(
        ["codex"],
        per_agent=1,
        cap=1,
        dry=False,
        task_id="T0",
        admission_checked=True,
        expected_contract_hash=selected_hash,
        reservation_blocker=blocker,
    )

    current = _board(tmp_path)["T0"]
    assert picked == []
    assert current.status == "open"
    assert load_limen_file(tmp_path / "tasks.yaml").portal.budget.track.spent == 0
    assert blocker["id"] == "targeted-execution-contract-mismatch"
    assert blocker["expected_hash"] == selected_hash
    assert blocker["actual_hash"] == execution_contract_hash(current)


def test_targeted_zero_launch_blocker_names_capability_refusal(tmp_path):
    """Regression for the 2026-07-16 silent zero-launch wedge.

    A local lane may not run a mutating predicate against the self-modifying repo
    (``agent_can_run_task`` → ``_isolated_safe_task`` → narrow verification).  The dispatcher
    filtered the exact task silently — ``launched 0``, ``blocker: null`` — so the overnight lane
    could not route around it.  The named blocker must attribute the refusal.
    """

    da = _load(tmp_path, n_open=1)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    task = lf.tasks[0]
    task.repo = "organvm/limen"
    task.predicate = "python3 scripts/reclaim-generated-state.py --apply"
    task.receipt_target = "git:organvm/limen:docs/receipts.json"
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["codex"], 1, 1, True, task_id="T0", admission_checked=True)
    blocker = da._targeted_zero_launch_blocker("T0", ["codex"])

    assert picked == []
    assert blocker["id"] == "targeted-agent-capability-refused"
    assert "T0" in str(blocker["reason"])


def test_targeted_zero_launch_receipt_carries_named_blocker(tmp_path, monkeypatch, capsys):
    """main() must publish the named refusal in the targeted JSON receipt, never blocker: null."""

    da = _load(tmp_path, n_open=1)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    task = lf.tasks[0]
    task.repo = "organvm/limen"
    task.predicate = "python3 scripts/reclaim-generated-state.py --apply"
    task.receipt_target = "git:organvm/limen:docs/receipts.json"
    save_limen_file(tmp_path / "tasks.yaml", lf)
    contract_hash = _contract_hash(tmp_path, "T0")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dispatch-async.py",
            "--lanes",
            "codex",
            "--per-lane",
            "1",
            "--local-per-lane",
            "1",
            "--max",
            "1",
            "--task-id",
            "T0",
            "--execution-contract-hash",
            contract_hash,
            "--targeted-only",
            "--json-output",
            "--dry-run",
        ],
    )

    rc = da.main()
    out = capsys.readouterr().out
    receipt = json.loads([line for line in out.splitlines() if line.startswith("{")][-1])

    assert rc == 10
    assert receipt["status"] == "zero_launch"
    assert receipt["blocker"]["id"] == "targeted-agent-capability-refused"


def test_targeted_zero_launch_blocker_names_missing_and_terminal_tasks(tmp_path):
    da = _load(tmp_path, n_open=1)
    assert da._targeted_zero_launch_blocker("NOPE", ["codex"])["id"] == "targeted-task-missing"
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.tasks[0].status = "done"
    save_limen_file(tmp_path / "tasks.yaml", lf)
    assert da._targeted_zero_launch_blocker("T0", ["codex"])["id"] == "targeted-task-not-dispatchable"


def test_inflight_markers_consume_slots(tmp_path):
    da = _load(tmp_path, n_open=6)
    for i in range(4):
        (da.RUNS / f"R{i}__codex.running").write_text(datetime.datetime.now(datetime.timezone.utc).isoformat())
    picked = da.reserve_and_launch(["codex"], per_agent=8, cap=4, dry=True)
    assert picked == []  # 4 already running, cap 4 → 0 new


def test_inflight_markers_consume_per_lane_limit(tmp_path):
    da = _load(tmp_path, n_open=0)
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"codex": 50, "agy": 50}
    lf.tasks = [
        *[
            Task(id=f"C{i}", title="t", repo="x/y", target_agent="codex", status="open", created=today)
            for i in range(3)
        ],
        *[Task(id=f"A{i}", title="t", repo="x/y", target_agent="agy", status="open", created=today) for i in range(3)],
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)
    for i in range(2):
        (da.RUNS / f"RC{i}__codex.running").write_text(datetime.datetime.now(datetime.timezone.utc).isoformat())

    picked = da.reserve_and_launch(["codex", "agy"], per_agent=2, cap=6, dry=True)

    assert picked == [("agy", "A0"), ("agy", "A1")]


def test_running_marker_blocks_duplicate_task_reservation_across_agents(tmp_path):
    da = _load(tmp_path, n_open=0)
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"codex": 50, "claude": 50}
    lf.tasks = [Task(id="DUP", title="t", repo="x/y", target_agent="any", status="open", created=today)]
    save_limen_file(tmp_path / "tasks.yaml", lf)
    (da.RUNS / "DUP__codex.running").write_text(datetime.datetime.now(datetime.timezone.utc).isoformat())

    picked = da.reserve_and_launch(["claude"], per_agent=4, cap=4, dry=True)

    assert picked == []


def test_pending_result_blocks_duplicate_task_reservation_across_agents(tmp_path):
    da = _load(tmp_path, n_open=0)
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"codex": 50, "claude": 50}
    lf.tasks = [Task(id="DUP", title="t", repo="x/y", target_agent="any", status="open", created=today)]
    save_limen_file(tmp_path / "tasks.yaml", lf)
    (da.RUNS / "DUP.result.json").write_text(
        json.dumps({"task_id": "DUP", "agent": "codex", "result": "https://github.com/x/y/pull/9"})
    )

    picked = da.reserve_and_launch(["claude"], per_agent=4, cap=4, dry=True)

    assert picked == []


def test_agy_weak_proxy_can_reserve_against_daily_runway(tmp_path):
    da = _load(tmp_path, n_open=0)
    today = datetime.date.today()
    reset_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.daily = 5
    lf.portal.budget.per_agent = {"agy": 1}
    lf.portal.budget.track = BudgetTrack(
        date=today.isoformat(), spent=1, per_agent={"agy": 1}, per_agent_reset={"agy": reset_at}
    )
    lf.tasks = [
        Task(id=f"A{i}", title="t", repo="x/y", target_agent="agy", status="open", created=today) for i in range(2)
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "logs" / "usage.json").write_text(
        json.dumps(
            {
                "vendors": {
                    "agy": {
                        "health": "exhausted",
                        "signal": "dispatch-count",
                        "limit_source": "operator board cap until live vendor meter",
                        "remaining": 0,
                        "headroom_pct": 0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    picked = da.reserve_and_launch(["agy"], per_agent=4, cap=4, dry=True)

    assert picked == [("agy", "A0"), ("agy", "A1")]


def test_agy_recent_rate_limit_does_not_bypass_proxy_budget(tmp_path):
    da = _load(tmp_path, n_open=0)
    today = datetime.date.today()
    reset_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.daily = 5
    lf.portal.budget.per_agent = {"agy": 1}
    lf.portal.budget.track = BudgetTrack(
        date=today.isoformat(), spent=1, per_agent={"agy": 1}, per_agent_reset={"agy": reset_at}
    )
    lf.tasks = [Task(id="A0", title="t", repo="x/y", target_agent="agy", status="open", created=today)]
    save_limen_file(tmp_path / "tasks.yaml", lf)
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "logs" / "usage.json").write_text(
        json.dumps(
            {
                "vendors": {
                    "agy": {
                        "health": "rate-limited",
                        "signal": "dispatch-count",
                        "limit_source": "operator board cap until live vendor meter",
                        "recent_rate_limit": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    picked = da.reserve_and_launch(["agy"], per_agent=4, cap=4, dry=True)

    assert picked == []


def test_agy_skips_limen_registry_discovery_tasks(tmp_path):
    da = _load(tmp_path, n_open=0)
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"agy": 50, "codex": 50}
    lf.tasks = [
        Task(
            id="DISCOVER-organvm-browser-state",
            title="Discover latent value",
            repo="organvm/browser-state",
            target_agent="any",
            status="open",
            created=today,
            context='Append "organvm/browser-state" to value-repos.json and write DISCOVERY.md.',
        )
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)

    # ac8677b5 broadened the registry-promotion gate to ALL local lanes (_LOCAL_AGENTS),
    # so codex is now also blocked from running discovery tasks that edit value-repos.json.
    assert da.reserve_and_launch(["agy"], per_agent=4, cap=4, dry=True) == []
    assert da.reserve_and_launch(["agy", "codex"], per_agent=4, cap=4, dry=True) == []


def test_agy_codex_and_claude_skip_limen_repo_tasks(tmp_path):
    da = _load(tmp_path, n_open=0)
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"agy": 50, "codex": 50, "claude": 50}
    lf.tasks = [
        Task(
            id="HEAL-cifix-organvm-limen-999",
            title="Fix Limen CI",
            repo="organvm/limen",
            target_agent="any",
            status="open",
            created=today,
        )
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)

    assert da.reserve_and_launch(["agy"], per_agent=4, cap=4, dry=True) == []
    assert da.reserve_and_launch(["codex"], per_agent=4, cap=4, dry=True) == []
    assert da.reserve_and_launch(["claude"], per_agent=4, cap=4, dry=True) == []
    assert da.reserve_and_launch(["agy", "codex", "claude"], per_agent=4, cap=4, dry=True) == []


def test_claude_skips_organvm_engine_pr_repair_tasks(tmp_path):
    da = _load(tmp_path, n_open=0)
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"claude": 50, "codex": 50}
    lf.tasks = [
        Task(
            id="HEAL-cifix-organvm-organvm-engine-999",
            title="Fix organvm-engine CI",
            repo="organvm/organvm-engine",
            target_agent="any",
            status="open",
            created=today,
        )
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)

    assert da.reserve_and_launch(["claude"], per_agent=4, cap=4, dry=True) == []
    assert da.reserve_and_launch(["claude", "codex"], per_agent=4, cap=4, dry=True) == [
        ("codex", "HEAL-cifix-organvm-organvm-engine-999")
    ]


def test_async_remote_lane_not_gated_by_local_concurrency_cap(tmp_path):
    """A jules (async/remote) task runs OFF-BOX (a `jules remote new` session executes on Google's VM),
    so it must NOT be starved by the LOCAL concurrency cap even when local in-flight runs have consumed
    every slot. This is the 'zero jules remote sessions launched' root cause: the local cap saturated
    before jules's turn, so a jules-targeted task never got reserved."""
    da = _load(tmp_path, n_open=0)
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"codex": 50, "jules": 50}
    lf.tasks = [Task(id="JT", title="slow", repo="x/y", target_agent="jules", status="open", created=today)]
    save_limen_file(tmp_path / "tasks.yaml", lf)
    # local in-flight runs fully saturate the cap (4 local markers, cap 4)
    for i in range(4):
        (da.RUNS / f"L{i}__codex.running").write_text(datetime.datetime.now(datetime.timezone.utc).isoformat())

    picked = da.reserve_and_launch(["codex", "jules"], per_agent=8, cap=4, dry=True)

    assert picked == [("jules", "JT")], f"jules starved by the local concurrency cap: {picked}"


def test_async_remote_lane_is_bounded_by_live_usage_remaining(tmp_path):
    """Remote lanes skip the local host cap, but they must still honor the live provider/run meter.
    Board budget can lag the rolling provider window; dispatch should cap reservations to the
    provider remaining count when logs/usage.json has one."""
    da = _load(tmp_path, n_open=0)
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"codex": 50, "jules": 100}
    lf.tasks = [
        Task(id=f"JT{i}", title="slow", repo="x/y", target_agent="jules", status="open", created=today)
        for i in range(10)
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "logs" / "usage.json").write_text(
        json.dumps({"vendors": {"jules": {"remaining": 6, "possible": 100, "health": "ok"}}}),
        encoding="utf-8",
    )
    for i in range(4):
        (da.RUNS / f"L{i}__codex.running").write_text(datetime.datetime.now(datetime.timezone.utc).isoformat())

    picked = da.reserve_and_launch(["jules"], per_agent=100, cap=4, dry=True)

    assert len(picked) == 6
    assert [task_id for _, task_id in picked] == [f"JT{i}" for i in range(6)]


def test_remote_burst_does_not_expand_local_lane_room(tmp_path):
    """A Jules burst is provider-runway work, not local CPU work. When remote and local lanes share
    one command, the remote --per-lane value must not become the OpenCode/Agy local fan-out size."""
    da = _load(tmp_path, n_open=0)
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"jules": 100, "opencode": 100}
    lf.tasks = [
        *[
            Task(id=f"JT{i}", title="remote", repo="x/y", target_agent="jules", status="open", created=today)
            for i in range(10)
        ],
        *[
            Task(id=f"OT{i}", title="local", repo="x/y", target_agent="opencode", status="open", created=today)
            for i in range(10)
        ],
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "logs" / "usage.json").write_text(
        json.dumps({"vendors": {"jules": {"remaining": 10, "possible": 100, "health": "ok"}}}),
        encoding="utf-8",
    )

    picked = da.reserve_and_launch(
        ["jules", "opencode"],
        per_agent=10,
        cap=4,
        dry=True,
        local_per_agent=2,
    )

    assert [task_id for agent, task_id in picked if agent == "jules"] == [f"JT{i}" for i in range(10)]
    assert [task_id for agent, task_id in picked if agent == "opencode"] == ["OT0", "OT1"]


def test_local_lane_still_bounded_by_cap_after_async_carveout(tmp_path):
    """The carve-out is remote-only: a jules run in flight must NOT free a slot for local lanes, and a
    local lane is still hard-capped by the concurrency budget (no over-dispatch of the host)."""
    da = _load(tmp_path, n_open=6, agent="codex")
    # one jules run in flight (off-box) + 4 local runs in flight; cap is 4 → local slots already spent
    (da.RUNS / "JX__jules.running").write_text(datetime.datetime.now(datetime.timezone.utc).isoformat())
    for i in range(4):
        (da.RUNS / f"L{i}__codex.running").write_text(datetime.datetime.now(datetime.timezone.utc).isoformat())

    picked = da.reserve_and_launch(["codex"], per_agent=8, cap=4, dry=True)

    assert picked == [], f"local lane over-dispatched past the cap: {picked}"


def test_remote_lane_can_launch_when_local_cap_is_zero(tmp_path):
    da = _load(tmp_path, n_open=0)
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"jules": 100}
    lf.tasks = [Task(id="JT", title="remote", repo="x/y", target_agent="jules", status="open", created=today)]
    save_limen_file(tmp_path / "tasks.yaml", lf)
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "logs" / "usage.json").write_text(
        json.dumps({"vendors": {"jules": {"remaining": 1, "possible": 100, "health": "ok"}}}),
        encoding="utf-8",
    )

    assert da.should_reserve(per_agent=1, cap=0)
    assert da.reserve_and_launch(["jules"], per_agent=1, cap=0, dry=True) == [("jules", "JT")]


def test_default_max_age_exceeds_lane_timeout(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=0)
    monkeypatch.delenv("LIMEN_ASYNC_MAX_AGE", raising=False)
    monkeypatch.setenv("LIMEN_LANE_TIMEOUT", "1800")

    assert da.default_max_age_s() == 2100

    monkeypatch.setenv("LIMEN_ASYNC_MAX_AGE", "99")
    assert da.default_max_age_s() == 99


def test_async_numeric_env_knobs_fail_open_when_malformed(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=0)

    monkeypatch.setenv("LIMEN_ASYNC_MAX_AGE", "not-an-int")
    assert da.default_max_age_s() == 2100

    monkeypatch.delenv("LIMEN_ASYNC_MAX_AGE", raising=False)
    monkeypatch.setenv("LIMEN_LANE_TIMEOUT", "not-an-int")
    assert da.default_max_age_s() == 2100

    monkeypatch.setenv("LIMEN_LOCAL_LIMIT", "not-an-int")
    monkeypatch.setenv("LIMEN_ASYNC_MAX", "not-an-int")
    monkeypatch.setattr(da, "_down_lanes", lambda: set())
    monkeypatch.setattr(sys, "argv", ["dispatch-async.py", "--lanes", "codex", "--dry-run"])

    assert da.main() == 0


def test_default_local_max_tracks_live_host_cpu_count(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=0)
    monkeypatch.setattr(da.os, "cpu_count", lambda: 14)

    assert da._default_local_max() == 14

    monkeypatch.setattr(da.os, "cpu_count", lambda: None)
    assert da._default_local_max() == 1


def test_async_main_value_gate_blocks_reservation(tmp_path, monkeypatch, capsys):
    da = _load(tmp_path, n_open=2)
    monkeypatch.setenv("LIMEN_DISPATCH_ADMISSION", "1")
    monkeypatch.setattr(
        da,
        "dispatch_admission_check",
        lambda *args, **kwargs: {
            "allow": False,
            "status": "blocked",
            "exit_code": 10,
            "action": "switch_to_direct_product_work",
            "reason": "switch to direct product work",
            "next_command": "python3 scripts/product-ledger.py --refresh --redacted-summary",
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["dispatch-async.py", "--lanes", "codex", "--per-lane", "2", "--max", "2", "--dry-run"],
    )

    assert da.main() == 0

    output = capsys.readouterr().out
    assert "dispatch admission blocked" in output
    assert "would launch 0" in output


def test_harvest_applies_pr_result_and_cleans(tmp_path):
    da = _load(tmp_path, n_open=2)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.track.spent = 1
    lf.portal.budget.track.per_agent["codex"] = 1
    lf.tasks[0].status = "dispatched"
    lf.tasks[0].dispatch_log.append(
        DispatchLogEntry(
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            agent="codex",
            session_id="async-reserve",
            status="dispatched",
            output="dispatch-async: reserved before detached worker launch",
        )
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)
    contract_hash = execution_contract_hash(lf.tasks[0])
    (da.RUNS / "T0__codex.running").write_text(datetime.datetime.now(datetime.timezone.utc).isoformat())
    (da.RUNS / "T0.result.json").write_text(
        json.dumps(
            {
                "task_id": "T0",
                "agent": "codex",
                "result": "https://github.com/x/y/pull/9",
                "ts": "n",
                "err": None,
                "execution_contract_hash": contract_hash,
                "execution_started": True,
            }
        )
    )
    assert da.harvest() == 1
    t0 = _board(tmp_path)["T0"]
    assert any("pull/9" in str(e.session_id) for e in t0.dispatch_log)
    assert not (da.RUNS / "T0.result.json").exists()
    assert not (da.RUNS / "T0__codex.running").exists()
    track = load_limen_file(tmp_path / "tasks.yaml").portal.budget.track
    assert track.spent == 1
    assert track.per_agent["codex"] == 1


def test_remote_harvest_accepts_only_complete_hash_bound_identity(tmp_path):
    da, result, _receipt = _remote_harvest_fixture(tmp_path)
    _write_async_result(da, result)

    assert da.harvest() == 1
    task = _board(tmp_path)["T0"]
    entry = task.dispatch_log[-1]
    metadata = result["remote_submission"]
    assert entry.session_id == metadata["provider_run_id"]
    assert entry.provider_run_id == metadata["provider_run_id"]
    assert entry.provider_url == metadata["provider_url"]
    assert entry.base_sha == metadata["base_sha"]
    assert entry.control_ref == metadata["control_ref"]
    assert entry.control_ref_kind == metadata["control_ref_kind"]
    assert entry.control_sha == metadata["control_sha"]
    assert entry.workflow_id == metadata["workflow_id"]
    assert entry.workflow_path == metadata["workflow_path"]
    assert entry.workflow_event == metadata["workflow_event"]
    assert entry.verification_context_digest == metadata["verification_context_digest"]
    assert entry.remote_request_id == metadata["remote_request_id"]
    assert entry.remote_receipt == metadata["remote_receipt"]
    assert not dispatch_module._REMOTE_SUBMISSION_RECEIPTS


def test_remote_preflight_blocker_is_consumed_once_without_run_metadata(tmp_path):
    da, result, _receipt = _remote_harvest_fixture(tmp_path)
    result["result"] = "__failed_blocked__:control workflow unavailable"
    result["remote_submission"] = {}
    result_path = _write_async_result(da, result)

    assert da.harvest() == 1
    task = _board(tmp_path)["T0"]
    assert task.status == "failed_blocked"
    assert task.dispatch_log[-1].status == "failed_blocked"
    assert task.dispatch_log[-1].output == "control workflow unavailable"
    assert not result_path.exists()
    assert da.harvest() == 0
    assert sum(entry.status == "failed_blocked" for entry in _board(tmp_path)["T0"].dispatch_log) == 1


def test_forged_remote_preflight_blocker_cannot_cross_execution_contract(tmp_path):
    da, result, _receipt = _remote_harvest_fixture(tmp_path)
    board = load_limen_file(tmp_path / "tasks.yaml")
    board.tasks[0].title = "changed after the worker snapshot"
    save_limen_file(tmp_path / "tasks.yaml", board)
    result["result"] = "__failed_blocked__:forged blocker"
    result["remote_submission"] = {}

    _assert_remote_harvest_blocked(tmp_path, da, result, marker_cleared=False)
    assert _board(tmp_path)["T0"].status == "dispatched"


def test_remote_harvest_rejects_result_run_id_that_differs_from_submission(tmp_path):
    da, result, _receipt = _remote_harvest_fixture(tmp_path)
    result["result"] = "99"
    _assert_remote_harvest_blocked(tmp_path, da, result)


@pytest.mark.parametrize("bad_task_id", [[], {}])
def test_remote_harvest_blocks_unhashable_task_id_without_board_mutation(tmp_path, bad_task_id):
    da, result, _receipt = _remote_harvest_fixture(tmp_path)
    result["task_id"] = bad_task_id
    before = (tmp_path / "tasks.yaml").read_bytes()
    path = da.RUNS / "00-malformed-remote.result.json"
    path.write_text(json.dumps(result))

    assert da.harvest() == 0
    assert (tmp_path / "tasks.yaml").read_bytes() == before
    assert not path.exists()
    archives = sorted(da.RECEIPT_ARCHIVE.rglob("*.result.json"))
    blocker = json.loads(archives[-1].read_text())
    assert blocker["reason"] == "remote-metadata-blocked"
    assert blocker["blocker"] == "async result task ID is missing or non-string"


def test_malformed_remote_task_id_does_not_starve_later_valid_result(tmp_path):
    da, valid, _receipt = _remote_harvest_fixture(tmp_path)
    malformed = dict(valid)
    malformed["task_id"] = []
    (da.RUNS / "00-malformed-remote.result.json").write_text(json.dumps(malformed))
    valid_path = _write_async_result(da, valid)

    assert da.harvest() == 1
    assert not valid_path.exists()
    assert _board(tmp_path)["T0"].dispatch_log[-1].provider_run_id == "42"


@pytest.mark.parametrize(
    "missing_field",
    [
        "provider",
        "task_id",
        "repo",
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
        "packet_digest",
        "remote_receipt",
    ],
)
def test_remote_harvest_rejects_each_incomplete_identity_without_board_mutation(
    tmp_path,
    missing_field,
):
    da, result, _receipt = _remote_harvest_fixture(tmp_path)
    result["remote_submission"].pop(missing_field)
    _assert_remote_harvest_blocked(tmp_path, da, result)


@pytest.mark.parametrize(
    ("field", "contradiction"),
    [
        ("provider", "renamed-actions"),
        ("task_id", "OTHER"),
        ("repo", "other/repo"),
        ("provider_run_id", "43"),
        ("provider_url", "https://github.com/organvm/limen/actions/runs/43"),
        ("base_sha", "9" * 40),
        ("control_repo", "other/control"),
        ("control_ref", "other"),
        ("control_ref_kind", "tag"),
        ("control_sha", "8" * 40),
        ("workflow_id", 456),
        ("workflow_path", ".github/workflows/other.yml"),
        ("workflow_event", "push"),
        ("verification_context_digest", f"sha256:{'7' * 64}"),
        ("remote_state", "running"),
        ("remote_request_id", "6" * 32),
        ("packet_digest", f"sha256:{'5' * 64}"),
    ],
)
def test_remote_harvest_rejects_each_contradictory_identity_without_board_mutation(
    tmp_path,
    field,
    contradiction,
):
    da, result, _receipt = _remote_harvest_fixture(tmp_path)
    result["remote_submission"][field] = contradiction
    if field == "provider_run_id":
        result["result"] = contradiction
    if field == "provider":
        result["agent"] = contradiction
    _assert_remote_harvest_blocked(tmp_path, da, result, marker_cleared=field != "provider")


@pytest.mark.parametrize(
    ("section", "field", "contradiction"),
    [
        ("request", "control_ref", "other"),
        ("request", "verification_context_digest", f"sha256:{'4' * 64}"),
        ("run", "provider_run_id", "43"),
        ("run", "control_ref_kind", "tag"),
        ("run", "workflow_event", "push"),
    ],
)
def test_remote_harvest_rejects_internal_request_run_contradictions(
    tmp_path,
    section,
    field,
    contradiction,
):
    da, result, receipt = _remote_harvest_fixture(tmp_path)
    receipt[section][field] = contradiction
    _rewrite_remote_receipt(tmp_path, da, result, receipt)
    _assert_remote_harvest_blocked(tmp_path, da, result)


def test_remote_harvest_rejects_incomplete_content_addressed_receipt(tmp_path):
    da, result, receipt = _remote_harvest_fixture(tmp_path)
    receipt["request"].pop("verification_context_digest")
    _rewrite_remote_receipt(tmp_path, da, result, receipt)
    _assert_remote_harvest_blocked(tmp_path, da, result)


def test_remote_harvest_rejects_receipt_hash_mismatch(tmp_path):
    da, result, receipt = _remote_harvest_fixture(tmp_path)
    path = tmp_path / result["remote_submission"]["remote_receipt"]
    receipt["detail"] = "tampered without content-address update"
    path.write_bytes(canonical_json(receipt) + b"\n")
    _assert_remote_harvest_blocked(tmp_path, da, result)


def test_remote_harvest_rejects_self_consistent_forged_packet_digest(tmp_path):
    da, result, receipt = _remote_harvest_fixture(tmp_path)
    forged_packet = f"sha256:{'0' * 64}"
    forged_request_id = forged_packet.removeprefix("sha256:")[:32]
    receipt["request"]["packet_digest"] = forged_packet
    receipt["run"]["request_id"] = forged_request_id
    result["remote_submission"]["packet_digest"] = forged_packet
    result["remote_submission"]["remote_request_id"] = forged_request_id
    _rewrite_remote_receipt(tmp_path, da, result, receipt)

    _assert_remote_harvest_blocked(tmp_path, da, result)


def test_remote_harvest_rejects_receipt_outside_configured_custody(tmp_path):
    da, result, receipt = _remote_harvest_fixture(tmp_path)
    path = tmp_path / f"{hashlib.sha256(canonical_json(receipt)).hexdigest()}.json"
    path.write_bytes(canonical_json(receipt) + b"\n")
    result["remote_submission"]["remote_receipt"] = str(path.relative_to(tmp_path))
    _assert_remote_harvest_blocked(tmp_path, da, result)


def test_remote_harvest_rejects_hash_valid_receipt_in_sibling_task_custody(tmp_path):
    da, result, receipt = _remote_harvest_fixture(tmp_path)
    digest = hashlib.sha256(canonical_json(receipt)).hexdigest()
    sibling = da.REMOTE_RECEIPT_ROOT / "OTHER-TASK" / f"{digest}.json"
    sibling.parent.mkdir(parents=True)
    sibling.write_bytes(canonical_json(receipt) + b"\n")
    result["remote_submission"]["remote_receipt"] = str(sibling.relative_to(tmp_path))
    _assert_remote_harvest_blocked(tmp_path, da, result)


def test_remote_harvest_rejects_symlinked_task_custody_outside_remote_root(tmp_path):
    da, result, receipt = _remote_harvest_fixture(tmp_path)
    digest = hashlib.sha256(canonical_json(receipt)).hexdigest()
    task_root = da.REMOTE_RECEIPT_ROOT / str(result["task_id"])
    for child in task_root.iterdir():
        child.unlink()
    task_root.rmdir()
    external = tmp_path / "external-task-custody"
    external.mkdir()
    (external / f"{digest}.json").write_bytes(canonical_json(receipt) + b"\n")
    task_root.symlink_to(external, target_is_directory=True)

    _assert_remote_harvest_blocked(tmp_path, da, result)


def test_remote_harvest_rejects_stale_result_after_newer_authoritative_reroute(tmp_path):
    da, result, _receipt = _remote_harvest_fixture(tmp_path)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    task = lf.tasks[0]
    task.status = "open"
    task.target_agent = "codex"
    task.dispatch_log.append(
        DispatchLogEntry(
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            agent="codex",
            session_id="manual-reroute",
            status="open",
            output="newer authoritative reroute",
        )
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)

    _assert_remote_harvest_blocked(tmp_path, da, result, marker_cleared=False)


def test_remote_harvest_rejects_old_same_agent_result_after_new_reservation(tmp_path):
    da, result, _receipt = _remote_harvest_fixture(tmp_path)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    task = next(item for item in lf.tasks if item.id == result["task_id"])
    task.title = "changed verification contract"
    task.predicate = "python3 scripts/check-other.py"
    task.dispatch_log.append(
        DispatchLogEntry(
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            agent="github_actions",
            session_id=f"async-reserve:{'b' * 32}",
            status="dispatched",
            output="newer same-agent reservation",
        )
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)

    _assert_remote_harvest_blocked(tmp_path, da, result, marker_cleared=False)


def test_remote_harvest_rejects_changed_current_contract_even_with_replayed_nonce(tmp_path):
    da, result, _receipt = _remote_harvest_fixture(tmp_path)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    task = next(item for item in lf.tasks if item.id == result["task_id"])
    task.title = "changed after reservation"
    save_limen_file(tmp_path / "tasks.yaml", lf)

    _assert_remote_harvest_blocked(tmp_path, da, result, marker_cleared=False)


def test_superseded_worker_never_calls_provider_or_overwrites_new_attempt(tmp_path, monkeypatch):
    _load(tmp_path, n_open=1, agent="github_actions")
    old_reservation = f"async-reserve:{'a' * 32}"
    current_reservation = f"async-reserve:{'b' * 32}"
    lf = load_limen_file(tmp_path / "tasks.yaml")
    task = lf.tasks[0]
    task.status = "dispatched"
    task.dispatch_log.append(
        DispatchLogEntry(
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            agent="github_actions",
            session_id=current_reservation,
            status="dispatched",
        )
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)
    contract_hash = execution_contract_hash(task)

    worker = _load_worker(tmp_path)
    worker.RUNS.mkdir(parents=True, exist_ok=True)
    old_marker = worker._running_marker_path(task.id, "github_actions", old_reservation)
    new_marker = worker._running_marker_path(task.id, "github_actions", current_reservation)
    old_marker.write_text("old")
    new_marker.write_text("new")
    new_result = worker._result_path(task.id, current_reservation)
    new_result.write_text("new-attempt-result")
    monkeypatch.setattr(
        worker,
        "call_agent_dispatch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("stale worker called provider")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "async-run-one.py",
            "--agent",
            "github_actions",
            "--task-id",
            task.id,
            "--reservation-id",
            old_reservation,
            "--execution-contract-hash",
            contract_hash,
        ],
    )

    assert worker.main() == 10
    old_result = json.loads(worker._result_path(task.id, old_reservation).read_text())
    assert old_result["result"] == "__notask__"
    assert old_result["validation_failure"]["id"] == "async-execution-claim-owner-mismatch"
    assert new_result.read_text() == "new-attempt-result"
    assert not old_marker.exists()
    assert new_marker.exists()


def test_reserve_and_launch_marks_and_spawns(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=6)
    calls = []
    monkeypatch.setattr(da.subprocess, "Popen", lambda *a, **k: calls.append(a) or type("P", (), {"pid": 1})())
    picked = da.reserve_and_launch(["codex"], per_agent=2, cap=8, dry=False)
    assert len(picked) == 2 and len(calls) == 2
    dispatched = [t for t in load_limen_file(tmp_path / "tasks.yaml").tasks if t.status == "dispatched"]
    assert len(dispatched) == 2
    assert all(t.dispatch_log[-1].status == "dispatched" for t in dispatched)
    reservation_ids = [t.dispatch_log[-1].session_id for t in dispatched]
    assert all(re.fullmatch(r"async-reserve:[0-9a-f]{32}", value) for value in reservation_ids)
    assert len(set(reservation_ids)) == len(reservation_ids)
    assert all(t.predicate and t.receipt_target for t in dispatched)
    current = {task.id: task for task in dispatched}
    for call in calls:
        argv = call[0]
        assert "--reservation-id" in argv
        task_id = argv[argv.index("--task-id") + 1]
        contract_hash = argv[argv.index("--execution-contract-hash") + 1]
        assert contract_hash == execution_contract_hash(current[task_id])
    assert len(list(da.RUNS.glob("*__codex--*.running"))) == 2
    track = load_limen_file(tmp_path / "tasks.yaml").portal.budget.track
    assert track.spent == 2
    assert track.per_agent["codex"] == 2


def test_spawn_failure_reopens_refunds_and_releases_machine_lease(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=1)
    monkeypatch.setattr(da.subprocess, "Popen", lambda *_a, **_k: (_ for _ in ()).throw(OSError("no spawn")))

    assert da.reserve_and_launch(["codex"], per_agent=1, cap=1, dry=False) == []

    task = _board(tmp_path)["T0"]
    assert task.status == "open"
    assert task.dispatch_log[-1].session_id == "async-launch-failed"
    assert load_limen_file(tmp_path / "tasks.yaml").portal.budget.track.spent == 0
    assert not dispatch_module._admission_lease_path("T0").exists()


def test_marker_failure_keeps_child_owned_machine_lease(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=1)
    monkeypatch.setattr(da.subprocess, "Popen", lambda *_a, **_k: type("P", (), {"pid": os.getpid()})())
    monkeypatch.setattr(da, "_write_running_marker", lambda *_a, **_k: (_ for _ in ()).throw(OSError("disk")))

    assert da.reserve_and_launch(["codex"], per_agent=1, cap=1, dry=False) == [("codex", "T0")]

    lease = dispatch_module._admission_lease_path("T0")
    payload = json.loads(lease.read_text())
    assert payload["phase"] == "worker-live-marker-failed"
    assert payload["pid"] == os.getpid()
    assert not list(da.RUNS.glob("T0__codex*.running"))
    dispatch_module._release_machine_admission("T0")


def test_async_marker_holds_checkout_room_until_worktree_birth(tmp_path):
    da = _load(tmp_path, n_open=0)
    now = da._now()
    da._write_running_marker("PENDING-WT", "codex", now, os.getpid(), 0.75)
    snapshot = _worktree_snapshot(blocked=False, room_gib=1.0)

    with dispatch_module._machine_admission_lock():
        promised, used_slots = dispatch_module._snapshot_with_machine_reservations(snapshot)
    assert used_slots == 1
    assert promised["reserved_gib"] == 0.75
    assert promised["room_gib"] == 0.25

    dispatch_module._mark_machine_admission_born("PENDING-WT")
    marker_payload = json.loads(da._running_marker_path("PENDING-WT", "codex").read_text())
    assert marker_payload["reserved_gib"] == 0.0
    da._running_marker_path("PENDING-WT", "codex").unlink()


def test_two_async_processes_cannot_reuse_slot_before_first_marker_exists(tmp_path):
    """The durable lease closes the board-save -> running-marker cross-process race."""
    da = _load(tmp_path, n_open=2)
    ready = tmp_path / "first-at-spawn"
    release = tmp_path / "release-first"
    first_out = tmp_path / "first.json"
    second_out = tmp_path / "second.json"
    env = {
        **os.environ,
        "LIMEN_ROOT": str(tmp_path),
        "LIMEN_TASKS": str(tmp_path / "tasks.yaml"),
        "LIMEN_DISPATCH_ADMISSION": "0",
        "LIMEN_WORKTREE_DEBT_GATE": "0",
        "LIMEN_ALWAYS_WORKING_BEFORE_DISPATCH": "0",
        "PYTHONPATH": str(CLI_SRC),
    }
    first_code = f"""
import importlib.util, json, os, time
from pathlib import Path
spec = importlib.util.spec_from_file_location('dispatch_async_child_one', {str(SCRIPT)!r})
da = importlib.util.module_from_spec(spec)
spec.loader.exec_module(da)
class FakeProc:
    pid = os.getpid()
def fake_popen(*args, **kwargs):
    Path({str(ready)!r}).write_text('ready')
    while not Path({str(release)!r}).exists():
        time.sleep(0.01)
    return FakeProc()
da.subprocess.Popen = fake_popen
picked = da.reserve_and_launch(['codex'], per_agent=1, cap=1, dry=False)
Path({str(first_out)!r}).write_text(json.dumps(picked))
"""
    second_code = f"""
import importlib.util, json
from pathlib import Path
spec = importlib.util.spec_from_file_location('dispatch_async_child_two', {str(SCRIPT)!r})
da = importlib.util.module_from_spec(spec)
spec.loader.exec_module(da)
def must_not_spawn(*args, **kwargs):
    raise AssertionError('second process reused the reserved local slot')
da.subprocess.Popen = must_not_spawn
picked = da.reserve_and_launch(['codex'], per_agent=1, cap=1, dry=False)
Path({str(second_out)!r}).write_text(json.dumps(picked))
"""
    first = subprocess.Popen([sys.executable, "-c", first_code], env=env)
    deadline = time.monotonic() + 10
    while not ready.exists() and first.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ready.exists(), "first dispatcher never reached the pre-marker barrier"
    try:
        second = subprocess.run(
            [sys.executable, "-c", second_code],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert second.returncode == 0, second.stderr
        assert json.loads(second_out.read_text()) == []
        # The first worker is still paused before writing its marker: only the machine lease can
        # have denied process two.
        assert not list(da.RUNS.glob("*.running"))
    finally:
        release.write_text("go")
        first.wait(timeout=10)
    assert first.returncode == 0
    assert len(json.loads(first_out.read_text())) == 1


def test_async_normalizes_only_selected_legacy_task(tmp_path):
    da = _load(tmp_path, n_open=0)
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.tasks = [
        Task(id="SELECTED", title="selected", repo="x/y", target_agent="codex", priority="critical", created=today),
        Task(id="UNSELECTED", title="unselected", repo="x/y", target_agent="codex", priority="low", created=today),
    ]

    picked, _reset_changed = da._pick_reservations(
        lf,
        ["codex"],
        per_agent=1,
        cap=1,
        dry=True,
        now=datetime.datetime.now(datetime.timezone.utc),
        usage_remaining={},
        weak_proxy_agents=set(),
    )

    assert picked == [("codex", "SELECTED")]
    assert lf.tasks[0].predicate and lf.tasks[0].receipt_target
    assert lf.tasks[1].predicate is None and lf.tasks[1].receipt_target is None


def test_async_skips_unowned_legacy_candidate_and_continues(tmp_path, capsys):
    da = _load(tmp_path, n_open=0)
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.tasks = [
        Task(id="UNOWNED", title="unowned", target_agent="codex", priority="critical", created=today),
        Task(id="OWNED", title="owned", repo="x/y", target_agent="codex", priority="high", created=today),
    ]

    picked, _reset_changed = da._pick_reservations(
        lf,
        ["codex"],
        per_agent=1,
        cap=1,
        dry=True,
        now=datetime.datetime.now(datetime.timezone.utc),
        usage_remaining={},
        weak_proxy_agents=set(),
    )

    assert picked == [("codex", "OWNED")]
    assert lf.tasks[0].predicate is None and lf.tasks[0].status == "open"
    assert "INTAKE BLOCKED UNOWNED" in capsys.readouterr().out


def test_dry_run_does_not_pick_same_any_task_for_multiple_lanes(tmp_path):
    da = _load(tmp_path, n_open=0)
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"codex": 50, "agy": 50}
    lf.tasks = [Task(id="ANY", title="t", repo="x/y", target_agent="any", status="open", created=today)]
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["codex", "agy"], per_agent=1, cap=2, dry=True)

    assert picked == [("codex", "ANY")]
    assert _board(tmp_path)["ANY"].status == "open"


def test_reserve_skips_generated_buildout_outside_value_tier(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_VALUE_REPOS", "x/y")
    monkeypatch.setenv("LIMEN_VALUE_REPOS_FILE", str(tmp_path / "no-such-tier.json"))
    da = _load(tmp_path, n_open=0)
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.tasks = [
        Task(
            id="GEN-NONVALUE",
            title="generated",
            repo="x/site.github.io",
            target_agent="codex",
            status="open",
            labels=["test-coverage", "generated", "build-out"],
            created=today,
        ),
        Task(id="VALUE-WORK", title="value", repo="x/y", target_agent="codex", status="open", created=today),
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["codex"], per_agent=5, cap=5, dry=True)

    assert picked == [("codex", "VALUE-WORK")]


def test_async_prefers_value_repo_over_higher_priority_generic_churn(tmp_path, monkeypatch):
    monkeypatch.delenv("LIMEN_VALUE_REPOS", raising=False)
    monkeypatch.delenv("LIMEN_VALUE_REPOS_FILE", raising=False)
    da = _load(tmp_path, n_open=0, agent="opencode")
    (tmp_path / "value-repos.json").write_text(
        json.dumps({"repos": ["organvm/mirror-mirror"]}),
        encoding="utf-8",
    )
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"opencode": 50}
    lf.tasks = [
        Task(
            id="GENERIC-HIGH-CI",
            title="fix failing CI on organvm/hokage-chess#85",
            repo="organvm/hokage-chess",
            target_agent="opencode",
            priority="high",
            status="open",
            created=today,
        ),
        Task(
            id="VALUE-MEDIUM-MIRROR",
            title="ship the mirror-mirror revenue predicate",
            repo="organvm/mirror-mirror",
            target_agent="opencode",
            priority="medium",
            status="open",
            created=today,
        ),
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["opencode"], per_agent=1, cap=1, dry=True)

    assert picked == [("opencode", "VALUE-MEDIUM-MIRROR")]


def test_async_value_gate_withholds_generic_churn_even_with_spare_capacity(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_VALUE_REPOS", "organvm/value-repo")
    monkeypatch.setenv("LIMEN_VALUE_REPOS_FILE", str(tmp_path / "missing-value-repos.json"))
    da = _load(tmp_path, n_open=0, agent="codex")
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"codex": 50}
    lf.tasks = [
        Task(
            id="GENERIC-CRITICAL-CI",
            title="generic failing CI",
            repo="organvm/generic-repo",
            target_agent="codex",
            priority="critical",
            status="open",
            created=today,
        ),
        Task(
            id="VALUE-LOW-OWNER",
            title="value-tier owner work",
            repo="organvm/value-repo",
            target_agent="codex",
            priority="low",
            status="open",
            created=today,
        ),
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["codex"], per_agent=5, cap=5, dry=True)

    assert picked == [("codex", "VALUE-LOW-OWNER")]


def test_async_value_gate_does_not_treat_corpus_repo_slug_as_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_VALUE_REPOS", "organvm/value-repo")
    monkeypatch.setenv("LIMEN_VALUE_REPOS_FILE", str(tmp_path / "missing-value-repos.json"))
    da = _load(tmp_path, n_open=0, agent="codex")
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"codex": 50}
    lf.tasks = [
        Task(
            id="HEAL-cifix-organvm-conversation-corpus-engine-42",
            title="fix failing CI on organvm/conversation-corpus-engine#42",
            repo="organvm/conversation-corpus-engine",
            target_agent="codex",
            priority="high",
            status="open",
            labels=["cifix", "self-heal", "ci-red"],
            created=today,
        )
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["codex"], per_agent=5, cap=5, dry=True)

    assert picked == []


def test_async_reserve_skips_lane_that_already_timed_out_task(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_VALUE_REPOS", "organvm/domus-genoma")
    monkeypatch.setenv("LIMEN_VALUE_REPOS_FILE", str(tmp_path / "missing-value-repos.json"))
    da = _load(tmp_path, n_open=0, agent="codex")
    today = datetime.date.today()
    now = datetime.datetime.now(datetime.timezone.utc)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"codex": 50}
    lf.tasks = [
        Task(
            id="HEAL-cifix-organvm-domus-genoma-174",
            title="fix failing CI on organvm/domus-genoma#174",
            repo="organvm/domus-genoma",
            target_agent="codex",
            priority="high",
            status="open",
            labels=["cifix", "self-heal", "ci-red", "slow"],
            created=today,
            dispatch_log=[
                DispatchLogEntry(
                    timestamp=now,
                    agent="codex",
                    session_id="cli",
                    status="timeout->jules",
                )
            ],
        )
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["codex"], per_agent=5, cap=5, dry=True)

    assert picked == []


def test_async_reserve_suppresses_chronic_noop_task(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_VALUE_REPOS", "organvm/value-repo")
    monkeypatch.setenv("LIMEN_VALUE_REPOS_FILE", str(tmp_path / "missing-value-repos.json"))
    da = _load(tmp_path, n_open=0, agent="codex")
    today = datetime.date.today()
    now = datetime.datetime.now(datetime.timezone.utc)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"codex": 50}
    lf.tasks = [
        Task(
            id="CHRONIC-NOOP",
            title="reopened no-op",
            repo="organvm/value-repo",
            target_agent="codex",
            priority="critical",
            status="open",
            labels=["noop"],
            created=today,
            dispatch_log=[
                DispatchLogEntry(
                    timestamp=now,
                    agent="codex",
                    session_id="prior-a",
                    status="failed",
                    output="No-op result; failed for recovery instead of archived.",
                ),
                DispatchLogEntry(
                    timestamp=now,
                    agent="codex",
                    session_id="prior-b",
                    status="failed",
                    output="No-op result; failed for recovery instead of archived.",
                ),
            ],
        ),
        Task(
            id="FRESH-WORK",
            title="fresh bounded product work",
            repo="organvm/value-repo",
            target_agent="codex",
            priority="low",
            status="open",
            created=today,
        ),
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["codex"], per_agent=5, cap=5, dry=True)

    chronic = load_limen_file(tmp_path / "tasks.yaml").tasks[0]
    assert da.chronic_dispatch_reason(chronic) == "repeated-no-op"
    assert picked == [("codex", "FRESH-WORK")]


def test_async_reserve_skips_cifix_superseded_by_active_rebase_task(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_VALUE_REPOS", "organvm/domus-genoma")
    monkeypatch.setenv("LIMEN_VALUE_REPOS_FILE", str(tmp_path / "missing-value-repos.json"))
    da = _load(tmp_path, n_open=0, agent="codex")
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"codex": 50}
    lf.tasks = [
        Task(
            id="HEAL-cifix-organvm-domus-genoma-185",
            title="fix failing CI on organvm/domus-genoma#185",
            repo="organvm/domus-genoma",
            target_agent="codex",
            priority="high",
            status="open",
            labels=["cifix", "self-heal", "ci-red"],
            created=today,
        ),
        Task(
            id="HEAL-rebase-organvm-domus-genoma-185",
            title="rebase/resolve conflicts on organvm/domus-genoma#185",
            repo="organvm/domus-genoma",
            target_agent="codex",
            priority="high",
            status="open",
            labels=["rebase", "self-heal", "conflict"],
            created=today,
        ),
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["codex"], per_agent=5, cap=5, dry=True)

    assert picked == [("codex", "HEAL-rebase-organvm-domus-genoma-185")]


def test_disk_pressure_filters_generic_churn_when_focused_work_exists(tmp_path, monkeypatch):
    monkeypatch.delenv("LIMEN_VALUE_REPOS", raising=False)
    monkeypatch.delenv("LIMEN_VALUE_REPOS_FILE", raising=False)
    monkeypatch.setenv("LIMEN_DISK_FLOOR_GIB", "999999")
    da = _load(tmp_path, n_open=0, agent="codex")
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.tasks = [
        Task(
            id="GENERIC-HIGH-REBASE",
            title="rebase/resolve conflicts on organvm/hokage-chess#85",
            repo="organvm/hokage-chess",
            target_agent="codex",
            priority="high",
            status="open",
            created=today,
        ),
        Task(
            id="PROMPT-LIFECYCLE-MEDIUM",
            title="record prompt packet lifecycle receipt",
            repo="organvm/session-meta",
            target_agent="codex",
            workstream="substrate",
            priority="medium",
            status="open",
            created=today,
        ),
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["codex"], per_agent=1, cap=1, dry=True)

    assert picked == [("codex", "PROMPT-LIFECYCLE-MEDIUM")]


def test_worktree_resource_pressure_suppresses_all_local_async_candidates(tmp_path, monkeypatch):
    # Custody unavailable → EVERY local candidate is withheld (a lifecycle/reclaim task creates a
    # worktree too; the heartbeat reaper drains debt OUTSIDE agent dispatch). No fixed count is used.
    monkeypatch.setenv("LIMEN_VALUE_REPOS", "organvm/generated")
    monkeypatch.delenv("LIMEN_VALUE_REPOS_FILE", raising=False)
    da = _load(tmp_path, n_open=0, agent="codex")
    monkeypatch.setenv("LIMEN_WORKTREE_DEBT_GATE", "1")
    monkeypatch.setattr(da, "_worktree_admission_snapshot", lambda: _worktree_snapshot(blocked=True))
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.tasks = [
        Task(
            id="GEN-BUILDOUT-HIGH",
            title="generated build-out for value repo",
            repo="organvm/generated",
            target_agent="codex",
            priority="high",
            status="open",
            labels=["generated", "build-out"],
            created=today,
        ),
        Task(
            id="SUBSTRATE-RECLAIM-MEDIUM",
            title="recover worktree lifecycle debt (still creates a worktree)",
            repo="organvm/session-meta",
            target_agent="codex",
            workstream="substrate",
            priority="medium",
            status="open",
            created=today,
        ),
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["codex"], per_agent=1, cap=1, dry=True)

    assert picked == []  # every local candidate withheld under resource block


def test_explicit_task_id_async_dispatch_still_obeys_admission(tmp_path, monkeypatch):
    # An explicit task_id async dispatch does NOT bypass worktree admission (item 7).
    da = _load(tmp_path, n_open=0, agent="codex")
    monkeypatch.setenv("LIMEN_WORKTREE_DEBT_GATE", "1")
    monkeypatch.setattr(da, "_worktree_admission_snapshot", lambda: _worktree_snapshot(blocked=True))
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.tasks = [
        Task(
            id="EXPLICIT-CODEX",
            title="explicit local task",
            repo="organvm/session-meta",
            target_agent="codex",
            priority="high",
            status="open",
            created=today,
        ),
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["codex"], per_agent=1, cap=1, dry=True, task_id="EXPLICIT-CODEX")

    assert picked == []


def test_remote_lane_never_inherits_local_worktree_pressure(tmp_path, monkeypatch):
    # A jules (remote/async) generated-buildout task runs OFF-BOX, so it is admitted even when the
    # local resource-custody signal is red. Requirement (3): remote lanes never inherit local pressure.
    monkeypatch.setenv("LIMEN_VALUE_REPOS", "organvm/generated")
    monkeypatch.delenv("LIMEN_VALUE_REPOS_FILE", raising=False)
    da = _load(tmp_path, n_open=0, agent="jules")
    monkeypatch.setenv("LIMEN_WORKTREE_DEBT_GATE", "1")
    snapshot = _worktree_snapshot(blocked=True)
    monkeypatch.setattr(da, "_worktree_admission_snapshot", lambda: snapshot)
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"jules": 50}
    lf.tasks = [
        Task(
            id="GEN-BUILDOUT-REMOTE",
            title="generated build-out on the remote lane",
            repo="organvm/generated",
            target_agent="jules",
            priority="high",
            status="open",
            labels=["generated", "build-out"],
            created=today,
        ),
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["jules"], per_agent=1, cap=1, dry=True)

    assert picked == [("jules", "GEN-BUILDOUT-REMOTE")]
    assert snapshot["reserved_gib"] == 0.0
    assert snapshot["room_gib"] == 0.0


def test_async_multi_candidate_selection_reserves_cumulative_local_checkout_room(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=0, agent="codex")
    monkeypatch.setenv("LIMEN_VALUE_GATE", "0")
    snapshot = _worktree_snapshot(blocked=False, room_gib=1.5)
    monkeypatch.setattr(da, "_worktree_admission_snapshot", lambda: snapshot)
    estimates = {"FIRST-LOCAL": 1.0, "SECOND-LOCAL": 0.6}
    monkeypatch.setattr(dispatch_module, "_tracked_head_checkout_gib", lambda task: estimates[task.id])
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.tasks = [
        Task(
            id="FIRST-LOCAL",
            title="first local checkout",
            repo="organvm/first",
            target_agent="codex",
            priority="critical",
            status="open",
            created=today,
        ),
        Task(
            id="SECOND-LOCAL",
            title="second local checkout",
            repo="organvm/second",
            target_agent="codex",
            priority="high",
            status="open",
            created=today,
        ),
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["codex"], per_agent=2, cap=2, dry=True)

    assert picked == [("codex", "FIRST-LOCAL")]
    assert snapshot["reserved_gib"] == 1.0
    assert snapshot["room_gib"] == 0.5


def test_async_remote_candidates_do_not_consume_or_require_local_checkout_estimates(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=0, agent="jules")
    monkeypatch.setenv("LIMEN_VALUE_GATE", "0")
    snapshot = _worktree_snapshot(blocked=True)
    monkeypatch.setattr(da, "_worktree_admission_snapshot", lambda: snapshot)
    monkeypatch.setattr(
        dispatch_module,
        "_tracked_head_checkout_gib",
        lambda _task: (_ for _ in ()).throw(AssertionError("remote must not estimate a local checkout")),
    )
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"jules": 50}
    lf.tasks = [
        Task(
            id=f"REMOTE-{index}",
            title="remote task",
            repo="organvm/remote",
            target_agent="jules",
            status="open",
            created=today,
        )
        for index in range(7)
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["jules"], per_agent=7, cap=0, dry=True)

    assert picked == [("jules", f"REMOTE-{index}") for index in range(7)]
    assert snapshot["reserved_gib"] == 0.0


def test_reaper_frees_dead_workers_not_live(tmp_path):
    da = _load(tmp_path, n_open=0)
    # two dispatched tasks, one with a stale marker (dead), one fresh (live)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    today = datetime.date.today()
    reserved_at = datetime.datetime.now(datetime.timezone.utc)
    lf.tasks += [
        Task(
            id="DEAD",
            title="t",
            repo="x/y",
            target_agent="codex",
            status="dispatched",
            created=today,
            dispatch_log=[
                DispatchLogEntry(
                    timestamp=reserved_at,
                    agent="codex",
                    session_id="async-reserve",
                    status="dispatched",
                    output="dispatch-async: reserved before detached worker launch",
                )
            ],
        ),
        Task(id="LIVE", title="t", repo="x/y", target_agent="codex", status="dispatched", created=today),
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)
    now = datetime.datetime.now(datetime.timezone.utc)
    (da.RUNS / "DEAD__codex.running").write_text((now - datetime.timedelta(seconds=3000)).isoformat())
    (da.RUNS / "LIVE__codex.running").write_text(now.isoformat())
    reaped = da.reap_stale(1200)
    assert reaped == ["DEAD"]
    assert not (da.RUNS / "DEAD__codex.running").exists()
    assert (da.RUNS / "LIVE__codex.running").exists()
    board = _board(tmp_path)
    assert board["DEAD"].status == "open" and board["LIVE"].status == "dispatched"
    assert board["DEAD"].dispatch_log[-1].session_id == "async-reap-stale"


def test_nonce_scoped_result_prevents_matching_dead_marker_reap(tmp_path):
    da = _load(tmp_path, n_open=0)
    reservation_id = f"async-reserve:{'a' * 32}"
    reserved_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=3000)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.tasks.append(
        Task(
            id="NONCE-RESULT",
            title="t",
            repo="x/y",
            target_agent="codex",
            status="dispatched",
            created=datetime.date.today(),
            dispatch_log=[
                DispatchLogEntry(
                    timestamp=reserved_at,
                    agent="codex",
                    session_id=reservation_id,
                    status="dispatched",
                )
            ],
        )
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)
    da._write_running_marker("NONCE-RESULT", "codex", reserved_at, 999999, 0.0, reservation_id)
    da._result_path("NONCE-RESULT", reservation_id).write_text(
        json.dumps(
            {
                "task_id": "NONCE-RESULT",
                "agent": "codex",
                "reservation_id": reservation_id,
                "result": True,
            }
        )
    )

    assert da.reap_stale(1200) == []
    assert _board(tmp_path)["NONCE-RESULT"].status == "dispatched"
    assert da._running_marker_path("NONCE-RESULT", "codex", reservation_id).exists()


def test_old_dead_marker_cannot_reopen_newer_same_agent_reservation(tmp_path):
    da = _load(tmp_path, n_open=0)
    old_reservation = f"async-reserve:{'a' * 32}"
    current_reservation = f"async-reserve:{'b' * 32}"
    old_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=3000)
    current_at = datetime.datetime.now(datetime.timezone.utc)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.tasks.append(
        Task(
            id="NEWER-RESERVATION",
            title="t",
            repo="x/y",
            target_agent="codex",
            status="dispatched",
            created=datetime.date.today(),
            dispatch_log=[
                DispatchLogEntry(
                    timestamp=old_at,
                    agent="codex",
                    session_id=old_reservation,
                    status="dispatched",
                ),
                DispatchLogEntry(
                    timestamp=current_at,
                    agent="codex",
                    session_id=current_reservation,
                    status="dispatched",
                ),
            ],
        )
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)
    before = (tmp_path / "tasks.yaml").read_bytes()
    old_marker = da._running_marker_path("NEWER-RESERVATION", "codex", old_reservation)
    da._write_running_marker("NEWER-RESERVATION", "codex", old_at, 999999, 0.0, old_reservation)

    assert da.reap_stale(1200) == []
    assert (tmp_path / "tasks.yaml").read_bytes() == before
    assert not old_marker.exists()


def test_inspect_stale_handles_unreadable_marker_without_mutation(tmp_path):
    da = _load(tmp_path, n_open=0)
    marker = da.RUNS / "BROKEN__codex.running"
    marker.write_text("{")

    assert da.inspect_stale(1200) == ["BROKEN"]
    assert marker.exists()


def test_non_object_marker_falls_back_to_filename_and_clears_without_crash(tmp_path):
    da = _load(tmp_path, n_open=0)
    marker = da.RUNS / "T0__github_actions.running"
    marker.write_text("[]")

    assert da._marker_task_agent(marker) == ("T0", "github_actions")
    da._clear_running_markers("T0")
    assert not marker.exists()


def test_reaper_restores_prior_done_instead_of_reopening(tmp_path):
    da = _load(tmp_path, n_open=0)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    today = datetime.date.today()
    reserved_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=3000)
    lf.tasks.append(
        Task(
            id="DONE-DEAD",
            title="t",
            repo="x/y",
            target_agent="codex",
            status="dispatched",
            created=today,
            dispatch_log=[
                DispatchLogEntry(
                    timestamp=reserved_at,
                    agent="codex",
                    session_id="prior",
                    status="done",
                    output="prior success",
                ),
                DispatchLogEntry(
                    timestamp=reserved_at,
                    agent="codex",
                    session_id="async-reserve",
                    status="dispatched",
                ),
            ],
        )
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)
    (da.RUNS / "DONE-DEAD__codex.running").write_text(reserved_at.isoformat())

    reaped = da.reap_stale(1200)

    assert reaped == ["DONE-DEAD"]
    task = _board(tmp_path)["DONE-DEAD"]
    assert task.status == "done"
    assert task.dispatch_log[-1].status == "done"
    assert task.dispatch_log[-1].session_id == "async-reap-stale"


def test_reaper_restores_prior_pr_open_instead_of_reopening(tmp_path):
    da = _load(tmp_path, n_open=0)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    today = datetime.date.today()
    reserved_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=3000)
    lf.tasks.append(
        Task(
            id="PR-DEAD",
            title="t",
            repo="x/y",
            target_agent="codex",
            status="dispatched",
            created=today,
            dispatch_log=[
                DispatchLogEntry(
                    timestamp=reserved_at,
                    agent="codex",
                    session_id="https://github.com/x/y/pull/9",
                    status="pr_open",
                    output="prior PR",
                ),
                DispatchLogEntry(
                    timestamp=reserved_at,
                    agent="codex",
                    session_id="async-reserve",
                    status="dispatched",
                ),
            ],
        )
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)
    (da.RUNS / "PR-DEAD__codex.running").write_text(reserved_at.isoformat())

    reaped = da.reap_stale(1200)

    assert reaped == ["PR-DEAD"]
    task = _board(tmp_path)["PR-DEAD"]
    assert task.status == "dispatched"
    assert task.dispatch_log[-1].status == "dispatched"
    assert task.dispatch_log[-1].session_id == "async-reap-stale"


def test_reaper_reopens_markerless_async_reservation(tmp_path):
    da = _load(tmp_path, n_open=0)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    today = datetime.date.today()
    reserved_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=3000)
    lf.tasks.append(
        Task(
            id="MARKERLESS",
            title="t",
            repo="x/y",
            target_agent="agy",
            status="dispatched",
            created=today,
            updated=reserved_at,
            dispatch_log=[
                DispatchLogEntry(
                    timestamp=reserved_at,
                    agent="agy",
                    session_id="async-reserve",
                    status="dispatched",
                    output="dispatch-async: reserved before detached worker launch",
                )
            ],
        )
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)

    reaped = da.reap_stale(1200)

    assert reaped == ["MARKERLESS"]
    task = _board(tmp_path)["MARKERLESS"]
    assert task.status == "open"
    assert task.dispatch_log[-1].session_id == "async-reap-stale"
    assert "markerless async reservation" in task.dispatch_log[-1].output


def test_reaper_restores_markerless_prior_pr_open_instead_of_reopening(tmp_path):
    da = _load(tmp_path, n_open=0)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    today = datetime.date.today()
    reserved_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=3000)
    lf.tasks.append(
        Task(
            id="PR-MARKERLESS",
            title="t",
            repo="x/y",
            target_agent="agy",
            status="dispatched",
            created=today,
            updated=reserved_at,
            dispatch_log=[
                DispatchLogEntry(
                    timestamp=reserved_at,
                    agent="agy",
                    session_id="https://github.com/x/y/pull/9",
                    status="pr_open",
                    output="prior PR",
                ),
                DispatchLogEntry(
                    timestamp=reserved_at,
                    agent="agy",
                    session_id="async-reserve",
                    status="dispatched",
                    output="dispatch-async: reserved before detached worker launch",
                ),
            ],
        )
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)

    reaped = da.reap_stale(1200)

    assert reaped == ["PR-MARKERLESS"]
    task = _board(tmp_path)["PR-MARKERLESS"]
    assert task.status == "dispatched"
    assert task.dispatch_log[-1].status == "dispatched"
    assert task.dispatch_log[-1].session_id == "async-reap-stale"


def test_async_reserve_counts_inflight_against_launch_room(tmp_path):
    """In-flight .running markers count toward the invocation's lane launch room, so a lane already
    at that room reserves nothing more."""
    import datetime

    da = _load(tmp_path, n_open=6, agent="codex")
    # set codex per-agent cap = 2
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"codex": 2}
    save_limen_file(tmp_path / "tasks.yaml", lf)
    # 2 codex runs already in-flight (markers) → at cap
    for i in range(2):
        (da.RUNS / f"INF{i}__codex.running").write_text(datetime.datetime.now(datetime.timezone.utc).isoformat())
    picked = da.reserve_and_launch(["codex"], per_agent=2, cap=20, dry=True)
    assert picked == [], f"over-dispatched past in-flight launch room: {picked}"


def test_async_reserve_accumulates_picks_against_launch_room(tmp_path):
    da = _load(tmp_path, n_open=6, agent="codex")
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"codex": 2}
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["codex"], per_agent=2, cap=20, dry=True)

    assert picked == [("codex", "T0"), ("codex", "T1")]


def test_async_reserve_does_not_use_stale_daily_board_cap(tmp_path):
    da = _load(tmp_path, n_open=0)
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.daily = 2
    lf.portal.budget.per_agent = {"codex": 50, "agy": 50}
    lf.tasks = [
        Task(id="C0", title="t", repo="x/y", target_agent="codex", status="open", created=today),
        Task(id="C1", title="t", repo="x/y", target_agent="codex", status="open", created=today),
        Task(id="A0", title="t", repo="x/y", target_agent="agy", status="open", created=today),
    ]
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["codex", "agy"], per_agent=8, cap=20, dry=True)

    assert picked == [("codex", "C0"), ("agy", "A0"), ("codex", "C1")]


def test_async_reserve_round_robins_local_slots_across_lanes(tmp_path):
    da = _load(tmp_path, n_open=0)
    today = datetime.date.today()
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.daily = 20
    lf.portal.budget.per_agent = {"codex": 20, "opencode": 20, "agy": 20}
    lf.tasks = (
        [Task(id=f"C{i}", title="t", repo="x/y", target_agent="codex", status="open", created=today) for i in range(4)]
        + [
            Task(id=f"O{i}", title="t", repo="x/y", target_agent="opencode", status="open", created=today)
            for i in range(4)
        ]
        + [Task(id=f"A{i}", title="t", repo="x/y", target_agent="agy", status="open", created=today) for i in range(4)]
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["codex", "opencode", "agy"], per_agent=8, cap=4, dry=True)

    assert picked == [("codex", "C0"), ("opencode", "O0"), ("agy", "A0"), ("codex", "C1")]


def test_async_reserve_projects_stale_budget_reset_before_selection(tmp_path, monkeypatch):
    now = datetime.datetime(2026, 7, 6, 12, 0, tzinfo=datetime.timezone.utc)
    stale = (now - datetime.timedelta(days=2)).isoformat()
    da = _load(tmp_path, n_open=0)
    monkeypatch.setattr(da, "_now", lambda: now)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.daily = 600
    lf.portal.budget.per_agent = {"jules": 100}
    lf.portal.budget.track = BudgetTrack(
        date="2026-07-03",
        spent=100,
        per_agent={"jules": 100},
        per_agent_reset={"jules": stale},
    )
    lf.tasks = [Task(id="JT", title="remote", repo="x/y", target_agent="jules", status="open", created=now.date())]
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["jules"], per_agent=8, cap=0, dry=True)

    assert picked == [("jules", "JT")]
    assert load_limen_file(tmp_path / "tasks.yaml").portal.budget.track.per_agent["jules"] == 100


def test_async_reserve_persists_stale_budget_reset_even_without_launches(tmp_path, monkeypatch):
    now = datetime.datetime(2026, 7, 6, 12, 0, tzinfo=datetime.timezone.utc)
    stale = (now - datetime.timedelta(days=2)).isoformat()
    da = _load(tmp_path, n_open=0)
    monkeypatch.setattr(da, "_now", lambda: now)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.daily = 600
    lf.portal.budget.per_agent = {"jules": 100}
    lf.portal.budget.track = BudgetTrack(
        date="2026-07-03",
        spent=100,
        per_agent={"jules": 100},
        per_agent_reset={"jules": stale},
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)

    assert da.reserve_and_launch(["jules"], per_agent=8, cap=0, dry=False) == []

    track = load_limen_file(tmp_path / "tasks.yaml").portal.budget.track
    assert track.per_agent["jules"] == 0
    assert track.spent == 0
    assert track.per_agent_reset["jules"] == now.isoformat()


def test_async_reserve_skips_open_task_with_prior_done(tmp_path):
    da = _load(tmp_path, n_open=0)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    today = datetime.date.today()
    lf.tasks.append(
        Task(
            id="DONE-OPEN",
            title="t",
            repo="x/y",
            target_agent="codex",
            status="open",
            created=today,
            dispatch_log=[
                DispatchLogEntry(
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                    agent="codex",
                    session_id="prior",
                    status="done",
                )
            ],
        )
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["codex"], per_agent=8, cap=20, dry=True)

    assert picked == []


def test_resolve_lanes_auto_and_all_use_capacity_registry(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=0)
    monkeypatch.setattr(
        da,
        "select_lanes",
        lambda selector, board, down_lanes=None: {
            "auto": ["codex", "github_actions"],
            "all": ["codex", "claude", "github_actions"],
        }.get(selector, ["github_actions", "agy"]),
    )

    assert da.resolve_lanes("auto", down={"claude"}) == ["codex", "github_actions"]
    assert "warp" not in da.resolve_lanes("all", down={"warp"})
    assert da.resolve_lanes("github-actions,antigravity,unknown", down=set()) == ["github_actions", "agy"]


def test_explicit_down_lane_does_not_fallback_to_codex(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=0)
    monkeypatch.setattr(da, "select_lanes", lambda selector, board, down_lanes=None: [])

    assert da.resolve_lanes("jules", down={"jules"}) == []
    assert da.resolve_lanes("auto", down=set()) == ["codex"]


def test_async_dry_run_does_not_reap_harvest_or_reserve_mutations(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=1)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.tasks.append(
        Task(
            id="STALE",
            title="stale",
            repo="x/y",
            target_agent="codex",
            status="dispatched",
            created=datetime.date.today(),
        )
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)
    stale = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=3000)
    marker = da.RUNS / "STALE__codex.running"
    result = da.RUNS / "STALE.result.json"
    marker.write_text(stale.isoformat())
    result.write_text(json.dumps({"task_id": "STALE", "agent": "codex", "result": True}))
    before_board = (tmp_path / "tasks.yaml").read_text()
    before_marker = marker.read_text()
    before_result = result.read_text()

    monkeypatch.setattr(sys, "argv", ["dispatch-async.py", "--lanes", "codex", "--max", "4", "--dry-run"])

    assert da.main() == 0

    assert (tmp_path / "tasks.yaml").read_text() == before_board
    assert marker.read_text() == before_marker
    assert result.read_text() == before_result


def test_async_dry_run_does_not_take_queue_lock(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=1)

    def fail_lock(*_args, **_kwargs):
        raise AssertionError("dry-run must not wait on the queue write lock")

    monkeypatch.setattr(da, "_queue_lock", fail_lock)
    monkeypatch.setattr(sys, "argv", ["dispatch-async.py", "--lanes", "codex", "--max", "4", "--dry-run"])

    assert da.main() == 0


def test_no_launch_mode_skips_always_working_writer(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=1)
    before = (tmp_path / "tasks.yaml").read_text()

    def fail_always_working(*_args, **_kwargs):
        raise AssertionError("harvest-only mode must not run pre-dispatch writers")

    monkeypatch.setattr(da, "run_always_working_before_dispatch", fail_always_working)
    monkeypatch.setattr(
        sys,
        "argv",
        ["dispatch-async.py", "--lanes", "codex", "--per-lane", "0", "--max", "0"],
    )

    assert da.main() == 0
    assert (tmp_path / "tasks.yaml").read_text() == before


def test_targeted_only_main_launches_exact_task_without_broad_reap_or_harvest(tmp_path, monkeypatch, capsys):
    da = _load(tmp_path, n_open=2)
    calls = []

    monkeypatch.setattr(da, "_down_lanes", lambda: set())
    monkeypatch.setattr(da, "resolve_lanes", lambda selector, down: ["codex"])
    contract_hash = _contract_hash(tmp_path, "T1")
    monkeypatch.setattr(
        da,
        "reap_stale",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not broad-reap")),
    )
    monkeypatch.setattr(
        da,
        "harvest",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not broad-harvest")),
    )
    monkeypatch.setattr(da, "dispatch_admission_check", lambda *_args, **_kwargs: {"allow": True})

    def fake_reserve(agents, per_agent, cap, dry, task_id=None, **kwargs):
        calls.append((agents, per_agent, cap, dry, task_id, kwargs))
        return [("codex", "T1")]

    monkeypatch.setattr(da, "reserve_and_launch", fake_reserve)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dispatch-async.py",
            "--lanes",
            "codex",
            "--per-lane",
            "1",
            "--local-per-lane",
            "1",
            "--max",
            "1",
            "--task-id",
            "T1",
            "--execution-contract-hash",
            contract_hash,
            "--targeted-only",
            "--json-output",
        ],
    )

    assert da.main() == 0
    assert len(calls) == 1
    assert calls[0][4] == "T1"
    assert calls[0][5]["admission_checked"] is True
    assert calls[0][5]["expected_contract_hash"] == contract_hash
    receipt = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert receipt == {
        "admission_allow": True,
        "blocker": None,
        "execution_contract_hash": contract_hash,
        "harvested_count": 0,
        "lanes": ["codex"],
        "launched": [["codex", "T1"]],
        "launched_count": 1,
        "reaped_count": 0,
        "reservation_id": None,
        "schema_version": "limen-targeted-dispatch.v1",
        "status": "launched",
        "targeted_only": True,
        "task_id": "T1",
    }


def test_targeted_only_main_returns_nonzero_named_zero_launch(tmp_path, monkeypatch, capsys):
    da = _load(tmp_path, n_open=1)
    monkeypatch.setattr(da, "_down_lanes", lambda: set())
    monkeypatch.setattr(da, "resolve_lanes", lambda selector, down: ["codex"])
    monkeypatch.setattr(da, "dispatch_admission_check", lambda *_args, **_kwargs: {"allow": True})
    monkeypatch.setattr(da, "reserve_and_launch", lambda *_args, **_kwargs: [])
    contract_hash = _contract_hash(tmp_path, "T0")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dispatch-async.py",
            "--lanes",
            "codex",
            "--per-lane",
            "1",
            "--max",
            "1",
            "--task-id",
            "T0",
            "--execution-contract-hash",
            contract_hash,
            "--targeted-only",
            "--json-output",
        ],
    )

    assert da.main() == 10
    receipt = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert receipt["status"] == "zero_launch"
    assert receipt["launched_count"] == 0
    assert receipt["targeted_only"] is True


def test_targeted_only_main_returns_named_contract_mismatch_without_mutation(tmp_path, monkeypatch, capsys):
    da = _load(tmp_path, n_open=1)
    selected_hash = _contract_hash(tmp_path, "T0")
    board = load_limen_file(tmp_path / "tasks.yaml")
    board.tasks[0].predicate = "python3 scripts/changed.py"
    save_limen_file(tmp_path / "tasks.yaml", board)
    before = (tmp_path / "tasks.yaml").read_bytes()
    monkeypatch.setattr(da, "_down_lanes", lambda: set())
    monkeypatch.setattr(da, "dispatch_admission_check", lambda *_args, **_kwargs: {"allow": True})
    monkeypatch.setattr(
        da.subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("mismatched task must not spawn")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dispatch-async.py",
            "--lanes",
            "codex",
            "--per-lane",
            "1",
            "--max",
            "1",
            "--task-id",
            "T0",
            "--execution-contract-hash",
            selected_hash,
            "--targeted-only",
            "--json-output",
        ],
    )

    assert da.main() == 10
    assert (tmp_path / "tasks.yaml").read_bytes() == before
    receipt = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert receipt["status"] == "contract_mismatch"
    assert receipt["blocker"]["id"] == "targeted-execution-contract-mismatch"
    assert receipt["launched_count"] == 0


def test_targeted_only_dry_run_is_exact_and_does_not_mutate(tmp_path, monkeypatch, capsys):
    da = _load(tmp_path, n_open=3)
    before = (tmp_path / "tasks.yaml").read_bytes()
    admission_calls = []
    monkeypatch.setattr(da, "_down_lanes", lambda: set())

    def admission(path, task_id=None, refresh_handoff=True):
        admission_calls.append((path, task_id, refresh_handoff))
        return {"allow": True}

    monkeypatch.setattr(da, "dispatch_admission_check", admission)
    contract_hash = _contract_hash(tmp_path, "T2")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dispatch-async.py",
            "--lanes",
            "codex",
            "--per-lane",
            "1",
            "--max",
            "1",
            "--task-id",
            "T2",
            "--execution-contract-hash",
            contract_hash,
            "--targeted-only",
            "--json-output",
            "--dry-run",
        ],
    )

    assert da.main() == 0
    assert (tmp_path / "tasks.yaml").read_bytes() == before
    assert list(da.RUNS.glob("*")) == []
    assert admission_calls == [(da.TASKS, "T2", False)]
    receipt = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert receipt["status"] == "would_launch"
    assert receipt["launched"] == [["codex", "T2"]]
    assert receipt["reaped_count"] == 0
    assert receipt["harvested_count"] == 0


def test_targeted_only_dry_run_is_unmocked_byte_identical_across_control_surfaces(tmp_path):
    os.environ["LIMEN_ROOT"] = str(tmp_path)
    os.environ["LIMEN_TASKS"] = str(tmp_path / "tasks.yaml")
    _load(tmp_path, n_open=1)
    board = load_limen_file(tmp_path / "tasks.yaml")
    task = board.tasks[0]
    task.context = "exact dry-run byte identity"
    task.predicate = "python3 scripts/check.py"
    task.receipt_target = "git:organvm/limen:logs/check.json"
    save_limen_file(tmp_path / "tasks.yaml", board)

    scripts = tmp_path / "scripts"
    logs = tmp_path / "logs"
    tickets = logs / "tickets" / "inbox"
    runs = logs / "async-runs"
    scripts.mkdir(parents=True, exist_ok=True)
    tickets.mkdir(parents=True, exist_ok=True)
    runs.mkdir(parents=True, exist_ok=True)
    handoff_script = scripts / "handoff-relay.py"
    handoff_script.write_text(
        """#!/usr/bin/env python3
import pathlib
import sys
if "--check" in sys.argv:
    print("handoff check ok")
    raise SystemExit(0)
pathlib.Path("logs/handoff.json").write_text("MUTATED BY FORBIDDEN REFRESH")
""",
        encoding="utf-8",
    )
    handoff_script.chmod(0o755)
    (logs / "handoff.json").write_text(
        json.dumps(
            {
                "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "next_action": {"task_id": task.id},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (tickets / "sentinel.json").write_bytes(b"ticket-bytes\n")
    (runs / "sentinel.bin").write_bytes(b"async-run-bytes\n")
    (logs / "overnight-watch-state.json").write_bytes(b'{"state":"sentinel"}\n')
    (logs / "overnight-watch-alert.json").write_bytes(b'{"alert":"sentinel"}\n')
    (logs / "overnight-watch.jsonl").write_bytes(b'{"receipt":"sentinel"}\n')
    (logs / "overnight-watch.md").write_bytes(b"receipt sentinel\n")

    watched = [
        tmp_path / "tasks.yaml",
        logs / "handoff.json",
        logs / "tickets",
        runs,
        logs / "overnight-watch-state.json",
        logs / "overnight-watch-alert.json",
        logs / "overnight-watch.jsonl",
        logs / "overnight-watch.md",
    ]

    def byte_snapshot():
        snapshot = {}
        for path in watched:
            if path.is_dir():
                for child in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
                    snapshot[str(child.relative_to(tmp_path))] = child.read_bytes()
            else:
                snapshot[str(path.relative_to(tmp_path))] = path.read_bytes()
        return snapshot

    before = byte_snapshot()
    env = {
        **os.environ,
        "LIMEN_ROOT": str(tmp_path),
        "LIMEN_TASKS": str(tmp_path / "tasks.yaml"),
        "LIMEN_DISPATCH_ADMISSION": "1",
        "LIMEN_REQUIRE_HANDOFF": "1",
        "LIMEN_REQUIRE_NEXT_ACTION_SOURCE": "1",
        "LIMEN_SESSION_VALUE_GATE": "1",
        "LIMEN_WORKTREE_DEBT_GATE": "0",
        "LIMEN_DISK_PRESSURE_VALUE_ONLY": "0",
    }
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--lanes",
            "codex",
            "--per-lane",
            "1",
            "--max",
            "1",
            "--task-id",
            task.id,
            "--execution-contract-hash",
            execution_contract_hash(task),
            "--targeted-only",
            "--json-output",
            "--dry-run",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert byte_snapshot() == before
    receipt = json.loads(proc.stdout.splitlines()[-1])
    assert receipt["status"] == "would_launch"
    assert receipt["launched"] == [["codex", task.id]]


def test_targeted_only_retains_dispatch_admission_gate(tmp_path, monkeypatch, capsys):
    da = _load(tmp_path, n_open=1)
    seen = []
    monkeypatch.setattr(da, "_down_lanes", lambda: set())

    def blocked_admission(path, task_id=None, refresh_handoff=True):
        seen.append((path, task_id, refresh_handoff))
        return {"allow": False, "reason": "fresh handoff is required"}

    monkeypatch.setattr(da, "dispatch_admission_check", blocked_admission)
    contract_hash = _contract_hash(tmp_path, "T0")
    monkeypatch.setattr(
        da,
        "reserve_and_launch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("blocked task must not reserve")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dispatch-async.py",
            "--lanes",
            "codex",
            "--per-lane",
            "1",
            "--max",
            "1",
            "--task-id",
            "T0",
            "--execution-contract-hash",
            contract_hash,
            "--targeted-only",
            "--json-output",
        ],
    )

    assert da.main() == 10
    assert seen == [(da.TASKS, "T0", True)]
    receipt = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert receipt["admission_allow"] is False
    assert receipt["status"] == "zero_launch"


def _mark_async_dispatched(tmp_path, *, age_seconds=0, reservation_id="async-reserve"):
    board = load_limen_file(tmp_path / "tasks.yaml")
    task = board.tasks[0]
    stamp = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=age_seconds)
    task.status = "dispatched"
    task.updated = stamp
    task.dispatch_log.append(
        DispatchLogEntry(
            timestamp=stamp,
            agent="codex",
            session_id=reservation_id,
            status="dispatched",
            output="reserved for exact recovery test",
        )
    )
    save_limen_file(tmp_path / "tasks.yaml", board)
    return task, execution_contract_hash(task), stamp


def test_exact_recovery_blocks_fresh_dead_marker(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=1)
    task, contract_hash, stamp = _mark_async_dispatched(tmp_path)
    da._write_running_marker(task.id, "codex", stamp, 999999, 0.0)
    monkeypatch.setattr(da, "_pid_alive", lambda _pid: False)
    monkeypatch.setenv("LIMEN_TARGETED_RECOVERY_GRACE", "3600")

    result = da.recover_exact_task(task.id, contract_hash, dry_run=True)

    assert result["status"] == "blocked"
    assert result["blocker"]["id"] == "targeted-recovery-marker-grace-active"
    assert _board(tmp_path)[task.id].status == "dispatched"


def test_exact_recovery_blocks_unreadable_marker(tmp_path):
    da = _load(tmp_path, n_open=1)
    task, contract_hash, _stamp = _mark_async_dispatched(tmp_path, age_seconds=7200)
    (da.RUNS / f"{task.id}__codex.running").write_text("{not-json", encoding="utf-8")

    result = da.recover_exact_task(task.id, contract_hash, dry_run=True)

    assert result["status"] == "blocked"
    assert result["blocker"]["id"] == "targeted-recovery-marker-unreadable"
    assert _board(tmp_path)[task.id].status == "dispatched"


def test_exact_recovery_blocks_markerless_claim_regardless_of_age(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=1)
    task, contract_hash, _stamp = _mark_async_dispatched(tmp_path, age_seconds=7200)
    monkeypatch.setenv("LIMEN_TARGETED_RECOVERY_GRACE", "1")

    result = da.recover_exact_task(task.id, contract_hash, dry_run=True)

    assert result["status"] == "blocked"
    assert result["blocker"]["id"] == "targeted-recovery-marker-required"
    assert _board(tmp_path)[task.id].status == "dispatched"


@pytest.mark.parametrize("pid", ["__missing__", None, 0, -1, "999999", True])
def test_exact_recovery_blocks_marker_without_explicit_valid_pid(tmp_path, monkeypatch, pid):
    da = _load(tmp_path, n_open=1)
    task, contract_hash, stamp = _mark_async_dispatched(tmp_path, age_seconds=7200)
    marker = {
        "started_at": stamp.isoformat(),
        "agent": "codex",
        "task_id": task.id,
    }
    if pid != "__missing__":
        marker["pid"] = pid
    da._running_marker_path(task.id, "codex").write_text(json.dumps(marker), encoding="utf-8")
    monkeypatch.setattr(
        da,
        "_pid_alive",
        lambda _pid: (_ for _ in ()).throw(AssertionError("invalid pid must never be probed")),
    )
    monkeypatch.setenv("LIMEN_TARGETED_RECOVERY_GRACE", "1")

    result = da.recover_exact_task(task.id, contract_hash, dry_run=True)

    assert result["status"] == "blocked"
    assert result["blocker"]["id"] == "targeted-recovery-marker-pid-invalid"
    assert _board(tmp_path)[task.id].status == "dispatched"


def test_exact_recovery_revalidates_dead_pid_immediately_before_mutation(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=1)
    task, contract_hash, stamp = _mark_async_dispatched(tmp_path, age_seconds=7200)
    da._write_running_marker(task.id, "codex", stamp, 999999, 0.0)
    probes = iter([False, True])
    monkeypatch.setattr(da, "_pid_alive", lambda _pid: next(probes))
    monkeypatch.setattr(da, "_active_admission_leases", lambda: [])
    monkeypatch.setenv("LIMEN_TARGETED_RECOVERY_GRACE", "1")

    result = da.recover_exact_task(task.id, contract_hash, dry_run=False)

    assert result == {"status": "already_running", "recovered_count": 0, "pid": 999999}
    assert _board(tmp_path)[task.id].status == "dispatched"
    assert da._running_marker_path(task.id, "codex").exists()


def test_exact_recovery_checks_live_lease_even_with_stale_dead_marker(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=1)
    task, contract_hash, stamp = _mark_async_dispatched(tmp_path, age_seconds=7200)
    da._write_running_marker(task.id, "codex", stamp, 999999, 0.0)
    monkeypatch.setattr(da, "_pid_alive", lambda _pid: False)
    monkeypatch.setattr(da, "_active_admission_leases", lambda: [{"task_id": task.id, "pid": 1234}])
    monkeypatch.setenv("LIMEN_TARGETED_RECOVERY_GRACE", "1")

    result = da.recover_exact_task(task.id, contract_hash, dry_run=True)

    assert result["status"] == "blocked"
    assert result["blocker"]["id"] == "targeted-recovery-live-lease"
    assert _board(tmp_path)[task.id].status == "dispatched"


def test_exact_recovery_rechecks_result_immediately_before_mutation(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=1)
    task, contract_hash, stamp = _mark_async_dispatched(tmp_path, age_seconds=7200)
    da._write_running_marker(task.id, "codex", stamp, 999999, 0.0)
    checks = []

    def result_exists(_task_id, _reservation_id=None):
        checks.append(True)
        return len(checks) > 1

    monkeypatch.setattr(da, "_result_exists", result_exists)
    monkeypatch.setattr(da, "_pid_alive", lambda _pid: False)
    monkeypatch.setattr(da, "_active_admission_leases", lambda: [])
    monkeypatch.setenv("LIMEN_TARGETED_RECOVERY_GRACE", "1")

    result = da.recover_exact_task(task.id, contract_hash, dry_run=False)

    assert result == {"status": "result_pending_harvest", "recovered_count": 0}
    assert len(checks) == 2
    assert _board(tmp_path)[task.id].status == "dispatched"


def test_async_worker_revalidates_contract_before_provider_side_effects(tmp_path, monkeypatch):
    _load(tmp_path, n_open=1)
    task, expected_hash, _stamp = _mark_async_dispatched(tmp_path)
    board = load_limen_file(tmp_path / "tasks.yaml")
    board.tasks[0].context = "changed after reservation"
    save_limen_file(tmp_path / "tasks.yaml", board)
    worker = _load_worker(tmp_path)
    monkeypatch.setattr(
        worker,
        "call_agent_dispatch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("provider must not run")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "async-run-one.py",
            "--agent",
            "codex",
            "--task-id",
            task.id,
            "--execution-contract-hash",
            expected_hash,
        ],
    )

    assert worker.main() == 10
    receipt = json.loads(worker._result_path(task.id).read_text(encoding="utf-8"))
    assert receipt["execution_started"] is False
    assert receipt["result"] == "__notask__"
    assert receipt["validation_failure"]["id"] == "async-execution-contract-mismatch"
    assert receipt["publication_failure"]["id"] == "async-result-publication-fenced"
    assert receipt["execution_contract_hash"] == expected_hash
    assert receipt["actual_execution_contract_hash"] == execution_contract_hash(_board(tmp_path)[task.id])


@pytest.mark.parametrize(
    ("case", "failure_id"),
    [
        ("queue_lock_busy", "async-execution-queue-lock-busy"),
        ("task_missing", "async-execution-task-missing"),
        ("contract_invalid", "async-execution-contract-invalid"),
        ("status_unsafe", "async-execution-status-unsafe"),
        ("owner_mismatch", "async-execution-claim-owner-mismatch"),
        ("contract_mismatch", "async-execution-contract-mismatch"),
    ],
)
def test_all_worker_validation_failures_are_publication_and_harvest_fenced(tmp_path, monkeypatch, case, failure_id):
    da = _load(tmp_path, n_open=1)
    task, expected_hash, _stamp = _mark_async_dispatched(tmp_path)
    board = load_limen_file(tmp_path / "tasks.yaml")
    current = board.tasks[0]
    if case in {"queue_lock_busy", "status_unsafe"}:
        current.status = "open"
    elif case == "task_missing":
        board.tasks = []
    elif case in {"contract_invalid", "contract_mismatch"}:
        current.context = f"changed before {case} validation"
    elif case == "owner_mismatch":
        current.dispatch_log[-1].agent = "claude"
    save_limen_file(tmp_path / "tasks.yaml", board)
    before = (tmp_path / "tasks.yaml").read_bytes()

    worker = _load_worker(tmp_path)
    if case == "contract_invalid":
        monkeypatch.setattr(
            worker,
            "execution_contract_hash",
            lambda _task: (_ for _ in ()).throw(ValueError("noncanonical contract")),
        )
    elif case == "queue_lock_busy":
        real_queue_lock = worker._queue_lock
        calls = 0

        @contextlib.contextmanager
        def first_lock_busy(path):
            nonlocal calls
            calls += 1
            if calls == 1:
                yield False
            else:
                with real_queue_lock(path) as got:
                    yield got

        monkeypatch.setattr(worker, "_queue_lock", first_lock_busy)

    monkeypatch.setattr(
        worker,
        "call_agent_dispatch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("provider must not run")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "async-run-one.py",
            "--agent",
            "codex",
            "--task-id",
            task.id,
            "--execution-contract-hash",
            expected_hash,
        ],
    )

    assert worker.main() == 10
    receipt = json.loads(worker._result_path(task.id).read_text(encoding="utf-8"))
    assert receipt["execution_started"] is False
    assert receipt["result"] == "__notask__"
    assert receipt["validation_failure"]["id"] == failure_id
    assert receipt["publication_failure"]["id"] in {
        "async-result-publication-fenced",
        "async-result-board-unreadable",
    }

    assert da.harvest() == 0
    assert (tmp_path / "tasks.yaml").read_bytes() == before
    archives = list(da.RECEIPT_ARCHIVE.glob("*/*.result.json"))
    assert len(archives) == 1
    assert json.loads(archives[0].read_text(encoding="utf-8"))["reason"] == "harvest-fenced"


@pytest.mark.parametrize("case", ["task_missing", "status_reopened", "contract_changed", "owner_changed"])
def test_harvest_independently_fences_non_notask_receipt_without_current_custody(tmp_path, case):
    da = _load(tmp_path, n_open=1)
    task, expected_hash, stamp = _mark_async_dispatched(tmp_path)
    da._write_running_marker(task.id, "codex", stamp, 999999, 0.0)
    board = load_limen_file(tmp_path / "tasks.yaml")
    current = board.tasks[0]
    if case == "task_missing":
        board.tasks = []
    elif case == "status_reopened":
        current.status = "open"
    elif case == "contract_changed":
        current.context = "changed after worker result"
    elif case == "owner_changed":
        current.dispatch_log[-1].agent = "claude"
    save_limen_file(tmp_path / "tasks.yaml", board)
    before = (tmp_path / "tasks.yaml").read_bytes()
    result_path = da._result_path(task.id)
    result_path.write_text(
        json.dumps(
            {
                "task_id": task.id,
                "agent": "codex",
                "result": "https://github.com/x/y/pull/99",
                "execution_contract_hash": expected_hash,
                "execution_started": True,
            }
        ),
        encoding="utf-8",
    )

    assert da.harvest() == 0
    assert (tmp_path / "tasks.yaml").read_bytes() == before
    assert da._running_marker_path(task.id, "codex").exists()
    assert not result_path.exists()
    archives = list(da.RECEIPT_ARCHIVE.glob("*/*.result.json"))
    assert len(archives) == 1
    assert json.loads(archives[0].read_text(encoding="utf-8"))["reason"] == "harvest-fenced"


def test_async_worker_fences_result_when_recovery_wins_publication_race(tmp_path, monkeypatch):
    _load(tmp_path, n_open=1)
    task, expected_hash, _stamp = _mark_async_dispatched(tmp_path)
    worker = _load_worker(tmp_path)
    seen = []

    def execute(_agent, task_snapshot, dry_run=False):
        seen.append((task_snapshot.context, execution_contract_hash(task_snapshot), dry_run))
        board = load_limen_file(tmp_path / "tasks.yaml")
        board.tasks[0].status = "open"
        save_limen_file(tmp_path / "tasks.yaml", board)
        return "https://github.com/x/y/pull/99"

    monkeypatch.setattr(worker, "call_agent_dispatch", execute)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "async-run-one.py",
            "--agent",
            "codex",
            "--task-id",
            task.id,
            "--execution-contract-hash",
            expected_hash,
        ],
    )

    assert worker.main() == 0
    receipt = json.loads(worker._result_path(task.id).read_text(encoding="utf-8"))
    assert seen == [(task.context, expected_hash, False)]
    assert receipt["execution_started"] is True
    assert receipt["result"] == "__notask__"
    assert receipt["publication_failure"]["id"] == "async-result-publication-fenced"
    assert _board(tmp_path)[task.id].status == "open"


def test_exact_orphan_recovery_command_reopens_once_and_is_idempotent(tmp_path, monkeypatch, capsys):
    da = _load(tmp_path, n_open=2)
    board = load_limen_file(tmp_path / "tasks.yaml")
    task = board.tasks[0]
    old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=2)
    task.status = "dispatched"
    task.updated = old
    task.dispatch_log.append(
        DispatchLogEntry(
            timestamp=old,
            agent="codex",
            session_id="async-reserve",
            status="dispatched",
            output="reserved for exact recovery test",
        )
    )
    save_limen_file(tmp_path / "tasks.yaml", board)
    contract_hash = execution_contract_hash(task)
    da._write_running_marker(task.id, "codex", old, 999999, 0.0)
    monkeypatch.setattr(da, "_pid_alive", lambda _pid: False)
    monkeypatch.setenv("LIMEN_TARGETED_RECOVERY_GRACE", "1")

    argv = [
        "dispatch-async.py",
        "--recover-task",
        task.id,
        "--execution-contract-hash",
        contract_hash,
        "--json-output",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert da.main() == 0
    first = json.loads(capsys.readouterr().out.splitlines()[-1])

    monkeypatch.setattr(sys, "argv", argv)
    assert da.main() == 0
    second = json.loads(capsys.readouterr().out.splitlines()[-1])

    current = _board(tmp_path)
    assert first["status"] == "recovered"
    assert first["recovered_count"] == 1
    assert second["status"] == "already_open"
    assert second["recovered_count"] == 0
    assert current[task.id].status == "open"
    assert current["T1"].status == "open"
    assert current[task.id].dispatch_log[-1].session_id == "async-recover-exact"


def test_reaper_rechecks_nonce_result_under_lock_before_reopening(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=1)
    reservation_id = "async-reserve:" + "b" * 32
    task, contract_hash, stamp = _mark_async_dispatched(
        tmp_path,
        age_seconds=7200,
        reservation_id=reservation_id,
    )
    da._write_running_marker(task.id, "codex", stamp, 999999, 0.0, reservation_id)
    result_path = da._result_path(task.id, reservation_id)
    before = (tmp_path / "tasks.yaml").read_bytes()
    killed = []
    real_queue_lock = da._queue_lock
    published = False

    @contextlib.contextmanager
    def publish_before_reaper_lock(path):
        nonlocal published
        with real_queue_lock(path) as got:
            if got and not published:
                result_path.write_text(
                    json.dumps(
                        {
                            "task_id": task.id,
                            "agent": "codex",
                            "reservation_id": reservation_id,
                            "execution_contract_hash": contract_hash,
                            "execution_started": True,
                            "result": True,
                        }
                    ),
                    encoding="utf-8",
                )
                published = True
            yield got

    monkeypatch.setattr(da, "_queue_lock", publish_before_reaper_lock)
    monkeypatch.setattr(da, "_pid_alive", lambda _pid: False)
    monkeypatch.setattr(da, "_worker_has_defunct_child", lambda _pid: False)
    monkeypatch.setattr(da, "_kill_worker_group", lambda pid: killed.append(pid))

    assert da.reap_stale(max_age_s=1) == []
    assert published is True
    assert result_path.exists()
    assert da._running_marker_path(task.id, "codex", reservation_id).exists()
    assert killed == []
    assert (tmp_path / "tasks.yaml").read_bytes() == before


def test_exact_recovery_ignores_malformed_marker_from_stale_nonce(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=1)
    reservation_a = "async-reserve:" + "a" * 32
    reservation_b = "async-reserve:" + "b" * 32
    task, contract_hash, stamp = _mark_async_dispatched(
        tmp_path,
        age_seconds=7200,
        reservation_id=reservation_b,
    )
    marker_b = da._running_marker_path(task.id, "codex", reservation_b)
    da._write_running_marker(task.id, "codex", stamp, 999999, 0.0, reservation_b)
    marker_a = da._running_marker_path(task.id, "codex", reservation_a)
    marker_a.write_text("{malformed-stale-a", encoding="utf-8")
    monkeypatch.setattr(da, "_pid_alive", lambda _pid: False)
    monkeypatch.setattr(da, "_active_admission_leases", lambda: [])
    monkeypatch.setenv("LIMEN_TARGETED_RECOVERY_GRACE", "1")

    result = da.recover_exact_task(
        task.id,
        contract_hash,
        reservation_id=reservation_b,
        dry_run=False,
    )

    assert result == {"status": "recovered", "recovered_count": 1}
    assert _board(tmp_path)[task.id].status == "open"
    assert not marker_b.exists()
    assert marker_a.read_text(encoding="utf-8") == "{malformed-stale-a"


def test_exact_open_task_launches_new_nonce_despite_stale_nonce_artifacts(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=1)
    task_id = "T0"
    agent = "codex"
    reservation_a = "async-reserve:" + "a" * 32
    marker_a = da._running_marker_path(task_id, agent, reservation_a)
    result_a = da._result_path(task_id, reservation_a)
    da._write_running_marker(
        task_id,
        agent,
        datetime.datetime.now(datetime.timezone.utc),
        11111,
        0.0,
        reservation_a,
    )
    result_a.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "agent": agent,
                "reservation_id": reservation_a,
                "result": "__notask__",
                "execution_started": False,
            }
        ),
        encoding="utf-8",
    )
    marker_a_bytes = marker_a.read_bytes()
    result_a_bytes = result_a.read_bytes()
    worker_argv = []

    def fake_popen(argv, **_kwargs):
        worker_argv.append(list(argv))
        return type("P", (), {"pid": 22222})()

    monkeypatch.setattr(da.subprocess, "Popen", fake_popen)

    launched = da.reserve_and_launch(
        [agent],
        per_agent=1,
        cap=1,
        dry=False,
        task_id=task_id,
        expected_contract_hash=_contract_hash(tmp_path, task_id),
    )

    assert launched == [(agent, task_id)]
    current = _board(tmp_path)[task_id]
    reservation_b = current.dispatch_log[-1].session_id
    assert re.fullmatch(r"async-reserve:[0-9a-f]{32}", reservation_b)
    assert reservation_b != reservation_a
    assert worker_argv[0][worker_argv[0].index("--reservation-id") + 1] == reservation_b
    assert da._running_marker_path(task_id, agent, reservation_b).exists()
    assert marker_a.read_bytes() == marker_a_bytes
    assert result_a.read_bytes() == result_a_bytes


@pytest.mark.parametrize("artifact_kind", ["legacy", "malformed", "wrong_path"])
def test_exact_open_task_keeps_unfenced_same_task_marker_fail_closed(tmp_path, monkeypatch, artifact_kind):
    da = _load(tmp_path, n_open=1)
    task_id = "T0"
    agent = "codex"
    marker = da._running_marker_path(task_id, agent)
    if artifact_kind == "legacy":
        da._write_running_marker(
            task_id,
            agent,
            datetime.datetime.now(datetime.timezone.utc),
            11111,
            0.0,
        )
    elif artifact_kind == "malformed":
        marker.write_text("{malformed", encoding="utf-8")
    else:
        marker.write_text(
            json.dumps(
                {
                    "task_id": task_id,
                    "agent": agent,
                    "reservation_id": "async-reserve:" + "a" * 32,
                    "reserved_gib": 0.0,
                    "pid": 11111,
                    "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
            ),
            encoding="utf-8",
        )
    before = (tmp_path / "tasks.yaml").read_bytes()
    monkeypatch.setattr(
        da.subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unfenced marker must block launch")),
    )

    assert da._task_claim_artifacts_are_nonce_fenced(task_id) is False
    assert da._running_for(agent, exclude_task_id=task_id) == 1
    assert da._running_local(exclude_task_id=task_id) == 1
    assert (
        da.reserve_and_launch(
            [agent],
            per_agent=1,
            cap=1,
            dry=False,
            task_id=task_id,
            expected_contract_hash=_contract_hash(tmp_path, task_id),
        )
        == []
    )
    assert marker.exists()
    assert (tmp_path / "tasks.yaml").read_bytes() == before


def test_exact_nonce_exclusion_recomputes_room_from_unclamped_base(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=1)
    task_id = "T0"
    agent = "codex"
    reservation_a = "async-reserve:" + "a" * 32
    base_snapshot = _worktree_snapshot(blocked=False, room_gib=1.0)
    da._write_running_marker(
        task_id,
        agent,
        datetime.datetime.now(datetime.timezone.utc),
        11111,
        5.0,
        reservation_a,
    )
    observed_snapshots = []
    real_admission = da._worktree_admission_for_task

    def record_admission(task, selected_agent, snapshot, **kwargs):
        observed_snapshots.append(dict(snapshot))
        return real_admission(task, selected_agent, snapshot, **kwargs)

    monkeypatch.setenv("LIMEN_WORKTREE_DEBT_GATE", "1")
    monkeypatch.setattr(da, "_worktree_admission_snapshot", lambda: dict(base_snapshot))
    monkeypatch.setattr(da, "_worktree_admission_for_task", record_admission)
    monkeypatch.setattr(dispatch_module, "_tracked_head_checkout_gib", lambda _task: 2.0)
    monkeypatch.setattr(
        da.subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("one GiB cannot admit two GiB")),
    )

    launched = da.reserve_and_launch(
        [agent],
        per_agent=1,
        cap=1,
        dry=False,
        task_id=task_id,
        expected_contract_hash=_contract_hash(tmp_path, task_id),
    )

    assert launched == []
    assert observed_snapshots
    assert observed_snapshots[0]["reserved_gib"] == 0.0
    assert observed_snapshots[0]["room_gib"] == 1.0
    assert _board(tmp_path)[task_id].status == "open"


def test_reservation_nonce_fences_reopened_task_from_stale_worker(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=1)
    task_id = "T0"
    agent = "codex"
    pids = iter([11111, 22222])
    worker_argv = []
    killed = []

    def fake_popen(argv, **_kwargs):
        worker_argv.append(list(argv))
        return type("P", (), {"pid": next(pids)})()

    monkeypatch.setattr(da.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(da, "_active_admission_leases", lambda: [])
    monkeypatch.setattr(da, "_kill_worker_group", lambda pid: killed.append(pid))
    monkeypatch.setattr(da, "_worker_has_defunct_child", lambda _pid: False)
    monkeypatch.setattr(da, "_pid_alive", lambda pid: pid == 22222)
    monkeypatch.setenv("LIMEN_TARGETED_RECOVERY_GRACE", "1")

    assert da.reserve_and_launch([agent], 1, 1, False, task_id=task_id) == [(agent, task_id)]
    task_a = _board(tmp_path)[task_id]
    contract_hash = execution_contract_hash(task_a)
    reservation_a = task_a.dispatch_log[-1].session_id
    assert re.fullmatch(r"async-reserve:[0-9a-f]{32}", reservation_a)
    marker_a = da._running_marker_path(task_id, agent, reservation_a)
    marker_a_payload = json.loads(marker_a.read_text(encoding="utf-8"))
    marker_a_payload["started_at"] = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=2)
    ).isoformat()
    marker_a.write_text(json.dumps(marker_a_payload), encoding="utf-8")

    recovered = da.recover_exact_task(
        task_id,
        contract_hash,
        reservation_id=reservation_a,
        dry_run=False,
    )
    assert recovered == {"status": "recovered", "recovered_count": 1}
    assert _board(tmp_path)[task_id].status == "open"
    assert not marker_a.exists()

    assert da.reserve_and_launch([agent], 1, 1, False, task_id=task_id) == [(agent, task_id)]
    task_b = _board(tmp_path)[task_id]
    reservation_b = task_b.dispatch_log[-1].session_id
    assert re.fullmatch(r"async-reserve:[0-9a-f]{32}", reservation_b)
    assert reservation_b != reservation_a
    marker_b = da._running_marker_path(task_id, agent, reservation_b)
    marker_b_bytes = marker_b.read_bytes()
    result_b = da._result_path(task_id, reservation_b)
    result_b_bytes = b'{"reservation":"B","sentinel":true}\n'
    result_b.write_bytes(result_b_bytes)
    board_b_bytes = (tmp_path / "tasks.yaml").read_bytes()

    assert [argv[argv.index("--reservation-id") + 1] for argv in worker_argv] == [
        reservation_a,
        reservation_b,
    ]

    stale_worker = _load_worker(tmp_path)
    monkeypatch.setattr(
        stale_worker,
        "call_agent_dispatch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("stale A must not execute")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "async-run-one.py",
            "--agent",
            agent,
            "--task-id",
            task_id,
            "--reservation-id",
            reservation_a,
            "--execution-contract-hash",
            contract_hash,
        ],
    )

    assert stale_worker.main() == 10
    result_a = stale_worker._result_path(task_id, reservation_a)
    stale_receipt = json.loads(result_a.read_text(encoding="utf-8"))
    assert stale_receipt["reservation_id"] == reservation_a
    assert stale_receipt["execution_started"] is False
    assert stale_receipt["result"] == "__notask__"
    assert stale_receipt["publication_failure"]["id"] == "async-result-publication-fenced"
    assert result_b.read_bytes() == result_b_bytes
    assert marker_b.read_bytes() == marker_b_bytes
    assert (tmp_path / "tasks.yaml").read_bytes() == board_b_bytes

    result_b.unlink()
    assert da.harvest() == 0
    assert not result_a.exists()
    assert marker_b.read_bytes() == marker_b_bytes
    assert (tmp_path / "tasks.yaml").read_bytes() == board_b_bytes

    stale_recovery = da.recover_exact_task(
        task_id,
        contract_hash,
        reservation_id=reservation_a,
        dry_run=False,
    )
    assert stale_recovery["status"] == "blocked"
    assert stale_recovery["blocker"]["id"] == "targeted-recovery-reservation-mismatch"
    assert marker_b.read_bytes() == marker_b_bytes
    assert (tmp_path / "tasks.yaml").read_bytes() == board_b_bytes

    old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=2)
    da._write_running_marker(task_id, agent, old, 11111, 0.0, reservation_a)
    da.reap_stale(max_age_s=1)
    assert killed == []
    assert marker_b.read_bytes() == marker_b_bytes
    assert (tmp_path / "tasks.yaml").read_bytes() == board_b_bytes
