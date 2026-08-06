"""Tests for scripts/check-host-pressure-estate.py — IF-HOST-PRESSURE as an estate, not a reading.

The row this predicate closes sat `probe: null` behind a reason that was *correct*: a one-shot
probe reporting live swap would report the weather of whatever machine ran pr-gate. The error was
in the noun, not the caution — the ideal says every axis "has an executable gauge and a mechanical
valve … and the gauges are watched", which is estate completeness and a repo fact.

So the thing under test is a ratchet, and a ratchet is only worth its gate if it can actually go
red. Each check is therefore exercised from both sides: the violation it must catch, and the
legitimate shape it must not flag. The `default: "0"` case matters most — a safety valve that is
off unless someone remembers to arm it is the SILENT-OFF class, and it is invisible in every
green-looking beat log, which is exactly how 2026-07-15 happened.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check-host-pressure-estate.py"

GAUGE_REL = "cli/src/limen/vigilia/vitals.py"
HOOK_REL = "scripts/hooks/pytest-scope-guard.sh"
SYMBOL = "memory_action"


@pytest.fixture
def mod(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("check_host_pressure_estate_under_test", CHECK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "ROOT", tmp_path)
    return m


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_sensors(root: Path, *, default: str = "1", armed: bool = True) -> None:
    arm = {"env": "LIMEN_HOST_RELIEF_APPLY", "default": default, "equals": "1", "args": ["--apply"]}
    if armed:
        arm["armed_valve_type"] = "safety"
    sensors = {
        "sensors": {
            "host-relief": {"steps": [{"command": "python3 scripts/host-relief.py --check", "args_when": [arm]}]},
            "host-pressure-stale": {"steps": [{"command": "python3 scripts/host-pressure-stale.py"}]},
        }
    }
    _write(root, "institutio/governance/sensors.yaml", yaml.safe_dump(sensors))


def _axes(**overrides) -> dict:
    axes = {
        "memory": {
            "note": "memory pressure",
            "gauge": {"path": GAUGE_REL, "symbol": SYMBOL},
            "valve": {"sensor": "host-relief", "env": "LIMEN_HOST_RELIEF_APPLY"},
        },
        "test-fanout": {
            "note": "full-suite pytest",
            "gauge": {"path": GAUGE_REL, "symbol": SYMBOL},
            "valve": {"path": HOOK_REL},
        },
        "gauge-watcher": {
            "role": "watcher",
            "note": "the gauges are watched",
            "gauge": {"sensor": "host-pressure-stale"},
            "valve": None,
            "valve_absent_reason": "a watcher's relief is its escalation",
        },
    }
    axes.update(overrides)
    return axes


def _write_registry(root: Path, axes: dict | None = None) -> None:
    _write(
        root,
        "institutio/governance/host-pressure-axes.yaml",
        yaml.safe_dump({"schema_version": 0.1, "axes": axes if axes is not None else _axes()}),
    )


@pytest.fixture
def estate(tmp_path):
    """A complete, honest estate — the shape every negative test perturbs by exactly one field."""
    _write(tmp_path, GAUGE_REL, f"def assess():\n    {SYMBOL} = 'ok'\n")
    _write(tmp_path, HOOK_REL, "#!/usr/bin/env bash\nexit 0\n")
    _write_sensors(tmp_path)
    _write_registry(tmp_path)
    return tmp_path


def _run(mod) -> tuple[list[str], set[str]]:
    axes = mod.load_axes()
    sensors = mod.load_sensors()
    findings: list[str] = []
    gauge_findings: list[str] = []
    for aid, axis in sorted(axes.items()):
        findings.extend(mod.check_a_schema(aid, axis))
        gf = mod.check_b_gauge(aid, axis, sensors)
        gauge_findings.extend(gf)
        findings.extend(gf)
        findings.extend(mod.check_c_valve(aid, axis, sensors))
    findings.extend(mod.check_d_watched(axes, gauge_findings))
    return findings, {f[:3] for f in findings}


# ── the estate as declared ────────────────────────────────────────────────────────


def test_a_complete_estate_is_clean(mod, estate):
    findings, _ = _run(mod)
    assert findings == [], "a gauged, valved, watched estate is the ideal — it must not be flagged"


# ── A: schema ─────────────────────────────────────────────────────────────────────


def test_a_flags_a_null_valve_with_no_reason(mod, estate):
    axes = _axes()
    del axes["gauge-watcher"]["valve_absent_reason"]
    _write_registry(estate, axes)

    findings, kinds = _run(mod)
    assert "[A]" in kinds
    assert any("unnamed vacuum" in f for f in findings), "Rule #1 — a vacuum is declared, never implicit"


def test_a_flags_a_file_gauge_with_no_symbol(mod, estate):
    axes = _axes()
    del axes["memory"]["gauge"]["symbol"]
    _write_registry(estate, axes)

    _, kinds = _run(mod)
    assert "[A]" in kinds, "a file gauge with no symbol cannot prove it still gauges anything"


# ── B: the gauge still gauges ─────────────────────────────────────────────────────


def test_b_flags_a_gauge_whose_symbol_was_refactored_away(mod, estate):
    """The failure that leaves an axis declared but blind — the file still exists, so nothing else notices."""
    axes = _axes()
    axes["memory"]["gauge"]["symbol"] = "memory_action_RENAMED"
    _write_registry(estate, axes)

    findings, kinds = _run(mod)
    assert "[B]" in kinds
    assert any("refactored away" in f for f in findings)


def test_b_flags_a_missing_gauge_file(mod, estate):
    (estate / GAUGE_REL).unlink()

    _, kinds = _run(mod)
    assert "[B]" in kinds


def test_b_flags_a_sensor_gauge_absent_from_the_registry(mod, estate):
    _write_sensors(estate)
    sensors = yaml.safe_load((estate / "institutio/governance/sensors.yaml").read_text())
    del sensors["sensors"]["host-pressure-stale"]
    _write(estate, "institutio/governance/sensors.yaml", yaml.safe_dump(sensors))

    _, kinds = _run(mod)
    assert "[B]" in kinds


# ── C: the valve is armed, not merely present ─────────────────────────────────────


def test_c_flags_a_safety_valve_that_defaults_to_off(mod, estate):
    """SILENT-OFF: present, classified, wired — and does nothing unless a human remembers."""
    _write_sensors(estate, default="0")

    findings, kinds = _run(mod)
    assert "[C]" in kinds
    assert any("SILENT-OFF" in f for f in findings)


def test_c_flags_an_unclassified_arm(mod, estate):
    _write_sensors(estate, armed=False)

    findings, kinds = _run(mod)
    assert "[C]" in kinds
    assert any("armed_valve_type" in f for f in findings)


def test_c_flags_a_missing_valve_hook(mod, estate):
    (estate / HOOK_REL).unlink()

    findings, kinds = _run(mod)
    assert "[C]" in kinds
    assert any("no hands" in f for f in findings)


def test_c_accepts_a_declared_valve_vacuum(mod, estate):
    """A watcher has no valve by construction; the reason is the contract, not an excuse."""
    findings, _ = _run(mod)
    assert not [f for f in findings if f.startswith("[C]") and "gauge-watcher" in f]


# ── D: the gauges are watched ─────────────────────────────────────────────────────


def test_d_flags_an_estate_with_no_watcher(mod, estate):
    axes = _axes()
    axes["gauge-watcher"]["role"] = "axis"
    _write_registry(estate, axes)

    findings, kinds = _run(mod)
    assert "[D]" in kinds
    assert any("unwatched" in f for f in findings)


def test_d_flags_a_watcher_whose_own_gauge_is_broken(mod, estate):
    """Nothing watches the watchers — the 2026-07-15 precondition, stated exactly."""
    axes = _axes()
    axes["gauge-watcher"]["gauge"] = {"sensor": "sensor-that-does-not-exist"}
    _write_registry(estate, axes)

    findings, kinds = _run(mod)
    assert "[D]" in kinds
    assert any("watches the watchers" in f for f in findings)


# ── the predicate through its real surface ────────────────────────────────────────


def test_main_prints_the_extract_target_on_both_paths(estate, monkeypatch):
    """`unguarded axes: N` is the ideal-forms probe's extract target — a red run must still yield a number."""
    monkeypatch.setenv("LIMEN_ROOT", str(estate))

    proc = subprocess.run([sys.executable, str(CHECK)], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout
    assert "unguarded axes: 0" in proc.stdout

    _write_sensors(estate, default="0")
    proc = subprocess.run([sys.executable, str(CHECK)], capture_output=True, text=True, check=False)
    assert proc.returncode == 1, proc.stdout
    assert "unguarded axes: 1" in proc.stdout, "a failing probe that prints no number reads as unmeasured, not red"
