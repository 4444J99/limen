"""Tests for scripts/check-main-green.py — the trunk-green invariant sensor.

Verdicts are injected via the cache stamp (logs/main-green.json under a tmp LIMEN_ROOT) with a large
throttle, so the test never calls live `gh`. The emit path writes into a tmp tasks.yaml.
"""

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check-main-green.py"

sys.path.insert(0, str(ROOT / "cli" / "src"))
from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.models import Budget, BudgetTrack, LimenFile, Portal  # noqa: E402


def _seed(tmp: Path, conclusion: str) -> None:
    logs = tmp / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "main-green.json").write_text(
        json.dumps(
            {
                "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "conclusion": conclusion,
                "head_sha": "deadbeef",
                "url": "https://github.com/organvm/limen/actions/runs/1",
            }
        ),
        encoding="utf-8",
    )


def _empty_board(tmp: Path) -> Path:
    tasks = tmp / "tasks.yaml"
    today = dt.date.today()
    save_limen_file(
        tasks,
        LimenFile(
            portal=Portal(budget=Budget(daily=300, per_agent={}, track=BudgetTrack(date=today.isoformat()))),
            tasks=[],
        ),
    )
    return tasks


def run(tmp: Path, *extra, apply=False):
    env = {
        "LIMEN_ROOT": str(tmp),
        "LIMEN_TASKS": str(tmp / "tasks.yaml"),
        "LIMEN_MAIN_GREEN_THROTTLE": "100000",  # force cache use
        "LIMEN_MAIN_GREEN_APPLY": "1" if apply else "0",
        "PATH": "/usr/bin:/bin",
    }
    import os

    child = os.environ.copy()
    child.update(env)
    return subprocess.run([sys.executable, str(CHECK), *extra], capture_output=True, text=True, env=child)


def test_green_verdict_exits_zero(tmp_path):
    _seed(tmp_path, "success")
    r = run(tmp_path)
    assert r.returncode == 0, r.stdout
    assert "GREEN" in r.stdout


def test_red_verdict_detection_only(tmp_path):
    _seed(tmp_path, "failure")
    _empty_board(tmp_path)
    r = run(tmp_path)  # APPLY off
    assert r.returncode == 1, r.stdout
    assert "RED" in r.stdout and "detection-only" in r.stdout
    # detection-only must NOT write a task
    assert not load_limen_file(tmp_path / "tasks.yaml").tasks


def test_red_verdict_emits_one_idempotent_task(tmp_path):
    _seed(tmp_path, "failure")
    _empty_board(tmp_path)
    r = run(tmp_path, apply=True)
    assert r.returncode == 1, r.stdout
    tasks = load_limen_file(tmp_path / "tasks.yaml").tasks
    assert len(tasks) == 1
    # SYMPTOM-scoped id (no SHA) so a moving red trunk converges on one task — limen#895
    assert tasks[0].id == "HEAL-mainred-organvm-limen"
    assert "deadbeef" in tasks[0].title  # the SHA lives in the title, not the id
    assert tasks[0].priority == "critical" and "mainred" in tasks[0].labels
    # idempotent: a second run adds nothing
    run(tmp_path, apply=True)
    assert len(load_limen_file(tmp_path / "tasks.yaml").tasks) == 1


def test_moving_red_trunk_converges_on_one_task(tmp_path):
    """A red trunk whose head SHA moves between beats must NOT spawn a task per SHA (limen#895)."""
    _seed(tmp_path, "failure")
    _empty_board(tmp_path)
    run(tmp_path, apply=True)
    # a new red commit lands: same symptom, different SHA
    _seed(tmp_path, "failure")  # (re-stamps checked_at; head_sha would differ live)
    # rewrite the cache with a different SHA to simulate the trunk moving while still red
    stamp = json.loads((tmp_path / "logs" / "main-green.json").read_text())
    stamp["head_sha"] = "feedface"
    (tmp_path / "logs" / "main-green.json").write_text(json.dumps(stamp), encoding="utf-8")
    run(tmp_path, apply=True)
    tasks = load_limen_file(tmp_path / "tasks.yaml").tasks
    assert len(tasks) == 1  # still ONE canonical task
    assert tasks[0].id == "HEAL-mainred-organvm-limen"


def test_recurrence_reopens_healed_task(tmp_path):
    """If a prior red episode healed (task done) and trunk is red again, the SAME singleton reopens —
    a recurrence must never be dropped by a stale done-row."""
    _seed(tmp_path, "failure")
    _empty_board(tmp_path)
    run(tmp_path, apply=True)
    tasks_path = tmp_path / "tasks.yaml"

    # simulate the heal landing: mark the singleton done
    lf = load_limen_file(tasks_path)
    lf.tasks[0].status = "done"
    save_limen_file(tasks_path, lf)

    # trunk goes red again → reopen the same ticket, not a duplicate
    run(tmp_path, apply=True)
    tasks = load_limen_file(tasks_path).tasks
    assert len(tasks) == 1
    assert tasks[0].id == "HEAL-mainred-organvm-limen"
    assert tasks[0].status == "open"  # reopened


def test_active_states_parity_with_dispatch():
    """The local _ACTIVE_STATES must stay in lockstep with dispatch's superseder set (no silent drift)."""
    m = _load()
    from limen.dispatch import _ACTIVE_SUPERSEDER_STATUSES

    assert set(m._ACTIVE_STATES) == set(_ACTIVE_SUPERSEDER_STATUSES)


