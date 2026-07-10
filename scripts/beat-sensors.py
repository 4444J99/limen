#!/usr/bin/env python3
"""beat-sensors — derive the beat's continuous-runtime sensor loop from the SENSORS registry.

The beat sensors (the `── 0x ──` blocks in metabolize.sh) are declared data in
``institutio/governance/sensors.yaml`` — the third axis of the VIGILIA spine (pre-merge=gates,
config=parameters, runtime=sensors). This is their single derived consumer: instead of 18 hand-wired
shell blocks, the beat runs one `beat-sensors.py --run`. Adding a sensor is one registry entry;
``scripts/check-sensors.py`` keeps the registry honest.

  python3 scripts/beat-sensors.py --list                 # print the sensor matrix
  python3 scripts/beat-sensors.py --run                   # run the metabolize sensors (the beat call)
  python3 scripts/beat-sensors.py --run --source heartbeat
  python3 scripts/beat-sensors.py --run --dry-run         # print what WOULD run (no execution)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
REGISTRY = ROOT / "institutio" / "governance" / "sensors.yaml"


def load_sensors(registry: Path = REGISTRY) -> dict:
    data = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
    return data.get("sensors") or {}


def _truthy(val: str | None) -> bool:
    return str(val or "").strip().lower() not in {"", "0", "false", "no", "off"}


def _gate_open(sensor: dict) -> bool:
    gate = sensor.get("gate")
    if gate is None:
        return True  # ungated — always runs
    return os.environ.get(gate, str(sensor.get("default", "1"))) == "1"


def _format_escalation(step: dict) -> str | None:
    sev = step.get("severity", "advisory")
    msg = step.get("escalation", "")
    if sev == "advisory":
        return f"  ↑ {msg}"
    if sev == "silent":
        return f"  ({msg})"
    return None  # fatal has no echo — it propagates


def iter_source(sensors: dict, source: str):
    """Sensors that run in the given beat source, in registry (declaration) order."""
    for sid, s in sensors.items():
        if source in (s.get("source") or []):
            yield sid, s


def run(source: str, *, dry_run: bool = False, registry: Path = REGISTRY) -> int:
    sensors = load_sensors(registry)
    worst = 0
    for _sid, s in iter_source(sensors, source):
        print(f"── {s['section']}. {s['title']} ──")
        if not _gate_open(s):
            continue
        for step in s.get("steps", []):
            we = step.get("when_env")
            if we and not _truthy(os.environ.get(we, str(step.get("when_default", "")))):
                continue
            cmd = step["command"]
            if dry_run:
                print(f"    $ {cmd}")
                continue
            stdout = subprocess.DEVNULL if step.get("quiet_output") else None
            try:
                rc = subprocess.run(cmd, shell=True, cwd=str(ROOT), stdout=stdout).returncode
            except OSError:
                rc = 1
            if rc != 0:
                line = _format_escalation(step)
                if line is not None:
                    print(line)
                if step.get("severity") == "fatal":
                    return rc
                worst = worst or 0  # advisory/silent never fail the beat
    return worst


def list_sensors(registry: Path = REGISTRY) -> int:
    sensors = load_sensors(registry)
    print(f"SENSORS registry — {len(sensors)} sensors ({REGISTRY})")
    for sid, s in sensors.items():
        gate = s.get("gate") or "(ungated)"
        srcs = ",".join(s.get("source") or [])
        print(f"  {s['section']:5} {sid:22} gate={gate:28} src={srcs}")
        for step in s.get("steps", []):
            extra = ""
            if step.get("when_env"):
                extra = f"  [when {step['when_env']}]"
            print(f"        {step.get('severity', 'advisory'):8} {step['command']}{extra}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="derive the beat sensor loop from sensors.yaml")
    ap.add_argument("--list", action="store_true", help="print the sensor matrix")
    ap.add_argument("--run", action="store_true", help="run the sensors for --source")
    ap.add_argument("--source", default="metabolize", help="beat source: metabolize | heartbeat")
    ap.add_argument("--dry-run", action="store_true", help="with --run: print commands, don't execute")
    args = ap.parse_args(argv)

    if args.list:
        return list_sensors()
    if args.run:
        return run(args.source, dry_run=args.dry_run)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
