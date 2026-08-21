import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_notification_registry_and_heartbeat_ownership_are_total():
    result = subprocess.run(
        [sys.executable, "scripts/check-notification-registry.py"], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_forbidden_heartbeat_plist_and_generator_are_absent():
    assert not (ROOT / "container" / "launchd" / "com.limen.heartbeat.plist").exists()
    assert not (ROOT / "container" / "launchd" / "com.limen.heartbeat.plist.tmpl").exists()
    assert not (ROOT / "scripts" / "gen-launchd-plist.sh").exists()
