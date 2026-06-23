#!/usr/bin/env python3
"""watchdog.py — the SELF-WATCHDOG organ: the loop that NOTICES ITS OWN DEATH.

The heartbeat once sat DEAD for ~8-26h on a silent false-pause (missing toolchain →
crash-loop; then a one-line `secrets` import bug failing every dispatch) and nothing
caught it — it took a human asking "why are we idle". A finished autonomic system
asserts its own health each beat. This organ closes that gap.

Each invocation it asserts THREE health checks and, on failure, raises EXACTLY ONE
alert (deduped by failure-signature — never a spam loop) and OPTIONALLY self-heals
behind a double gate. Default is DETECT + ALERT only; it never restarts unprompted.

  CHECK 1  daemon-up     launchd com.limen.heartbeat running AND the pid in
                         logs/heartbeat-loop.pid is alive (ps -p).
  CHECK 2  beating       most-recent `tick emitted: <ISO8601> ...` in
                         logs/heartbeat.out.log is within LIMEN_WATCHDOG_STALE_SEC.
  CHECK 3  not-wedged    no >=LIMEN_WATCHDOG_MAX_FAILS consecutive most-recent
                         `PARALLEL done` beats produced 0 PRs (wedged dispatch).

It also carries ONE soft, non-health SIGNAL (it never raises the red alert):

  loop-body  current?    the running daemon's loaded loop body == what's on disk.
                         A loop-body edit (heartbeat-loop.sh) only takes effect when the
                         daemon RELOADS — the live `while true` body is read once at startup.
                         sync-release ff's the file to disk, but the running process keeps the
                         OLD body until a kickstart, so a merged loop-body fix lies DORMANT until
                         the daemon happens to restart — today only on a freeze, i.e. the very
                         failure the fix may exist to prevent. When the on-disk loop body is newer
                         than the running daemon (pidfile mtime == daemon start; written once at
                         startup), this organ kickstarts BETWEEN BEATS to load it — same double-gate
                         (+ LIMEN_WATCHDOG_RELOAD) as heal(), self-clearing, no alert.

On any failure: write ONE alert to logs/watchdog-alert.json (ts, failed check,
evidence) + append a line to logs/watchdog.log. Idempotent: same signature already
active → no re-fire; health returns → clear the alert. Self-heal (launchctl kickstart)
is gated behind --heal AND LIMEN_WATCHDOG_HEAL=1.

  --dry-run   assess + print, NO writes (and NO reload kickstart)
  --heal      allow restart (also needs LIMEN_WATCHDOG_HEAL=1); also arms loop-body reload
  (default)   assess + write alert/log, no restart

Env-parameterized (DERIVE, never hardcode):
  LIMEN_ROOT             conductor root (default ~/Workspace/limen)
  LIMEN_WATCHDOG_STALE_SEC  tick staleness ceiling (default = 3 × slowest beat)
  LIMEN_WATCHDOG_MAX_FAILS  consecutive all-failed beats → wedged (default 3)
  LIMEN_WATCHDOG_HEAL    "1" arms --heal restart (and loop-body reload)
  LIMEN_WATCHDOG_RELOAD  "1" arms loop-body reload (default "1"; set "0" to disable)
  LIMEN_WATCHDOG_RELOAD_SETTLE_SEC  loop body must be stable this long before reload (default 120)
  LIMEN_LAUNCHD_LABEL    launchd label (default com.limen.heartbeat)
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# --- DERIVE all locations/thresholds from env; names are outputs ----------------
ROOT = Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen")))
LOGS = ROOT / "logs"
PIDFILE = LOGS / "heartbeat-loop.pid"
BEATLOG = LOGS / "heartbeat.out.log"
ALERT = LOGS / "watchdog-alert.json"
WDLOG = LOGS / "watchdog.log"
LOOPSCRIPT = ROOT / "scripts" / "heartbeat-loop.sh"  # the live loop body the daemon runs
LABEL = os.environ.get("LIMEN_LAUNCHD_LABEL", "com.limen.heartbeat")

# Staleness: derive from the loop's REAL max inter-tick gap, not a magic literal. The daemon
# emits a tick at the END of every beat, so the longest healthy gap between ticks is:
#   idle BACKOFF sleep (≤ LIMEN_LOOP_MAX) + dispatch work + reconcile/web overhead.
# The OLD basis (3 × LOOP_MAX) ignored dispatch duration entirely — it only coincidentally
# absorbed it, which is why a 2026-06-23 ~91min dispatch freeze barely tripped the 5400s ceiling
# (recovered by luck, not the watchdog). Dispatch is now HARD-bounded by the loop's SIGKILL
# ceiling (LIMEN_DISPATCH_CEILING), so we derive a TRUE upper bound from the real components
# ([[logic-over-inherited-config]] — rederive the knob, never inherit the literal).
_MAX_BEAT = int(os.environ.get("LIMEN_LOOP_MAX", "1800") or "1800")
_LANE_TIMEOUT = int(os.environ.get("LIMEN_LANE_TIMEOUT", "1800") or "1800")
# mirror heartbeat-loop.sh's default ceiling (lane cap + slack) so STALE tracks the real bound
_DISPATCH_CEILING = int(os.environ.get("LIMEN_DISPATCH_CEILING", str(_LANE_TIMEOUT + 600))
                        or str(_LANE_TIMEOUT + 600))
_OVERHEAD = int(os.environ.get("LIMEN_WATCHDOG_OVERHEAD_SEC", "600") or "600")
STALE_SEC = int(os.environ.get("LIMEN_WATCHDOG_STALE_SEC",
                               str(_MAX_BEAT + _DISPATCH_CEILING + _OVERHEAD)))
# Wedged: N consecutive most-recent dispatch beats that produced ZERO PRs. A single
# all-no-op beat is normal (queue lull); a run of them = a real wedge (the secrets-bug
# class of failure where every dispatch silently fails). Default 3 = brief's value.
MAX_FAILS = int(os.environ.get("LIMEN_WATCHDOG_MAX_FAILS", "3"))

# Loop-body reload settle window: a loop-body edit must have been stable on disk this long before
# we kickstart to load it. Guards against racing an in-progress sync-release write (and the only
# false-positive vector: a real ff is settled within one window, while a git no-op ff doesn't
# touch mtime at all). DERIVE — small, generous of the ff's fsync, well under a watchdog interval.
RELOAD_SETTLE_SEC = int(os.environ.get("LIMEN_WATCHDOG_RELOAD_SETTLE_SEC", "120") or "120")

# tail bound — read only the log's recent window; the beat log grows unbounded.
TAIL_BYTES = 256 * 1024

TICK_RE = re.compile(r"tick emitted:\s*(\S+)")
# `── PARALLEL done: N ran · M dispatched/PR · ...` — M is the PRs produced that beat.
PARALLEL_RE = re.compile(r"PARALLEL done:.*?·\s*(\d+)\s*dispatched/PR")


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _run(args, timeout=15):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except Exception as e:  # never crash the caller
        return subprocess.CompletedProcess(args, 1, "", str(e))


def _tail(path, nbytes=TAIL_BYTES):
    try:
        sz = path.stat().st_size
        with open(path, "rb") as f:
            if sz > nbytes:
                f.seek(sz - nbytes)
            data = f.read()
        return data.decode("utf-8", "replace")
    except Exception:
        return ""


# --- CHECK 1: daemon up ---------------------------------------------------------
def check_daemon_up():
    pid = None
    try:
        pid = int((PIDFILE.read_text().strip() or "0"))
    except Exception:
        pid = None
    pid_alive = bool(pid) and _run(["ps", "-p", str(pid)]).returncode == 0
    ls = _run(["launchctl", "list"])
    ld_pid = None
    ld_running = False
    for line in ls.stdout.splitlines():
        cols = line.split("\t")
        if len(cols) >= 3 and cols[2].strip() == LABEL:
            raw = cols[0].strip()
            ld_running = raw not in ("-", "")
            ld_pid = raw if ld_running else None
            break
    ok = pid_alive and ld_running
    return ok, {
        "pidfile_pid": pid,
        "pid_alive": pid_alive,
        "launchd_label": LABEL,
        "launchd_running": ld_running,
        "launchd_pid": ld_pid,
    }


# --- CHECK 2: beating recently --------------------------------------------------
def check_beating():
    text = _tail(BEATLOG)
    last = None
    for m in TICK_RE.finditer(text):
        last = m.group(1)
    if last is None:
        return False, {"reason": "no tick line found in recent log window",
                       "stale_sec_threshold": STALE_SEC, "last_tick": None, "age_sec": None}
    try:
        ts = datetime.datetime.fromisoformat(last)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return False, {"reason": f"unparseable tick timestamp {last!r}",
                       "stale_sec_threshold": STALE_SEC, "last_tick": last, "age_sec": None}
    age = (_now() - ts).total_seconds()
    ok = age <= STALE_SEC
    return ok, {"last_tick": last, "age_sec": round(age, 1),
                "stale_sec_threshold": STALE_SEC}


# --- CHECK 3: dispatch not wedged ----------------------------------------------
def check_not_wedged():
    text = _tail(BEATLOG)
    pr_counts = [int(m.group(1)) for m in PARALLEL_RE.finditer(text)]
    if not pr_counts:
        # no dispatch beats in window — can't be wedged on evidence we don't have.
        return True, {"reason": "no PARALLEL beats in window", "recent_pr_counts": [],
                      "max_fails_threshold": MAX_FAILS}
    recent = pr_counts[-MAX_FAILS:]
    # wedged = the last MAX_FAILS beats ALL produced 0 PRs (and we have that many).
    wedged = len(recent) >= MAX_FAILS and all(c == 0 for c in recent)
    return (not wedged), {"recent_pr_counts": recent, "max_fails_threshold": MAX_FAILS,
                          "consecutive_zero": all(c == 0 for c in recent)}


# --- SOFT SIGNAL: is the running daemon on the LATEST loop body? -----------------
def check_loop_body_current():
    """Soft signal (NOT one of the health CHECKS): True when the running daemon's loaded loop
    body matches what's on disk. The daemon writes logs/heartbeat-loop.pid ONCE at startup
    (heartbeat-loop.sh: `echo $$ > ...pid`), so the pidfile's mtime == the daemon's start time;
    heartbeat-loop.sh's mtime is when sync-release last ff'd it. Disk newer than the pidfile ⇒ a
    merged loop-body edit is on disk but DORMANT in the running process (drift). Two mtimes on one
    clock — no ps/date/locale parsing. ok=True on no-pidfile/no-script (nothing actionable here;
    daemon-up owns the missing-daemon case)."""
    try:
        daemon_start = PIDFILE.stat().st_mtime
    except Exception:
        return True, {"reason": "no pidfile (daemon-up owns that)", "drift": False}
    try:
        disk_mtime = LOOPSCRIPT.stat().st_mtime
    except Exception:
        return True, {"reason": "no loop script on disk", "drift": False, "loop_script": str(LOOPSCRIPT)}
    drift = disk_mtime > daemon_start
    return (not drift), {
        "loop_script": str(LOOPSCRIPT),
        "daemon_start_mtime": round(daemon_start, 1),
        "disk_loop_mtime": round(disk_mtime, 1),
        "disk_newer_by_sec": round(disk_mtime - daemon_start, 1),
        "drift": drift,
    }


CHECKS = [
    ("daemon-up", check_daemon_up),
    ("beating", check_beating),
    ("not-wedged", check_not_wedged),
]


def signature(failures):
    """Stable failure-signature for dedupe — WHICH checks failed, not the volatile
    evidence (ages/counts change every beat; we don't want a re-fire each beat)."""
    return "+".join(sorted(name for name, _ in failures)) or "healthy"


def heal():
    """Self-heal: launchctl kickstart the daemon. Double-gated by the caller."""
    uid = os.getuid()
    r = _run(["launchctl", "kickstart", "-k", f"gui/{uid}/{LABEL}"], timeout=30)
    return (r.returncode == 0, (r.stdout + r.stderr).strip())


def _dispatch_running():
    """True if a dispatch subprocess is mid-beat. NEVER kickstart through a live dispatch — it
    would SIGKILL in-flight agents. With the loop's SIGKILL ceiling now bounding every beat, a
    between-beats window always arrives soon, so deferring is safe (we just try again next run)."""
    for pat in ("dispatch-parallel.py", "dispatch-async.py"):
        if _run(["pgrep", "-f", pat], timeout=10).returncode == 0:
            return True
    return False


def _maybe_reload(loop_ev, armed, healed, ts):
    """Quiet loop-body self-deploy: kickstart to load a newer on-disk loop body. NOT a health
    action — it raises no alert and does not touch the failure signature. Gated identically to
    heal() (--heal + LIMEN_WATCHDOG_HEAL=1) plus LIMEN_WATCHDOG_RELOAD, and only fires when the
    edit is SETTLED and we're BETWEEN BEATS. Self-clearing: the kickstart rewrites the pidfile,
    so its mtime jumps past the loop script and drift is gone next run (no thrash)."""
    if healed:
        return False  # heal() already kickstarted → a fresh loop body is loading
    if not loop_ev.get("drift"):
        return False
    if not armed:
        return False
    age = _now().timestamp() - loop_ev["disk_loop_mtime"]
    if age < RELOAD_SETTLE_SEC:
        print(f"[watchdog] loop-body drift but unsettled ({age:.0f}s < {RELOAD_SETTLE_SEC}s) — waiting")
        return False
    if _dispatch_running():
        print("[watchdog] loop-body drift but a dispatch is mid-beat — deferring reload")
        return False
    ok, out = heal()
    _append_log(f"{ts} RELOAD {'ok' if ok else 'FAIL'} "
                f"disk_newer_by={loop_ev.get('disk_newer_by_sec')}s :: {out}")
    print(f"[watchdog] RELOAD: loop-body drift (disk newer than running daemon) → "
          f"kickstart {'ok' if ok else 'FAILED'}: {out}")
    return ok


def _append_log(line):
    try:
        with open(WDLOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description="Limen self-watchdog organ")
    ap.add_argument("--dry-run", action="store_true", help="assess + print, no writes")
    ap.add_argument("--heal", action="store_true",
                    help="allow restart (also needs LIMEN_WATCHDOG_HEAL=1)")
    a = ap.parse_args()

    results = []
    failures = []
    for name, fn in CHECKS:
        ok, ev = fn()
        results.append((name, ok, ev))
        if not ok:
            failures.append((name, ev))

    # soft signal — assessed + printed, but never part of healthy/sig (it's deploy-pending,
    # not unhealthy). Acted on separately, after the alert machine, via _maybe_reload.
    loop_ok, loop_ev = check_loop_body_current()

    ts = _now().isoformat()
    healthy = not failures
    sig = signature(failures)

    print(f"[watchdog] {ts} {'HEALTHY' if healthy else 'UNHEALTHY'} sig={sig}")
    for name, ok, ev in results:
        print(f"  {'ok ' if ok else 'FAIL'} {name}: {json.dumps(ev)}")
    print(f"  {'ok  ' if loop_ok else 'DRIFT'} loop-body: {json.dumps(loop_ev)}")

    if a.dry_run:
        return 0 if healthy else 1

    # loop-body reload is armed by the SAME --heal + LIMEN_WATCHDOG_HEAL gate as heal()
    # (kickstart authority), plus its own LIMEN_WATCHDOG_RELOAD switch (default on).
    reload_armed = (a.heal and os.environ.get("LIMEN_WATCHDOG_HEAL") == "1"
                    and os.environ.get("LIMEN_WATCHDOG_RELOAD", "1") == "1")

    # --- idempotent alert state machine ---------------------------------------
    prior = None
    if ALERT.exists():
        try:
            prior = json.loads(ALERT.read_text())
        except Exception:
            prior = None
    prior_active = bool(prior) and prior.get("active")
    prior_sig = prior.get("signature") if prior else None

    if healthy:
        if prior_active:
            cleared = dict(prior)
            cleared.update({"active": False, "resolved_at": ts})
            try:
                ALERT.write_text(json.dumps(cleared, indent=2))
            except Exception:
                pass
            _append_log(f"{ts} RESOLVED sig={prior_sig}")
            print(f"[watchdog] resolved prior alert sig={prior_sig}")
        # healthy daemon may still be on a STALE loop body (a merged fix not yet loaded) —
        # the common case this organ exists for. Load it between beats.
        _maybe_reload(loop_ev, reload_armed, healed=False, ts=ts)
        return 0

    # unhealthy
    heal_armed = a.heal and os.environ.get("LIMEN_WATCHDOG_HEAL") == "1"
    if prior_active and prior_sig == sig:
        # SAME alert already active → do NOT re-fire (dedupe). Keep it quiet.
        print(f"[watchdog] alert already active sig={sig} — not re-firing")
        _append_log(f"{ts} STILL sig={sig}")
    else:
        record = {
            "active": True,
            "signature": sig,
            "fired_at": ts,
            "failed_checks": [name for name, _ in failures],
            "all_checks": {name: {"ok": ok, "evidence": ev} for name, ok, ev in results},
        }
        try:
            ALERT.write_text(json.dumps(record, indent=2))
        except Exception:
            pass
        _append_log(f"{ts} FIRED sig={sig} checks={','.join(n for n, _ in failures)}")
        print(f"[watchdog] FIRED alert sig={sig}")

    # heal only when armed AND the daemon itself is down/stale.
    healed = False
    if heal_armed and any(n in ("daemon-up", "beating") for n, _ in failures):
        ok, out = heal()
        healed = ok
        _append_log(f"{ts} HEAL {'ok' if ok else 'FAIL'} sig={sig} :: {out}")
        print(f"[watchdog] heal {'ok' if ok else 'FAILED'}: {out}")

    # if we didn't just heal (which already reloads the body), still reconcile loop-body drift.
    _maybe_reload(loop_ev, reload_armed, healed=healed, ts=ts)

    return 1


if __name__ == "__main__":
    sys.exit(main())
