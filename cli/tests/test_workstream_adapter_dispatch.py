"""Regression proof for conducted packets at the real local spawn seams."""

from __future__ import annotations

import json
import subprocess
from datetime import date

import pytest

import limen.dispatch as D
from limen.models import Task
from limen.workstream_contract import packet_contract


def _task(agent: str = "codex", *, workstream: bool = True) -> Task:
    payload = {
        "id": f"T-WORKSTREAM-{agent.upper()}",
        "title": "fixture",
        "target_agent": agent,
        "created": date(2026, 7, 17),
    }
    if workstream:
        payload["workstream_contract"] = packet_contract("2d")
    return Task(**payload)


def test_codex_workstream_argv_places_exact_safe_globals_before_exec(monkeypatch):
    monkeypatch.setattr(D, "_codex_model", lambda task=None: "fixture-model")

    argv = D._agent_argv("codex", _task("codex"))

    assert argv[:5] == [
        "--ask-for-approval",
        "never",
        "--sandbox",
        "workspace-write",
        "exec",
    ]
    assert argv[5] == "--skip-git-repo-check"
    assert argv[-2:] == ["-m", "fixture-model"]
    D._assert_codex_workstream_argv(argv)


@pytest.mark.parametrize(
    "argv",
    [
        ["--ask-for-approval", "on-request", "--sandbox", "workspace-write", "exec"],
        ["exec", "--ask-for-approval", "never", "--sandbox", "workspace-write"],
        ["--ask-for-approval", "never", "--sandbox", "danger-full-access", "exec"],
        [
            "--ask-for-approval",
            "never",
            "--sandbox",
            "workspace-write",
            "--dangerously-bypass-approvals-and-sandbox",
            "exec",
        ],
        [
            "--ask-for-approval",
            "never",
            "--sandbox",
            "workspace-write",
            "--add-dir",
            "/tmp/extra",
            "exec",
        ],
        [
            "--ask-for-approval",
            "never",
            "--sandbox",
            "workspace-write",
            "--ignore-rules",
            "exec",
        ],
    ],
)
def test_codex_unsafe_or_misordered_argv_fails_before_launch(argv):
    with pytest.raises(D.WorkstreamLaunchContractError):
        D._assert_codex_workstream_argv(argv)


def test_agy_workstream_argv_is_sandboxed_bounded_and_never_bypasses(monkeypatch):
    task = _task("agy")
    deadline = int(task.workstream_contract["runway"]["deadline_epoch"])
    monkeypatch.setattr(D.time, "time", lambda: deadline - 90)
    monkeypatch.setenv("LIMEN_LANE_TIMEOUT", "1800")

    argv = D._agent_argv("agy", task)

    assert argv == ["--sandbox", "--print-timeout", "90s", "-p"]
    assert "--dangerously-skip-permissions" not in argv
    D._assert_agy_workstream_argv(argv)


@pytest.mark.parametrize("workstream", [False, True])
def test_agy_derives_900s_ceiling_before_asserting_argv(monkeypatch, workstream):
    monkeypatch.setenv("LIMEN_LANE_TIMEOUT", "900")

    argv = D._agent_argv("agy", _task("agy", workstream=workstream))

    assert argv == ["--sandbox", "--print-timeout", "900s", "-p"]


@pytest.mark.parametrize(
    "argv",
    [
        ["--print-timeout", "30m", "-p"],
        ["--sandbox", "--print-timeout", "forever", "-p"],
        ["--sandbox", "--print-timeout", "999999d", "-p"],
        ["--sandbox", "--print-timeout", "30m", "-p", "--mode", "accept-edits"],
        ["--sandbox", "--print-timeout", "30m", "--dangerously-skip-permissions", "-p"],
        ["--sandbox", "--print-timeout", "30m", "--add-dir", "/tmp/extra", "-p"],
        ["--sandbox", "--print-timeout", "30m", "--prompt-interactive", "-p"],
    ],
)
def test_agy_unbounded_interactive_or_bypass_drift_fails_before_launch(argv):
    with pytest.raises(D.WorkstreamLaunchContractError):
        D._assert_agy_workstream_argv(argv)


