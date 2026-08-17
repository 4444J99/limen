#!/usr/bin/env python3
"""Pause-marker hygiene predicate — an AUTONOMY_PAUSED marker that can never autoclear is a defect.

The recurring freeze (2026-07-14 → 2026-07-15 → 2026-07-16, three times): a
``logs/AUTONOMY_PAUSED`` marker whose release path the governor can never reach. current_mode()
returns ``"paused"`` for *any* marker unless _marker_owner_merged() clears it — and that clears
ONLY when a resolvable ``pr:``/``owner:`` coordinate names a MERGED PR. A marker carrying only an
``owner_surface:`` prose line (which never parses as ``owner:``), or an ``owner:`` label that
matches no branch, can therefore idle the whole beat forever. autonomy-governor's own docstring
(``_marker_owner_merged``) documents this as "the 2026-07-15 freeze recurrence". Nothing catches it.
This is that catch.

A marker is HEALTHY when it can either self-clear or tell someone how to clear it:
  • a release COORDINATE — a ``pr:`` number or a non-empty ``owner:`` branch that is still
    merge-reachable (best-effort resolved against GitHub when ``gh`` is available; fail-OPEN so
    offline/gh-down never false-fails). The governor autoclears ONLY on a MERGED PR, so a coordinate
    that resolves to a CLOSED-but-unmerged PR is itself a defect — it can never self-clear (the
    superseded-coordinate case: a preservation/draft PR whose remedy was extracted into other PRs and
    which then closes unmerged, leaving the marker pinned to a dead coordinate), OR
  • a ``next_command:`` recovery runbook (machine-executable per the 2026-07-15 discipline).

Exit 0 ⟺ no marker, or the marker is healthy.
Exit 1 ⟺ a marker exists that can neither self-clear nor be cleared by runbook — no coordinate/runbook,
         a coordinate that matches NO PR, or a coordinate that names only a CLOSED-unmerged PR.

Wired advisory into the beat (institutio/governance/sensors.yaml → ``pause-marker-hygiene``): an
advisory sensor never breaks the beat, it just surfaces the defect with a ``↑`` every cycle until a
release coordinate or runbook is added. Standalone it is a plain predicate for CI / omega / a
session. Read-only; the marker is never written here.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT") or Path(__file__).resolve().parents[1])
MARKER = ROOT / "logs" / "AUTONOMY_PAUSED"

# The strict ``<name>:`` prefix parse — an ``owner_surface:`` line never reads as ``owner:``.
# Kept identical to autonomy-governor._marker_fields so the two agree on what a coordinate is.
_FIELDS = ("owner", "pr", "reason", "prohibitions", "release_predicate", "next_command", "class")


def _marker_fields(marker: Path) -> dict[str, str]:
    try:
        lines = marker.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    def field(name: str) -> str:
        return next((ln.split(":", 1)[1].strip() for ln in lines if ln.strip().startswith(f"{name}:")), "")

    return {name: field(name) for name in _FIELDS}


def _pr_number(fields: dict[str, str]) -> str:
    match = re.search(r"(\d+)\s*$", fields.get("pr", ""))
    return match.group(1) if match else ""


def _coordinate_status(fields: dict[str, str], *, timeout: float) -> str:
    """Best-effort classification of the ``pr:``/``owner:`` release coordinate against GitHub.

    The governor autoclears a marker ONLY when the coordinate names a MERGED PR — so a coordinate that
    can still reach a merge is healthy, but one that never can is the freeze defect. Returns:
      • ``"reachable"``       — resolves to an OPEN or MERGED PR (can still self-clear, or already has),
                                OR gh is unavailable/offline/errored (fail-OPEN: a hiccup must never nag);
      • ``"unmatched"``       — gh SUCCEEDED and the coordinate names NO PR (the 2026-07-15 label defect);
      • ``"closed_unmerged"`` — resolves ONLY to a CLOSED-but-unmerged PR; the governor clears on MERGED
                                alone, so this can never autoclear (the superseded-coordinate defect).
    """
    pr = _pr_number(fields)
    owner = fields.get("owner", "")
    try:
        if pr:
            proc = subprocess.run(
                ["gh", "pr", "view", pr, "--json", "state"],
                capture_output=True, text=True, timeout=timeout, check=False, cwd=str(ROOT),
            )
            if proc.returncode != 0:
                return "unknown"  # not-found, auth, or offline all land here → fail-open
            state = str(json.loads(proc.stdout).get("state", "")).upper()
            return "closed_unmerged" if state == "CLOSED" else "reachable"
        if owner:
            proc = subprocess.run(
                ["gh", "pr", "list", "--head", owner, "--state", "all", "--json", "state", "--limit", "20"],
                capture_output=True, text=True, timeout=timeout, check=False, cwd=str(ROOT),
            )
            if proc.returncode != 0:
                return "unknown"
            rows = json.loads(proc.stdout)
            if not (isinstance(rows, list) and rows):
                return "unmatched"
            states = {str(r.get("state", "")).upper() for r in rows}
            # healthy if any branch PR is still merge-reachable (OPEN) or already MERGED
            return "reachable" if (states & {"OPEN", "MERGED"}) else "closed_unmerged"
    except (OSError, subprocess.SubprocessError, ValueError):
        return "unknown"
    return "unknown"


def evaluate(*, resolve: bool, timeout: float) -> tuple[int, str]:
    if not MARKER.exists():
        return 0, "pause-marker-hygiene: OK — no AUTONOMY_PAUSED marker present"

    fields = _marker_fields(MARKER)
    reason = (fields.get("reason") or "see logs/AUTONOMY_PAUSED")[:140]

    # Schema guard: an explicit `class:` must be fence|wall. A present-but-invalid value is a defect —
    # readers (session-orient) silently fall back to reason-sniffing, so a typo'd class can render a
    # fence as a wall (or vice-versa) against intent. An ABSENT class is fine (legacy → regex fallback).
    declared_class = (fields.get("class") or "").strip().lower()
    if declared_class and declared_class not in ("fence", "wall"):
        return 1, (
            f"pause-marker-hygiene: DEFECT — marker declares class {declared_class!r}, not fence|wall; "
            f"readers fall back to reason-sniffing, so the fence/wall render may disagree with intent. "
            f"Fix the `class:` line (scripts/pause.py writes it well-formed). Marker reason: {reason}"
        )

    has_coordinate = bool(_pr_number(fields)) or bool(fields.get("owner"))
    has_runbook = bool(fields.get("next_command"))

    if has_runbook:
        return 0, f"pause-marker-hygiene: OK — marker carries a next_command recovery runbook ({reason})"

    if has_coordinate:
        if not resolve:
            return 0, f"pause-marker-hygiene: OK — marker declares a release coordinate ({reason})"
        status = _coordinate_status(fields, timeout=timeout)
        coord = fields.get("pr") or fields.get("owner")
        if status == "unmatched":
            return 1, (
                f"pause-marker-hygiene: DEFECT — release coordinate {coord!r} resolves to NO PR and "
                f"there is no next_command runbook; the governor can never autoclear this marker "
                f"(the 2026-07-15 label-mismatch freeze). Point pr:/owner: at a real PR or add a "
                f"next_command. Marker reason: {reason}"
            )
        if status == "closed_unmerged":
            return 1, (
                f"pause-marker-hygiene: DEFECT — release coordinate {coord!r} resolves ONLY to a "
                f"CLOSED-but-unmerged PR and there is no next_command runbook; the governor autoclears "
                f"on MERGED alone, so this marker can never self-clear (the superseded-coordinate "
                f"freeze). Repoint pr:/owner: at the PR that will actually land, or add a next_command. "
                f"Marker reason: {reason}"
            )
        # reachable or unknown (fail-open) → healthy
        return 0, f"pause-marker-hygiene: OK — marker's release coordinate is merge-reachable ({reason})"

    # No coordinate at all AND no runbook — the exact defect (this is the owner_surface-only class).
    return 1, (
        "pause-marker-hygiene: DEFECT — marker has no `pr:`/`owner:` release coordinate and no "
        "`next_command` runbook, so autonomy-governor can never autoclear it and the beat idles "
        "forever (the 2026-07-15 freeze recurrence). Add `pr: <n>`/`owner: <branch>` or a "
        f"`next_command:`. Marker reason: {reason}"
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="AUTONOMY_PAUSED marker hygiene predicate")
    ap.add_argument(
        "--no-resolve",
        action="store_true",
        help="structural check only; do not consult gh to resolve a declared pr:/owner: coordinate",
    )
    ap.add_argument("--timeout", type=float, default=15.0, help="per-gh-call timeout seconds (default 15)")
    args = ap.parse_args(argv)

    code, message = evaluate(resolve=not args.no_resolve, timeout=args.timeout)
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
