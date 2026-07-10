#!/usr/bin/env python3
"""SENSORS registry drift-predicate — hold institutio/governance/sensors.yaml to the code.

The beat sensors are declared data (sensors.yaml). This is their drift-check, the sensors-domain twin
of check-gates.py / check-params.py. Exit 0 ⟺ the registry agrees with the scripts, the parameter
panel, and the beat sources:

  A schema        — each sensor has section + source + steps; each step has command + severity.
  B scripts exist — every `scripts/<x>.(py|sh)` a step invokes is a real file.
  C gate declared — every non-null gate is declared in institutio/governance/parameters.yaml.
  D shell parity  — every registry gate actually appears in the beat sources (metabolize.sh /
                    heartbeat-loop.sh), i.e. the registry names no phantom sensor.

  python3 scripts/check-sensors.py     # gate (CI): exit 1 on any drift
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio" / "governance" / "sensors.yaml"
PARAMS = ROOT / "institutio" / "governance" / "parameters.yaml"
PARAMS_BASELINE = ROOT / "institutio" / "governance" / "undeclared-params-baseline.txt"
BEAT_SOURCES = (ROOT / "scripts" / "metabolize.sh", ROOT / "scripts" / "heartbeat-loop.sh")
VALID_SEVERITY = {"advisory", "silent", "fatal"}
SCRIPT_RX = re.compile(r"scripts/[\w./-]+\.(?:py|sh)")

_failures: list[str] = []


def fail(check: str, message: str) -> None:
    _failures.append(f"[{check}] {message}")


def declared_params() -> set[str]:
    """Declared panel params PLUS the grandfathered undeclared baseline — same ratchet as check-params
    (a gate already in the baseline is accepted; only a genuinely NEW sensor gate must be declared)."""
    known: set[str] = set()
    try:
        panel = yaml.safe_load(PARAMS.read_text(encoding="utf-8")) or {}
        known |= set((panel.get("parameters") if isinstance(panel, dict) else None) or {})
    except (OSError, ValueError):
        pass
    if PARAMS_BASELINE.exists():
        known |= {
            ln.strip()
            for ln in PARAMS_BASELINE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        }
    return known


def beat_source_text() -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in BEAT_SOURCES if p.exists())


def derived_sources(shell: str) -> set[str]:
    """Beat sources whose sensor loop is DERIVED from the registry — the shell invokes
    ``beat-sensors.py --run [--source <s>]`` instead of hand-wiring each ``${LIMEN_*}`` gate. Under
    the derive path the individual gate strings correctly vanish from the shell, so D-parity is
    satisfied by the runner call instead of a literal gate match. A bare ``--run`` is the metabolize
    source. This keeps the check green across the migration (dark → default-on) and after the
    legacy blocks are deleted."""
    # `["']?` tolerates the closing quote in the real call `"$LIMEN_ROOT/scripts/beat-sensors.py" --run`.
    derived: set[str] = set()
    if not re.search(r"""beat-sensors\.py["']?\s+--run""", shell):
        return derived
    for src in ("metabolize", "heartbeat"):
        if re.search(rf"""beat-sensors\.py["']?\s+--run[^\n]*--source\s+{src}""", shell):
            derived.add(src)
    if re.search(r"""beat-sensors\.py["']?\s+--run(?![^\n]*--source)""", shell):  # bare --run == metabolize
        derived.add("metabolize")
    return derived


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SENSORS registry drift-predicate")
    ap.add_argument("--registry", default=None, help="registry path override (for tests)")
    args = ap.parse_args(argv)
    registry_path = Path(args.registry) if args.registry else REGISTRY

    try:
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError) as exc:
        print(f"FAILED: check-sensors — cannot read {registry_path}: {exc}")
        return 1

    sensors = registry.get("sensors") or {}
    if not sensors:
        print("FAILED: check-sensors — no sensors declared")
        return 1

    params = declared_params()
    shell = beat_source_text()
    derived = derived_sources(shell)

    for sid, s in sensors.items():
        # A schema
        if not s.get("section"):
            fail("A", f"{sid}: missing section")
        if not s.get("source"):
            fail("A", f"{sid}: missing source")
        steps = s.get("steps") or []
        if not steps:
            fail("A", f"{sid}: no steps")
        for i, step in enumerate(steps):
            if not step.get("command"):
                fail("A", f"{sid}.step[{i}]: missing command")
            sev = step.get("severity")
            if sev not in VALID_SEVERITY:
                fail("A", f"{sid}.step[{i}]: severity {sev!r} not in {sorted(VALID_SEVERITY)}")
            # B scripts exist
            for m in SCRIPT_RX.findall(step.get("command", "")):
                if not (ROOT / m).exists():
                    fail("B", f"{sid}: script {m} does not exist")

        # C gate declared
        gate = s.get("gate")
        if gate is not None and gate not in params:
            fail("C", f"{sid}: gate {gate} not declared in parameters.yaml")

        # D shell parity — the registry names no phantom sensor: either the gate literal appears in a
        # beat source (hand-wired path), OR every source it runs in DERIVES the loop via beat-sensors.py.
        if gate is not None and gate not in shell:
            srcs = s.get("source") or []
            if not (srcs and all(src in derived for src in srcs)):
                fail("D", f"{sid}: gate {gate} not found in any beat source (phantom sensor?)")

    if _failures:
        print("SENSORS DRIFT — registry does not match code/params/beat:")
        for f in _failures:
            print(f"  ✗ {f}")
        print("FAILED: check-sensors")
        return 1

    print(
        f"check-sensors: OK — {len(sensors)} sensors; schema valid, scripts exist, "
        f"gates declared in the parameter panel, all gates present in the beat sources."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