def test_opencode_workstream_uses_pure_run_and_exact_deny_overlay(monkeypatch, tmp_path):
    monkeypatch.setattr(D, "_opencode_model", lambda task=None: "provider/fixture")
    task = _task("opencode")

    base = D._agent_argv("opencode", task)
    argv = D._workspace_agent_args("opencode", base, tmp_path)
    run_env = {"OPENCODE_DISABLE_PROJECT_CONFIG": "1"}
    D._opencode_workstream_env(run_env)

    assert base == ["--pure", "run", "-m", "provider/fixture"]
    assert D._option_values(argv, "--dir") == [str(tmp_path)]
    assert "OPENCODE_DISABLE_PROJECT_CONFIG" not in run_env
    assert json.loads(run_env["OPENCODE_PERMISSION"]) == D._OPENCODE_WORKSTREAM_PERMISSION
    assert json.loads(run_env["OPENCODE_PERMISSION"])["*"] == "deny"
    assert json.loads(run_env["OPENCODE_PERMISSION"])["bash"] == "deny"
    assert json.loads(run_env["OPENCODE_PERMISSION"])["external_directory"] == "deny"
    assert json.loads(run_env["OPENCODE_PERMISSION"])["question"] == "deny"
    D._assert_final_workstream_launch("opencode", task, argv, run_env, tmp_path)


@pytest.mark.parametrize(
    "extra",
    [
        ["--auto"],
        ["--share"],
        ["--attach", "http://localhost:4096"],
        ["--interactive"],
        ["-i"],
        ["--yolo"],
        ["--dangerously-skip-permissions"],
    ],
)
def test_opencode_unsafe_or_interactive_flags_fail_before_launch(extra, tmp_path):
    argv = ["--pure", "run", *extra, "--dir", str(tmp_path)]

    with pytest.raises(D.WorkstreamLaunchContractError):
        D._assert_opencode_workstream_argv(argv, workspace=tmp_path)


def test_opencode_final_spawn_receives_exact_safe_argv_and_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(D, "_opencode_model", lambda task=None: "provider/fixture")
    monkeypatch.setattr(D, "_show_opencode_clock_after_run", lambda task: None)
    task = _task("opencode")
    argv = D._workspace_agent_args("opencode", D._agent_argv("opencode", task), tmp_path)
    cmd = ["opencode", *argv, "perform the bounded edit"]
    seen: dict[str, object] = {}

    def fake_run(command, *, cwd=None, timeout=0, env=None):
        seen.update(command=command, cwd=cwd, timeout=timeout, env=env)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(D, "_run_capture", fake_run)

    assert D._run_isolated_agent("opencode", task, tmp_path, cmd, 1800) is True
    assert seen["command"] == cmd
    assert seen["cwd"] == str(tmp_path)
    env = seen["env"]
    assert isinstance(env, dict)
    assert env["OPENCODE_PERMISSION"] == D._OPENCODE_WORKSTREAM_PERMISSION_JSON
    assert env["OPENCODE_PURE"] == "1"
    assert env["OPENCODE_DISABLE_EXTERNAL_SKILLS"] == "1"
    assert env["OPENCODE_DISABLE_SHARE"] == "1"
    assert "OPENCODE_DISABLE_PROJECT_CONFIG" not in env


def test_opencode_environment_drift_stops_before_process_creation(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(D, "_opencode_model", lambda task=None: "provider/fixture")
    task = _task("opencode")
    argv = D._workspace_agent_args("opencode", D._agent_argv("opencode", task), tmp_path)
    cmd = ["opencode", *argv, "perform the bounded edit"]
    spawned = False

    def bad_env(agent, wt=None, task=None):
        return {"OPENCODE_PERMISSION": json.dumps({"edit": "allow"})}

    def forbidden_spawn(*args, **kwargs):
        nonlocal spawned
        spawned = True
        raise AssertionError("provider process must not start")

    monkeypatch.setattr(D, "_lane_run_env", bad_env)
    monkeypatch.setattr(D, "_run_capture", forbidden_spawn)

    result = D._run_isolated_agent("opencode", task, tmp_path, cmd, 1800)
    assert D._is_workstream_successor_result(result)
    assert spawned is False
    assert "refusing provider launch so the lane can successor-route" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("agent", "argv"),
    [
        (
            "codex",
            [
                "--ask-for-approval",
                "never",
                "--sandbox",
                "workspace-write",
                "--ignore-rules",
                "exec",
            ],
        ),
        (
            "agy",
            ["--sandbox", "--print-timeout", "30m", "--prompt-interactive", "-p"],
        ),
    ],
)
def test_final_adapter_argv_drift_stops_before_process_creation(agent, argv, monkeypatch, tmp_path, capsys):
    task = _task(agent)
    spawned = False

    def forbidden_spawn(*args, **kwargs):
        nonlocal spawned
        spawned = True
        raise AssertionError("provider process must not start")

    monkeypatch.setattr(D, "_run_capture", forbidden_spawn)

    result = D._run_isolated_agent(agent, task, tmp_path, [agent, *argv, "prompt"], 1800)
    assert D._is_workstream_successor_result(result)
    assert spawned is False
    assert "refusing provider launch so the lane can successor-route" in capsys.readouterr().out


