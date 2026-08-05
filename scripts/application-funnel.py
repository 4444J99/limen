#!/usr/bin/env python3
"""Beat driver: mount the application-pipeline outbound job funnel onto the limen beat.

The ``application-pipeline`` repo ships a complete, mature outbound funnel
(``daily_pipeline_orchestrator.py``: Scan -> Match -> Build -> Apply -> Outreach),
but nothing schedules it — the loop is dormant, run only by hand. This thin driver
— the outbound sibling of ``opportunity-review-delta.py``'s
``_sync_opportunity_pipeline()`` (inbound) — runs it on the beat, REVERSIBLY by default:

  * Always (disarmed): ``scan -> match -> build -> outreach``, executed with ``--yes``.
    These SOURCE roles from ATS/public APIs, SCORE them (>=9.0 precision threshold),
    BUILD tailored materials, STAGE complete application packages, and PREPARE
    follow-up dates. Nothing leaves the machine: no application is submitted and no
    email/DM is sent — the ``outreach`` phase only prepares dates/templates
    (``prepare_outreach`` is verified send-free). Reversible, egg-proof.

  * ``apply`` — the ONLY outbound phase (submits staged applications to ATS portals) —
    runs ONLY when ``LIMEN_APPLY_FIRE=1``, exactly as ``send_drafts.py``'s SAFE
    auto-send is gated behind ``LIMEN_MAIL_SEND=1``. Submits stay capped by the
    engine's own precision limits (<=3 confirmed/local-day, score >=9.0,
    one role per organization, live posting, evidence map, and no active hold).

No follow-up *sender* is beat-wired here, so the ``warm-lead-leverage-never-chase``
rule cannot be violated by this driver: the only outbound the arm enables is applying
to NEW postings (categorically distinct from chasing a warm inbound recruiter, which
stays owned by ``correspondence-walk.py``).

Writing ``LIMEN_APPLY_FIRE=1`` is the operator's one-time paste (persistence-arming is
classifier-gated); until then the beat stages and he glances. Filed as lever
``L-APPLY-FIRE`` in ``his-hand-levers.json``.

Fail-open at every step (absent pipeline / error -> PII-clean note, exit 0); the beat
sensor runs it ``silent`` so a network hiccup can never red the beat.

Usage:
    python3 scripts/application-funnel.py           # reversible cycle (+ apply iff armed)
    python3 scripts/application-funnel.py --json     # machine-readable summary
    python3 scripts/application-funnel.py --notify    # also emit a one-line notify
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()

# Candidate checkout locations, in priority order. A single hardcoded default made this
# driver fail SILENTLY on 2026-08-03: the clone lives at ~/Workspace/4444J99/application-pipeline
# (owner-namespaced, the estate's normal layout) while the default pointed one directory up.
# _find_orchestrator() returned None, run() took its fail-open path, and the beat reported a
# clean note every cycle while the funnel had never once executed. Fail-open is right for a
# network hiccup and wrong for a permanently wrong path — so resolution is now a SEARCH, and
# run() distinguishes "no checkout anywhere" from "checkout present but cycle failed".
PIPELINE_CANDIDATES = (
    HOME / "Workspace" / "application-pipeline",
    HOME / "Workspace" / "4444J99" / "application-pipeline",
    HOME / "Workspace" / "organvm" / "application-pipeline",
    HOME / "application-pipeline",
)


def _resolve_pipeline() -> Path:
    """First candidate that actually carries the orchestrator; else the declared default.

    An explicit APPLICATION_PIPELINE always wins, even if it does not exist — an operator
    pointing somewhere deliberately gets a loud failure there, not a silent relocation.
    """
    override = os.environ.get("APPLICATION_PIPELINE")
    if override:
        return Path(override).expanduser()
    for candidate in PIPELINE_CANDIDATES:
        for sub in ("scripts", "tools"):
            if (candidate / sub / "daily_pipeline_orchestrator.py").exists():
                return candidate
    return PIPELINE_CANDIDATES[0]


APPLICATION_PIPELINE = _resolve_pipeline()

# The reversible phases: they source/score/build/stage + prepare follow-up dates, but
# NEVER submit or send. `apply` is deliberately excluded here and gated behind the arm.
REVERSIBLE_PHASES = ["scan", "match", "build", "outreach"]

# A full cycle is a multi-minute job (match alone re-scores the whole pipeline), so the beat
# normally triggers it detached and returns. The daily coordinator uses ``wait=True`` so its
# persisted run owns the exact current result instead of reading stale detached output.
STATE_DIR = Path(os.environ.get("LIMEN_APPLICATION_STATE_DIR", HOME / "System" / "Logs"))
LOCK = STATE_DIR / "funnel.lock"
LOG = STATE_DIR / "funnel-cycle.log"
RESULT = STATE_DIR / "funnel-last-result.json"
MAX_RUNTIME = int(os.environ.get("LIMEN_APPLICATION_CYCLE_MAX_SECONDS", "1800"))


def _pipeline_python() -> tuple[str, bool]:
    """Resolve the interpreter that has the pipeline's deps (ruamel, anthropic, ...).

    Priority: LIMEN_APPLICATION_PIPELINE_PYTHON override -> the pipeline's own .venv ->
    sys.executable. Returns (path, is_venv). The beat's own python does NOT carry the
    pipeline's deps, so falling back to it means the orchestrator will fail its imports —
    the driver reports that loudly rather than pretending the funnel ran."""
    override = os.environ.get("LIMEN_APPLICATION_PIPELINE_PYTHON")
    if override and Path(override).exists():
        return override, True
    venv = APPLICATION_PIPELINE / ".venv" / "bin" / "python"
    if venv.exists():
        return str(venv), True
    return sys.executable, False


def _find_orchestrator() -> Path | None:
    """Locate daily_pipeline_orchestrator.py in the pipeline checkout (scripts/ or tools/)."""
    if not APPLICATION_PIPELINE.exists():
        return None
    for sub in ("scripts", "tools"):
        candidate = APPLICATION_PIPELINE / sub / "daily_pipeline_orchestrator.py"
        if candidate.exists():
            return candidate
    return None


def _pid_alive(pid: int) -> bool:
    """True if the pid is running. PermissionError ⇒ alive but not ours (still alive)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _lock_state() -> tuple[str, int | None, int | None]:
    """('running', pid, age_s) if a fresh cycle holds the lock, else ('free', None, None).

    A stale lock (dead pid, or older than MAX_RUNTIME) is stolen so a crashed cycle can
    never wedge the funnel shut."""
    if not LOCK.exists():
        return "free", None, None
    try:
        pid = int(LOCK.read_text().split()[0])
        age = int(time.time() - LOCK.stat().st_mtime)
    except (ValueError, OSError, IndexError):
        return "free", None, None
    if _pid_alive(pid) and age < MAX_RUNTIME:
        return "running", pid, age
    try:
        LOCK.unlink()
    except OSError:
        pass
    return "free", None, None


