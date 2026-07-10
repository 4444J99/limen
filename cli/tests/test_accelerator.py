"""The reset-window front-load accelerator + its brakes.

The daemon paced dispatch EVENLY and left 40–60% of usable headroom expiring unspent at every reset.
These cover the fix: scale a lane's per-beat volume UP as it under-spends toward its cliff, but only
on LEDGER-WON work-classes (never pour expiring budget into junk), lane-AWARE (async lanes burst, sync
local lanes stay pool-bounded), with the reserve decaying to a floor near the cliff and routing
draining the cliff-edge lane first. All fail-open + floored.
"""

from __future__ import annotations

import datetime
import importlib
import json
import sys
from pathlib import Path

import limen.dispatch as D
from limen.models import Budget, BudgetTrack, LimenFile, Portal, Task

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def _spec_load(name: str, filename: str):
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _lf(per_agent: dict, spent: dict, resets: dict) -> LimenFile:
    track = BudgetTrack(
        date="2026-06-22", spent=sum(spent.values()), per_agent=dict(spent), per_agent_reset=dict(resets)
    )
    return LimenFile(portal=Portal(budget=Budget(daily=600, per_agent=per_agent, track=track)))


def _iso(now: datetime.datetime, hours_ago: float) -> str:
    return (now - datetime.timedelta(hours=hours_ago)).isoformat()


# ── accelerator window + scaling ──────────────────────────────────────────────────────────────
def test_accel_window_detects_under_spend(monkeypatch):
    monkeypatch.setattr(D, "_window_hours", lambda a: 24.0)
    now = datetime.datetime.now(datetime.timezone.utc)
    lf = _lf({"jules": 100}, {"jules": 10}, {"jules": _iso(now, 22)})  # 22h into a 24h window, 90% left
    rem, tleft = D._accel_window(lf, "jules", now)
    assert rem > 0.85 and tleft < 0.12  # lots of budget, almost no time → will under-spend


def test_accel_scales_async_lane_toward_cliff(monkeypatch):
    monkeypatch.setattr(D, "_window_hours", lambda a: 24.0)
    monkeypatch.delenv("LIMEN_ACCEL", raising=False)
    now = datetime.datetime.now(datetime.timezone.utc)
    lf = _lf({"jules": 100}, {"jules": 10}, {"jules": _iso(now, 22)})
    eff = D._accel_limit(lf, "jules", base_limit=3, now=now)
    assert eff > 3, "an under-spending async lane near its cliff must accelerate above base"
    assert eff <= 25, "but never past the async ceiling"


def test_accel_local_sync_lane_ceilinged_below_async(monkeypatch):
    # codex is a SYNC local lane: it shares the beat-blocking thread pool, so its ceiling is the pool
    # (8), not the async burst ceiling (25) — even at the same cliff urgency.
    monkeypatch.setattr(D, "_window_hours", lambda a: 5.0)
    monkeypatch.delenv("LIMEN_ACCEL", raising=False)
    monkeypatch.delenv("LIMEN_DISPATCH_ASYNC", raising=False)
    now = datetime.datetime.now(datetime.timezone.utc)
    lf = _lf({"codex": 100}, {"codex": 5}, {"codex": _iso(now, 4.7)})  # near the 5h cliff, barely spent
    eff = D._accel_limit(lf, "codex", base_limit=3, now=now)
    assert 3 < eff <= 8, "local sync lane accelerates but is pool-bounded, not burst-bounded"


def test_accel_local_bursts_when_async_mode_on(monkeypatch):
    # when dispatch is async (non-blocking), even local lanes may burst — logic follows the PATH.
    monkeypatch.setattr(D, "_window_hours", lambda a: 5.0)
    monkeypatch.setenv("LIMEN_DISPATCH_ASYNC", "1")
    now = datetime.datetime.now(datetime.timezone.utc)
    lf = _lf({"codex": 100}, {"codex": 5}, {"codex": _iso(now, 4.7)})
    eff = D._accel_limit(lf, "codex", base_limit=3, now=now)
    assert eff > 8, "async path lifts the local ceiling to the burst ceiling"


def test_accel_no_acceleration_when_paced_evenly(monkeypatch):
    monkeypatch.setattr(D, "_window_hours", lambda a: 24.0)
    now = datetime.datetime.now(datetime.timezone.utc)
    lf = _lf({"jules": 100}, {"jules": 50}, {"jules": _iso(now, 12)})  # half spent, half the window gone
    assert D._accel_limit(lf, "jules", 3, now) == 3, "even pacing ⇒ no acceleration (base)"


