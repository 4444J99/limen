from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import limen.dispatch as D
from limen.capacity import PAID_AGENT_ORDER, agent_status, capacity_census, format_capacity_census, select_lanes
from limen.dispatch import dispatch_parallel, dispatch_tasks, release_stale_tasks
from limen.doctor import qa_report, readiness_report, stale_tasks
from limen.io import load_limen_file
from limen.jules_remote import JulesRemoteSnapshot
from limen.models import BudgetTrack, DispatchLogEntry, LimenFile, Task
from limen.status import print_status


def load_route_module():
    route_path = Path(__file__).resolve().parents[2] / "scripts" / "route.py"
    spec = importlib.util.spec_from_file_location("limen_route_test", route_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(tmp_path: Path, monkeypatch) -> None:
    """Dispatch selection consults LIMEN_ROOT-relative registries (value-repos.json, worktree
    receipts), so ambient fleet state on the host silently changes selection semantics. Pin the
    root to an empty per-test dir; tests that need a real root re-set LIMEN_ROOT themselves."""
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path / "hermetic-root"))
    monkeypatch.setenv("LIMEN_DISPATCH_ADMISSION", "0")
    monkeypatch.setenv("LIMEN_WORKTREE_DEBT_GATE", "0")
    for var in ("LIMEN_VALUE_REPOS", "LIMEN_VALUE_REPOS_FILE", "LIMEN_VALUE_GATE_STRICT"):
        monkeypatch.delenv(var, raising=False)


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


def test_always_working_timeout_fails_open_by_default(tmp_path: Path, monkeypatch, capsys) -> None:
    root = tmp_path / "root"
    script = root / "scripts" / "always-working.py"
    tasks_path = root / "tasks.yaml"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    tasks_path.write_text("version: '1.0'\ntasks: []\n", encoding="utf-8")
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    monkeypatch.delenv("LIMEN_ALWAYS_WORKING_TIMEOUT_HARD_GATE", raising=False)

    def timeout_capture(*_args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="always-working", timeout=kwargs.get("timeout", 1))

    monkeypatch.setattr(D, "_run_capture", timeout_capture)

    assert D.run_always_working_before_dispatch(tasks_path) is True
    assert "Always-working gate timed out before dispatch reservation" in capsys.readouterr().out


def test_always_working_timeout_can_be_hard_gated(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "root"
    script = root / "scripts" / "always-working.py"
    tasks_path = root / "tasks.yaml"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    tasks_path.write_text("version: '1.0'\ntasks: []\n", encoding="utf-8")
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    monkeypatch.setenv("LIMEN_ALWAYS_WORKING_TIMEOUT_HARD_GATE", "1")

    def timeout_capture(*_args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="always-working", timeout=kwargs.get("timeout", 1))

    monkeypatch.setattr(D, "_run_capture", timeout_capture)

    assert D.run_always_working_before_dispatch(tasks_path) is False


def test_dispatch_admission_pause_marker_blocks_even_when_general_gate_is_disabled(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "root"
    logs = root / "logs"
    logs.mkdir(parents=True)
    tasks = root / "tasks.yaml"
    tasks.write_text("version: '1.0'\ntasks: []\n", encoding="utf-8")
    (logs / "AUTONOMY_PAUSED").write_text(
        "integration drain\nreason: preserve current workers\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    monkeypatch.setenv("LIMEN_DISPATCH_ADMISSION", "0")
    monkeypatch.delenv("LIMEN_FORCE_AUTONOMY", raising=False)

    result = D.dispatch_admission_check(tasks, refresh_handoff=False)

    assert result["allow"] is False
    assert result["dispatch_allowed"] is False
    assert result["sources"] == ["autonomy_pause"]
    assert "integration drain" in result["reason"]


def _blocked_admission(*_args, **_kwargs):
    return {
        "allow": False,
        "status": "blocked",
        "exit_code": 10,
        "reason": "session value gate requested packetization",
        "next_command": "python3 scripts/prompt-packet-ledger.py --write",
        "value_gate": {"action": "switch_to_packetization"},
    }


def test_serial_dispatch_admission_blocks_before_worker_and_budget(tmp_path: Path, monkeypatch, capsys) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "T1",
                "title": "work",
                "repo": "x/y",
                "target_agent": "codex",
                "status": "open",
                "priority": "critical",
                "created": str(date.today()),
            }
        ],
    )
    monkeypatch.setenv("LIMEN_DISPATCH_ADMISSION", "1")
    monkeypatch.setattr(D, "dispatch_admission_check", _blocked_admission)
    monkeypatch.setattr(D, "call_agent_dispatch", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()))

    dispatch_tasks(load_limen_file(tasks_path), tasks_path, agent="codex", dry_run=False)

    out = capsys.readouterr().out
    board = read_board(tasks_path)
    assert "dispatch admission blocked" in out
    assert "python3 scripts/prompt-packet-ledger.py --write" in out
    assert board["tasks"][0]["status"] == "open"
    assert board["portal"]["budget"]["track"]["spent"] == 0


def test_parallel_dispatch_admission_blocks_before_reservation(tmp_path: Path, monkeypatch, capsys) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "T1",
                "title": "work",
                "repo": "x/y",
                "target_agent": "codex",
                "status": "open",
                "priority": "critical",
                "created": str(date.today()),
            }
        ],
    )
    monkeypatch.setenv("LIMEN_DISPATCH_ADMISSION", "1")
    monkeypatch.setattr(D, "dispatch_admission_check", _blocked_admission)
    monkeypatch.setattr(D, "call_agent_dispatch", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()))

    dispatch_parallel(load_limen_file(tasks_path), tasks_path, agents=["codex"], dry_run=False)

    out = capsys.readouterr().out
    board = read_board(tasks_path)
    assert "dispatch admission blocked" in out
    assert board["tasks"][0]["status"] == "open"
    assert board["tasks"][0].get("dispatch_log") in (None, [])
    assert board["portal"]["budget"]["track"]["spent"] == 0


def test_parallel_selection_suppresses_chronic_push_rejection(tmp_path: Path, monkeypatch, capsys) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    now = datetime.now(timezone.utc)
    write_board(
        tasks_path,
        [
            {
                "id": "CHRONIC",
                "title": "loop",
                "repo": "x/y",
                "target_agent": "codex",
                "status": "open",
                "priority": "critical",
                "created": str(date.today()),
                "dispatch_log": [
                    {
                        "timestamp": now.isoformat(),
                        "agent": "codex",
                        "session_id": "a",
                        "status": "failed",
                        "output": "push rejected by remote",
                    },
                    {
                        "timestamp": now.isoformat(),
                        "agent": "codex",
                        "session_id": "b",
                        "status": "failed",
                        "output": "non-fast-forward push rejected",
                    },
                ],
            },
            {
                "id": "FRESH",
                "title": "fresh",
                "repo": "x/y",
                "target_agent": "codex",
                "status": "open",
                "priority": "low",
                "created": str(date.today()),
            },
        ],
    )

    monkeypatch.setattr(D, "_worktree_debt_gate", lambda: (False, ""))

    dispatch_parallel(load_limen_file(tasks_path), tasks_path, agents=["codex"], per_agent_limit=2, dry_run=True)

    out = capsys.readouterr().out
    assert D.chronic_dispatch_reason(load_limen_file(tasks_path).tasks[0]) == "push-rejection-loop"
    assert "codex: FRESH" in out
    assert "codex: CHRONIC" not in out


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


def test_isolated_lane_env_points_limen_root_at_worktree(tmp_path: Path, monkeypatch) -> None:
    live_root = tmp_path / "live"
    wt = tmp_path / "worktree"
    monkeypatch.setenv("LIMEN_ROOT", str(live_root))
    monkeypatch.setenv("LIMEN_TASKS", str(live_root / "tasks.yaml"))

    env = D._lane_run_env("codex", wt)

    assert env["LIMEN_LIVE_ROOT"] == str(live_root)
    assert env["LIMEN_ROOT"] == str(wt)
    assert env["LIMEN_TASKS"] == str(wt / "tasks.yaml")
    assert env["PWD"] == str(wt)
    assert env["OLDPWD"] == str(live_root)


def test_auto_lane_selector_includes_github_actions_and_blocks_oz_without_warp_key(tmp_path: Path, monkeypatch) -> None:
    gh = tmp_path / "gh"
    gh.write_text("#!/bin/sh\nexit 0\n")
    gh.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("WARP_API_KEY", raising=False)

    tasks_path = tmp_path / "tasks.yaml"
    write_board(tasks_path, [])
    board = load_limen_file(tasks_path)

    lanes = select_lanes("auto", board)

    assert "github_actions" in lanes
    assert "oz" not in lanes


def test_auto_lane_selector_keeps_agy_up_on_weak_proxy_budget_saturation(tmp_path: Path, monkeypatch) -> None:
    agy = tmp_path / "agy"
    agy.write_text("#!/bin/sh\nexit 0\n")
    agy.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "usage.json").write_text(
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
        )
    )
    tasks_path = tmp_path / "tasks.yaml"
    tasks_path.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "portal": {
                    "name": "Universal Task Intake",
                    "budget": {
                        "daily": 10,
                        "unit": "runs",
                        "per_agent": {"agy": 1},
                        "track": {"date": "", "spent": 1, "per_agent": {"agy": 1}},
                    },
                },
                "tasks": [],
            },
            sort_keys=False,
        )
    )
    board = load_limen_file(tasks_path)

    rows = {row["agent"]: row for row in capacity_census(board)}
    lanes = select_lanes("auto", board)

    assert rows["agy"]["reachable"] is True
    assert rows["agy"]["remaining"] == 9
    assert "agy" in lanes


def test_github_actions_lane_requires_configured_workflow(tmp_path: Path, monkeypatch) -> None:
    gh = tmp_path / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = workflow ] && [ "$2" = view ]; then\n'
        "  echo 'workflow missing' >&2\n"
        "  exit 1\n"
        "fi\n"
        "exit 0\n"
    )
    gh.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("WARP_API_KEY", raising=False)

    tasks_path = tmp_path / "tasks.yaml"
    write_board(tasks_path, [])
    board = load_limen_file(tasks_path)

    status = agent_status("github_actions")
    lanes = select_lanes("auto", board)

    assert status["reachable"] is False
    assert "workflow=limen-agent.yml@organvm/limen unavailable" in status["detail"]
    assert "github_actions" not in lanes


def test_github_actions_lane_uses_configured_executor_workflow(tmp_path: Path, monkeypatch) -> None:
    gh = tmp_path / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = workflow ] && [ "$2" = view ] && [ "$3" = custom-agent.yml ]; then\n'
        "  exit 0\n"
        "fi\n"
        "exit 1\n"
    )
    gh.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("LIMEN_GITHUB_ACTIONS_WORKFLOW", "custom-agent.yml")

    status = agent_status("github_actions")

    assert status["reachable"] is True
    assert "workflow=custom-agent.yml@organvm/limen" in status["detail"]


def test_route_distributes_local_work_and_reaches_extended_fleet(tmp_path: Path) -> None:
    """Ideal-form router: repo work spreads across repo-capable lanes by budget+refresh-runway.

    Local checkout work may now include the jules remote batch-fill lane; copilot/warp/oz still stay
    out of ordinary repo routing unless reached through the extended-fleet fallback.
    """
    route = load_route_module()
    workdir = tmp_path / "work"
    checkout = workdir / "organvm" / "limen"
    (checkout / ".git").mkdir(parents=True)
    health = {agent: True for agent in PAID_AGENT_ORDER}
    budget = {a: 10 for a in ("codex", "claude", "agy", "opencode", "jules")}

    # Many local-checkout tasks must SPREAD across repo-capable lanes, never serialize onto one.
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
    repo_worker_lanes = {"codex", "claude", "agy", "opencode", "gemini", "ollama", "jules"}
    assert set(picks) <= repo_worker_lanes, f"repo work leaked to {set(picks)}"
    assert len(set(picks)) >= 2, f"work serialized onto {set(picks)}"

    # A repo with NO local checkout still reaches a local lane because dispatch.py clones on demand.
    remote = {
        "id": "REMOTE-1",
        "title": "Remote-only repo",
        "repo": "someorg/no-local-here",
        "status": "open",
        "budget_cost": 1,
        "urls": ["https://github.com/someorg/no-local-here/issues/9"],
    }
    vendor, reason = route.route_task(remote, health, workdir, assigned={}, budget=budget)
    assert vendor in repo_worker_lanes, (vendor, reason)
    assert "clone" in reason


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


