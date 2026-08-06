#!/usr/bin/env python3
"""HOST-PRESSURE estate predicate — every axis keeps a gauge and an armed valve.

This is the executable form of IF-HOST-PRESSURE, and it deliberately does NOT measure host
pressure. The row sat `probe: null` for a good reason — a probe reporting the live swap of
whatever machine ran pr-gate is reporting WEATHER, and would go red because someone compiled
something. But the ideal's own sentence is about the ESTATE:

    "every host-pressure axis ... has an executable gauge and a mechanical valve ... and the
     gauges are watched."

Gauge-and-valve completeness is a repo fact. So this is a ratchet, not a thermometer: green while
every declared axis keeps both halves, red the moment one is deleted or quietly disarmed. That is
the 2026-07-15 failure mode exactly — three individually-legitimate loads stacked while the gauge
that should have seen them was watched by nothing.

  A schema     — every axis declares note + gauge; gauge and valve each name EXACTLY ONE of
                 {path+symbol} or {sensor}; a null valve REQUIRES valve_absent_reason (Rule #1:
                 a vacuum is declared, never implicit).
  B gauge      — the gauge resolves: the file exists AND still contains the named symbol, or the
                 named sensor exists in the SENSORS registry. A gauge whose symbol was refactored
                 away is a gauge that stopped gauging.
  C valve      — the valve resolves AND is armed-by-default: a sensor valve must carry an
                 args_when entry with `armed_valve_type` on the declared env whose default is
                 "1"; a path valve must exist. A safety valve silently defaulted to "0" is the
                 SILENT-OFF class scripts/armed-valve-audit.py exists to catch — here it is a
                 red check on the specific axes that thrash this host.
  D watched    — at least one axis declares role: watcher and its gauge resolves. Without it the
                 gauges are unwatched, which is clause (c) of the ideal unmet.

Axes are read BY CAPABILITY, never by id — the estate is asked "which axes lack a gauge or an
armed valve", never "what does the sensor called host-relief do". Renaming an axis is free.

Prints `unguarded axes: N` on BOTH the green and red paths, because that line is the ideal-forms
probe's extract target and a red run must still yield a number.

  python3 scripts/check-host-pressure-estate.py
  python3 scripts/check-host-pressure-estate.py --list
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
REGISTRY_REL = "institutio/governance/host-pressure-axes.yaml"
SENSORS_REL = "institutio/governance/sensors.yaml"


def load_yaml(rel: str) -> dict:
    path = ROOT / rel
    if not path.is_file():
        raise SystemExit(f"FAIL — missing {rel}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_axes() -> dict[str, dict]:
    return load_yaml(REGISTRY_REL).get("axes") or {}


def load_sensors() -> dict[str, dict]:
    return load_yaml(SENSORS_REL).get("sensors") or {}


def _one_of(spec, *keys: str) -> str | None:
    """Which of `keys` this block declares, or None when it is not exactly one."""
    if not isinstance(spec, dict):
        return None
    present = [k for k in keys if spec.get(k) is not None]
    return present[0] if len(present) == 1 else None


def check_a_schema(axis_id: str, axis: dict) -> list[str]:
    found: list[str] = []
    if not str(axis.get("note") or "").strip():
        found.append(f"[A] {axis_id}: no `note` — an axis nobody can explain is not a declaration")

    gauge = axis.get("gauge")
    if _one_of(gauge, "path", "sensor") is None:
        found.append(f"[A] {axis_id}: gauge must declare EXACTLY ONE of path / sensor")
    elif gauge.get("path") and not str(gauge.get("symbol") or "").strip():
        found.append(f"[A] {axis_id}: a file gauge must name the `symbol` that proves it still gauges")

    if "valve" not in axis:
        found.append(f"[A] {axis_id}: no `valve` key — declare one, or null with valve_absent_reason")
    elif axis.get("valve") is None:
        if not str(axis.get("valve_absent_reason") or "").strip():
            found.append(f"[A] {axis_id}: valve is null without `valve_absent_reason` — an unnamed vacuum")
    elif _one_of(axis["valve"], "sensor", "path") is None:
        found.append(f"[A] {axis_id}: valve must declare EXACTLY ONE of sensor / path")
    return found


def check_b_gauge(axis_id: str, axis: dict, sensors: dict[str, dict]) -> list[str]:
    gauge = axis.get("gauge")
    if _one_of(gauge, "path", "sensor") is None:
        return []  # already reported by A

    if gauge.get("sensor"):
        sid = gauge["sensor"]
        if sid not in sensors:
            return [f"[B] {axis_id}: gauge names sensor {sid!r}, absent from the SENSORS registry"]
        return []

    rel = gauge["path"]
    path = ROOT / rel
    if not path.is_file():
        return [f"[B] {axis_id}: gauge file {rel} does not exist — the axis is ungauged"]
    symbol = str(gauge.get("symbol") or "").strip()
    if not symbol:
        return []  # already reported by A; B must not crash on a shape A has rejected
    if symbol not in path.read_text(encoding="utf-8"):
        return [
            f"[B] {axis_id}: {rel} no longer contains {symbol!r} — the gauge was refactored away "
            "and the axis is now unmeasured while still declared"
        ]
    return []


def check_c_valve(axis_id: str, axis: dict, sensors: dict[str, dict]) -> list[str]:
    valve = axis.get("valve")
    if valve is None:
        return []  # a declared vacuum; A already required the reason
    if _one_of(valve, "sensor", "path") is None:
        return []  # already reported by A

    if valve.get("path"):
        rel = valve["path"]
        if not (ROOT / rel).is_file():
            return [f"[C] {axis_id}: valve file {rel} does not exist — the axis has a gauge but no hands"]
        return []

    sid = valve["sensor"]
    sensor = sensors.get(sid)
    if sensor is None:
        return [f"[C] {axis_id}: valve names sensor {sid!r}, absent from the SENSORS registry"]

    env = valve.get("env")
    for step in sensor.get("steps") or []:
        for arm in step.get("args_when") or []:
            if arm.get("env") != env:
                continue
            if not arm.get("armed_valve_type"):
                return [f"[C] {axis_id}: {sid}/{env} is not classified with `armed_valve_type`"]
            if str(arm.get("default")) != "1":
                return [
                    f"[C] {axis_id}: {sid}/{env} defaults to {arm.get('default')!r}, not '1' — a "
                    "safety valve that is off unless someone remembers to arm it is SILENT-OFF, "
                    "and this host thrashes while it waits"
                ]
            return []
    return [f"[C] {axis_id}: {sid} declares no armed `args_when` entry for {env!r} — the valve has no arm"]


def check_d_watched(axes: dict[str, dict], gauge_findings: list[str]) -> list[str]:
    watchers = [aid for aid, a in axes.items() if a.get("role") == "watcher"]
    if not watchers:
        return [
            "[D] no axis declares role: watcher — the gauges are unwatched, which is clause (c) "
            "of the ideal unmet and the precondition of the 2026-07-15 stack"
        ]
    if all(any(w in f for f in gauge_findings) for w in watchers):
        return ["[D] every declared watcher's own gauge is broken — nothing watches the watchers"]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="print the declared estate and exit 0")
    args = parser.parse_args(argv)

    axes = load_axes()
    if not axes:
        print("FAIL — host-pressure-axes registry declares no axes")
        print("unguarded axes: 1")
        return 1

    if args.list:
        print(f"HOST-PRESSURE estate — {len(axes)} axes ({REGISTRY_REL})")
        for aid, axis in axes.items():
            gauge = axis.get("gauge") or {}
            valve = axis.get("valve")
            g = gauge.get("sensor") or f"{gauge.get('path')}:{gauge.get('symbol')}"
            v = "—(declared vacuum)" if valve is None else (valve.get("sensor") or valve.get("path"))
            role = axis.get("role", "axis")
            print(f"  {aid:16} {role:8} gauge={g}")
            print(f"  {'':16} {'':8} valve={v}")
        return 0

    sensors = load_sensors()
    findings: list[str] = []
    gauge_findings: list[str] = []
    unguarded: set[str] = set()

    for aid, axis in sorted(axes.items()):
        axis_findings = check_a_schema(aid, axis)
        gf = check_b_gauge(aid, axis, sensors)
        gauge_findings.extend(gf)
        axis_findings.extend(gf)
        axis_findings.extend(check_c_valve(aid, axis, sensors))
        if axis_findings:
            unguarded.add(aid)
        findings.extend(axis_findings)

    findings.extend(check_d_watched(axes, gauge_findings))

    if findings:
        print(f"FAILED: check-host-pressure-estate — {len(findings)} finding(s)")
        for f in findings:
            print(f"  ✗ {f}")
        print(f"unguarded axes: {max(len(unguarded), 1)}")
        print(
            "the ideal is an estate, not a thermometer: an axis without a gauge cannot see the "
            "load, and an axis without an armed valve cannot shed it"
        )
        return 1

    watchers = sum(1 for a in axes.values() if a.get("role") == "watcher")
    print(
        f"OK: check-host-pressure-estate — {len(axes)} axes "
        f"({len(axes) - watchers} gauged+valved, {watchers} watcher); every valve armed-by-default"
    )
    print("unguarded axes: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
