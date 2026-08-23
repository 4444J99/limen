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

Four rungs, each catching one real trap the previous one is structurally blind to:

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

  3. EFFICACY (live-host only; SKIP with no ledger — CI-safe). A rung that is wired AND live
     can still fail on every single beat, and rungs 1-2 are structurally blind to it. Measured
     2026-08-07: ``heal-board.py --canonical`` failed on EVERY beat with
     ``Exceeded allowed rows written in Durable Objects free tier`` while this audit printed
     "3 rung(s) green/skip" and twelve regressed ``needs-human`` atoms stayed regressed. The
     gap was not a flag missing from this file — the audit is registry-derived, and that flag
     WAS declared and WAS on. The gap was a missing axis. Reads the per-rung outcome ledger
     ``logs/beat-rungs.jsonl`` that ``heartbeat-loop.sh``'s ``beat_run`` writes, and goes RED on
     a rung failing N consecutive beats. Catches "enacted but ineffective".

  4. POTENCY (live-host only; SKIP with no ledger — CI-safe). A rung that is wired, live AND
     exiting 0 can still produce no EFFECT, and rungs 1-3 are blind to that too, because a valve
     that succeeds at doing nothing looks identical to one with nothing to do. Measured 2026-08-09
     (#2150): ``self-heal.py``'s retirement pass ran every beat, exited 0 every beat, and retired
     nothing for a day — its enumeration was capped below the live open-PR count, so its truncation
     guard refused to retire from a prefix, correctly and silently. The same run at a sufficient cap
     found 257 retirable tasks. Reads ``logs/valve-effects.jsonl`` (see ``_valve_effects``) and goes
     RED on N consecutive runs where the valve COULD have acted and did not. The candidate count is
     what makes that decidable: "0 effects" is ambiguous, "0 of 257" is not. Catches "effective but
     INERT".

Usage:
  scripts/enactment-audit.py            # human report (all rungs, with live context)
  scripts/enactment-audit.py --check    # gate: exit 1 on any RED rung (SKIP/INFO never fail)
  scripts/enactment-audit.py --heartbeat PATH --params PATH   # override inputs (tests)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import _root  # noqa: E402  — sibling helper, importable only after the sys.path insert above
import _valve_effects  # noqa: E402  — sibling helper; the POTENCY rung's ledger reader

SCRIPT_ROOT = Path(__file__).resolve().parent.parent  # the checkout THIS script lives in
LIVE_ROOT = Path(os.environ.get("LIMEN_ROOT", str(SCRIPT_ROOT)))
ROOT_IS_EXPLICIT = bool(os.environ.get("LIMEN_ROOT"))
HOME = Path(os.path.expanduser("~"))

GREEN, RED, SKIP, INFO = "GREEN", "RED", "SKIP", "INFO"
# sysexits(3). A rung uses this to say "blocked on a condition already filed with a human owner"
# rather than "I am broken" — see efficacy_rung() for why that distinction must not be RED.
EX_TEMPFAIL = 75

# This audit's OWN label in heartbeat-loop.sh's beat_run call. Its exit code is a pure function of
# this report — `--check` exits non-zero whenever ANY rung is RED — so a self-failure carries no
# independent signal about this rung's health. Reporting it RED latches the gate permanently: the
# beat records that exit into logs/beat-rungs.jsonl, which is the very ledger this rung reads, so
# one red beat guarantees the next one, and the audit can never return to green no matter how many
# real defects are repaired. See efficacy_rung(); scripts/tests/enactment-audit.test.sh pins both
# the un-latching and the drift between this constant and the loop's literal.
SELF_RUNG = "enactment-audit-check"


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


def live_checkout() -> Path | None:
    """The checkout the RUNNING daemon was launched from, or None if it cannot be resolved.

    THE DEFECT THIS EXISTS FOR. `heartbeat_pid()` is `pgrep -f heartbeat-loop.sh` — host-GLOBAL, so
    it finds the one real daemon no matter which checkout the audit runs from. The wiring mtime was
    read from `LIVE_ROOT`, which defaults to the checkout this script lives in — per-WORKTREE. Git
    stamps a linked worktree's files at checkout time, which is essentially always AFTER the daemon
    started, so comparing the two fabricated a RED every single time this ran from a worktree.

    Measured 2026-08-07 from a session worktree: `daemon pid 59319 started 11973s ago but its wiring
    changed 984s more recently — running stale env`. The live checkout's copy was stamped 14:42:29,
    the daemon started at 15:20:25, and the two files were byte-identical — the daemon was carrying
    its wiring correctly. 984s is exactly the worktree's checkout time minus the daemon's start.

    A false RED is not the harmless direction of this error. This organ is what `.claude/skills/
    verify` tells a session to run to decide whether a merged loop-body edit is live, and sessions
    work in worktrees by charter — so the reading was wrong precisely in the place it is most used,
    and it says "kickstart the daemon" while handing over no way to tell a real stale daemon from
    the artifact of asking from the wrong tree.

    Explicit `LIMEN_ROOT` is returned untouched: `_root.resolve()` states the rule this follows —
    explicit configuration is never silently overridden. Only the DEFAULTED root gets corrected.
    """
    if ROOT_IS_EXPLICIT:
        return LIVE_ROOT
    if not _root.is_worktree(SCRIPT_ROOT):
        return SCRIPT_ROOT
    # A linked worktree's `.git` file points at `<primary>/.git/worktrees/<name>`; `--git-common-dir`
    # resolves that to `<primary>/.git`, whose parent is the checkout the daemon actually runs from.
    try:
        out = subprocess.run(
            ["git", "-C", str(SCRIPT_ROOT), "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception:
        return None
    if not out:
        return None
    common = Path(out)
    if not common.is_absolute():
        common = SCRIPT_ROOT / common
    primary = common.resolve().parent
    # Never trust the derivation blindly — a bare/relocated git dir has no checkout beside it.
    return primary if (primary / "scripts" / "heartbeat-loop.sh").is_file() else None


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
    # The daemon is host-global (pgrep); its wiring must be read from the checkout it was launched
    # from, never from whichever worktree happens to be asking. See live_checkout() for the false
    # RED this prevents. Unresolvable → SKIP, never RED: a fabricated RED is the defect being
    # removed here, so no path added by this fix may be able to produce one.
    root = live_checkout()
    if root is None:
        return [
            {
                "rung": "liveness",
                "name": "heartbeat-daemon",
                "status": SKIP,
                "detail": (
                    f"heartbeat pid {pid} is running but its checkout could not be resolved from "
                    f"this worktree ({SCRIPT_ROOT}) — set LIMEN_ROOT to the live checkout to audit "
                    f"staleness from here (rung N/A)"
                ),
            }
        ]
    # Only files that ACTUALLY assign a fleet flag are its wiring — a file the beat churns
    # (~/.limen.env, re-hydrated every beat) without setting the flag is not a wiring change.
    wiring_files = [root / "scripts" / "heartbeat-loop.sh", HOME / ".limen.env"]
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
                    "(limen observe --once --scope host)"
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


# --------------------------------------------------------------------------- efficacy
def _rung_outcomes(ledger: Path) -> list[tuple[str, int]]:
    """(rung, exit) in beat order. Malformed lines are skipped, never fatal — this is a sensor."""
    outcomes: list[tuple[str, int]] = []
    try:
        text = ledger.read_text()
    except OSError:
        return outcomes
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            outcomes.append((str(row["rung"]), int(row["exit"])))
        except (ValueError, KeyError, TypeError):
            continue
    return outcomes


def failing_streaks(outcomes: list[tuple[str, int]]) -> dict[str, tuple[int, int]]:
    """Per rung, its TRAILING run of consecutive non-zero exits: {rung: (streak, last_exit)}.

    Trailing, not total: a rung that failed twice last week and has succeeded since is healthy, and
    counting its history would make the rung permanently red and therefore ignored. Only rungs with
    a live streak appear.
    """
    latest: dict[str, list[int]] = {}
    for rung, code in outcomes:
        latest.setdefault(rung, []).append(code)
    streaks: dict[str, tuple[int, int]] = {}
    for rung, codes in latest.items():
        streak = 0
        for code in reversed(codes):
            if code == 0:
                break
            streak += 1
        if streak:
            streaks[rung] = (streak, codes[-1])
    return streaks


def efficacy_rung() -> list[dict]:
    """RED when a beat rung has FAILED on N consecutive beats — the axis the other two cannot see.

    Wiring proves a flag is set. Liveness proves the running daemon is not older than its wiring.
    Neither can see a rung that is wired, live, and fails on every single beat — and that is not a
    hypothetical. Measured 2026-08-07: ``heal-board.py --canonical`` (#2014) failed on EVERY beat
    with ``conduct broker rejected request (500): Exceeded allowed rows written in Durable Objects
    free tier`` while this audit printed "3 rung(s) green/skip". Twelve regressed ``needs-human``
    atoms stayed regressed for hours behind a fully-enacted, completely ineffective rung.

    The reason it was invisible was not a missing flag in this file — this audit is registry-derived,
    so a flag only gets a row by declaring ``fleet_runtime``. It was a missing AXIS. Adding
    ``LIMEN_BOARD_CANONICAL_HEAL`` to a list would have proven the switch was on, which it was.

    ``heartbeat-loop.sh``'s ``beat_run`` helper now records ``{ts,rung,exit}`` per rung per beat to
    ``logs/beat-rungs.jsonl``; this rung is that ledger's reader — the effector the old
    ``2>&1 | tail -1`` idiom denied it by destroying the exit status before anything could record it.

    ``EX_TEMPFAIL`` (75) is reported but NOT red, deliberately. It is the code a rung uses to say
    "blocked on a condition already filed with a human owner" (``heal-board --canonical`` raises it
    for the keeper's spent storage plan, citing lever ``L-CLOUDFLARE-DO-QUOTA``). Making a correctly
    homed, human-gated blocker permanently RED would hold this gate red until the operator acts,
    which trains everyone to ignore it — the precise failure the loop's own comments warn about, and
    a violation of the charter's "never re-surface a filed gate". So it is visible and named, but it
    does not fail the audit; a rung failing for any OTHER reason does.

    SKIP when the ledger is absent (CI, or a daemon that has not yet run a loop carrying beat_run).
    """
    # Resolve the ledger against the checkout the DAEMON runs from, not the one this script lives
    # in. #2053 fixed exactly this asymmetry for the liveness rung — a host-global daemon compared
    # against a per-worktree path — and the efficacy rung would reintroduce it verbatim: run from a
    # session worktree, LIVE_ROOT is that worktree, its logs/ has no ledger, and the rung SKIPs while
    # the real one sits in the live checkout. A silent SKIP where the evidence exists is the same
    # "I found nothing" / "I read nothing" confusion this whole lineage is about.
    override = os.environ.get("LIMEN_BEAT_RUNG_LOG")
    if override:
        ledger = Path(override)
    else:
        root = live_checkout() or LIVE_ROOT
        ledger = root / "logs" / "beat-rungs.jsonl"
    if not ledger.is_file():
        return [
            {
                "rung": "efficacy",
                "name": "beat-rungs",
                "status": SKIP,
                "detail": f"no rung-outcome ledger at {ledger} — not on a live host running beat_run (rung N/A)",
            }
        ]
    outcomes = _rung_outcomes(ledger)
    if not outcomes:
        return [
            {
                "rung": "efficacy",
                "name": "beat-rungs",
                "status": SKIP,
                "detail": f"rung-outcome ledger at {ledger} holds no readable records yet (rung N/A)",
            }
        ]
    try:
        threshold = int(os.environ.get("LIMEN_RUNG_FAIL_STREAK_RED", "3"))
    except ValueError:
        threshold = 3
    threshold = max(1, threshold)

    streaks = failing_streaks(outcomes)
    rows: list[dict] = []
    for rung, (streak, last_exit) in sorted(streaks.items(), key=lambda kv: (-kv[1][0], kv[0])):
        if rung == SELF_RUNG:
            # DERIVED, never an independent defect — see SELF_RUNG. Reported for the same reason
            # EX_TEMPFAIL is: visible and named, but it does not fail the audit, because a
            # permanently-red gate is an ignored gate. Repair the reds below and this clears itself
            # on the next beat that records a zero.
            rows.append(
                {
                    "rung": "efficacy",
                    "name": rung,
                    "status": INFO,
                    "detail": (
                        f"failing {streak} consecutive beat(s) (last exit {last_exit}) — this "
                        f"audit's OWN rung. `--check` exits non-zero whenever any rung is RED and "
                        f"the beat writes that exit to the ledger this rung reads, so a self-streak "
                        f"is derived from the other findings, not evidence of a defect here. It "
                        f"clears when they do."
                    ),
                }
            )
            continue
        if last_exit == EX_TEMPFAIL:
            rows.append(
                {
                    "rung": "efficacy",
                    "name": rung,
                    "status": INFO,
                    "detail": (
                        f"failing {streak} beat(s) running with exit {EX_TEMPFAIL} (EX_TEMPFAIL) — a "
                        f"blocker already filed with a human owner, not a fleet defect. Left non-red "
                        f"on purpose: a permanently-red gate is an ignored gate."
                    ),
                }
            )
        elif streak >= threshold:
            rows.append(
                {
                    "rung": "efficacy",
                    "name": rung,
                    "status": RED,
                    "detail": (
                        f"enacted but INEFFECTIVE — failed {streak} consecutive beats (last exit "
                        f"{last_exit}). The switch is on and the daemon is current; the rung itself "
                        f"is not landing. Read its `── RUNG FAIL [{rung}] ──` block in the beat log."
                    ),
                }
            )
        else:
            rows.append(
                {
                    "rung": "efficacy",
                    "name": rung,
                    "status": INFO,
                    "detail": (
                        f"failed the last {streak} beat(s) (exit {last_exit}) — under the "
                        f"{threshold}-beat threshold; a single bad beat is noise, not a defect"
                    ),
                }
            )
    if not rows:
        distinct = len({rung for rung, _ in outcomes})
        rows.append(
            {
                "rung": "efficacy",
                "name": "beat-rungs",
                "status": GREEN,
                "detail": (
                    f"every one of {distinct} rung(s) succeeded on its most recent beat "
                    f"({len(outcomes)} outcome(s) on record)"
                ),
            }
        )
    return rows


# --------------------------------------------------------------------------- potency
def potency_rung() -> list[dict]:
    """RED when a DESTRUCTIVE valve has been able to act and has not, N runs running.

    The axis the other three cannot see, and the progression is exact:

      WIRING   proves the flag resolves ON.
      LIVENESS proves the daemon post-dates its wiring.
      EFFICACY proves the rung is not exiting NON-ZERO.
      POTENCY  proves a zero exit came with an EFFECT.

    A valve that succeeds at doing nothing passes the first three. Measured 2026-08-09 (#2150):
    self-heal.py's retirement pass was wired, live, and exited 0 on every beat for a day while
    retiring nothing — its enumeration was capped below the live open-PR count, so the truncation
    guard refused to retire from a prefix. Correctly. Silently. The same run at a sufficient cap
    reported 257 retirable tasks.

    Why a naive "effects == 0" alarm would be worse than nothing: a healthy valve on a drained
    backlog also reports zero, forever. An alarm that cannot tell those apart gets muted, and takes
    the real signal with it. The separator is the DENOMINATOR — ``_valve_effects`` requires every
    valve to report the candidates it evaluated, computed independently of whether it was
    authorized to act, so "0 of 0" (healthy idle) and "0 of 257" (dead) stop looking alike.

    SKIP when no ledger exists (CI, or no valve has run yet) — never a silent GREEN, because
    "I read nothing" and "nothing is wrong" must not print the same thing.
    """
    override = os.environ.get("LIMEN_VALVE_EFFECT_LOG")
    if override:
        ledger = Path(override)
    else:
        # Same daemon-root resolution as the efficacy rung, for the same #2053 reason: run from a
        # session worktree, the writer and reader would sit in different logs/ directories and the
        # rung would SKIP while the real evidence exists one directory over.
        root = live_checkout() or LIVE_ROOT
        ledger = root / "logs" / _valve_effects.LEDGER_NAME
    if not ledger.is_file():
        return [
            {
                "rung": "potency",
                "name": "valve-effects",
                "status": SKIP,
                "detail": f"no valve-effect ledger at {ledger} — no destructive valve has recorded a run (rung N/A)",
            }
        ]
    rows_in = _valve_effects.read_rows(ledger)
    if not rows_in:
        return [
            {
                "rung": "potency",
                "name": "valve-effects",
                "status": SKIP,
                "detail": f"valve-effect ledger at {ledger} holds no readable records yet (rung N/A)",
            }
        ]
    try:
        threshold = int(os.environ.get("LIMEN_VALVE_IDLE_STREAK_RED", "3"))
    except ValueError:
        threshold = 3
    threshold = max(1, threshold)

    streaks = _valve_effects.idle_streaks(rows_in)
    rows: list[dict] = []
    for valve, info in sorted(streaks.items(), key=lambda kv: (-kv[1]["streak"], kv[0])):
        streak, why = info["streak"], info["why"]
        if streak >= threshold:
            rows.append(
                {
                    "rung": "potency",
                    "name": valve,
                    "status": RED,
                    "detail": (
                        f"armed but INERT — {streak} consecutive run(s) with no effect: {why}. "
                        f"The valve is wired, live and exiting 0; it is simply not firing. A dead "
                        f"valve and a healthy idle one emit the same quiet beat, which is why this "
                        f"reads the candidate count rather than the effect count alone."
                    ),
                }
            )
        else:
            rows.append(
                {
                    "rung": "potency",
                    "name": valve,
                    "status": INFO,
                    "detail": (
                        f"no effect on the last {streak} run(s) — {why}; under the {threshold}-run "
                        f"threshold, so still noise rather than a dead valve"
                    ),
                }
            )
    if not rows:
        valves = sorted({str(r.get("valve")) for r in rows_in})
        rows.append(
            {
                "rung": "potency",
                "name": "valve-effects",
                "status": GREEN,
                "detail": (
                    f"every one of {len(valves)} destructive valve(s) either acted or had nothing to "
                    f"act on, on its most recent run ({len(rows_in)} record(s)): {', '.join(valves)}"
                ),
            }
        )
    return rows


# ------------------------------------------------------------------------------ main
def run(
    heartbeat: Path,
    params_path: Path,
    *,
    wiring_only: bool = False,
    efficacy_only: bool = False,
    potency_only: bool = False,
) -> list[dict]:
    if potency_only:
        return potency_rung()
    if efficacy_only:
        # One axis at a time, so a test can drive it against a fixture ledger without the
        # host-dependent liveness rung flapping the result between CI and the live host.
        return efficacy_rung()
    params = yaml.safe_load(params_path.read_text()) or {}
    live = LIVE_ROOT == SCRIPT_ROOT or (LIVE_ROOT / "scripts" / "heartbeat-loop.sh").exists()
    rows = wiring_rung(params, heartbeat, live=live)
    if not wiring_only:  # liveness/efficacy/potency read live host state; tests pin the code contract only
        rows += liveness_rung(params)
        rows += efficacy_rung()
        rows += potency_rung()
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Prove declared-ON fleet flags are actually enacted.")
    ap.add_argument("--check", action="store_true", help="gate mode: exit 1 on any RED rung")
    ap.add_argument(
        "--wiring-only",
        action="store_true",
        help="skip the live-host liveness + efficacy rungs (deterministic code-contract check for tests)",
    )
    ap.add_argument(
        "--efficacy-only",
        action="store_true",
        help="run ONLY the rung-outcome efficacy rung (point LIMEN_BEAT_RUNG_LOG at a fixture ledger)",
    )
    ap.add_argument(
        "--potency-only",
        action="store_true",
        help="run ONLY the valve-effect potency rung (point LIMEN_VALVE_EFFECT_LOG at a fixture ledger)",
    )
    ap.add_argument("--heartbeat", default=str(SCRIPT_ROOT / "scripts" / "heartbeat-loop.sh"))
    ap.add_argument("--params", default=str(SCRIPT_ROOT / "institutio" / "governance" / "parameters.yaml"))
    args = ap.parse_args(argv)

    rows = run(
        Path(args.heartbeat),
        Path(args.params),
        wiring_only=args.wiring_only,
        efficacy_only=args.efficacy_only,
        potency_only=args.potency_only,
    )
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
