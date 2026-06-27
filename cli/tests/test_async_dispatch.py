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
from limen.models import Budget, BudgetTrack, LimenFile, Portal, Task  # noqa: E402


def _load(tmp_path, n_open=6, agent="codex"):
    """Point the engine at an isolated tasks.yaml + build n open tasks, then import it fresh so its
    module-level ROOT/TASKS/RUNS pick up this env."""
    os.environ["LIMEN_ROOT"] = str(tmp_path)
    os.environ["LIMEN_TASKS"] = str(tmp_path / "tasks.yaml")
    today = datetime.date.today()
    lf = LimenFile(
        portal=Portal(budget=Budget(daily=300, per_agent={agent: 50},
                                    track=BudgetTrack(date=today.isoformat()))),
        tasks=[Task(id=f"T{i}", title="t", repo="x/y", target_agent=agent,
                    status="open", created=today) for i in range(n_open)],
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


def test_harvest_applies_pr_result_and_cleans(tmp_path):
    da = _load(tmp_path, n_open=2)
    (da.RUNS / "T0.result.json").write_text(json.dumps(
        {"task_id": "T0", "agent": "codex", "result": "https://github.com/x/y/pull/9", "ts": "n", "err": None}))
    assert da.harvest() == 1
    t0 = _board(tmp_path)["T0"]
    assert any("pull/9" in str(e.session_id) for e in t0.dispatch_log)
    assert not (da.RUNS / "T0.result.json").exists()


def test_reserve_and_launch_marks_and_spawns(tmp_path, monkeypatch):
    da = _load(tmp_path, n_open=6)
    calls = []
    monkeypatch.setattr(da.subprocess, "Popen",
                        lambda *a, **k: calls.append(a) or type("P", (), {"pid": 1})())
    picked = da.reserve_and_launch(["codex"], per_agent=2, cap=8, dry=False)
    assert len(picked) == 2 and len(calls) == 2
    dispatched = [t for t in load_limen_file(tmp_path / "tasks.yaml").tasks if t.status == "dispatched"]
    assert len(dispatched) == 2
    assert all(t.dispatch_log[-1].status == "dispatched" for t in dispatched)
    assert all(t.dispatch_log[-1].session_id == "async-reserve" for t in dispatched)
    assert len(list(da.RUNS.glob("*__codex.running"))) == 2


def test_reaper_frees_dead_workers_not_live(tmp_path):
    da = _load(tmp_path, n_open=0)
    # two dispatched tasks, one with a stale marker (dead), one fresh (live)
    lf = load_limen_file(tmp_path / "tasks.yaml")
    today = datetime.date.today()
    lf.tasks += [Task(id="DEAD", title="t", repo="x/y", target_agent="codex", status="dispatched", created=today),
                 Task(id="LIVE", title="t", repo="x/y", target_agent="codex", status="dispatched", created=today)]
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
