"""Process-level regressions for the mandatory hook's untrusted input boundary."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from limen.host_admission_capabilities import host_admission_capabilities

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "scripts/hooks/codex-host-admission.py"


def assert_denied(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert set(output) == {"hookSpecificOutput"}
    verdict = output["hookSpecificOutput"]
    assert verdict["hookEventName"] == "PreToolUse"
    assert verdict["permissionDecision"] == "deny"
    assert verdict["permissionDecisionReason"]


@pytest.mark.parametrize("raw", ["{", "[]", "null", "{}", '{"hook_event_name":7}'])
def test_unclassifiable_registered_mutation_is_denied(raw: str) -> None:
    result = subprocess.run(
        [sys.executable, str(HOOK), "--event", "PreToolUse"],
        input=raw,
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert_denied(result)


def test_registered_event_cannot_be_downgraded_by_payload() -> None:
    result = subprocess.run(
        [sys.executable, str(HOOK), "--event", "PreToolUse"],
        input='{"hook_event_name":"UserPromptSubmit"}',
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert_denied(result)


def test_invalid_utf8_is_a_native_denial() -> None:
    result = subprocess.run(
        [sys.executable, str(HOOK), "--event", "PreToolUse"],
        input=b"\xff",
        capture_output=True,
        timeout=3,
    )
    assert_denied(
        subprocess.CompletedProcess(result.args, result.returncode, result.stdout.decode(), result.stderr.decode())
    )


def test_input_size_limit_denies_before_parsing() -> None:
    result = subprocess.run(
        [sys.executable, str(HOOK), "--event", "PreToolUse"],
        input=json.dumps({"hook_event_name": "UserPromptSubmit", "data": "x" * 1_100_000}),
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert_denied(result)


def test_stalled_stdin_exits_with_denial_inside_native_hook_budget() -> None:
    started = time.monotonic()
    process = subprocess.Popen(
        [sys.executable, str(HOOK), "--event", "PreToolUse"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        process.wait(timeout=9)
        assert process.stdout is not None and process.stderr is not None
        assert_denied(
            subprocess.CompletedProcess(process.args, process.returncode, process.stdout.read(), process.stderr.read())
        )
        assert time.monotonic() - started < 9
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


@pytest.mark.parametrize(
    "response", ["{}", '{"continue":"false"}', '{"hookSpecificOutput":{"permissionDecision":"bogus"}}']
)
def test_malformed_delegate_verdict_fails_closed(tmp_path: Path, response: str) -> None:
    target = tmp_path / "delegate.py"
    capabilities = json.dumps(host_admission_capabilities())
    target.write_text(f"import sys\nprint({capabilities!r} if sys.argv[1:] == ['--capabilities'] else {response!r})\n")
    result = subprocess.run(
        [sys.executable, str(HOOK), "--delegate-immutable", str(target), "--event", "PreToolUse"],
        input='{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"x"}}',
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert_denied(result)
    assert "runtime-delegate-invalid-verdict" in result.stdout


def test_malformed_known_lifecycle_input_stays_nonblocking() -> None:
    result = subprocess.run(
        [sys.executable, str(HOOK), "--event", "Stop"],
        input="{",
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert result.returncode == 0
    assert set(json.loads(result.stdout)) == {"systemMessage"}


@pytest.mark.parametrize(
    "body,reason",
    [
        ("raise RuntimeError('private payload')", "runtime-delegate-nonzero"),
        ("print('x' * 100000)", "runtime-delegate-output"),
        ("print('{}\\n{}')", "runtime-delegate-malformed-output"),
    ],
)
def test_failed_delegate_is_bounded_and_redacted(tmp_path: Path, body: str, reason: str) -> None:
    target = tmp_path / "delegate.py"
    capabilities = json.dumps(host_admission_capabilities())
    target.write_text(
        f"import sys\nif sys.argv[1:] == ['--capabilities']:\n    print({capabilities!r})\nelse:\n    {body}\n"
    )
    result = subprocess.run(
        [sys.executable, str(HOOK), "--delegate-immutable", str(target), "--event", "PreToolUse"],
        input='{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"x"}}',
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert_denied(result)
    assert reason in result.stdout
    assert "private payload" not in result.stdout + result.stderr


def test_registered_runner_rejects_malformed_input(tmp_path: Path) -> None:
    config = json.loads((ROOT / ".codex/hooks.json").read_text())
    command = config["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    result = subprocess.run(
        ["bash", "-c", command],
        input="{",
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=3,
    )
    assert_denied(result)


def test_registered_runner_denies_if_policy_entrypoint_is_missing(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/hooks/codex-hook-runner.sh"), "host-admission", "--event", "PreToolUse"],
        input="{",
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PATH": os.environ["PATH"], "HOME": str(tmp_path), "CODEX_PROJECT_DIR": str(tmp_path)},
        timeout=3,
    )
    assert_denied(result)


def test_delegate_descendants_are_terminated(tmp_path: Path) -> None:
    target = tmp_path / "delegate.py"
    witness = tmp_path / "child.pid"
    capabilities = json.dumps(host_admission_capabilities())
    target.write_text(
        "import sys,subprocess,pathlib\n"
        "if sys.argv[1:] == ['--capabilities']:\n"
        f"    print({capabilities!r})\n"
        "else:\n"
        "    child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],"
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
        f"    pathlib.Path({str(witness)!r}).write_text(str(child.pid))\n"
        "    print('{}')\n"
    )
    result = subprocess.run(
        [sys.executable, str(HOOK), "--delegate-immutable", str(target), "--event", "PreToolUse"],
        input='{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"x"}}',
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert_denied(result)
    assert "runtime-delegate-descendants" in result.stdout
    pid = int(witness.read_text())
    status = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    assert not status.stdout.strip() or status.stdout.strip().startswith("Z")


def test_stdin_and_delegate_share_one_deadline(tmp_path: Path) -> None:
    target = tmp_path / "slow.py"
    witness = tmp_path / "delegate-started"
    capabilities = json.dumps(host_admission_capabilities())
    target.write_text(
        "import sys,time,pathlib\n"
        "if sys.argv[1:] == ['--capabilities']:\n"
        f"    print({capabilities!r})\n"
        "else:\n"
        f"    pathlib.Path({str(witness)!r}).touch()\n"
        "    time.sleep(6)\n"
        '    print(\'{"hookSpecificOutput":{"hookEventName":"PreToolUse",'
        '"permissionDecision":"allow","permissionDecisionReason":"fixture"}}\')\n'
    )
    started = time.monotonic()
    process = subprocess.Popen(
        [sys.executable, str(HOOK), "--delegate-immutable", str(target), "--event", "PreToolUse"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(3)
        stdout, stderr = process.communicate(
            '{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"x"}}',
            timeout=6,
        )
        assert_denied(subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr))
        assert witness.is_file()
        assert time.monotonic() - started < 9
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()
