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
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
POLICY_PATH = ROOT / "logs" / "autonomy-policy.json"
PAUSE_MARKER = ROOT / "logs" / "AUTONOMY_PAUSED"
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


def current_mode() -> str:
    if PAUSE_MARKER.exists() and os.environ.get("LIMEN_FORCE_AUTONOMY") != "1":
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