def test_dispatch_skips_open_task_with_prior_done_log(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
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


def test_dispatch_bulk_gates_unmet_deps_but_explicit_task_overrides(tmp_path: Path, capsys) -> None:
    # Serial bulk dispatch must gate on dependencies the same way dispatch_parallel does; an
    # explicit --task is a human override that bypasses the gate.
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "DEP",
                "title": "Predecessor — PR not yet merged",
                # neutral slug: agent_can_run_task bars codex/claude from organvm/limen
                "repo": "someorg/dispatch-lab",
                "target_agent": "external",  # keep DEP out of the codex candidate set
                "priority": "high",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-30",
                "dispatch_log": [],
            },
            {
                "id": "DEPENDENT",
                "title": "Waits on DEP",
                "repo": "someorg/dispatch-lab",
                "target_agent": "codex",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "depends_on": ["DEP"],
                "created": "2026-06-30",
                "dispatch_log": [],
            },
        ],
    )

    # BULK: DEP is unmerged, so DEPENDENT is withheld (matches the parallel path's gate).
    dispatch_tasks(load_limen_file(tasks_path), tasks_path, agent="codex", dry_run=True)
    bulk = capsys.readouterr().out
    assert "DEPENDENT" not in bulk
    assert "No open tasks for agent 'codex'" in bulk

    # EXPLICIT single-task dispatch is a deliberate human override — it bypasses the deps gate.
    dispatch_tasks(load_limen_file(tasks_path), tasks_path, agent="codex", dry_run=True, task_id="DEPENDENT")
    override = capsys.readouterr().out
    assert "DRY-RUN: 1 task(s)" in override


def test_dispatch_parallel_skips_needs_human_label(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(D, "_worktree_debt_gate", lambda: (False, ""))
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "HUMAN-GATE",
                "title": "Needs human",
                "repo": "someorg/dispatch-lab",
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
                "repo": "someorg/dispatch-lab",
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


def test_parallel_selection_normalizes_only_selected_legacy_task(monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_VALUE_GATE", "0")
    board = LimenFile.model_validate(
        {
            "portal": {"budget": {"daily": 10, "per_agent": {"codex": 10}, "track": {"date": ""}}},
            "tasks": [
                {
                    "id": "SELECTED",
                    "title": "Selected legacy task",
                    "repo": "someorg/dispatch-lab",
                    "target_agent": "codex",
                    "priority": "critical",
                    "status": "open",
                    "created": "2026-07-12",
                },
                {
                    "id": "UNSELECTED",
                    "title": "Unselected legacy task",
                    "repo": "someorg/dispatch-lab",
                    "target_agent": "codex",
                    "priority": "low",
                    "status": "open",
                    "created": "2026-07-12",
                },
            ],
        }
    )

    picked = D._select_parallel_reservations(
        board,
        ["codex"],
        1,
        datetime.now(timezone.utc),
        dry_run=False,
        admission_snapshot=None,
    )

    assert picked == [("codex", "SELECTED")]
    selected, unselected = board.tasks
    assert selected.predicate and selected.receipt_target
    assert selected.status == "dispatched"
    assert unselected.predicate is None and unselected.receipt_target is None
    assert unselected.status == "open"


def test_parallel_selection_fails_closed_when_legacy_owner_cannot_be_derived(monkeypatch, capsys) -> None:
    monkeypatch.setenv("LIMEN_VALUE_GATE", "0")
    board = LimenFile.model_validate(
        {
            "portal": {"budget": {"daily": 10, "per_agent": {"codex": 10}, "track": {"date": ""}}},
            "tasks": [
                {
                    "id": "NO-OWNER",
                    "title": "Missing owner repo",
                    "target_agent": "codex",
                    "priority": "critical",
                    "status": "open",
                    "created": "2026-07-12",
                }
            ],
        }
    )

    picked = D._select_parallel_reservations(
        board,
        ["codex"],
        1,
        datetime.now(timezone.utc),
        dry_run=False,
        admission_snapshot=None,
    )

    assert picked == []
    assert board.tasks[0].status == "open"
    assert "INTAKE BLOCKED NO-OWNER" in capsys.readouterr().out


def _blocked_local_snapshot() -> "D.WorktreeAdmissionSnapshot":
    return D.WorktreeAdmissionSnapshot(
        active=True,
        block_new_local=True,
        reason="local free 2.0 GiB < 45 GiB floor",
        resource_blocked=True,
        vitals_shed=False,
        reaper_blocked=False,
        free_gib=2.0,
        floor_gib=45,
        reserved_gib=0.0,
        room_gib=0.0,
        targets_present=True,
        debt=0,
        vitals_action="ok",
    )


def test_dispatch_parallel_admission_blocks_every_local_candidate(tmp_path: Path, capsys, monkeypatch) -> None:
    """When custody is unavailable, EVERY local candidate is withheld (not only generated build-out);
    a remote lane still runs the same work off-box."""
    monkeypatch.setenv("LIMEN_WORKTREE_DEBT_GATE", "1")
    monkeypatch.setattr(D, "_worktree_admission_snapshot", _blocked_local_snapshot)
    tasks_path = tmp_path / "tasks.yaml"
    board = [
        {
            "id": "GEN-BUILDOUT",
            "title": "Generated build-out",
            "repo": "someorg/dispatch-lab",
            "target_agent": "any",
            "priority": "critical",
            "budget_cost": 1,
            "status": "open",
            "labels": ["typing", "generated", "build-out"],
            "created": "2026-06-20",
            "dispatch_log": [],
        },
        {
            "id": "LIFECYCLE-RECLAIM",
            "title": "Reclaim lifecycle debt (still creates a local worktree)",
            "repo": "someorg/dispatch-lab",
            "target_agent": "any",
            "priority": "critical",
            "budget_cost": 1,
            "status": "open",
            "labels": ["lifecycle", "reclaim"],
            "created": "2026-06-20",
            "dispatch_log": [],
        },
    ]
    write_board(tasks_path, board)

    # Local lane: both candidates blocked — cleanup/reclaim is NOT exempt (it creates a worktree too).
    dispatch_parallel(load_limen_file(tasks_path), tasks_path, agents=["codex"], dry_run=True)
    output = capsys.readouterr().out
    assert "Worktree admission" in output
    assert "GEN-BUILDOUT" not in output  # non-value generated build-out is filtered before final selection
    assert "Worktree admission blocked LIFECYCLE-RECLAIM" in output

    # Remote lane: runs off-box, never inherits local pressure.
    write_board(tasks_path, board)
    dispatch_parallel(load_limen_file(tasks_path), tasks_path, agents=["jules"], dry_run=True)
    remote_out = capsys.readouterr().out
    assert "jules:" in remote_out


def test_dispatch_parallel_skips_generated_buildout_outside_value_tier(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_VALUE_REPOS", "someorg/value-lab")
    monkeypatch.setenv("LIMEN_VALUE_REPOS_FILE", str(tmp_path / "no-such-tier.json"))
    monkeypatch.setattr(D, "_worktree_debt_gate", lambda: (False, ""))
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "GEN-NONVALUE",
                "title": "Generated non-value build-out",
                "repo": "organvm/site.github.io",
                "target_agent": "any",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "labels": ["typing", "generated", "build-out"],
                "created": "2026-06-20",
                "dispatch_log": [],
            },
            {
                "id": "VALUE-WORK",
                "title": "Value-tier work",
                "repo": "someorg/value-lab",
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
    assert "VALUE-WORK" in output
    assert "GEN-NONVALUE" not in output


def test_serial_dispatch_value_gate_withholds_generic_non_value_work(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_VALUE_REPOS", "organvm/value-repo")
    monkeypatch.setenv("LIMEN_VALUE_REPOS_FILE", str(tmp_path / "missing-value-repos.json"))
    monkeypatch.setenv("LIMEN_DISPATCH_CMD", "agent-stub")
    monkeypatch.setattr(D, "_worktree_debt_gate", lambda: (False, ""))
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "GENERIC-WORK",
                "title": "Generic queue churn",
                "repo": "organvm/generic-repo",
                "target_agent": "codex",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-07-08",
                "dispatch_log": [],
            },
            {
                "id": "VALUE-WORK",
                "title": "Value-tier owner work",
                "repo": "organvm/value-repo",
                "target_agent": "codex",
                "priority": "low",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-07-08",
                "dispatch_log": [],
            },
        ],
    )

    dispatch_tasks(load_limen_file(tasks_path), tasks_path, agent="codex", dry_run=True)

    output = capsys.readouterr().out
    assert "VALUE-WORK" in output
    assert "GENERIC-WORK" not in output


def test_dispatch_parallel_value_gate_withholds_generic_non_value_work(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_VALUE_REPOS", "organvm/value-repo")
    monkeypatch.setenv("LIMEN_VALUE_REPOS_FILE", str(tmp_path / "missing-value-repos.json"))
    monkeypatch.setattr(D, "_worktree_debt_gate", lambda: (False, ""))
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "GENERIC-WORK",
                "title": "Generic queue churn",
                "repo": "organvm/generic-repo",
                "target_agent": "any",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-07-08",
                "dispatch_log": [],
            },
            {
                "id": "LIFECYCLE-WORK",
                "title": "Preserve worktree lifecycle receipt",
                "repo": "organvm/generic-repo",
                "target_agent": "any",
                "priority": "high",
                "budget_cost": 1,
                "status": "open",
                "labels": ["lifecycle"],
                "created": "2026-07-08",
                "dispatch_log": [],
            },
        ],
    )

    dispatch_parallel(load_limen_file(tasks_path), tasks_path, agents=["codex"], dry_run=True)

    output = capsys.readouterr().out
    assert "LIFECYCLE-WORK" in output
    assert "GENERIC-WORK" not in output


def test_dispatch_parallel_reloads_under_queue_lock_before_reserve_write(
    tmp_path: Path,
    monkeypatch,
) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "DISPATCH-ME",
                "title": "Dispatch me",
                "repo": "someorg/dispatch-lab",
                "target_agent": "codex",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-20",
                "dispatch_log": [],
            }
        ],
    )
    stale = load_limen_file(tasks_path)
    board = read_board(tasks_path)
    board["tasks"].append(
        {
            "id": "CONCURRENT",
            "title": "Concurrent task",
            "repo": "someorg/dispatch-lab",
            "target_agent": "agy",
            "priority": "critical",
            "budget_cost": 1,
            "status": "open",
            "created": "2026-06-20",
            "dispatch_log": [],
        }
    )
    tasks_path.write_text(yaml.safe_dump(board, sort_keys=False))
    calls: list[str] = []

    def fake_dispatch(agent, task, dry_run=False):
        calls.append(task.id)
        return True

    monkeypatch.setattr(D, "_worktree_debt_gate", lambda: (False, ""))
    monkeypatch.setattr(D, "call_agent_dispatch", fake_dispatch)

    dispatch_parallel(stale, tasks_path, agents=["codex"], per_agent_limit=1, max_workers=1, dry_run=False)

    tasks = {task["id"]: task for task in read_board(tasks_path)["tasks"]}
    assert set(tasks) == {"DISPATCH-ME", "CONCURRENT"}
    assert tasks["DISPATCH-ME"]["status"] == "dispatched"
    assert tasks["CONCURRENT"]["status"] == "open"
    assert calls == ["DISPATCH-ME"]


def test_dispatch_parallel_does_not_dispatch_stale_open_task(
    tmp_path: Path,
    monkeypatch,
) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "ALREADY-DONE",
                "title": "Already done",
                "repo": "organvm/limen",
                "target_agent": "codex",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-20",
                "dispatch_log": [],
            }
        ],
    )
    stale = load_limen_file(tasks_path)
    board = read_board(tasks_path)
    board["tasks"][0]["status"] = "done"
    tasks_path.write_text(yaml.safe_dump(board, sort_keys=False))
    calls: list[str] = []

    monkeypatch.setattr(D, "call_agent_dispatch", lambda agent, task, dry_run=False: calls.append(task.id) or True)
    monkeypatch.setattr(D, "_worktree_debt_gate", lambda: (False, ""))

    dispatch_parallel(stale, tasks_path, agents=["codex"], per_agent_limit=1, max_workers=1, dry_run=False)

    tasks = {task["id"]: task for task in read_board(tasks_path)["tasks"]}
    assert tasks["ALREADY-DONE"]["status"] == "done"
    assert calls == []


def _concurrent_fold(tasks_path: Path, task_id: str = "CONCURRENT-FOLD") -> None:
    """Simulate a keeper/route write landing on tasks.yaml while a dispatch cycle holds a
    stale in-memory snapshot (the lost-update wipe scenario)."""
    board = read_board(tasks_path)
    board["tasks"].append(
        {
            "id": task_id,
            "title": "Folded while agents ran",
            "repo": "organvm/limen",
            "target_agent": "agy",
            "priority": "critical",
            "budget_cost": 1,
            "status": "open",
            "created": "2026-06-20",
            "dispatch_log": [],
        }
    )
    tasks_path.write_text(yaml.safe_dump(board, sort_keys=False))


