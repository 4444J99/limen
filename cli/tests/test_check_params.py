"""Tests for the no-hardcode gate (scripts/check-params.py, VIGILIA build #3)."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-params.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_params", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_normalize_strips_trailing_underscore():
    cp = _load()
    assert cp.normalize("LIMEN_BEAT_") == "LIMEN_BEAT"
    assert cp.normalize("LIMEN_X") == "LIMEN_X"


def test_compute_undeclared_excludes_declared_and_external():
    cp = _load()
    referenced = {"LIMEN_A", "LIMEN_B", "DISABLE_AUTOUPDATER"}
    declared = {"LIMEN_A"}
    assert cp.compute_undeclared(referenced, declared) == {"LIMEN_B"}


def test_panel_integrity_flags_missing_fields():
    cp = _load()
    errs = cp.panel_integrity_errors("parameters:\n  FOO:\n    default: 1\n")
    assert any("missing 'env'" in e for e in errs)
    assert any("missing 'owner'" in e for e in errs)


def test_panel_integrity_clean():
    cp = _load()
    text = "parameters:\n  FOO:\n    default: 1\n    env: FOO\n    owner: x\n"
    assert cp.panel_integrity_errors(text) == []


def test_panel_integrity_detects_duplicate_key():
    cp = _load()
    text = (
        "parameters:\n"
        "  FOO:\n    default: 1\n    env: FOO\n    owner: x\n"
        "  FOO:\n    default: 2\n    env: FOO\n    owner: x\n"
    )
    assert any("duplicate param key: FOO" in e for e in cp.panel_integrity_errors(text))


def test_gate_passes_on_repo():
    # the committed baseline must keep the gate green (no new hardcodes vs baseline).
    r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