def test_accel_off_when_disabled(monkeypatch):
    monkeypatch.setattr(D, "_window_hours", lambda a: 24.0)
    monkeypatch.setenv("LIMEN_ACCEL", "0")
    now = datetime.datetime.now(datetime.timezone.utc)
    lf = _lf({"jules": 100}, {"jules": 1}, {"jules": _iso(now, 23)})
    assert D._accel_limit(lf, "jules", 3, now) == 3


def test_accel_never_decelerates_below_base(monkeypatch):
    # an OVER-spending lane (more time left than budget) must floor at base, never below — the budget
    # gate, not the accelerator, is what stops over-spend.
    monkeypatch.setattr(D, "_window_hours", lambda a: 24.0)
    now = datetime.datetime.now(datetime.timezone.utc)
    lf = _lf({"jules": 100}, {"jules": 90}, {"jules": _iso(now, 2)})  # 10% left, 92% of window remains
    assert D._accel_limit(lf, "jules", 3, now) == 3


# ── the ledger gate on the acceleration tail ────────────────────────────────────────────────────
def test_accel_allows_is_ledger_gated():
    lanes = {
        "clean": {"waste_classes": [], "win_classes": ["code"]},  # earns across the board
        "mixed": {"waste_classes": ["coverage"], "win_classes": ["revenue"]},
        "pit": {"waste_classes": ["code"], "win_classes": []},  # only wastes
    }
    rev = Task(id="R", title="t", repo="x/y", target_agent="any", type="code", labels=["revenue"], created="2026-06-22")
    cov = Task(
        id="C", title="t", repo="x/y", target_agent="any", type="code", labels=["coverage"], created="2026-06-22"
    )
    assert D._accel_allows("clean", cov, lanes) is True  # clean earner accelerates anything
    assert D._accel_allows("mixed", rev, lanes) is True  # win class rides the tail
    assert D._accel_allows("mixed", cov, lanes) is False  # its waste class does NOT
    assert D._accel_allows("pit", rev, lanes) is False  # pure pit never accelerates
    assert D._accel_allows("unknown", rev, lanes) is False  # no ledger record ⇒ base only


# ── dispatch_parallel integration: the tail is win-class only ───────────────────────────────────
def test_dispatch_parallel_accel_tail_is_win_class_only(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_DISPATCH_ADMISSION", "0")
    monkeypatch.setattr(D, "_window_hours", lambda a: 24.0)
    monkeypatch.delenv("LIMEN_ACCEL", raising=False)
    # jules near its cliff with budget to burn; ledger: jules WINS revenue, WASTES coverage.
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "ledger.json").write_text(
        json.dumps({"lanes": {"jules": {"waste_classes": ["coverage"], "win_classes": ["revenue"]}}})
    )
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    now = datetime.datetime.now(datetime.timezone.utc)
    reset = {"jules": _iso(now, 23)}
    tasks = [
        Task(
            id=f"REV{i}",
            title="t",
            repo="x/y",
            target_agent="jules",
            type="code",
            labels=["revenue"],
            status="open",
            created="2026-06-22",
        )
        for i in range(10)
    ] + [
        Task(
            id=f"COV{i}",
            title="t",
            repo="x/y",
            target_agent="jules",
            type="code",
            labels=["coverage"],
            status="open",
            created="2026-06-22",
        )
        for i in range(10)
    ]
    lf = _lf({"jules": 100}, {"jules": 5}, reset)
    lf.tasks = tasks
    tp = tmp_path / "tasks.yaml"
    picked: list[tuple[str, str]] = []
    monkeypatch.setattr(D, "_deps_met", lambda t, by: True)
    monkeypatch.setattr(D, "_worktree_debt_gate", lambda: (False, ""))
    monkeypatch.setattr(D, "call_agent_dispatch", lambda agent, task, dry_run=False: True)
    # dry-run prints picks; capture by monkeypatching print is noisy — instead call and inspect status.
    D.dispatch_parallel(lf, tp, ["jules"], per_agent_limit=3, dry_run=True)
    # The accelerated tail beyond the 3 base picks must be REVENUE (win) tasks, never COVERAGE (waste).
    # Re-run non-dry to see which got reserved=dispatched.
    D.dispatch_parallel(lf, tp, ["jules"], per_agent_limit=3, dry_run=False)
    disp = [t.id for t in lf.tasks if t.status == "dispatched"]
    assert len(disp) > 3, "accelerator dispatched more than the base 3 toward the cliff"
    assert all(i.startswith("REV") for i in disp), f"tail must be win-class only, got {disp}"
    assert all(t.dispatch_log[-1].status == "dispatched" for t in lf.tasks if t.status == "dispatched")
    assert all(t.dispatch_log[-1].session_id == "reserve" for t in lf.tasks if t.status == "dispatched")
    _ = picked


