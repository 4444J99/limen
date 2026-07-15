"""VITALS — the don't-crash reaction function (CFO).

Reads the kernel's own memory-pressure gauge and, under pressure, makes the beat
go idle (stop opening new dispatch lanes) and sheds discretionary load (ollama).
This is the hand that was missing at the 08:47 kernel panic: the diagnosis
("treat 16 GB as a budget, not a floor") existed; the reaction did not.

macOS ``kern.memorystatus_vm_pressure_level``: 1 = normal, 2 = warn, 4 = critical.
  * >= warn      -> throttle (dispatch continues at a reduced cap — a 16 GB host lives
                    at warn under normal load; a full idle beat here starved the fleet
                    for a night, 2026-07-08: 273 skipped beats with budget unused)
  * >= critical  -> block new local checkout work + shed discretionary load (ollama);
                    off-box provider lanes remain eligible

Second axis (2026-07-15 host-thrash incident): 1-min load average per core. Backblaze's
post-reboot crawl plus concurrent full pytest suites pinned the CPU while the jetsam
gauge alone could not see the storm shape — memory stays the primary gauge, the load
axis catches CPU-only storms. The two axes combine by MAX severity: either can
throttle/shed, neither can mask the other.

Fail-OPEN everywhere: a sensor fault reads as 'normal' and never blocks the beat.
"""

from __future__ import annotations

import os
import subprocess

from . import params

OK = "ok"
THROTTLE = "throttle"  # >= warn: dispatch continues, cap divided by VITALS_THROTTLE_DIVISOR
SHED = "shed"  # >= critical: local admission stops; remote dispatch remains live

# kernel level for "normal" — the fail-open value when the gauge can't be read.
_NORMAL = 1


def read_pressure() -> int:
    """Return the integer memory-pressure level, or 1 (normal) on any failure."""
    gauge = params.get("VITALS_PRESSURE_GAUGE", "kern.memorystatus_vm_pressure_level")
    try:
        out = subprocess.run(
            ["sysctl", "-n", str(gauge)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        val = out.stdout.strip()
        if out.returncode == 0 and val.lstrip("-").isdigit():
            return int(val)
    except Exception:
        pass
    return _NORMAL


def assess(level: int) -> str:
    """Map a pressure level to an action ('ok' | 'throttle' | 'shed')."""
    warn = params.get("VITALS_PRESSURE_WARN", 2, cast=int)
    crit = params.get("VITALS_PRESSURE_CRITICAL", 4, cast=int)
    if level >= crit:
        return SHED
    if level >= warn:
        return THROTTLE
    return OK


def read_load() -> float:
    """Return the 1-min load average per core, or 0.0 (normal) on any failure."""
    try:
        return os.getloadavg()[0] / (os.cpu_count() or 1)
    except Exception:
        return 0.0


def assess_load(per_core: float) -> str:
    """Map per-core load to an action. Thresholds are deliberately loose (warn 1.5,
    crit 3.0) so memory stays the primary gauge — the 2026-07-08 starved-fleet night
    is the precedent against tight thresholds."""
    warn = params.get("VITALS_LOAD_WARN_PER_CORE", 1.5, cast=float)
    crit = params.get("VITALS_LOAD_CRIT_PER_CORE", 3.0, cast=float)
    if per_core >= crit:
        return SHED
    if per_core >= warn:
        return THROTTLE
    return OK


_SEVERITY = {OK: 0, THROTTLE: 1, SHED: 2}


def shed_ollama() -> list[str]:
    """Best-effort: stop loaded ollama models to free RAM. Gated + fail-open.

    Returns the names of models it asked to stop (empty if none/unavailable).
    """
    stopped: list[str] = []
    try:
        ps = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=5)
        if ps.returncode != 0:
            return stopped
        for line in ps.stdout.splitlines()[1:]:  # skip header row
            parts = line.split()
            if not parts:
                continue
            name = parts[0]
            try:
                subprocess.run(
                    ["ollama", "stop", name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                stopped.append(name)
            except Exception:
                pass
    except Exception:
        pass
    return stopped


def beat_gate(shed: bool = True) -> dict:
    """The per-beat VITALS decision.

    Returns a status dict. The heartbeat reads ``status['action'] == 'shed'`` to
    force an idle beat. Under critical pressure (and ``shed``), also sheds ollama.
    """
    level = read_pressure()
    memory_action = assess(level)
    load_per_core = read_load()
    load_action = assess_load(load_per_core)
    # MAX severity across the two axes: either gauge can throttle/shed, neither masks the other.
    action = max(memory_action, load_action, key=lambda a: _SEVERITY.get(a, 0))
    warn = params.get("VITALS_PRESSURE_WARN", 2, cast=int)
    crit = params.get("VITALS_PRESSURE_CRITICAL", 4, cast=int)
    shed_enabled = str(params.get("VITALS_SHED_OLLAMA", "1")) not in ("0", "false", "False")
    stopped: list[str] = []
    if shed and shed_enabled and action == SHED:
        stopped = shed_ollama()
    return {
        "organ": "vitals",
        "level": level,
        "warn": warn,
        "critical": crit,
        "load_per_core": round(load_per_core, 3),
        "load_action": load_action,
        "memory_action": memory_action,
        "action": action,
        "shed_ollama": stopped,
        "heavy_surface_limit": params.get("VITALS_HEAVY_SURFACE_LIMIT", 1, cast=int),
    }
