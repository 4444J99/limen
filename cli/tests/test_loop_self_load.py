"""The loop-body self-load rung — a merged rung must load itself, exactly once, and never blindly.

``heartbeat-loop.sh`` is a ``while true`` loop, so it never re-reads its own script: a merged rung
sits on disk inert until the process restarts. launchd does not cover this — ``KeepAlive`` restarts
on EXIT and this loop never exits, so the daemon can outlive its own wiring indefinitely.

Three touchpoints existed for that fact and none of them ACTED: ``sync-release.sh`` sets
``logs/.loop-update-pending`` on a loop-body fast-forward, ``enactment-audit.py`` reports it RED with
the exact kickstart command, and the loop clears it at startup. The flag was cleared by the very
restart it was meant to cause and nothing caused that restart. Measured 2026-08-07: the
board-publication rung (#2016) merged, fast-forwarded onto disk, and stayed dark behind a daemon
5h15m older than its own wiring — the repair for a 12-day board freeze shipped and did not run.

The rung is tested by EXTRACTING it from the shipped script and executing it against a stub
``launchctl``, rather than by asserting on its source text. A grep-based test would pass on a rung
whose guards had been reordered into uselessness; this one runs the real bytes and observes the real
decision. The effector is a stub because the alternative is restarting the operator's daemon inside
a test run.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LOOP = ROOT / "scripts" / "heartbeat-loop.sh"

GUARD_OPEN = 'if [ "${LIMEN_LOOP_SELF_KICKSTART:-1}" = "1" ] && [ -f "$LIMEN_ROOT/logs/.loop-update-pending" ]; then'


def _rung_source() -> str:
    """The shipped rung, lifted verbatim from the loop body.

    Anchored on the guard's own opening line and closed at the next dedent to two spaces, which is
    the loop body's own indent level. If the rung is ever restructured this raises rather than
    silently testing an empty string — a test that quietly stops covering anything is worse than a
    failing one.
    """
    lines = LOOP.read_text().splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == GUARD_OPEN), None)
    assert start is not None, f"guard line not found in {LOOP} — did the rung move?"
    for end in range(start + 1, len(lines)):
        if lines[end] == "  fi":
            return "\n".join(line[2:] if line.startswith("  ") else line for line in lines[start : end + 1])
    raise AssertionError("rung's closing `fi` not found at loop-body indent")


def _run(tmp_path: Path, *, marker: bool, label: str, managed: bool, enabled: str = "1") -> tuple[str, list[str]]:
    """Execute the real rung with a stub launchctl; return (stdout, argv-lines the stub recorded)."""
    root = tmp_path / "root"
    (root / "logs").mkdir(parents=True)
    if marker:
        (root / "logs" / ".loop-update-pending").touch()

    bindir = tmp_path / "bin"
    bindir.mkdir()
    listing = label if managed else "com.something.else"
    stub = bindir / "launchctl"
    # `list` answers the managed-or-not question; every other subcommand (i.e. kickstart) is recorded
    # instead of performed. Recording argv is the point: a wrong domain or a missing -k would restart
    # nothing, or the wrong thing, and still look green.
    stub.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "list" ]; then printf "%s\\n" ' + f'"{listing}"' + "; exit 0; fi\n"
        f'printf "%s\\n" "$*" >> "{tmp_path}/argv.log"\n'
        "exit 0\n"
    )
    stub.chmod(0o755)

    script = tmp_path / "rung.sh"
    script.write_text("set -u\n" + _rung_source() + "\n")

    proc = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{bindir}:/usr/bin:/bin",
            "LIMEN_ROOT": str(root),
            "LIMEN_HEARTBEAT_LABEL": label,
            "LIMEN_LOOP_SELF_KICKSTART": enabled,
            # The shipped default is a 5s settle window for launchd's SIGTERM. Paying it four times
            # over would make this suite slow for no information at all.
            "LIMEN_LOOP_KICKSTART_SETTLE": "0",
        },
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    argv_log = tmp_path / "argv.log"
    recorded = argv_log.read_text().splitlines() if argv_log.is_file() else []
    marker_left = (root / "logs" / ".loop-update-pending").is_file()
    return proc.stdout + f"\n[marker_left={marker_left}]", recorded


def test_no_marker_is_a_silent_no_op(tmp_path: Path) -> None:
    """The overwhelmingly common case. A rung that logs every beat trains people to ignore it."""
    out, recorded = _run(tmp_path, marker=False, label="com.limen.heartbeat", managed=True)
    assert recorded == []
    assert "self-load" not in out


def test_a_pending_marker_kickstarts_the_managed_label(tmp_path: Path) -> None:
    """The whole point: the loop reloads itself instead of waiting on a human reading a log line."""
    out, recorded = _run(tmp_path, marker=True, label="com.limen.heartbeat", managed=True)
    assert "kickstart com.limen.heartbeat" in out
    assert len(recorded) == 1
    # -k is what makes it a RESTART rather than a start-if-stopped; the gui/<uid> domain is what
    # reaches a LaunchAgent at all. Both are silent failures if wrong.
    assert recorded[0].startswith("kickstart -k gui/")
    assert recorded[0].endswith("/com.limen.heartbeat")


def test_an_unmanaged_label_never_kickstarts_and_stops_re_logging(tmp_path: Path) -> None:
    """A hand-run loop has no label to restart. It must not print the same impossible advice forever."""
    out, recorded = _run(tmp_path, marker=True, label="com.limen.heartbeat", managed=False)
    assert recorded == []
    assert "not launchd-managed" in out
    assert "[marker_left=False]" in out, "the marker must be cleared or this logs every beat forever"


def test_the_kill_switch_wins_over_a_pending_marker(tmp_path: Path) -> None:
    """Set 0 and nothing happens — including no marker clear, so the signal survives for a human."""
    out, recorded = _run(tmp_path, marker=True, label="com.limen.heartbeat", managed=True, enabled="0")
    assert recorded == []
    assert "self-load" not in out
    assert "[marker_left=True]" in out


def test_the_label_is_not_hardcoded_past_the_env(tmp_path: Path) -> None:
    """A wrong label must restart nothing rather than fall back to the real daemon's name."""
    out, recorded = _run(tmp_path, marker=True, label="com.example.other", managed=True)
    assert len(recorded) == 1
    assert recorded[0].endswith("/com.example.other")
    assert "com.limen.heartbeat" not in out


