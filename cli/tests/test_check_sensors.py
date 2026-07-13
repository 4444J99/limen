"""Tests for scripts/check-sensors.py — the SENSORS registry drift-predicate.

The real registry must pass; fixture registries via --registry exercise the failure modes. (--registry
overrides only the registry; params + beat sources stay the real repo, so gate checks are meaningful.)
"""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check-sensors.py"


def run(*extra):
    return subprocess.run([sys.executable, str(CHECK), *extra], capture_output=True, text=True)


def _mod():
    spec = importlib.util.spec_from_file_location("check_sensors_under_test", CHECK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_real_registry_is_green():
    r = run()
    assert r.returncode == 0, r.stdout
    assert "check-sensors: OK" in r.stdout


def _write(tmp_path, body):
    p = tmp_path / "sensors.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_bad_severity_fails(tmp_path):
    reg = _write(
        tmp_path,
        "sensors:\n  x:\n    section: '0x'\n    source: [metabolize]\n    gate: LIMEN_FORK_SAFETY_CHECK\n"
        "    steps:\n      - command: 'python3 scripts/check-fork-safety.py'\n        severity: bogus\n"
        "        escalation: 'e'\n",
    )
    r = run("--registry", str(reg))
    assert r.returncode == 1
    assert "[A]" in r.stdout and "severity" in r.stdout


def test_missing_script_fails(tmp_path):
    reg = _write(
        tmp_path,
        "sensors:\n  x:\n    section: '0x'\n    source: [metabolize]\n    gate: LIMEN_FORK_SAFETY_CHECK\n"
        "    steps:\n      - command: 'python3 scripts/does-not-exist.py'\n        severity: advisory\n"
        "        escalation: 'e'\n",
    )
    r = run("--registry", str(reg))
    assert r.returncode == 1
    assert "[B]" in r.stdout and "does-not-exist.py" in r.stdout


def test_derived_sources_detects_quoted_runner_call():
    """D-parity must accept the derive-runner in place of the literal gate strings — otherwise
    Branch-1b (deleting the hand-wired blocks) would turn check-sensors red. The real shell quotes
    the path: `"$LIMEN_ROOT/scripts/beat-sensors.py" --run` — the `"` between .py and --run must not
    defeat detection (the bug this test locks out)."""
    m = _mod()
    assert m.derived_sources('python3 "$LIMEN_ROOT/scripts/beat-sensors.py" --run --source metabolize') == {
        "metabolize"
    }


def test_derived_sources_bare_and_heartbeat_and_none():
    m = _mod()
    assert m.derived_sources("x/beat-sensors.py --run") == {"metabolize"}  # bare --run == metabolize
    assert m.derived_sources("beat-sensors.py --run --source heartbeat") == {"heartbeat"}
    assert m.derived_sources("no runner here at all") == set()


def test_current_real_shell_derives_metabolize():
    """The metabolize.sh shipped in Branch 1 wires the derive-runner (dark, behind LIMEN_BEAT_DERIVE),
    so the current beat sources already resolve the metabolize source as derived."""
    m = _mod()
    assert "metabolize" in m.derived_sources(m.beat_source_text())


def test_derive_fallback_matches_panel_default():
    """Every `${LIMEN_BEAT_DERIVE:-N}` fallback in BOTH beat sources must equal the parameter-panel
    default. The drift class this pins shut: metabolize.sh said `:-1`, heartbeat-loop.sh said `:-0`,
    and the panel declared \"1\" — three copies of one default, so the heartbeat's whole scheduled
    sensor lane (github-estate-reconcile, the 0g4 liveness rung) silently never executed live while
    every layer looked declared-on."""
    panel = yaml.safe_load((ROOT / "institutio/governance/parameters.yaml").read_text(encoding="utf-8"))
    declared = str(panel["parameters"]["LIMEN_BEAT_DERIVE"]["default"]).strip()
    for source in (ROOT / "scripts/metabolize.sh", ROOT / "scripts/heartbeat-loop.sh"):
        fallbacks = re.findall(r"\$\{LIMEN_BEAT_DERIVE:-([^}]+)\}", source.read_text(encoding="utf-8"))
        assert fallbacks, f"{source.name}: no ${{LIMEN_BEAT_DERIVE:-N}} fallback found"
        assert all(fb.strip() == declared for fb in fallbacks), (
            f"{source.name}: LIMEN_BEAT_DERIVE fallbacks {fallbacks} != panel default {declared!r}"
        )


def test_prompt_corpus_sensor_is_dark_manual_only_and_default_aligned():
    """Do not let the unmeasured corpus drain become heartbeat or Omega work by configuration drift."""
    registry = yaml.safe_load((ROOT / "institutio/governance/sensors.yaml").read_text(encoding="utf-8"))
    panel = yaml.safe_load((ROOT / "institutio/governance/parameters.yaml").read_text(encoding="utf-8"))
    sensor = registry["sensors"]["prompt-corpus-control"]
    parameter = panel["parameters"]["LIMEN_PROMPT_ATOM_CONTROL"]

    assert str(sensor["default"]) == str(parameter["default"]) == "0"
    assert not sensor.get("omega_eligible")
    assert "prompt-atom-ledger.py --scan" in sensor["steps"][0]["command"]
    assert (
        _mod().default_parity_errors(
            "prompt-corpus-control",
            sensor,
            panel["parameters"],
        )
        == []
    )


def test_default_parity_rejects_dark_gate_or_shell_fallback_drift():
    m = _mod()
    sensor = {
        "gate": "LIMEN_PROMPT_ATOM_CONTROL",
        "default": "1",
        "steps": [{"command": 'python3 scripts/prompt-atom-ledger.py --days "${LIMEN_PROMPT_ATOM_DAYS:-99}"'}],
    }
    params = {
        "LIMEN_PROMPT_ATOM_CONTROL": {"default": "0"},
        "LIMEN_PROMPT_ATOM_DAYS": {"default": 2},
    }
    errors = m.default_parity_errors("prompt-corpus-control", sensor, params)
    assert any("LIMEN_PROMPT_ATOM_CONTROL default '0'" in error for error in errors)
    assert any("LIMEN_PROMPT_ATOM_DAYS default 2" in error for error in errors)


def test_undeclared_and_phantom_gate_fails(tmp_path):
    # A non-derived source still exercises [D]. Both real beat sources now contain a generic
    # derive-runner, so their individual gate literals correctly need not appear in shell.
    reg = _write(
        tmp_path,
        "sensors:\n  x:\n    section: '0x'\n    source: [manual]\n    gate: LIMEN_TOTALLY_FAKE_GATE\n"
        "    steps:\n      - command: 'python3 scripts/check-fork-safety.py'\n        severity: advisory\n"
        "        escalation: 'e'\n",
    )
    r = run("--registry", str(reg))
    assert r.returncode == 1
    # not declared in the panel/baseline (C) AND not present in any beat source (D)
    assert "[C]" in r.stdout and "[D]" in r.stdout


def test_phantom_gate_on_derived_source_still_caught_by_c(tmp_path):
    """A fake gate on a DERIVED source (metabolize) no longer trips [D] — the registry is the source
    of truth so no sensor can be phantom — but [C] (must be declared in parameters.yaml) still catches it."""
    reg = _write(
        tmp_path,
        "sensors:\n  x:\n    section: '0x'\n    source: [metabolize]\n    gate: LIMEN_TOTALLY_FAKE_GATE\n"
        "    steps:\n      - command: 'python3 scripts/check-fork-safety.py'\n        severity: advisory\n"
        "        escalation: 'e'\n",
    )
    r = run("--registry", str(reg))
    assert r.returncode == 1
    assert "[C]" in r.stdout  # undeclared gate still fails the build
    assert "[D]" not in r.stdout  # derived source → phantom check is vacuous


def test_generic_scheduled_capabilities_accept_an_arbitrarily_renamed_sensor(tmp_path):
    reg = _write(
        tmp_path,
        """\
sensors:
  arbitrary.future.id:
    section: heartbeat
    title: renamed sensor
    source: [heartbeat]
    gate: LIMEN_GITVS
    default: "1"
    cadence: {env: LIMEN_BEAT_GITVS, default: 8}
    timeout: {env: LIMEN_GITVS_TIMEOUT, default: 120}
    steps:
      - command: "python3 scripts/gitvs.py reconcile"
        args_when:
          - env: LIMEN_GITVS_APPLY
            default: "0"
            equals: "1"
            args: ["--apply"]
            armed_valve_type: safety
        severity: silent
        escalation: skipped
    omega_eligible:
      - label: arbitrary parity
        tier: det
        command: "python3 scripts/gitvs.py doctor --offline --parity-only"
""",
    )
    r = run("--registry", str(reg))
    assert r.returncode == 0, r.stdout


def test_invalid_capability_shape_fails_schema(tmp_path):
    reg = _write(
        tmp_path,
        """\
sensors:
  arbitrary:
    section: heartbeat
    source: [heartbeat]
    gate: LIMEN_GITVS
    cadence: {env: LIMEN_BEAT_GITVS, default: 0}
    steps:
      - command: "python3 scripts/gitvs.py reconcile"
        args_when:
          - env: LIMEN_GITVS_APPLY
            args: ["--apply"]
            armed_valve_type: magical
        severity: silent
        escalation: skipped
""",
    )
    r = run("--registry", str(reg))
    assert r.returncode == 1
    assert "positive integer" in r.stdout
    assert "armed_valve_type" in r.stdout
