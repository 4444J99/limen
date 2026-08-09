#!/usr/bin/env python3
"""Shared effect ledger for DESTRUCTIVE valves — the denominator that tells dead from idle.

The gap this closes (measured 2026-08-09, organvm/limen#2150): ``self-heal.py``'s retirement pass
shipped beat-wired and scheduled, ran on every beat, exited 0 on every beat, and retired nothing on
any beat. Its enumeration was capped below the live open-PR count, so the truncation guard refused
to retire from a prefix — correctly, and silently. It stayed dead for a day.

Nothing in the estate could see it, and the reason is structural rather than a missing flag:

  * ``armed-valve-audit.py`` classifies ARMING. The valve was ARMED.
  * ``enactment-audit.py``'s WIRING rung proves a flag resolves ON. It did.
  * its LIVENESS rung proves the daemon post-dates its wiring. It did.
  * its EFFICACY rung goes RED on consecutive NON-ZERO exits. Every exit was 0.

A valve that succeeds at doing nothing passes all four. **The healthy case and the dead case emit
the identical signal** — a quiet beat and a zero — so no reader of that signal can separate them.

They separate on the DENOMINATOR. "I retired 0" is ambiguous; "I retired 0 of 257 I could have"
is a defect and "I retired 0 of 0" is a healthy idle beat. So this ledger requires ``candidates``
alongside ``effects``, and requires them to be computed INDEPENDENTLY of authorization: a valve
that refuses to act must still report what it would have acted on, or refusing looks exactly like
having nothing to do. That is the whole design — everything else here is plumbing.

Adopting it is one call at the end of a valve's run:

    from _valve_effects import record
    record("heal-retirement", authorized=ok, candidates=len(cands), effects=len(done),
           dry_run=args.dry_run, detail=why)

Read by ``enactment-audit.py``'s POTENCY rung. Fail-open everywhere: a sensor that can wedge the
organ it observes is worse than no sensor.
"""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path

LEDGER_NAME = "valve-effects.jsonl"
# Bounded so an unrotated ledger cannot grow without limit on a machine that beats every ~10
# minutes. The POTENCY rung only ever reads a TRAILING streak, so old rows have no readers.
MAX_ROWS = 2000


def ledger_path(root: Path | str | None = None) -> Path:
    """Where the ledger lives, resolved the same way every other beat ledger is.

    ``LIMEN_VALVE_EFFECT_LOG`` overrides outright (tests, fixtures). Otherwise it sits beside
    ``beat-rungs.jsonl`` under the root the DAEMON runs from — #2053 fixed exactly this asymmetry
    for enactment-audit's liveness rung, and resolving against a session worktree here would put
    the writer and the reader in different directories, which reads as "no data" rather than as a
    misconfiguration.
    """
    override = os.environ.get("LIMEN_VALVE_EFFECT_LOG")
    if override:
        return Path(override)
    base = Path(root) if root else Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
    return base / "logs" / LEDGER_NAME


def record(
    valve: str,
    *,
    authorized: bool,
    candidates: int,
    effects: int,
    dry_run: bool = False,
    detail: str = "",
    root: Path | str | None = None,
) -> bool:
    """Append one run's effect row. Returns True if written; never raises.

    ``candidates`` is the load-bearing field and it is NOT optional. A valve reporting only
    ``effects`` re-creates the exact blindness this ledger exists to remove, so pass the count you
    evaluated even — especially — when ``authorized`` is False.
    """
    row = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "valve": str(valve),
        "authorized": bool(authorized),
        "candidates": int(candidates),
        "effects": int(effects),
        "dry_run": bool(dry_run),
        "detail": str(detail)[:400],
    }
    path = ledger_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        _trim(path)
        return True
    except OSError:
        return False  # fail-open: a sensor must never wedge the organ it observes


def _trim(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_ROWS:
            path.write_text("\n".join(lines[-MAX_ROWS:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def read_rows(path: Path) -> list[dict]:
    """Rows in run order. Malformed lines are skipped, never fatal — this is a sensor."""
    rows: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return rows
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and "valve" in row:
            rows.append(row)
    return rows


def idle_streaks(rows: list[dict]) -> dict[str, dict]:
    """Per valve, its TRAILING run of consecutive IDLE runs: {valve: {streak, why, last}}.

    A run is IDLE when the valve could have acted and did not — either it was refused
    (``authorized`` False) or it was authorized with candidates waiting and produced no effects.
    Everything else BREAKS the streak, and each exclusion is deliberate:

      * ``effects > 0``      — it acted. Obviously healthy.
      * ``candidates == 0``  — nothing to act on. This is the case that makes a naive
                               "effects == 0" alarm useless: a healthy valve on a drained backlog
                               reports zero forever, and an alarm that fires on it gets muted,
                               taking the real signal with it.
      * ``dry_run``          — a dry run does not act BY DESIGN. Counting it would make every
                               operator's `--dry-run` poke look like a defect.

    Trailing rather than total, matching ``enactment-audit.failing_streaks``: a valve that was dead
    last week and has acted since is healthy, and counting history would pin it red permanently —
    which trains readers to ignore it, the precise failure this whole lineage is about.
    """
    per: dict[str, list[dict]] = {}
    for row in rows:
        per.setdefault(str(row.get("valve")), []).append(row)

    out: dict[str, dict] = {}
    for valve, runs in per.items():
        streak = 0
        why = ""
        for row in reversed(runs):
            if row.get("dry_run"):
                continue  # neither breaks nor extends: a dry run is not evidence either way
            effects = int(row.get("effects") or 0)
            candidates = int(row.get("candidates") or 0)
            authorized = bool(row.get("authorized"))
            if effects > 0 or (authorized and candidates == 0):
                break
            if not authorized:
                reason = f"refused to act ({row.get('detail') or 'no reason recorded'})"
            else:
                reason = f"authorized with {candidates} candidate(s) and produced no effect"
            streak += 1
            if not why:
                why = reason
        if streak:
            out[valve] = {"streak": streak, "why": why, "last": runs[-1]}
    return out
