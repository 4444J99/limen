"""The SCHEDULES registry predicates' own contract (gates.yaml: schedules-test).

Drives the shipped scripts (scripts/check-schedules.py, scripts/schedule-utilization.py, both over
scripts/_schedules.py) against tmp fixtures — never an extracted copy of a rung — and pins the
defects that would otherwise read GREEN: a half-elapsed day compared against a whole day's fires,
an unmeasured plane counted as dark, a stagger baseline that rots, a sibling repo the runner
cannot see reported as drift.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve the owning module through sys.modules (py3.13)
    spec.loader.exec_module(module)
    return module


S = _load("limen_test_schedules_lib", "_schedules.py")
CHECK = _load("limen_test_check_schedules", "check-schedules.py")
UTIL = _load("limen_test_schedule_utilization", "schedule-utilization.py")
BEAT = _load("limen_test_schedule_beat_sensors", "beat-sensors.py")

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
TODAY = NOW.date()


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────


def _plane(**over) -> dict:
    base = {
        "provider": "github",
        "surface": "cron",
        "owner": "governance",
        "effector": "fix it",
        "allotment": {
            "runs": None,
            "window": "calendar-day",
            "concurrency": None,
            "source": "test",
            "entitlement": "unpublished",
        },
        "fill_policy": "declared",
        "floor": None,
        "jobs_source": None,
        "evidence": {"kind": "none", "locator": None},
        "declared_on": "2026-10-23",
        "enabled": True,
    }
    base.update(over)
    return base


def _job(jid: str, plane: str, cron, **over) -> dict:
    base = {
        "id": jid,
        "plane": plane,
        "cron": cron,
        "tz": "UTC",
        "delivery": {"kind": "bookend-tsv", "locator": "x"},
        "class": "report",
        "source_of_truth": "4444J99/ops:.github/workflows/job.yml",
        "enabled": True,
    }
    base.update(over)
    return base


def write_registry(
    root: Path, planes: dict, jobs: list, baseline: list[str] | None = None, house=(11, 17, 23, 36, 49)
) -> None:
    gov = root / "institutio" / "governance"
    gov.mkdir(parents=True, exist_ok=True)
    (gov / "schedules.yaml").write_text(
        yaml.safe_dump(
            {"schema_version": 0.1, "house_offsets": list(house), "planes": planes, "jobs": jobs}, sort_keys=False
        )
    )
    (gov / "schedule-stagger-baseline.txt").write_text("# test baseline\n" + "\n".join(baseline or []) + "\n")
    # consumers: a sensor step and a gate row so check F passes on fixtures
    (gov / "sensors.yaml").write_text(
        yaml.safe_dump(
            {"sensors": {"schedule-utilization": {"steps": [{"command": "python3 scripts/schedule-utilization.py"}]}}}
        )
    )
    (gov / "gates.yaml").write_text(
        yaml.safe_dump({"gates": {"check-schedules": {"command": "python3 scripts/check-schedules.py"}}})
    )


def write_workflow(root: Path, name: str, crons: list[str]) -> None:
    wf = root / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    body = "name: %s\non:\n  schedule:\n%s  workflow_dispatch: {}\njobs: {}\n" % (
        name,
        "".join(f"    - cron: '{c}'\n" for c in crons),
    )
    (wf / f"{name}.yml").write_text(body)


def run_check(root: Path, *extra: str, env: dict | None = None) -> subprocess.CompletedProcess:
    merged = {"PATH": "/usr/bin:/bin", "HOME": str(root / "home"), **(env or {})}
    (root / "home").mkdir(exist_ok=True)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "check-schedules.py"), "--root", str(root), *extra],
        capture_output=True,
        text=True,
        env=merged,
        check=False,
    )


# ── _schedules: cron + timezone ───────────────────────────────────────────────────────────────


def test_cron_parses_lists_ranges_steps_and_rejects_names():
    c = S.parse_cron("0 1,5,9-11 * * 1-5")
    assert (
        c.minutes == frozenset({0}) and c.hours == frozenset({1, 5, 9, 10, 11}) and c.dow == frozenset({1, 2, 3, 4, 5})
    )
    assert S.parse_cron("*/30 * * * *").minutes == frozenset(range(0, 60, 30))
    assert S.parse_cron("0 0 * * 7").dow == frozenset({0})
    for bad in ("0 9 * * MON", "0 9 * *", "61 9 * * *", "0 9 L * *"):
        with pytest.raises(S.CronError):
            S.parse_cron(bad)


def test_vixie_dom_dow_or_semantics():
    both = S.parse_cron("0 0 1 * 1")  # 1st of month OR Mondays
    assert both.matches(datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc))  # Thursday the 1st
    assert both.matches(datetime(2026, 10, 5, 0, 0, tzinfo=timezone.utc))  # a Monday
    assert not both.matches(datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))


def test_eastern_crons_convert_to_utc_fires():
    fires = S.fires_on_utc_day(S.parse_cron("0 13,19 * * *"), S.resolve_tz("America/New_York"), date(2026, 10, 23))
    assert [f.strftime("%H:%M") for f in fires] == ["17:00", "23:00"]
    hourly = S.fires_on_utc_day(S.parse_cron("0 * * * *"), S.resolve_tz("America/New_York"), date(2026, 10, 23))
    assert len(hourly) == 24


def test_cadence_class_matches_manifest_vocabulary():
    assert S.cadence_class(S.parse_cron("7 9 * * 1-5")) == "weekdays"
    assert S.cadence_class(S.parse_cron("23 9 * * 1")) == "weekly"
    assert S.cadence_class(S.parse_cron("8 22 * * *")) == "daily"


def test_workflow_jobs_survive_pyyaml_reading_on_as_true(tmp_path):
    write_workflow(tmp_path, "deploy", ["0 * * * *"])
    write_workflow(tmp_path, "ci", ["43 7 * * *"])
    (tmp_path / ".github" / "workflows" / "pr-gate.yml").write_text("on:\n  pull_request:\njobs: {}\n")
    jobs = S.derive_workflow_jobs(tmp_path, "github-actions-limen")
    assert {j.id: j.crons for j in jobs} == {"limen/ci": ["43 7 * * *"], "limen/deploy": ["0 * * * *"]}
    assert all(j.derived and j.tz == "UTC" for j in jobs)


# ── check-schedules ──────────────────────────────────────────────────────────────────────────


def test_real_registry_is_green():
    run = subprocess.run(
        [sys.executable, str(SCRIPTS / "check-schedules.py"), "--quiet"], capture_output=True, text=True, check=False
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert "check-schedules: OK" in run.stdout


def test_schema_failures_are_named(tmp_path):
    write_registry(
        tmp_path,
        {"p": _plane(surface="cronjob", allotment={"window": "weekly"})},
        [_job("p/x", "p", "0 9 * * MON", tz="Mars/Olympus")],
    )
    run = run_check(tmp_path)
    assert run.returncode == 1
    out = run.stdout
    assert "[A] plane p: `surface`='cronjob'" in out
    assert "`entitlement`" in out and "`window`='weekly'" in out
    assert "unsupported token 'MON'" in out and "unknown time zone 'Mars/Olympus'" in out


def test_declared_row_on_a_derived_plane_is_duplication(tmp_path):
    write_workflow(tmp_path, "deploy", ["17 * * * *"])
    planes = {"github-actions-limen": _plane(jobs_source={"kind": "workflows", "locator": ".github/workflows"})}
    write_registry(tmp_path, planes, [_job("limen/deploy", "github-actions-limen", "17 * * * *")])
    run = run_check(tmp_path)
    assert run.returncode == 1 and "[B] job limen/deploy: plane github-actions-limen derives its jobs" in run.stdout


def test_stagger_ratchet_fails_new_violation_and_rotten_baseline(tmp_path):
    write_workflow(tmp_path, "deploy", ["0 * * * *"])
    write_workflow(tmp_path, "report", ["17 9 * * *"])
    write_workflow(tmp_path, "probe", ["17 * * * *"])
    planes = {"github-actions-limen": _plane(jobs_source={"kind": "workflows", "locator": ".github/workflows"})}
    # nothing baselined: three violations are new
    write_registry(tmp_path, planes, [])
    run = run_check(tmp_path)
    assert run.returncode == 1
    assert "new stagger violation github-actions-limen:limen/deploy:on-the-hour" in run.stdout
    assert "new stagger violation github-actions-limen:limen/report:shared-minute" in run.stdout
    assert "new stagger violation github-actions-limen:limen/probe:shared-minute" in run.stdout
    # fully baselined: green
    base = [
        "github-actions-limen:limen/deploy:on-the-hour",
        "github-actions-limen:limen/report:shared-minute",
        "github-actions-limen:limen/probe:shared-minute",
    ]
    write_registry(tmp_path, planes, [], baseline=base)
    assert run_check(tmp_path).returncode == 0
    # the deploy cron moves off the hour, but its baseline line stays: that rot is itself red
    write_workflow(tmp_path, "deploy", ["23 * * * *"])
    run = run_check(tmp_path)
    assert (
        run.returncode == 1
        and "baseline line github-actions-limen:limen/deploy:on-the-hour names a violation that no longer exists"
        in run.stdout
    )


def test_non_github_planes_are_exempt_from_stagger(tmp_path):
    planes = {
        "chatgpt": _plane(
            provider="openai",
            surface="ui",
            allotment={
                "runs": 15,
                "window": "active-tasks",
                "concurrency": None,
                "source": "t",
                "entitlement": "unverified",
            },
        )
    }
    jobs = [
        _job(
            "chatgpt/a",
            "chatgpt",
            "0 8 * * *",
            tz="America/New_York",
            source_of_truth="ChatGPT app",
            delivery={"kind": "issue-comments", "locator": "x#1"},
        ),
        _job(
            "chatgpt/b",
            "chatgpt",
            "0 * * * *",
            tz="America/New_York",
            source_of_truth="ChatGPT app",
            delivery={"kind": "issue-comments", "locator": "x#1"},
        ),
    ]
    write_registry(tmp_path, planes, jobs)
    assert run_check(tmp_path).returncode == 0


def test_sibling_parity_unverifiable_without_clone_and_verified_with_one(tmp_path):
    planes = {
        "github-actions-ops": _plane(),
        "cloudflare-ops-scheduler": _plane(
            provider="cloudflare",
            allotment={
                "runs": 2000,
                "window": "calendar-day",
                "concurrency": 4,
                "source": "t",
                "entitlement": "verified",
            },
        ),
    }
    jobs = [
        _job(
            "ops/org-hygiene-report",
            "github-actions-ops",
            "36 13 * * *",
            source_of_truth="4444J99/ops:.github/workflows/org-hygiene-report.yml",
        ),
        _job(
            "cloudflare/bountyscope",
            "cloudflare-ops-scheduler",
            "*/30 * * * *",
            allotment={"runs": 48, "window": "calendar-day"},
            source_of_truth="4444J99/ops:cloudflare/src/manifest.ts",
            delivery={"kind": "bookend-tsv", "locator": "y"},
        ),
    ]
    write_registry(tmp_path, planes, jobs)
    run = run_check(tmp_path)
    assert run.returncode == 0 and "unverifiable here, not drift" in run.stdout
    clone = tmp_path / "clones" / "ops"
    (clone / ".git").mkdir(parents=True)
    write_workflow(clone, "org-hygiene-report", ["36 13 * * *"])
    (clone / "cloudflare" / "src").mkdir(parents=True)
    (clone / "cloudflare" / "src" / "manifest.ts").write_text(
        "export const M = [\n  {\n    name: 'bountyscope',\n    ownership: { maxInvocationsPerDay:48, freshnessMs:1 },\n    schedule: '*/30 * * * *',\n  },\n];\n"
    )
    run = run_check(tmp_path, env={"LIMEN_OPS_ROOT": str(clone)})
    assert run.returncode == 0 and "verified against sibling clone" in run.stdout
    # drift in the clone is red: a cron moved, an allowance changed, a workflow appeared
    write_workflow(clone, "org-hygiene-report", ["49 13 * * *"])
    write_workflow(clone, "new-cron", ["11 4 * * *"])
    (clone / "cloudflare" / "src" / "manifest.ts").write_text(
        "export const M = [\n  {\n    name: 'bountyscope',\n    ownership: { maxInvocationsPerDay:96, freshnessMs:1 },\n    schedule: '*/30 * * * *',\n  },\n];\n"
    )
    run = run_check(tmp_path, env={"LIMEN_OPS_ROOT": str(clone)})
    assert run.returncode == 1
    assert "ops/org-hygiene-report: crons ['36 13 * * *'] != sibling ['49 13 * * *']" in run.stdout
    assert "new-cron.yml has crons ['11 4 * * *'] but no registry row" in run.stdout
    assert "allotment.runs 48 != manifest maxInvocationsPerDay 96" in run.stdout


def test_claude_parity_reads_newest_snapshot_by_routine_and_cadence(tmp_path):
    planes = {
        "claude-cloud": _plane(
            provider="anthropic",
            surface="ui+api",
            jobs_source={"kind": "cloud-routines", "locator": "cloud-routines.json"},
            allotment={
                "runs": 100,
                "window": "per-hour",
                "concurrency": None,
                "source": "t",
                "entitlement": "verified",
            },
            fill_policy="floor",
            floor=2,
            evidence={"kind": "claude-snapshot", "locator": "docs/receipts/claude-triggers-snapshot-*.json"},
        )
    }
    write_registry(tmp_path, planes, [])
    (tmp_path / "cloud-routines.json").write_text(
        json.dumps(
            {
                "routines": [
                    {"name": "stale-pr-sweep", "cadence": "weekdays", "enabled": True, "class": "delta-gated"},
                    {"name": "uv-dep-refresh", "cadence": "weekly", "enabled": True, "class": "pr-delivery"},
                ]
            }
        )
    )
    run = run_check(tmp_path)
    assert run.returncode == 0 and "unverifiable here" in run.stdout  # no snapshot yet
    receipts = tmp_path / "docs" / "receipts"
    receipts.mkdir(parents=True)
    old = {
        "observed_at": "2026-09-01T00:00:00Z",
        "triggers": [{"routine": "stale-pr-sweep", "cron": "7 9 * * 1-5", "enabled": True}],
    }
    new = {
        "observed_at": "2026-10-23T00:00:00Z",
        "triggers": [
            {
                "routine": "stale-pr-sweep",
                "cron": "7 9 * * *",
                "enabled": False,
            },  # live cron is daily, manifest says weekdays
            {"routine": "ghost-routine", "cron": "1 1 * * *", "enabled": True, "id": "trig_x"},
        ],
    }
    (receipts / "claude-triggers-snapshot-20260901.json").write_text(json.dumps(old))
    (receipts / "claude-triggers-snapshot-20261023.json").write_text(json.dumps(new))
    run = run_check(tmp_path)
    assert run.returncode == 1
    assert "routine stale-pr-sweep: manifest cadence 'weekdays' but live cron '7 9 * * *' is daily" in run.stdout
    assert (
        "routine uv-dep-refresh: enabled in cloud-routines.json but absent from claude-triggers-snapshot-20261023.json"
        in run.stdout
    )
    assert "live trigger routine 'ghost-routine' (trig_x) is not in cloud-routines.json" in run.stdout


def test_registry_readers_are_an_allowlist_and_never_effectors(tmp_path):
    write_registry(tmp_path, {"p": _plane(fill_policy="idle-by-design")}, [])
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "schedule-utilization.py").write_text("import _schedules\n")
    assert run_check(tmp_path).returncode == 0
    (scripts / "jules-dispatch.py").write_text("from _schedules import load_registry\n")
    run = run_check(tmp_path)
    assert (
        run.returncode == 1
        and "[G] scripts/jules-dispatch.py reads the SCHEDULES registry but is not an allowlisted reader" in run.stdout
    )
    (scripts / "jules-dispatch.py").unlink()
    (tmp_path / "institutio" / "governance" / "outbound-effectors.yaml").write_text(
        "effectors:\n  - predicate: scripts/schedule-utilization.py\n"
    )
    run = run_check(tmp_path)
    assert run.returncode == 1 and "named in outbound-effectors.yaml" in run.stdout


def test_slot_map_lists_every_fire_in_utc_with_flags(tmp_path):
    write_workflow(tmp_path, "deploy", ["0 */12 * * *"])
    planes = {
        "github-actions-limen": _plane(jobs_source={"kind": "workflows", "locator": ".github/workflows"}),
        "chatgpt": _plane(
            provider="openai",
            surface="ui",
            allotment={
                "runs": 15,
                "window": "active-tasks",
                "concurrency": None,
                "source": "t",
                "entitlement": "unverified",
            },
        ),
    }
    write_registry(
        tmp_path,
        planes,
        [
            _job(
                "chatgpt/landing",
                "chatgpt",
                "0 13,19 * * *",
                tz="America/New_York",
                source_of_truth="app",
                delivery={"kind": "issue-comments", "locator": "x#1"},
            )
        ],
        baseline=["github-actions-limen:limen/deploy:on-the-hour"],
    )
    run = run_check(tmp_path, "--slot-map", "--day", "2026-10-23")
    assert run.returncode == 0
    rows = [line for line in run.stdout.splitlines() if line.startswith("| ") and "job" not in line.split("|")[2]]
    utc = [r.split("|")[1].strip() for r in rows]
    assert utc == ["00:00", "12:00", "17:00", "23:00"]
    assert "on-the-hour" in rows[0]


# ── schedule-utilization ─────────────────────────────────────────────────────────────────────


def _reader(value, detail="stub"):
    return lambda pid, plane, jobs, today, root: (value, detail)


def test_verdict_matrix_unmeasured_is_never_red():
    full = _plane()
    assert UTIL.verdict_for(full, declared=10, observed=9, fill_floor=0.5) == "full"
    assert UTIL.verdict_for(full, declared=10, observed=4, fill_floor=0.5) == "underfilled"
    assert UTIL.verdict_for(full, declared=10, observed=0, fill_floor=0.5) == "dark"
    assert UTIL.verdict_for(full, declared=10, observed=None, fill_floor=0.5) == "unmeasured"
    assert UTIL.verdict_for(full, declared=0, observed=None, fill_floor=0.5) == "unmeasured"
    assert (
        UTIL.verdict_for(_plane(fill_policy="idle-by-design"), declared=0, observed=0, fill_floor=0.5)
        == "idle-by-design"
    )
    floor = _plane(fill_policy="floor", floor=13, allotment={"runs": 100, "window": "per-hour"})
    assert UTIL.verdict_for(floor, declared=5, observed=5, fill_floor=0.5) == "unscheduled-headroom"
    assert UTIL.verdict_for(floor, declared=13, observed=0, fill_floor=0.5) == "dark"
    assert UTIL.verdict_for(floor, declared=13, observed=6, fill_floor=0.5) == "underfilled"
    assert UTIL.verdict_for(floor, declared=13, observed=13, fill_floor=0.5) == "full"
    jules = _plane(fill_policy="floor", floor=25, allotment={"runs": 100, "window": "rolling-24h"})
    assert UTIL.verdict_for(jules, declared=25, observed=3, fill_floor=0.5) == "underfilled"
    comments = _plane(evidence={"kind": "issue-comments", "locator": "x#1"})
    assert UTIL.verdict_for(comments, declared=27, observed=1, fill_floor=0.5) == "partial-evidence"


def test_summarize_runs_counts_only_successes_as_observed():
    rows = [
        {"conclusion": "success"},
        {"conclusion": "failure"},
        {"conclusion": "startup_failure"},
        {"conclusion": None},
        "junk",
    ]
    assert UTIL.summarize_runs(rows) == (1, 2)


def test_declared_fires_are_pro_rated_to_now(tmp_path):
    planes = {"p": _plane(evidence={"kind": "gh-actions-runs", "locator": "o/r"})}
    write_registry(
        tmp_path,
        planes,
        [_job("p/hourly", "p", "17 * * * *", source_of_truth="4444J99/ops:.github/workflows/hourly.yml")],
    )
    noon = UTIL.evaluate(tmp_path, TODAY, readers={"gh-actions-runs": _reader(12)}, now=NOW)
    assert noon["planes"][0]["declared"] == 12 and noon["planes"][0]["verdict"] == "full"
    end = UTIL.evaluate(
        tmp_path,
        TODAY,
        readers={"gh-actions-runs": _reader(12)},
        now=datetime(2026, 10, 23, 23, 59, tzinfo=timezone.utc),
    )
    assert end["planes"][0]["declared"] == 24 and end["planes"][0]["verdict"] == "full"
    assert (
        UTIL.evaluate(
            tmp_path,
            TODAY,
            readers={"gh-actions-runs": _reader(5)},
            now=end["as_of"] and datetime(2026, 10, 23, 23, 59, tzinfo=timezone.utc),
        )["planes"][0]["verdict"]
        == "underfilled"
    )
    yesterday = UTIL.evaluate(tmp_path, date(2026, 10, 22), readers={"gh-actions-runs": _reader(24)}, now=NOW)
    assert yesterday["planes"][0]["declared"] == 24


def test_evaluate_status_and_effector_and_broken_reader(tmp_path):
    planes = {
        "a": _plane(evidence={"kind": "bookend-tsv", "locator": "o/r:bookends"}, effector="ops keepalive"),
        "b": _plane(
            provider="xai",
            surface="ui",
            allotment={
                "runs": None,
                "window": "active-tasks",
                "concurrency": None,
                "source": "t",
                "entitlement": "unpublished",
            },
        ),
        "c": _plane(evidence={"kind": "witness-audit", "locator": "o/w:audit"}),
    }
    jobs = [
        _job("a/report", "a", "36 1 * * *"),
        _job("c/t", "c", "0 12 * * *", source_of_truth="4444J99/ops:cloudflare/src/manifest.ts"),
    ]
    write_registry(tmp_path, planes, jobs)

    def boom(pid, plane, jobs, today, root):
        raise RuntimeError("network")

    report = UTIL.evaluate(
        tmp_path, TODAY, readers={"bookend-tsv": _reader(0, "absent"), "witness-audit": boom}, now=NOW
    )
    by = {p["plane"]: p for p in report["planes"]}
    assert by["a"]["verdict"] == "dark" and by["a"]["effector"] == "ops keepalive"
    assert by["b"]["verdict"] == "unmeasured" and "declare a delivery locator" in by["b"]["detail"]
    assert by["c"]["verdict"] == "unmeasured" and "reader error: RuntimeError" in by["c"]["detail"]
    assert report["status"] == "fail" and report["red"] == ["a"] and set(report["unmeasured"]) == {"b", "c"}


def test_claude_snapshot_reader_age_and_enabled_count(tmp_path, monkeypatch):
    planes = {
        "claude-cloud": _plane(
            provider="anthropic",
            surface="ui+api",
            jobs_source={"kind": "cloud-routines", "locator": "cloud-routines.json"},
            allotment={
                "runs": 100,
                "window": "per-hour",
                "concurrency": None,
                "source": "t",
                "entitlement": "verified",
            },
            fill_policy="floor",
            floor=2,
            evidence={"kind": "claude-snapshot", "locator": "docs/receipts/claude-triggers-snapshot-*.json"},
        )
    }
    write_registry(tmp_path, planes, [])
    (tmp_path / "cloud-routines.json").write_text(
        json.dumps(
            {
                "routines": [
                    {"name": "a", "cadence": "daily", "enabled": True},
                    {"name": "b", "cadence": "daily", "enabled": True},
                ]
            }
        )
    )
    receipts = tmp_path / "docs" / "receipts"
    receipts.mkdir(parents=True)
    (receipts / "claude-triggers-snapshot-20261022.json").write_text(
        json.dumps(
            {
                "observed_at": "2026-10-22T00:00:00Z",
                "triggers": [
                    {"routine": "a", "cron": "1 1 * * *", "enabled": False, "last_run_failure_reason": "ACCESS_DENIED"},
                    {"routine": "b", "cron": "2 2 * * *", "enabled": True},
                ],
            }
        )
    )
    report = UTIL.evaluate(tmp_path, TODAY, now=NOW)
    plane = report["planes"][0]
    assert plane["declared"] == 2 and plane["observed"] is None and plane["verdict"] == "unmeasured"
    assert plane["configured_enabled"] == 1 and plane["measurement_kind"] == "configuration"
    assert "1 last failed ACCESS_DENIED" in plane["detail"]
    monkeypatch.setenv("LIMEN_SCHEDULE_SNAPSHOT_MAX_AGE_DAYS", "1")
    report = UTIL.evaluate(tmp_path, date(2026, 10, 30), now=datetime(2026, 10, 30, 12, tzinfo=timezone.utc))
    assert report["planes"][0]["verdict"] == "unmeasured" and "re-export" in report["planes"][0]["detail"]


def test_bookend_reader_pairs_start_and_end(tmp_path, monkeypatch):
    clone = tmp_path / "ops"
    (clone / ".git").mkdir(parents=True)
    (clone / "bookends").mkdir()
    (clone / "bookends" / f"{TODAY.isoformat()}.tsv").write_text(
        "2026-10-23T13:36:00Z\torg-hygiene-report\t-\t-\tstart\trunning\n"
        "2026-10-23T13:37:00Z\torg-hygiene-report\t-\t-\tend\tsuccess\n"
        "2026-10-23T14:00:00Z\tdied-mid-run\t-\t-\tstart\trunning\n"
    )
    monkeypatch.setenv("LIMEN_OPS_ROOT", str(clone))
    plane = _plane(evidence={"kind": "bookend-tsv", "locator": "4444J99/ops:bookends"})
    observed, detail = UTIL.read_bookend_tsv("github-actions-ops", plane, [], TODAY, tmp_path)
    assert observed == 1 and "org-hygiene-report" in detail and "died-mid-run" not in detail


def test_declared_off_reconciles_against_live_workflow_state(tmp_path, monkeypatch):
    planes = {
        "github-actions-limen": _plane(
            jobs_source={"kind": "workflows", "locator": ".github/workflows"},
            evidence={"kind": "gh-actions-runs", "locator": "o/r"},
            declared_off=[{"file": "deploy.yml", "since": "x", "reason": "parked"}],
        )
    }
    write_workflow(tmp_path, "deploy", ["0 * * * *"])
    write_workflow(tmp_path, "report", ["17 9 * * *"])
    write_registry(tmp_path, planes, [], baseline=["github-actions-limen:limen/deploy:on-the-hour"])
    monkeypatch.setattr(UTIL, "gh_available", lambda: True)
    monkeypatch.setattr(UTIL, "gh_json", lambda args: [{"conclusion": "success"}] if args[0] == "run" else None)
    # deploy disabled + declared off, report active: clean
    monkeypatch.setattr(
        UTIL, "workflow_states", lambda repo: {"deploy.yml": "disabled_manually", "report.yml": "active"}
    )
    plane = UTIL.evaluate(tmp_path, TODAY, now=NOW)["planes"][0]
    assert plane["verdict"] == "full" and "declared off, not counted: deploy.yml=disabled_manually" in plane["detail"]
    # report disabled but nobody declared it: red, owner-named
    monkeypatch.setattr(
        UTIL, "workflow_states", lambda repo: {"deploy.yml": "disabled_manually", "report.yml": "disabled_inactivity"}
    )
    plane = UTIL.evaluate(tmp_path, TODAY, now=NOW)["planes"][0]
    assert plane["verdict"] == "undeclared-off" and "UNDECLARED OFF" in plane["detail"]
    # deploy declared off but active live: the declaration rotted
    monkeypatch.setattr(UTIL, "workflow_states", lambda repo: {"deploy.yml": "active", "report.yml": "active"})
    plane = UTIL.evaluate(tmp_path, TODAY, now=NOW)["planes"][0]
    assert plane["verdict"] == "declared-off-but-active"


def test_stale_readback_is_distinct_from_green_and_red(tmp_path):
    planes = {
        "measurable": _plane(evidence={"kind": "witness-audit", "locator": "o/w:audit"}),
        "declared-unmeasurable": _plane(
            provider="xai",
            surface="ui",
            allotment={
                "runs": None,
                "window": "active-tasks",
                "concurrency": None,
                "source": "t",
                "entitlement": "unpublished",
            },
        ),
    }
    write_registry(
        tmp_path,
        planes,
        [_job("measurable/t", "measurable", "0 12 * * *", source_of_truth="4444J99/ops:cloudflare/src/manifest.ts")],
    )
    report = UTIL.evaluate(tmp_path, TODAY, readers={"witness-audit": _reader(None, "19d old")}, now=NOW)
    assert (
        report["status"] == "stale-readback"
        and report["stale_readback"] == ["measurable"]
        and report["measured"] == "0/1"
    )
    assert report["red"] == []
    report = UTIL.evaluate(tmp_path, TODAY, readers={"witness-audit": _reader(1)}, now=NOW)
    assert report["status"] == "pass" and report["measured"] == "1/1"
    by = {p["plane"]: p for p in report["planes"]}
    assert by["measurable"]["execution_gap"] == 0 and by["declared-unmeasurable"]["allocation_gap"] is None


def test_unreadable_plane_becomes_stale_readback_after_its_budget(tmp_path, monkeypatch):
    planes = {
        "grok": _plane(
            provider="xai",
            surface="ui",
            declared_on="2026-10-01",
            allotment={
                "runs": None,
                "window": "active-tasks",
                "concurrency": None,
                "source": "t",
                "entitlement": "unpublished",
            },
            authority={"owner_repo": "4444J99/ops", "upstream_state": "proposed", "note": "t"},
        )
    }
    write_registry(tmp_path, planes, [])
    fresh = UTIL.evaluate(tmp_path, date(2026, 10, 23), now=datetime(2026, 10, 23, 12, tzinfo=timezone.utc))
    assert (
        fresh["status"] == "pass"
        and fresh["planes"][0]["verdict"] == "unmeasured"
        and "readback budget left" in fresh["planes"][0]["detail"]
    )
    assert fresh["planes"][0]["upstream_state"] == "proposed"
    late = UTIL.evaluate(tmp_path, date(2026, 11, 5), now=datetime(2026, 11, 5, 12, tzinfo=timezone.utc))
    assert (
        late["status"] == "stale-readback"
        and late["stale_readback"] == ["grok"]
        and late["planes"][0]["readback_overdue"]
    )
    monkeypatch.setenv("LIMEN_SCHEDULE_READBACK_MAX_AGE_DAYS", "60")
    assert (
        UTIL.evaluate(tmp_path, date(2026, 11, 5), now=datetime(2026, 11, 5, 12, tzinfo=timezone.utc))["status"]
        == "pass"
    )


def test_receipt_is_written_atomically_with_history(tmp_path):
    planes = {"p": _plane(fill_policy="idle-by-design")}
    write_registry(tmp_path, planes, [])
    report = UTIL.evaluate(tmp_path, TODAY, now=NOW)
    report["generated_at"] = NOW.isoformat()
    receipt = tmp_path / "logs" / "schedule-utilization.json"
    UTIL.write_receipt(receipt, report, receipt.with_suffix(".jsonl"))
    assert json.loads(receipt.read_text())["status"] == "pass"
    assert not list((tmp_path / "logs").glob(".schedule-utilization.*.tmp"))
    rows = [json.loads(line) for line in receipt.with_suffix(".jsonl").read_text().splitlines()]
    assert rows == [
        {
            "ts": NOW.isoformat(),
            "day": TODAY.isoformat(),
            "plane": "p",
            "allotment": None,
            "window": "calendar-day",
            "declared": 0,
            "observed": None,
            "verdict": "idle-by-design",
        }
    ]


def test_collection_deadline_writes_receipt_and_preserves_completed_and_local_evidence(tmp_path, monkeypatch):
    """A remote outage consumes one shared budget, without erasing readable evidence or skipping the receipt."""
    planes = {
        "completed": _plane(evidence={"kind": "gh-actions-runs", "locator": "o/completed"}),
        "outage": _plane(evidence={"kind": "bookend-tsv", "locator": "o/outage:bookends"}),
        "unread": _plane(evidence={"kind": "issue-comments", "locator": "o/unread#1"}),
        "local": _plane(
            evidence={"kind": "voice-stamps", "locator": "logs/.voice"},
            jobs_source={"kind": "sensors", "locator": "sensors.yaml"},
        ),
    }
    write_registry(
        tmp_path,
        planes,
        [_job("completed/job", "completed", "17 1 * * *", source_of_truth="o/completed:.github/workflows/job.yml")],
    )
    (tmp_path / "sensors.yaml").write_text(yaml.safe_dump({"sensors": {"local": {"cadence": 1}}}))
    voice = tmp_path / "logs" / ".voice"
    voice.mkdir(parents=True)
    (voice / "local").write_text("")
    elapsed = [0.0]
    calls = []
    monkeypatch.setenv("LIMEN_SCHEDULE_UTILIZATION_TIMEOUT", "4")
    monkeypatch.setattr(time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(UTIL, "gh_available", lambda: True)

    def remote(args, **kwargs):
        calls.append(args)
        if "actions/workflows" in args[-1]:
            elapsed[0] += 0.25
            payload = {"workflows": [{"path": ".github/workflows/job.yml", "state": "active"}]}
        elif args[1:3] == ["run", "list"]:
            elapsed[0] += 0.25
            payload = [{"conclusion": "success"}]
        else:
            elapsed[0] += kwargs["timeout"]
            raise subprocess.TimeoutExpired(args, kwargs["timeout"])
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(UTIL.subprocess, "run", remote)
    receipt = tmp_path / "logs" / "schedule-utilization.json"
    assert UTIL.main(["--root", str(tmp_path), "--day", TODAY.isoformat(), "--receipt", str(receipt)]) == 3
    report = json.loads(receipt.read_text())
    by = {p["plane"]: p for p in report["planes"]}
    assert elapsed[0] <= 2.0  # half the sensor's four-second ceiling remains for receipt/other local work
    assert len(calls) == 3  # the later remote plane never starts another independent timeout
    assert by["completed"]["observed"] == 1 and by["local"]["observed"] == 1
    for pid in ("outage", "unread"):
        assert by[pid]["observed"] is None and by[pid]["verdict"] == "unmeasured"
        assert "collection deadline reached" in by[pid]["detail"]
    assert report["status"] == "stale-readback" and report["red"] == []
    assert len(receipt.with_suffix(".jsonl").read_text().splitlines()) == 4


def test_collection_deadline_cli_finishes_before_sensor_timeout_during_outage(tmp_path):
    """An actual blocked gh process cannot prevent the sensor from replacing its stale receipt."""
    write_registry(
        tmp_path,
        {
            "actions": _plane(evidence={"kind": "gh-actions-runs", "locator": "o/r"}),
            "bookends": _plane(evidence={"kind": "bookend-tsv", "locator": "o/r:bookends"}),
        },
        [],
    )
    bindir = tmp_path / "bin"
    bindir.mkdir()
    gh = bindir / "gh"
    gh.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(30)\n")
    gh.chmod(0o755)
    receipt = tmp_path / "receipt.json"
    receipt.write_text('{"stale": true}\n')
    started = time.monotonic()
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPTS / "schedule-utilization.py"), "--root", str(tmp_path), "--receipt", str(receipt)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        env={"PATH": str(bindir), "HOME": str(tmp_path), "LIMEN_SCHEDULE_UTILIZATION_TIMEOUT": "4"},
    )
    try:
        stdout, stderr = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        pytest.fail("collector exceeded the sensor timeout without publishing a bounded outage receipt")
    assert proc.returncode == 3, stdout + stderr
    assert time.monotonic() - started < 4
    report = json.loads(receipt.read_text())
    assert report["status"] == "stale-readback" and report["measured"] == "0/2"
    assert all(p["observed"] is None and "collection deadline reached" in p["detail"] for p in report["planes"])
    assert len(receipt.with_suffix(".jsonl").read_text().splitlines()) == 2


def test_real_registry_evaluates_without_network(tmp_path, monkeypatch):
    """The shipped registry must evaluate end to end with every network reader stubbed — no crash, every plane classified."""
    stubs = {kind: _reader(None, "stubbed") for kind in UTIL.READERS}
    report = UTIL.evaluate(ROOT, TODAY, readers=stubs, now=NOW)
    assert {p["plane"] for p in report["planes"]} >= {
        "claude-cloud",
        "jules",
        "github-actions-ops",
        "grok-automations",
        "gemini-scheduled-actions",
    }
    assert all(p["verdict"] in {"unmeasured", "idle-by-design", "unscheduled-headroom"} for p in report["planes"]), (
        report["planes"]
    )


# ── review round 1 (PR #3178, Codex): the three ways a plane read GREEN or RED for the wrong reason ──


def test_sensor_cadence_is_beats_and_converts_at_worst_case_loop_max(tmp_path):
    """sensors.yaml `cadence` is BEATS (beat-sensors.py `_due`), not hours: cadence 48 at the default 1,800s
    loop ceiling is a daily sensor and must stay inside the daily-or-faster set."""
    (tmp_path / "sensors.yaml").write_text(
        yaml.safe_dump(
            {
                "sensors": {
                    "daily-at-48": {"cadence": {"default": 48}, "source": ["heartbeat"]},
                    "six-hourly": {"cadence": 12, "source": ["heartbeat"]},
                    "over-a-day": {"cadence": {"default": 49}, "source": ["heartbeat"]},
                    "every-beat": {"cadence": 1, "source": ["metabolize"]},
                    "uncadenced": {"source": ["metabolize"]},
                }
            }
        )
    )
    jobs = S.derive_sensor_jobs(tmp_path, "limen-beat", "sensors.yaml", loop_max=1800)
    by_id = {j.id: (j.cadence_beats, j.cadence_hours) for j in jobs}
    assert by_id == {
        "beat/daily-at-48": (48, 24),
        "beat/six-hourly": (12, 6),
        "beat/over-a-day": (49, 25),
        "beat/every-beat": (1, 1),
    }
    assert all(j.extra["loop_max_seconds"] == 1800 for j in jobs)
    assert S.beats_to_hours(48, 900) == 12 and S.beats_to_hours(1, 60) == 1
    assert S.beat_loop_max({"LIMEN_LOOP_MAX": "900"}) == 900
    assert S.beat_loop_max({"LIMEN_LOOP_MAX": "junk"}) == S.BEAT_LOOP_MAX_SECONDS
    assert S.beat_loop_max({}) == 1800
    plane = _plane(
        evidence={"kind": "voice-stamps", "locator": "logs/.voice"},
        allotment={"runs": None, "window": "per-beat", "concurrency": 1, "source": "t", "entitlement": "verified"},
    )
    assert UTIL.declared_for(plane, jobs, TODAY, NOW) == 3  # 48, 12 and 1 beats; 49 beats is 25h, excluded
    # The shipped registry: the three cadence-48 sensors Codex named are daily, so they count.
    real = {j.id: j.cadence_hours for j in S.derive_sensor_jobs(ROOT, "limen-beat", loop_max=1800)}
    assert {real["beat/daily-execution"], real["beat/conversion-funnel"], real["beat/collaboration-hub-sync"]} == {24}


def test_sensor_cadence_overrides_drive_freshness_and_daily_membership(tmp_path, monkeypatch):
    """Longer and shorter host cadences must move both the daily set and each stamp's freshness bound."""
    sensors = {
        "host-relief": {"cadence": {"env": "LIMEN_BEAT_HOST_RELIEF", "default": 1}},
        "moved-out": {"cadence": {"env": "TEST_CADENCE_OUT", "default": 48}},
        "moved-in": {"cadence": {"env": "TEST_CADENCE_IN", "default": 49}},
    }
    (tmp_path / "sensors.yaml").write_text(yaml.safe_dump({"sensors": sensors}))
    monkeypatch.setenv("LIMEN_BEAT_HOST_RELIEF", "16")
    monkeypatch.setenv("TEST_CADENCE_OUT", "49")
    monkeypatch.setenv("TEST_CADENCE_IN", "1")
    jobs = S.derive_sensor_jobs(tmp_path, "limen-beat", "sensors.yaml", loop_max=1800)
    by = {j.id: j for j in jobs}
    assert {j.id: (j.cadence_beats, j.cadence_hours) for j in jobs} == {
        "beat/host-relief": (16, 8),
        "beat/moved-out": (49, 25),
        "beat/moved-in": (1, 1),
    }
    assert by["beat/host-relief"].extra["cadence_default_beats"] == 1
    assert by["beat/host-relief"].extra["cadence_env"] == "LIMEN_BEAT_HOST_RELIEF"
    voice = tmp_path / "logs" / ".voice"
    voice.mkdir(parents=True)
    two_hours_ago = time.time() - 2 * 3600
    for sid in sensors:
        stamp = voice / sid
        stamp.write_text("")
        os.utime(stamp, (two_hours_ago, two_hours_ago))
    plane = _plane(evidence={"kind": "voice-stamps", "locator": "logs/.voice"})
    observed, detail = UTIL.read_voice_stamps("limen-beat", plane, jobs, TODAY, tmp_path)
    assert observed == 1 and detail.startswith("1/2 ")
    assert "moved-in (2h)" in detail and "host-relief" not in detail.split("late:")[1]
    assert UTIL.declared_for(plane, jobs, TODAY, NOW) == 2
    assert UTIL._stamp_bound_seconds(by["beat/host-relief"]) == 16 * 1800 * 2


