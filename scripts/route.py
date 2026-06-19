#!/usr/bin/env python3
"""Vendor-tiering router — the conductor's missing thin piece.

Assigns each OPEN work-item to the cheapest-capable AVAILABLE vendor, instead of
dumping the whole backlog on one lane (which is what starved the local fleet on
2026-06-16: 100 tasks all routed to Jules, codex/opencode/agy idle).

Cost model (the "tiering", one level up from model-tiering):
  - Local lanes (codex/opencode/agy/claude) are "free" against the scarce Jules
    100/day quota — they use local compute. PREFER them when a local checkout of
    the task's repo exists.
  - Jules is the only lane that clones a remote repo on demand, and runs async in
    parallel. RESERVE it for repos with no local checkout, and for large batches.
  - Capability routing: deploy/infra/cloudflare work -> opencode (the Agents-SDK
    specialist); everything else local -> codex (strongest local reasoner),
    falling back to agy/claude.
  - Health: a vendor with no usable auth/CLI is skipped (gemini needs
    GEMINI_API_KEY; treated as DOWN until set).

Read-only by default: prints a routing plan. With --apply it only rewrites each
task's target_agent in tasks.yaml (reversible) — it never dispatches. Dispatch
stays a separate, explicitly-gated step (`limen dispatch --agent X --live`).

Usage:
  python3 route.py [--tasks tasks.yaml] [--apply] [--workdir ~/Workspace]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("pyyaml required", file=sys.stderr)
    sys.exit(1)

# route every tasks.yaml write through the ONE atomic primitive (see limen/io.py) so a
# concurrent heartbeat read can never observe a truncated/empty queue.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.io import atomic_write_text

# Vendor health: which local lanes are usable right now. gemini needs an API key.
def _vendor_health() -> dict[str, bool]:
    def has(bin_: str) -> bool:
        return subprocess.run(["which", bin_], capture_output=True).returncode == 0

    gemini_auth = bool(os.environ.get("GEMINI_API_KEY")) or (
        Path.home() / ".gemini" / "settings.json"
    ).exists() and "auth" in (
        (Path.home() / ".gemini" / "settings.json").read_text(errors="ignore")
        if (Path.home() / ".gemini" / "settings.json").exists()
        else ""
    )
    return {
        "jules": has("jules"),
        "codex": has("codex"),
        "opencode": has("opencode"),
        "agy": has("agy"),
        "claude": has("claude"),
        "gemini": has("gemini") and bool(gemini_auth),
    }


def _local_checkout(repo: str | None, workdir: Path) -> Path | None:
    """Mirror of dispatch._resolve_repo_dir: does a local git checkout exist?"""
    if not repo:
        return None
    org, _, name = repo.partition("/")
    cart = Path.home() / "Workspace" / ".home-cartridge" / "Code"
    for cand in (workdir / repo, workdir / org / name, workdir / name,
                 cart / org / name, cart / name):
        if (cand / ".git").exists():
            return cand
    for root in (workdir, cart):
        for p in root.glob(f"*/{name}"):
            if (p / ".git").exists():
                return p
    return None


# Capability hints by task type / title keyword -> preferred LOCAL vendor.
_DEPLOY_HINTS = ("deploy", "cloudflare", "worker", "wrangler", "infra", "hosting")


# General local lanes that compete for non-deploy work. opencode is reserved for deploy/infra
# (and used only as a last-resort fallback below) because it historically times out on big tasks.
_LOCAL_LANES = ("codex", "claude", "agy")


def _pick_local(
    task: dict,
    health: dict[str, bool],
    assigned: dict[str, int],
    budget: dict[str, int],
) -> str | None:
    """Pick a healthy LOCAL lane, distributing across ALL of them by per-agent budget headroom.

    The old version returned the first healthy lane (always codex), which serialized the whole
    fleet onto one vendor and starved claude/agy/jules — violating the use-all-vendors mandate.
    We now spread load proportional to each lane's daily budget: pick the lane with the lowest
    assigned/budget ratio so far, weighting higher-budget lanes to take proportionally more.
    """
    text = f"{task.get('type','')} {task.get('title','')} {task.get('context','')}".lower()
    if any(h in text for h in _DEPLOY_HINTS) and health.get("opencode"):
        return "opencode"
    candidates = [v for v in _LOCAL_LANES if health.get(v)]
    if not candidates and health.get("opencode"):  # only opencode is up locally -> use it
        candidates = ["opencode"]
    if not candidates:
        return None

    def load(v: str) -> float:
        b = budget.get(v, 0) or 1
        return assigned.get(v, 0) / b

    # least-loaded by budget ratio; tie-break toward the higher-budget lane, then name (stable).
    return min(candidates, key=lambda v: (load(v), -budget.get(v, 0), v))


def route_task(
    task: dict,
    health: dict[str, bool],
    workdir: Path,
    assigned: dict[str, int] | None = None,
    budget: dict[str, int] | None = None,
) -> tuple[str, str]:
    """Return (vendor, reason) for one open task."""
    assigned = assigned if assigned is not None else {}
    budget = budget if budget is not None else {}
    repo = task.get("repo")
    checkout = _local_checkout(repo, workdir)
    if checkout is not None:
        local = _pick_local(task, health, assigned, budget)
        if local:
            return local, f"local checkout at {checkout} -> {local} (distributed by budget)"
        # local exists but no healthy local lane -> fall through to jules
    if health.get("jules"):
        why = "no local checkout; only Jules clones remotely" if checkout is None \
              else "no healthy local lane; Jules fallback"
        return "jules", why
    return "unroutable", "no healthy vendor (no local lane and Jules down)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", "tasks.yaml"))
    ap.add_argument("--workdir", default=os.environ.get(
        "LIMEN_WORKDIR", str(Path.home() / "Workspace")))
    ap.add_argument("--apply", action="store_true",
                    help="rewrite target_agent in tasks.yaml (reversible); never dispatches")
    args = ap.parse_args()

    tasks_path = Path(args.tasks)
    workdir = Path(args.workdir).expanduser()
    data = yaml.safe_load(tasks_path.read_text())
    health = _vendor_health()

    up = [k for k, v in health.items() if v]
    down = [k for k, v in health.items() if not v]
    print(f"# Router plan  (vendors up: {', '.join(up)}; down: {', '.join(down) or 'none'})\n")

    opens = [t for t in data["tasks"] if t.get("status") == "open"]
    if not opens:
        print("No open tasks to route. (Backlog is empty or fully dispatched.)")
        return 0

    print("| task | repo | -> vendor | reason |")
    print("|---|---|---|---|")
    from collections import Counter
    # per-agent daily budget drives the distribution (derived from tasks.yaml, never pinned).
    budget = (data.get("portal", {}).get("budget", {}) or {}).get("per_agent", {}) or {}
    tally: Counter = Counter()
    for t in opens:
        # pass the running tally as the assigned-so-far counts so load spreads across lanes.
        vendor, reason = route_task(t, health, workdir, assigned=tally, budget=budget)
        tally[vendor] += 1
        print(f"| {t['id']} | {t.get('repo','-')} | {vendor} | {reason} |")
        if args.apply and vendor not in ("unroutable",):
            t["target_agent"] = vendor

    print(f"\nrouted: {dict(tally)}")
    if args.apply:
        atomic_write_text(tasks_path, yaml.safe_dump(data, sort_keys=False))
        print(f"applied target_agent assignments -> {tasks_path} "
              f"(dispatch separately, gated: limen dispatch --agent <v> --live)")
    else:
        print("dry-run (no changes). re-run with --apply to set target_agent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
