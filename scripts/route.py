#!/usr/bin/env python3
"""Paid-agent router — the conductor's missing thin piece.

Assigns each OPEN work-item to a capable AVAILABLE paid service, instead of
dumping the whole backlog on one lane (which is what starved the local fleet on
2026-06-16: 100 tasks all routed to Jules, codex/opencode/agy idle).

Cost model (the "tiering", one level up from model-tiering):
  - Local lanes (codex/opencode/agy/claude/gemini) use a local checkout.
  - Jules is the only lane that clones a remote repo on demand, and runs async in
    parallel. RESERVE it for repos with no local checkout, and for large batches.
  - Copilot assigns an existing GitHub issue to copilot-swe-agent.
  - GitHub Actions triggers a configured workflow_dispatch workflow.
  - Warp/Oz are configurable paid-service lanes via LIMEN_WARP_DISPATCH_CMD and
    LIMEN_OZ_DISPATCH_CMD, or the generic agent-dispatch adapter.
  - Health: a service with no usable auth/CLI/config is skipped.
  - Capacity: every run prints a census of the paid fleet, then round-robins
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
import os
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

try:
    import yaml
except ImportError:
    print("pyyaml required", file=sys.stderr)
    sys.exit(1)


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


def _capable_agents(
    task: dict,
    health: dict[str, bool],
    planned_remaining: dict[str, int],
    workdir: Path,
) -> tuple[list[str], dict[str, str]]:
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


def route_task(task: dict, health: dict[str, bool], workdir: Path) -> tuple[str, str]:
    """Return (vendor, reason) for one open task."""
    planned_remaining = {agent: _task_cost(task) for agent in PAID_AGENT_ORDER}
    agents, reasons = _capable_agents(task, health, planned_remaining, workdir)
    if not agents:
        return "unroutable", "no reachable capable paid lane"
    agent = agents[0]
    return agent, reasons[agent]


def route_tasks(
    tasks: list[dict],
    health: dict[str, bool],
    planned_remaining: dict[str, int],
    workdir: Path,
) -> list[tuple[dict, str, str]]:
    """Route a batch by round-robin across all healthy capable paid lanes."""
    live_order = [agent for agent in PAID_AGENT_ORDER if health.get(agent)]
    cursor = 0
    routed: list[tuple[dict, str, str]] = []

    for task in tasks:
        agents, reasons = _capable_agents(task, health, planned_remaining, workdir)
        if not agents or not live_order:
            routed.append((task, "unroutable", "no reachable capable paid lane"))
            continue

        selected = None
        for offset in range(len(live_order)):
            candidate = live_order[(cursor + offset) % len(live_order)]
            if candidate in agents:
                selected = candidate
                cursor = (cursor + offset + 1) % len(live_order)
                break
        if selected is None:
            selected = agents[0]
            cursor = (live_order.index(selected) + 1) % len(live_order)

        planned_remaining[selected] = max(
            0, planned_remaining.get(selected, 0) - _task_cost(task)
        )
        routed.append((task, selected, reasons[selected]))

    return routed


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
    health = {row["agent"]: bool(row["reachable"]) for row in census}
    planned_remaining = {
        row["agent"]: int(row["remaining"] or 0)
        for row in census
    }

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
    tally: Counter = Counter()
    for t, vendor, reason in route_tasks(opens, health, planned_remaining, workdir):
        tally[vendor] += 1
        print(f"| {t['id']} | {t.get('repo','-')} | {vendor} | {reason} |")
        if args.apply and vendor not in ("unroutable",):
            t["target_agent"] = vendor

    print(f"\nrouted: {dict(tally)}")
    if args.apply:
        tasks_path.write_text(yaml.safe_dump(data, sort_keys=False))
        print(f"applied target_agent assignments -> {tasks_path} "
              f"(dispatch separately, gated: limen dispatch --agent <v> --live)")
    else:
        print("dry-run (no changes). re-run with --apply to set target_agent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