@pytest.mark.parametrize(
    ("cadence", "override", "expected"),
    [
        ({"env": "TEST_CADENCE", "default": "4"}, "9", 9),
        ({"env": "TEST_CADENCE", "default": "4"}, "bad", 4),
        ({"env": "TEST_CADENCE", "default": 4}, "0", 4),
        ({"env": "TEST_CADENCE", "default": 4}, "-2", 4),
        ({"env": "TEST_CADENCE", "default": 4}, "", 4),
        ({"env": "TEST_CADENCE"}, "7", 7),
        ({"env": "TEST_CADENCE"}, "bad", None),
        ("6", "9", 6),
    ],
)
def test_sensor_cadence_uses_heartbeat_positive_integer_fallbacks(tmp_path, monkeypatch, cadence, override, expected):
    (tmp_path / "sensors.yaml").write_text(yaml.safe_dump({"sensors": {"sample": {"cadence": cadence}}}))
    monkeypatch.setenv("TEST_CADENCE", override)
    jobs = S.derive_sensor_jobs(tmp_path, "limen-beat", "sensors.yaml")
    assert BEAT._positive_int(cadence) == expected
    assert (jobs[0].cadence_beats if jobs else None) == expected


@pytest.mark.parametrize("flags", [(), ("--slot-map",)])
def test_checker_exposes_resolved_sensor_cadence_override(tmp_path, flags):
    write_registry(
        tmp_path,
        {"limen-beat": _plane(jobs_source={"kind": "sensors", "locator": "sensors.yaml"})},
        [],
    )
    (tmp_path / "sensors.yaml").write_text(
        yaml.safe_dump({"sensors": {"host-relief": {"cadence": {"env": "LIMEN_BEAT_HOST_RELIEF", "default": 1}}}})
    )
    run = run_check(tmp_path, *flags, env={"LIMEN_BEAT_HOST_RELIEF": "16"})
    assert run.returncode == 0, run.stdout + run.stderr
    assert "beat/host-relief" in run.stdout and "cadence override" in run.stdout
    assert "LIMEN_BEAT_HOST_RELIEF=16" in run.stdout and "registry default 1" in run.stdout