@pytest.mark.parametrize("agent", ["codex", "agy"])
def test_call_local_agent_passes_validated_argv_into_isolated_path(agent, monkeypatch):
    task = _task(agent)
    seen: dict[str, object] = {}
    monkeypatch.setattr(D, "agent_can_run_task", lambda candidate, packet: True)
    monkeypatch.setattr(D, "_worktree_isolation_enabled", lambda: True)
    monkeypatch.setattr(D, "_codex_model", lambda task=None: None)

    def fake_isolated(candidate, packet, dry_run, args):
        seen.update(agent=candidate, task=packet, dry_run=dry_run, args=args)
        return "isolated"

    monkeypatch.setattr(D, "_isolated_local_run", fake_isolated)

    assert D._call_local_agent(agent, task, dry_run=False) == "isolated"
    assert seen["task"] is task
    D._assert_workstream_agent_argv(agent, seen["args"])


def test_legacy_opencode_task_stays_noninteractive_without_workstream_overlay(monkeypatch):
    monkeypatch.setattr(D, "_opencode_model", lambda task=None: "provider/fixture")
    for name in (
        "OPENCODE_PERMISSION",
        "OPENCODE_PURE",
        "OPENCODE_DISABLE_EXTERNAL_SKILLS",
        "OPENCODE_DISABLE_SHARE",
    ):
        monkeypatch.delenv(name, raising=False)

    argv = D._agent_argv("opencode", _task("opencode", workstream=False))
    run_env = D._lane_run_env("opencode", task=_task("opencode", workstream=False))

    assert argv == ["--pure", "run", "-m", "provider/fixture"]
    assert "--auto" not in argv
    assert "--interactive" not in argv
    assert "OPENCODE_PERMISSION" not in run_env


def test_expired_packet_blocks_remote_lane_before_provider_call(monkeypatch):
    expired = packet_contract("15m", now_epoch=1_000)
    task = Task(
        id="T-EXPIRED-JULES",
        title="fixture",
        target_agent="jules",
        created=date(2026, 7, 17),
        workstream_contract=expired,
    )
    called = False

    def forbidden_jules(packet, dry_run):
        nonlocal called
        called = True
        raise AssertionError("remote provider must not start")

    monkeypatch.setattr(D, "_call_jules", forbidden_jules)
    monkeypatch.setattr(D.time, "time", lambda: 1_900)

    result = D.call_agent_dispatch("jules", task, dry_run=False)
    assert D._is_workstream_successor_result(result)
    assert called is False


def test_generic_dispatch_override_cannot_bypass_conducted_adapter(monkeypatch):
    task = _task("codex")
    monkeypatch.setenv("LIMEN_DISPATCH_CMD", "unsafe-generic-override")
    monkeypatch.setattr(
        D,
        "_run_cmd",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("override must not launch")),
    )

    result = D.call_agent_dispatch("codex", task, dry_run=False)

    assert D._is_workstream_successor_result(result)
    assert "cannot bypass" in D._workstream_successor_reason(result)


def test_unverifiable_provider_model_override_becomes_routing_blocker(monkeypatch):
    monkeypatch.setenv("LIMEN_CODEX_MODEL", "fixture-provider-id")

    result = D._call_local_agent("codex", _task("codex"), dry_run=True)

    assert D._is_blocked_result(result)
    assert "no live model catalog" in D._blocked_reason(result)


def test_shared_command_spawn_rechecks_runway_after_provider_preflight(monkeypatch):
    task = _task("warp")
    deadline = int(task.workstream_contract["runway"]["deadline_epoch"])
    monkeypatch.setattr(D.time, "time", lambda: deadline)
    monkeypatch.setattr(
        D,
        "_run_capture",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("expired provider must not launch")),
    )

    result = D._run_cmd(["provider", "submit"], task, dry_run=False)

    assert D._is_workstream_successor_result(result)
    assert "runway is exhausted" in D._workstream_successor_reason(result)


def test_claude_auth_retry_rechecks_runway_before_second_process(monkeypatch, tmp_path):
    task = _task("claude")
    deadline = int(task.workstream_contract["runway"]["deadline_epoch"])
    clock = [deadline - 1]
    calls = 0

    def auth_blip(cmd, cwd=None, timeout=600, env=None):
        nonlocal calls
        calls += 1
        clock[0] = deadline
        return subprocess.CompletedProcess(cmd, 1, "", "Not logged in")

    monkeypatch.setattr(D.time, "time", lambda: clock[0])
    monkeypatch.setattr(D, "_run_capture", auth_blip)

    result = D._run_isolated_agent("claude", task, tmp_path, ["claude", "prompt"], 30)

    assert D._is_workstream_successor_result(result)
    assert "runway is exhausted" in D._workstream_successor_reason(result)
    assert calls == 1
