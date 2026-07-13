"""Tests for the ASYNC dispatch engine (scripts/dispatch-async.py) — the throughput-decoupling
path (fire detached workers + harvest, so a slow agent never gates the beat). Covers the pure
orchestration: concurrency cap, in-flight marker accounting, harvest-applies-results, and the
dead-worker reaper. Agent spawning (subprocess.Popen) is monkeypatched so no real agents run.
"""

import datetime
import contextlib
import importlib.util
import json
import os
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


def test_reserve_and_launch_marks_and_spawns(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=6)
    calls = []
    monkeypatch.setattr(da.subprocess, "Popen", lambda *a, **k: calls.append(a) or type("P", (), {"pid": 1})())
    picked = da.reserve_and_launch(["codex"], per_agent=2, cap=8, dry=False)
    assert len(picked) == 2 and len(calls) == 2
    dispatched = [t for t in load_limen_file(tmp_path / "tasks.yaml").tasks if t.status == "dispatched"]
    assert len(dispatched) == 2
    assert all(t.dispatch_log[-1].status == "dispatched" for t in dispatched)
    assert all(t.dispatch_log[-1].session_id == "async-reserve" for t in dispatched)
    assert all(t.predicate and t.receipt_target for t in dispatched)
    current = {task.id: task for task in dispatched}
    for call in calls:
        argv = call[0]
        task_id = argv[argv.index("--task-id") + 1]
        contract_hash = argv[argv.index("--execution-contract-hash") + 1]
        assert contract_hash == execution_contract_hash(current[task_id])
    assert len(list(da.RUNS.glob("*__codex.running"))) == 2
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
    assert not da._running_marker_path("T0", "codex").exists()
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


def test_targeted_only_main_launches_exact_task_without_broad_reap_or_harvest(
    tmp_path, monkeypatch, capsys
):
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


def _mark_async_dispatched(tmp_path, *, age_seconds=0):
    board = load_limen_file(tmp_path / "tasks.yaml")
    task = board.tasks[0]
    stamp = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=age_seconds)
    task.status = "dispatched"
    task.updated = stamp
    task.dispatch_log.append(
        DispatchLogEntry(
            timestamp=stamp,
            agent="codex",
            session_id="async-reserve",
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

    def result_ids():
        checks.append(True)
        return set() if len(checks) == 1 else {task.id}

    monkeypatch.setattr(da, "_result_task_ids", result_ids)
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
def test_all_worker_validation_failures_are_publication_and_harvest_fenced(
    tmp_path, monkeypatch, case, failure_id
):
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
def test_harvest_independently_fences_non_notask_receipt_without_current_custody(
    tmp_path, case
):
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
