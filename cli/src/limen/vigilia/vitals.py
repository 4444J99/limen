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
axis catches CPU-only storms.

Third axis (2026-07-16 host-thrash incident): swap-backed memory starvation. A
`bztransmit -updatebackupstats` pass held 8.6 GiB while swap sat at 17.3/18 GiB and
free RAM at 94 MB — and the jetsam gauge reported only 'warn' for hours. Two swap
signals close that blind spot: the OS growing the swap ESTATE to physical-RAM size is
its own overcommit declaration (crit), and swap USED near RAM size is the warn ramp.
Cold swap stock alone (large used, modest total, healthy free RAM) stays green.

All axes combine by MAX severity: any can throttle/shed, none can mask another. A
warn that SUSTAINS for VITALS_WARN_SUSTAIN_BEATS consecutive gate beats escalates to
shed — 7/16 sat at 'warn' for hours; sustained warn IS critical. The streak counts
only on real gate/admission observations, at most once per minute. Read-only
records never count. Shared host state is boot-bound and expires after two
declared VITALS sampling periods; old checkout counters stay untouched.

Kernel/load/swap fallback behavior is unchanged. Invalid shared warning history
propagates as unmeasured to admission rather than fabricating a normal history.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import subprocess
import stat
import sys
import tempfile
import time
from pathlib import Path

from . import params

OK = "ok"
THROTTLE = "throttle"  # >= warn: report pressure; the keeper owns campaign admission
SHED = "shed"  # >= critical: local admission stops; keeper-routed off-box work remains eligible

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
            timeout=1,
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


_SWAP_RE = re.compile(r"total\s*=\s*([\d.]+)M.*?used\s*=\s*([\d.]+)M")


def read_swap() -> dict | None:
    """Swap estate + physical RAM in bytes, or None on any failure (fail-open)."""
    try:
        swap = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, timeout=5)
        ram = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
        m = _SWAP_RE.search(swap.stdout or "")
        if swap.returncode == 0 and m and ram.returncode == 0 and ram.stdout.strip().isdigit():
            mib = 1024 * 1024
            return {
                "total_bytes": int(float(m.group(1)) * mib),
                "used_bytes": int(float(m.group(2)) * mib),
                "ram_bytes": int(ram.stdout.strip()),
            }
    except Exception:
        pass
    return None


def assess_swap(swap: dict | None) -> str:
    """Map the swap estate to an action. Crit ⟺ swap TOTAL allocated >= physical RAM
    (the OS declaring overcommit — 18 GiB > 16 GiB during the 2026-07-16 thrash);
    warn ⟺ swap USED >= VITALS_SWAP_WARN_RATIO x RAM. Healthy cold swap stays ok."""
    if not swap or not swap.get("ram_bytes"):
        return OK
    ram = swap["ram_bytes"]
    crit_ratio = params.get("VITALS_SWAP_TOTAL_CRIT_RATIO", 1.0, cast=float)
    warn_ratio = params.get("VITALS_SWAP_WARN_RATIO", 0.75, cast=float)
    if swap.get("total_bytes", 0) >= ram * crit_ratio:
        return SHED
    if swap.get("used_bytes", 0) >= ram * warn_ratio:
        return THROTTLE
    return OK


def _streak_path() -> Path:
    from limen.host_admission import default_state_root

    return default_state_root() / "vitals-streak.json"


def _boot_identity() -> str:
    if sys.platform == "darwin":
        from limen.heartbeat import _clock_observation

        observation = _clock_observation()
        if observation.get("measured") is True:
            return str(observation["boot_id"])
    else:
        try:
            return hashlib.sha256(Path("/proc/sys/kernel/random/boot_id").read_bytes()).hexdigest()
        except OSError:
            pass
    raise ValueError("vitals_boot_unmeasured")


def _streak_max_age() -> float:
    return 2 * max(60, params.get("VITALS_SAMPLE_SECONDS", 300, cast=int))


def _read_streak(path: Path, now: float, boot: str) -> tuple[int, float]:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return 0, 0.0
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 16384:
            raise ValueError("vitals_streak_state_unsafe")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            prior = json.loads(stream.read(16385))
    finally:
        os.close(fd)
    if not isinstance(prior, dict) or prior.get("schema") != "limen.vitals_warn_streak.v2":
        raise ValueError("vitals_streak_state_invalid")
    streak, last = prior.get("streak"), prior.get("last")
    if type(streak) is not int or streak < 0 or not isinstance(last, (int, float)) or isinstance(last, bool):
        raise ValueError("vitals_streak_state_invalid")
    try:
        timestamp = float(last)
    except OverflowError as exc:
        raise ValueError("vitals_streak_state_invalid") from exc
    if not math.isfinite(timestamp):
        raise ValueError("vitals_streak_state_invalid")
    if prior.get("boot_id") != boot or not 0 <= now - timestamp <= _streak_max_age():
        return 0, 0.0
    return streak, timestamp


