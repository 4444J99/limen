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
import re
import subprocess
import sys
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


def _marker_fields(marker: Path) -> dict[str, str]:
    """Parse the marker's structured lines by strict ``<name>:`` prefix — an ``owner_surface:``
    line never reads as ``owner:`` (the 2026-07-15 operator study-pause relies on exactly that)."""
    try:
        lines = marker.read_text().splitlines()
    except OSError:
        return {}

    def field(name: str) -> str:
        return next(
            (ln.split(":", 1)[1].strip() for ln in lines if ln.strip().startswith(f"{name}:")),
            "",
        )

    return {name: field(name) for name in ("owner", "pr", "repo", "prohibitions", "release_predicate")}


def _pr_owned_pause(fields: dict[str, str]) -> bool:
    """True iff the marker DECLARES its own release to be the merge of an identifiable PR.

    Every clause fails toward check-only (today's behavior). An operator pause is structurally
    ineligible twice over: its prohibitions mention merge, and it carries no ``owner:``/``pr:``
    identity (``owner_surface:`` does not parse as ``owner:``).
    """
    if os.environ.get("LIMEN_AUTONOMY_MARKER_AUTOMERGE", "1") != "1":
        return False
    if not (fields.get("owner") or fields.get("pr")):
        return False
    if "merge" not in fields.get("release_predicate", "").lower():
        return False  # the marker's author did not declare merge as the release — never infer it
    if "merge" in fields.get("prohibitions", "").lower():
        return False  # the marker forbids merging — the governor is bound like everyone else
    return True


def _resolve_release_pr(fields: dict[str, str]) -> str:
    """The marker's release PR number: an explicit ``pr:`` line, else the single OPEN PR whose
    head is the ``owner:`` branch. Zero or multiple candidates → '' (ambiguity → check-only)."""
    pr_match = re.search(r"(\d+)\s*$", fields.get("pr", ""))
    if pr_match:
        return pr_match.group(1)
    owner = fields.get("owner", "")
    if not owner:
        return ""
    try:
        proc = subprocess.run(
            ["gh", "pr", "list", "--head", owner, "--state", "open", "--json", "number"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            cwd=str(ROOT),
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        return ""
    try:
        rows = json.loads(proc.stdout)
    except ValueError:
        return ""
    if isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict) and rows[0].get("number"):
        return str(rows[0]["number"])
    return ""


def _try_complete_release(fields: dict[str, str]) -> bool:
    """COMPLETE a PR-owned pause instead of merely checking it — the deadly-embrace fix.

    A pause whose release predicate is "the owner PR merges" used to wait on an organ that lives
    INSIDE the paused beat (merge-drain runs on the drain voice; the heartbeat exits when paused),
    so a session or human always had to babysit the merge (the 2026-07-15 endless-watcher
    incident). Here the governor itself runs the ONE merge predicate (scripts/merge-policy.sh)
    and, only on CLEARED (exit 0), performs the squash merge head-pinned to the predicate's
    MERGE-HEAD line. Fail-CLOSED everywhere: HOLD/BLOCKED/broken-predicate/failed-merge all
    return False and the estate stays paused for the next throttled cycle. True only after gh
    re-confirms the PR is MERGED — the caller then unlinks the marker.
    """
    if not _pr_owned_pause(fields):
        return False
    pr = _resolve_release_pr(fields)
    if not pr:
        return False
    policy = os.environ.get("LIMEN_MERGE_POLICY_BIN") or str(Path(__file__).resolve().parent / "merge-policy.sh")
    try:
        verdict = subprocess.run(
            ["bash", policy, pr], capture_output=True, text=True, timeout=90, check=False, cwd=str(ROOT)
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if verdict.returncode != 0:
        return False  # HOLD (2) / BLOCKED (3) / broken predicate — stay paused, retry next window
    merge_cmd = ["gh", "pr", "merge", pr, "--squash"]
    sha = re.search(r"^MERGE-HEAD: ([0-9a-f]+)", verdict.stdout, re.M)
    if sha:
        merge_cmd += ["--match-head-commit", sha.group(1)]
    try:
        if (
            subprocess.run(merge_cmd, capture_output=True, text=True, timeout=90, check=False, cwd=str(ROOT)).returncode
            != 0
        ):
            return False
        confirm = subprocess.run(
            ["gh", "pr", "view", pr, "--json", "state"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            cwd=str(ROOT),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    try:
        merged = confirm.returncode == 0 and str(json.loads(confirm.stdout).get("state")) == "MERGED"
    except ValueError:
        return False
    if merged:
        print(
            f"autonomy-governor: completed pause release — merge-policy CLEARED and PR #{pr} squash-merged",
            file=sys.stderr,
        )
    return merged


def _marker_owner_merged(marker: Path) -> bool:
    """True iff the pause marker's release PR merged — via ``pr:`` line or ``owner:`` branch.

    A stale "integration drain" marker whose owner PR already merged is the exact 21h-freeze
    incident (2026-07-10, owner codex/dynamic-routing-closeout-20260710, PR #921 merged the next
    morning): under launchd KeepAlive the beat respawn-spins on ``return "paused"`` forever
    because nothing clears the marker. This lets current_mode() — the single chokepoint the
    heartbeat and dispatch admission both read — clear it within one cycle of the merge.

    When the release PR is NOT yet merged, a PR-owned marker (see _pr_owned_pause) gets its
    release COMPLETED here via _try_complete_release — merge-policy CLEARED → squash merge —
    so the pause can never deadly-embrace the paused beat that would have merged it.

    Fail-CLOSED: any ambiguity (autoclear disabled, no owner line, gh missing/errored, offline,
    not-yet-merged-and-not-completable) returns False so the beat stays paused. Throttled to at
    most once per LIMEN_AUTONOMY_MARKER_RECHECK_SECS so rapid callers don't hammer ``gh`` while
    a marker exists — the completion attempt runs inside the same throttle window.
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
    fields = _marker_fields(marker)
    owner = fields.get("owner", "")
    # An explicit ``pr:`` line names the release PR directly (e.g. ``pr: 1036`` or
    # ``pr: organvm/limen#1036``). The 2026-07-15 freeze recurrence: the marker's owner said
    # ``manual/overnight-watch-pause-guard-20260714`` but the guard merged from branch
    # ``agent/overnight-watch-pause-guard`` — the --head search can never match a hand-written
    # owner label, so the beat stayed paused after its release predicate was already satisfied.
    pr_match = re.search(r"(\d+)\s*$", fields.get("pr", ""))
    pr_number = pr_match.group(1) if pr_match else ""
    if not owner and not pr_number:
        return False
    try:
        MARKER_RECHECK_STAMP.parent.mkdir(parents=True, exist_ok=True)
        MARKER_RECHECK_STAMP.write_text(str(now))
    except OSError:
        pass
    if pr_number:
        try:
            proc = subprocess.run(
                ["gh", "pr", "view", pr_number, "--json", "state"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
                cwd=str(ROOT),
            )
        except (OSError, subprocess.SubprocessError):
            return False
        if proc.returncode == 0:
            try:
                if str(json.loads(proc.stdout).get("state")) == "MERGED":
                    return True
            except ValueError:
                pass
        if not owner:
            return _try_complete_release(fields)
    try:
        proc = subprocess.run(
            ["gh", "pr", "list", "--head", owner, "--state", "merged", "--json", "number", "--limit", "1"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            cwd=str(ROOT),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    # A merged PR row survives branch deletion in GitHub's PR index, so --head is reliable here.
    if proc.stdout.strip() not in ("", "[]"):
        return True
    return _try_complete_release(fields)


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
