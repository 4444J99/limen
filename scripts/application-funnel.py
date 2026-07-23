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
    engine's own precision limits (<=2/week, 1/org, <=10 active).

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
APPLICATION_PIPELINE = Path(os.environ.get("APPLICATION_PIPELINE", HOME / "Workspace" / "application-pipeline"))

# The reversible phases: they source/score/build/stage + prepare follow-up dates, but
# NEVER submit or send. `apply` is deliberately excluded here and gated behind the arm.
REVERSIBLE_PHASES = ["scan", "match", "build", "outreach"]

# A full cycle is a multi-minute job (match alone re-scores the whole pipeline), so the beat
# must TRIGGER it detached and return, never block on it. One instance at a time (lock); the
# next beat reports the last completed cycle's counts from the result file.
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
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _last_result() -> dict | None:
    try:
        return json.loads(RESULT.read_text())
    except (OSError, ValueError):
        return None


def _summary(last: dict | None, armed: bool, launched: bool, notes: list[str]) -> dict:
    """PII-clean count summary from the LAST completed cycle — no titles, orgs, or contacts."""
    s: dict = {"sourced": 0, "qualified": 0, "staged": 0, "submitted": 0, "armed": armed, "launched": launched}
    if last:
        scan = last.get("scan") or {}
        match = last.get("match") or {}
        adv = last.get("auto_advance") or {}
        ap = last.get("apply") or {}
        s["sourced"] = int(scan.get("total_fetched", 0) or 0)
        s["qualified"] = len(match.get("qualified", []) or [])
        s["staged"] = len([a for a in (adv.get("advanced") or []) if a.get("to") == "staged"])
        s["submitted"] = len(ap.get("submitted", []) or [])
    s["notes"] = notes
    return s


def run() -> dict:
    notes: list[str] = []
    orchestrator = _find_orchestrator()
    if orchestrator is None:
        if not APPLICATION_PIPELINE.exists():
            notes.append("application-pipeline absent — funnel idle (fail-open)")
        else:
            notes.append("daily_pipeline_orchestrator.py not found (scripts/ or tools/) — funnel idle")
        return _summary(None, False, False, notes)

    # A real effector needs the pipeline's own deps. Without its .venv the orchestrator would
    # crash on imports every cycle; surface that LOUDLY + actionably instead of fail-open into
    # a silent forever-green no-op (the sensor-without-effector defect).
    py, is_venv = _pipeline_python()
    if not is_venv:
        notes.append(
            "pipeline .venv missing — funnel idle. Bootstrap: "
            "cd ~/Workspace/application-pipeline && python3 -m venv .venv && "
            ".venv/bin/pip install -e . (or set LIMEN_APPLICATION_PIPELINE_PYTHON)"
        )
        return _summary(_last_result(), False, False, notes)

    armed = os.environ.get("LIMEN_APPLY_FIRE") == "1"
    last = _last_result()
    state, pid, age = _lock_state()
    if state == "running":
        notes.append(f"cycle already running (pid {pid}, {age}s) — not relaunched")
        return _summary(last, armed, False, notes)

    phases = REVERSIBLE_PHASES + (["apply"] if armed else [])
    _launch(orchestrator, py, phases)
    notes.append("cycle launched (detached): " + " ".join(phases))
    if armed:
        notes.append("apply ARMED (LIMEN_APPLY_FIRE=1) — submits staged apps, capped by engine precision (2/wk, 1/org)")
    else:
        notes.append("apply disarmed — staged only, nothing submitted; arm via lever L-APPLY-FIRE")
    if last is None:
        notes.append("no completed cycle yet — counts populate after the first cycle finishes")
    return _summary(last, armed, True, notes)


def main() -> int:
    ap = argparse.ArgumentParser(description="Beat driver for the application-pipeline outbound funnel")
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    ap.add_argument("--notify", action="store_true", help="emit a one-line notify to stdout")
    args = ap.parse_args()

    summary = run()

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
