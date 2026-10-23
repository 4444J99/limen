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
import subprocess
import sys
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
    assert UTIL.verdict_for(comments, declared=27, observed=1, fill_floor=0.5) == "full"


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
    assert plane["declared"] == 2 and plane["observed"] == 1 and plane["verdict"] == "underfilled"
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
