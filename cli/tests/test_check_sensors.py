"""Tests for scripts/check-sensors.py — the SENSORS registry drift-predicate.

The real registry must pass; fixture registries via --registry exercise the failure modes. (--registry
overrides only the registry; params + beat sources stay the real repo, so gate checks are meaningful.)
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check-sensors.py"


def run(*extra):
    return subprocess.run([sys.executable, str(CHECK), *extra], capture_output=True, text=True)


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


def test_undeclared_and_phantom_gate_fails(tmp_path):
    reg = _write(
        tmp_path,
        "sensors:\n  x:\n    section: '0x'\n    source: [metabolize]\n    gate: LIMEN_TOTALLY_FAKE_GATE\n"
        "    steps:\n      - command: 'python3 scripts/check-fork-safety.py'\n        severity: advisory\n"
        "        escalation: 'e'\n",
    )
    r = run("--registry", str(reg))
    assert r.returncode == 1
    # not declared in the panel/baseline (C) AND not present in any beat source (D)
    assert "[C]" in r.stdout and "[D]" in r.stdout
