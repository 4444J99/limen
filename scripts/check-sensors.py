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
  E default parity — registry consumer defaults and `${ENV:-fallback}` values agree with the
                     parameter-panel defaults, so a declared dark gate cannot wake up by drift.

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
VALID_OMEGA_TIER = {"det", "live"}
VALID_VALVE_TYPE = {"deliverable", "safety"}
SENSOR_ID_RX = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
SCRIPT_RX = re.compile(r"scripts/[\w./-]+\.(?:py|sh)")
SHELL_DEFAULT_RX = re.compile(r"\$\{(LIMEN_[A-Z0-9_]+):-([^}\n]+)\}")

_failures: list[str] = []


def fail(check: str, message: str) -> None:
    _failures.append(f"[{check}] {message}")


def parameter_specs() -> dict[str, dict]:
    """Return the parameter-panel mappings used to verify executable-registry defaults."""
    try:
        panel = yaml.safe_load(PARAMS.read_text(encoding="utf-8")) or {}
        params = (panel.get("parameters") if isinstance(panel, dict) else None) or {}
        return {str(key): spec for key, spec in params.items() if isinstance(spec, dict)}
    except (OSError, ValueError):
        return {}


def declared_params() -> set[str]:
    """Declared panel params PLUS the grandfathered undeclared baseline — same ratchet as check-params
    (a gate already in the baseline is accepted; only a genuinely NEW sensor gate must be declared)."""
    known = set(parameter_specs())
    if PARAMS_BASELINE.exists():
        known |= {
            ln.strip()
            for ln in PARAMS_BASELINE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        }
    return known


def _default_text(value) -> str:
    """YAML may spell the same executable fallback as `0` or `"0"`; compare its shell value."""
    return str(value).strip()


def default_parity_errors(sensor_id: str, sensor: dict, params: dict[str, dict]) -> list[str]:
    """Compare every registry-owned fallback with its parameter-panel declaration.

    ``beat-sensors.py`` consumes ``sensor.default`` as the fallback for a missing gate environment
    variable. Commands can additionally contain shell ``${ENV:-fallback}`` values, while cadence and
    timeout capabilities carry the same contract as ``{env, default}``. Keeping these copies equal is
    especially important for dark gates: one stale `1` would silently activate the sensor.
    """
    errors: list[str] = []

    def compare(location: str, env_name: str, consumer_default) -> None:
        spec = params.get(env_name)
        if not spec or "default" not in spec:
            return
        declared_default = spec["default"]
        if _default_text(consumer_default) != _default_text(declared_default):
            errors.append(
                f"{sensor_id}.{location}: consumer default {consumer_default!r} != "
                f"parameters.yaml {env_name} default {declared_default!r}"
            )

    gate = sensor.get("gate")
    if gate:
        # This is the exact fallback used by beat-sensors._gate_open when the env var is absent.
        compare("default", str(gate), sensor.get("default", "1"))

    for capability in ("cadence", "timeout"):
        value = sensor.get(capability)
        if isinstance(value, dict) and value.get("env") and "default" in value:
            compare(f"{capability}.default", str(value["env"]), value["default"])

    for index, step in enumerate(sensor.get("steps") or []):
        command = str(step.get("command") or "")
        for env_name, fallback in SHELL_DEFAULT_RX.findall(command):
            compare(f"step[{index}].command fallback", env_name, fallback)
        for condition_index, condition in enumerate(step.get("args_when") or []):
            if isinstance(condition, dict) and condition.get("env") and "default" in condition:
                compare(
                    f"step[{index}].args_when[{condition_index}].default",
                    str(condition["env"]),
                    condition["default"],
                )

    return errors


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


def _script_exists(sid: str, command: str) -> None:
    for match in SCRIPT_RX.findall(command):
        if not (ROOT / match).exists():
            fail("B", f"{sid}: script {match} does not exist")


