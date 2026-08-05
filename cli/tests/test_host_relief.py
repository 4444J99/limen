"""Tests for scripts/host-relief.py — the SHED effector (IF-HOST-PRESSURE form 4).

Hermetic: ps/launchctl fixtures + --gate-action override; fixtures force plan-only
behavior so no test can ever kickstart a real agent, and LIMEN_NOTIFY=0 keeps the
dedup bookkeeping without popping notifications.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "host-relief.py"

# The 2026-07-16 incident, as a ps fixture (rss column is KiB):
#   overnight-watch at 3.1 GiB (over the 1024 MB ceiling), bztransmit at 8.6 GiB (root hog),
#   heartbeat healthy, a big non-root browser that must NOT be flagged.
PS_FIXTURE = """\
28017 4jp 3267776 /opt/homebrew/bin/python3 /Users/4jp/Workspace/limen/scripts/overnight-watch.py
10899 root 9000000 /Library/Backblaze.bzpkg/bztransmit -updatebackupstats
32082 4jp 20480 /bin/bash /Users/4jp/Workspace/limen/scripts/heartbeat-loop.sh
40001 4jp 5300000 /Applications/Chrome.app/Contents/MacOS/Chrome
1 root 13824 /sbin/launchd
"""

LAUNCHCTL_FIXTURE = """\
28017\t1\tcom.limen.overnight-watch
32082\t0\tcom.limen.heartbeat
-\t0\tcom.limen.creds-hydrate
598\t0\tcom.apple.WindowServer
"""


def run_relief(tmp_path: Path, *extra: str):
    ps = tmp_path / "ps.txt"
    lc = tmp_path / "launchctl.txt"
    if not ps.exists():
        ps.write_text(PS_FIXTURE)
        lc.write_text(LAUNCHCTL_FIXTURE)
    env = os.environ.copy()
    env["LIMEN_ROOT"] = str(tmp_path)
    env["LIMEN_NOTIFY"] = "0"
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--ps-fixture",
            str(ps),
            "--launchctl-fixture",
            str(lc),
            "--json",
            *extra,
        ],
        capture_output=True,
        text=True,
        env=env,
    )


def test_shed_plans_kickstart_for_over_ceiling_agent(tmp_path):
    proc = run_relief(tmp_path, "--gate-action", "shed", "--check")
    report = json.loads(proc.stdout)
    assert proc.returncode == 0, proc.stdout
    assert report["relieve"] is True
    labels = [item["label"] for item in report["over_ceiling"]]
    assert labels == ["com.limen.overnight-watch"]  # 3.1 GiB > 1024 MB; heartbeat at 20 MB untouched
    assert report["kickstarts"][0]["planned"] is True
    assert "com.limen.overnight-watch" in report["kickstarts"][0]["target"]


def test_root_hog_escalated_with_preformed_one_liner(tmp_path):
    proc = run_relief(tmp_path, "--gate-action", "shed", "--check")
    report = json.loads(proc.stdout)
    hogs = report["root_hogs"]
    assert [h["pid"] for h in hogs] == [10899]  # bztransmit; launchd (pid 1) and non-root Chrome excluded
    assert hogs[0]["one_liner"] == "sudo kill 10899"
    assert "root-hog-10899" in report["notified"]


def test_apply_with_fixtures_stays_plan_only(tmp_path):
    proc = run_relief(tmp_path, "--gate-action", "shed", "--apply")
    report = json.loads(proc.stdout)
    assert proc.returncode == 0
    assert all(k.get("planned") for k in report["kickstarts"])  # fixtures never cause side effects


def test_ok_gate_stands_by_and_clears_conditions(tmp_path):
    # onset under shed...
    first = json.loads(run_relief(tmp_path, "--gate-action", "shed", "--check").stdout)
    assert "shed-onset" in first["notified"]
    # ...dedup on repeat...
    second = json.loads(run_relief(tmp_path, "--gate-action", "shed", "--check").stdout)
    assert second["notified"] == []
    # ...ok clears shed-onset (root hog keys clear when the hog is gone), so a future onset re-fires
    ok = json.loads(run_relief(tmp_path, "--gate-action", "ok", "--check").stdout)
    assert ok["relieve"] is False
    assert ok["root_hogs"] == []  # gate ok — hogs are not escalated outside pressure
    third = json.loads(run_relief(tmp_path, "--gate-action", "shed", "--check").stdout)
    assert "shed-onset" in third["notified"]


def test_throttle_reports_but_does_not_relieve(tmp_path):
    report = json.loads(run_relief(tmp_path, "--gate-action", "throttle", "--check").stdout)
    assert report["relieve"] is False
    assert report["kickstarts"] == []
    # visibility is preserved: the over-ceiling census still names the bloated agent
    assert [i["label"] for i in report["over_ceiling"]] == ["com.limen.overnight-watch"]
    # and a root hog under pressure (gate != ok) is still escalated
    assert [h["pid"] for h in report["root_hogs"]] == [10899]


def test_notify_state_written_under_limen_root(tmp_path):
    run_relief(tmp_path, "--gate-action", "shed", "--check")
    state = json.loads((tmp_path / "logs" / "vigilia" / "relief-state.json").read_text())
    assert "shed-onset" in state and "root-hog-10899" in state