def test_board_reader_treats_public_projection_as_unmeasured(tmp_path, monkeypatch):
    """The public checkout's tasks.yaml is a redacted projection (schema limen.public_board_projection.v1,
    tasks: []). It proves nothing about jules launches, so it is UNMEASURED — never 0 and never dark."""
    monkeypatch.delenv("LIMEN_TASKS", raising=False)
    monkeypatch.delenv("LIMEN_ROOT", raising=False)
    plane = _plane(
        evidence={"kind": "board-dispatch-receipts", "locator": "tasks.yaml"},
        allotment={"runs": 100, "window": "rolling-24h", "concurrency": 15, "source": "t", "entitlement": "unverified"},
        fill_policy="floor",
        floor=25,
    )
    # the shipped checkout IS the public projection
    observed, detail = UTIL.read_board_dispatch_receipts("jules", plane, [], TODAY, ROOT)
    assert observed is None and "public projection" in detail and "LIMEN_TASKS" in detail
    assert UTIL.verdict_for(plane, 25, observed, 0.5) == "unmeasured"
    # a copy of it under a tmp root reads the same way
    (tmp_path / "tasks.yaml").write_text((ROOT / "tasks.yaml").read_text())
    assert UTIL.read_board_dispatch_receipts("jules", plane, [], TODAY, tmp_path)[0] is None
    assert UTIL.is_public_projection({"portal": {"public_projection": {}}, "tasks": []})
    assert not UTIL.is_public_projection({"tasks": [{"id": "t1"}]})
    # a real board (dispatch_log rows) counts jules launches inside the rolling 24h only
    now = datetime.now(timezone.utc)
    stamp = lambda hours: (now - __import__("datetime").timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    board = {
        "tasks": [
            {
                "id": "t1",
                "dispatch_log": [
                    {"agent": "jules", "status": "dispatched", "timestamp": stamp(1)},
                    {"agent": "jules", "status": "dispatched", "timestamp": stamp(30)},
                    {"agent": "codex", "status": "dispatched", "timestamp": stamp(1)},
                    {"agent": "jules", "status": "failed", "timestamp": stamp(2)},
                ],
            }
        ]
    }
    live = tmp_path / "live"
    live.mkdir()
    (live / "tasks.yaml").write_text(yaml.safe_dump(board))
    monkeypatch.setenv("LIMEN_ROOT", str(live))
    assert UTIL.board_path(tmp_path, "tasks.yaml") == live / "tasks.yaml"
    observed, detail = UTIL.read_board_dispatch_receipts("jules", plane, [], TODAY, tmp_path)
    assert observed == 1 and "jules launches" in detail
    explicit = tmp_path / "elsewhere.yaml"
    explicit.write_text(yaml.safe_dump({"tasks": []}))
    monkeypatch.setenv("LIMEN_TASKS", str(explicit))
    assert UTIL.board_path(tmp_path, "tasks.yaml") == explicit
    assert UTIL.read_board_dispatch_receipts("jules", plane, [], TODAY, tmp_path)[0] == 0  # a real, empty board IS zero


def test_bookend_reader_distinguishes_unreadable_from_absent(tmp_path, monkeypatch):
    """No clone + a failed Contents read is UNMEASURED; a confirmed 404 is an observed empty day (0)."""
    monkeypatch.delenv("LIMEN_OPS_ROOT", raising=False)
    monkeypatch.delenv("LIMEN_WORKDIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))  # no ~/Workspace/ops here
    plane = _plane(evidence={"kind": "bookend-tsv", "locator": "4444J99/ops:bookends"})
    rel = f"bookends/{TODAY.isoformat()}.tsv"
    real_gh_contents = UTIL._gh_contents

    monkeypatch.setattr(UTIL, "_gh_contents", lambda repo, r: (None, UTIL.UNREADABLE))
    observed, detail = UTIL.read_bookend_tsv("github-actions-ops", plane, [], TODAY, tmp_path)
    assert observed is None and "unmeasured, not zero" in detail
    assert UTIL.verdict_for(plane, 3, observed, 0.5) == "unmeasured"

    monkeypatch.setattr(UTIL, "_gh_contents", lambda repo, r: (None, UTIL.ABSENT))
    observed, detail = UTIL.read_bookend_tsv("github-actions-ops", plane, [], TODAY, tmp_path)
    assert observed == 0 and "confirmed absent" in detail and rel in detail

    tsv = "2026-10-23T13:36:00Z\torg-hygiene-report\t-\t-\tstart\trunning\n2026-10-23T13:37:00Z\torg-hygiene-report\t-\t-\tend\tsuccess\n"
    monkeypatch.setattr(UTIL, "_gh_contents", lambda repo, r: (tsv, UTIL.PRESENT))
    assert UTIL.read_bookend_tsv("github-actions-ops", plane, [], TODAY, tmp_path)[0] == 1

    # _gh_contents itself: a bare 404 proves nothing (an unauthenticated read of a private repo is a 404 too);
    # absence is confirmed only by a parent-folder listing that lacks the file.
    class Run:
        def __init__(self, code, out):
            self.returncode, self.stdout = code, out

    file_api, folder_api = f"repos/4444J99/ops/contents/{rel}", "repos/4444J99/ops/contents/bookends"
    not_found = Run(1, '{"message":"Not Found","status":"404"}')
    listing_without = Run(0, json.dumps([{"name": ".gitkeep"}, {"name": "2026-10-22.tsv"}]))
    listing_with = Run(0, json.dumps([{"name": ".gitkeep"}, {"name": f"{TODAY.isoformat()}.tsv"}]))

    def fake_run(responses):
        return lambda argv, **k: responses[argv[2]]

    monkeypatch.setattr(UTIL, "gh_available", lambda: True)
    monkeypatch.setattr(UTIL.subprocess, "run", fake_run({file_api: not_found, folder_api: listing_without}))
    assert real_gh_contents("4444J99/ops", rel) == (None, UTIL.ABSENT)
    monkeypatch.setattr(UTIL.subprocess, "run", fake_run({file_api: not_found, folder_api: not_found}))
    assert real_gh_contents("4444J99/ops", rel) == (
        None,
        UTIL.UNREADABLE,
    )  # the folder is invisible too: private+unauth
    monkeypatch.setattr(UTIL.subprocess, "run", fake_run({file_api: not_found, folder_api: listing_with}))
    assert real_gh_contents("4444J99/ops", rel) == (
        None,
        UTIL.UNREADABLE,
    )  # listed but unreadable: contradictory, not absent
    monkeypatch.setattr(UTIL.subprocess, "run", fake_run({file_api: Run(1, ""), folder_api: listing_without}))
    assert real_gh_contents("4444J99/ops", rel) == (None, UTIL.UNREADABLE)  # network cut: no body, no 404
    monkeypatch.setattr(
        UTIL.subprocess, "run", fake_run({file_api: Run(1, '{"message":"Bad credentials","status":"401"}')})
    )
    assert real_gh_contents("4444J99/ops", rel) == (None, UTIL.UNREADABLE)
    encoded = __import__("base64").b64encode(tsv.encode()).decode()
    monkeypatch.setattr(
        UTIL.subprocess, "run", fake_run({file_api: Run(0, json.dumps({"encoding": "base64", "content": encoded}))})
    )
    assert real_gh_contents("4444J99/ops", rel) == (tsv, UTIL.PRESENT)
    monkeypatch.setattr(UTIL, "gh_available", lambda: False)
    assert real_gh_contents("4444J99/ops", rel) == (None, UTIL.UNREADABLE)


def test_voice_reader_treats_a_never_stamped_directory_as_unmeasured(tmp_path):
    """A voice dir that exists but was never stamped (a worktree, CI) is not a dark heartbeat — unmeasured."""
    (tmp_path / "logs" / ".voice").mkdir(parents=True)
    plane = _plane(evidence={"kind": "voice-stamps", "locator": "logs/.voice"})
    jobs = [
        S.Job(
            id="beat/x", plane="limen-beat", crons=[], tz="UTC", enabled=True, derived=True, source="s", cadence_hours=6
        )
    ]
    observed, detail = UTIL.read_voice_stamps("limen-beat", plane, jobs, TODAY, tmp_path)
    assert observed is None and "no stamps at all" in detail
    (tmp_path / "logs" / ".voice" / "y").write_text("")  # a stale stamp from another day: now it IS a beating host
    observed, detail = UTIL.read_voice_stamps("limen-beat", plane, jobs, date(2020, 1, 1), tmp_path)
    assert observed == 0 and "0/1" in detail


# ── review round 2 (PR #3178, Codex): claims vs launches, cadence windows vs midnight, four readbacks ──


def test_board_reader_counts_confirmed_launches_not_claims(tmp_path, monkeypatch):
    """A `dispatched` row is a claim (AGENTS.md task states). The serial dispatcher writes a reservation row
    before the provider runs and `_apply_result` writes the confirmed submission; only the latter is a launch,
    and a launch echoed by several rows is still one launch."""
    monkeypatch.delenv("LIMEN_TASKS", raising=False)
    monkeypatch.delenv("LIMEN_ROOT", raising=False)
    import datetime as _dt

    now = datetime.now(timezone.utc)
    stamp = lambda hours: (now - _dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    reservation = "dispatch-serial: canonical claim requested before provider execution"
    board = {
        "tasks": [
            {  # serial: reservation + confirmed submission = ONE launch
                "id": "t1",
                "dispatch_log": [
                    {
                        "agent": "jules",
                        "status": "dispatched",
                        "session_id": "a" * 64,
                        "timestamp": stamp(2),
                        "output": reservation,
                    },
                    {
                        "agent": "jules",
                        "status": "dispatched",
                        "session_id": "jules://session/1",
                        "timestamp": stamp(2),
                    },
                ],
            },
            {  # parallel: reservation + confirmed submission = ONE launch
                "id": "t2",
                "dispatch_log": [
                    {
                        "agent": "jules",
                        "status": "dispatched",
                        "session_id": "reserve",
                        "timestamp": stamp(3),
                        "output": "dispatch-parallel: reserved before agent execution",
                    },
                    {
                        "agent": "jules",
                        "status": "dispatched",
                        "session_id": "jules://session/2",
                        "timestamp": stamp(3),
                    },
                ],
            },
            {  # reservation whose provider launch never started: released, NOT a launch
                "id": "t3",
                "dispatch_log": [
                    {
                        "agent": "jules",
                        "status": "dispatched",
                        "session_id": "b" * 64,
                        "timestamp": stamp(4),
                        "output": reservation,
                    },
                    {
                        "agent": "jules",
                        "status": "open",
                        "session_id": "daemon",
                        "timestamp": stamp(4),
                        "output": "provider launch did not start; canonical claim released: x",
                    },
                ],
            },
            {  # lifecycle guard keeping an open-PR task out of churn: NOT a launch
                "id": "t4",
                "dispatch_log": [
                    {
                        "agent": "jules",
                        "status": "dispatched",
                        "session_id": "pr-open-lifecycle-guard",
                        "timestamp": stamp(1),
                        "output": "dispatch result ignored because this task already recorded an open PR",
                    },
                ],
            },
            {  # the same confirmed submission echoed twice = ONE launch; one outside the window = none
                "id": "t5",
                "dispatch_log": [
                    {
                        "agent": "jules",
                        "status": "dispatched",
                        "session_id": "jules://session/5",
                        "timestamp": stamp(5),
                    },
                    {
                        "agent": "jules",
                        "status": "dispatched",
                        "session_id": "jules://session/5",
                        "timestamp": stamp(5),
                    },
                    {
                        "agent": "jules",
                        "status": "dispatched",
                        "session_id": "jules://session/old",
                        "timestamp": stamp(30),
                    },
                ],
            },
        ]
    }
    (tmp_path / "tasks.yaml").write_text(yaml.safe_dump(board))
    plane = _plane(
        evidence={"kind": "board-dispatch-receipts", "locator": "tasks.yaml"},
        allotment={"runs": 100, "window": "rolling-24h", "concurrency": 15, "source": "t", "entitlement": "unverified"},
        fill_policy="floor",
        floor=25,
    )
    observed, detail = UTIL.read_board_dispatch_receipts("jules", plane, [], TODAY, tmp_path)
    assert observed == 3, detail
    assert "3 confirmed jules launches" in detail and "4 pre-launch claim/guard rows not counted" in detail
    assert UTIL.is_confirmed_launch({"status": "dispatched", "session_id": "x"})
    assert not UTIL.is_confirmed_launch({"status": "dispatched", "session_id": "serial-reserve"})
    assert not UTIL.is_confirmed_launch({"status": "done", "session_id": "x"})


def test_voice_reader_scores_stamps_against_their_cadence_window_not_midnight(tmp_path):
    """A cadence-48 sensor stamped at 23:59 is not missing at 00:01: a stamp is current while younger than
    2 × its worst-case cadence window (the beat-sensors canary bound), whatever UTC day it was written on."""
    import os
    import time

    voice = tmp_path / "logs" / ".voice"
    voice.mkdir(parents=True)
    now = time.time()

    def job(sid, beats):
        return S.Job(
            id=f"beat/{sid}",
            plane="limen-beat",
            crons=[],
            tz="UTC",
            enabled=True,
            derived=True,
            source="s",
            cadence_hours=S.beats_to_hours(beats, 1800),
            cadence_beats=beats,
            extra={"loop_max_seconds": 1800},
        )

    jobs = [job("daily", 48), job("four-beat", 4), job("twelve-beat", 12), job("two-day", 96)]
    for sid, age_hours in (("daily", 30), ("four-beat", 6), ("twelve-beat", 0)):
        p = voice / sid
        p.write_text("")
        os.utime(p, (now - age_hours * 3600, now - age_hours * 3600))
    # daily: 30h old, bound 48h → current (a midnight cutoff would have faulted it); four-beat: 6h old,
    # bound 4h → late; twelve-beat: fresh → current; two-day (96 beats = 48h) is not in the daily set.
    plane = _plane(evidence={"kind": "voice-stamps", "locator": "logs/.voice"})
    observed, detail = UTIL.read_voice_stamps("limen-beat", plane, jobs, TODAY, tmp_path)
    assert (
        observed == 2
        and detail.startswith("2/3 ")
        and "four-beat (6h)" in detail
        and "daily" not in detail.split("late:")[1]
    )
    assert UTIL.declared_for(plane, jobs, TODAY, NOW) == 3
    assert UTIL._stamp_bound_seconds(job("daily", 48)) == 48 * 1800 * 2


def test_readbacks_lever_predicate_requires_all_four_ui_only_planes():
    """L-SCHED-READBACKS names four UI-only schedulers; its predicate must not discharge on three."""
    import shlex

    levers = json.loads((ROOT / "his-hand-levers.json").read_text())

    def walk(o):
        if isinstance(o, dict):
            if o.get("id") == "L-SCHED-READBACKS":
                yield o
            for v in o.values():
                yield from walk(v)
        elif isinstance(o, list):
            for i in o:
                yield from walk(i)

    lever = next(walk(levers))
    predicate = json.dumps(lever, ensure_ascii=False)
    m = re.search(r"schedule-utilization\.py --json \| (python3 -c .*?)(?<!\\\\)\"(?=[,}])", predicate)
    assert m, "predicate not found"
    argv = shlex.split(json.loads('"' + m.group(1) + '"'))
    four = ["chatgpt-scheduled-tasks", "grok-automations", "gemini-scheduled-actions", "jules-native-scheduled-tasks"]

    def run(verdicts):
        report = {"planes": [{"plane": p, "verdict": v} for p, v in verdicts.items()]}
        return subprocess.run(argv, input=json.dumps(report), capture_output=True, text=True, check=False).returncode

    assert run({p: "full" for p in four}) == 0
    assert run({p: "full" for p in four[:3]}) == 1  # three measured, Jules-native missing from the report
    assert run({**{p: "full" for p in four[:3]}, "jules-native-scheduled-tasks": "unmeasured"}) == 1
    assert run({**{p: "full" for p in four}, "gemini-scheduled-actions": "unmeasured"}) == 1
    # the registry carries the fourth plane, unmeasured by construction until the readback lands
    planes = S.load_registry(ROOT)["planes"]
    assert planes["jules-native-scheduled-tasks"]["evidence"]["kind"] == "none"


# ── census-derived fleet planes (2026-10-24): rows by fact, ceilings, redaction, not-this-host ─────


def _census_plane(visibility: str | None, *, carrier: str = "gh-workflow", **over) -> dict:
    src = {
        "kind": "census",
        "locator": "logs/schedule-census.json",
        "carrier": carrier,
        "scope": "residual" if carrier == "gh-workflow" else "all",
    }
    if visibility:
        src["visibility"] = visibility
    base = _plane(
        owner="fleet",
        jobs_source=src,
        evidence={"kind": "census-receipt", "locator": "logs/schedule-census.json"}
        if carrier == "gh-workflow"
        else {"kind": "launchctl", "locator": "launchctl list"},
        declared_on="2026-10-24",
    )
    if carrier == "launchd":
        base.update(provider="apple", surface="launchd")
    base.update(over)
    return base


def _wf(
    path: str,
    crons: list[str],
    state: str = "active",
    name: str | None = None,
    last_at: str | None = None,
    conclusion: str = "success",
    fires_per_day: float = 1.0,
) -> dict:
    return {
        "path": path,
        "crons": crons,
        "state": state,
        "name": name or Path(path).stem,
        "last_at": last_at,
        "conclusion": conclusion,
        "fires_per_day": fires_per_day,
    }


def _repo(
    repo: str,
    *,
    private: bool,
    archived: bool = False,
    partial: bool = False,
    workflows: list[dict] | None = None,
    launchd: list[dict] | None = None,
) -> dict:
    decls, by_workflow = [], {}
    for w in workflows or []:
        decls.append(
            {
                "kind": "gh-workflow",
                "path": w["path"],
                "crons": w["crons"],
                "state": w["state"],
                "name": w["name"],
                "fires_per_day": w["fires_per_day"],
            }
        )
        if w["last_at"]:
            by_workflow[w["name"]] = {
                "last_at": w["last_at"],
                "last_conclusion": w["conclusion"],
                "runs_on_page": 1,
                "failed_on_page": 0,
            }
    for ld in launchd or []:
        decls.append({"kind": "launchd", **ld})
    return {
        "repo": repo,
        "reach": "ok",
        "private": private,
        "archived": archived,
        "partial": partial,
        "declarations": decls,
        "fired": {"total_scheduled_runs": len(by_workflow), "by_workflow": by_workflow, "listing_capped": False},
        "channels": {},
    }


def _receipt(repos: list[dict], generated_at: str = "2026-10-23T00:00:00+00:00", **denominators) -> dict:
    d = {
        "universe_count": len(repos),
        "scanned": len(repos),
        "unreachable": 0,
        "unscanned_by_budget": 0,
        "internal_errors": 0,
        "scanned_partial": sum(1 for r in repos if r.get("partial")),
    }
    d.update(denominators)
    return {"schema": S.CENSUS_SCHEMA, "generated_at": generated_at, "denominators": d, "repos": repos}


def write_fleet_root(
    root: Path,
    planes: dict,
    jobs: list | None = None,
    receipt: dict | None = None,
    *,
    baseline: list[str] | None = None,
    ignore: bool = True,
) -> None:
    """Registry + the workflows plane's own cron file (check B needs the locator to exist) + the census receipt."""
    write_workflow(root, "own", ["17 9 * * *"])
    write_registry(root, planes, jobs or [], baseline=baseline)
    if receipt is not None:
        write_receipt(root, receipt, ignore=ignore)


def write_receipt(root: Path, receipt: dict, *, ignore: bool = True) -> Path:
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    if ignore:
        (logs / ".gitignore").write_text("*\n!.gitignore\n")
    path = logs / "schedule-census.json"
    path.write_text(json.dumps(receipt))
    return path


SECRET = "o/secret-thing"  # a private repository the receipt lists and no committed line may name
FLEET_PLANES = {
    "github-actions-limen": _plane(
        jobs_source={"kind": "workflows", "locator": ".github/workflows"},
        evidence={"kind": "gh-actions-runs", "locator": "o/limen"},
    ),
    "github-actions-fleet-private": _census_plane(
        "private",
        ceilings={"active": 3, "on-the-hour": 1, "shared-minute": 2},
        declared_off=[
            {"match": {"archived": True}, "since": "x", "reason": "archiving is the off-switch"},
            {
                "match": {"archived": False, "state": ["disabled_manually", "disabled_inactivity"]},
                "ceiling": {"disabled_manually": 1, "disabled_inactivity": 0},
                "since": "x",
                "reason": "owned as a count",
            },
        ],
    ),
    "github-actions-fleet-public": _census_plane(
        "public", ceilings={"active": 1, "on-the-hour": 0, "shared-minute": 0}
    ),
    "launchd-host": _census_plane(None, carrier="launchd", ceilings={"active": 2}),
}
FLEET_RECEIPT = _receipt(
    [
        _repo(
            "o/limen", private=False, workflows=[_wf(".github/workflows/own.yml", ["0 9 * * *"])]
        ),  # covered by the workflows plane → never residual
        _repo(
            SECRET,
            private=True,
            workflows=[
                _wf(
                    ".github/workflows/a.yml", ["17 9 * * *"], last_at="2026-10-22T09:17:00Z"
                ),  # succeeded 1d before the receipt
                _wf(
                    ".github/workflows/b.yml", ["17 10 * * *"], last_at="2026-10-01T10:17:00Z"
                ),  # too old for a daily job
                _wf(
                    ".github/workflows/c.yml", ["0 3 * * 1"], fires_per_day=0.143, last_at="2026-10-20T03:00:00Z"
                ),  # weekly, on the hour, alive
                _wf(".github/workflows/off.yml", ["23 4 * * *"], state="disabled_manually"),
            ],
            launchd=[{"path": "launchd/com.x.beat.plist", "interval_seconds": 60, "label": "com.x.beat"}],
        ),
        _repo(
            "o/archived-priv", private=True, archived=True, workflows=[_wf(".github/workflows/z.yml", ["0 1 * * *"])]
        ),
        _repo(
            "o/public-thing",
            private=False,
            workflows=[_wf(".github/workflows/p.yml", ["36 5 * * *"], last_at="2026-10-22T05:36:00Z")],
            launchd=[
                {"path": "x/com.x.beat.plist", "interval_seconds": 60, "label": "com.x.beat"},
                {"path": "y/com.y.tend.plist", "calendar": [{"Hour": 7, "Minute": 0}]},
            ],
        ),
    ]
)


def test_census_rows_derive_by_fact_and_partition_by_visibility(tmp_path):
    write_registry(tmp_path, FLEET_PLANES, [])
    write_receipt(tmp_path, FLEET_RECEIPT)
    registry = S.load_registry(tmp_path)
    assert S.specific_plane_repos(registry) == {"o/limen"}
    assert S.residual_planes(registry) == {
        "private": "github-actions-fleet-private",
        "public": "github-actions-fleet-public",
    }
    jobs = S.derived_jobs(tmp_path, registry)
    private = [j for j in jobs if j.plane == "github-actions-fleet-private"]
    public = [j for j in jobs if j.plane == "github-actions-fleet-public"]
    launchd = [j for j in jobs if j.plane == "launchd-host"]
    assert sorted(j.id for j in private) == [
        "fleet/o/archived-priv/z",
        f"fleet/{SECRET}/a",
        f"fleet/{SECRET}/b",
        f"fleet/{SECRET}/c",
        f"fleet/{SECRET}/off",
    ]
    assert [j.id for j in public] == ["fleet/o/public-thing/p"]  # o/limen is covered, never residual
    assert {j.id: j.enabled for j in private} == {
        f"fleet/{SECRET}/a": True,
        f"fleet/{SECRET}/b": True,
        f"fleet/{SECRET}/c": True,
        f"fleet/{SECRET}/off": False,
        "fleet/o/archived-priv/z": False,
    }
    assert S.census_plane_counts(private) == {
        "active": 3,
        "on-the-hour": 1,
        "shared-minute": 2,
    }  # a + b share :17 in one repo
    per_rule, undeclared, unverified = S.census_off_counts(FLEET_PLANES["github-actions-fleet-private"], private)
    assert per_rule == [{"active": 1, "archived": 1}, {"disabled_manually": 1}] and undeclared == [] and unverified == 0
    # launchd: one job per Label, deduplicated across repositories; the stem is the fallback Label
    assert sorted(j.id for j in launchd) == ["launchd/com.x.beat", "launchd/com.y.tend"]
    beat = next(j for j in launchd if j.id == "launchd/com.x.beat")
    assert sorted(beat.extra["repos"]) == ["o/public-thing", SECRET] and beat.extra["private"] is True
    # the ids carry the private name only in memory: nothing in `source` does
    assert all(SECRET not in j.source for j in jobs)


def test_check_schedules_holds_census_ceilings_and_off_rules(tmp_path):
    write_fleet_root(tmp_path, FLEET_PLANES, receipt=FLEET_RECEIPT)
    run = run_check(tmp_path)
    assert run.returncode == 0, run.stdout
    assert "census ceilings" in run.stdout and SECRET not in run.stdout
    # growth above a ceiling is red; slack below it is an advisory naming the number to lower to
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private"]["ceilings"] = {"active": 2, "on-the-hour": 1, "shared-minute": 5}
    write_registry(tmp_path, planes, [])
    run = run_check(tmp_path)
    assert run.returncode == 1
    assert "[A] plane github-actions-fleet-private: active is 3, above its ceiling 2" in run.stdout
    assert "shared-minute is 2, below its ceiling 5 — lower ceilings.shared-minute to 2" in run.stdout
    assert SECRET not in run.stdout
    # an off-state row no match rule owns, and a declared_off ceiling exceeded, are both red
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private"]["declared_off"] = [
        {"match": {"archived": True}, "since": "x", "reason": "r"}
    ]
    write_registry(tmp_path, planes, [])
    run = run_check(tmp_path)
    assert (
        run.returncode == 1
        and "1 off-state workflow(s) no declared_off match owns — {'disabled_manually': 1}" in run.stdout
    )
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private"]["declared_off"][1]["ceiling"] = {
        "disabled_manually": 0,
        "disabled_inactivity": 0,
    }
    write_registry(tmp_path, planes, [])
    run = run_check(tmp_path)
    assert (
        run.returncode == 1
        and "declared_off[1] counts 1 disabled_manually workflow(s), above its ceiling 0" in run.stdout
    )


def test_census_schema_names_its_failures(tmp_path):
    planes = {
        "github-actions-limen": _plane(
            jobs_source={"kind": "workflows", "locator": ".github/workflows"}, ceilings={"active": 1}
        ),
        "fleet-a": _census_plane(
            "private",
            ceilings={"active": -1, "bogus": 2},
            declared_off=[
                {"file": "x.yml", "since": "x", "reason": "r"},
                {"match": {"state": ["active"]}, "ceiling": {"disabled_manually": 1}, "since": "x", "reason": "r"},
                {"match": {"archived": False}, "since": "x", "reason": "r"},
            ],
        ),
        "fleet-b": _census_plane(None, carrier="cronjob"),
    }
    write_registry(tmp_path, planes, [])
    run = run_check(tmp_path)
    assert run.returncode == 1
    out = run.stdout
    assert "plane github-actions-limen: `ceilings` belongs to census planes only" in out
    assert "ceilings.active must be an int ≥ 0" in out and "ceilings key 'bogus'" in out
    assert "declared_off[0]: a census plane declares off-switches by FACT" in out
    assert (
        "match.state ['active'] not in" in out
        and "ceiling key 'disabled_manually' is not one of this row's matched states" in out
    )
    assert "declared_off[2]: a match must name off states or select `archived: true`" in out
    assert "jobs_source.carrier='cronjob'" in out
    # the residual partition: a private half alone leaves every public cron owned by nobody
    write_registry(
        tmp_path,
        {
            "github-actions-limen": _plane(jobs_source={"kind": "workflows", "locator": ".github/workflows"}),
            "fleet-a": _census_plane("private"),
        },
        [],
    )
    run = run_check(tmp_path)
    assert (
        "residual gh-workflow planes cover ['private'] only — a ['public'] cron would be owned by nobody" in run.stdout
    )
    # two owners for one fact, or a whole-remainder plane beside a split one, is overlap
    write_registry(tmp_path, {"fleet-a": _census_plane("private"), "fleet-b": _census_plane("private")}, [])
    assert "both derive the residual gh-workflow fleet for visibility 'private'" in run_check(tmp_path).stdout
    write_registry(
        tmp_path,
        {"fleet-a": _census_plane(None), "fleet-b": _census_plane("private"), "fleet-c": _census_plane("public")},
        [],
    )
    assert (
        "derives the whole residual fleet while ['private', 'public'] split it by visibility — overlap"
        in run_check(tmp_path).stdout
    )


def test_declared_off_file_that_no_longer_exists_has_rotted(tmp_path):
    write_workflow(tmp_path, "report", ["17 9 * * *"])
    planes = {
        "github-actions-limen": _plane(
            jobs_source={"kind": "workflows", "locator": ".github/workflows"},
            declared_off=[{"file": "gone.yml", "since": "x", "reason": "parked"}],
        )
    }
    write_registry(tmp_path, planes, [])
    run = run_check(tmp_path)
    assert (
        run.returncode == 1
        and "declared_off names gone.yml but .github/workflows/gone.yml no longer exists — delete the row" in run.stdout
    )


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_census_locator_must_be_gitignored(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    write_fleet_root(repo, FLEET_PLANES, receipt=FLEET_RECEIPT, ignore=False)
    _git(repo, "init", "-q")
    run = run_check(repo)
    assert run.returncode == 1
    assert (
        "[B] plane github-actions-fleet-private: census locator logs/schedule-census.json is not git-ignored"
        in run.stdout
    )
    (repo / "logs" / ".gitignore").write_text("*\n!.gitignore\n")
    assert run_check(repo).returncode == 0
    # no repository at all (a sibling directory, outside the one above): unverifiable here, not drift
    other = tmp_path / "plain"
    other.mkdir()
    write_fleet_root(other, FLEET_PLANES, receipt=FLEET_RECEIPT, ignore=False)
    run = run_check(other, env={"GIT_CEILING_DIRECTORIES": str(tmp_path)})
    assert run.returncode == 0 and "cannot ask git whether logs/schedule-census.json is ignored" in run.stdout
    # the real leak: a receipt that is matched by .gitignore but TRACKED anyway (git check-ignore says not ignored)
    (repo / "logs" / ".gitignore").write_text("*\n!.gitignore\n")
    _git(repo, "add", "-f", "logs/schedule-census.json")
    run = run_check(repo)
    assert run.returncode == 1 and "is not git-ignored" in run.stdout


def test_redaction_fails_a_private_slug_and_exempts_disclosed_tokens(tmp_path):
    planes = json.loads(json.dumps(FLEET_PLANES))
    # a projected plane legitimately names its owner repository — even though the receipt lists it as private
    planes["github-actions-ops-like"] = _plane(
        authority={"owner_repo": "o/ops-like", "upstream_state": "proposed", "note": "mirror"},
        evidence={"kind": "bookend-tsv", "locator": "o/ops-like:bookends"},
    )
    jobs = [
        _job(
            "ops-like/report",
            "github-actions-ops-like",
            "36 13 * * *",
            source_of_truth="o/ops-like:.github/workflows/report.yml",
        )
    ]
    receipt = json.loads(json.dumps(FLEET_RECEIPT))
    receipt["repos"].append(
        _repo("o/ops-like", private=True, workflows=[_wf(".github/workflows/report.yml", ["36 13 * * *"])])
    )
    write_fleet_root(tmp_path, planes, jobs, receipt)
    run = run_check(tmp_path)
    assert run.returncode == 0, run.stdout
    assert "[I]" not in run.stdout.replace("[I] no census", "")
    # a private slug planted in a plane note fails H by file:line, and the message withholds the token
    planes["github-actions-fleet-private"]["note"] = f"growth came from {SECRET} last week"
    write_registry(tmp_path, planes, jobs)
    run = run_check(tmp_path)
    assert run.returncode == 1
    line = next(ln for ln in run.stdout.splitlines() if "[I]" in ln and "names a private repository" in ln)
    assert "institutio/governance/schedules.yaml:" in line and SECRET not in line and "secret-thing" not in line
    # a compound bare name in the baseline fails too; a disclosed owner repository's bare name does not
    planes["github-actions-fleet-private"].pop("note")
    write_registry(tmp_path, planes, jobs, baseline=["# ops-like keeps :36", "# secret-thing moved off the hour"])
    run = run_check(tmp_path)
    assert run.returncode == 1
    assert (
        "schedule-stagger-baseline.txt:3 names a private repository" in run.stdout
    )  # line 1 is the header, 2 the disclosed owner name
    assert "schedule-stagger-baseline.txt:2 names" not in run.stdout


def test_redaction_catches_sentence_end_git_suffix_and_case_and_exempts_exactly_r1(tmp_path):
    base_planes = json.loads(json.dumps(FLEET_PLANES))
    write_fleet_root(tmp_path, base_planes, receipt=FLEET_RECEIPT)
    assert run_check(tmp_path).returncode == 0
    for spelling in (f"see {SECRET}.", f"clone {SECRET}.git first", SECRET.upper(), "the Secret-Thing workflows"):
        planes = json.loads(json.dumps(FLEET_PLANES))
        planes["github-actions-fleet-private"]["note"] = spelling
        write_registry(tmp_path, planes, [])
        run = run_check(tmp_path)
        assert run.returncode == 1 and "names a private repository" in run.stdout, spelling
        assert "secret-thing" not in run.stdout.lower().replace("secret-thing", "") or SECRET not in run.stdout
    # a different token that merely starts with the name is not the name
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private"]["note"] = "secret-thing.yml is a workflow file name, secret-thinger a word"
    write_registry(tmp_path, planes, [])
    assert run_check(tmp_path).returncode == 0
    # R1 exactly: a source_of_truth or an evidence locator on a non-authority plane does NOT exempt the name
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["limen-beat-like"] = _plane(
        provider="limen", surface="launchd", evidence={"kind": "gh-actions-runs", "locator": SECRET}
    )
    write_registry(
        tmp_path, planes, [_job("beat/x", "limen-beat-like", "11 7 * * *", source_of_truth=f"{SECRET}:a.yml")]
    )
    run = run_check(tmp_path)
    assert run.returncode == 1 and run.stdout.count("names a private repository") >= 2
    assert SECRET not in S.disclosed_repo_tokens(S.load_registry(tmp_path))


def test_incomplete_or_stale_receipt_is_unmeasured_in_the_gate_but_growth_still_fails(tmp_path, monkeypatch):
    write_fleet_root(
        tmp_path, FLEET_PLANES, receipt=_receipt(FLEET_RECEIPT["repos"], universe_count=40, unreachable=30)
    )
    run = run_check(tmp_path)
    assert run.returncode == 0, run.stdout
    assert (
        "census receipt is incomplete" in run.stdout
        and "lower ceilings" not in run.stdout
        and "✗ [B]" not in run.stdout
    )
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private"]["ceilings"]["active"] = 1  # 3 > 1 on an undercount is still growth
    write_registry(tmp_path, planes, [])
    run = run_check(tmp_path)
    assert run.returncode == 1 and "active is 3, above its ceiling 1" in run.stdout
    # stale: compared, but never "lower to N"
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private"]["ceilings"]["active"] = 9
    write_registry(tmp_path, planes, [])
    write_receipt(tmp_path, _receipt(FLEET_RECEIPT["repos"], generated_at="2026-09-01T00:00:00+00:00"))
    run = run_check(tmp_path)
    assert (
        run.returncode == 0
        and "receipt_stale 1" in run.stdout
        and "do not lower" in run.stdout
        and "lower ceilings.active to 3" not in run.stdout
    )


def test_slack_advice_is_withheld_when_the_floor_is_unmeasured(tmp_path):
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private"]["ceilings"]["shared-minute"] = 4
    receipt = _receipt(
        FLEET_RECEIPT["repos"], universe_count=5, unreachable=1
    )  # 20% unread: still complete, but not a floor
    write_fleet_root(tmp_path, planes, receipt=receipt)
    run = run_check(tmp_path)
    assert run.returncode == 0
    assert "shared-minute is 2, below its ceiling 4 — floor unmeasured (unreachable 1) — do not lower" in run.stdout
    report, by = _fleet_eval(tmp_path)
    priv = by["github-actions-fleet-private"]
    assert (
        priv["verdict"] == "full"
        and priv["readback_overdue"] is False
        and "floor unmeasured (unreachable 1) — do not lower" in priv["detail"]
    )
    assert "github-actions-fleet-private" not in report["stale_readback"]
    # a partial row in the plane has the same effect
    receipt = json.loads(json.dumps(FLEET_RECEIPT))
    receipt["repos"][1]["partial"] = True
    write_receipt(tmp_path, receipt)
    run = run_check(tmp_path)
    assert "floor unmeasured (partial_rows 4" in run.stdout and "lower ceilings.shared-minute" not in run.stdout


def test_zero_rows_from_a_complete_receipt_is_advisory_and_malformed_caps_do_not_crash(tmp_path):
    receipt = _receipt(
        [r for r in FLEET_RECEIPT["repos"] if r["private"] or r["repo"] == "o/limen"]
    )  # no public residual rows
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-public"]["ceilings"] = {"active": 0, "on-the-hour": 0, "shared-minute": 0}
    write_fleet_root(tmp_path, planes, receipt=receipt)
    run = run_check(tmp_path)
    assert run.returncode == 0, run.stdout
    assert "plane github-actions-fleet-public: a complete census receipt derived zero rows" in run.stdout
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private"]["declared_off"][1]["ceiling"] = {
        "disabled_manually": "17",
        "disabled_inactivity": 0,
    }
    write_registry(tmp_path, planes, [])
    run = run_check(tmp_path)
    assert (
        run.returncode == 1
        and "ceiling.disabled_manually must be an int ≥ 0" in run.stdout
        and "Traceback" not in run.stderr
    )
    planes["github-actions-fleet-private"]["declared_off"][1]["ceiling"] = [17]
    write_registry(tmp_path, planes, [])
    run = run_check(tmp_path)
    assert run.returncode == 1 and "`ceiling` must be a mapping" in run.stdout and "Traceback" not in run.stderr


def test_census_plane_locators_must_agree_and_a_workflows_plane_must_name_its_repo(tmp_path):
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private"]["evidence"] = {"kind": "census-receipt", "locator": "logs/other.json"}
    planes["github-actions-limen"]["evidence"] = {"kind": "none", "locator": None}
    write_fleet_root(tmp_path, planes, receipt=FLEET_RECEIPT)
    run = run_check(tmp_path)
    assert run.returncode == 1
    assert (
        "evidence.locator 'logs/other.json' differs from jobs_source.locator 'logs/schedule-census.json'" in run.stdout
    )
    assert "plane github-actions-limen: a workflows plane must name its own repository" in run.stdout
    # without census planes the workflows plane may keep evidence none (unit fixtures do)
    write_registry(tmp_path, {"github-actions-limen": planes["github-actions-limen"]}, [])
    assert run_check(tmp_path).returncode == 0


def test_scope_all_and_a_lone_residual_plane_and_a_str_state(tmp_path):
    planes = {
        "github-actions-limen": FLEET_PLANES["github-actions-limen"],
        "fleet-all": _census_plane(None, ceilings={"active": 5}),
    }
    planes["fleet-all"]["jobs_source"]["scope"] = "all"
    planes["fleet-all"]["declared_off"] = [
        {"match": {"state": "disabled_manually"}, "since": "x", "reason": "str state"},
        {"match": {"archived": True}, "since": "x", "reason": "r"},
    ]
    write_fleet_root(tmp_path, planes, receipt=FLEET_RECEIPT)
    registry = S.load_registry(tmp_path)
    jobs = [j for j in S.derived_jobs(tmp_path, registry) if j.plane == "fleet-all"]
    assert "fleet/o/limen/own" in {j.id for j in jobs}  # scope all: the covered repository is in too
    assert S.census_plane_counts(jobs)["active"] == 5
    per_rule, undeclared, _ = S.census_off_counts(planes["fleet-all"], jobs)
    assert per_rule[0] == {"disabled_manually": 1} and undeclared == []
    assert run_check(tmp_path).returncode == 0
    # a lone residual plane with no visibility owns both halves
    planes["fleet-all"]["jobs_source"]["scope"] = "residual"
    write_registry(tmp_path, planes, [])
    registry = S.load_registry(tmp_path)
    ids = {j.id for j in S.derived_jobs(tmp_path, registry) if j.plane == "fleet-all"}
    assert "fleet/o/limen/own" not in ids and "fleet/o/public-thing/p" in ids and f"fleet/{SECRET}/a" in ids
    assert S.residual_planes(registry) == {None: "fleet-all"}
    planes["fleet-all"]["ceilings"] = {"active": 4}
    write_registry(tmp_path, planes, [])
    assert run_check(tmp_path).returncode == 0


def test_a_workflow_crowded_off_the_run_listing_is_unmeasurable_not_failed(tmp_path):
    receipt = json.loads(json.dumps(FLEET_RECEIPT))
    repo = receipt["repos"][1]
    repo["declarations"].append(
        {
            "kind": "gh-workflow",
            "path": ".github/workflows/weekly.yml",
            "crons": ["49 4 * * 1"],
            "state": "active",
            "name": "weekly",
            "fires_per_day": 0.143,
        }
    )
    repo["fired"]["oldest_seen"] = (
        "2026-10-22T20:00:00Z"  # the page spans 4h: a weekly job with no row is unmeasurable, not dark
    )
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private"]["ceilings"] = {"active": 4, "on-the-hour": 1, "shared-minute": 2}
    write_fleet_root(tmp_path, planes, receipt=receipt)
    _, by = _fleet_eval(tmp_path)
    priv = by["github-actions-fleet-private"]
    assert (priv["declared"], priv["observed"]) == (3, 2) and "1 crowded off the run listing unmeasured" in priv[
        "detail"
    ]
    # with a listing that reaches back past the window, the same silent workflow is simply not observed
    repo["fired"]["oldest_seen"] = "2026-09-01T00:00:00Z"
    write_receipt(tmp_path, receipt)
    _, by = _fleet_eval(tmp_path)
    priv = by["github-actions-fleet-private"]
    assert (priv["declared"], priv["observed"]) == (4, 2) and "0 crowded" in priv["detail"]
    # a receipt that read the deepest page too holds the repository's FIRST run in oldest_seen: that says nothing
    # about the summarized page, so without the page's own edge the silent workflow is unmeasurable, not scored
    repo["fired"]["oldest_page_read"] = True
    write_receipt(tmp_path, receipt)
    _, by = _fleet_eval(tmp_path)
    priv = by["github-actions-fleet-private"]
    assert (priv["declared"], priv["observed"]) == (3, 2) and "1 crowded" in priv["detail"]
    repo["fired"]["page_oldest_seen"] = "2026-10-22T20:00:00Z"  # the page spans 4h: still crowded off
    write_receipt(tmp_path, receipt)
    _, by = _fleet_eval(tmp_path)
    assert "1 crowded" in by["github-actions-fleet-private"]["detail"]
    repo["fired"]["page_oldest_seen"] = "2026-09-01T00:00:00Z"  # the page itself reaches back: measurable
    write_receipt(tmp_path, receipt)
    _, by = _fleet_eval(tmp_path)
    priv = by["github-actions-fleet-private"]
    assert (priv["declared"], priv["observed"]) == (4, 2) and "0 crowded" in priv["detail"]


def test_census_floor_is_unmeasured_from_a_targeted_census_or_a_universe_short_of_an_owner(tmp_path):
    assert S.census_floor_unmeasured({"denominators": {"universe_source": "repos-file:/u.txt", "scanned": 3}}, []) == {}
    assert S.census_floor_unmeasured({"denominators": {"universe_source": "explicit", "scanned": 1}}, []) == {
        "explicit_scope": 1
    }
    assert S.census_floor_unmeasured(
        {"denominators": {"universe_source": "gh-repo-list:o", "universe_unlisted_owners": 2}}, []
    ) == {"universe_unlisted_owners": 2}
    # through the gate: a complete one-repository census written to the default receipt never advises lowering
    receipt = json.loads(json.dumps(FLEET_RECEIPT))
    receipt["denominators"]["universe_source"] = "explicit"
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private"]["ceilings"]["active"] = 4
    write_fleet_root(tmp_path, planes, receipt=receipt)
    run = run_check(tmp_path)
    assert run.returncode == 0 and "floor unmeasured (explicit_scope 1) — do not lower" in run.stdout
    assert "lower ceilings.active" not in run.stdout
    _, by = _fleet_eval(tmp_path)
    priv = by["github-actions-fleet-private"]
    assert priv["readback_overdue"] is False and "explicit_scope 1" in priv["detail"]


def test_launchctl_reader_honours_the_receipt_state(tmp_path, monkeypatch):
    monkeypatch.setattr(UTIL.shutil, "which", lambda name: "/bin/launchctl" if name == "launchctl" else None)

    class Run:
        returncode = 0
        stdout = "PID\tStatus\tLabel\n412\t0\tcom.x.beat\n"

    monkeypatch.setattr(UTIL.subprocess, "run", lambda *a, **k: Run())
    write_fleet_root(tmp_path, FLEET_PLANES)  # no receipt at all
    report, by = _fleet_eval(tmp_path)
    assert by["launchd-host"]["verdict"] == "unmeasured" and by["launchd-host"]["not_this_host"] is True
    write_receipt(tmp_path, _receipt(FLEET_RECEIPT["repos"], generated_at="2026-10-01T00:00:00+00:00"))  # stale
    report, by = _fleet_eval(tmp_path)
    ld = by["launchd-host"]
    assert (
        ld["verdict"] == "unmeasured"
        and ld["not_this_host"] is False
        and "22d old" in ld["detail"]
        and "launchd-host" in report["stale_readback"]
    )
    (tmp_path / "logs" / "schedule-census.json").write_text(json.dumps({"schema": "other"}))
    report, by = _fleet_eval(tmp_path)
    assert (
        by["launchd-host"]["verdict"] == "unmeasured"
        and "wrong-schema" in by["launchd-host"]["detail"]
        and "launchd-host" in report["stale_readback"]
    )
    write_receipt(
        tmp_path, _receipt(FLEET_RECEIPT["repos"], universe_count=5, unreachable=1)
    )  # complete, but not a floor
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["launchd-host"]["ceilings"] = {"active": 3}
    write_registry(tmp_path, planes, [])
    _, by = _fleet_eval(tmp_path)
    assert (
        by["launchd-host"]["readback_overdue"] is False
        and "floor unmeasured (unreachable 1) — do not lower" in by["launchd-host"]["detail"]
    )


def test_ratchet_direction_fails_a_rising_ceiling_against_the_merge_base(tmp_path):
    write_fleet_root(tmp_path, FLEET_PLANES, receipt=FLEET_RECEIPT)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "institutio")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert run_check(tmp_path).returncode == 0
    # active may rise (deliberately); on-the-hour and shared-minute may not; nor may a declared_off ceiling
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private"]["ceilings"]["active"] = 4
    write_registry(tmp_path, planes, [])
    run = run_check(tmp_path)
    assert run.returncode == 0 and "[J]" not in run.stdout
    assert (
        "active is 3, below its ceiling 4 — lower ceilings.active to 3" in run.stdout
    )  # a complete receipt with no partial rows: the floor is measured
    planes["github-actions-fleet-private"]["ceilings"]["active"] = 3
    planes["github-actions-fleet-private"]["ceilings"]["on-the-hour"] = 2
    planes["github-actions-fleet-private"]["declared_off"][1]["ceiling"]["disabled_manually"] = 2
    write_registry(tmp_path, planes, [])
    run = run_check(tmp_path)
    assert run.returncode == 1
    assert "[J] plane github-actions-fleet-private: ceilings.on-the-hour rose 1 → 2" in run.stdout
    assert "declared_off ceiling disabled_manually rose 1 → 2" in run.stdout
    # (the receipt still says on-the-hour is 1, so A also reports the slack — a raised ceiling is wrong twice)
    assert "on-the-hour is 1, below its ceiling 2" in run.stdout
    # the other escapes: dropping a ratchet key, dropping a rule's ceiling, deleting a rule with a live ceiling, respelling the match
    planes = json.loads(json.dumps(FLEET_PLANES))
    del planes["github-actions-fleet-private"]["ceilings"]["shared-minute"]
    write_registry(tmp_path, planes, [])
    run = run_check(tmp_path)
    assert run.returncode == 1 and "ceilings.shared-minute was 2 at" in run.stdout and "is gone now" in run.stdout
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private"]["declared_off"][1]["match"]["state"] = [
        "disabled_inactivity",
        "disabled_manually",
    ]  # reordered
    del planes["github-actions-fleet-private"]["declared_off"][1]["ceiling"]["disabled_manually"]
    write_registry(tmp_path, planes, [])
    run = run_check(tmp_path)
    assert run.returncode == 1 and "declared_off ceiling disabled_manually was 1 at" in run.stdout
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private"]["declared_off"] = planes["github-actions-fleet-private"]["declared_off"][:1]
    write_registry(tmp_path, planes, [])
    run = run_check(tmp_path)
    assert (
        run.returncode == 1
        and "with ceilings {'disabled_manually': 1} at" in run.stdout
        and "is gone — a rule leaves only once its ceilings reach 0" in run.stdout
    )
    # continuity is by fact: a renamed plane deriving the same carrier/scope/visibility inherits the ratchet …
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private-v2"] = planes.pop("github-actions-fleet-private")
    planes["github-actions-fleet-private-v2"]["ceilings"]["on-the-hour"] = 2
    write_registry(tmp_path, planes, [])
    run = run_check(tmp_path)
    assert run.returncode == 1 and (
        "[J] plane github-actions-fleet-private-v2 (was github-actions-fleet-private): ceilings.on-the-hour rose 1 → 2"
        in run.stdout
    )
    # … and a plane may leave only once every ratchet ceiling it carried is 0
    planes = json.loads(json.dumps(FLEET_PLANES))
    del planes["github-actions-fleet-private"]
    write_registry(tmp_path, planes, [])
    run = run_check(tmp_path)
    assert "[J] plane github-actions-fleet-private at" in run.stdout and "is gone with live ceilings {" in run.stdout
    assert "'on-the-hour': 1" in run.stdout and "disabled_manually" in run.stdout
    planes = json.loads(json.dumps(FLEET_PLANES))
    del planes["launchd-host"]  # ceilings {active: N} only: active is not a ratchet, so the plane may leave
    write_registry(tmp_path, planes, [])
    assert "[J]" not in run_check(tmp_path).stdout
    # a plane the base never had is not ratcheted against anything
    _git(tmp_path, "rm", "-rq", "--cached", "institutio")
    write_registry(tmp_path, {"github-actions-limen": FLEET_PLANES["github-actions-limen"]}, [])
    _git(tmp_path, "add", "institutio")
    _git(tmp_path, "commit", "-q", "-m", "no census planes yet")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    write_registry(tmp_path, FLEET_PLANES, [])
    run = run_check(tmp_path)
    assert run.returncode == 0 and "[J]" not in run.stdout