def test_dispatch_serial_commit_survives_concurrent_board_write(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Serial dispatch loads the board, runs agents for minutes, then saves — persisting that
    stale snapshot erased every interim write (keeper folds, route stamps). The commit must
    re-apply results onto a FRESH reload so concurrent writes survive."""
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "DISPATCH-ME",
                "title": "Dispatch me",
                "repo": "someorg/dispatch-lab",
                "target_agent": "codex",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-20",
                "dispatch_log": [],
            }
        ],
    )
    stale = load_limen_file(tasks_path)

    def fold_then_succeed(agent, task, dry_run=False):
        _concurrent_fold(tasks_path)
        concurrent = read_board(tasks_path)
        dispatched = next(row for row in concurrent["tasks"] if row["id"] == "DISPATCH-ME")
        dispatched["predicate"] = "pytest -q concurrent-owner-check"
        dispatched["receipt_target"] = "git:someorg/dispatch-lab:receipts/concurrent-owner.json"
        tasks_path.write_text(yaml.safe_dump(concurrent, sort_keys=False))
        return True

    monkeypatch.setattr(D, "_down_lanes", lambda: set())
    monkeypatch.setattr(D, "_worktree_debt_gate", lambda: (False, ""))
    monkeypatch.setattr(D, "call_agent_dispatch", fold_then_succeed)

    dispatch_tasks(stale, tasks_path, agent="codex", dry_run=False)

    tasks = {task["id"]: task for task in read_board(tasks_path)["tasks"]}
    assert set(tasks) == {"DISPATCH-ME", "CONCURRENT-FOLD"}
    assert tasks["DISPATCH-ME"]["status"] == "dispatched"
    assert tasks["DISPATCH-ME"]["predicate"] == "pytest -q concurrent-owner-check"
    assert tasks["DISPATCH-ME"]["receipt_target"].endswith("concurrent-owner.json")
    assert tasks["CONCURRENT-FOLD"]["status"] == "open"


def test_dispatch_budget_reset_persist_survives_concurrent_board_write(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The no-candidate budget-reset persist saved the caller's whole stale snapshot; it must
    commit the reset via a fresh reload instead."""
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    tasks_path = tmp_path / "tasks.yaml"
    write_board(tasks_path, [])
    board = read_board(tasks_path)
    board["portal"]["budget"]["track"] = {
        "date": "2026-01-01",
        "spent": 2,
        "per_agent": {"codex": 2},
        "per_agent_reset": {"codex": "2026-01-01T00:00:00+00:00"},
    }
    tasks_path.write_text(yaml.safe_dump(board, sort_keys=False))
    stale = load_limen_file(tasks_path)

    _concurrent_fold(tasks_path)

    monkeypatch.setattr(D, "_down_lanes", lambda: set())
    monkeypatch.setattr(D, "_worktree_debt_gate", lambda: (False, ""))

    dispatch_tasks(stale, tasks_path, agent="codex", dry_run=False)

    board = read_board(tasks_path)
    assert "CONCURRENT-FOLD" in {task["id"] for task in board["tasks"]}
    assert board["portal"]["budget"]["track"]["per_agent"]["codex"] == 0


def test_release_stale_apply_survives_concurrent_board_write(
    tmp_path: Path,
) -> None:
    """release-stale APPLY re-selects and mutates a FRESH board under the queue lock; saving
    the caller's snapshot would erase concurrent writes."""
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "STALE-CLAIM",
                "title": "Stale dispatched task",
                "repo": "organvm/limen",
                "target_agent": "codex",
                "priority": "high",
                "budget_cost": 1,
                "status": "dispatched",
                "created": "2026-06-01",
                "dispatch_log": [],
            }
        ],
    )
    stale = load_limen_file(tasks_path)

    _concurrent_fold(tasks_path)

    report = release_stale_tasks(stale, tasks_path, hours=24, dry_run=False)

    tasks = {task["id"]: task for task in read_board(tasks_path)["tasks"]}
    assert set(tasks) == {"STALE-CLAIM", "CONCURRENT-FOLD"}
    assert tasks["STALE-CLAIM"]["status"] == "open"
    assert report["status"] == "applied"
    assert report["released"] == ["STALE-CLAIM"]


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

    monkeypatch.delenv("LIMEN_CLAUDE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("LIMEN_CLAUDE_API_KEY", raising=False)
    claude_keyless_env = D._lane_run_env("claude")
    assert "ANTHROPIC_API_KEY" not in claude_keyless_env
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in claude_keyless_env

    monkeypatch.setenv("LIMEN_CLAUDE_API_KEY", "fleet-api-key")
    claude_api_env = D._lane_run_env("claude")
    assert claude_api_env["ANTHROPIC_API_KEY"] == "fleet-api-key"
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in claude_api_env


def test_failed_agent_result_names_lane_and_task(capsys) -> None:
    task = Task(
        id="LIMEN-FAIL-LANE",
        title="Fail lane",
        repo="organvm/limen",
        target_agent="claude",
        priority="high",
        budget_cost=1,
        status="open",
        created="2026-07-06",
    )
    run = subprocess.CompletedProcess(["claude"], 1, stdout="", stderr="connector shadowed")

    assert D._failed_agent_result("claude", task, run) is False
    assert "FAILED agent claude on LIMEN-FAIL-LANE (1): connector shadowed" in capsys.readouterr().out


def test_resolve_agent_binary_uses_opencode_clock_when_installed(monkeypatch) -> None:
    monkeypatch.delenv("LIMEN_OPENCODE_BIN", raising=False)
    monkeypatch.setattr(D.shutil, "which", lambda binary: f"/bin/{binary}" if binary == "opencode-clock" else None)

    assert D._resolve_agent_binary("opencode") == "opencode-clock"


def test_resolve_agent_binary_falls_back_when_wrapper_missing(monkeypatch) -> None:
    monkeypatch.delenv("LIMEN_OPENCODE_BIN", raising=False)
    monkeypatch.setattr(D.shutil, "which", lambda binary: None)

    assert D._resolve_agent_binary("opencode") == "opencode"


def test_path_like_repo_resolves_to_local_checkout(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    (repo / ".git").mkdir(parents=True)
    task = Task(id="LOCAL-PATH", title="local", repo=str(repo), target_agent="codex", created=date(2026, 7, 7))

    assert D._resolve_repo_dir(task) == repo
    assert D._clone_repo(task) == repo


def test_jules_path_repo_derives_remote_slug(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "checkout"
    (repo / ".git").mkdir(parents=True)
    task = Task(id="JULES-PATH", title="jules", repo=str(repo), target_agent="jules", created=date(2026, 7, 7))
    calls: list[list[str]] = []

    monkeypatch.setattr(D, "_github_slug_from_local_repo", lambda path: "organvm/limen")

    def fake_run_cmd(cmd, task, dry_run, cwd=None):
        calls.append(cmd)
        return "123456789012345"

    monkeypatch.setattr(D, "_run_cmd", fake_run_cmd)

    assert D._call_jules(task, dry_run=False) == "123456789012345"
    assert calls[0][3:5] == ["--repo", "organvm/limen"]


def test_jules_success_without_session_id_is_failure(monkeypatch, capsys) -> None:
    task = Task(id="JULES-NO-ID", title="jules", repo="organvm/limen", target_agent="jules", created=date(2026, 7, 7))

    def fake_run_capture(cmd, cwd=None, timeout=600, env=None):
        return subprocess.CompletedProcess(cmd, 0, "Session is created.\n", "")

    monkeypatch.setattr(D, "_run_capture", fake_run_capture)

    assert D._run_cmd(["jules", "remote", "new"], task, dry_run=False) is False
    assert "no session id" in capsys.readouterr().out


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


def test_dispatch_numeric_env_knobs_fail_open_when_malformed(tmp_path: Path, monkeypatch) -> None:
    import datetime
    import socket

    class FakeSocket:
        def close(self) -> None:
            pass

    oauth_timeouts: list[float] = []

    def fake_create_connection(addr, timeout):
        oauth_timeouts.append(timeout)
        return FakeSocket()

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    monkeypatch.setenv("LIMEN_OAUTH_PREFLIGHT_TIMEOUT", "not-a-float")
    assert D._oauth_unreachable_lanes() == set()
    assert oauth_timeouts == [3.0]

    captured: dict[str, int] = {}

    def fake_run_capture(cmd, cwd=None, timeout=600, env=None):
        captured["timeout"] = timeout
        return subprocess.CompletedProcess(cmd, 0, "", "")

    task = Task(id="ENV-KNOBS", title="env", repo="x/y", target_agent="codex", created=date(2026, 6, 27))
    monkeypatch.setattr(D, "_run_capture", fake_run_capture)
    monkeypatch.setenv("LIMEN_DISPATCH_TIMEOUT", "not-an-int")
    assert D._run_cmd(["codex"], task, dry_run=False) is True
    assert captured["timeout"] == 600

    monkeypatch.setattr(D, "_resolve_agent_binary", lambda agent: agent)
    monkeypatch.setattr(D, "_resolve_repo_dir", lambda _task: tmp_path)
    monkeypatch.setenv("LIMEN_LANE_TIMEOUT", "not-an-int")
    assert D._isolated_local_run("codex", task, dry_run=True) is True

    tasks_path = tmp_path / "tasks.yaml"
    write_board(tasks_path, [])
    limen = load_limen_file(tasks_path)
    monkeypatch.setenv("LIMEN_ACCEL_TLEFT_FLOOR", "not-a-float")
    monkeypatch.setenv("LIMEN_ACCEL_ASYNC_CEIL", "not-an-int")
    assert D._accel_limit(limen, "jules", 2, datetime.datetime.now(datetime.timezone.utc)) >= 2


def test_same_repo_pr_head_for_task_resolves_open_pr(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_capture(cmd, cwd=None, timeout=600, env=None):
        calls.append(cmd)
        return subprocess.CompletedProcess(
            cmd,
            0,
            json.dumps(
                {
                    "baseRefName": "master",
                    "headRefName": "limen/fix-ci-175",
                    "headRepositoryOwner": {"login": "organvm"},
                    "state": "OPEN",
                }
            ),
            "",
        )

    monkeypatch.setattr(D, "_run_capture", fake_run_capture)
    task = Task(
        id="HEAL-175",
        title="fix failing CI on organvm/domus-genoma#175",
        repo="organvm/domus-genoma",
        target_agent="codex",
        created=date(2026, 6, 27),
    )

    assert D._task_github_pr_ref(task) == ("organvm/domus-genoma", 175)
    assert D._same_repo_pr_head_for_task(task) == {
        "repo": "organvm/domus-genoma",
        "number": "175",
        "head_ref": "limen/fix-ci-175",
        "base_ref": "master",
    }
    assert calls[0][:4] == ["gh", "pr", "view", "175"]


def test_pr_repair_prompt_forbids_assumed_limen_workflow() -> None:
    task = Task(
        id="HEAL-172",
        title="fix failing CI on organvm/domus-genoma#172",
        repo="organvm/domus-genoma",
        target_agent="codex",
        urls=["https://github.com/organvm/domus-genoma/pull/172"],
        created=date(2026, 6, 27),
    )

    prompt = D._build_prompt(task)

    assert "statusCheckRollup" in prompt
    assert "workflow list" in prompt
    assert "do not assume" in prompt
    assert "Limen-owned workflow file" in prompt


def test_isolated_local_run_updates_same_repo_pr_head(tmp_path: Path, monkeypatch) -> None:
    git_calls: list[list[str]] = []
    pushed_pr_heads: list[tuple[str, Path]] = []
    auto_merge_urls: list[str] = []
    cleanups: list[tuple[str, bool]] = []

    def fake_git_plumbing(args, cwd, timeout=120):
        git_calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    def fake_git(args, cwd, timeout=120):
        if args == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, "base-head\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(D, "_resolve_agent_binary", lambda agent: agent)
    monkeypatch.setattr(D, "_resolve_repo_dir", lambda _task: tmp_path)
    monkeypatch.setattr(D, "_default_branch", lambda _repo: "master")
    monkeypatch.setattr(
        D,
        "_same_repo_pr_head_for_task",
        lambda _task: {
            "repo": "organvm/domus-genoma",
            "number": "175",
            "head_ref": "limen/fix-ci-175",
            "base_ref": "master",
        },
    )
    monkeypatch.setattr(D, "_git_plumbing", fake_git_plumbing)
    monkeypatch.setattr(D, "_git", fake_git)
    monkeypatch.setattr(D, "_run_isolated_agent", lambda *args: True)
    monkeypatch.setattr(D, "_commit_isolated_changes", lambda *args: True)
    monkeypatch.setattr(
        D,
        "_push_existing_pr_head",
        lambda task, wt, pr_head: pushed_pr_heads.append((pr_head["head_ref"], wt)) or True,
    )
    monkeypatch.setattr(
        D,
        "_arm_auto_merge",
        lambda task, wt, url: auto_merge_urls.append(url),
    )
    monkeypatch.setattr(
        D,
        "_cleanup_isolated_worktree",
        lambda repo_dir, wt, branch, base_ref, pushed, task=None: cleanups.append((base_ref, pushed)),
    )
    monkeypatch.setattr(D.secrets, "token_hex", lambda _n: "abcd")
    monkeypatch.setattr(D, "_isolation_root", lambda: tmp_path / "worktrees")
    task = Task(
        id="HEAL-cifix-organvm-domus-genoma-175",
        title="fix failing CI on organvm/domus-genoma#175",
        repo="organvm/domus-genoma",
        target_agent="codex",
        created=date(2026, 6, 27),
    )

    result = D._isolated_local_run("codex", task, dry_run=False)

    assert result == "https://github.com/organvm/domus-genoma/pull/175"
    assert git_calls[0] == [
        "fetch",
        "origin",
        "+refs/heads/limen/fix-ci-175:refs/remotes/origin/limen/fix-ci-175",
    ]
    assert git_calls[1] == [
        "worktree",
        "add",
        "-b",
        "limen/heal-cifix-organvm-domus-genoma-175-abcd",
        str(tmp_path / "worktrees" / "heal-cifix-organvm-domus-genoma-175-abcd"),
        "origin/limen/fix-ci-175",
    ]
    assert pushed_pr_heads == [
        ("limen/fix-ci-175", tmp_path / "worktrees" / "heal-cifix-organvm-domus-genoma-175-abcd")
    ]
    assert auto_merge_urls == ["https://github.com/organvm/domus-genoma/pull/175"]
    assert cleanups == [("origin/limen/fix-ci-175", True)]


def test_isolated_local_run_treats_agent_committed_pr_head_as_work(tmp_path: Path, monkeypatch) -> None:
    heads = iter(["base-head\n", "agent-commit\n"])
    pushed_pr_heads: list[str] = []

    def fake_git(args, cwd, timeout=120):
        if args == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, next(heads), "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(D, "_resolve_agent_binary", lambda agent: agent)
    monkeypatch.setattr(D, "_resolve_repo_dir", lambda _task: tmp_path)
    monkeypatch.setattr(D, "_default_branch", lambda _repo: "master")
    monkeypatch.setattr(
        D,
        "_same_repo_pr_head_for_task",
        lambda _task: {
            "repo": "organvm/domus-genoma",
            "number": "175",
            "head_ref": "limen/fix-ci-175",
            "base_ref": "master",
        },
    )
    monkeypatch.setattr(D, "_git_plumbing", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "", ""))
    monkeypatch.setattr(D, "_git", fake_git)
    monkeypatch.setattr(D, "_run_isolated_agent", lambda *args: True)
    monkeypatch.setattr(D, "_commit_isolated_changes", lambda *args: D._NOOP)
    monkeypatch.setattr(
        D,
        "_push_existing_pr_head",
        lambda task, wt, pr_head: pushed_pr_heads.append(pr_head["head_ref"]) or True,
    )
    monkeypatch.setattr(D, "_arm_auto_merge", lambda *args: None)
    monkeypatch.setattr(D, "_cleanup_isolated_worktree", lambda *args, **kwargs: None)
    monkeypatch.setattr(D.secrets, "token_hex", lambda _n: "abcd")
    monkeypatch.setattr(D, "_isolation_root", lambda: tmp_path / "worktrees")
    task = Task(
        id="HEAL-cifix-organvm-domus-genoma-175",
        title="fix failing CI on organvm/domus-genoma#175",
        repo="organvm/domus-genoma",
        target_agent="codex",
        created=date(2026, 6, 27),
    )

    result = D._isolated_local_run("codex", task, dry_run=False)

    assert result == "https://github.com/organvm/domus-genoma/pull/175"
    assert pushed_pr_heads == ["limen/fix-ci-175"]


def test_git_plumbing_retries_transient_config_lock(tmp_path: Path, monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_git(args, cwd, timeout=120):
        calls.append(args)
        if len(calls) == 1:
            return subprocess.CompletedProcess(
                args, 128, "", "error: could not lock config file .git/config: File exists"
            )
        return subprocess.CompletedProcess(args, 0, "ok", "")

    monkeypatch.setattr(D, "_git", fake_git)
    monkeypatch.setattr(D.time, "sleep", lambda _seconds: None)

    result = D._git_plumbing(["worktree", "add"], tmp_path)

    assert result.returncode == 0
    assert len(calls) == 2


def _git_ok(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return result.stdout


def _make_cleanup_repo(tmp_path: Path) -> tuple[Path, Path, str]:
    repo = tmp_path / "repo"
    wt = tmp_path / "wt"
    repo.mkdir()
    _git_ok(repo, "init", "-q", "-b", "main")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git_ok(repo, "add", "README.md")
    _git_ok(repo, "-c", "user.email=t@example.com", "-c", "user.name=test", "commit", "-qm", "base")
    branch = "limen/test-cleanup"
    _git_ok(repo, "worktree", "add", "-q", "-b", branch, str(wt), "main")
    return repo, wt, branch


def test_cleanup_isolated_worktree_retains_clean_noop_branch_for_reclaim(tmp_path: Path) -> None:
    repo, wt, branch = _make_cleanup_repo(tmp_path)
    (wt / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (wt / "node_modules").mkdir()
    (wt / "node_modules" / "dep.txt").write_text("generated\n", encoding="utf-8")

    D._cleanup_isolated_worktree(repo, wt, branch, "main", pushed=False)

    assert wt.exists()
    assert not (wt / "node_modules").exists()
    assert branch in _git_ok(repo, "branch", "--list", branch)


def test_worktree_birth_receipt_is_written_to_private_gitdir(tmp_path: Path, monkeypatch) -> None:
    repo, wt, branch = _make_cleanup_repo(tmp_path)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path / "limen"))
    task = Task(
        id="BIRTH-1",
        title="birth receipt",
        repo="organvm/limen",
        target_agent="codex",
        created=date(2026, 7, 9),
    )

    D._record_worktree_birth(task, wt, branch, "origin/main", "main", existing_pr=False)

    gitdir = Path(_git_ok(wt, "rev-parse", "--git-dir").strip())
    if not gitdir.is_absolute():
        gitdir = wt / gitdir
    receipt = gitdir / "limen-worktree-birth.json"
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["task_id"] == "BIRTH-1"
    assert payload["remote_branch"] == branch
    assert not (wt / "limen-worktree-birth.json").exists()
    assert "limen-worktree-birth.json" not in _git_ok(wt, "status", "--porcelain")


def test_cleanup_isolated_worktree_preserves_dirty_failed_work(tmp_path: Path) -> None:
    repo, wt, branch = _make_cleanup_repo(tmp_path)
    (wt / "local.txt").write_text("local-only\n", encoding="utf-8")
    (wt / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (wt / "node_modules").mkdir()
    (wt / "node_modules" / "dep.txt").write_text("generated\n", encoding="utf-8")

    D._cleanup_isolated_worktree(repo, wt, branch, "main", pushed=False)

    assert wt.exists()
    assert (wt / "local.txt").exists()
    assert not (wt / "node_modules").exists()
    assert branch in _git_ok(repo, "branch", "--list", branch)


def test_cleanup_isolated_worktree_preserves_unpushed_commits(tmp_path: Path) -> None:
    repo, wt, branch = _make_cleanup_repo(tmp_path)
    (wt / "README.md").write_text("base\nlocal commit\n", encoding="utf-8")
    _git_ok(wt, "add", "README.md")
    _git_ok(wt, "-c", "user.email=t@example.com", "-c", "user.name=test", "commit", "-qm", "local work")

    D._cleanup_isolated_worktree(repo, wt, branch, "main", pushed=False)

    assert wt.exists()
    assert D._unpreserved_work_reason(wt, "main") == "unpushed-commits"


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


def test_rate_limit_and_timeout_events_are_canonical_routes(monkeypatch) -> None:
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc)
    monkeypatch.setattr(D, "_cascade_or_requeue", lambda _agent: "opencode")
    rate_limited = Task(
        id="RATE",
        title="rate limited",
        target_agent="codex",
        status="open",
        created=date(2026, 7, 10),
    )
    D._apply_result(rate_limited, "codex", D._RATELIMIT, now, BudgetTrack(date="2026-07-10"))
    assert rate_limited.status == "open"
    assert rate_limited.dispatch_log[-1].status == "open"
    assert rate_limited.dispatch_log[-1].route_to == "opencode"

    timed_out = Task(
        id="TIME",
        title="timed out",
        target_agent="codex",
        status="open",
        created=date(2026, 7, 10),
    )
    D._apply_result(timed_out, "codex", D._TIMEOUT, now, BudgetTrack(date="2026-07-10"))
    assert timed_out.status == "open"
    assert timed_out.dispatch_log[-1].status == "open"
    assert timed_out.dispatch_log[-1].route_to == "jules"
    assert D.agent_can_run_task("codex", timed_out) is False


def test_warp_auto_dispatch_sends_dynamic_profile_without_model_override(monkeypatch) -> None:
    captured: list[str] = []

    def fake_run(cmd, _task, _dry_run):
        captured.extend(cmd)
        return True

    monkeypatch.delenv("LIMEN_WARP_MODEL_OVERRIDE", raising=False)
    monkeypatch.setattr(D, "_run_cmd", fake_run)
    monkeypatch.setattr(D, "_claude_fable_acceptance_present", lambda: False)
    task = Task(
        id="WARP-AUTO",
        title="repair parser",
        repo="organvm/example",
        target_agent="warp",
        status="open",
        created=date(2026, 7, 10),
    )

    result = D._call_warp_oz("warp", task, False)

    assert result == "warp-oz:organvm/limen:limen-warp-oz.yml"
    assert any(arg.startswith("execution_profile={") for arg in captured)
    assert not any(arg.startswith("model=") for arg in captured)
    receipt = D._MODEL_SELECTION_RECEIPTS.pop(task.id)
    assert receipt["selection_source"] == "warp_auto"
    assert receipt["selected_model"] is None


def test_agent_argv_threads_task_into_dynamic_opencode_selector(monkeypatch) -> None:
    observed: list[Task | None] = []
    task = Task(
        id="OPENCODE-PROFILE",
        title="task evidence reaches the selector",
        target_agent="opencode",
        created=date(2026, 7, 10),
    )

    def select(current: Task | None = None) -> str:
        observed.append(current)
        return "fixture/runtime-output"

    monkeypatch.setattr(D, "_opencode_model", select)
    argv = D._agent_argv("opencode", task)

    assert observed == [task]
    assert argv == ["run", "-m", "fixture/runtime-output"]


def test_dispatch_event_records_dynamic_selection_receipt() -> None:
    import datetime

    task = Task(
        id="SELECTED",
        title="selected dynamically",
        target_agent="opencode",
        status="open",
        created=date(2026, 7, 10),
    )
    D._MODEL_SELECTION_RECEIPTS[task.id] = {
        "execution_profile": {"reasoning_depth": 0.7},
        "selected_model": "fixture/runtime-output",
        "selection_source": "opencode_live_catalog",
        "catalog_hash": "abc123",
    }

    D._apply_result(
        task,
        "opencode",
        True,
        datetime.datetime.now(datetime.timezone.utc),
        BudgetTrack(date="2026-07-10"),
    )

    event = task.dispatch_log[-1]
    assert event.status == "dispatched"
    assert event.selected_model == "fixture/runtime-output"
    assert event.selection_source == "opencode_live_catalog"
    assert event.catalog_hash == "abc123"


def test_pr_open_receipt_blocks_duplicate_dispatch_and_noop_demotion() -> None:
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc)
    task = Task(
        id="PR-OPEN",
        title="already has a PR",
        target_agent="opencode",
        status="open",
        created=date(2026, 6, 27),
        labels=[],
        dispatch_log=[
            DispatchLogEntry(
                timestamp=now,
                agent="agy",
                session_id="https://github.com/x/y/pull/99",
                status="pr_open",
                output="PR is open and green",
            )
        ],
    )

    assert D._dispatchable(task) is False

    task.status = "dispatched"
    D._apply_result(task, "opencode", D._NOOP, now, BudgetTrack(date="2026-06-27"))

    assert task.status == "dispatched"
    assert "noop" not in task.labels
    assert task.dispatch_log[-1].status == "dispatched"
    assert task.dispatch_log[-1].session_id == "result-lifecycle-guard"


def test_blocked_result_is_terminal_failed_blocked() -> None:
    import datetime

    task = Task(
        id="BLOCKED",
        title="blocked attempt",
        repo="organvm/missing",
        target_agent="codex",
        status="open",
        created=date(2026, 6, 27),
        labels=[],
    )
    track = BudgetTrack(date="2026-06-27")
    now = datetime.datetime.now(datetime.timezone.utc)

    D._apply_result(task, "codex", D._blocked_result("repo unavailable: organvm/missing"), now, track)

    assert task.status == "failed_blocked"
    assert task.target_agent == "codex"
    assert "blocked:routing" in task.labels
    assert track.spent == 0
    assert task.dispatch_log[-1].status == "failed_blocked"
    assert "repo unavailable" in str(task.dispatch_log[-1].output)


def test_dispatch_parallel_records_blocked_without_counting_failure(tmp_path: Path, monkeypatch, capsys) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "BLOCKED-PARALLEL",
                "title": "blocked parallel",
                "repo": "organvm/missing",
                "target_agent": "codex",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-20",
                "dispatch_log": [],
            }
        ],
    )
    monkeypatch.setattr(
        D,
        "call_agent_dispatch",
        lambda agent, task, dry_run=False: D._blocked_result("repo unavailable: organvm/missing"),
    )
    monkeypatch.setattr(D, "_worktree_debt_gate", lambda: (False, ""))

    dispatch_parallel(load_limen_file(tasks_path), tasks_path, agents=["codex"], per_agent_limit=1, max_workers=1)

    output = capsys.readouterr().out
    task = read_board(tasks_path)["tasks"][0]
    assert task["status"] == "failed_blocked"
    assert task["dispatch_log"][-1]["status"] == "failed_blocked"
    assert "1 blocked" in output
    assert "0 failed" in output


