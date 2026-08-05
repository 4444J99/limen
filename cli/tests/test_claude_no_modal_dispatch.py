"""Regression proof for Limen's unattended Claude launch contract."""

from __future__ import annotations

from datetime import date

import pytest

import limen.dispatch as D
from limen.models import Task


def test_real_claude_dispatch_argv_is_noninteractive_and_fail_closed(monkeypatch):
    monkeypatch.setattr(D, "_claude_model", lambda task=None: None)

    argv = D._agent_argv("claude")

    assert argv[0] == "-p"
    assert D._option_values(argv, "--permission-mode") == ["dontAsk"]
    allowed = set(D._option_values(argv, "--allowedTools")[0].split(","))
    assert {"Edit", "Write"} <= allowed
    assert "Bash" not in allowed
    assert D._option_values(argv, "--disallowedTools") == ["AskUserQuestion"]


@pytest.mark.parametrize("mode", ["default", "acceptEdits", "plan", "auto", "bypassPermissions"])
def test_prompt_capable_or_host_unsafe_modes_fail_before_launch(mode):
    argv = [
        "-p",
        "--permission-mode",
        mode,
        "--allowedTools",
        "Bash,Edit,Write",
    ]

    with pytest.raises(RuntimeError, match="exactly one dontAsk"):
        D._assert_claude_no_modal_contract(argv)


@pytest.mark.parametrize(
    "argv",
    [
        ["-p", "--allowedTools", "Bash,Edit,Write"],
        [
            "-p",
            "--permission-mode",
            "dontAsk",
            "--permission-mode",
            "auto",
            "--allowedTools",
            "Bash,Edit,Write",
        ],
    ],
)
def test_missing_or_ambiguous_mode_fails_before_launch(argv):
    with pytest.raises(RuntimeError, match="exactly one dontAsk"):
        D._assert_claude_no_modal_contract(argv)


def test_interactive_claude_launch_fails_before_launch():
    argv = ["--permission-mode", "dontAsk", "--allowedTools", "Bash,Edit,Write"]

    with pytest.raises(RuntimeError, match="non-interactive print mode"):
        D._assert_claude_no_modal_contract(argv)


@pytest.mark.parametrize("allowed", ["Write", "Edit", "NotebookEdit"])
def test_missing_core_build_tool_fails_before_launch(allowed):
    argv = ["-p", "--permission-mode=dontAsk", "--allowed-tools", allowed]

    with pytest.raises(RuntimeError, match="missing required pre-approved build tools"):
        D._assert_claude_no_modal_contract(argv)


@pytest.mark.parametrize(
    "grant",
    [
        "Bash",
        "Bash(*)",
        "Bash(**)",
        "Bash(:*)",
        "Bash( *)",
        "WebFetch",
        "WebFetch(domain:*)",
        "WebFetch(domain:*.)",
        "WebSearch",
    ],
)
def test_blanket_shell_or_network_grant_fails_before_launch(grant):
    argv = [
        "-p",
        "--permission-mode",
        "dontAsk",
        "--allowedTools",
        f"{grant},Edit,Write",
        "--disallowedTools",
        "AskUserQuestion",
    ]

    with pytest.raises(D.ClaudeLaunchContractError, match="must not add blanket Bash/network grants"):
        D._assert_claude_no_modal_contract(argv)


def test_scoped_shell_and_network_rules_are_not_blanket_grants():
    argv = [
        "-p",
        "--permission-mode",
        "dontAsk",
        "--allowedTools",
        "Bash(git status *),WebFetch(domain:github.com),Edit,Write",
        "--disallowedTools",
        "AskUserQuestion",
    ]

    D._assert_claude_no_modal_contract(argv)


def test_permission_prompt_callback_fails_before_launch():
    argv = [
        "-p",
        "--permission-mode",
        "dontAsk",
        "--allowedTools",
        "Edit Write",
        "--permission-prompt-tool",
        "mcp__permissions__approve",
    ]

    with pytest.raises(RuntimeError, match="must not install a permission-prompt callback"):
        D._assert_claude_no_modal_contract(argv)


@pytest.mark.parametrize("flag", ["--dangerously-skip-permissions", "--allow-dangerously-skip-permissions"])
def test_bypass_enabling_flags_fail_before_launch(flag):
    argv = [
        "-p",
        "--permission-mode",
        "dontAsk",
        "--allowedTools",
        "Edit,Write",
        "--disallowedTools",
        "AskUserQuestion",
        flag,
    ]

    with pytest.raises(RuntimeError, match="must not enable bypassPermissions"):
        D._assert_claude_no_modal_contract(argv)


def test_question_tool_must_be_removed_before_launch():
    argv = ["-p", "--permission-mode", "dontAsk", "--allowedTools", "Edit,Write"]

    with pytest.raises(RuntimeError, match="must remove AskUserQuestion"):
        D._assert_claude_no_modal_contract(argv)


def test_model_selection_cannot_displace_no_modal_flags(monkeypatch):
    monkeypatch.setattr(D, "_claude_model", lambda task=None: "fixture-model")

    argv = D._agent_argv("claude")

    assert argv[-2:] == ["--model", "fixture-model"]
    assert D._option_values(argv, "--permission-mode") == ["dontAsk"]
    D._assert_claude_no_modal_contract(argv)


def test_static_flag_drift_is_rejected_at_runtime(monkeypatch):
    monkeypatch.setattr(D, "_claude_model", lambda task=None: None)
    monkeypatch.setitem(
        D._LOCAL_AGENTS,
        "claude",
        ["-p", "--permission-mode", "acceptEdits", "--allowedTools", "Bash,Edit,Write"],
    )

    with pytest.raises(D.ClaudeLaunchContractError, match="exactly one dontAsk"):
        D._agent_argv("claude")


def test_contract_drift_blocks_only_the_lane_so_dispatch_can_cascade(monkeypatch, capsys):
    monkeypatch.setitem(
        D._LOCAL_AGENTS,
        "claude",
        ["-p", "--permission-mode", "auto", "--allowedTools", "Bash,Edit,Write"],
    )
    task = Task(id="T-NO-MODAL", title="fixture", target_agent="claude", created=date(2026, 7, 14))

    assert D._call_local_agent("claude", task, dry_run=False) is False
    assert "refusing provider launch so the lane can cascade" in capsys.readouterr().out