def test_stagger_exempts_census_planes_and_slot_map_folds_them_to_counts(tmp_path):
    write_fleet_root(tmp_path, FLEET_PLANES, receipt=FLEET_RECEIPT)
    run = run_check(tmp_path)
    assert (
        run.returncode == 0 and "[E]" not in run.stdout
    )  # c.yml is on the hour and a+b share :17: ceilings, not stagger lines
    out = run_check(tmp_path, "--slot-map", "--day", "2026-10-26").stdout  # a Monday, so c.yml fires
    assert SECRET not in out and "fleet/" not in out
    rows = [ln for ln in out.splitlines() if "fleet workflow" in ln]
    assert any("| 09:17 | 1 fleet workflow (counts only) | github-actions-fleet-private |" in ln for ln in rows)
    assert any("| 03:00 | 1 fleet workflow (counts only) | github-actions-fleet-private |" in ln for ln in rows)
    assert not any("04:23" in ln for ln in rows)  # off.yml is disabled: an off-switch is not a slot
    assert any("| 05:36 | 1 fleet workflow (counts only) | github-actions-fleet-public |" in ln for ln in rows)
    # --compact never merges census slots: the same three rows survive, each on its own plane
    compact = run_check(tmp_path, "--slot-map", "--compact", "--day", "2026-10-26").stdout
    for needle in (
        "| 09:17 | 1 fleet workflow (counts only) | github-actions-fleet-private |",
        "| 03:00 | 1 fleet workflow (counts only) | github-actions-fleet-private |",
        "| 05:36 | 1 fleet workflow (counts only) | github-actions-fleet-public |",
    ):
        assert needle in compact, compact
    assert SECRET not in compact


