import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GOVERNOR = ROOT / "scripts" / "autonomy-governor.py"


def run_governor(tmp_path, *args):
    return subprocess.run(
        [sys.executable, str(GOVERNOR), *args],
        capture_output=True,
        text=True,
        env={"LIMEN_ROOT": str(tmp_path)},
    )


def test_missing_policy_defaults_to_observe(tmp_path):
    proc = run_governor(tmp_path, "mode")
    assert proc.returncode == 0
    assert proc.stdout.strip() == "observe"
    assert (tmp_path / "logs" / "autonomy-policy.json").exists()


def test_dispatch_ok_requires_dispatch_mode_and_flag(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "autonomy-policy.json").write_text(json.dumps({"mode": "observe", "dispatch_enabled": False}))
    proc = run_governor(tmp_path, "dispatch-ok")
    assert proc.returncode == 2
    assert "autonomy mode is observe" in proc.stdout

    (logs / "autonomy-policy.json").write_text(json.dumps({"mode": "dispatch", "dispatch_enabled": False}))
    proc = run_governor(tmp_path, "dispatch-ok")
    assert proc.returncode == 2
    assert "dispatch_enabled is false" in proc.stdout


def test_dispatch_ok_blocks_when_primary_paid_lanes_are_dead(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "autonomy-policy.json").write_text(json.dumps({"mode": "dispatch", "dispatch_enabled": True}))
    (logs / "usage.json").write_text(
        json.dumps(
            {
                "vendors": {
                    "codex": {"health": "exhausted"},
                    "claude": {"health": "rate-limited"},
                    "jules": {"health": "exhausted"},
                    "agy": {"health": "ok"},
                }
            }
        )
    )
    proc = run_governor(tmp_path, "dispatch-ok")
    assert proc.returncode == 2
    assert "primary paid lanes exhausted" in proc.stdout


def test_dispatch_ok_allows_dispatch_mode_with_headroom(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "autonomy-policy.json").write_text(json.dumps({"mode": "dispatch", "dispatch_enabled": True}))
    (logs / "usage.json").write_text(json.dumps({"vendors": {"codex": {"health": "ok"}, "claude": {"health": "ok"}}}))
    proc = run_governor(tmp_path, "dispatch-ok")
    assert proc.returncode == 0
    assert "dispatch allowed" in proc.stdout


def _fake_gh(tmp_path, script_body):
    """Install a fake `gh` on PATH so the marker autoclear's subprocess calls are hermetic."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text("#!/bin/bash\n" + script_body)
    gh.chmod(0o755)
    return bin_dir


def run_governor_with_gh(tmp_path, gh_body, *args):
    bin_dir = _fake_gh(tmp_path, gh_body)
    return subprocess.run(
        [sys.executable, str(GOVERNOR), *args],
        capture_output=True,
        text=True,
        env={
            "LIMEN_ROOT": str(tmp_path),
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "LIMEN_AUTONOMY_MARKER_RECHECK_SECS": "0",
        },
    )


def test_marker_pr_line_autoclears_when_that_pr_merged(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "autonomy-policy.json").write_text(json.dumps({"mode": "dispatch", "dispatch_enabled": True}))
    (logs / "AUTONOMY_PAUSED").write_text("reason: safety gate\nowner: manual/hand-written-label-20260714\npr: 1036\n")
    # fake gh: `pr view 1036 --json state` -> MERGED; the owner --head search would find nothing
    body = 'if [ "$1" = "pr" ] && [ "$2" = "view" ]; then echo \'{"state":"MERGED"}\'; else echo "[]"; fi'
    proc = run_governor_with_gh(tmp_path, body, "mode")
    assert proc.stdout.strip() == "dispatch"
    assert not (logs / "AUTONOMY_PAUSED").exists()


def test_marker_hand_written_owner_alone_stays_paused(tmp_path):
    # The 2026-07-15 recurrence: owner label matches no branch; without a pr: line the
    # autoclear must stay fail-closed.
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "autonomy-policy.json").write_text(json.dumps({"mode": "dispatch", "dispatch_enabled": True}))
    (logs / "AUTONOMY_PAUSED").write_text("reason: safety gate\nowner: manual/hand-written-label-20260714\n")
    body = 'echo "[]"'
    proc = run_governor_with_gh(tmp_path, body, "mode")
    assert proc.stdout.strip() == "paused"
    assert (logs / "AUTONOMY_PAUSED").exists()


def test_marker_pr_line_unmerged_stays_paused(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "autonomy-policy.json").write_text(json.dumps({"mode": "dispatch", "dispatch_enabled": True}))
    (logs / "AUTONOMY_PAUSED").write_text("reason: safety gate\npr: 1036\n")
    body = 'if [ "$1" = "pr" ] && [ "$2" = "view" ]; then echo \'{"state":"OPEN"}\'; else echo "[]"; fi'
    proc = run_governor_with_gh(tmp_path, body, "mode")
    assert proc.stdout.strip() == "paused"
    assert (logs / "AUTONOMY_PAUSED").exists()
