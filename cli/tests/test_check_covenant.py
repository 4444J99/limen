"""Tests for scripts/check-covenant.py — the record-keeper covenant drift predicate.

The real registry must pass GREEN in its PENDING posture (memory lane not yet landed, the
write-guard unarmed). The synthetic-violator fixtures exercise check D (no-other-writer) via
--scan-root, so the tests never touch the real memory dir.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
CHECK = SCRIPTS / "check-covenant.py"
REGISTRY = ROOT / "institutio" / "governance" / "covenant.yaml"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import covenant  # noqa: E402


def run(*extra):
    # Pin LIMEN_ROOT to the real repo root so an ambient profile value can't misdirect the
    # registry lookup; the subprocess resolves covenant.yaml under this worktree.
    env = {**os.environ, "LIMEN_ROOT": str(ROOT)}
    return subprocess.run([sys.executable, str(CHECK), *extra], capture_output=True, text=True, env=env)


def _mod():
    spec = importlib.util.spec_from_file_location("check_covenant_under_test", CHECK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_registry_loads_and_schema_passes():
    entries = covenant.covenant_entries(REGISTRY)
    assert set(entries) == {"memory", "board"}
    mod = _mod()
    assert mod.check_schema(entries) == []


def test_resolve_memory_dir_honors_override(monkeypatch, tmp_path):
    override = tmp_path / "mem"
    monkeypatch.setenv("LIMEN_MEMORY_DIR", str(override))
    assert covenant.resolve_memory_dir() == override


def test_resolve_memory_dir_default_is_out_of_repo(monkeypatch):
    monkeypatch.delenv("LIMEN_MEMORY_DIR", raising=False)
    monkeypatch.setenv("LIMEN_WORKDIR", "/Users/x/Workspace/limen")
    resolved = covenant.resolve_memory_dir()
    assert resolved == Path.home() / ".claude" / "projects" / "-Users-x-Workspace-limen" / "memory"


def test_out_of_repo_safety_skips_green_when_dir_absent(monkeypatch, tmp_path):
    # Point the memory dir at a path that does not exist → check F must not raise or fail.
    monkeypatch.setenv("LIMEN_MEMORY_DIR", str(tmp_path / "does-not-exist"))
    mod = _mod()
    entries = covenant.covenant_entries(REGISTRY)
    assert mod.check_out_of_repo_safety(entries) == []


def test_no_other_writer_clean_tree_passes(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True)
    # An innocuous module that writes something unrelated — no memory token, no violation.
    (scripts / "innocent.py").write_text(
        "from pathlib import Path\n\n\ndef go():\n    Path('/tmp/out.txt').write_text('hi')\n",
        encoding="utf-8",
    )
    mod = _mod()
    assert mod.check_no_other_writer(tmp_path) == []


def test_no_other_writer_catches_synthetic_violator(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True)
    # A module that writes MEMORY.md — an unlisted memory writer the scan must flag.
    (scripts / "rogue.py").write_text(
        "from pathlib import Path\n\n\n"
        "def leak(memdir):\n"
        "    Path(memdir, 'MEMORY.md').write_text('- a session wrote me directly\\n')\n",
        encoding="utf-8",
    )
    mod = _mod()
    errors = mod.check_no_other_writer(tmp_path)
    assert any("scripts/rogue.py" in e for e in errors), errors


def test_no_other_writer_allowlisted_writer_is_ignored(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True)
    # The same rogue write, but at an allowlisted path → tolerated.
    (scripts / "memory-ticket.py").write_text(
        "from pathlib import Path\n\n\ndef leak(memdir):\n    Path(memdir, 'MEMORY.md').write_text('legit\\n')\n",
        encoding="utf-8",
    )
    mod = _mod()
    assert mod.check_no_other_writer(tmp_path) == []


def test_pending_posture_is_green_end_to_end():
    # The real repo: memory lane not landed, write-guard unarmed → the whole predicate is GREEN.
    r = run()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "record-keeper covenant verified" in r.stdout
    assert "lane PENDING" in r.stdout
    assert "guard PENDING" in r.stdout