def test_the_startup_clear_still_exists_because_it_is_what_bounds_the_rung(tmp_path: Path) -> None:
    """The rung has no counter; the startup clear is its ONLY bound.

    ``heartbeat-loop.sh`` removes the marker before entering the loop, so the restart destroys its own
    trigger and the rung fires at most once per loop-body change. Delete that line and this rung
    becomes a restart loop, so it is asserted here rather than trusted.
    """
    text = LOOP.read_text()
    clear = 'rm -f "$LIMEN_ROOT/logs/.loop-update-pending"'
    assert clear in text
    assert text.index(clear) < text.index("while true; do"), "the clear must run BEFORE the loop"


@pytest.mark.parametrize("subcommand", ["kickstart"])
def test_the_rung_only_ever_asks_launchctl_to_kickstart(tmp_path: Path, subcommand: str) -> None:
    """No bootout, no unload, no stop — a restart is the whole authority this rung takes."""
    _, recorded = _run(tmp_path, marker=True, label="com.limen.heartbeat", managed=True)
    assert all(line.split()[0] == subcommand for line in recorded), recorded


def test_the_extractor_fails_loudly_if_the_rung_moves() -> None:
    """Guards the test itself: a silently-empty extraction would make every case above vacuous."""
    source = _rung_source()
    assert "launchctl kickstart -k" in source
    assert source.count("launchctl") == 2, "expect exactly the `list` probe and the `kickstart` effector"


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