def _fleet_eval(root: Path):
    report = UTIL.evaluate(root, TODAY, now=NOW)
    return report, {p["plane"]: p for p in report["planes"]}


def test_census_reader_scores_recent_successes_job_matched_and_overrides(tmp_path):
    write_registry(tmp_path, FLEET_PLANES, [])
    write_receipt(tmp_path, FLEET_RECEIPT)
    report, by = _fleet_eval(tmp_path)
    priv, pub = by["github-actions-fleet-private"], by["github-actions-fleet-public"]
    # a (1d-old success) and c (weekly, 3d-old success) are alive; b's last success is 22 days old for a daily job
    assert (priv["declared"], priv["observed"], priv["verdict"]) == (3, 2, "full")
    assert (pub["declared"], pub["observed"], pub["verdict"]) == (1, 1, "full")
    assert priv["allocation_gap"] is None  # job-matched counts are not a run unit
    assert (
        SECRET not in priv["detail"]
        and "secret-thing" not in priv["detail"]
        and "2/3 enabled residual workflows" in priv["detail"]
    )
    assert (
        "2 declared off by fact" in priv["detail"]
        and "counts active 3/3, on-the-hour 1/1, shared-minute 2/2" in priv["detail"]
    )  # off.yml + the archived z
    assert priv["readback_overdue"] is False and priv["not_this_host"] is False
    # a partial row and an ambiguous display-name join are unmeasured per job, not scored
    receipt = json.loads(json.dumps(FLEET_RECEIPT))
    receipt["repos"][1]["partial"] = True
    receipt["repos"].append(
        _repo(
            "o/twins",
            private=True,
            workflows=[
                _wf(".github/workflows/x.yml", ["11 7 * * *"], name="Same", last_at="2026-10-22T07:11:00Z"),
                _wf(".github/workflows/y.yml", ["49 7 * * *"], name="Same", last_at="2026-10-22T07:49:00Z"),
            ],
        )
    )
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private"]["ceilings"] = {"active": 5, "on-the-hour": 1, "shared-minute": 2}
    write_registry(tmp_path, planes, [])
    write_receipt(tmp_path, receipt)
    report, by = _fleet_eval(tmp_path)
    priv = by["github-actions-fleet-private"]
    # every enabled row is on the partial read or the ambiguous join: nothing measurable is unmeasured, not idle
    assert (priv["declared"], priv["observed"], priv["verdict"]) == (0, None, "unmeasured")
    assert (
        "3 on partially read rows, 2 ambiguous name join(s) and 0 crowded off the run listing unmeasured"
        in priv["detail"]
    )
    assert "github-actions-fleet-private" in report["stale_readback"]
    # overrides: undeclared-off > undeclared-growth > stagger-regressed
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private"]["declared_off"] = [
        {"match": {"archived": True}, "since": "x", "reason": "r"}
    ]
    write_registry(tmp_path, planes, [])
    write_receipt(tmp_path, FLEET_RECEIPT)
    _, by = _fleet_eval(tmp_path)
    assert (
        by["github-actions-fleet-private"]["verdict"] == "undeclared-off"
        and "UNDECLARED OFF: 1" in by["github-actions-fleet-private"]["detail"]
    )
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private"]["ceilings"]["active"] = 2
    write_registry(tmp_path, planes, [])
    _, by = _fleet_eval(tmp_path)
    assert (
        by["github-actions-fleet-private"]["verdict"] == "undeclared-growth"
        and "active 3>2" in by["github-actions-fleet-private"]["detail"]
    )
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private"]["ceilings"]["on-the-hour"] = 0
    write_registry(tmp_path, planes, [])
    report, by = _fleet_eval(tmp_path)
    assert by["github-actions-fleet-private"]["verdict"] == "stagger-regressed" and report["status"] == "fail"
    # slack: measured and green, but the ceiling must come down — readback_overdue, status stale-readback (exit 3), never red
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["github-actions-fleet-private"]["ceilings"]["shared-minute"] = 4
    write_registry(tmp_path, planes, [])
    report, by = _fleet_eval(tmp_path)
    priv = by["github-actions-fleet-private"]
    assert (
        priv["verdict"] == "full"
        and priv["readback_overdue"] is True
        and "lower ceilings.shared-minute to 2 (ceiling 4)" in priv["detail"]
    )
    assert "github-actions-fleet-private" in report["stale_readback"] and report["status"] == "stale-readback"
    assert UTIL.RED_VERDICTS >= {"undeclared-growth", "stagger-regressed", "undeclared-off"}


