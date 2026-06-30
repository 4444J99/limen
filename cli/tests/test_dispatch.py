from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import limen.dispatch as D
from limen.capacity import PAID_AGENT_ORDER, capacity_census, format_capacity_census
from limen.dispatch import dispatch_parallel, dispatch_tasks, release_stale_tasks
from limen.doctor import qa_report, readiness_report, stale_tasks
from limen.io import load_limen_file
from limen.models import BudgetTrack, Task
from limen.status import print_status


def load_route_module():
    route_path = Path(__file__).resolve().parents[2] / "scripts" / "route.py"
    spec = importlib.util.spec_from_file_location("limen_route_test", route_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_board(path: Path, tasks: list[dict]) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "portal": {
                    "name": "Universal Task Intake",
                    "budget": {
                        "daily": 100,
                        "unit": "runs",
                        "per_agent": {"jules": 100, "codex": 2, "external": 2},
                        "track": {"date": "", "spent": 0, "per_agent": {}},
                    },
                },
                "tasks": tasks,
            },
            sort_keys=False,
        )
    )


def read_board(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_capacity_census_lists_every_paid_lane(tmp_path: Path, monkeypatch) -> None:
    for binary in ("codex", "claude", "opencode", "agy", "gemini", "jules", "ollama", "gh", "agent-dispatch"):
        path = tmp_path / binary
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("WARP_API_KEY", "test-key")
    monkeypatch.setenv("LIMEN_COPILOT_ENABLED", "1")
    # ollama's floor lane is reachable only once a model is pulled — set the pin so the
    # "everything configured" census sees it up (mirrors GEMINI_API_KEY/WARP_API_KEY above).
    monkeypatch.setenv("LIMEN_OLLAMA_MODEL", "test-model")

    tasks_path = tmp_path / "tasks.yaml"
    write_board(tasks_path, [])
    rows = capacity_census(load_limen_file(tasks_path))

    assert [row["agent"] for row in rows] == list(PAID_AGENT_ORDER)
    assert {row["agent"] for row in rows if row["reachable"]} == set(PAID_AGENT_ORDER)
    text = format_capacity_census(rows)
    assert "-- capacity census" in text
    assert "github_actions" in text


def test_route_distributes_local_work_and_reaches_extended_fleet(tmp_path: Path) -> None:
    """Ideal-form router (origin's local-first split + the extended-fleet graft): local-checkout
    work spreads across LOCAL lanes by budget+refresh-runway (no single-lane serialization), and a
    repo with NO local checkout but a GitHub issue still reaches the extended fleet (copilot/jules)
    instead of being stranded. Supersedes the old fan-everything-round-robin assertion — which routed
    local work to copilot/warp/oz the daemon can't dispatch (the 'don't strand' lesson origin learned)."""
    route = load_route_module()
    workdir = tmp_path / "work"
    checkout = workdir / "organvm" / "limen"
    (checkout / ".git").mkdir(parents=True)
    health = {agent: True for agent in PAID_AGENT_ORDER}
    budget = {a: 10 for a in ("codex", "claude", "agy", "opencode")}

    # Many local-checkout tasks must SPREAD across local lanes, never serialize onto one.
    tally: dict[str, int] = {}
    picks = []
    for i in range(8):
        task = {
            "id": f"LIMEN-{i:03}",
            "title": f"Task {i}",
            "repo": "organvm/limen",
            "status": "open",
            "budget_cost": 1,
            "urls": [f"https://github.com/organvm/limen/issues/{i}"],
        }
        vendor, _ = route.route_task(task, health, workdir, assigned=tally, budget=budget)
        tally[vendor] = tally.get(vendor, 0) + 1
        picks.append(vendor)
    assert set(picks) <= {"codex", "claude", "agy", "opencode"}, f"local work leaked to {set(picks)}"
    assert len(set(picks)) >= 2, f"work serialized onto {set(picks)}"

    # A repo with NO local checkout but a GitHub issue reaches the extended fleet, not 'unroutable'.
    remote = {
        "id": "REMOTE-1",
        "title": "Remote-only repo",
        "repo": "someorg/no-local-here",
        "status": "open",
        "budget_cost": 1,
        "urls": ["https://github.com/someorg/no-local-here/issues/9"],
    }
    vendor, reason = route.route_task(remote, health, workdir, assigned={}, budget=budget)
    assert vendor in ("copilot", "github_actions", "jules"), (vendor, reason)


def test_self_improve_weight_nudge_steers_local_split(monkeypatch) -> None:
    """The self-IMPROVE rung closing the loop: a learned down-weight makes _pick_local prefer the
    other lane even when budget+load+runway are otherwise tied. Default (no weights) keeps the
    stable name-order pick — so the nudge only bites when armed."""
    route = load_route_module()
    task = {"type": "code", "title": "neutral work", "context": ""}
    health = {"codex": True, "claude": True, "agy": False, "opencode": False}
    # codex has more budget headroom, so by load (assigned/budget) it's the lighter lane and wins.
    budget = {"codex": 20, "claude": 10}
    assigned = {"codex": 1, "claude": 1}  # load: codex 0.05 < claude 0.10

    # No learned weights -> lightest-load lane: codex (unchanged behavior).
    monkeypatch.setattr(route, "_learned_weights", lambda: {})
    assert route._pick_local(task, health, assigned, budget) == "codex"

    # codex down-weighted (0.25) -> effective load 0.05/0.25=0.20 > claude 0.10 -> claude wins.
    monkeypatch.setattr(route, "_learned_weights", lambda: {"codex": 0.25})
    assert route._pick_local(task, health, assigned, budget) == "claude"


def test_dispatch_dry_run_prints_capacity_census_and_copilot_command(tmp_path: Path, capsys) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-COPILOT",
                "title": "Use Copilot lane",
                "repo": "organvm/limen",
                "target_agent": "copilot",
                "priority": "high",
                "budget_cost": 1,
                "status": "open",
                "urls": ["https://github.com/organvm/limen/issues/12"],
                "created": "2026-06-20",
                "dispatch_log": [],
            }
        ],
    )

    dispatch_tasks(load_limen_file(tasks_path), tasks_path, agent="copilot", dry_run=True)

    output = capsys.readouterr().out
    assert "-- capacity census" in output
    assert "copilot" in output
    assert (
        "would: gh api graphql (fetch node IDs + replaceActorsForAssignable for copilot-swe-agent on organvm/limen#12)"
    ) in output


