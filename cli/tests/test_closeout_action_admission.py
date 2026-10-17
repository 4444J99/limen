from __future__ import annotations

import shlex
from pathlib import Path

import pytest
from limen.action_admission import classify_action
from limen.action_admission_runtime import admit_pre_tool_action

ROOT = Path(__file__).resolve().parents[2]


def request(command: str, cwd: Path) -> dict:
    return {"tool_name": "Bash", "cwd": str(cwd), "tool_input": {"command": command}}


def command(script: Path, *extra: str) -> str:
    return shlex.join(
        [
            "bash",
            str(script),
            "--session-id",
            "native-id",
            "--worktree",
            "/foreign/root",
            "--receipt",
            "/foreign/receipt.json",
            *extra,
        ]
    )


@pytest.mark.parametrize("relative", [False, True])
def test_canonical_session_closeout_is_observation(relative: bool) -> None:
    script = Path("scripts/no-tasks-on-me.sh") if relative else ROOT / "scripts/no-tasks-on-me.sh"
    action = classify_action(request(command(script, "--scope-root", "other=/foreign/other", "--json"), ROOT))
    assert action.category == "observe"


def test_closeout_observation_needs_no_writer_or_repository(tmp_path: Path) -> None:
    result = admit_pre_tool_action(
        request(command(ROOT / "scripts/no-tasks-on-me.sh"), tmp_path),
        controller=object(),
        owner=None,
        pid=1,
        surface="fixture",
        ttl_seconds=30,
    )
    assert result.allowed


@pytest.mark.parametrize(
    "extra",
    [
        ["--execute"],
        ["--session-id", "duplicate"],
        ["--scope-root"],
        ["--receipt", "duplicate"],
        ["--apply"],
        ["--json", "--unknown"],
    ],
)
def test_unknown_or_ambiguous_modes_are_not_observation(extra: list[str]) -> None:
    assert classify_action(request(command(ROOT / "scripts/no-tasks-on-me.sh", *extra), ROOT)).category != "observe"


def test_estate_mode_is_not_session_observation() -> None:
    assert (
        classify_action(request(shlex.join(["bash", str(ROOT / "scripts/no-tasks-on-me.sh")]), ROOT)).category
        != "observe"
    )


def test_copied_checker_name_does_not_confer_authority(tmp_path: Path) -> None:
    script = tmp_path / "no-tasks-on-me.sh"
    script.write_text("touch /foreign/marker\n")
    assert classify_action(request(command(script), ROOT)).category != "observe"


def test_checker_leaf_symlink_does_not_change_companion_resolution(tmp_path: Path) -> None:
    script = tmp_path / "no-tasks-on-me.sh"
    script.symlink_to(ROOT / "scripts/no-tasks-on-me.sh")
    assert classify_action(request(command(script), ROOT)).category != "observe"


def test_checker_output_redirection_remains_a_write() -> None:
    assert (
        classify_action(request(command(ROOT / "scripts/no-tasks-on-me.sh") + " > /foreign/output", ROOT)).category
        == "workspace_write"
    )


def test_checker_chaining_remains_denied() -> None:
    assert (
        classify_action(request(command(ROOT / "scripts/no-tasks-on-me.sh") + "; touch /foreign/marker", ROOT)).category
        == "deny"
    )


def test_absolute_impostor_interpreter_is_not_observation() -> None:
    value = command(ROOT / "scripts/no-tasks-on-me.sh").replace("bash ", "/foreign/bash ", 1)
    assert classify_action(request(value, ROOT)).category != "observe"


def test_readonly_receipt_name_cannot_trigger_heavy_classification() -> None:
    value = command(ROOT / "scripts/no-tasks-on-me.sh").replace("/foreign/receipt.json", "/foreign/verify-whole.sh")
    assert classify_action(request(value, ROOT)).category == "observe"