def test_census_receipt_states_stale_incomplete_and_wrong_schema(tmp_path, monkeypatch):
    write_fleet_root(tmp_path, FLEET_PLANES)
    # stale: older than LIMEN_SCHEDULE_CENSUS_MAX_AGE_DAYS → unmeasured + stale readback (the receipt exists; it is just old)
    write_receipt(tmp_path, _receipt(FLEET_RECEIPT["repos"], generated_at="2026-10-01T00:00:00+00:00"))
    report, by = _fleet_eval(tmp_path)
    priv = by["github-actions-fleet-private"]
    assert priv["verdict"] == "unmeasured" and priv["not_this_host"] is False and "22d old (> 8d)" in priv["detail"]
    assert "github-actions-fleet-private" in report["stale_readback"]
    assert priv["declared"] == 3  # rows still derive from a stale receipt; they are just not scored
    monkeypatch.setenv("LIMEN_SCHEDULE_CENSUS_MAX_AGE_DAYS", "30")
    _, by = _fleet_eval(tmp_path)
    assert by["github-actions-fleet-private"]["verdict"] == "full"
    monkeypatch.delenv("LIMEN_SCHEDULE_CENSUS_MAX_AGE_DAYS")
    # incomplete: more than a quarter unread → nothing concluded
    write_receipt(tmp_path, _receipt(FLEET_RECEIPT["repos"], universe_count=40, unreachable=30))
    _, by = _fleet_eval(tmp_path)
    assert (
        by["github-actions-fleet-private"]["verdict"] == "unmeasured"
        and "is incomplete (4/40 scanned, 30 unreachable" in by["github-actions-fleet-private"]["detail"]
    )
    # wrong schema: the locator points at something that is not the census — stale readback for the sensor, drift for the gate
    (tmp_path / "logs" / "schedule-census.json").write_text(json.dumps({"schema": "other", "repos": []}))
    report, by = _fleet_eval(tmp_path)
    assert (
        by["github-actions-fleet-private"]["verdict"] == "unmeasured"
        and "wrong-schema" in by["github-actions-fleet-private"]["detail"]
    )
    assert "github-actions-fleet-private" in report["stale_readback"]
    run = run_check(tmp_path)
    assert run.returncode == 1 and "is wrong-schema — not a limen.schedule_census.v1 receipt" in run.stdout


