"""Tests for scripts/beat-sensors.py — the SENSORS registry runner.

Loads the script via importlib (hyphenated filename) and drives it against a fixture registry, so the
tests never execute the real beat sensors.
"""

import importlib.util
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "beat-sensors.py"
REAL_REGISTRY = ROOT / "institutio" / "governance" / "sensors.yaml"
METABOLIZE = ROOT / "scripts" / "metabolize.sh"
_SCRIPT_RE = re.compile(r"scripts/([\w./-]+\.(?:py|sh))")

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


def test_reload_env_loads_written_file(tmp_path):
    """reload_env re-sources a shell-style env file into os.environ (the creds-hydrate → ~/.limen.env
    ordering, now declared data). conftest autouse restores os.environ after the test."""
    m = _mod()
    envf = tmp_path / ".limen.env"
    envf.write_text('export FOO_RELOAD_KEY="bar123"\n# a comment\nBAZ_RELOAD=qux\n', encoding="utf-8")
    os.environ.pop("FOO_RELOAD_KEY", None)
    os.environ.pop("BAZ_RELOAD", None)
    m._load_env_file(envf)
    assert os.environ["FOO_RELOAD_KEY"] == "bar123"  # export + quotes stripped
    assert os.environ["BAZ_RELOAD"] == "qux"


def test_reload_env_missing_file_is_fail_open(tmp_path):
    m = _mod()
    m._load_env_file(tmp_path / "does-not-exist.env")  # must not raise


def _script_of(cmd: str):
    hit = _SCRIPT_RE.search(cmd)
    return hit.group(1) if hit else None


def _registry_script_sequence():
    """Ordered sensor scripts the SENSORS registry declares for the metabolize source (all steps)."""
    m = _mod()
    sensors = m.load_sensors(REAL_REGISTRY)
    seq = []
    for _sid, s in m.iter_source(sensors, "metabolize"):
        for step in s.get("steps", []):
            sc = _script_of(step.get("command", ""))
            if sc:
                seq.append(sc)
    return seq


def _shell_script_sequence():
    """Ordered sensor scripts the hand-wired `── 0x ──` blocks (the LIMEN_BEAT_DERIVE else-branch) run."""
    text = METABOLIZE.read_text(encoding="utf-8")
    start = text.index("LIMEN_BEAT_DERIVE")
    else_idx = text.index("\nelse\n", start)
    end_idx = text.index("fi  # ── end beat sensors")
    block = text[else_idx:end_idx]
    seq = []
    for raw in block.splitlines():
        line = raw.strip()
        if line.startswith("#") or "scripts/" not in line:
            continue
        if "python3" not in line and "bash " not in line:
            continue
        sc = _script_of(line)
        if sc:
            seq.append(sc)
    return seq


def test_equivalence_derived_matches_handwired_blocks():
    """THE FLIP SAFETY PROOF: the sensor-script sequence the registry derives for the metabolize beat
    is byte-identical (same scripts, same order, same multiplicity) to what the hand-wired `── 0x ──`
    blocks invoke. If Phase-1's transcription dropped, added, or reordered a sensor, this fails —
    so LIMEN_BEAT_DERIVE=1 runs exactly what the legacy blocks ran."""
    derived = _registry_script_sequence()
    handwired = _shell_script_sequence()
    assert derived == handwired, (
        "SENSOR DERIVE-FLIP DIVERGENCE — registry vs metabolize.sh hand-wired blocks:\n"
        f"  registry-derived: {derived}\n"
        f"  shell-handwired : {handwired}\n"
        f"  only in registry: {[s for s in derived if s not in handwired]}\n"
        f"  only in shell   : {[s for s in handwired if s not in derived]}"
    )
