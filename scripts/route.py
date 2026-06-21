#!/usr/bin/env python3
"""Paid-agent router — the conductor's missing thin piece.

Assigns each OPEN work-item to a capable AVAILABLE paid service, instead of
dumping the whole backlog on one lane (which is what starved the local fleet on
2026-06-16: 100 tasks all routed to Jules, codex/opencode/agy idle).

Cost model (the "tiering", one level up from model-tiering):
  - Local lanes (codex/opencode/agy/claude/gemini) use a local checkout. Among
    them the split is made by TWO live signals: per-agent daily BUDGET headroom
    (don't dump all on one lane) and refresh-window RUNWAY from the usage meter
    (don't feed a lane pacing toward its reserve) — so load steers to the FRESHEST
    window and no lane is burned to 0 while another sits idle.
  - Jules is the only lane that clones a remote repo on demand, and runs async in
    parallel. RESERVE it for repos with no local checkout, and for large batches.
  - Copilot assigns an existing GitHub issue to copilot-swe-agent.
  - GitHub Actions triggers a configured workflow_dispatch workflow.
  - Warp/Oz are configurable paid-service lanes via LIMEN_WARP_DISPATCH_CMD and
    LIMEN_OZ_DISPATCH_CMD, or the generic agent-dispatch adapter.
  - Health: a service with no usable auth/CLI/config is skipped. The LIVE usage
    meter (logs/usage.json) additionally drops any lane that is token-exhausted,
    rate-limited, or at/below its pacing reserve (`_down_lanes`) — route and
    dispatch agree on which lanes can actually produce, and a lane rejoins the
    instant its rolling window refills.
  - Capacity: every run prints a census of the paid fleet, then distributes work
    across every reachable capable lane so no paid service sits idle while work
    exists.

Read-only by default: prints a routing plan. With --apply it only rewrites each
task's target_agent in tasks.yaml (reversible) — it never dispatches. Dispatch
stays a separate, explicitly-gated step (`limen dispatch --agent X --live`).

Usage:
  python3 route.py [--tasks tasks.yaml] [--apply] [--workdir ~/Workspace]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.capacity import (  # noqa: E402
    ISSUE_ASSIGNMENT_AGENTS,
    LOCAL_CHECKOUT_AGENTS,
    PAID_AGENT_ORDER,
    capacity_census,
    format_capacity_census,
    task_has_github_issue,
)
from limen.io import atomic_write_text  # noqa: E402
from limen.dispatch import _down_lanes  # noqa: E402

try:
    import yaml
except ImportError:
    print("pyyaml required", file=sys.stderr)
    sys.exit(1)


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


def _fleet_health(data) -> dict[str, bool]:
    """One health map for the WHOLE PAID_AGENT_ORDER. Origin's local-CLI probe for the six vendor
    lanes, UNIONed with the capacity census's reachability for the extended paid fleet
    (copilot/github_actions/warp/oz) so fan-all coverage is REAL, not just declared — a remote-only
    repo with a GitHub issue can still route to copilot when no local lane can serve it."""
    health = _vendor_health()
    try:
        for row in capacity_census(data):
            a = row["agent"]
            if a not in health:
                health[a] = bool(row["reachable"])
    except Exception:
        pass
    return health


def _vendor_runway() -> dict[str, float]:
    """Per-vendor hours-of-runway from the LIVE usage meter (logs/usage.json, written by
    usage-telemetry.py). This is the refresh-vs-remaining input to the split decision: how long
    until each lane's rolling window is exhausted at the current burn. Missing/None runway (an idle
    lane, burn≈0) reads as +inf — maximally fresh. Derived from the live signal, never pinned."""
    f = Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen"))) / "logs" / "usage.json"
    try:
        vendors = (json.loads(f.read_text()) or {}).get("vendors", {})
    except (OSError, ValueError):
        return {}
    out: dict[str, float] = {}
    for name, info in vendors.items():
        if not isinstance(info, dict):
            continue
        r = info.get("runway_h")
        out[name] = float("inf") if r is None else float(r)
    return out


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


def _task_cost(task: dict) -> int:
    try:
        return int(task.get("budget_cost", 1))
    except (TypeError, ValueError):
        return 1


# General local lanes that compete for non-deploy work, distributed by budget headroom + runway.
# opencode is in the GENERAL rotation: its specialty (deploy/cloudflare) is blocked on Cloudflare
# auth (those tasks are needs_human), so reserving it for deploy would leave a whole lane with
# ~full budget IDLE — a "don't leave a lane with usage idle" violation. The 1800s lane timeout +
# jules async-fallback bound its historical big-task timeouts. It still gets FIRST pick for genuine
# deploy/infra work (the _DEPLOY_HINTS branch below) when that's unblocked.
_DEPLOY_HINTS = ("deploy", "cloudflare", "worker", "wrangler", "infra", "hosting")
_LOCAL_LANES = ("codex", "claude", "agy", "opencode")


def _pick_local(
    task: dict,
    health: dict[str, bool],
    assigned: dict[str, int],
    budget: dict[str, int],
    runway: dict[str, float] | None = None,
) -> str | None:
    """Pick a healthy LOCAL lane, splitting across ALL of them by per-agent budget headroom AND
    live refresh-window runway.

    The old version returned the first healthy lane (always codex), which serialized the whole
    fleet onto one vendor and starved claude/agy/jules — violating the use-all-vendors mandate.
    We now spread load proportional to each lane's daily budget (least assigned/budget ratio first)
    and, among lanes at the same load, STEER toward the one with the most refresh runway — so when
    loads are even (early/idle) work flows to the freshest rolling window, and a lane pacing toward
    its reserve sheds new work before it trips the gate. Both signals are live + derived, not pinned.
    """
    runway = runway or {}
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
        # round so near-equal loads tie and let the refresh-runway signal break the tie.
        return round(assigned.get(v, 0) / b, 3)

    def runway_of(v: str) -> float:
        return runway.get(v, float("inf"))

    # least-loaded by budget ratio; then MOST refresh runway (freshest window); then higher-budget
    # lane; then name (stable).
    return min(candidates, key=lambda v: (load(v), -runway_of(v), -budget.get(v, 0), v))


def _capable_agents(
    task: dict,
    health: dict[str, bool],
    planned_remaining: dict[str, int],
    workdir: Path,
) -> tuple[list[str], dict[str, str]]:
    """The full paid-fleet capability map for one task — kept so the conductor can reach the
    EXTENDED lanes (copilot/github_actions/warp/oz) when no local lane can serve a repo, instead of
    stranding it. Local lanes here are still subject to the budget+runway split via _pick_local."""
    repo = task.get("repo")
    checkout = _local_checkout(repo, workdir)
    has_repo = bool(repo)
    has_issue = task_has_github_issue(task)
    cost = _task_cost(task)
    agents: list[str] = []
    reasons: dict[str, str] = {}

    for agent in PAID_AGENT_ORDER:
        if not health.get(agent):
            continue
        if planned_remaining.get(agent, 0) < cost:
            continue
        if agent in LOCAL_CHECKOUT_AGENTS:
            if checkout is None:
                continue
            agents.append(agent)
            reasons[agent] = f"local checkout at {checkout}"
        elif agent in ISSUE_ASSIGNMENT_AGENTS:
            if not has_issue:
                continue
            agents.append(agent)
            reasons[agent] = "GitHub issue URL -> copilot-swe-agent assignment"
        elif agent == "github_actions":
            if not has_repo:
                continue
            agents.append(agent)
            reasons[agent] = "repo workflow_dispatch via GitHub Actions runner"
        elif agent == "jules":
            if not has_repo:
                continue
            agents.append(agent)
            reasons[agent] = "remote async clone lane"
        elif agent in ("warp", "oz"):
            if not has_repo and checkout is None:
                continue
            agents.append(agent)
            reasons[agent] = "configured paid-service lane"

    return agents, reasons


def route_task(
    task: dict,
    health: dict[str, bool],
    workdir: Path,
    assigned: dict[str, int] | None = None,
    budget: dict[str, int] | None = None,
    runway: dict[str, float] | None = None,
) -> tuple[str, str]:
    """Return (vendor, reason) for one open task.

    Local-first: if a local checkout exists, split across the healthy local lanes by budget + refresh
    runway. Otherwise extend to the full paid fleet (copilot for issues, github_actions, warp/oz),
    and fall back to Jules' remote clone — so a repo with no local copy is never stranded."""
    assigned = assigned if assigned is not None else {}
    budget = budget if budget is not None else {}
    repo = task.get("repo")
    checkout = _local_checkout(repo, workdir)
    if checkout is not None:
        local = _pick_local(task, health, assigned, budget, runway)
        if local:
            return local, f"local checkout at {checkout} -> {local} (split by budget+refresh runway)"
        # local exists but no healthy local lane -> fall through to the extended fleet / jules

    # No (healthy) local lane: reach the extended paid fleet for whatever it can serve.
    planned_remaining = {agent: _task_cost(task) for agent in PAID_AGENT_ORDER}
    agents, _reasons = _capable_agents(task, health, planned_remaining, workdir)
    for agent in agents:
        if agent in LOCAL_CHECKOUT_AGENTS:
            continue  # local lanes were already offered via _pick_local above
        return agent, _reasons[agent]
    if health.get("jules"):
        why = "no local checkout; only Jules clones remotely" if checkout is None \
              else "no healthy local lane; Jules fallback"
        return "jules", why
    return "unroutable", "no reachable capable paid lane"


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
    census = capacity_census(data)
    health = _fleet_health(data)

    # Only route LOCAL lanes the daemon can actually DISPATCH. The dispatchable set is DERIVED from
    # LIMEN_LANES (the same env the heartbeat uses) + jules. This stops stranding tasks on a local
    # lane that's healthy but not in the dispatch rotation (e.g. agy when the launchd plist drops it).
    # Remote/issue lanes (jules/copilot/github_actions/warp/oz) self-dispatch and aren't constrained.
    _lanes_env = os.environ.get("LIMEN_LANES")
    if _lanes_env:
        _dispatchable = {l.strip() for l in _lanes_env.split(",") if l.strip()} | {"jules"}
        health = {
            k: (v and (k in _dispatchable or k not in LOCAL_CHECKOUT_AGENTS))
            for k, v in health.items()
        }

    # Honest routing: never assign work to a lane the LIVE usage meter says is dead — token-exhausted,
    # rate-limited, or at/below the pacing reserve (stop BEFORE 0). Same _down_lanes() the dispatcher
    # skips on, so route and dispatch agree. Self-heals as each lane's window refills.
    _dead = _down_lanes()
    if _dead:
        health = {k: (v and k not in _dead) for k, v in health.items()}

    # The refresh-vs-remaining split signal: hours of runway per lane (live, derived).
    runway = _vendor_runway()

    up = [k for k, v in health.items() if v]
    down = [k for k, v in health.items() if not v]
    print(format_capacity_census(census))
    print(
        f"\n# Router plan  (agents up: {', '.join(up) or 'none'}; "
        f"down: {', '.join(down) or 'none'})\n"
    )

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
        # pass the running tally as the assigned-so-far counts so load spreads across lanes,
        # and the live runway so the split steers toward the freshest refresh window.
        vendor, reason = route_task(t, health, workdir, assigned=tally, budget=budget, runway=runway)
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
