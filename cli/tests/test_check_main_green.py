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
from limen.models import (  # noqa: E402
    JULES_LANDING_HOLD_LABEL,
    Budget,
    BudgetTrack,
    LimenFile,
    Portal,
)


def _seed(tmp: Path, conclusion: str) -> None:
    logs = tmp / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "main-green.json").write_text(
        json.dumps(
            {
                "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "conclusion": conclusion,
                "head_sha": "deadbeef" * 5,
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
    assert "deadbeef" * 5 in tasks[0].predicate
    assert "gh pr list" not in tasks[0].predicate
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
    stamp["head_sha"] = "feedface" * 5
    (tmp_path / "logs" / "main-green.json").write_text(json.dumps(stamp), encoding="utf-8")
    run(tmp_path, apply=True)
    tasks = load_limen_file(tmp_path / "tasks.yaml").tasks
    assert len(tasks) == 1  # still ONE canonical task
    assert tasks[0].id == "HEAL-mainred-organvm-limen"
    assert "feedface" * 5 in tasks[0].predicate
    assert "deadbeef" * 5 not in tasks[0].predicate


def test_active_refresh_leaves_jules_landing_held_singleton_byte_stable(tmp_path):
    _seed(tmp_path, "failure")
    _empty_board(tmp_path)
    run(tmp_path, apply=True)
    tasks_path = tmp_path / "tasks.yaml"

    lf = load_limen_file(tasks_path)
    lf.tasks[0].labels.append(JULES_LANDING_HOLD_LABEL)
    save_limen_file(tasks_path, lf)
    before = tasks_path.read_bytes()

    stamp_path = tmp_path / "logs" / "main-green.json"
    stamp = json.loads(stamp_path.read_text())
    stamp["head_sha"] = "feedface" * 5
    stamp_path.write_text(json.dumps(stamp), encoding="utf-8")

    r = run(tmp_path, apply=True)

    assert r.returncode == 1
    assert tasks_path.read_bytes() == before


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


def test_recurrence_does_not_reopen_successor_required_singleton(tmp_path):
    _seed(tmp_path, "failure")
    _empty_board(tmp_path)
    run(tmp_path, apply=True)
    tasks_path = tmp_path / "tasks.yaml"

    lf = load_limen_file(tasks_path)
    lf.tasks[0].status = "failed"
    lf.tasks[0].labels.append("workstream:successor-required")
    save_limen_file(tasks_path, lf)
    before = tasks_path.read_bytes()

    r = run(tmp_path, apply=True)

    assert r.returncode == 1
    assert tasks_path.read_bytes() == before


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


# --- CI-jam class (2026-07-17: the never-started jam; root cause = VISIBILITY DRIFT) -----------
# Fingerprint from the real incident (run 29581455210): every job "fails" in 3-4 s with ZERO steps
# and the check-run annotation reads "...recent account payments have failed or your spending limit
# needs to be increased...". That generic string is a QUOTA/never-started signal, NOT proof a bill is
# owed — the true cause was limen flipped private, metering the Free tier. A real failure always has
# executed steps.

QUOTA_ANNOTATION = (
    "The job was not started because recent account payments have failed or "
    "your spending limit needs to be increased. Please check the 'Billing & plans' section"
)


def _jobs(*, steps: int, conclusion="failure", n=2):
    return {"jobs": [{"id": 100 + i, "conclusion": conclusion, "steps": [{"name": "s"}] * steps} for i in range(n)]}


def _classify_with(monkeypatch, m, jobs, annotations):
    calls = []

    def fake_gh_json(args, default):
        calls.append(args)
        if "/jobs" in args[1]:
            return jobs
        if "/annotations" in args[1]:
            return annotations
        return default

    monkeypatch.setattr(m, "_gh_json", fake_gh_json)
    return m.classify_red_run(29581455210)


def test_classify_jam_from_zero_steps_and_quota_annotation(monkeypatch):
    m = _load()
    klass, detail = _classify_with(monkeypatch, m, _jobs(steps=0), [{"message": QUOTA_ANNOTATION}])
    assert klass == "ci-jam"
    # detail names the quota/never-started cause — never "payment failure" or a card lever
    assert "quota" in detail.lower() or "never started" in detail.lower()
    assert "card" not in detail.lower() and "payment failure" not in detail.lower()


def test_classify_jam_when_zero_steps_without_quota_text(monkeypatch):
    m = _load()
    klass, _ = _classify_with(monkeypatch, m, _jobs(steps=0), [{"message": "runner exploded"}])
    assert klass == "ci-jam"  # zero-step never-started is still a jam, whatever the annotation


def test_classify_real_failure_when_steps_executed(monkeypatch):
    m = _load()
    klass, _ = _classify_with(monkeypatch, m, _jobs(steps=3), [{"message": QUOTA_ANNOTATION}])
    assert klass == "ci-fail"  # steps ran — a real failure even if the annotation text were misleading


def test_classify_fails_open_to_ci_fail(monkeypatch):
    m = _load()
    monkeypatch.setattr(m, "_gh_json", lambda args, default: default)  # API unavailable
    assert m.classify_red_run(123) == ("ci-fail", "")
    assert m.classify_red_run(0) == ("ci-fail", "")  # cached stamp without run_id


def test_jammed_pr_run_ids_extracts_filters_and_dedups():
    m = _load()
    url = "https://github.com/organvm/limen/actions/runs/{}/job/9"

    def pr(number, name, concl, run, draft=False, updated="2026-07-17T00:00:00Z"):
        return {
            "number": number,
            "isDraft": draft,
            "updatedAt": updated,
            "statusCheckRollup": [{"name": name, "conclusion": concl, "detailsUrl": url.format(run)}],
        }

    prs = [
        pr(1, "pr-gate", "FAILURE", 111),
        pr(2, "pr-gate", "FAILURE", 111),  # same run id — dedup
        pr(3, "python", "FAILURE", 222),  # not a required check — ignored
        pr(4, "pr-gate", "SUCCESS", 333),  # green — ignored
        pr(5, "pr-gate", "FAILURE", 444, draft=True),  # draft — ignored
        pr(6, "pr-gate", "FAILURE", 555, updated="2026-01-01T00:00:00Z"),  # stale — ignored
        pr(7, "pr-gate", "FAILURE", 666),
    ]
    assert m.jammed_pr_run_ids(prs, {"pr-gate"}, "2026-07-16T00:00:00Z") == [111, 666]


def test_attempt_reruns_backoff_cap_and_state(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    m = _load()  # JAM_STATE now under tmp_path
    reran = []

    def fake_run(args, **kwargs):
        assert args[:3] == ["gh", "run", "rerun"]
        reran.append(int(args[3]))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    ids = [111, 222, 333, 444, 555, 666, 777, 888]  # 8 targets, cap is 6
    r1 = m.attempt_reruns(ids, now=1000.0)
    assert [x["action"] for x in r1] == ["rerun"] * 6 and reran == ids[:6]
    # immediately again — everything inside base backoff
    r2 = m.attempt_reruns(ids, now=1001.0)
    assert [x["action"] for x in r2] == ["backoff"] * 6 and len(reran) == 6
    # past base backoff — attempt 2 fires; next delay doubles
    r3 = m.attempt_reruns(ids[:1], now=1000.0 + 1801)
    assert r3[0]["action"] == "rerun"
    state = json.loads((tmp_path / "logs" / "vigilia" / "ci-jam-state.json").read_text())
    assert state["111"]["attempts"] == 2
    # 2nd->3rd attempt needs 2*base; base alone is now inside the window
    r4 = m.attempt_reruns(ids[:1], now=1000.0 + 1801 + 1801)
    assert r4[0]["action"] == "backoff"


def test_jam_red_path_notifies_reruns_and_skips_heal_task(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_NOTIFY", "0")  # bookkeeping only — hermetic runs never pop notifications
    monkeypatch.setenv("LIMEN_MAIN_GREEN_THROTTLE", "100000")
    monkeypatch.setenv("LIMEN_MAIN_GREEN_APPLY", "1")  # armed — and the jam class must STILL not emit
    m = _load()
    _seed(tmp_path, "failure")
    stamp = json.loads((tmp_path / "logs" / "main-green.json").read_text())
    stamp["run_id"] = 29581455210
    (tmp_path / "logs" / "main-green.json").write_text(json.dumps(stamp), encoding="utf-8")

    monkeypatch.setattr(m, "classify_red_run", lambda rid: ("ci-jam", "runner never started (Actions quota)"))
    monkeypatch.setattr(m, "_visibility_drift", lambda repo: True)  # the real 2026-07-17 cause
    monkeypatch.setattr(m, "_fetch_open_prs", lambda: [])
    seen = {}
    monkeypatch.setattr(m, "attempt_reruns", lambda ids, now=None: seen.setdefault("ids", ids) and [])
    monkeypatch.setattr(
        m, "_emit_heal_task", lambda *a, **k: (_ for _ in ()).throw(AssertionError("heal emitted for jam"))
    )

    assert m.main([]) == 1
    out = capsys.readouterr().out
    assert "[ci-jam]" in out and "jam recovery" in out
    assert "L-CARD-FRAUD" not in out and "payment failure" not in out.lower()  # the mislabel is gone
    assert seen["ids"] == [29581455210]  # the trunk run is the first rerun target
    relief = json.loads((tmp_path / "logs" / "vigilia" / "relief-state.json").read_text())
    assert "ci-jam" in relief  # onset recorded (dedup) even with notifications killed
    # the notification names the drift + its real fix (restore public), never a payment chore
    assert "VISIBILITY DRIFT" in relief["ci-jam"]["message"] and "restore" in relief["ci-jam"]["message"].lower()


def test_green_clears_jam_state_and_notification(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_NOTIFY", "0")
    monkeypatch.setenv("LIMEN_MAIN_GREEN_THROTTLE", "100000")
    m = _load()
    _seed(tmp_path, "success")
    jam = tmp_path / "logs" / "vigilia"
    jam.mkdir(parents=True, exist_ok=True)
    (jam / "ci-jam-state.json").write_text('{"111": {"attempts": 3, "last": 1.0}}')
    (jam / "relief-state.json").write_text('{"ci-jam": {"first_seen": 1.0}}')
    monkeypatch.setattr(m, "_fetch_open_prs", lambda: [])

    assert m.main([]) == 0
    assert "GREEN" in capsys.readouterr().out
    assert not (jam / "ci-jam-state.json").exists()  # backoff history reset
    assert "ci-jam" not in json.loads((jam / "relief-state.json").read_text())  # re-arms


def test_visibility_drift_detects_registry_public_but_observed_private(tmp_path, monkeypatch):
    """The 2026-07-17 root cause, as a unit: a conductor-class repo (registry public) observed
    private is a drift; a public observed repo, or a genuinely-private-desired repo, is not."""
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    est = tmp_path / "institutio" / "github"
    est.mkdir(parents=True, exist_ok=True)
    (est / "estate.yaml").write_text(
        "classes:\n"
        "  conductor:\n"
        '    match: ["organvm/limen"]\n'
        "    visibility: public\n"
        "  operation_private:\n"
        '    match: ["organvm/arca"]\n'
        "    visibility: private\n"
    )
    m = _load()  # ESTATE now resolves under tmp LIMEN_ROOT

    def observed(private):
        return lambda args, default: private if args[:2] == ["api", "repos/organvm/limen"] else default

    monkeypatch.setattr(m, "_gh_json", observed(True))
    assert m._visibility_drift("organvm/limen") is True  # registry public, observed private → DRIFT
    monkeypatch.setattr(m, "_gh_json", observed(False))
    assert m._visibility_drift("organvm/limen") is False  # already public → no drift
    # a repo the registry WANTS private, observed private, is not a drift
    monkeypatch.setattr(m, "_gh_json", lambda args, default: True if "arca" in args[1] else default)
    assert m._visibility_drift("organvm/arca") is False
