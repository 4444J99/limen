"""Tests for scripts/beat-sensors.py — the SENSORS registry runner.

Loads the script via importlib (hyphenated filename) and drives it against a fixture registry, so the
tests never execute the real beat sensors.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "beat-sensors.py"

FIXTURE = """\
schema_version: 0.1
sensors:
  alpha:
    section: "0a"
    title: "alpha check"
    gate: LIMEN_ALPHA
    default: "1"
    source: [metabolize]
    steps:
      - command: "python3 scripts/alpha.py"
        severity: advisory
        escalation: "alpha failed"
  beta:
    section: "0b"
    title: "beta check"
    gate: LIMEN_BETA
    default: "0"
    source: [metabolize]
    steps:
      - command: "python3 scripts/beta.py"
        severity: silent
        escalation: "beta skipped"
  gamma:
    section: "0c"
    title: "gamma heartbeat-only"
    gate: null
    default: "1"
    source: [heartbeat]
    steps:
      - command: "python3 scripts/gamma.py"
        when_env: LIMEN_GAMMA_ON
        severity: advisory
        escalation: "gamma failed"
"""


def _mod():
    spec = importlib.util.spec_from_file_location("beat_sensors_under_test", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _registry(tmp_path):
    p = tmp_path / "sensors.yaml"
    p.write_text(FIXTURE, encoding="utf-8")
    return p


def test_list_counts_all_sensors(tmp_path, capsys):
    m = _mod()
    m.list_sensors(_registry(tmp_path))
    out = capsys.readouterr().out
    assert "3 sensors" in out
    assert "alpha" in out and "beta" in out and "gamma" in out


def test_dry_run_metabolize_respects_gate_default(tmp_path, capsys, monkeypatch):
    m = _mod()
    monkeypatch.delenv("LIMEN_ALPHA", raising=False)
    monkeypatch.delenv("LIMEN_BETA", raising=False)
    m.run("metabolize", dry_run=True, registry=_registry(tmp_path))
    out = capsys.readouterr().out
    # alpha default=1 → its command shows; beta default=0 → header only, no command
    assert "$ python3 scripts/alpha.py" in out
    assert "── 0b. beta check ──" in out
    assert "$ python3 scripts/beta.py" not in out


def test_gate_env_override_enables_beta(tmp_path, capsys, monkeypatch):
    m = _mod()
    monkeypatch.setenv("LIMEN_BETA", "1")
    m.run("metabolize", dry_run=True, registry=_registry(tmp_path))
    assert "$ python3 scripts/beta.py" in capsys.readouterr().out


def test_source_filter_and_when_env(tmp_path, capsys, monkeypatch):
    m = _mod()
    # gamma is heartbeat-only → absent from metabolize
    m.run("metabolize", dry_run=True, registry=_registry(tmp_path))
    assert "gamma" not in capsys.readouterr().out
    # in heartbeat, gamma's step only shows when LIMEN_GAMMA_ON is set
    monkeypatch.delenv("LIMEN_GAMMA_ON", raising=False)
    m.run("heartbeat", dry_run=True, registry=_registry(tmp_path))
    out = capsys.readouterr().out
    assert "── 0c. gamma heartbeat-only ──" in out
    assert "$ python3 scripts/gamma.py" not in out
    monkeypatch.setenv("LIMEN_GAMMA_ON", "1")
    m.run("heartbeat", dry_run=True, registry=_registry(tmp_path))
    assert "$ python3 scripts/gamma.py" in capsys.readouterr().out
