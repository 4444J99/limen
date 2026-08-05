"""The internal-legibility face — reconcile our own public claims to their source.

OBSERVATORY's micro face asks: *are our own public numbers true and coherent?* The
sensor and diff for that already exist — **VVLTVS** (``scripts/vvltvs-organ.py``) reads
the ``face-ownership.json`` constitution, computes each register pipe's health
(live / severed / stale) and each face's value-vs-source drift, and prints a
remediation plan. The one thing missing was an *effector*: something that acts on that
plan inside OBSERVATORY's loop.

This module is that effector — and, following GITVS's "~90% orchestration, never
re-implement a mutation" doctrine, it **delegates to VVLTVS** rather than re-deriving
drift (re-deriving it here would be the very "fourth stamper" the constitution forbids).
It:

  1. runs ``vvltvs --json`` to get the structured assessment,
  2. converts drifted faces + severed pipes into internal-legibility **gaps**,
  3. captures ``vvltvs --apply`` (the read-only remediation plan) as the proposal text,
  4. writes it to the evidence ledger + a regenerated latest doc, and returns a summary
     the daily brief folds in.

It never writes a public surface. The remediation (revive a severed CI pipe, make a face
project from its register) is emitted as a **human-gated proposal**; opening the actual
cross-repo PR is the armed extension, not v1. ``check()`` delegates to ``vvltvs --check``.
Everything is fail-open: if VVLTVS is absent or errors, the face degrades to
``sensor_unavailable`` (advisory), never a crash.
"""

from __future__ import annotations

import json
import os
import subprocess

from . import config, ledger


def _vvltvs_path():
    return config.repo_root() / "scripts" / "vvltvs-organ.py"


def _run_vvltvs(flags: list[str], timeout: int = 90) -> subprocess.CompletedProcess:
    """Invoke the VVLTVS sensor. Fail-open: returncode 1 + reason, never raises."""
    script = _vvltvs_path()
    if not script.exists():
        return subprocess.CompletedProcess(flags, 1, "", "vvltvs absent")
    try:
        return subprocess.run(
            ["python3", str(script), *flags],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ},
        )
    except Exception as e:  # fail open
        return subprocess.CompletedProcess(flags, 1, "", str(e))


def assess() -> dict | None:
    """The structured VVLTVS assessment (``--json``), or None when unavailable."""
    r = _run_vvltvs(["--json"])
    if r.returncode != 0 or not (r.stdout or "").strip():
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def plan_text() -> str:
    """The read-only remediation plan (``--apply``) — the human-facing proposal body."""
    r = _run_vvltvs(["--apply"])
    return (r.stdout or "").strip() if r.returncode == 0 else ""


def check() -> int:
    """Delegate the coherence predicate to ``vvltvs --check`` (exit 0 ⟺ coherent)."""
    r = _run_vvltvs(["--check"])
    return int(r.returncode)


def gaps(assessment: dict) -> list[dict]:
    """Derive internal-legibility gaps from a VVLTVS assessment.

    Two kinds, each an honest, sourced record:
      * ``claim_drift`` — a face whose value diverges from its canonical source.
      * ``severed_pipe`` — a register conduit that stopped flowing (the root cause; a
        severed pipe upstream of a face is why the face froze).
    A face bound to a *stale/absent* source is advisory, not a hard gap (VVLTVS's rule:
    you cannot hold a face to a target whose own pipe is severed — fix the conduit first).
    """
    out: list[dict] = []

    # VVLTVS's mirror is a dict {"faces": [...]}; each check carries the observed value under
    # "face" and the canonical value under "src"; agreement is state "agree".
    faces = (assessment.get("mirror") or {}).get("faces", []) or []
    for face in faces:
        face_name = face.get("face") or face.get("path") or "?"
        for check_row in face.get("checks", []) or []:
            state = check_row.get("state")
            if state == "drift":
                out.append(
                    {
                        "kind": "claim_drift",
                        "face": face_name,
                        "metric": check_row.get("metric"),
                        "observed": check_row.get("face"),
                        "canonical": check_row.get("src"),
                        "remediation": "re-stamp / project this face from its reconciled source",
                        "reversible": True,
                        "advisory": False,
                    }
                )
            elif state in ("source-stale", "source_stale"):
                out.append(
                    {
                        "kind": "claim_drift",
                        "face": face_name,
                        "metric": check_row.get("metric"),
                        "observed": check_row.get("face"),
                        "canonical": check_row.get("src"),
                        "remediation": "fix the source conduit first (face awaits a stale target)",
                        "reversible": True,
                        "advisory": True,
                    }
                )

    for pipe in assessment.get("pipes", []) or []:
        if pipe.get("state") in ("severed", "stale"):
            out.append(
                {
                    "kind": "severed_pipe",
                    "register": pipe.get("key"),
                    "state": pipe.get("state"),
                    "detail": pipe.get("detail"),
                    "remediation": "revive the severed conduit (root cause; faces auto-heal once it flows)",
                    "reversible": True,
                    "advisory": False,
                }
            )

    return out


def run(*, apply: bool = False) -> dict:
    """The executive stage entry: orchestrate VVLTVS → gaps → evidence + latest.

    Read-only against every public surface. ``apply`` is accepted for signature parity
    with the other stages and reserved for the armed PUBLIC-propose extension; in v1 it
    does not change behavior (the output is always a human-gated proposal).
    """
    assessment = assess()
    if assessment is None:
        report = {"face": "internal_legibility", "sensor": "unavailable", "gap_count": 0, "advisory": True}
        ledger.write_latest("reconcile-latest.json", report)
        return report

    found = gaps(assessment)
    hard = [g for g in found if not g.get("advisory")]
    report = {
        "face": "internal_legibility",
        "sensor": "vvltvs",
        "gap_count": len(found),
        "hard_gaps": len(hard),
        "gaps": found,
        "plan": plan_text(),
        "coherent": not hard,
    }
    # append-only evidence (immutable) + regenerated derived latest
    ledger.append_jsonl("reconcile.jsonl", {"gap_count": len(found), "hard_gaps": len(hard), "gaps": found})
    ledger.write_latest("reconcile-latest.json", report)

    # the executive wants a flat summary
    return {
        "face": "internal_legibility",
        "sensor": "vvltvs",
        "gap_count": len(found),
        "hard_gaps": len(hard),
        "coherent": not hard,
    }