def test_dispatch_skips_needs_human_label(tmp_path: Path, capsys) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "HUMAN-GATE",
                "title": "Needs human",
                "repo": "organvm/limen",
                "target_agent": "external",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "labels": ["needs-human"],
                "created": "2026-06-20",
                "dispatch_log": [],
            }
        ],
    )

    dispatch_tasks(load_limen_file(tasks_path), tasks_path, agent="external", dry_run=True)

    output = capsys.readouterr().out
    assert "No open tasks for agent 'external'" in output
    assert "HUMAN-GATE" not in output


def test_dispatch_skips_open_task_with_prior_done_log(tmp_path: Path, capsys) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "REOPENED-DONE",
                "title": "Already completed",
                "repo": "organvm/limen",
                "target_agent": "codex",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-30",
                "dispatch_log": [
                    {
                        "timestamp": "2026-06-30T00:00:00+00:00",
                        "agent": "codex",
                        "session_id": "prior",
                        "status": "done",
                    }
                ],
            }
        ],
    )

    dispatch_tasks(load_limen_file(tasks_path), tasks_path, agent="codex", dry_run=True)

    output = capsys.readouterr().out
    assert "No open tasks for agent 'codex'" in output
    assert "REOPENED-DONE" not in output


def test_dispatch_parallel_skips_needs_human_label(tmp_path: Path, capsys) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "HUMAN-GATE",
                "title": "Needs human",
                "repo": "organvm/limen",
                "target_agent": "any",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "labels": ["needs-human"],
                "created": "2026-06-20",
                "dispatch_log": [],
            },
            {
                "id": "MACHINE-WORK",
                "title": "Machine work",
                "repo": "organvm/limen",
                "target_agent": "any",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-20",
                "dispatch_log": [],
            },
        ],
    )

    dispatch_parallel(load_limen_file(tasks_path), tasks_path, agents=["codex"], dry_run=True)

    output = capsys.readouterr().out
    assert "MACHINE-WORK" in output
    assert "HUMAN-GATE" not in output


