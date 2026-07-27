from __future__ import annotations

import importlib.util
import io
import json
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLAUDE_HOOK = ROOT / "scripts" / "hooks" / "claude-host-admission.py"
CODEX_HOOK = ROOT / "scripts" / "hooks" / "codex-host-admission.py"


def load_hook(path: Path) -> ModuleType:
    name = f"{path.stem.replace('-', '_')}_{path.stat().st_ino}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolver(module: ModuleType):
    return module.claude_owner_pid if hasattr(module, "claude_owner_pid") else module.codex_owner_pid


@pytest.mark.parametrize("path", [CLAUDE_HOOK, CODEX_HOOK])
def test_process_table_preserves_full_argv(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hook = load_hook(path)
    process = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=" 401 101 /usr/local/bin/node /opt/provider/package/cli.js --flag\n",
        stderr="",
    )
    monkeypatch.setattr(hook.subprocess, "run", lambda *args, **kwargs: process)

    assert hook._process_table() == {401: (101, "/usr/local/bin/node /opt/provider/package/cli.js --flag")}


@pytest.mark.parametrize(
    ("path", "table", "expected"),
    [
        (
            CLAUDE_HOOK,
            {
                500: (401, "/usr/bin/python3 /opt/limen/claude-host-admission.py"),
                401: (101, "/usr/local/bin/node /opt/node_modules/@anthropic-ai/claude-code/cli.js"),
                101: (1, "/Applications/Warp.app/Contents/MacOS/stable"),
            },
            401,
        ),
        (
            CLAUDE_HOOK,
            {
                500: (401, "/usr/bin/python3 /opt/limen/claude-host-admission.py"),
                401: (1, "/Applications/Claude.app/Contents/MacOS/Claude"),
            },
            401,
        ),
        (
            CLAUDE_HOOK,
            {
                500: (401, "/usr/bin/python3 /opt/limen/claude-host-admission.py"),
                401: (1, "/Users/test/.local/share/claude/versions/2.1.220 --print"),
            },
            401,
        ),
        (
            CODEX_HOOK,
            {
                500: (401, "/usr/bin/python3 /opt/limen/codex-host-admission.py"),
                401: (101, "/usr/local/bin/node /opt/node_modules/@openai/codex/bin/codex.js"),
                101: (1, "/Applications/Terminal.app/Contents/MacOS/Terminal"),
            },
            401,
        ),
        (
            CODEX_HOOK,
            {
                500: (401, "/usr/bin/python3 /opt/limen/codex-host-admission.py"),
                401: (1, "/opt/codex-aarch64-apple-darwin"),
            },
            401,
        ),
    ],
)
def test_owner_pid_selects_a_proven_provider_process(
    path: Path,
    table: dict[int, tuple[int, str]],
    expected: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hook = load_hook(path)
    monkeypatch.setattr(hook.os, "getppid", lambda: 500)
    monkeypatch.setattr(hook, "_process_table", lambda: table)

    assert resolver(hook)() == expected


@pytest.mark.parametrize(
    ("path", "table"),
    [
        (
            CLAUDE_HOOK,
            {
                500: (401, "/usr/bin/python3 /tmp/claude-project/hook.py"),
                401: (101, "/usr/local/bin/node /tmp/claude-project/cli.js"),
                101: (1, "/Applications/Warp.app/Contents/MacOS/stable"),
            },
        ),
        (
            CODEX_HOOK,
            {
                500: (401, "/usr/bin/python3 /tmp/codex-project/hook.py"),
                401: (101, "/usr/local/bin/node /tmp/codex-project/cli.js"),
                101: (1, "/Applications/Terminal.app/Contents/MacOS/Terminal"),
            },
        ),
    ],
)
def test_owner_pid_never_falls_back_to_a_terminal_or_project_name(
    path: Path,
    table: dict[int, tuple[int, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hook = load_hook(path)
    monkeypatch.setattr(hook.os, "getppid", lambda: 500)
    monkeypatch.setattr(hook, "_process_table", lambda: table)

    with pytest.raises(ValueError, match="owner ancestor cannot be proven"):
        resolver(hook)()


@pytest.mark.parametrize("path", [CLAUDE_HOOK, CODEX_HOOK])
def test_unproven_owner_is_denied_before_admission(
    path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    hook = load_hook(path)
    monkeypatch.setattr(hook.os, "getppid", lambda: 500)
    monkeypatch.setattr(
        hook,
        "_process_table",
        lambda: {
            500: (401, "/usr/bin/python3 /tmp/provider-project/hook.py"),
            401: (101, "/bin/zsh -l"),
            101: (1, "/Applications/Warp.app/Contents/MacOS/stable"),
        },
    )
    monkeypatch.setattr(
        hook.sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "hook_event_name": "PreToolUse",
                    "session_id": "session-a",
                    "cwd": str(ROOT),
                    "permission_mode": "default",
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(ROOT / "new.txt")},
                }
            )
        ),
    )

    assert hook.main() == 0
    output = json.loads(capsys.readouterr().out)
    specific = output["hookSpecificOutput"]
    assert specific["permissionDecision"] == "deny"
    assert "owner ancestor cannot be proven" in specific["permissionDecisionReason"]
