"""The retired heartbeat may not revive itself."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_heartbeat_loop_has_no_self_kickstart() -> None:
    source = (ROOT / "scripts" / "heartbeat-loop.sh").read_text()
    assert "LIMEN_LOOP_SELF_KICKSTART" not in source
    assert "self-load-kickstart" not in source
    assert "launchctl kickstart" not in source


def test_retired_plists_are_not_shipped() -> None:
    launchd = ROOT / "container" / "launchd"
    assert not (launchd / "com.limen.heartbeat.plist").exists()
    assert not (launchd / "com.limen.watchdog.plist").exists()