def _numeric_capability(sid: str, name: str, spec, params: set[str]) -> None:
    if spec is None:
        return
    value = spec
    if isinstance(spec, dict):
        env = spec.get("env")
        value = spec.get("default")
        if not env:
            fail("A", f"{sid}.{name}: mapping requires env")
        elif env not in params:
            fail("C", f"{sid}.{name}: env {env} not declared in parameters.yaml")
    try:
        if int(value) <= 0:
            raise ValueError
    except (TypeError, ValueError):
        fail("A", f"{sid}.{name}: default must be a positive integer")


def main(argv=None) -> int:
    _failures.clear()
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

    param_specs = parameter_specs()
    params = declared_params()
    shell = beat_source_text()
    derived = derived_sources(shell)

    for sid, s in sensors.items():
        # A schema
        if not SENSOR_ID_RX.fullmatch(str(sid)):
            fail("A", f"{sid}: id must match {SENSOR_ID_RX.pattern}")
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
            _script_exists(sid, step.get("command", ""))
            _numeric_capability(sid, f"step[{i}].timeout", step.get("timeout"), params)
            args_when = step.get("args_when") or []
            if not isinstance(args_when, list):
                fail("A", f"{sid}.step[{i}].args_when: must be a list")
                args_when = []
            for j, condition in enumerate(args_when):
                if not isinstance(condition, dict) or not condition.get("env"):
                    fail("A", f"{sid}.step[{i}].args_when[{j}]: mapping requires env")
                    continue
                if condition["env"] not in params:
                    fail(
                        "C",
                        f"{sid}.step[{i}].args_when[{j}]: env {condition['env']} not declared in parameters.yaml",
                    )
                args_value = condition.get("args")
                if not isinstance(args_value, (str, list)) or not args_value:
                    fail("A", f"{sid}.step[{i}].args_when[{j}]: args must be a string or non-empty list")
                valve_type = condition.get("armed_valve_type")
                if valve_type is not None and valve_type not in VALID_VALVE_TYPE:
                    fail(
                        "A",
                        f"{sid}.step[{i}].args_when[{j}]: armed_valve_type {valve_type!r} "
                        f"not in {sorted(VALID_VALVE_TYPE)}",
                    )

        _numeric_capability(sid, "cadence", s.get("cadence"), params)
        _numeric_capability(sid, "timeout", s.get("timeout"), params)
        sensor_valve_type = s.get("armed_valve_type")
        if sensor_valve_type is not None:
            if sensor_valve_type not in VALID_VALVE_TYPE:
                fail(
                    "A",
                    f"{sid}: armed_valve_type {sensor_valve_type!r} not in {sorted(VALID_VALVE_TYPE)}",
                )
            if not s.get("gate"):
                fail("A", f"{sid}: armed_valve_type requires a gate")

        omega_checks = s.get("omega_eligible") or []
        if not isinstance(omega_checks, list):
            fail("A", f"{sid}.omega_eligible: must be a list")
            omega_checks = []
        for i, check in enumerate(omega_checks):
            if not isinstance(check, dict):
                fail("A", f"{sid}.omega_eligible[{i}]: must be a mapping")
                continue
            if not check.get("label") or not check.get("command"):
                fail("A", f"{sid}.omega_eligible[{i}]: label and command are required")
            if check.get("tier") not in VALID_OMEGA_TIER:
                fail(
                    "A",
                    f"{sid}.omega_eligible[{i}]: tier {check.get('tier')!r} not in {sorted(VALID_OMEGA_TIER)}",
                )
            _script_exists(sid, check.get("command", ""))
            _numeric_capability(sid, f"omega_eligible[{i}].timeout", check.get("timeout"), params)

        # C gate declared
        gate = s.get("gate")
        if gate is not None and gate not in params:
            fail("C", f"{sid}: gate {gate} not declared in parameters.yaml")

        # E default parity — the registry is executable configuration. Its fallback values must
        # agree with the parameter panel, particularly for default-off safety gates.
        for message in default_parity_errors(str(sid), s, param_specs):
            fail("E", message)

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
        f"gates declared, consumer defaults match the parameter panel, all gates present in the beat sources."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