def test_census_planes_without_receipt_or_launchctl_are_not_this_host(tmp_path, monkeypatch):
    write_fleet_root(tmp_path, FLEET_PLANES)
    monkeypatch.setattr(UTIL.shutil, "which", lambda name: None)  # no gh, no launchctl
    report, by = _fleet_eval(tmp_path)
    for pid in ("github-actions-fleet-private", "github-actions-fleet-public", "launchd-host"):
        p = by[pid]
        assert p["verdict"] == "unmeasured" and p["not_this_host"] is True and p["declared"] == 0, p
        assert pid not in report["stale_readback"]
    # the limen workflows plane had a way to look (gh) and could not: THAT is a stale readback; the fleet planes are not
    assert report["stale_readback"] == ["github-actions-limen"] and report["status"] == "stale-readback"
    assert report["measured"] == "0/1"  # not-this-host planes are not measurable here
    # the gate: absent receipt is 'not this host', never drift
    run = run_check(tmp_path)
    assert run.returncode == 0 and "no census receipt at logs/schedule-census.json on this host" in run.stdout


def test_launchctl_reader_counts_loaded_labels_only(tmp_path, monkeypatch):
    write_registry(tmp_path, FLEET_PLANES, [])
    write_receipt(tmp_path, FLEET_RECEIPT)
    monkeypatch.setattr(UTIL.shutil, "which", lambda name: "/bin/launchctl" if name == "launchctl" else None)

    class Run:
        returncode = 0
        stdout = "PID\tStatus\tLabel\n412\t0\tcom.x.beat\n-\t78\tcom.y.tend\n-\t0\tcom.apple.other\n"

    monkeypatch.setattr(UTIL.subprocess, "run", lambda *a, **k: Run())
    report, by = _fleet_eval(tmp_path)
    ld = by["launchd-host"]
    assert (ld["declared"], ld["observed"], ld["verdict"]) == (2, 1, "full")  # 1/2 meets the 0.5 fill floor
    assert (
        "1/2 declared Labels loaded with last exit 0 (2 loaded at all; 3 jobs in launchctl list; receipt 0d old)"
        in ld["detail"]
    )
    assert ld["not_this_host"] is False and "com.x.beat" not in ld["detail"] and SECRET not in ld["detail"]
    Run.stdout = (
        "PID\tStatus\tLabel\n-\t78\tcom.x.beat\n-\t1\tcom.y.tend\n"  # both loaded, both failing: nothing observed
    )
    _, by = _fleet_eval(tmp_path)
    assert (by["launchd-host"]["observed"], by["launchd-host"]["verdict"]) == (0, "dark")
    # a Label above the ceiling is growth; fewer is slack
    planes = json.loads(json.dumps(FLEET_PLANES))
    planes["launchd-host"]["ceilings"] = {"active": 1}
    write_registry(tmp_path, planes, [])
    _, by = _fleet_eval(tmp_path)
    assert by["launchd-host"]["verdict"] == "undeclared-growth"
    planes["launchd-host"]["ceilings"] = {"active": 3}
    write_registry(tmp_path, planes, [])
    _, by = _fleet_eval(tmp_path)
    assert (
        by["launchd-host"]["readback_overdue"] is True and "lower ceilings.active to 2" in by["launchd-host"]["detail"]
    )


