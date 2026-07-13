"""Tests for the ASYNC dispatch engine (scripts/dispatch-async.py) — the throughput-decoupling
path (fire detached workers + harvest, so a slow agent never gates the beat). Covers the pure
orchestration: concurrency cap, in-flight marker accounting, harvest-applies-results, and the
dead-worker reaper. Agent spawning (subprocess.Popen) is monkeypatched so no real agents run.
"""

import datetime
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path


CLI_SRC = Path(__file__).resolve().parents[1] / "src"
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "dispatch-async.py"
sys.path.insert(0, str(CLI_SRC))

from limen.io import load_limen_file, save_limen_file  # noqa: E402
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


def _board(tmp_path):
    return {t.id: t for t in load_limen_file(tmp_path / "tasks.yaml").tasks}


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
    (da.RUNS / "T0__codex.running").write_text(datetime.datetime.now(datetime.timezone.utc).isoformat())
    (da.RUNS / "T0.result.json").write_text(
        json.dumps(
            {"task_id": "T0", "agent": "codex", "result": "https://github.com/x/y/pull/9", "ts": "n", "err": None}
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
