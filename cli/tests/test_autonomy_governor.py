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
    (logs / "autonomy-policy.json").write_text(
        json.dumps({"mode": "observe", "dispatch_enabled": False})
    )
    proc = run_governor(tmp_path, "dispatch-ok")
    assert proc.returncode == 2
    assert "autonomy mode is observe" in proc.stdout

    (logs / "autonomy-policy.json").write_text(
        json.dumps({"mode": "dispatch", "dispatch_enabled": False})
    )
    proc = run_governor(tmp_path, "dispatch-ok")
    assert proc.returncode == 2
    assert "dispatch_enabled is false" in proc.stdout


def test_dispatch_ok_blocks_when_primary_paid_lanes_are_dead(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "autonomy-policy.json").write_text(
        json.dumps({"mode": "dispatch", "dispatch_enabled": True})
    )
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
    (logs / "autonomy-policy.json").write_text(
        json.dumps({"mode": "dispatch", "dispatch_enabled": True})
    )
    (logs / "usage.json").write_text(
        json.dumps({"vendors": {"codex": {"health": "ok"}, "claude": {"health": "ok"}}})
    )
    proc = run_governor(tmp_path, "dispatch-ok")
    assert proc.returncode == 0
    assert "dispatch allowed" in proc.stdout