def test_dispatch_parallel_debt_gate_skips_routine_generated_buildout(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        D,
        "worktree_debt_exceeded",
        lambda: (True, {"debt": 13, "total": 13, "by_reason": {}, "items": []}, 12),
    )
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "GEN-BUILDOUT",
                "title": "Generated build-out",
                "repo": "organvm/limen",
                "target_agent": "any",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "labels": ["typing", "generated", "build-out"],
                "created": "2026-06-20",
                "dispatch_log": [],
            },
            {
                "id": "RECOVERY",
                "title": "Recover lifecycle debt",
                "repo": "organvm/limen",
                "target_agent": "any",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "labels": ["lifecycle"],
                "created": "2026-06-20",
                "dispatch_log": [],
            },
        ],
    )

    dispatch_parallel(load_limen_file(tasks_path), tasks_path, agents=["codex"], dry_run=True)

    output = capsys.readouterr().out
    assert "Lifecycle debt gate" in output
    assert "RECOVERY" in output
    assert "GEN-BUILDOUT" not in output


def test_lane_run_env_keeps_lane_specific_isolation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("LIMEN_GEMINI_OAUTH", "1")
    for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY"):
        monkeypatch.setenv(key, "api-secret")

    gemini_env = D._lane_run_env("gemini")
    assert not any(key in gemini_env for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY"))

    agy_env = D._lane_run_env("agy")
    assert agy_env["PATH"].startswith(str(tmp_path / "scripts" / "agy-noop-shim") + os.pathsep)
    assert agy_env["BROWSER"] == "true"

    monkeypatch.setenv("ANTHROPIC_API_KEY", "interactive-key")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "keychain-token")
    monkeypatch.setenv("LIMEN_CLAUDE_AUTH_TOKEN", "fleet-token")
    claude_env = D._lane_run_env("claude")
    assert claude_env["ANTHROPIC_AUTH_TOKEN"] == "fleet-token"
    assert "ANTHROPIC_API_KEY" not in claude_env
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in claude_env


def test_run_isolated_agent_retries_transient_claude_auth_blip(tmp_path: Path, monkeypatch) -> None:
    calls: list[dict] = []

    def fake_run_capture(cmd, cwd=None, timeout=600, env=None):
        calls.append({"cmd": cmd, "cwd": cwd, "timeout": timeout, "env": env})
        if len(calls) == 1:
            return subprocess.CompletedProcess(cmd, 1, "", "Not logged in")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(D, "_run_capture", fake_run_capture)
    task = Task(id="AUTH-BLIP", title="retry", target_agent="claude", created=date(2026, 6, 27))

    assert D._run_isolated_agent("claude", task, tmp_path, ["claude"], 3) is True
    assert len(calls) == 2


def test_noop_result_stays_recoverable_not_cancelled() -> None:
    import datetime

    task = Task(
        id="NOOP",
        title="no-op attempt",
        target_agent="codex",
        status="open",
        created=date(2026, 6, 27),
        labels=[],
    )
    now = datetime.datetime.now(datetime.timezone.utc)

    D._apply_result(task, "codex", D._NOOP, now, BudgetTrack(date="2026-06-27"))

    assert task.status == "failed"
    assert "noop" in task.labels
    assert "cancelled" not in task.labels
    assert task.dispatch_log[-1].status == "failed"


def test_release_stale_dry_run_does_not_mutate(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-001",
                "title": "Stale Jules task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "dispatched",
                "created": "2026-06-01",
                "dispatch_log": [
                    {
                        "timestamp": "2026-06-01T00:00:00+00:00",
                        "agent": "jules",
                        "session_id": "test",
                        "status": "dispatched",
                    }
                ],
            }
        ],
    )
    before = tasks_path.read_text()

    release_stale_tasks(load_limen_file(tasks_path), tasks_path, hours=24, dry_run=True)

    assert tasks_path.read_text() == before


def test_release_stale_apply_reopens_task(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-002",
                "title": "Stale Jules task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "in_progress",
                "created": "2026-06-01",
                "dispatch_log": [],
            }
        ],
    )

    report = release_stale_tasks(load_limen_file(tasks_path), tasks_path, hours=24, dry_run=False)

    task = read_board(tasks_path)["tasks"][0]
    assert task["status"] == "open"
    assert task["dispatch_log"][-1]["status"] == "open"
    assert report["status"] == "applied"
    assert report["count"] == 1
    assert report["released"] == ["LIMEN-002"]
    assert report["restored_done"] == []


