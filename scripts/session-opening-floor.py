#!/usr/bin/env python3
"""session-opening-floor.py — what tier does each lane OPEN an interactive session at?

The cadence question generalized past Claude (F6 of the 2026-08-07 cadence-guard arc). The
operator's framing was "all providers, not just Claude": every vendor with an interactive surface
has some opening default, each pinned in its own file, and until this existed nothing in the
estate could say what any of them were. Measured that day, by hand, because no predicate could:
`~/.codex/config.toml` carried gpt-5.6-sol at `ultra` effort — one rung above what the work needs
— and `~/.gemini/settings.json` carried no `model` key at all.

ONE PROBE, DERIVED — never a per-vendor branch. Rows come from `census.OPENING_FLOORS`, keyed by
canonical vendor name and completeness-checked against `census.VENDORS`, so a new lane lands as a
RED undeclared row instead of silently inheriting "no cadence applies". Nothing here dispatches on
a vendor name; it dispatches on `OpeningFloor.kind`, exactly as the sensor registry's consumers
read capabilities rather than sensor ids.

VERDICTS. Every row carries a reason — Rule #1: an N/A is a vacuum, never a resting state.

  ok            the declared pin is at or below the lane's ceiling
  above-ceiling the lane opens dearer than declared, AND a lever cites it   → PARKED, exit 0
  ABOVE-CEILING the lane opens dearer than declared with NO lever citation  → exit 1
  unset         the config exists but declares no pin — reported as UNKNOWN, never as cheap
  unresolved    the lane is interactive but its config was not located (the honest starting state)
  arm-delegated the pin lives in a store no predicate can read; the arming valve owns it (D8)
  not-interactive / not-metered   no opening default can exist here, and that is the reason
  UNDECLARED    a vendor with no OPENING_FLOORS row                        → exit 1

`arm-delegated` is design decision D8 in force: `~/.claude/settings.json` arming state has exactly
ONE reader in this estate — `armed-valve-audit.probe_file_json`, driven by spec/armed-valves.json.
This script delegates to it by valve id and never opens that file itself, so the two can never
disagree about whether the guard is armed.

READ-ONLY. Never writes a config, never arms anything.

Usage:
  python3 scripts/session-opening-floor.py            # census report
  python3 scripts/session-opening-floor.py --check    # gate mode
  python3 scripts/session-opening-floor.py --json     # machine rows
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent.parent


def _load(path: Path, modname: str):
    """Load a module by FILE PATH from this script's own repo tree — code by __file__, runtime
    state by LIMEN_ROOT (the same split the session guard's loader uses, for the same reason: a
    worktree-run verification must resolve the code it is verifying)."""
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


def _census():
    return _load(SCRIPT_ROOT / "cli" / "src" / "limen" / "census.py", "_limen_census_floor")


def _model_selection():
    return _load(SCRIPT_ROOT / "cli" / "src" / "limen" / "model_selection.py", "_limen_ms_floor")


def _armed_valve_audit():
    return _load(SCRIPT_ROOT / "scripts" / "armed-valve-audit.py", "_limen_ava_floor")


def _resolve_ladder(floor, ms) -> tuple[str, ...]:
    """A declared ladder, or the one named by `ladder_ref` — a REFERENCE to live code, never a
    copied snapshot, so the Claude ladder is not re-typed in the census and cannot drift."""
    if floor.ladder:
        return tuple(floor.ladder)
    ref = getattr(floor, "ladder_ref", "")
    if ref and ms is not None and ":" in ref:
        _, attr = ref.split(":", 1)
        value = getattr(ms, attr, None)
        if isinstance(value, tuple):
            return value
    return ()


def _read_pin(path: Path, pointer: str):
    """Provider-neutral read: json or toml, dotted pointer. (value, detail)."""
    if not path.exists():
        return None, f"{path} absent"
    try:
        text = path.read_text(errors="replace")
        if path.suffix == ".toml":
            import tomllib

            doc = tomllib.loads(text)
        else:
            doc = json.loads(text)
    except Exception as exc:  # noqa: BLE001 — an unreadable config is the finding
        return None, f"unreadable ({type(exc).__name__})"
    cur = doc
    for seg in pointer.split("."):
        if not isinstance(cur, dict) or seg not in cur:
            return None, f"no {pointer!r} key in {path.name}"
        cur = cur[seg]
    return cur, ""


def _arm_state(valve_id: str, registry_path: Path):
    """Delegate to the ONE reader of settings.json arming state (D8)."""
    ava = _armed_valve_audit()
    if ava is None:
        return None, "armed-valve-audit unavailable"
    try:
        registry = json.loads(registry_path.read_text())
    except Exception as exc:  # noqa: BLE001
        return None, f"armed-valve registry unreadable ({type(exc).__name__})"
    for entry in registry.get("deliverable", []):
        if entry.get("id") == valve_id:
            ok, note = ava.probe_file_json(entry)
            return ok, note
    return None, f"valve {valve_id} not classified in spec/armed-valves.json"


def rows(levers_text: str = "", registry_path: Path | None = None) -> list[dict]:
    census = _census()
    ms = _model_selection()
    if census is None:
        return [{"lane": "-", "verdict": "UNDECLARED", "detail": "census.py could not be loaded"}]
    registry_path = registry_path or (SCRIPT_ROOT / "spec" / "armed-valves.json")

    out: list[dict] = []
    for name in census.undeclared_opening_floors():
        out.append(
            {
                "lane": name,
                "verdict": "UNDECLARED",
                "kind": "",
                "detail": "vendor has no OPENING_FLOORS row — declare one in cli/src/limen/census.py",
            }
        )

    for vendor in census.VENDORS:
        floor = census.OPENING_FLOORS.get(vendor.name)
        if floor is None:
            continue  # already surfaced as UNDECLARED above
        kind = floor.kind
        row = {"lane": vendor.name, "kind": kind, "ceiling": floor.ceiling, "detail": floor.note}

        if kind in ("not-interactive", "not-metered", "unresolved"):
            row["verdict"] = kind
            out.append(row)
            continue

        if kind == "hook-armed":
            armed, note = _arm_state(floor.arming_valve, registry_path)
            row["verdict"] = "arm-delegated"
            row["armed"] = armed
            row["detail"] = f"valve {floor.arming_valve}: {note} — {floor.note}"
            out.append(row)
            continue

        # kind == "config-file": the provider-neutral probe.
        path = Path(os.path.expandvars(floor.config_path)).expanduser()
        value, detail = _read_pin(path, floor.pointer)
        if value is None:
            row["verdict"] = "unset"
            row["detail"] = f"{detail} — reported as UNKNOWN, never assumed cheap"
            out.append(row)
            continue

        ladder = _resolve_ladder(floor, ms)
        row["pin"] = str(value)
        if ms is None or not ladder:
            row["verdict"] = "unresolved"
            row["detail"] = f"pin={value!r} but no ladder is resolvable for this lane"
            out.append(row)
            continue

        verdict = ms.opening_verdict(str(value), floor.ceiling or None, ladder)
        if verdict["state"] == "ok":
            row["verdict"] = "ok"
            row["detail"] = f"pin={value!r} at rung {verdict['rung']!r} <= ceiling {verdict['ceiling']!r}"
        elif verdict["state"] == "unresolved":
            row["verdict"] = "unresolved"
            row["detail"] = f"pin={value!r} matches no rung of {ladder} — cannot be placed"
        else:
            cited = bool(levers_text) and ("L-LANE-OPENING-FLOOR" in levers_text or vendor.name in levers_text)
            row["verdict"] = "above-ceiling" if cited else "ABOVE-CEILING"
            row["detail"] = (
                f"pin={value!r} is rung {verdict['rung']!r}, above ceiling {verdict['ceiling']!r} "
                f"({floor.config_path} :: {floor.pointer})"
                + ("  [owned: L-LANE-OPENING-FLOOR]" if cited else "  [NO lever cites it]")
            )
        out.append(row)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Per-lane interactive session-opening floor census.")
    ap.add_argument("--check", action="store_true", help="gate mode: exit 1 on an uncited breach or an undeclared lane")
    ap.add_argument("--json", action="store_true", help="print rows as JSON")
    ap.add_argument("--levers", default=str(SCRIPT_ROOT / "his-hand-levers.json"))
    ap.add_argument("--registry", default=str(SCRIPT_ROOT / "spec" / "armed-valves.json"))
    args = ap.parse_args(argv)

    levers = Path(args.levers)
    levers_text = levers.read_text(errors="replace") if levers.exists() else ""
    result = rows(levers_text, Path(args.registry))

    if args.json:
        print(json.dumps(result, indent=1))
    else:
        for r in result:
            print(f"  {r['verdict']:<16} {r['lane']:<16} {r.get('detail', '')}")
        counts: dict[str, int] = {}
        for r in result:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        print("session-opening-floor: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    hard = [r for r in result if r["verdict"] in ("ABOVE-CEILING", "UNDECLARED")]
    if args.check and hard:
        print(
            "session-opening-floor: RED — "
            + ", ".join(f"{r['lane']} ({r['verdict']})" for r in hard)
            + "; lower the pin, or file it as L-LANE-OPENING-FLOOR in his-hand-levers.json",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