def test_fail_open_when_status_unavailable(tmp_path):
    # no cache seeded + no gh on PATH → gh call fails → unknown → exit 0 (never break the beat)
    r = run(tmp_path)
    assert r.returncode == 0, r.stdout
    assert "SKIP" in r.stdout


# --- blast-radius / queue-wedge (integrated from PR #882) ---

import importlib.util  # noqa: E402


def _load():
    spec = importlib.util.spec_from_file_location("check_main_green", CHECK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pr(number, checks, draft=False, updated="2026-07-10T00:00:00Z"):
    return {
        "number": number,
        "isDraft": draft,
        "updatedAt": updated,
        "statusCheckRollup": [{"name": n, "conclusion": c} for n, c in checks],
    }


def test_failing_required_checks_only_required_and_bad():
    m = _load()
    pr = _pr(1, [("pr-gate", "FAILURE"), ("python", "FAILURE"), ("web", "SUCCESS")])
    assert m.failing_required_checks(pr, {"pr-gate"}) == {"pr-gate"}  # non-required 'python' ignored


def test_wedge_impact_fires_at_threshold():
    m = _load()
    prs = [_pr(n, [("pr-gate", "FAILURE")]) for n in range(5)]
    v = m.wedge_impact(prs, {"pr-gate"}, fresh_since=None, k=5)
    assert v["wedged_checks"] == {"pr-gate": 5}
    assert v["wedged_prs"] == 5


def test_wedge_impact_below_threshold_is_zero():
    m = _load()
    prs = [_pr(n, [("pr-gate", "FAILURE")]) for n in range(3)]
    v = m.wedge_impact(prs, {"pr-gate"}, fresh_since=None, k=5)
    assert v["wedged_prs"] == 0 and v["wedged_checks"] == {}


def test_wedge_impact_excludes_stale_and_draft():
    m = _load()
    stale = [_pr(n, [("pr-gate", "FAILURE")], updated="2026-01-01T00:00:00Z") for n in range(50)]
    drafts = [_pr(100 + n, [("pr-gate", "FAILURE")], draft=True) for n in range(50)]
    v = m.wedge_impact(stale + drafts, {"pr-gate"}, fresh_since="2026-07-09T00:00:00Z", k=5)
    assert v["wedged_prs"] == 0 and v["considered"] == 0


def test_wedge_impact_counts_fresh_only():
    m = _load()
    stale = [_pr(n, [("pr-gate", "FAILURE")], updated="2026-01-01T00:00:00Z") for n in range(50)]
    fresh = [_pr(200 + n, [("pr-gate", "FAILURE")], updated="2026-07-10T00:00:00Z") for n in range(6)]
    v = m.wedge_impact(stale + fresh, {"pr-gate"}, fresh_since="2026-07-09T00:00:00Z", k=5)
    assert v["wedged_prs"] == 6 and v["considered"] == 6


# --- Omega exact-head contract ---------------------------------------------------------------


def _run_row(head, *, conclusion="success", status="completed", event="push"):
    return {
        "databaseId": 1,
        "conclusion": conclusion,
        "status": status,
        "headSha": head,
        "url": "https://github.com/organvm/limen/actions/runs/1",
        "event": event,
    }


def test_exact_head_selector_ignores_prior_pending_and_non_push_runs():
    m = _load()
    current = "a" * 40
    prior = "b" * 40
    runs = [
        _run_row(current, status="in_progress"),
        _run_row(current, event="workflow_dispatch"),
        _run_row(prior),
        _run_row(current),
    ]
    assert m.select_completed_push_run(runs, head_sha=current) == runs[-1]
    assert m.select_completed_push_run(runs[:3], head_sha=current) is None


def test_exact_head_check_requires_success_for_current_remote_main(monkeypatch, capsys):
    m = _load()
    current = "a" * 40
    monkeypatch.setattr(m, "_remote_main_head", lambda: current)
    monkeypatch.setattr(m, "_gh_main_runs", lambda: [_run_row("b" * 40), _run_row(current)])
    assert m.exact_head_check() == 0
    assert "EXACT-HEAD GREEN" in capsys.readouterr().out

    monkeypatch.setattr(m, "_gh_main_runs", lambda: [_run_row(current, conclusion="failure")])
    assert m.exact_head_check() == 1
    assert "EXACT-HEAD RED" in capsys.readouterr().out


def test_exact_head_check_fails_closed_without_matching_completed_run(monkeypatch, capsys):
    m = _load()
    current = "a" * 40
    monkeypatch.setattr(m, "_remote_main_head", lambda: current)
    monkeypatch.setattr(m, "_gh_main_runs", lambda: [_run_row(current, status="in_progress")])
    assert m.exact_head_check() == 1
    assert "no completed" in capsys.readouterr().out


def test_remote_main_head_reads_owner_ref_not_cached_tracking_ref(monkeypatch):
    m = _load()
    current = "c" * 40

    def fake_run(args, **kwargs):
        assert args[-4:] == ["ls-remote", "--exit-code", "origin", "refs/heads/main"]
        return subprocess.CompletedProcess(args, 0, f"{current}\trefs/heads/main\n", "")

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    assert m._remote_main_head() == current