def test_release_stale_restores_prior_done_instead_of_reopening(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "DONE-REOPENED",
                "title": "Already done but active",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "in_progress",
                "created": "2026-06-01",
                "dispatch_log": [
                    {
                        "timestamp": "2026-06-01T00:00:00+00:00",
                        "agent": "jules",
                        "session_id": "prior",
                        "status": "done",
                    }
                ],
            }
        ],
    )

    report = release_stale_tasks(load_limen_file(tasks_path), tasks_path, hours=24, dry_run=False)

    task = read_board(tasks_path)["tasks"][0]
    assert task["status"] == "done"
    assert task["dispatch_log"][-1]["status"] == "done"
    assert report["released"] == []
    assert report["restored_done"] == ["DONE-REOPENED"]


def test_dispatch_limit_and_per_agent_budget(tmp_path: Path, monkeypatch) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    dispatch_bin = tmp_path / "agent-dispatch"
    dispatch_bin.write_text("#!/bin/sh\nexit 0\n")
    dispatch_bin.chmod(0o755)
    monkeypatch.setenv("LIMEN_DISPATCH_CMD", str(dispatch_bin))
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-003",
                "title": "Open external task one",
                "repo": "4444J99/limen",
                "target_agent": "external",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-03",
                "dispatch_log": [],
            },
            {
                "id": "LIMEN-004",
                "title": "Open external task two",
                "repo": "4444J99/limen",
                "target_agent": "external",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-03",
                "dispatch_log": [],
            },
            {
                "id": "LIMEN-005",
                "title": "Open external task three",
                "repo": "4444J99/limen",
                "target_agent": "external",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-03",
                "dispatch_log": [],
            },
        ],
    )

    dispatch_tasks(load_limen_file(tasks_path), tasks_path, agent="external", dry_run=False, limit=3)

    board = read_board(tasks_path)
    statuses = {task["id"]: task["status"] for task in board["tasks"]}
    assert statuses == {"LIMEN-003": "dispatched", "LIMEN-004": "dispatched", "LIMEN-005": "open"}
    assert board["portal"]["budget"]["track"]["per_agent"]["external"] == 2


def test_dispatch_skips_lane_marked_down_by_usage_meter(tmp_path: Path, monkeypatch) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    dispatch_bin = tmp_path / "agent-dispatch"
    dispatch_bin.write_text("#!/bin/sh\nexit 99\n")
    dispatch_bin.chmod(0o755)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_DISPATCH_CMD", str(dispatch_bin))
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "usage.json").write_text('{"vendors":{"claude":{"health":"rate-limited"}}}')
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-DOWN-CLAUDE",
                "title": "Should not dispatch",
                "repo": "4444J99/limen",
                "target_agent": "claude",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-19",
                "dispatch_log": [],
            }
        ],
    )

    dispatch_tasks(load_limen_file(tasks_path), tasks_path, agent="claude", dry_run=False, limit=1)

    board = read_board(tasks_path)
    assert board["tasks"][0]["status"] == "open"
    assert board["tasks"][0]["dispatch_log"] == []
    assert board["portal"]["budget"]["track"].get("per_agent", {}) == {}


def test_status_prints_creation_age_and_recorded_throughput(tmp_path: Path, capsys) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-AGE-001",
                "title": "Completed task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "done",
                "created": "2026-05-31",
                "dispatch_log": [
                    {
                        "timestamp": "2026-05-31T00:00:00+00:00",
                        "agent": "jules",
                        "session_id": "test",
                        "status": "dispatched",
                    },
                    {
                        "timestamp": "2026-05-31T01:00:00+00:00",
                        "agent": "jules",
                        "session_id": "test",
                        "status": "done",
                    },
                ],
            },
            {
                "id": "LIMEN-AGE-002",
                "title": "Active task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "dispatched",
                "created": "2026-06-01",
                "dispatch_log": [],
            },
        ],
    )

    print_status(load_limen_file(tasks_path))

    output = capsys.readouterr().out
    assert "Throughput: created 2026-05-31 ->" in output
    assert "capacity 100/day" in output
    assert "recorded: 2 log events, 1 starts, 1 finishes, 1 done, 1 not done" in output