def test_shared_cadence_functions_match_the_census_vocabulary():
    cases = {
        "*/30 * * * *": (48.0, "sub-hourly"),
        "0 * * * *": (24.0, "hourly"),
        "0 */4 * * *": (6.0, "intraday"),
        "0 9 * * *": (1.0, "daily"),
        "0 9 * * 1": (0.143, "weekly"),
        "0 9 * * 1-5": (0.714, "weekdays"),
        "0 0 1 * *": (0.033, "monthly"),
    }
    for cron, expected in cases.items():
        parsed = S.parse_cron(cron)
        assert (S.cron_fires_per_day(parsed), S.cadence_label(parsed)) == expected, cron


def test_real_registry_owns_the_fleet_by_fact_and_names_no_private_repository():
    registry = S.load_registry(ROOT)
    planes = registry["planes"]
    assert S.residual_planes(registry) == {
        "private": "github-actions-fleet-private",
        "public": "github-actions-fleet-public",
    }
    assert S.specific_plane_repos(registry, "4444J99/limen") == {"4444J99/limen", "4444J99/ops", "4444J99/ops-witness"}
    for pid in ("github-actions-fleet-private", "github-actions-fleet-public", "launchd-host"):
        plane = planes[pid]
        assert S.is_census_plane(plane) and set(plane["ceilings"]) <= S.CEILING_KEYS
        for row in plane.get("declared_off") or []:
            assert "match" in row and "file" not in row  # by fact, never by name
    private = planes["github-actions-fleet-private"]
    assert private["ceilings"] == {"active": 77, "on-the-hour": 67, "shared-minute": 62}
    assert private["declared_off"][1]["ceiling"] == {"disabled_manually": 17, "disabled_inactivity": 1}
    assert planes["github-actions-fleet-public"]["ceilings"] == {"active": 41, "on-the-hour": 40, "shared-minute": 35}
    assert planes["launchd-host"]["ceilings"] == {"active": 15}
    # R1: the committed registry carries no repository slug beyond the disclosed projection tokens
    text = (ROOT / S.REGISTRY_REL).read_text()
    slugs = set(re.findall(r"\b4444J99/[\w.-]+", text))
    assert slugs <= {"4444J99/limen", "4444J99/ops", "4444J99/ops-witness"}, slugs
