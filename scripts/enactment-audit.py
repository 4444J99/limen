#!/usr/bin/env python3
"""ENACTMENT audit — the predicate that proves a declared-ON flag is actually LIVE.

The gap this closes (the reason a switch had to be asked for five times): the repo's
"done" predicates — ``verify-whole.sh`` (lint/compile/tests/build) and
``no-tasks-on-me.sh`` (nothing dangling) — all measure **declaration**: code merged,
build green, nothing parked. **None measures ENACTMENT** — is the switch on in the
*running* beat, and did the daemon reload after the wiring changed. TABVLARIVS #576
shipped its producers switched OFF; ``parameters.yaml``'s note *claimed in prose* the
fleet enabled it; and every gate went green on the dark state. The only thing that
could see the gap was the operator, by hand, repeatedly. This script is that missing
gate — it makes "enacted" a predicate, not a memory.

Two rungs, each catching one real trap:

  1. WIRING (static, CI-safe, ALWAYS enforced). For every ``parameters.yaml`` flag that
     declares ``fleet_runtime:`` (the value the LIVE FLEET must resolve it to), re-derive
     what ``scripts/heartbeat-loop.sh`` (+ ``~/.limen.env`` on the live host) actually
     resolves the flag to, and fail if it diverges. Catches "declared ON, wired nowhere"
     — the #576 bug exactly (the note said ON, no ``export`` line made it so).

  2. LIVENESS (live-host only; SKIP when no daemon is running — CI-safe). The running
     heartbeat daemon must have started AFTER the last change to its wiring
     (``heartbeat-loop.sh`` / ``~/.limen.env``). A long-running ``while true`` never
     re-sources itself, so a wiring change that predates the process is live-dark until
     a kickstart. Catches "wired but daemon not kickstarted" (sync-release's own log
     says "kickstart to load").

Usage:
  scripts/enactment-audit.py            # human report (all rungs, with live context)
  scripts/enactment-audit.py --check    # gate: exit 1 on any RED rung (SKIP never fails)
  scripts/enactment-audit.py --heartbeat PATH --params PATH   # override inputs (tests)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

SCRIPT_ROOT = Path(__file__).resolve().parent.parent  # the checkout THIS script lives in
LIVE_ROOT = Path(os.environ.get("LIMEN_ROOT", str(SCRIPT_ROOT)))
HOME = Path(os.path.expanduser("~"))

GREEN, RED, SKIP, INFO = "GREEN", "RED", "SKIP", "INFO"


# --------------------------------------------------------------------------- wiring
def heartbeat_default(var: str, heartbeat: Path) -> str | None:
    """What the beat's own wiring defaults ``var`` to.

    The heartbeat resolves each fleet flag with a line of the shape
    ``export VAR="${VAR:-DEFAULT}"`` (sourced AFTER ~/.limen.env, so an env override
    wins; absent an override the DEFAULT is what the fleet gets). Return DEFAULT, or
    None when the beat has no such line at all — the #576 state: the flag is declared
    but the beat wires nothing, so the running process never sees it set.
    """
    if not heartbeat.exists():
        return None
    text = heartbeat.read_text(errors="ignore")
    # export VAR="${VAR:-DEFAULT}"  /  export VAR=${VAR:-DEFAULT}  (quotes optional)
    pat = re.compile(
        r"^\s*export\s+" + re.escape(var) + r'=(?:"?)\$\{' + re.escape(var) + r":-([^}]*)\}",
        re.MULTILINE,
    )
    m = pat.search(text)
    if m:
        return m.group(1).strip('"')
    # A bare `export VAR="1"` (no :- default) also wires it deterministically.
    bare = re.compile(r"^\s*export\s+" + re.escape(var) + r'="?([^"\n$][^"\n]*)"?\s*$', re.MULTILINE)
    b = bare.search(text)
    return b.group(1).strip('"') if b else None


def limen_env_override(var: str) -> str | None:
    """A non-empty value the live host pins for ``var`` in ~/.limen.env (wins over the
    beat default, since it is sourced first and ``${VAR:-…}`` keeps a set value).
    Empty assignment (VAR="") counts as unset for ``:-`` semantics → None."""
    env_file = HOME / ".limen.env"
    if not env_file.exists():
        return None
    for line in env_file.read_text(errors="ignore").splitlines():
        m = re.match(r"^\s*(?:export\s+)?" + re.escape(var) + r"=(.*)$", line)
        if m:
            val = m.group(1).strip().strip('"').strip("'")
            return val or None
    return None


def wiring_rung(params: dict, heartbeat: Path, *, live: bool) -> list[dict]:
    """One row per flag that declares ``fleet_runtime``. RED when the committed beat
    wiring does not resolve the flag to the declared fleet value."""
    rows: list[dict] = []
    for name, spec in (params.get("parameters") or {}).items():
        if not isinstance(spec, dict) or "fleet_runtime" not in spec:
            continue
        want = str(spec["fleet_runtime"])
        wired = heartbeat_default(name, heartbeat)
        override = limen_env_override(name) if live else None
        # The gate enforces the CODE contract: the committed beat wiring must resolve
        # to the declared fleet value. A deliberate live override is reported, not failed.
        if wired == want:
            status, why = GREEN, f"heartbeat wires {name}={want} (matches fleet_runtime)"
        elif wired is None:
            status, why = (
                RED,
                (
                    f"{name} declares fleet_runtime={want} but heartbeat-loop.sh wires it NOWHERE "
                    f"— the running beat never sets it (this is the #576 dark-switch failure)"
                ),
            )
        else:
            status, why = RED, (f"{name} declares fleet_runtime={want} but heartbeat-loop.sh wires it to {wired!r}")
        if override is not None and override != want:
            rows.append(
                {
                    "rung": "wiring",
                    "name": name,
                    "status": INFO,
                    "detail": f"live ~/.limen.env pins {name}={override!r} (deliberate operator override of fleet default {want})",
                }
            )
        rows.append({"rung": "wiring", "name": name, "status": status, "detail": why})
    return rows


# -------------------------------------------------------------------------- liveness
def parse_etime(etime: str) -> int | None:
    """ps -o etime (``[[dd-]hh:]mm:ss``) → elapsed seconds. macOS/BSD-safe (no etimes)."""
    etime = etime.strip()
    if not etime:
        return None
    days = 0
    if "-" in etime:
        d, etime = etime.split("-", 1)
        days = int(d)
    parts = [int(p) for p in etime.split(":")]
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = 0, parts[0], parts[1]
    else:
        return None
    return days * 86400 + h * 3600 + m * 60 + s


def heartbeat_pid() -> int | None:
    try:
        out = subprocess.run(["pgrep", "-f", "heartbeat-loop.sh"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return None
    pids = [int(x) for x in out.split() if x.strip().isdigit()]
    return min(pids) if pids else None  # the loop process is the oldest


def process_start_epoch(pid: int) -> float | None:
    try:
        out = subprocess.run(["ps", "-o", "etime=", "-p", str(pid)], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return None
    elapsed = parse_etime(out)
    return (time.time() - elapsed) if elapsed is not None else None


def file_assigns_any(path: Path, names: list[str]) -> bool:
    """True if ``path`` actually assigns any of ``names`` (an ``export VAR=`` / ``VAR=``
    line). This is what makes the liveness rung immune to files a beat rewrites without
    touching the flag — e.g. the credential organ re-hydrates ~/.limen.env EVERY beat
    (bumping its mtime), but never assigns LIMEN_TICKETS_PRODUCE, so it must not count as
    a wiring change. Only a file that genuinely sets the flag is its wiring."""
    if not path.exists():
        return False
    text = path.read_text(errors="ignore")
    for var in names:
        if re.search(r"^\s*(?:export\s+)?" + re.escape(var) + r"=", text, re.MULTILINE):
            return True
    return False


def liveness_rung(params: dict) -> list[dict]:
    """RED when the running daemon predates its wiring (stale env → live-dark).
    SKIP when no daemon is running (CI / non-live host) — never fails there."""
    fleet_vars = [
        k for k, s in (params.get("parameters") or {}).items() if isinstance(s, dict) and "fleet_runtime" in s
    ]
    if not fleet_vars:  # nothing asserts a fleet_runtime intent → nothing to keep live
        return []
    pid = heartbeat_pid()
    if pid is None:
        return [
            {
                "rung": "liveness",
                "name": "heartbeat-daemon",
                "status": SKIP,
                "detail": "no heartbeat-loop.sh process running — not on the live host (rung N/A)",
            }
        ]
    start = process_start_epoch(pid)
    if start is None:
        return [
            {
                "rung": "liveness",
                "name": "heartbeat-daemon",
                "status": SKIP,
                "detail": f"heartbeat pid {pid} found but start time unreadable (rung N/A)",
            }
        ]
    # Only files that ACTUALLY assign a fleet flag are its wiring — a file the beat churns
    # (~/.limen.env, re-hydrated every beat) without setting the flag is not a wiring change.
    wiring_files = [LIVE_ROOT / "scripts" / "heartbeat-loop.sh", HOME / ".limen.env"]
    newest = 0.0
    newest_src = None
    for f in wiring_files:
        if file_assigns_any(f, fleet_vars) and f.stat().st_mtime > newest:
            newest, newest_src = f.stat().st_mtime, f
    if newest > start:
        drift = int(newest - start)
        return [
            {
                "rung": "liveness",
                "name": "heartbeat-daemon",
                "status": RED,
                "detail": (
                    f"daemon pid {pid} started {int(time.time() - start)}s ago but its wiring "
                    f"({newest_src.name if newest_src else '?'}) changed {drift}s more recently "
                    f"— running stale env; kickstart to load "
                    f"(launchctl kickstart -k gui/$(id -u)/com.limen.heartbeat)"
                ),
            }
        ]
    return [
        {
            "rung": "liveness",
            "name": "heartbeat-daemon",
            "status": GREEN,
            "detail": f"daemon pid {pid} started after its last wiring change — running current env",
        }
    ]


# ------------------------------------------------------------------------------ main
def run(heartbeat: Path, params_path: Path, *, wiring_only: bool = False) -> list[dict]:
    params = yaml.safe_load(params_path.read_text()) or {}
    live = LIVE_ROOT == SCRIPT_ROOT or (LIVE_ROOT / "scripts" / "heartbeat-loop.sh").exists()
    rows = wiring_rung(params, heartbeat, live=live)
    if not wiring_only:  # liveness reads live host state; tests pin to the code contract only
        rows += liveness_rung(params)
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Prove declared-ON fleet flags are actually enacted.")
    ap.add_argument("--check", action="store_true", help="gate mode: exit 1 on any RED rung")
    ap.add_argument(
        "--wiring-only",
        action="store_true",
        help="skip the live-host liveness rung (deterministic code-contract check for tests)",
    )
    ap.add_argument("--heartbeat", default=str(SCRIPT_ROOT / "scripts" / "heartbeat-loop.sh"))
    ap.add_argument("--params", default=str(SCRIPT_ROOT / "institutio" / "governance" / "parameters.yaml"))
    args = ap.parse_args(argv)

    rows = run(Path(args.heartbeat), Path(args.params), wiring_only=args.wiring_only)
    reds = [r for r in rows if r["status"] == RED]

    if not args.check:
        icon = {GREEN: "✅", RED: "❌", SKIP: "⚪", INFO: "ℹ️ "}
        print("ENACTMENT audit — is each declared-ON fleet flag actually LIVE?\n")
        for r in rows:
            print(f"  {icon.get(r['status'], '?')} [{r['rung']}] {r['name']}: {r['detail']}")
        if not rows:
            print("  (no flag declares fleet_runtime — nothing to enact-check)")
        print()
        print(f"{len(reds)} RED / {len(rows)} rungs")

    if reds:
        if args.check:
            for r in reds:
                print(f"ENACTMENT RED [{r['rung']}] {r['name']}: {r['detail']}", file=sys.stderr)
        return 1
    if args.check:
        print(f"enactment-audit: {len(rows)} rung(s) green/skip — declared-ON flags are enacted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
