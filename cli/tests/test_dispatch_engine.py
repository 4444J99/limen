"""Regression tests for the dispatch-engine reliability keystones added 2026-06-18/19:
  - _run_capture: process-group timeout (the fix for the 23-min beat freeze — a plain
    subprocess.run(timeout) can't kill grandchildren holding the stdout pipe).
  - _down_lanes: derive unproductive lanes from logs/lanes-down.txt (skip gemini/agy).
  - _queue_lock: cross-process mutex on tasks.yaml writes (the #11 lock).
These guard against silently reintroducing the freeze / lane-waste / write-race.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from limen import dispatch as D  # noqa: E402


@pytest.fixture(autouse=True)
def disable_oauth_preflight(monkeypatch):
    monkeypatch.setenv("LIMEN_OAUTH_PREFLIGHT", "0")


def test_run_capture_fast_path():
    r = D._run_capture(["echo", "ok"], timeout=5)
    assert r.returncode == 0 and "ok" in r.stdout


def test_run_capture_kills_grandchild_holding_pipe_on_timeout():
    # The exact freeze shape: the direct child exits immediately but backgrounds a grandchild that
    # inherits the stdout pipe. Plain subprocess.run(timeout) would block ~30s on communicate();
    # _run_capture must SIGKILL the whole group and raise promptly.
    token = f"limen-run-capture-grandchild-{os.getpid()}-{time.time_ns()}"
    grandchild = "import time; time.sleep(30)"
    launcher = (
        f"import subprocess, sys; subprocess.Popen([sys.executable, '-c', {grandchild!r}, {token!r}]); print('started')"
    )
    t0 = time.time()
    with pytest.raises(subprocess.TimeoutExpired):
        D._run_capture([sys.executable, "-c", launcher], timeout=2)
    assert time.time() - t0 < 15, "group-kill did not fire — grandchild hung the call"
    # and no orphaned sleep survived
    leftover = _matching_live_pids(token)
    try:
        assert not leftover, f"orphan grandchild survived the group-kill: {leftover}"
    finally:
        for pid in leftover:
            subprocess.run(["kill", "-9", pid], check=False)


def _matching_live_pids(token: str) -> list[str]:
    try:
        ps = subprocess.run(["ps", "-axo", "pid=,stat=,command="], capture_output=True, text=True, check=False)
    except PermissionError as exc:
        pytest.skip(f"process listing is unavailable in this sandbox: {exc}")
    matches: list[str] = []
    for line in ps.stdout.splitlines():
        if token not in line:
            continue
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        pid, stat, _command = parts
        if pid != str(os.getpid()) and not stat.startswith("Z"):
            matches.append(pid)
    return matches


def test_down_lanes_reads_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "lanes-down.txt").write_text("gemini  # ratelimited\nagy\n\n# a comment line\n")
    assert D._down_lanes() == {"gemini", "agy"}


def test_down_lanes_absent_file_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))  # no logs/lanes-down.txt
    assert D._down_lanes() == set()


def test_queue_lock_is_mutually_exclusive(tmp_path):
    tp = tmp_path / "tasks.yaml"
    tp.write_text("x")
    with D._queue_lock(tp) as got1:
        assert got1 is True
        lockd = tmp_path / "logs" / ".queue.lock.d"
        assert lockd.exists()
        assert (lockd / "pid").read_text().strip() == str(os.getpid())
        assert (lockd / "created_at").read_text().strip()
        with D._queue_lock(tp, timeout=1) as got2:  # held → second acquire fails fast
            assert got2 is False
    assert not (tmp_path / "logs" / ".queue.lock.d").exists()  # released on exit


def test_queue_lock_reenters_when_outer_heartbeat_lock_is_held(tmp_path, monkeypatch):
    tp = tmp_path / "tasks.yaml"
    tp.write_text("x")
    lockd = tmp_path / "logs" / ".queue.lock.d"
    lockd.parent.mkdir()
    lockd.mkdir()
    monkeypatch.setenv("LIMEN_QUEUE_LOCK_HELD", "1")

    with D._queue_lock(tp, timeout=1) as got:
        assert got is True

    assert lockd.exists(), "inner queue_lock must not release the heartbeat's outer lock"


def test_queue_lock_does_not_steal_fresh_anonymous_lock(tmp_path, monkeypatch):
    tp = tmp_path / "tasks.yaml"
    tp.write_text("x")
    lockd = tmp_path / "logs" / ".queue.lock.d"
    lockd.mkdir(parents=True)
    monkeypatch.setenv("LIMEN_QUEUE_LOCK_STALE_SEC", "3600")

    with D._queue_lock(tp, timeout=1) as got:
        assert got is False

    assert lockd.exists()


def test_queue_lock_reaps_old_anonymous_lock(tmp_path, monkeypatch):
    tp = tmp_path / "tasks.yaml"
    tp.write_text("x")
    lockd = tmp_path / "logs" / ".queue.lock.d"
    lockd.mkdir(parents=True)
    old = time.time() - 60
    os.utime(lockd, (old, old))
    monkeypatch.setenv("LIMEN_QUEUE_LOCK_STALE_SEC", "1")

    with D._queue_lock(tp, timeout=2) as got:
        assert got is True
        assert (lockd / "pid").read_text().strip() == str(os.getpid())

    assert not lockd.exists()


def test_queue_lock_reaps_dead_pid_lock(tmp_path, monkeypatch):
    tp = tmp_path / "tasks.yaml"
    tp.write_text("x")
    lockd = tmp_path / "logs" / ".queue.lock.d"
    lockd.mkdir(parents=True)
    (lockd / "pid").write_text("424242\n")
    (lockd / "created_at").write_text("2026-07-03T00:00:00Z\n")

    def fake_kill(pid, sig):
        assert pid == 424242
        assert sig == 0
        raise ProcessLookupError

    monkeypatch.setattr(D.os, "kill", fake_kill)

    with D._queue_lock(tp, timeout=2) as got:
        assert got is True
        assert (lockd / "pid").read_text().strip() == str(os.getpid())

    assert not lockd.exists()


def test_deps_met_gates_on_merged_predecessor():
    """depends_on is satisfied only when the predecessor's PR is MERGED (reconcile marker),
    not merely built (PR open). No deps → always met."""
    import datetime
    from limen.models import DispatchLogEntry, Task

    today = datetime.date.today()
    A = "codex"
    dep_open = Task(
        id="DEP", title="d", repo="x/y", target_agent=A, status="dispatched", created=today
    )  # built, PR open
    dep_merged = Task(
        id="DEPM",
        title="d",
        repo="x/y",
        target_agent=A,
        status="done",
        created=today,
        dispatch_log=[
            DispatchLogEntry(
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                agent="limen",
                session_id="heal",
                status="done",
                output="heal-dispatch: PR merged → done",
            )
        ],
    )
    by = {dep_open.id: dep_open, dep_merged.id: dep_merged}
    assert (
        D._deps_met(
            Task(id="A", title="a", repo="x/y", target_agent=A, status="open", created=today, depends_on=["DEP"]), by
        )
        is False
    )
    assert (
        D._deps_met(
            Task(id="B", title="b", repo="x/y", target_agent=A, status="open", created=today, depends_on=["DEPM"]), by
        )
        is True
    )
    assert D._deps_met(Task(id="C", title="c", repo="x/y", target_agent=A, status="open", created=today), by) is True
    assert (
        D._deps_met(
            Task(id="E", title="e", repo="x/y", target_agent=A, status="open", created=today, depends_on=["MISSING"]),
            by,
        )
        is False
    )


def test_reset_budget_only_resets_stale_windows(tmp_path, monkeypatch):
    """Cadence-aware reset: a lane whose window has elapsed resets to 0; a lane still inside its
    window keeps its spend. (No logs/usage-limits.json in the temp root → default 24h window.)"""
    import datetime
    from limen.models import Budget, BudgetTrack, LimenFile, Portal

    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))  # no usage-limits.json → _window_hours = 24h
    now = datetime.datetime(2026, 6, 19, 12, 0, 0, tzinfo=datetime.timezone.utc)
    track = BudgetTrack(
        date="2026-06-18",
        spent=50,
        per_agent={"codex": 30, "claude": 20},
        per_agent_reset={
            "codex": (now - datetime.timedelta(hours=30)).isoformat(),
            "claude": (now - datetime.timedelta(hours=1)).isoformat(),
        },
    )
    lf = LimenFile(portal=Portal(budget=Budget(daily=300, per_agent={"codex": 50, "claude": 50}, track=track)))
    D._reset_budget_if_needed(lf, now)
    assert track.per_agent["codex"] == 0  # 30h elapsed > 24h window → reset
    assert track.per_agent["claude"] == 20  # 1h < 24h window → kept
    assert track.spent == 20  # = sum(per_agent)


def test_heal_dispatch_funnel_transitions(tmp_path):
    """The reconcile funnel: PR_MERGED + PR_OPEN → done (leave the loop, no dup re-dispatch);
    PR_CLOSED + DISPATCHED_NO_PR → open (re-dispatch). Guards the self-clearing queue."""
    import datetime
    import json
    import os
    import subprocess
    import sys
    from limen.io import load_limen_file, save_limen_file
    from limen.models import Budget, BudgetTrack, LimenFile, Portal, Task

    today = datetime.date.today()
    tasks = [
        Task(id=i, title="t", repo="x/y", target_agent="codex", status="dispatched", created=today)
        for i in ("M", "C", "N", "O")
    ]
    lf = LimenFile(
        portal=Portal(budget=Budget(daily=300, per_agent={}, track=BudgetTrack(date=str(today)))), tasks=tasks
    )
    save_limen_file(tmp_path / "tasks.yaml", lf)
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "dispatch-verify.json").write_text(
        json.dumps(
            {
                "detail": {
                    "PR_MERGED": [{"id": "M", "ref": "x/y#11"}],
                    "PR_CLOSED": [{"id": "C"}],
                    "DISPATCHED_NO_PR": [{"id": "N"}],
                    "PR_OPEN": [{"id": "O", "ref": "x/y#12"}],
                }
            }
        )
    )
    script = Path(__file__).resolve().parents[2] / "scripts" / "heal-dispatch.py"
    env = {
        **os.environ,
        "LIMEN_ROOT": str(tmp_path),
        "LIMEN_TASKS": str(tmp_path / "tasks.yaml"),
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
    }
    result = subprocess.run(
        [sys.executable, str(script), "--apply"], env=env, capture_output=True, text=True, timeout=40
    )
    assert result.returncode == 0, result.stderr
    assert "1 merged→done, 1 open-pr→done, 2 stuck→open" in result.stdout
    tasks_by_id = {t.id: t for t in load_limen_file(tmp_path / "tasks.yaml").tasks}
    assert tasks_by_id["M"].status == "done" and tasks_by_id["O"].status == "done"
    assert tasks_by_id["C"].status == "open" and tasks_by_id["N"].status == "open"
    assert tasks_by_id["M"].dispatch_log[-1].lifecycle_repair == "pr-observed-terminal"
    assert tasks_by_id["M"].dispatch_log[-1].pr_observed_state == "merged"
    assert tasks_by_id["M"].dispatch_log[-1].pr_observed_ref == "x/y#11"
    assert tasks_by_id["O"].dispatch_log[-1].lifecycle_repair == "pr-observed-terminal"
    assert tasks_by_id["O"].dispatch_log[-1].pr_observed_state == "open"
    assert tasks_by_id["O"].dispatch_log[-1].pr_observed_ref == "x/y#12"


def test_reload_fresh_commit_preserves_concurrent_write(tmp_path):
    """#11 keystone: a dispatch holds a STALE in-memory copy across its slow run; a supervisor
    seeds a task during that window; the commit (reload-fresh under the lock + apply by id) must
    NOT clobber the seed. Guards against regressing to a stale-copy save."""
    import datetime
    from limen.io import load_limen_file, save_limen_file
    from limen.models import Budget, BudgetTrack, LimenFile, Portal, Task

    tp = tmp_path / "tasks.yaml"
    today = datetime.date.today()
    lf = LimenFile(
        portal=Portal(budget=Budget(daily=300, per_agent={"codex": 50}, track=BudgetTrack(date=str(today)))),
        tasks=[Task(id="A", title="a", repo="x/y", target_agent="codex", status="dispatched", created=today)],
    )
    save_limen_file(tp, lf)
    load_limen_file(tp)  # dispatch's stale copy (only A)
    sup = load_limen_file(tp)  # supervisor seeds B mid-run
    sup.tasks.append(Task(id="B-SEED", title="s", repo="x/y", target_agent="codex", status="open", created=today))
    save_limen_file(tp, sup)
    now = datetime.datetime.now(datetime.timezone.utc)
    with D._queue_lock(tp):  # the real commit path: reload-fresh + apply by id
        fresh = load_limen_file(tp)
        fid = {t.id: t for t in fresh.tasks}
        D._apply_result(fid["A"], "codex", "https://github.com/x/y/pull/1", now, fresh.portal.budget.track)
        save_limen_file(tp, fresh)
    final = {t.id: t for t in load_limen_file(tp).tasks}
    assert "B-SEED" in final, "concurrent seed was clobbered (the #11 bug)"
    assert any("pull/1" in str(e.session_id) for e in final["A"].dispatch_log), "result not recorded"


def test_deps_not_met_on_awaiting_merge_marker():
    """Regression: a dependency whose only heal marker is 'PR open (awaiting merge) → done' must
    NOT be considered merged (the bare-stem 'merg' bug unlocked dependents on PR-open prematurely)."""
    import datetime
    from limen.models import DispatchLogEntry, Task

    today = datetime.date.today()
    now = datetime.datetime.now(datetime.timezone.utc)
    awaiting = Task(
        id="AW",
        title="d",
        repo="x/y",
        target_agent="codex",
        status="done",
        created=today,
        dispatch_log=[
            DispatchLogEntry(
                timestamp=now,
                agent="limen",
                session_id="heal",
                status="done",
                output="heal-dispatch: PR open (awaiting merge) → done",
            )
        ],
    )
    dependent = Task(
        id="DEP1", title="x", repo="x/y", target_agent="codex", status="open", created=today, depends_on=["AW"]
    )
    assert D._deps_met(dependent, {"AW": awaiting}) is False  # awaiting-merge ≠ merged → still gated
