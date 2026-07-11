#!/usr/bin/env python3
"""Small policy gate for Limen autonomy.

The heartbeat is allowed to exist without being allowed to spend. This file is the
single local switch:

  mode=paused   -> exit immediately
  mode=observe  -> telemetry/status only, no queue mutation or dispatch
  mode=dispatch -> full conductor loop, still subject to usage health gates
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
POLICY_PATH = ROOT / "logs" / "autonomy-policy.json"
PAUSE_MARKER = ROOT / "logs" / "AUTONOMY_PAUSED"
MARKER_RECHECK_STAMP = ROOT / "logs" / ".autonomy-marker-recheck"
VALID_MODES = {"paused", "observe", "dispatch"}

DEFAULT_POLICY = {
    "mode": "observe",
    "dispatch_enabled": False,
    "reason": "Default after 2026-06-20 usage audit: observe safely; dispatch requires an explicit policy change.",
}


def load_policy() -> dict[str, Any]:
    if not POLICY_PATH.exists():
        POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
        POLICY_PATH.write_text(json.dumps(DEFAULT_POLICY, indent=2) + "\n")
        return dict(DEFAULT_POLICY)
    try:
        policy = json.loads(POLICY_PATH.read_text())
    except Exception:
        return {"mode": "paused", "dispatch_enabled": False, "reason": "invalid autonomy-policy.json"}
    if not isinstance(policy, dict):
        return {"mode": "paused", "dispatch_enabled": False, "reason": "autonomy policy must be an object"}
    mode = str(policy.get("mode", "observe")).lower()
    if mode not in VALID_MODES:
        policy["mode"] = "paused"
        policy["dispatch_enabled"] = False
        policy["reason"] = f"invalid mode {mode!r}"
    return policy


def usage_dead_lanes() -> set[str]:
    path = ROOT / "logs" / "usage.json"
    try:
        vendors = (json.loads(path.read_text()) or {}).get("vendors", {})
    except Exception:
        return set()
    return {
        name
        for name, info in vendors.items()
        if isinstance(info, dict) and info.get("health") in {"exhausted", "rate-limited"}
    }


def _marker_owner_merged(marker: Path) -> bool:
    """True iff the pause marker's ``owner:`` branch has a MERGED PR on GitHub.

    A stale "integration drain" marker whose owner PR already merged is the exact 21h-freeze
    incident (2026-07-10, owner codex/dynamic-routing-closeout-20260710, PR #921 merged the next
    morning): under launchd KeepAlive the beat respawn-spins on ``return "paused"`` forever
    because nothing clears the marker. This lets current_mode() — the single chokepoint the
    heartbeat and dispatch admission both read — clear it within one cycle of the merge.

    Fail-CLOSED: any ambiguity (autoclear disabled, no owner line, gh missing/errored, offline,
    not-yet-merged) returns False so the beat stays paused. Throttled to at most once per
    LIMEN_AUTONOMY_MARKER_RECHECK_SECS so rapid callers don't hammer ``gh`` while a marker exists.
    """
    if os.environ.get("LIMEN_AUTONOMY_MARKER_AUTOCLEAR", "1") != "1":
        return False
    try:
        recheck = float(os.environ.get("LIMEN_AUTONOMY_MARKER_RECHECK_SECS", "120"))
    except ValueError:
        recheck = 120.0
    now = time.time()
    try:
        if now - MARKER_RECHECK_STAMP.stat().st_mtime < recheck:
            return False  # checked recently — stay paused until the throttle window elapses
    except OSError:
        pass
    try:
        owner = next(
            (ln.split(":", 1)[1].strip() for ln in marker.read_text().splitlines()
             if ln.strip().startswith("owner:")),
            "",
        )
    except OSError:
        return False
    if not owner:
        return False
    try:
        MARKER_RECHECK_STAMP.parent.mkdir(parents=True, exist_ok=True)
        MARKER_RECHECK_STAMP.write_text(str(now))
    except OSError:
        pass
    try:
        proc = subprocess.run(
            ["gh", "pr", "list", "--head", owner, "--state", "merged", "--json", "number", "--limit", "1"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    # A merged PR row survives branch deletion in GitHub's PR index, so --head is reliable here.
    return proc.stdout.strip() not in ("", "[]")


def current_mode() -> str:
    if PAUSE_MARKER.exists() and os.environ.get("LIMEN_FORCE_AUTONOMY") != "1":
        if _marker_owner_merged(PAUSE_MARKER):
            try:
                PAUSE_MARKER.unlink()
            except OSError:
                pass
            # owner PR merged — fall through to policy mode; a merged-owner marker
            # can never freeze the next cycle. (Merge is a strict prerequisite of the
            # marker's release_predicate; the remaining conditions are separately enforced
            # by the ship-gate / omega sensors.)
        else:
            return "paused"
    return str(load_policy().get("mode", "observe")).lower()


def dispatch_allowed() -> tuple[bool, str]:
    policy = load_policy()
    mode = current_mode()
    if mode != "dispatch":
        return False, f"autonomy mode is {mode}"
    if not bool(policy.get("dispatch_enabled")) and os.environ.get("LIMEN_FORCE_AUTONOMY") != "1":
        return False, "dispatch_enabled is false"
    dead = usage_dead_lanes()
    if {"codex", "claude", "jules"}.issubset(dead):
        return False, "primary paid lanes exhausted/rate-limited"
    return True, "dispatch allowed"


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("mode")
    sub.add_parser("dispatch-ok")
    sub.add_parser("explain")
    args = ap.parse_args()

    if args.cmd == "mode":
        print(current_mode())
        return 0
    if args.cmd == "dispatch-ok":
        ok, reason = dispatch_allowed()
        print(reason)
        return 0 if ok else 2
    policy = load_policy()
    ok, reason = dispatch_allowed()
    print(
        json.dumps(
            {
                "mode": current_mode(),
                "policy": policy,
                "dispatchAllowed": ok,
                "dispatchReason": reason,
                "deadLanes": sorted(usage_dead_lanes()),
                "pauseMarker": str(PAUSE_MARKER),
                "pauseMarkerExists": PAUSE_MARKER.exists(),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
