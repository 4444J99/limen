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
import shlex
import signal
import subprocess
import sys
import time
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


def _positive_int(spec, *, fallback: int | None = None) -> int | None:
    """Resolve a registry number, optionally overridden by an environment variable.

    ``spec`` may be an integer/string or ``{env: NAME, default: N}``.  Keeping the
    environment name in the registry means the runner never needs to know a sensor's
    identity or parameter namespace.
    """
    if spec is None:
        return fallback
    value = spec
    declared_default = fallback
    if isinstance(spec, dict):
        declared_default = spec.get("default", fallback)
        value = os.environ.get(str(spec.get("env") or ""), declared_default)
    for candidate in (value, declared_default, fallback):
        try:
            number = int(candidate)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return None


def _condition_matches(condition: dict) -> bool:
    value = os.environ.get(str(condition.get("env") or ""), str(condition.get("default", "")))
    if "equals" in condition:
        return value == str(condition["equals"])
    if "not_equals" in condition:
        return value != str(condition["not_equals"])
    return _truthy(value)


def _step_command(step: dict) -> str:
    """Return the command plus any declarative conditional arguments."""
    command = str(step["command"])
    for condition in step.get("args_when") or []:
        if not isinstance(condition, dict) or not _condition_matches(condition):
            continue
        args = condition.get("args") or []
        if isinstance(args, str):
            args = [args]
        command += " " + " ".join(shlex.quote(str(arg)) for arg in args)
    return command


def _run_command(command: str, *, timeout: int | None, quiet: bool) -> int:
    """Run one trusted registry command with a real process-group timeout.

    A plain ``subprocess.run(..., timeout=)`` can leave a grandchild holding the
    pipe open.  Each sensor gets its own process group so the declared ceiling is
    a ceiling for the whole command tree, matching the heartbeat's boundedness.
    """
    stdout = subprocess.DEVNULL if quiet else None
    try:
        proc = subprocess.Popen(  # noqa: S602 - commands are trusted, reviewed registry data
            command,
            shell=True,
            cwd=str(ROOT),
            stdout=stdout,
            start_new_session=True,
        )
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                proc.kill()
            proc.wait()
            return 124
    except OSError:
        return 1


def _cadence(sensor: dict) -> int | None:
    return _positive_int(sensor.get("cadence"))


def _due(sensor_id: str, sensor: dict, *, beat: int, loop_max: int, voice_dir: Path) -> bool:
    """Mirror heartbeat ``due_voice`` without knowing any sensor names."""
    cadence = _cadence(sensor)
    if cadence is None:
        return True
    if beat % cadence == 0:
        return True
    stamp_path = voice_dir / sensor_id
    try:
        age = time.time() - stamp_path.stat().st_mtime
    except OSError:
        return True
    return age >= cadence * max(1, loop_max)