def test_failed_result_skips_down_lane_in_default_cascade(tmp_path: Path, monkeypatch) -> None:
    import datetime

    monkeypatch.delenv("LIMEN_DISPATCH_LANES", raising=False)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_OAUTH_PREFLIGHT", "0")
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "usage.json").write_text(
        json.dumps(
            {
                "vendors": {
                    "gemini": {"health": "exhausted"},
                    "jules": {"health": "ok"},
                }
            }
        )
    )

    def fake_select_lanes(selector, board=None, *, down_lanes=None):
        assert selector == "auto"
        assert "gemini" in set(down_lanes or ())
        return ["codex", "opencode", "agy", "claude", "jules"]

    monkeypatch.setattr(D, "select_lanes", fake_select_lanes)
    task = Task(
        id="CASCADE",
        title="cascade around down lane",
        target_agent="claude",
        status="open",
        created=date(2026, 6, 27),
        labels=[],
    )
    now = datetime.datetime.now(datetime.timezone.utc)

    D._apply_result(task, "claude", False, now, BudgetTrack(date="2026-06-27"))

    assert task.status == "open"
    assert task.target_agent == "jules"
    assert task.dispatch_log[-1].status == "open"
    assert task.dispatch_log[-1].route_to == "jules"
    assert "tried:claude" in task.labels