# ── codex provider-auto selection ───────────────────────────────────────────────────────────────
def test_codex_uses_provider_auto_without_override(monkeypatch):
    monkeypatch.delenv("LIMEN_CODEX_MODEL", raising=False)
    assert D._codex_model() is None
    argv = D._agent_argv("codex")
    assert "-m" not in argv, f"bare invocation must delegate to provider Auto: {argv}"


def test_codex_explicit_model_override_is_opaque(monkeypatch):
    monkeypatch.setenv("LIMEN_CODEX_MODEL", "future-provider-id")
    assert D._codex_model() == "future-provider-id"
    argv = D._agent_argv("codex")
    assert argv[-2:] == ["-m", "future-provider-id"]


# ── cliff-edge routing (route.py) ───────────────────────────────────────────────────────────────
def test_routing_drains_cliff_edge_lane_first(tmp_path, monkeypatch):
    route = importlib.import_module("route")
    monkeypatch.setattr(route, "ROOT", tmp_path)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    (tmp_path / "logs").mkdir()
    # codex is near its reset with budget unspent (high headroom, low time-left); claude is fresh.
    (tmp_path / "logs" / "usage.json").write_text(
        json.dumps(
            {
                "vendors": {
                    "codex": {"headroom_pct": 80, "time_left_frac": 0.05, "runway_h": 50},
                    "claude": {"headroom_pct": 80, "time_left_frac": 0.9, "runway_h": 50},
                }
            }
        )
    )
    health = {"codex": True, "claude": True}
    pick = route._pick_local(
        {"title": "build", "type": "code"},
        health,
        assigned={},
        budget={"codex": 100, "claude": 100},
        runway={"codex": 50.0, "claude": 50.0},
    )
    assert pick == "codex", "the lane about to lose unspent budget at reset drains first"


def test_routing_no_cliff_data_is_today_behaviour(tmp_path, monkeypatch):
    route = importlib.import_module("route")
    monkeypatch.setattr(route, "ROOT", tmp_path)  # no usage.json → cliff urgency {} → runway breaks tie
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))  # isolate ledger/self-improve reads from LIVE logs/ too
    health = {"codex": True, "claude": True}
    pick = route._pick_local(
        {"title": "build", "type": "code"},
        health,
        assigned={},
        budget={"codex": 100, "claude": 100},
        runway={"codex": 10.0, "claude": 99.0},
    )
    assert pick == "claude", "with no cliff signal, freshest-runway wins as before"


# ── reserve burn-down-with-floor (usage-telemetry.py) ───────────────────────────────────────────
def test_reserve_decays_to_floor_near_cliff():
    ut = _spec_load("usage_telemetry_mod", "usage-telemetry.py")
    # full reserve early in the window, floor at the cliff, monotonic between.
    early = ut._effective_reserve(15.0, 5.0, time_left_frac=1.0)
    cliff = ut._effective_reserve(15.0, 5.0, time_left_frac=0.0)
    mid = ut._effective_reserve(15.0, 5.0, time_left_frac=0.5)
    assert early == 15.0
    assert cliff == 5.0, "near the reset the reserve is the floor — never 0, never the full hold-back"
    assert 5.0 < mid < 15.0


def test_reserve_floor_clamped_to_reserve():
    ut = _spec_load("usage_telemetry_mod2", "usage-telemetry.py")
    # a floor larger than the reserve must not INFLATE the reserve near a cliff.
    assert ut._effective_reserve(3.0, 5.0, time_left_frac=0.0) == 3.0


def test_time_left_frac_from_reset_stamp():
    ut = _spec_load("usage_telemetry_mod3", "usage-telemetry.py")
    now = ut.NOW
    reset_map = {"jules": (now - datetime.timedelta(hours=18)).isoformat()}
    tlf = ut._time_left_frac("jules", reset_map, window_hours=24.0)
    assert 0.2 < tlf < 0.3, "6h left in a 24h window ≈ 0.25"
    assert ut._time_left_frac("absent", {}, 24.0) == 1.0, "unknown reset ⇒ treat as fresh (full reserve)"
