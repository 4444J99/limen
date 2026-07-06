"""Tests for the ASYNC dispatch engine (scripts/dispatch-async.py) — the throughput-decoupling
path (fire detached workers + harvest, so a slow agent never gates the beat). Covers the pure
orchestration: concurrency cap, in-flight marker accounting, harvest-applies-results, and the
dead-worker reaper. Agent spawning (subprocess.Popen) is monkeypatched so no real agents run.
"""

import datetime
import importlib.util
import json
import os
import sys
from pathlib import Path


CLI_SRC = Path(__file__).resolve().parents[1] / "src"
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "dispatch-async.py"
sys.path.insert(0, str(CLI_SRC))

from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.models import Budget, BudgetTrack, DispatchLogEntry, LimenFile, Portal, Task  # noqa: E402


def _load(tmp_path, n_open=6, agent="codex"):
    """Point the engine at an isolated tasks.yaml + build n open tasks, then import it fresh so its
    module-level ROOT/TASKS/RUNS pick up this env."""
    os.environ["LIMEN_ROOT"] = str(tmp_path)
    os.environ["LIMEN_TASKS"] = str(tmp_path / "tasks.yaml")
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


def test_concurrency_cap_bounds_reservation(tmp_path):
    da = _load(tmp_path, n_open=6)
    picked = da.reserve_and_launch(["codex"], per_agent=8, cap=4, dry=True)
    assert len(picked) == 4  # cap (4) < open (6) and < per_agent (8)


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

    assert da.reserve_and_launch(["agy"], per_agent=4, cap=4, dry=True) == []
    assert da.reserve_and_launch(["agy", "codex"], per_agent=4, cap=4, dry=True) == [
        ("codex", "DISCOVER-organvm-browser-state")
    ]


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


def test_harvest_applies_pr_result_and_cleans(tmp_path):
    da = _load(tmp_path, n_open=2)
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
    assert len(list(da.RUNS.glob("*__codex.running"))) == 2
    track = load_limen_file(tmp_path / "tasks.yaml").portal.budget.track
    assert track.spent == 2
    assert track.per_agent["codex"] == 2


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


def test_async_reserve_counts_inflight_against_budget(tmp_path):
    """In-flight .running markers count toward a lane's per-agent budget, so a lane already at its
    cap via in-flight runs reserves nothing more (prevents over-dispatch between reserve & harvest)."""
    import datetime

    da = _load(tmp_path, n_open=6, agent="codex")
    # set codex per-agent cap = 2
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"codex": 2}
    save_limen_file(tmp_path / "tasks.yaml", lf)
    # 2 codex runs already in-flight (markers) → at cap
    for i in range(2):
        (da.RUNS / f"INF{i}__codex.running").write_text(datetime.datetime.now(datetime.timezone.utc).isoformat())
    picked = da.reserve_and_launch(["codex"], per_agent=8, cap=20, dry=True)
    assert picked == [], f"over-dispatched past in-flight budget: {picked}"


def test_async_reserve_accumulates_picked_cost_against_agent_budget(tmp_path):
    da = _load(tmp_path, n_open=6, agent="codex")
    lf = load_limen_file(tmp_path / "tasks.yaml")
    lf.portal.budget.per_agent = {"codex": 2}
    save_limen_file(tmp_path / "tasks.yaml", lf)

    picked = da.reserve_and_launch(["codex"], per_agent=8, cap=20, dry=True)

    assert picked == [("codex", "T0"), ("codex", "T1")]


def test_async_reserve_accumulates_picked_cost_against_daily_budget(tmp_path):
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

    assert picked == [("codex", "C0"), ("agy", "A0")]


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