def test_remote_service_failure_skips_unarmed_ollama_floor(monkeypatch) -> None:
    import datetime

    monkeypatch.setattr(D, "_lane_cascade", lambda: ["jules", "ollama", "opencode"])
    monkeypatch.setattr(D, "local_floor_enabled", lambda: False)

    task = Task(
        id="REMOTE-FAIL",
        title="remote service failure",
        repo="organvm/limen",
        type="code",
        target_agent="jules",
        status="open",
        created=date(2026, 7, 9),
        labels=[],
    )
    now = datetime.datetime.now(datetime.timezone.utc)

    D._apply_result(task, "jules", False, now, BudgetTrack(date="2026-07-09"))

    assert task.status == "open"
    assert task.target_agent == "opencode"
    assert task.dispatch_log[-1].status == "open"
    assert task.dispatch_log[-1].route_to == "opencode"
    assert task.dispatch_log[-1].output == "remote/service lane failed; reopened to healthy fleet cascade"
    assert "tried:jules" in task.labels


def test_remote_service_failure_can_use_armed_matching_ollama_floor(monkeypatch) -> None:
    import datetime

    monkeypatch.setattr(D, "_lane_cascade", lambda: ["jules", "ollama", "opencode"])
    monkeypatch.setattr(D, "local_floor_enabled", lambda: True)
    monkeypatch.setattr(D, "local_floor_classes", lambda: {"scan"})
    monkeypatch.setattr(D, "ollama_model", lambda: "qwen3:8b")

    task = Task(
        id="REMOTE-FLOOR",
        title="remote service floor fallback",
        repo="organvm/limen",
        type="scan",
        target_agent="jules",
        status="open",
        created=date(2026, 7, 9),
        labels=[],
    )
    now = datetime.datetime.now(datetime.timezone.utc)

    D._apply_result(task, "jules", False, now, BudgetTrack(date="2026-07-09"))

    assert task.status == "open"
    assert task.target_agent == "ollama"
    assert task.dispatch_log[-1].status == "open"
    assert task.dispatch_log[-1].route_to == "ollama"
    assert "tried:jules" in task.labels


def test_agent_can_run_task_blocks_unarmed_ollama_code(monkeypatch) -> None:
    monkeypatch.setattr(D, "local_floor_enabled", lambda: False)

    task = Task(
        id="HEAL-rebase-org-repo-1",
        title="rebase/resolve conflicts",
        repo="organvm/example",
        type="code",
        target_agent="ollama",
        status="open",
        created=date(2026, 7, 9),
    )

    assert not D.agent_can_run_task("ollama", task)


def test_agent_can_run_task_allows_armed_ollama_floor_class(monkeypatch) -> None:
    monkeypatch.setattr(D, "local_floor_enabled", lambda: True)
    monkeypatch.setattr(D, "local_floor_classes", lambda: {"scan"})
    monkeypatch.setattr(D, "ollama_model", lambda: "qwen3:8b")

    task = Task(
        id="SCAN-org-repo-1",
        title="scan repository links",
        repo="organvm/example",
        type="scan",
        target_agent="ollama",
        status="open",
        created=date(2026, 7, 9),
    )

    assert D.agent_can_run_task("ollama", task)


def test_local_lanes_do_not_run_value_registry_promotion_tasks() -> None:
    task = Task(
        id="DISCOVER-organvm-example",
        title="Discover latent value",
        repo="organvm/example",
        type="research",
        target_agent="any",
        status="open",
        created=date(2026, 7, 9),
        context='append "organvm/example" to value-repos.json after writing DISCOVERY.md',
    )

    assert not D.agent_can_run_task("claude", task)
    assert not D.agent_can_run_task("codex", task)
    assert D.agent_can_run_task("jules", task)


def test_default_cascade_uses_reachable_auto_lanes(monkeypatch) -> None:
    import datetime

    monkeypatch.delenv("LIMEN_DISPATCH_LANES", raising=False)
    monkeypatch.setattr(D, "_down_lanes", lambda: {"codex", "gemini", "jules"})
    monkeypatch.setattr(
        D,
        "select_lanes",
        lambda selector, board=None, *, down_lanes=None: ["opencode", "agy", "claude"],
    )
    task = Task(
        id="NO-UNREACHABLE",
        title="do not fall to unreachable floor",
        target_agent="claude",
        status="open",
        created=date(2026, 6, 27),
        labels=[],
    )
    now = datetime.datetime.now(datetime.timezone.utc)

    D._apply_result(task, "claude", False, now, BudgetTrack(date="2026-06-27"))

    assert task.status == "failed"
    assert task.target_agent == "claude"
    assert task.dispatch_log[-1].status == "failed"
    assert "tried:claude" in task.labels


def test_agent_can_not_rerun_task_after_timeout_to_jules() -> None:
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc)
    task = Task(
        id="SLOW-CODEX",
        title="slow local task",
        repo="organvm/domus-genoma",
        target_agent="codex",
        status="open",
        created=date(2026, 7, 8),
        labels=["slow"],
        dispatch_log=[
            DispatchLogEntry(
                timestamp=now,
                agent="codex",
                session_id="cli",
                status="timeout->jules",
            )
        ],
    )

    assert not D.agent_can_run_task("codex", task)
    assert D.agent_can_run_task("jules", task)


def test_late_result_does_not_reopen_already_done_task() -> None:
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc)
    task = Task(
        id="DONE-LATE",
        title="already done",
        target_agent="opencode",
        status="done",
        created=date(2026, 6, 27),
        labels=[],
        dispatch_log=[
            DispatchLogEntry(
                timestamp=now,
                agent="opencode",
                session_id="cli",
                status="done",
                output="completed before async worker result arrived",
            )
        ],
    )
    track = BudgetTrack(date="2026-06-27")

    D._apply_result(task, "opencode", D._NOOP, now, track)

    assert task.status == "done"
    assert "noop" not in task.labels
    assert task.dispatch_log[-1].status == "done"
    assert track.spent == 0


def test_isolated_local_run_blocks_unavailable_repo_without_cascading(monkeypatch) -> None:
    task = Task(
        id="MISSING-REPO",
        title="missing repo",
        repo="organvm/missing",
        target_agent="codex",
        created=date(2026, 6, 27),
    )
    monkeypatch.setattr(D, "_resolve_agent_binary", lambda agent: agent)
    monkeypatch.setattr(D, "_resolve_repo_dir", lambda task: None)
    monkeypatch.setattr(D, "_repo_unavailable_reason", lambda repo: "repo unavailable: organvm/missing")
    monkeypatch.setattr(D, "_clone_repo", lambda task: pytest.fail("unavailable repo should not clone"))

    result = D._isolated_local_run("codex", task, dry_run=False)

    assert D._is_blocked_result(result)
    assert "organvm/missing" in D._blocked_reason(result)


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

    release_stale_tasks(
        load_limen_file(tasks_path),
        tasks_path,
        hours=24,
        dry_run=True,
        jules_snapshot=JulesRemoteSnapshot(available=False, sessions={}),
    )

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
                "target_agent": "codex",
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

    report = release_stale_tasks(
        load_limen_file(tasks_path),
        tasks_path,
        hours=24,
        dry_run=True,
        agent="jules",
        jules_snapshot=JulesRemoteSnapshot(available=False, sessions={}),
    )

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


# ── Marginal worktree-impact classification (binary, census-derived locality) ──


def _wtask(labels=None, agent="codex", repo="x/y", workstream=None) -> Task:
    return Task(
        id="WT-CLASSIFY",
        title="t",
        repo=repo,
        target_agent=agent,
        status="open",
        created=date(2026, 7, 12),
        labels=labels or [],
        workstream=workstream,
    )


def test_classify_impact_local_checkout_lane_is_debt_creating() -> None:
    # EVERY local-checkout lane creates a worktree — labels are irrelevant. Locality authority is
    # census LOCAL_CHECKOUT_AGENTS.
    for lane in sorted(D.LOCAL_CHECKOUT_AGENTS):
        assert D._classify_worktree_impact(_wtask(["generated", "build-out"]), lane) == D.IMPACT_DEBT_CREATING
        assert D._classify_worktree_impact(_wtask(["reclaim", "cleanup", "receipt"]), lane) == D.IMPACT_DEBT_CREATING
        assert D._classify_worktree_impact(_wtask([]), lane) == D.IMPACT_DEBT_CREATING


def test_classify_impact_non_local_lane_is_remote() -> None:
    for lane in ("jules", "github_actions", "warp", "oz", "copilot"):
        assert lane not in D.LOCAL_CHECKOUT_AGENTS
        assert D._classify_worktree_impact(_wtask(["generated", "build-out"]), lane) == D.IMPACT_REMOTE


def test_classify_impact_locality_is_census_not_hardcoded(monkeypatch) -> None:
    # An arbitrary/renamed agent gains locality purely from the census set — no hand-kept lane table.
    renamed = "codex_ng_20260712"
    assert D._classify_worktree_impact(_wtask([], agent=renamed), renamed) == D.IMPACT_REMOTE
    monkeypatch.setattr(D, "LOCAL_CHECKOUT_AGENTS", frozenset(D.LOCAL_CHECKOUT_AGENTS) | {renamed})
    assert D._classify_worktree_impact(_wtask([], agent=renamed), renamed) == D.IMPACT_DEBT_CREATING


