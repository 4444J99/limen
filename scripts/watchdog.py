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

On any failure: write ONE alert to logs/watchdog-alert.json (ts, failed check,
evidence) + append a line to logs/watchdog.log. Idempotent: same signature already
active → no re-fire; health returns → clear the alert. Self-heal (launchctl kickstart)
is gated behind --heal AND LIMEN_WATCHDOG_HEAL=1.

  --dry-run   assess + print, NO writes
  --heal      allow restart (also needs LIMEN_WATCHDOG_HEAL=1)
  (default)   assess + write alert/log, no restart

Env-parameterized (DERIVE, never hardcode):
  LIMEN_ROOT             conductor root (default ~/Workspace/limen)
  LIMEN_WATCHDOG_STALE_SEC  tick staleness ceiling (default = 3 × slowest beat)
  LIMEN_WATCHDOG_MAX_FAILS  consecutive all-failed beats → wedged (default 3)
  LIMEN_WATCHDOG_HEAL    "1" arms --heal restart
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

    ts = _now().isoformat()
    healthy = not failures
    sig = signature(failures)

    print(f"[watchdog] {ts} {'HEALTHY' if healthy else 'UNHEALTHY'} sig={sig}")
    for name, ok, ev in results:
        print(f"  {'ok ' if ok else 'FAIL'} {name}: {json.dumps(ev)}")

    if a.dry_run:
        return 0 if healthy else 1

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
    if heal_armed and any(n in ("daemon-up", "beating") for n, _ in failures):
        ok, out = heal()
        _append_log(f"{ts} HEAL {'ok' if ok else 'FAIL'} sig={sig} :: {out}")
        print(f"[watchdog] heal {'ok' if ok else 'FAILED'}: {out}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
