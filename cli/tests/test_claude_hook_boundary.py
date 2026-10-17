from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / "scripts/hooks/claude-host-admission.py"


def load_hook():
    spec = importlib.util.spec_from_file_location("claude_boundary", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "raw",
    [
        b"{",
        b"[]",
        b"\xff",
        b"x" * (1024 * 1024 + 1),
        b'{"hook_event_name":"Stop"}',
        b'{"hook_event_name":"PreToolUse"}',
    ],
)
def test_invalid_input_is_denied(raw, monkeypatch, capsys):
    hook = load_hook()
    monkeypatch.setattr(hook.sys, "stdin", io.TextIOWrapper(io.BytesIO(raw)))
    monkeypatch.setattr(hook, "handle", lambda payload: pytest.fail("invalid input reached policy"))
    assert hook.main() == 0
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("failure", [False, True])
def test_evaluation_outcome(failure, monkeypatch, capsys):
    hook = load_hook()
    raw = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}})
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO(raw))

    def evaluate(payload):
        if failure:
            raise RuntimeError("unexpected private evaluation detail")
        return None

    monkeypatch.setattr(hook, "handle", evaluate)
    assert hook.main() == 0
    output = capsys.readouterr().out
    if failure:
        assert json.loads(output)["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "private evaluation detail" not in output
    else:
        assert not output


def test_open_stdin_is_bounded():
    code = (
        "import importlib.util; "
        f"s=importlib.util.spec_from_file_location('h', {str(HOOK)!r}); "
        "h=importlib.util.module_from_spec(s); s.loader.exec_module(h); "
        "h._HOOK_BUDGET_SECONDS=0.05; raise SystemExit(h.main())"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        process.wait(timeout=3)
        assert process.returncode == 0
        output = json.loads(process.stdout.read())
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdin.close()