def test_tracked_head_checkout_estimate_uses_live_block_allocation_and_tree_structure(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    _init_test_git_repo(repo)
    task = _wtask(repo=str(repo))
    monkeypatch.setattr(D, "_filesystem_block_size", lambda _path: 4096)

    # One rounded blob block + root directory + tracked dirent + .git control-file blocks.
    assert D._tracked_head_checkout_gib(task) == (4 * 4096) / (1024**3)


def test_tracked_head_checkout_estimate_unknown_without_local_repo() -> None:
    assert D._tracked_head_checkout_gib(_wtask(repo="not-present/example")) is None


def test_missing_checkout_requirement_uses_live_remote_repository_and_tree_bytes(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_capture(cmd, **_kwargs):
        calls.append(cmd)
        if cmd[-1] == "repos/not-present/example":
            payload = {"default_branch": "trunk", "size": 2048}
        else:
            payload = {
                "truncated": False,
                "tree": [
                    {"type": "tree", "path": "src"},
                    {"type": "blob", "path": "README.md", "size": 1024},
                    {"type": "blob", "path": "src/app.py", "size": 3072},
                ],
            }
        return subprocess.CompletedProcess(cmd, 0, json.dumps(payload), "")

    monkeypatch.setattr(D, "_resolve_repo_dir", lambda _task: None)
    monkeypatch.setattr(D, "_clone_cache_root", lambda: Path("/scratch/.worktrees-repo-cache"))
    monkeypatch.setattr(D, "_filesystem_block_size", lambda _path: 4096)
    monkeypatch.setattr(D, "_filesystem_device", lambda _path: 2)
    monkeypatch.setattr(D, "_run_capture", fake_capture)

    task = _wtask(repo="not-present/example")
    checkout_bytes = 7 * 4096
    repository_bytes = 2048 * 1024 + 4 * 4096
    expected = (repository_bytes + checkout_bytes) / (1024**3)
    assert D._local_admission_requirement_gib(task) == expected
    assert calls == [
        ["gh", "api", "repos/not-present/example"],
        ["gh", "api", "repos/not-present/example/git/trees/trunk?recursive=1"],
    ]


@pytest.mark.parametrize(
    "tree_payload",
    [
        {"truncated": True, "tree": []},
        {"truncated": False, "tree": [{"type": "blob", "path": "bad"}]},
    ],
)
def test_missing_checkout_requirement_fails_closed_on_inexact_remote_tree(monkeypatch, tree_payload) -> None:
    responses = iter(
        [
            {"default_branch": "main", "size": 1},
            tree_payload,
        ]
    )
    monkeypatch.setattr(D, "_resolve_repo_dir", lambda _task: None)
    monkeypatch.setattr(D, "_clone_cache_root", lambda: Path("/scratch/.worktrees-repo-cache"))
    monkeypatch.setattr(D, "_filesystem_block_size", lambda _path: 4096)
    monkeypatch.setattr(D, "_filesystem_device", lambda _path: 2)
    monkeypatch.setattr(
        D,
        "_run_capture",
        lambda cmd, **_kwargs: subprocess.CompletedProcess(cmd, 0, json.dumps(next(responses)), ""),
    )
    assert D._local_admission_requirement_gib(_wtask(repo="not-present/example")) is None


def test_missing_checkout_is_measured_reserved_hydrated_then_isolated(tmp_path: Path, monkeypatch) -> None:
    workdir = tmp_path / "workspace"
    isolation_root = tmp_path / "worktrees"
    task = _wtask(repo="not-present/example")
    clone_calls: list[list[str]] = []
    plumbing_calls: list[list[str]] = []
    born: list[Path] = []
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path / "limen"))
    monkeypatch.setenv("LIMEN_WORKDIR", str(workdir))
    clone_cache = tmp_path / ".worktrees-repo-cache"
    monkeypatch.setattr(D, "_clone_cache_root", lambda: clone_cache)
    monkeypatch.setattr(D, "_remote_hydration_requirement_gib", lambda _task: 0.5)
    monkeypatch.setattr(D, "_repo_unavailable_reason", lambda _repo: None)
    monkeypatch.setattr(D, "_resolve_agent_binary", lambda agent: agent)
    monkeypatch.setattr(D, "_default_branch", lambda _repo: "main")
    monkeypatch.setattr(D, "_same_repo_pr_head_for_task", lambda _task: None)
    monkeypatch.setattr(D, "_isolation_root", lambda: isolation_root)
    monkeypatch.setattr(D.secrets, "token_hex", lambda _n: "abcd1234")

    def fake_capture(cmd, **_kwargs):
        clone_calls.append(cmd)
        dest = Path(cmd[-1])
        (dest / ".git").mkdir(parents=True)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def fake_plumbing(args, _repo, timeout=120):
        plumbing_calls.append(args)
        if args[:2] == ["worktree", "add"]:
            Path(args[4]).mkdir(parents=True)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(D, "_run_capture", fake_capture)
    monkeypatch.setattr(D, "_git_plumbing", fake_plumbing)
    monkeypatch.setattr(D, "_record_worktree_birth", lambda _task, wt, *_a, **_k: born.append(wt))
    monkeypatch.setattr(
        D,
        "_git",
        lambda args, _cwd, timeout=120: subprocess.CompletedProcess(args, 0, "base-head\n", ""),
    )
    monkeypatch.setattr(D, "_run_isolated_agent", lambda *_a, **_k: True)
    monkeypatch.setattr(D, "_commit_isolated_changes", lambda *_a, **_k: D._NOOP)
    monkeypatch.setattr(D, "_cleanup_isolated_worktree", lambda *_a, **_k: None)

    snapshot = D.WorktreeAdmissionSnapshot(
        active=True,
        block_new_local=False,
        reason="",
        resource_blocked=False,
        vitals_shed=False,
        reaper_blocked=False,
        free_gib=60.5,
        floor_gib=60.0,
        reserved_gib=0.0,
        room_gib=0.5,
        targets_present=False,
        debt=0,
        vitals_action="ok",
    )
    with D._machine_admission_lock():
        blocked, reason = D._worktree_admission_for_task(task, "codex", snapshot, reserve=True, machine_lease=True)
    assert not blocked, reason
    assert D._admission_lease_path(task.id).exists()

    try:
        assert D._isolated_local_run("codex", task, dry_run=False) == D._NOOP
        expected_clone = clone_cache / D._clone_cache_key(task.repo)
        assert clone_calls == [["gh", "repo", "clone", "not-present/example", str(expected_clone)]]
        assert any(call[:2] == ["worktree", "add"] for call in plumbing_calls)
        assert born == [isolation_root / "wt-classify-abcd1234"]
        payload = json.loads(D._admission_lease_path(task.id).read_text())
        assert payload["phase"] == "worktree-born"
        assert payload["reserved_gib"] == 0.0
    finally:
        D._release_machine_admission(task.id)


def test_allocation_estimate_is_positive_for_empty_zero_and_tiny_trees() -> None:
    block = 16_384
    assert D._tracked_tree_allocation_bytes([], block) == 2 * block
    assert D._tracked_tree_allocation_bytes([("empty", "blob", 0)], block) == 4 * block
    assert D._tracked_tree_allocation_bytes([("src/tiny", "blob", 1)], block) == 5 * block


def test_clone_cache_stays_on_worktree_device_not_workdir_device(tmp_path: Path, monkeypatch) -> None:
    scratch = tmp_path / "scratch"
    worktrees = scratch / "worktrees"
    internal = tmp_path / "internal" / "Workspace"
    scratch.mkdir()
    internal.mkdir(parents=True)
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(worktrees))
    monkeypatch.setenv("LIMEN_WORKDIR", str(internal))

    monkeypatch.setattr(D, "dispatch_clone_cache_root", lambda: scratch / ".worktrees-repo-cache")
    clone_calls: list[list[str]] = []

    def fake_capture(cmd, **_kwargs):
        clone_calls.append(cmd)
        (Path(cmd[-1]) / ".git").mkdir(parents=True)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(D, "_run_capture", fake_capture)
    task = _wtask(repo="not-present/example")
    repo = D._clone_repo(task)

    expected = scratch / ".worktrees-repo-cache" / D._clone_cache_key(task.repo)
    assert repo == expected
    assert clone_calls == [["gh", "repo", "clone", task.repo, str(expected)]]
    assert not str(repo).startswith(str(internal))


def test_clone_cache_fails_closed_when_parent_is_a_different_device(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "mount" / "worktrees"
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(root))
    monkeypatch.setattr(D, "dispatch_clone_cache_root", lambda: None)
    assert D._clone_cache_root() is None


def test_clone_cache_keys_are_flat_and_collision_safe() -> None:
    first = D._clone_cache_key("owner-a/repo")
    second = D._clone_cache_key("owner/a--repo")
    assert "/" not in first
    assert "/" not in second
    assert first != second


def test_parallel_multi_lane_reserves_shared_checkout_room_only_when_selected(monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_VALUE_GATE", "0")
    board = LimenFile.model_validate(
        {
            "portal": {
                "budget": {
                    "daily": 10,
                    "per_agent": {"codex": 10, "claude": 10},
                    "track": {"date": "", "spent": 0, "per_agent": {}},
                }
            },
            "tasks": [
                {
                    "id": "FIRST-SMALL",
                    "title": "first small local checkout",
                    "repo": "someorg/first",
                    "target_agent": "any",
                    "priority": "critical",
                    "status": "open",
                    "created": "2026-07-12",
                },
                {
                    "id": "SECOND-OVER-ROOM",
                    "title": "second local checkout",
                    "repo": "someorg/second",
                    "target_agent": "any",
                    "priority": "high",
                    "status": "open",
                    "created": "2026-07-12",
                },
            ],
        }
    )
    snapshot = D.WorktreeAdmissionSnapshot(
        active=True,
        block_new_local=False,
        reason="",
        resource_blocked=False,
        vitals_shed=False,
        reaper_blocked=False,
        free_gib=61.5,
        floor_gib=60.0,
        reserved_gib=0.0,
        room_gib=1.5,
        targets_present=False,
        debt=0,
        vitals_action="ok",
    )
    estimates = {"FIRST-SMALL": 1.0, "SECOND-OVER-ROOM": 0.6}
    monkeypatch.setattr(D, "_tracked_head_checkout_gib", lambda task: estimates[task.id])

    picked = D._select_parallel_reservations(
        board,
        ["codex", "claude"],
        1,
        datetime.now(timezone.utc),
        dry_run=False,
        admission_snapshot=snapshot,
    )

    assert picked == [("codex", "FIRST-SMALL")]
    assert snapshot["reserved_gib"] == 1.0
    assert snapshot["room_gib"] == 0.5


@pytest.mark.parametrize(
    "marker_body",
    [
        "{malformed",
        json.dumps({"task_id": "LEGACY-LOCAL"}),
        json.dumps({"agent": "jules", "task_id": "LEGACY-LOCAL"}),
    ],
)
def test_local_running_marker_with_unknown_reservation_fails_closed(
    tmp_path: Path,
    monkeypatch,
    marker_body: str,
) -> None:
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    run_dir = tmp_path / "logs" / "async-runs"
    run_dir.mkdir(parents=True)
    (run_dir / "LEGACY-LOCAL__codex.running").write_text(marker_body, encoding="utf-8")

    slots, reserved_gib = D._running_local_marker_state()

    assert slots == 1
    assert reserved_gib == float("inf")


def test_remote_parallel_batch_starts_outside_saturated_local_executor() -> None:
    local_release = threading.Event()
    remote_started = threading.Event()
    finished = threading.Event()
    results: list[tuple[str, str, bool | str]] = []

    def run_one(item: tuple[str, str]) -> tuple[str, str, bool | str]:
        agent, task_id = item
        if agent == "codex":
            assert local_release.wait(timeout=2), "test did not release the local worker"
        else:
            remote_started.set()
        return agent, task_id, True

    def run_batch() -> None:
        results.extend(
            D._run_parallel_batch(
                [("codex", "LOCAL"), ("jules", "REMOTE")],
                run_one,
                max_local_workers=1,
            )
        )
        finished.set()

    thread = threading.Thread(target=run_batch)
    thread.start()
    try:
        assert remote_started.wait(timeout=1), "remote task queued behind the occupied local worker"
    finally:
        local_release.set()
        thread.join(timeout=3)

    assert finished.is_set()
    assert results == [("codex", "LOCAL", True), ("jules", "REMOTE", True)]


# ── Narrow agent_can_run_task safety (replaces the blanket repo bans) ───────


def _limen_task(**kw) -> Task:
    base = dict(
        id="HEAL-cifix-organvm-limen-1",
        title="Fix Limen CI",
        repo="organvm/limen",
        target_agent="any",
        status="open",
        created=date(2026, 7, 12),
    )
    base.update(kw)
    return Task(**base)


@pytest.mark.parametrize(
    "repo",
    [
        "organvm/limen",
        "organvm/limen/",
        "ORGANVM/LIMEN.git",
        "github.com/OrganVM/Limen.git",
        "https://github.com/ORGANVM/LIMEN.git",
        "https://github.com/organvm/limen/",
        "ssh://git@github.com/OrganVM/Limen.git",
        "SSH://GIT@GitHub.com/OrganVM/Limen.git",
        "git@github.com:OrganVM/Limen.git",
    ],
)
def test_limen_repo_identity_accepts_supported_github_forms(repo: str) -> None:
    assert D._github_repo_identity(repo) == "organvm/limen"
    assert D._limen_repo_task(_limen_task(repo=repo))


@pytest.mark.parametrize(
    "repo",
    [
        "",
        "limen",
        "organvm/limen/extra",
        "github.com/organvm/limen/extra",
        "https://github.com/organvm/limen/issues",
        "https://github.com//organvm/limen",
        "https://github.com/organvm/limen?tab=readme",
        "https://github.com.evil.example/organvm/limen",
        "https://gitlab.com/organvm/limen",
        "git@gitlab.com:organvm/limen.git",
        "ssh://root@github.com/organvm/limen.git",
    ],
)
def test_github_repo_identity_rejects_ambiguous_or_non_github_forms(repo: str) -> None:
    assert D._github_repo_identity(repo) is None
    assert not D._limen_repo_task(_limen_task(repo=repo))


def test_organvm_engine_repo_identity_accepts_url_form() -> None:
    task = Task(
        id="ENGINE-URL",
        title="Engine URL",
        repo="SSH://git@GitHub.com/OrganVM/OrganVM-Engine.git",
        target_agent="any",
        status="open",
        created=date(2026, 7, 12),
    )
    assert D._organvm_engine_task(task)


def _init_test_git_repo(path: Path, *, origin: str | None = None) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "limen-test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Limen Test"], check=True)
    (path / "README.md").write_text("limen\n")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "init"], check=True)
    if origin:
        subprocess.run(["git", "-C", str(path), "remote", "add", "origin", origin], check=True)


