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


def test_compute_orphans_flags_declared_but_unread_limen_param():
    # The LIMEN_RECLAIM_PUSHED_OK class: declared in the panel, read by no source → orphan.
    cp = _load()
    panel = {"parameters": {"LIMEN_KNOB": {"env": "LIMEN_KNOB", "default": "0", "owner": "x"}}}
    assert cp.compute_orphans(panel, referenced_wide=set()) == {"LIMEN_KNOB"}


def test_compute_orphans_clears_when_param_is_read():
    cp = _load()
    panel = {"parameters": {"LIMEN_KNOB": {"env": "LIMEN_KNOB", "default": "0", "owner": "x"}}}
    assert cp.compute_orphans(panel, referenced_wide={"LIMEN_KNOB"}) == set()


def test_compute_orphans_skips_non_limen_namespaces():
    # A non-LIMEN param (VITALS_/INSTITVTIO_) is out of scope — the LIMEN_* scanner cannot see it.
    cp = _load()
    panel = {"parameters": {"VITALS_GAUGE": {"env": "VITALS_GAUGE", "default": "1", "owner": "x"}}}
    assert cp.compute_orphans(panel, referenced_wide=set()) == set()


def test_compute_orphans_respects_external_allow():
    cp = _load()
    # a LIMEN_ param whose only name is in EXTERNAL_ALLOW is not an orphan
    panel = {"parameters": {"K": {"env": "LIMEN_EXT", "default": "0", "owner": "x"}}}
    cp.EXTERNAL_ALLOW = cp.EXTERNAL_ALLOW | {"LIMEN_EXT"}
    assert cp.compute_orphans(panel, referenced_wide=set()) == set()


def test_referenced_tokens_treats_executable_registry_file_as_a_reader(tmp_path):
    cp = _load()
    registry = tmp_path / "institutio" / "governance" / "sensors.yaml"
    registry.parent.mkdir(parents=True)
    registry.write_text("cadence: {env: LIMEN_RENAMED_SENSOR_CADENCE, default: 4}\n", encoding="utf-8")
    assert cp.referenced_tokens(tmp_path, dirs=("institutio/governance/sensors.yaml",)) == {
        "LIMEN_RENAMED_SENSOR_CADENCE"
    }


def test_gate_passes_on_repo():
    # the committed baseline must keep the gate green (no new hardcodes AND no new orphans vs baseline).
    r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
