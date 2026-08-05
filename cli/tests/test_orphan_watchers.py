"""Tests for scripts/orphan-watchers.py — the endless-watcher detection organ.

The ps table is injected via --ps-fixture (a `ps -axo pid=,ppid=,etime=,command=` replay) under a
tmp LIMEN_ROOT, so classification is hermetic. The reap path is proven against a real disposable
`sleep` child spawned in its own session (its own process group), never against fixture-only pids.
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "orphan-watchers.py"

SNAP = "/Users/u/.claude/shell-snapshots/snapshot-zsh-1.sh"
CLAUDE_PARENT = "2501     1 37:18 /Users/u/.local/share/claude/versions/2.1.190 --bg-spare /tmp/x.sock"


def watcher_row(pid=26294, ppid=2501, etime="45:00", poll="gh pr view 1066 --json statusCheckRollup"):
    return f"{pid} {ppid} {etime} /bin/zsh -c source {SNAP} && eval 'for i in $(seq 1 40); do {poll}; sleep 45; done'"


def run(tmp: Path, fixture_text: str, *args: str, min_age: str | None = None):
    fixture = tmp / "ps.txt"
    fixture.write_text(fixture_text, encoding="utf-8")
    env = os.environ.copy()
    env["LIMEN_ROOT"] = str(tmp)
    if min_age is not None:
        env["LIMEN_ORPHAN_WATCHER_MIN_AGE"] = min_age
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--ps-fixture", str(fixture), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def journal_events(tmp: Path) -> list[dict]:
    path = tmp / "logs" / "session-lifecycle.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_watcher_with_live_claude_parent_is_not_orphan(tmp_path):
    table = CLAUDE_PARENT + "\n" + watcher_row(ppid=2501)
    proc = run(tmp_path, table, "--check")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "0 orphaned" in proc.stdout


def test_watcher_with_dead_parent_above_floor_is_orphan(tmp_path):
    proc = run(tmp_path, watcher_row(ppid=1, etime="45:00"), "--check")
    assert proc.returncode == 1
    assert "ORPHAN" in proc.stdout and "26294" in proc.stdout
    events = journal_events(tmp_path)
    assert events and events[-1]["event"] == "orphan-watchers"
    assert events[-1]["orphans"][0]["pid"] == 26294


def test_young_orphan_below_age_floor_is_spared(tmp_path):
    proc = run(tmp_path, watcher_row(ppid=1, etime="10:00"), "--check")  # 600s < 1800s floor
    assert proc.returncode == 0


def test_plain_sleep_is_not_a_watcher(tmp_path):
    proc = run(tmp_path, "999 1 99:00 sleep 45", "--check")
    assert proc.returncode == 0
    assert "0 watcher(s), 0 orphaned" in proc.stdout


def test_merge_policy_poller_is_a_watcher(tmp_path):
    row = watcher_row(ppid=1, etime="45:00", poll="bash scripts/merge-policy.sh 1075")
    proc = run(tmp_path, row, "--check")
    assert proc.returncode == 1


def test_await_pr_run_counts_as_watcher_and_orphans_past_floor(tmp_path):
    row = "500 1 45:00 bash /Users/u/Workspace/limen/scripts/await-pr.sh 7 --merge"
    proc = run(tmp_path, row, "--check")
    assert proc.returncode == 1
    lock_row = "501 1 45:00 mkdir /Users/u/Workspace/limen/logs/.await-pr-7.lock"
    assert run(tmp_path, lock_row, "--check").returncode == 0


def test_day_etime_parses_above_floor(tmp_path):
    proc = run(tmp_path, watcher_row(ppid=1, etime="2-01:00:10"), "--check")
    assert proc.returncode == 1


def test_min_age_env_override(tmp_path):
    proc = run(tmp_path, watcher_row(ppid=1, etime="10:00"), "--check", min_age="60")
    assert proc.returncode == 1


def test_session_end_always_exits_zero_and_journals(tmp_path):
    table = CLAUDE_PARENT + "\n" + watcher_row(ppid=2501, etime="05:00")
    proc = run(tmp_path, table, "--session-end", "--sid", "sess-42")
    assert proc.returncode == 0
    assert "watcher shell(s) still running" in proc.stderr
    events = journal_events(tmp_path)
    assert events[-1]["event"] == "session-end-watcher-audit"
    assert events[-1]["sid"] == "sess-42"
    assert events[-1]["watchers"][0]["pid"] == 26294
    clean = run(tmp_path, "999 1 05:00 sleep 45", "--session-end", "--sid", "sess-43")
    assert clean.returncode == 0 and clean.stderr == ""


def test_check_never_signals_and_reap_kills_only_orphans(tmp_path):
    victim = subprocess.Popen(["sleep", "300"], start_new_session=True)
    try:
        row = watcher_row(pid=victim.pid, ppid=1, etime="45:00")
        proc = run(tmp_path, row, "--check")
        assert proc.returncode == 1
        time.sleep(0.2)
        assert victim.poll() is None, "--check must never signal a process"

        proc = run(tmp_path, row, "--check", "--reap")
        assert proc.returncode == 1
        assert "REAPED" in proc.stdout
        deadline = time.time() + 5
        while time.time() < deadline and victim.poll() is None:
            time.sleep(0.1)
        assert victim.poll() is not None, "--reap must terminate the orphan"
        events = journal_events(tmp_path)
        assert any(e["event"] == "orphan-watcher-reaped" and e["pid"] == victim.pid for e in events)
    finally:
        if victim.poll() is None:
            os.killpg(victim.pid, signal.SIGKILL)
        victim.wait(timeout=10)