def _assert_local_limen_repo_guard(repo: str) -> None:
    broad = _limen_task(
        repo=repo,
        predicate="scripts/verify-whole.sh",
        receipt_target="organvm/limen#local-broad",
    )
    narrow = _limen_task(
        repo=repo,
        predicate="python -m pytest cli/tests/test_dispatch.py -q",
        receipt_target="organvm/limen#local-narrow",
    )
    assert D._limen_repo_task(broad)
    assert not D.agent_can_run_task("codex", broad)
    assert D.agent_can_run_task("codex", narrow)


def test_limen_local_absolute_tilde_and_relative_paths_keep_self_repo_guard(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    root = home / "Workspace" / "limen"
    _init_test_git_repo(root)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    monkeypatch.setenv("LIMEN_ISOLATION", "worktree")

    _assert_local_limen_repo_guard(str(root))
    _assert_local_limen_repo_guard("~/Workspace/limen")
    monkeypatch.chdir(root)
    _assert_local_limen_repo_guard(".")


def test_registered_limen_worktree_path_keeps_self_repo_guard(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "limen"
    worktree = tmp_path / "limen-isolated-worktree"
    _init_test_git_repo(root)
    subprocess.run(
        ["git", "-C", str(root), "worktree", "add", "-q", "-b", "test-isolated", str(worktree)],
        check=True,
    )
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    monkeypatch.setenv("LIMEN_ISOLATION", "worktree")

    _assert_local_limen_repo_guard(str(worktree))


def test_local_origin_slug_keeps_self_repo_guard(tmp_path: Path, monkeypatch) -> None:
    checkout = tmp_path / "renamed-checkout"
    _init_test_git_repo(checkout, origin="git@github.com:OrganVM/Limen.git")
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path / "unrelated-live-root"))
    monkeypatch.setenv("LIMEN_ISOLATION", "worktree")

    _assert_local_limen_repo_guard(str(checkout))


@pytest.mark.parametrize(
    "predicate",
    [
        "python -m pytest cli/tests/test_dispatch.py -q",
        "pytest cli/tests/test_dispatch.py::test_narrow_safe_limen_task_allowed_for_local_lanes",
        "scripts/verify.py --changed",
        "scripts/verify-scoped.sh cli/src/limen/dispatch.py",
        "pytest cli/tests/test_dispatch.py -q && rg -n dispatch cli/src/limen/dispatch.py",
        "scripts/verify.py --changed; pytest cli/tests/test_dispatch.py",
        "bash -lc 'python -m pytest cli/tests/test_dispatch.py -q'",
        'python -m pytest cli/tests/test_dispatch.py -q && test "$(gh pr list --json number --jq length)" -gt 0',
    ],
)
def test_narrow_verification_accepts_independently_scoped_commands(predicate: str) -> None:
    assert D._is_narrow_verification(predicate)


@pytest.mark.parametrize(
    "predicate",
    [
        "",
        "scripts/verify-whole.sh",
        "scripts/verify-whole.sh; echo --changed",
        "scripts/verify.py",
        "scripts/verify.py && echo --changed",
        "scripts/verify.py --changed --full",
        "scripts/verify.py --changed --full=true",
        "python -m pytest",
        "python -m pytest; echo cli/tests/fake.py",
        "pytest cli/tests",
        "pytest $(echo cli/tests/test_dispatch.py)",
        "scripts/verify.py --changed $EXTRA_ARGS",
        "pytest `echo cli/tests/test_dispatch.py`",
        "eval 'pytest cli/tests/test_dispatch.py'",
        "bash -c 'python -m pytest'",
        "sh -lc 'python -m pytest; echo cli/tests/fake.py'",
        "bash -lc 'scripts/verify.py && echo --changed'",
        "bash -lc 'pytest cli/tests/test_dispatch.py && scripts/verify-whole.sh'",
        "bash -lc 'scripts/verify.py --changed --full'",
        "bash -lc 'test \"$(python -m pytest cli/tests/test_dispatch.py)\" -eq 0'",
        "bash -lc 'test \"$(scripts/verify.py --changed)\" = ok'",
        'pytest cli/tests/test_dispatch.py "$(gh pr view --json body --jq .body)"',
        "pytest cli/tests/test_dispatch.py && scripts/verify-whole.sh",
        "pytest cli/tests/test_dispatch.py\necho scripts/verify-whole.sh",
    ],
)
def test_narrow_verification_rejects_broad_or_shell_bypass(predicate: str) -> None:
    assert not D._is_narrow_verification(predicate)


@pytest.mark.parametrize(
    "predicate",
    [
        "python -c 'import pytest; raise SystemExit(pytest.main())'",
        "make test",
        "scripts/check-everything.sh",
        "nox -s tests",
        "tox",
        "npm test",
        "pnpm test",
        "yarn test",
        "bun test",
        "gh pr list --repo organvm/limen",
        "pytest cli/tests/test_dispatch.py && scripts/check-everything.sh",
    ],
)
def test_narrow_verification_fails_closed_for_unknown_or_receipt_only_commands(predicate: str) -> None:
    assert not D._is_narrow_verification(predicate)


@pytest.mark.parametrize(
    "predicate",
    [
        "pytest --ignore cli/tests/test_dispatch.py",
        "pytest --confcutdir cli/tests/test_dispatch.py",
        "pytest --basetemp cli/tests/test_dispatch.py",
        "pytest -c cli/tests/test_dispatch.py",
        "pytest -p cli/tests/test_dispatch.py",
        "python -m pytest --ignore cli/tests/test_dispatch.py",
        "python3 -m pytest --confcutdir cli/tests/test_dispatch.py",
        "pytest --ignore=cli/tests/test_dispatch.py",
        "pytest cli/tests/test_dispatch.py tests",
        "pytest --unknown-option cli/tests/test_dispatch.py",
    ],
)
def test_pytest_option_values_cannot_launder_a_collection_target(predicate: str) -> None:
    assert not D._is_narrow_verification(predicate)


@pytest.mark.parametrize(
    "predicate",
    [
        "pytest -q cli/tests/test_dispatch.py",
        "pytest cli/tests/test_dispatch.py -q",
        "python -m pytest -k narrow cli/tests/test_dispatch.py",
        "python3 -m pytest cli/tests/test_dispatch.py -k narrow",
        "pytest --ignore cli/tests/test_other.py cli/tests/test_dispatch.py",
        "pytest --ignore=cli/tests/test_other.py cli/tests/test_dispatch.py",
        "pytest -- cli/tests/test_dispatch.py::test_narrow_safe_limen_task_allowed_for_local_lanes",
    ],
)
def test_pytest_explicit_targets_survive_known_options_before_and_after(predicate: str) -> None:
    assert D._is_narrow_verification(predicate)


@pytest.mark.parametrize(
    "predicate",
    [
        "pytest --collect-only cli/tests/test_dispatch.py",
        "pytest --fixtures cli/tests/test_dispatch.py",
        "pytest --setup-plan cli/tests/test_dispatch.py",
        "pytest --version cli/tests/test_dispatch.py",
        "pytest --pyargs cli/tests/test_dispatch.py",
    ],
)
def test_pytest_non_executing_modes_are_not_execution_proof(predicate: str) -> None:
    assert not D._is_narrow_verification(predicate)


@pytest.mark.parametrize(
    "predicate",
    [
        "pytest cli/tests/*.py",
        "bash -lc 'pytest cli/tests/*.py'",
        "pytest 'cli/tests/*.py'",
        "pytest cli/tests/test_?.py",
        "pytest cli/tests/test_[ad]*.py",
        "pytest cli/tests/{test_dispatch,test_worktree_debt}.py",
        "pytest cli/tests/**/test_*.py",
        "pytest cli/tests/test_dispatch.py::test_*",
        "pytest @cli/tests/test_dispatch.py",
    ],
)
def test_pytest_collection_targets_reject_indirect_or_runtime_expanding_scope(predicate: str) -> None:
    assert not D._is_narrow_verification(predicate)


@pytest.mark.parametrize(
    "predicate",
    [
        "pytest cli/tests/test_dispatch.py",
        "pytest cli/tests/test_dispatch.py::test_narrow_safe_limen_task_allowed_for_local_lanes",
        "bash -lc 'pytest cli/tests/test_dispatch.py'",
        "bash -lc 'pytest cli/tests/test_dispatch.py::test_narrow_safe_limen_task_allowed_for_local_lanes'",
    ],
)
def test_pytest_literal_file_and_node_targets_remain_narrow(predicate: str) -> None:
    assert D._is_narrow_verification(predicate)


@pytest.mark.parametrize(
    "predicate",
    [
        "evil-verify-scoped-whole.sh",
        "verify-scoped-not-really cli/tests/test_dispatch.py",
        "python evil-verify-scoped.py",
        "/tmp/verify-scoped.sh cli/tests/test_dispatch.py",
        "python /tmp/verify.py --changed",
        "pytest cli/tests/test_dispatch.py && evil-verify-scoped-whole.sh",
    ],
)
def test_only_exact_verify_scoped_wrapper_is_recognized(predicate: str) -> None:
    assert not D._is_narrow_verification(predicate)


@pytest.mark.parametrize(
    "predicate",
    [
        "scripts/verify-scoped.sh",
        "./scripts/verify-scoped.sh",
        "scripts/verify.py --changed",
        "python ./scripts/verify.py --changed",
    ],
)
def test_only_canonical_repo_verifier_scripts_are_recognized(predicate: str) -> None:
    assert D._is_narrow_verification(predicate)


@pytest.mark.parametrize(
    "predicate",
    [
        "pytest cli/tests/test_dispatch.py && git branch --show-current",
        "pytest cli/tests/test_dispatch.py && git branch --list",
        "pytest cli/tests/test_dispatch.py && git remote -v",
        "pytest cli/tests/test_dispatch.py && git remote get-url origin",
        "pytest cli/tests/test_dispatch.py && git remote show -n origin",
        "pytest cli/tests/test_dispatch.py && git symbolic-ref HEAD",
        "pytest cli/tests/test_dispatch.py && git symbolic-ref --short HEAD",
        "pytest cli/tests/test_dispatch.py && git diff --exit-code",
        "pytest cli/tests/test_dispatch.py && git show --no-patch HEAD",
    ],
)
def test_git_receipt_controls_are_read_only(predicate: str) -> None:
    assert D._is_narrow_verification(predicate)


@pytest.mark.parametrize(
    "predicate",
    [
        "pytest cli/tests/test_dispatch.py && git branch -D old-branch",
        "pytest cli/tests/test_dispatch.py && git remote remove origin",
        "pytest cli/tests/test_dispatch.py && git symbolic-ref HEAD refs/heads/newref",
        "pytest cli/tests/test_dispatch.py && git diff --output=/Users/4jp/Workspace/limen/tasks.yaml",
        "pytest cli/tests/test_dispatch.py && git show --output=/Users/4jp/Workspace/limen/tasks.yaml HEAD",
        "pytest cli/tests/test_dispatch.py && git log --paginate",
        "pytest cli/tests/test_dispatch.py && git grep --open-files-in-pager=less pattern",
    ],
)
def test_mutating_git_receipt_commands_are_denied(predicate: str) -> None:
    assert not D._is_narrow_verification(predicate)


@pytest.mark.parametrize(
    "predicate",
    [
        "pytest cli/tests/test_dispatch.py && true > victim",
        "pytest cli/tests/test_dispatch.py && true >> victim",
        "pytest cli/tests/test_dispatch.py && true < victim",
        "pytest cli/tests/test_dispatch.py && true 2> victim",
        "pytest cli/tests/test_dispatch.py && true 2>> victim",
        "pytest cli/tests/test_dispatch.py && true <<EOF",
        "pytest cli/tests/test_dispatch.py && true <<< value",
    ],
)
def test_unquoted_shell_redirections_are_denied(predicate: str) -> None:
    assert not D._is_narrow_verification(predicate)