def _update_warn_streak(action: str, update: bool, *, state_root: Path | None = None) -> int:
    """Consecutive gate beats at >= throttle, persisted across processes.

    Increments only on the gate path (``update=True``) and at most once per 60 s, so
    the executive's read-only record and rapid re-invocations never inflate it.
    Freshness, boot identity and atomic host-wide updates define consecutiveness.
    Read-only calls never create/reset files. Invalid shared state is unmeasured;
    admission fails closed rather than fabricating a healthy history.
    """
    path = state_root / "vitals-streak.json" if state_root is not None else _streak_path()
    if not update:
        try:
            path.lstat()
        except FileNotFoundError:
            return 0
        streak, _last = _read_streak(path, time.time(), _boot_identity())
        return 0 if action == OK else streak
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or parent.st_mode & 0o077:
        raise ValueError("vitals_streak_root_unsafe")
    lock = os.open(path.with_suffix(".lock"), os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    temporary = None
    try:
        info = os.fstat(lock)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("vitals_streak_lock_unsafe")
        deadline = time.monotonic() + 0.25
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ValueError("vitals_streak_lock_unavailable")
                time.sleep(0.005)
        now, boot = time.time(), _boot_identity()
        streak, last = _read_streak(path, now, boot)
        if action == OK:
            streak, last = 0, now
        elif streak == 0 or now - last >= 60.0:
            streak, last = streak + 1, now
        fd, temporary = tempfile.mkstemp(prefix=".vitals-streak-", dir=path.parent)
        with os.fdopen(fd, "w") as stream:
            json.dump(
                {"schema": "limen.vitals_warn_streak.v2", "streak": streak, "last": last, "boot_id": boot}, stream
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        return streak
    finally:
        if temporary is not None:
            os.unlink(temporary)
        os.close(lock)


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


def beat_gate(shed: bool = True, *, record: bool | None = None, state_root: Path | None = None) -> dict:
    """The per-beat VITALS decision.

    Returns a status dict. The heartbeat reads ``status['action'] == 'shed'`` to
    force an idle beat. Under critical pressure (and ``shed``), also sheds ollama.
    """
    level = read_pressure()
    memory_action = assess(level)
    load_per_core = read_load()
    load_action = assess_load(load_per_core)
    swap = read_swap()
    swap_action = assess_swap(swap)
    # MAX severity across the axes: any gauge can throttle/shed, none masks another.
    action = max(memory_action, load_action, swap_action, key=lambda a: _SEVERITY.get(a, 0))
    # Sustained warn IS critical (2026-07-16: hours at 'warn' while swap filled).
    sustain = params.get("VITALS_WARN_SUSTAIN_BEATS", 3, cast=int)
    recorded = shed if record is None else record
    streak_status = "measured"
    try:
        if state_root is None:
            streak = _update_warn_streak(action, update=recorded)
        else:
            streak = _update_warn_streak(action, update=recorded, state_root=state_root)
    except (OSError, ValueError):
        if action != SHED:
            raise
        streak, streak_status = 0, "unmeasured"
    sustained = sustain > 0 and action == THROTTLE and streak >= sustain
    if sustained:
        action = SHED
    warn = params.get("VITALS_PRESSURE_WARN", 2, cast=int)
    crit = params.get("VITALS_PRESSURE_CRITICAL", 4, cast=int)
    shed_enabled = str(params.get("VITALS_SHED_OLLAMA", "1")) not in ("0", "false", "False")
    stopped: list[str] = []
    if shed and shed_enabled and action == SHED:
        stopped = shed_ollama()
    gib = 2**30
    return {
        "organ": "vitals",
        "level": level,
        "warn": warn,
        "critical": crit,
        "load_per_core": round(load_per_core, 3),
        "load_action": load_action,
        "memory_action": memory_action,
        "swap_used_gib": round(swap["used_bytes"] / gib, 2) if swap else None,
        "swap_total_gib": round(swap["total_bytes"] / gib, 2) if swap else None,
        "ram_gib": round(swap["ram_bytes"] / gib, 2) if swap else None,
        "swap_action": swap_action,
        "warn_streak": streak,
        "warn_streak_status": streak_status,
        "warn_streak_mode": "shared_boot_bound_recent",
        "warn_streak_recorded": recorded,
        "warn_streak_max_age_seconds": _streak_max_age(),
        "migration_diagnostic": "legacy_repository_streak_not_imported",
        "sustained_warn": sustained,
        "action": action,
        "shed_ollama": stopped,
        "heavy_surface_limit": params.get("VITALS_HEAVY_SURFACE_LIMIT", 1, cast=int),
    }
