"""Tests for scripts/backblaze-exclusions.py — the organ-owned exclusion estate.

Hermetic: every case runs against a fixture bzinfo.xml in tmp, never the live
/Library/Backblaze.bzpkg state.
"""

from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "backblaze-exclusions.py"

ALL_REQUIRED = (
    "/users/4jp/workspace/limen/.claude/worktrees/",
    "/users/4jp/workspace/.limen-worktrees/",
    "/users/4jp/workspace/limen-worktrees/",
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


def run_apply(bzinfo: Path, *extra: str):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--apply", "--bzinfo", str(bzinfo), *extra],
        capture_output=True,
        text=True,
    )


def write_bzinfo(tmp_path: Path, dirs: tuple[str, ...]) -> Path:
    filters = "\n".join(f'  <bzdirfilter dir="{d}" whichfiles="none" />' for d in dirs)
    p = tmp_path / "bzinfo.xml"
    p.write_text(f"<bzinfo>\n{filters}\n</bzinfo>\n")
    return p


def write_bzinfo_do_backup(tmp_path: Path, dirs: tuple[str, ...]) -> Path:
    """The live-file shape: filters inside <do_backup>, catch-all terminator on the close line."""
    filters = "".join(f'    <bzdirfilter dir="{d}" whichfiles="none" />\n' for d in dirs)
    p = tmp_path / "bzinfo.xml"
    p.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<bzinfo>\n  <do_backup>\n'
        f'{filters}    <bzdirfilter dir="/" whichfiles="all" /></do_backup>\n</bzinfo>\n'
    )
    return p


def test_all_present_is_green(tmp_path):
    proc = run_check(write_bzinfo(tmp_path, ALL_REQUIRED))
    assert proc.returncode == 0, proc.stdout
    assert "ok" in proc.stdout


def test_missing_entries_fail_and_name_the_effector(tmp_path):
    proc = run_check(write_bzinfo(tmp_path, ALL_REQUIRED[:1]))
    assert proc.returncode == 1
    assert "--apply" in proc.stdout
    assert "/users/4jp/.ollama/models/" in proc.stdout


def test_parent_prefix_covers_children(tmp_path):
    # excluding the whole workspace tree + ollama satisfies every entry beneath them
    proc = run_check(write_bzinfo(tmp_path, ("/users/4jp/workspace/", "/users/4jp/.ollama/")))
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


# ── --apply: the organ-owned effector ──────────────────────────────────────────


def test_apply_inserts_missing_before_catchall(tmp_path):
    p = write_bzinfo_do_backup(tmp_path, ALL_REQUIRED[:1])
    proc = run_apply(p)
    assert proc.returncode == 0, proc.stdout
    assert "applied" in proc.stdout
    # result is valid XML, fully green, and the catch-all is still the LAST dirfilter
    root = ET.parse(p).getroot()
    dirs = [el.get("dir") for el in root.iter("bzdirfilter")]
    assert dirs[-1] == "/"
    assert run_check(p).returncode == 0
    backups = list(tmp_path.glob("bzinfo.xml.limen-bak-*"))
    assert len(backups) == 1


def test_apply_is_idempotent_noop_when_green(tmp_path):
    p = write_bzinfo_do_backup(tmp_path, ALL_REQUIRED)
    before = p.read_bytes()
    proc = run_apply(p)
    assert proc.returncode == 0, proc.stdout
    assert "ok" in proc.stdout
    assert p.read_bytes() == before
    assert not list(tmp_path.glob("bzinfo.xml.limen-bak-*"))  # no write, no backup


def test_apply_twice_adds_nothing_twice(tmp_path):
    p = write_bzinfo_do_backup(tmp_path, ())
    assert run_apply(p).returncode == 0
    after_first = p.read_bytes()
    assert run_apply(p).returncode == 0
    assert p.read_bytes() == after_first


def test_apply_absent_file_fails_open(tmp_path):
    proc = run_apply(tmp_path / "nope.xml")
    assert proc.returncode == 0
    assert "unknown" in proc.stdout


def test_apply_readonly_file_is_blocked_and_untouched(tmp_path):
    p = write_bzinfo_do_backup(tmp_path, ALL_REQUIRED[:1])
    before = p.read_bytes()
    p.chmod(0o444)
    try:
        proc = run_apply(p)
        assert proc.returncode == 1
        assert "BLOCKED" in proc.stdout
        assert p.read_bytes() == before
    finally:
        p.chmod(0o644)


def test_apply_without_catchall_is_blocked_and_untouched(tmp_path):
    p = write_bzinfo(tmp_path, ALL_REQUIRED[:1])  # no do_backup/catch-all shape
    before = p.read_bytes()
    proc = run_apply(p)
    assert proc.returncode == 1
    assert "BLOCKED" in proc.stdout
    assert p.read_bytes() == before


def test_apply_json_shape(tmp_path):
    p = write_bzinfo_do_backup(tmp_path, ALL_REQUIRED[:1])
    proc = run_apply(p, "--json")
    report = json.loads(proc.stdout)
    assert report["status"] == "applied"
    assert set(report["added"]) == set(ALL_REQUIRED[1:])
    assert report["missing"] == []
    assert proc.returncode == 0