@pytest.mark.parametrize(
    "predicate",
    [
        'pytest cli/tests/test_dispatch.py && test "3 > 2" = "3 > 2"',
        'pytest cli/tests/test_dispatch.py && test "<" = "<"',
    ],
)
def test_quoted_comparison_characters_remain_receipt_data(predicate: str) -> None:
    assert D._is_narrow_verification(predicate)


@pytest.mark.parametrize(
    "predicate",
    [
        "pytest cli/tests/test_dispatch.py && gh pr list --repo organvm/limen",
        "scripts/verify.py --changed && git diff --exit-code",
        "scripts/verify-scoped.sh && true",
    ],
)
def test_narrow_verifier_plus_read_only_receipt_is_authoritative(predicate: str) -> None:
    assert D._is_narrow_verification(predicate)


def test_broad_limen_task_still_banned_for_local_lanes_allowed_remote() -> None:
    task = _limen_task()  # no predicate/receipt → broad, no isolation contract
    assert not D.agent_can_run_task("codex", task)
    assert not D.agent_can_run_task("claude", task)
    assert not D.agent_can_run_task("agy", task)
    assert D.agent_can_run_task("jules", task)  # remote runs off-box, never gated here


def test_narrow_safe_limen_task_allowed_for_local_lanes() -> None:
    task = _limen_task(
        id="FIX-limen-scoped-1",
        predicate="python -m pytest cli/tests/test_dispatch.py -q",
        receipt_target="organvm/limen#123",
    )
    assert D.agent_can_run_task("codex", task)
    assert D.agent_can_run_task("claude", task)
    assert D.agent_can_run_task("agy", task)


_CANONICAL_DYNAMIC_ADMISSION_PREDICATE = r"""bash -lc 'python3 -m pytest cli/tests/test_dispatch.py cli/tests/test_worktree_debt.py -q && test "$(gh pr list --repo organvm/limen --state merged --search "FIX-dynamic-worktree-admission-0712 in:body" --json body --jq "([.[] | select((.body // "") | test("(^|[^A-Za-z0-9_.-])FIX\-dynamic\-worktree\-admission\-0712([^A-Za-z0-9_.-]|$)"))] | length)")" -gt 0' """.strip()


def test_canonical_dynamic_admission_predicate_allows_every_local_lane(monkeypatch) -> None:
    task = _limen_task(
        id="FIX-dynamic-worktree-admission-0712",
        predicate=_CANONICAL_DYNAMIC_ADMISSION_PREDICATE,
        receipt_target="github:organvm/limen:pull-request:FIX-dynamic-worktree-admission-0712",
    )
    # Ollama's separate task-class floor is irrelevant to this isolation-contract regression.
    monkeypatch.setattr(D, "_local_floor_allowed_for_task", lambda _task: True)

    assert D._is_narrow_verification(task.predicate)
    for lane in sorted(D.LOCAL_CHECKOUT_AGENTS):
        assert D.agent_can_run_task(lane, task), lane


def test_broad_verification_limen_task_denied_even_with_receipt() -> None:
    task = _limen_task(
        id="FIX-limen-broad-1",
        predicate="scripts/verify-whole.sh",  # whole-world gate → off the isolation contract
        receipt_target="organvm/limen#124",
    )
    assert not D.agent_can_run_task("codex", task)
    assert not D.agent_can_run_task("claude", task)


def test_limen_task_missing_receipt_denied() -> None:
    task = _limen_task(id="FIX-limen-noreceipt", predicate="python -m pytest cli/tests/test_x.py -q")
    assert not D.agent_can_run_task("codex", task)


def test_organvm_engine_narrow_scope_preserved_for_codex() -> None:
    # organvm-engine's ban was Claude-only; codex was always allowed and still is.
    task = Task(
        id="HEAL-cifix-organvm-engine-1",
        title="Fix engine CI",
        repo="organvm/organvm-engine",
        target_agent="any",
        status="open",
        created=date(2026, 7, 12),
    )
    assert not D.agent_can_run_task("claude", task)
    assert D.agent_can_run_task("codex", task)
    # With the isolation contract, claude is admitted too.
    safe = Task(
        id="FIX-engine-scoped-1",
        title="Fix engine",
        repo="organvm/organvm-engine",
        target_agent="any",
        status="open",
        created=date(2026, 7, 12),
        predicate="python -m pytest tests/test_a.py::test_b",
        receipt_target="organvm/organvm-engine#9",
    )
    assert D.agent_can_run_task("claude", safe)


def test_agy_live_root_registry_hazard_preserved_even_with_contract() -> None:
    # The truly task-specific Agy hazard is NOT a repo ban and survives the narrowing.
    task = Task(
        id="DISCOVER-organvm-example",
        title="Discover latent value",
        repo="organvm/example",
        type="research",
        target_agent="any",
        status="open",
        created=date(2026, 7, 12),
        context='append "organvm/example" to value-repos.json after writing DISCOVERY.md',
        predicate="python -m pytest cli/tests/test_x.py -q",
        receipt_target="organvm/example#1",
    )
    assert not D.agent_can_run_task("agy", task)


def test_isolated_safe_task_denied_when_isolation_off(monkeypatch) -> None:
    # LIMEN_ISOLATION=off runs in-place (touches the live tree) → never safe for a self-modifying repo,
    # even with a full typed predicate + receipt + narrow verification.
    task = _limen_task(
        id="FIX-limen-offisolation",
        predicate="python -m pytest cli/tests/test_dispatch.py -q",
        receipt_target="organvm/limen#125",
    )
    assert D.agent_can_run_task("codex", task)  # isolation on (default) → allowed
    monkeypatch.setenv("LIMEN_ISOLATION", "off")
    assert not D.agent_can_run_task("codex", task)
    assert not D.agent_can_run_task("claude", task)


def test_local_runtime_uses_same_worktree_isolation_authority(tmp_path: Path, monkeypatch) -> None:
    task = _wtask(repo="example/repo")
    monkeypatch.setattr(D, "_isolated_local_run", lambda *_args: "isolated")
    monkeypatch.setattr(D, "_resolve_repo_dir", lambda _task: tmp_path)
    monkeypatch.setattr(D, "_run_cmd", lambda *_args, **_kwargs: "in-place")

    monkeypatch.setenv("LIMEN_ISOLATION", " worktree ")
    assert D._worktree_isolation_enabled()
    assert D._call_local_agent("codex", task, False) == "isolated"

    monkeypatch.setenv("LIMEN_ISOLATION", " OFF ")
    assert not D._worktree_isolation_enabled()
    assert D._call_local_agent("codex", task, False) == "in-place"


def test_isolation_creation_root_follows_live_env_after_module_import(tmp_path: Path, monkeypatch) -> None:
    first = tmp_path / "first-volume" / "worktrees"
    second = tmp_path / "second-volume" / "worktrees"

    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(first))
    assert D._isolation_root() == first

    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(second))
    assert D._isolation_root() == second


# ── Explicit --task does NOT bypass worktree admission (item 7) ─────────────


def _resource_blocked_snapshot() -> "D.WorktreeAdmissionSnapshot":
    return D.WorktreeAdmissionSnapshot(
        active=True,
        block_new_local=True,
        reason="local free 1.0 GiB < 45 GiB floor",
        resource_blocked=True,
        vitals_shed=False,
        reaper_blocked=False,
        free_gib=1.0,
        floor_gib=45,
        reserved_gib=0.0,
        room_gib=0.0,
        targets_present=True,
        debt=0,
        vitals_action="ok",
    )


def test_explicit_task_dispatch_still_obeys_admission(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_WORKTREE_DEBT_GATE", "1")
    monkeypatch.setattr(D, "_worktree_admission_snapshot", _resource_blocked_snapshot)
    monkeypatch.setattr(
        D, "call_agent_dispatch", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not dispatch"))
    )
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "EXPLICIT-LOCAL",
                "title": "explicit local task",
                "repo": "someorg/dispatch-lab",
                "target_agent": "codex",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-20",
                "dispatch_log": [],
            }
        ],
    )

    dispatch_tasks(load_limen_file(tasks_path), tasks_path, agent="codex", dry_run=False, task_id="EXPLICIT-LOCAL")

    out = capsys.readouterr().out
    assert "Worktree admission blocked EXPLICIT-LOCAL" in out
    assert read_board(tasks_path)["tasks"][0]["status"] == "open"


def test_explicit_task_reserves_its_dynamic_checkout_estimate(tmp_path: Path, capsys, monkeypatch) -> None:
    snapshot = D.WorktreeAdmissionSnapshot(
        active=True,
        block_new_local=False,
        reason="",
        resource_blocked=False,
        vitals_shed=False,
        reaper_blocked=False,
        free_gib=61.25,
        floor_gib=60.0,
        reserved_gib=0.0,
        room_gib=1.25,
        targets_present=False,
        debt=0,
        vitals_action="ok",
    )
    monkeypatch.setattr(D, "_worktree_admission_snapshot", lambda: snapshot)
    monkeypatch.setattr(D, "_tracked_head_checkout_gib", lambda _task: 0.75)
    monkeypatch.setattr(D, "call_agent_dispatch", lambda *_args, **_kwargs: True)
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "EXPLICIT-SIZED",
                "title": "explicit sized local task",
                "repo": "someorg/dispatch-lab",
                "target_agent": "codex",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-20",
                "dispatch_log": [],
            }
        ],
    )

    dispatch_tasks(load_limen_file(tasks_path), tasks_path, agent="codex", dry_run=True, task_id="EXPLICIT-SIZED")

    assert "DRY-RUN: 1 task" in capsys.readouterr().out
    assert snapshot["reserved_gib"] == 0.75
    assert snapshot["room_gib"] == 0.5


def test_serial_live_dispatch_obeys_machine_local_slot_ceiling(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_ASYNC_MAX", "1")
    holder = _wtask(repo="someorg/holder")
    with D._machine_admission_lock():
        D._write_machine_admission_lease(holder, "codex", 0.0)
    monkeypatch.setattr(
        D, "call_agent_dispatch", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("slot must block"))
    )
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "SERIAL-SECOND",
                "title": "second serial local task",
                "repo": "someorg/second",
                "target_agent": "codex",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-20",
            }
        ],
    )
    try:
        dispatch_tasks(load_limen_file(tasks_path), tasks_path, agent="codex", dry_run=False)
    finally:
        D._release_machine_admission(holder.id)

    assert "machine local slots full (1/1)" in capsys.readouterr().out
    assert read_board(tasks_path)["tasks"][0]["status"] == "open"


def test_explicit_local_task_with_unknown_checkout_estimate_is_denied(tmp_path: Path, capsys, monkeypatch) -> None:
    snapshot = D.WorktreeAdmissionSnapshot(
        active=True,
        block_new_local=False,
        reason="",
        resource_blocked=False,
        vitals_shed=False,
        reaper_blocked=False,
        free_gib=100.0,
        floor_gib=60.0,
        reserved_gib=0.0,
        room_gib=40.0,
        targets_present=False,
        debt=0,
        vitals_action="ok",
    )
    monkeypatch.setattr(D, "_worktree_admission_snapshot", lambda: snapshot)
    monkeypatch.setattr(D, "_tracked_head_checkout_gib", lambda _task: None)
    monkeypatch.setattr(
        D, "call_agent_dispatch", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not dispatch"))
    )
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "EXPLICIT-UNKNOWN-SIZE",
                "title": "explicit unknown local task",
                "repo": "someorg/missing",
                "target_agent": "codex",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-20",
                "dispatch_log": [],
            }
        ],
    )

    dispatch_tasks(
        load_limen_file(tasks_path),
        tasks_path,
        agent="codex",
        dry_run=True,
        task_id="EXPLICIT-UNKNOWN-SIZE",
    )

    out = capsys.readouterr().out
    assert "Worktree admission blocked EXPLICIT-UNKNOWN-SIZE" in out
    assert "tracked HEAD checkout size is unknown" in out


def test_explicit_task_operator_override_gate_off(tmp_path: Path, capsys, monkeypatch) -> None:
    # The documented override is LIMEN_WORKTREE_DEBT_GATE=0 (snapshot inactive), not task_id.
    monkeypatch.setenv("LIMEN_WORKTREE_DEBT_GATE", "0")
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "EXPLICIT-LOCAL",
                "title": "explicit local task",
                "repo": "someorg/dispatch-lab",
                "target_agent": "codex",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-20",
                "dispatch_log": [],
            }
        ],
    )

    dispatch_tasks(load_limen_file(tasks_path), tasks_path, agent="codex", dry_run=True, task_id="EXPLICIT-LOCAL")
    out = capsys.readouterr().out
    assert "Worktree admission blocked" not in out
    assert "DRY-RUN: 1 task" in out
