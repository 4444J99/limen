"""Tests for scripts/check-fork-safety.py — the macOS 26.6 fork/os_log crash predicate.

Boundary and reports dir are injected (--since / --reports-dir) so the test is deterministic and
never touches the host's real ~/Library/Logs/DiagnosticReports. Crash time is a file mtime, set
via os.utime, so before/after-boundary is controlled precisely.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREDICATE = ROOT / "scripts" / "check-fork-safety.py"

BOUNDARY = 1_000_000_000  # arbitrary fixed epoch; before/after set relative to this
SIGNATURE_BODY = "Thread crashed ... nw_settings_child_has_forked ... _os_log_preferences_refresh\n"
BENIGN_BODY = "Thread crashed ... KeyError ... some other traceback\n"


def _ips(dir_path: Path, name: str, mtime: int, body: str = SIGNATURE_BODY) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    p = dir_path / name
    p.write_text(body, encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def run(reports_dir: Path, *extra, env=None):
    child_env = os.environ.copy()
    # Hermetic: pin LIMEN_ROOT to the real repo so a sibling test that leaks LIMEN_ROOT into
    # os.environ (e.g. test_async_dispatch) can't flip clause 1 (mitigation present). An explicit
    # env= (the mitigation-removed test) still overrides, since it is applied after.
    child_env["LIMEN_ROOT"] = str(ROOT)
    if env:
        child_env.update(env)
    return subprocess.run(
        [
            sys.executable,
            str(PREDICATE),
            "--check",
            "--reports-dir",
            str(reports_dir),
            "--since",
            str(BOUNDARY),
            *extra,
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=child_env,
    )


def test_green_when_only_pre_boundary_crashes(tmp_path):
    # A crash from BEFORE the mitigation is the known incident — not a recurrence.
    _ips(tmp_path, "Python-old.ips", BOUNDARY - 5000)
    r = run(tmp_path)
    assert r.returncode == 0, r.stdout
    assert "GREEN" in r.stdout
    assert "RECURRENCE" not in r.stdout


def test_red_on_post_boundary_recurrence(tmp_path):
    _ips(tmp_path, "Python-old.ips", BOUNDARY - 5000)
    _ips(tmp_path, "Python-new.ips", BOUNDARY + 5000)
    r = run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "RECURRENCE" in r.stdout
    assert "Python-new.ips" in r.stdout  # names the offender
    assert "LIMEN_FORK_SAFE" in r.stdout  # points at the escalation


def test_benign_post_boundary_crash_is_ignored(tmp_path):
    # A python crash after the boundary that does NOT match the atfork/os_log signature is not ours.
    _ips(tmp_path, "Python-benign.ips", BOUNDARY + 5000, body=BENIGN_BODY)
    r = run(tmp_path)
    assert r.returncode == 0, r.stdout
    assert "GREEN" in r.stdout


def test_retired_subdir_is_scanned(tmp_path):
    # macOS rotates old reports into Retired/ — a recurrence there must still be caught.
    _ips(tmp_path / "Retired", "Python-retired.ips", BOUNDARY + 5000)
    r = run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "Python-retired.ips" in r.stdout


def test_red_when_mitigation_removed(tmp_path):
    # Point LIMEN_ROOT at a tree with no beat scripts → clause 1 (mitigation present) fails.
    reports = tmp_path / "reports"
    _ips(reports, "Python-old.ips", BOUNDARY - 5000)  # clause 2 clean
    fake_root = tmp_path / "root"
    (fake_root / "scripts").mkdir(parents=True)
    r = run(reports, env={"LIMEN_ROOT": str(fake_root)})
    assert r.returncode == 1, r.stdout
    assert "mitigation MISSING" in r.stdout


def test_no_pii_only_names_and_frames(tmp_path):
    # The report must never echo crash-report bodies — only basenames/frames/times.
    _ips(tmp_path, "Python-new.ips", BOUNDARY + 5000, body="SECRET_TOKEN=hunter2 ... nw_settings_child_has_forked\n")
    r = run(tmp_path)
    assert "hunter2" not in r.stdout
    assert "Python-new.ips" in r.stdout