def _launch(orchestrator: Path, py: str, phases: list[str]) -> None:
    """Fire the cycle DETACHED and return immediately. The child writes its own pid to the
    lock, runs the orchestrator to a temp result (atomically promoted on success so a failed
    run preserves the last good counts), appends stderr to the log, and always clears the lock."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    phase_args = " ".join(f"--phase {p}" for p in phases)
    inner = (
        f'echo $$ > "{LOCK}"; '
        f'cd "{APPLICATION_PIPELINE}" && "{py}" "{orchestrator}" --yes --json {phase_args} '
        f'> "{RESULT}.tmp" 2>> "{LOG}" && mv "{RESULT}.tmp" "{RESULT}"; '
        f'rm -f "{LOCK}"'
    )
    subprocess.Popen(  # noqa: S603 — detached beat-owned cycle, single-instance via lock
        ["/bin/sh", "-c", inner],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _last_result() -> tuple[dict | None, str | None]:
    """Return ``(result, defect)`` for the last completed cycle.

    Collapsing "no file" and "unreadable file" into a bare ``None`` made a CORRUPT
    result indistinguishable from a cycle that has simply never run: both produced an
    all-zero summary and the reassuring note "no completed cycle yet". On 2026-08-05
    ``funnel-last-result.json`` held the literal five-byte string ``test``; every
    subsequent read reported zero sourced, zero staged, zero submitted, and nothing
    anywhere said the state file was garbage.

    A silent zero is the worst possible reading of a broken sensor, because it is
    indistinguishable from a true zero. Absence stays quiet; corruption is named.
    """
    try:
        raw = RESULT.read_text()
    except OSError:
        return None, None  # genuinely absent — the pre-first-cycle state, not a defect
    try:
        value = json.loads(raw)
    except ValueError:
        return None, f"last-cycle result is unreadable ({RESULT.name}) — counts below are NOT a true zero"
    if not isinstance(value, dict):
        return None, f"last-cycle result is not an object ({RESULT.name}) — counts below are NOT a true zero"
    return value, None


def _summary(
    last: dict | None,
    armed: bool,
    launched: bool,
    notes: list[str],
    *,
    cycle_completed: bool = False,
) -> dict:
    """PII-clean count summary from the LAST completed cycle — no titles, orgs, or contacts."""
    s: dict = {
        "sourced": 0,
        "qualified": 0,
        "staged": 0,
        "submitted": 0,
        "attempted": 0,
        "confirmed": 0,
        "ambiguous": 0,
        "blocked": 0,
        "superseded": 0,
        "retry_locked": False,
        "armed": armed,
        "launched": launched,
        "cycle_completed": cycle_completed,
    }
    if last:
        scan = last.get("scan") or {}
        match = last.get("match") or {}
        adv = last.get("auto_advance") or {}
        ap = last.get("apply") or {}
        s["sourced"] = int(scan.get("total_fetched", 0) or 0)
        s["qualified"] = len(match.get("qualified", []) or [])
        s["staged"] = len([a for a in (adv.get("advanced") or []) if a.get("to") == "staged"])
        s["submitted"] = len(ap.get("submitted", []) or [])
        s["attempted"] = len(ap.get("attempted", []) or []) or s["submitted"]
        s["confirmed"] = len(ap.get("confirmed", []) or [])
        s["ambiguous"] = len(ap.get("ambiguous", []) or [])
        s["blocked"] = len(ap.get("blocked", []) or [])
        s["superseded"] = len(ap.get("superseded", []) or [])
        s["retry_locked"] = bool(ap.get("retry_locked", False))
    s["notes"] = notes
    return s


def _parse_json(stdout: str) -> dict | None:
    try:
        value = json.loads(stdout)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    # Extract JSON object bounded by outermost '{' and '}'
    start = stdout.find("{")
    end = stdout.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            value = json.loads(stdout[start : end + 1])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass

    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    return None


def _run_waiting(orchestrator: Path, py: str, phases: list[str]) -> tuple[dict | None, str | None]:
    """Run one owner cycle synchronously for the daily coordinator."""

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        lock_tmp = LOCK.with_name(f".{LOCK.name}.{os.getpid()}.tmp")
        lock_tmp.write_text(str(os.getpid()), encoding="utf-8")
        lock_tmp.replace(LOCK)
        phase_args = [arg for phase in phases for arg in ("--phase", phase)]
        completed = subprocess.run(
            [py, str(orchestrator), "--yes", "--json", *phase_args],
            cwd=str(APPLICATION_PIPELINE),
            capture_output=True,
            text=True,
            timeout=MAX_RUNTIME,
            check=False,
        )
        parsed = _parse_json(completed.stdout or "")
        if completed.returncode != 0:
            return parsed, f"application owner cycle failed (exit {completed.returncode})"
        if parsed is None:
            return None, "application owner cycle returned no structured result"
        temporary = RESULT.with_name(f".{RESULT.name}.tmp")
        temporary.write_text(json.dumps(parsed, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(RESULT)
        return parsed, None
    except subprocess.TimeoutExpired:
        return None, "application owner cycle timed out"
    except OSError:
        return None, "application owner cycle unavailable"
    finally:
        try:
            LOCK.unlink()
        except OSError:
            pass


def run(*, wait: bool = False) -> dict:
    notes: list[str] = []
    orchestrator = _find_orchestrator()
    if orchestrator is None:
        if not APPLICATION_PIPELINE.exists():
            notes.append("application-pipeline absent — funnel idle (fail-open)")
        else:
            notes.append("daily_pipeline_orchestrator.py not found (scripts/ or tools/) — funnel idle")
        return _summary(None, False, False, notes, cycle_completed=False)

    # A real effector needs the pipeline's own deps. Without its .venv the orchestrator would
    # crash on imports every cycle; surface that LOUDLY + actionably instead of fail-open into
    # a silent forever-green no-op (the sensor-without-effector defect).
    py, is_venv = _pipeline_python()
    if not is_venv:
        notes.append(
            f"pipeline .venv missing — funnel idle. Bootstrap: cd {APPLICATION_PIPELINE} "
            "&& python3 -m venv .venv && .venv/bin/pip install -e . "
            "(or set LIMEN_APPLICATION_PIPELINE_PYTHON)"
        )
        stale, stale_defect = _last_result()
        if stale_defect:
            notes.append(stale_defect)
        return _summary(stale, False, False, notes, cycle_completed=False)

    armed = os.environ.get("LIMEN_APPLY_FIRE") == "1"
    last, last_defect = _last_result()
    if last_defect:
        notes.append(last_defect)
    state, pid, age = _lock_state()
    if state == "running":
        notes.append(f"cycle already running (pid {pid}, {age}s) — not relaunched")
        return _summary(last, armed, False, notes, cycle_completed=False)

    phases = REVERSIBLE_PHASES + (["apply"] if armed else [])
    if wait:
        completed, error = _run_waiting(orchestrator, py, phases)
        if error:
            notes.append(error)
            return _summary(completed or last, armed, True, notes, cycle_completed=False)
        notes.append("cycle completed synchronously for the daily coordinator")
        if armed:
            notes.append("apply ARMED (LIMEN_APPLY_FIRE=1) — provider receipts required")
        else:
            notes.append("apply disarmed — staged only, nothing submitted")
        return _summary(completed, armed, True, notes, cycle_completed=True)
    _launch(orchestrator, py, phases)
    notes.append("cycle launched (detached): " + " ".join(phases))
    if armed:
        notes.append(
            "apply ARMED (LIMEN_APPLY_FIRE=1) — submits staged apps only when they meet "
            "the 3-confirmed/local-day policy"
        )
    else:
        notes.append("apply disarmed — staged only, nothing submitted; arm via lever L-APPLY-FIRE")
    if last is None and not last_defect:
        notes.append("no completed cycle yet — counts populate after the first cycle finishes")
    return _summary(last, armed, True, notes, cycle_completed=False)


def main() -> int:
    ap = argparse.ArgumentParser(description="Beat driver for the application-pipeline outbound funnel")
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    ap.add_argument("--notify", action="store_true", help="emit a one-line notify to stdout")
    ap.add_argument("--wait", action="store_true", help="wait for the owner cycle and return its current result")
    args = ap.parse_args()

    summary = run(wait=args.wait)

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        armed = "ARMED" if summary["armed"] else "staged-only"
        launched = "launched" if summary["launched"] else "not launched"
        print(
            f"[funnel] cycle {launched} ({armed}) · last: sourced {summary['sourced']} · "
            f"qualified {summary['qualified']} · staged {summary['staged']} · submitted {summary['submitted']}"
        )
        for n in summary.get("notes", []):
            print(f"  - {n}")
    if args.notify:
        print(
            f"FUNNEL: cycle {'launched' if summary['launched'] else 'held'} "
            f"({'armed' if summary['armed'] else 'staged-only'}); last +{summary['staged']} staged, "
            f"{summary['submitted']} submitted"
        )
    return 0  # fail-open: the beat must never red on this


if __name__ == "__main__":
    sys.exit(main())
