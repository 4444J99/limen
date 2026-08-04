from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CONTROLLER = ROOT / "scripts" / "reclaim-cycle.py"
PLAN_SHA = "a" * 64


FAKE_REAPER = r"""#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time
from pathlib import Path

args = sys.argv[1:]
log = Path(os.environ["FAKE_REAPER_LOG"])
with log.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(args) + "\n")

mode = os.environ.get("FAKE_REAPER_MODE", "ok")
if "--generated-only" in args:
    print("reclaim [generated-only]: 1 cleaned, 0 failed")
    raise SystemExit(0)

if "--check" in args:
    if mode == "check-fail":
        print("inventory unavailable", file=sys.stderr)
        raise SystemExit(7)
    if mode == "malformed":
        print("{not-json")
        raise SystemExit(0)
    if mode == "missing-sha":
        print(json.dumps({"candidate_manifest": {"candidates": []}}))
        raise SystemExit(0)
    if mode == "slow-cycle":
        time.sleep(0.05)
    if mode == "child-sleep":
        subprocess.Popen([
            sys.executable,
            "-c",
            "import os,time; from pathlib import Path; time.sleep(1); Path(os.environ['FAKE_CHILD_MARKER']).write_text('survived')",
        ])
        time.sleep(5)
    print(json.dumps({"plan_sha256": "a" * 64, "candidate_manifest": {"candidates": []}}))
    raise SystemExit(0)

if "--apply" in args:
    if mode == "slow-cycle":
        time.sleep(5)
    if mode == "drift":
        print("reclaim [APPLY-BLOCKED]: plan-sha-mismatch")
        raise SystemExit(2)
    if mode == "remote-proof-failure":
        print("FAIL target: remote-purge-proof-drift")
        raise SystemExit(3)
    print("reclaim [APPLY]: exact plan applied")
    raise SystemExit(0)

print("reclaim [dry-run]: preview")
"""


def _fake_reaper(tmp_path: Path) -> tuple[Path, Path]:
    reaper = tmp_path / "fake-reaper.py"
    reaper.write_text(FAKE_REAPER, encoding="utf-8")
    return reaper, tmp_path / "calls.jsonl"


def _run(
    tmp_path: Path,
    *,
    mode: str = "ok",
    timeout: str = "2",
    args: tuple[str, ...] = ("--apply",),
) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
    reaper, log = _fake_reaper(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "FAKE_REAPER_LOG": str(log),
            "FAKE_REAPER_MODE": mode,
            "FAKE_CHILD_MARKER": str(tmp_path / "child-survived"),
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            str(CONTROLLER),
            "--timeout",
            timeout,
            "--output-lines",
            "20",
            "--reaper",
            str(reaper),
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=5,
        env=env,
        check=False,
    )
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    return result, calls


def test_full_cycle_applies_only_the_sha_returned_by_check(tmp_path: Path):
    result, calls = _run(tmp_path)

    assert result.returncode == 0
    assert calls == [
        ["--check", "--json"],
        ["--apply", "--expected-plan-sha", PLAN_SHA],
    ]
    assert f"applied plan_sha256={PLAN_SHA}" in result.stdout


@pytest.mark.parametrize(
    ("mode", "message"),
    [("malformed", "invalid-plan-json"), ("missing-sha", "invalid-plan-sha")],
)
def test_invalid_plan_never_reaches_apply(tmp_path: Path, mode: str, message: str):
    result, calls = _run(tmp_path, mode=mode)

    assert result.returncode == 2
    assert calls == [["--check", "--json"]]
    assert message in result.stderr


def test_nonzero_check_never_reaches_apply(tmp_path: Path):
    result, calls = _run(tmp_path, mode="check-fail")

    assert result.returncode == 7
    assert calls == [["--check", "--json"]]
    assert "inventory unavailable" in result.stderr
    assert "check-failed rc=7" in result.stderr


@pytest.mark.parametrize("mode", ["drift", "remote-proof-failure"])
def test_apply_failure_is_visible_and_nonzero(tmp_path: Path, mode: str):
    result, calls = _run(tmp_path, mode=mode)

    assert result.returncode != 0
    assert calls[-1] == ["--apply", "--expected-plan-sha", PLAN_SHA]
    assert "apply-failed" in result.stderr
    if mode == "drift":
        assert "plan-sha-mismatch" in result.stderr
    else:
        assert "remote-purge-proof-drift" in result.stderr


def test_full_cycle_deadline_includes_apply(tmp_path: Path):
    started = time.monotonic()
    result, calls = _run(tmp_path, mode="slow-cycle", timeout="0.25")
    elapsed = time.monotonic() - started

    assert result.returncode == 124
    assert elapsed < 2
    assert calls == [
        ["--check", "--json"],
        ["--apply", "--expected-plan-sha", PLAN_SHA],
    ]
    assert "timeout phase=apply" in result.stderr


def test_timeout_terminates_the_reaper_process_group(tmp_path: Path):
    started = time.monotonic()
    result, calls = _run(tmp_path, mode="child-sleep", timeout="0.2")
    elapsed = time.monotonic() - started

    assert result.returncode == 124
    assert elapsed < 0.8
    assert calls == [["--check", "--json"]]
    time.sleep(0.3)
    assert not (tmp_path / "child-survived").exists()


def test_generated_only_apply_remains_one_pass(tmp_path: Path):
    result, calls = _run(tmp_path, args=("--generated-only", "--apply"))

    assert result.returncode == 0
    assert calls == [["--generated-only", "--apply"]]
    assert "generated-only" in result.stderr


def test_preview_remains_one_bounded_non_applying_pass(tmp_path: Path):
    result, calls = _run(tmp_path, args=())

    assert result.returncode == 0
    assert calls == [[]]
    assert all("--apply" not in call for call in calls)