def test_readiness_report_flags_stale_claims_and_next_actions(tmp_path: Path, monkeypatch) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    dispatch_bin = tmp_path / "jules"
    dispatch_bin.write_text("#!/bin/sh\nexit 0\n")
    dispatch_bin.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ.get('PATH', '')}")
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-006",
                "title": "Stale Jules task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "critical",
                "budget_cost": 1,
                "status": "dispatched",
                "created": "2026-06-01",
                "dispatch_log": [],
            },
            {
                "id": "LIMEN-007",
                "title": "Open Jules task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-03",
                "dispatch_log": [],
            },
        ],
    )
    limen = load_limen_file(tasks_path)

    report = readiness_report(limen, tasks_path, agent="jules")

    assert len(stale_tasks(limen, agent="jules")) == 1
    assert report["status"] == "degraded"
    assert report["counts"]["stale"] == 1
    assert "limen release-stale --agent jules --hours 24 --apply" in report["next_actions"]
    assert any(action.startswith("limen dispatch --agent jules") for action in report["next_actions"])


def test_release_stale_report_dry_run_does_not_mutate(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-008",
                "title": "Stale Jules task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "dispatched",
                "created": "2026-06-01",
                "dispatch_log": [],
            }
        ],
    )
    before = tasks_path.read_text()

    report = release_stale_tasks(load_limen_file(tasks_path), tasks_path, hours=24, dry_run=True, agent="jules")

    assert report["status"] == "dry_run"
    assert report["count"] == 1
    assert report["candidates"][0]["id"] == "LIMEN-008"
    assert tasks_path.read_text() == before


def test_qa_report_derives_lifecycle_without_mutation_or_private_fields(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-009",
                "title": "Recover task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "dispatched",
                "context": "private context must not leak",
                "urls": ["https://github.com/4444J99/limen/issues/9"],
                "created": "2026-06-01",
                "dispatch_log": [
                    {
                        "timestamp": "2026-06-01T00:00:00+00:00",
                        "agent": "jules",
                        "session_id": "private-session",
                        "status": "dispatched",
                    }
                ],
            },
            {
                "id": "LIMEN-010",
                "title": "Verify task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "medium",
                "budget_cost": 1,
                "status": "in_progress",
                "urls": ["https://github.com/4444J99/limen/pull/10"],
                "created": "2026-06-03",
                "dispatch_log": [
                    {
                        "timestamp": "2099-06-03T00:00:00+00:00",
                        "agent": "jules",
                        "session_id": "private-session",
                        "status": "in_progress",
                    }
                ],
            },
            {
                "id": "LIMEN-011",
                "title": "Assign task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "low",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-03",
                "dispatch_log": [],
            },
            {
                "id": "LIMEN-012",
                "title": "Archive task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "low",
                "budget_cost": 1,
                "status": "done",
                "created": "2026-06-03",
                "dispatch_log": [],
            },
            {
                "id": "LIMEN-013",
                "title": "Archived task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "low",
                "budget_cost": 1,
                "status": "archived",
                "created": "2026-06-03",
                "dispatch_log": [],
            },
        ],
    )
    before = tasks_path.read_text()

    report = qa_report(load_limen_file(tasks_path), tasks_path, agent="jules")

    assert report["status"] == "degraded"
    assert report["lifecycle"] == {
        "total": 5,
        "assign": 1,
        "verify": 1,
        "recover": 1,
        "archive_ready": 1,
        "archived": 1,
    }
    assert [item["id"] for item in report["steering"]["next_batch"]] == ["LIMEN-009", "LIMEN-010", "LIMEN-011"]
    assert [item["id"] for item in report["steering"]["assignment_queue"]] == ["LIMEN-011"]
    text = str(report)
    assert "private context must not leak" not in text
    assert "private-session" not in text
    assert "https://github.com/4444J99/limen/pull/10" not in text
    assert {mechanism["id"] for mechanism in report["mechanisms"]} == {
        "release-stale",
        "qa-verify",
        "assign-next",
        "archive-done",
    }
    mechanisms = {mechanism["id"]: mechanism for mechanism in report["mechanisms"]}
    assert mechanisms["release-stale"]["command"] == "POST /api/release-stale?hours=24&dry_run=false"
    assert mechanisms["qa-verify"]["command"] == "POST /api/tasks/{task_id}/verify"
    assert mechanisms["qa-verify"]["mode"] == "human-approved evidence gate"
    assert mechanisms["assign-next"]["command"] == "POST /api/tasks/{task_id}/assign"
    assert mechanisms["archive-done"]["command"] == "POST /api/tasks/{task_id}/archive"
    assert tasks_path.read_text() == before
