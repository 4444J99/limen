"""Tests for scripts/backblaze-exclusions.py — the L-BACKBLAZE-EXCLUDE completion predicate.

Hermetic: every case runs against a fixture bzinfo.xml in tmp, never the live
/Library/Backblaze.bzpkg state.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "backblaze-exclusions.py"

ALL_REQUIRED = (
    "/users/4jp/workspace/limen/.claude/worktrees/",
    "/users/4jp/workspace/limen/.venv/",
    "/users/4jp/workspace/limen/cli/.venv/",
    "/users/4jp/.ollama/models/",
)


def run_check(bzinfo: Path, *extra: str):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--bzinfo", str(bzinfo), *extra],
        capture_output=True,
        text=True,
    )


def write_bzinfo(tmp_path: Path, dirs: tuple[str, ...]) -> Path:
    filters = "\n".join(f'  <bzdirfilter dir="{d}" whichfiles="none" />' for d in dirs)
    p = tmp_path / "bzinfo.xml"
    p.write_text(f"<bzinfo>\n{filters}\n</bzinfo>\n")
    return p


def test_all_present_is_green(tmp_path):
    proc = run_check(write_bzinfo(tmp_path, ALL_REQUIRED))
    assert proc.returncode == 0, proc.stdout
    assert "ok" in proc.stdout


def test_missing_entries_fail_and_are_named(tmp_path):
    proc = run_check(write_bzinfo(tmp_path, ALL_REQUIRED[:1]))
    assert proc.returncode == 1
    assert "L-BACKBLAZE-EXCLUDE" in proc.stdout
    assert "/users/4jp/.ollama/models/" in proc.stdout


def test_parent_prefix_covers_children(tmp_path):
    # excluding the whole limen tree + ollama satisfies the three limen entries beneath it
    proc = run_check(write_bzinfo(tmp_path, ("/users/4jp/workspace/limen/", "/users/4jp/.ollama/")))
    assert proc.returncode == 0, proc.stdout


def test_case_and_trailing_slash_normalized(tmp_path):
    mixed = tuple(d.upper().rstrip("/") for d in ALL_REQUIRED)
    proc = run_check(write_bzinfo(tmp_path, mixed))
    assert proc.returncode == 0, proc.stdout


def test_whichfiles_all_does_not_count(tmp_path):
    filters = "\n".join(f'  <bzdirfilter dir="{d}" whichfiles="all" />' for d in ALL_REQUIRED)
    p = tmp_path / "bzinfo.xml"
    p.write_text(f"<bzinfo>\n{filters}\n</bzinfo>\n")
    proc = run_check(p)
    assert proc.returncode == 1  # present but NOT excluded


def test_absent_file_fails_open(tmp_path):
    proc = run_check(tmp_path / "nope.xml")
    assert proc.returncode == 0
    assert "unknown" in proc.stdout


def test_malformed_xml_fails_open(tmp_path):
    p = tmp_path / "bzinfo.xml"
    p.write_text("<bzinfo><unclosed")
    proc = run_check(p)
    assert proc.returncode == 0
    assert "unknown" in proc.stdout


def test_json_report_shape(tmp_path):
    proc = run_check(write_bzinfo(tmp_path, ALL_REQUIRED[:2]), "--json")
    report = json.loads(proc.stdout)
    assert report["status"] == "missing"
    assert "/users/4jp/.ollama/models/" in report["missing"]
    assert proc.returncode == 1