def _stamp(sensor_id: str, voice_dir: Path) -> None:
    try:
        voice_dir.mkdir(parents=True, exist_ok=True)
        (voice_dir / sensor_id).write_text(
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _format_escalation(step: dict) -> str | None:
    sev = step.get("severity", "advisory")
    msg = step.get("escalation", "")
    if sev == "advisory":
        return f"  ↑ {msg}"
    if sev == "silent":
        return f"  ({msg})"
    return None  # fatal has no echo — it propagates


def _load_env_file(path: Path) -> None:
    """Load a shell-style env file (``KEY=VALUE`` / ``export KEY=VALUE``) into os.environ, mirroring
    ``set -a; . <file>``. A sensor (creds-hydrate) may WRITE this file, and later sensors need those
    values in their environment — the ordering metabolize.sh hard-codes as a ``. ~/.limen.env`` source
    right after block 0a. Honoring it here (via the registry's ``reload_env`` field) makes that
    sequencing constraint declared data rather than shell tribal knowledge. Fail-open if absent."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key:
            os.environ[key] = val


def iter_source(sensors: dict, source: str):
    """Sensors that run in the given beat source, in registry (declaration) order."""
    for sid, s in sensors.items():
        if source in (s.get("source") or []):
            yield sid, s


def run(
    source: str,
    *,
    dry_run: bool = False,
    registry: Path = REGISTRY,
    scheduled_only: bool = False,
    beat: int = 0,
    loop_max: int = 1800,
    voice_dir: Path | None = None,
) -> int:
    sensors = load_sensors(registry)
    worst = 0
    voice_dir = voice_dir or (ROOT / "logs" / ".voice")
    for sid, s in iter_source(sensors, source):
        cadence = _cadence(s)
        if scheduled_only and cadence is None:
            continue
        if cadence is not None and not _due(sid, s, beat=beat, loop_max=loop_max, voice_dir=voice_dir):
            continue
        print(f"── {s['section']}. {s['title']} ──")
        if not _gate_open(s):
            if cadence is not None and not dry_run:
                _stamp(sid, voice_dir)
            continue
        fatal_rc = 0
        for step in s.get("steps", []):
            we = step.get("when_env")
            if we and not _truthy(os.environ.get(we, str(step.get("when_default", "")))):
                continue
            cmd = _step_command(step)
            if dry_run:
                print(f"    $ {cmd}")
                continue
            timeout = _positive_int(step.get("timeout"), fallback=_positive_int(s.get("timeout")))
            rc = _run_command(cmd, timeout=timeout, quiet=bool(step.get("quiet_output")))
            if rc != 0:
                line = _format_escalation(step)
                if line is not None:
                    print(line)
                if step.get("severity") == "fatal":
                    fatal_rc = rc
                    break
                worst = worst or 0  # advisory/silent never fail the beat
        # reload_env — after this sensor's steps, re-source an env file it may have written so the
        # REST of the loop inherits it (the creds-hydrate → ~/.limen.env ordering, now registry data).
        reload = s.get("reload_env")
        if reload:
            if dry_run:
                print(f"    · reload_env {reload}")
            else:
                _load_env_file(Path(os.path.expanduser(str(reload))))
        if cadence is not None and not dry_run:
            _stamp(sid, voice_dir)
        if fatal_rc:
            return fatal_rc
    return worst


def iter_omega(sensors: dict):
    """Yield registry-declared fixed-point checks in declaration order."""
    for sensor_id, sensor in sensors.items():
        for index, check in enumerate(sensor.get("omega_eligible") or []):
            yield sensor_id, index, sensor, check


def list_omega(registry: Path = REGISTRY) -> int:
    """Emit stable TSV contract metadata; execution still stays inside the registry runner."""
    for sensor_id, index, sensor, check in iter_omega(load_sensors(registry)):
        timeout = _positive_int(check.get("timeout"), fallback=_positive_int(sensor.get("timeout")))
        fields = (
            sensor_id,
            str(index),
            str(check.get("tier", "det")),
            str(check.get("label", sensor_id)),
            str(check["command"]),
            str(timeout),
        )
        if any("\t" in field or "\n" in field for field in fields):
            print(f"beat-sensors: invalid tab/newline in omega metadata for {sensor_id}", file=sys.stderr)
            return 2
        print("\t".join(fields))
    return 0


def run_omega(sensor_id: str, index: int, *, registry: Path = REGISTRY) -> int:
    sensors = load_sensors(registry)
    sensor = sensors.get(sensor_id)
    checks = (sensor or {}).get("omega_eligible") or []
    if not sensor or index < 0 or index >= len(checks):
        print(f"beat-sensors: unknown omega check {sensor_id}[{index}]", file=sys.stderr)
        return 2
    check = checks[index]
    timeout = _positive_int(check.get("timeout"), fallback=_positive_int(sensor.get("timeout")))
    return _run_command(str(check["command"]), timeout=timeout, quiet=False)


def list_sensors(registry: Path = REGISTRY) -> int:
    sensors = load_sensors(registry)
    print(f"SENSORS registry — {len(sensors)} sensors ({REGISTRY})")
    for sid, s in sensors.items():
        gate = s.get("gate") or "(ungated)"
        srcs = ",".join(s.get("source") or [])
        cadence = _cadence(s)
        schedule = f" cadence={cadence}" if cadence is not None else ""
        print(f"  {s['section']:5} {sid:22} gate={gate:28} src={srcs}{schedule}")
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
    ap.add_argument("--registry", type=Path, default=REGISTRY, help="sensor registry path")
    ap.add_argument("--scheduled-only", action="store_true", help="run only sensors declaring cadence")
    ap.add_argument("--beat", type=int, default=0, help="current heartbeat counter for cadence")
    ap.add_argument("--loop-max", type=int, default=1800, help="maximum loop seconds for overdue detection")
    ap.add_argument("--voice-dir", type=Path, default=None, help="voice-stamp directory")
    ap.add_argument("--list-omega", action="store_true", help="emit TSV metadata for omega-eligible checks")
    ap.add_argument("--run-omega", nargs=2, metavar=("SENSOR_ID", "INDEX"), help="run one omega check")
    args = ap.parse_args(argv)

    if args.list:
        return list_sensors(args.registry)
    if args.list_omega:
        return list_omega(args.registry)
    if args.run_omega:
        try:
            index = int(args.run_omega[1])
        except ValueError:
            return 2
        return run_omega(args.run_omega[0], index, registry=args.registry)
    if args.run:
        return run(
            args.source,
            dry_run=args.dry_run,
            registry=args.registry,
            scheduled_only=args.scheduled_only,
            beat=args.beat,
            loop_max=args.loop_max,
            voice_dir=args.voice_dir,
        )
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
