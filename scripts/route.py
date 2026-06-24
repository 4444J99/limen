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
import time
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
from limen.io import load_limen_file, queue_lock, save_limen_file  # noqa: E402
from limen.dispatch import _down_lanes  # noqa: E402


# Vendor health: which local lanes are usable right now. gemini needs an API key.
def _vendor_health() -> dict[str, bool]:
    def has(bin_: str) -> bool:
        return subprocess.run(["which", bin_], capture_output=True).returncode == 0

    def _gemini_settings_has_auth() -> bool:
        # ~/.gemini is another app's data — on macOS TCC the read can be denied. Never crash;
        # a denied/absent read just means "no settings-file auth" (env key is checked first).
        try:
            f = Path.home() / ".gemini" / "settings.json"
            return f.exists() and "auth" in f.read_text(errors="ignore")
        except (PermissionError, OSError):
            return False

    gemini_auth = bool(os.environ.get("GEMINI_API_KEY")) or _gemini_settings_has_auth()
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


def _vendor_cliff_urgency() -> dict[str, float]:
    """Per-vendor 'budget about to EXPIRE unused' pressure, from the live meter (usage.json, written
    by usage-telemetry.py: headroom_pct + time_left_frac). urgency = headroom_frac * (1 - time_left_frac):
    HIGH when a lane has lots of unspent budget AND little time left in its window → drain it FIRST so
    it ships value before the reset wipes the headroom. ~0 early in a window (runway breaks the tie as
    before). Derived from the live signal, never pinned; missing meter → {} → no effect (today's routing)."""
    f = Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen"))) / "logs" / "usage.json"
    try:
        vendors = (json.loads(f.read_text()) or {}).get("vendors", {})
    except (OSError, ValueError):
        return {}
    out: dict[str, float] = {}
    for name, info in vendors.items():
        if not isinstance(info, dict):
            continue
        hp = info.get("headroom_pct")
        tlf = info.get("time_left_frac")
        if isinstance(hp, (int, float)) and isinstance(tlf, (int, float)):
            out[name] = max(0.0, (hp / 100.0) * (1.0 - tlf))
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


def _learned_weights() -> dict[str, float]:
    """Conservative lane weights LEARNED by the self-improve organ — the feedback that closes the
    self-IMPROVE rung (route consumes what improve learned). Read from the proposal the organ already
    writes (logs/self-improve-proposal.json: lane_adjustments[].target_weight). Applied to the local
    split by default now that the ladder is closed — set LIMEN_SI_APPLY=0 to disable (clean rollback).
    Still a no-op until a proposal exists (fail-open below), so the flip is safe before the first run.

    A down-weighted lane gets a proportionally higher effective load (picked less), but every weight
    is floored (LIMEN_SI_WEIGHT_FLOOR, default 0.25) so no lane is ever fully STARVED — it can still
    win work and recover as its later tries succeed. Missing lane -> 1.0 (no effect). Derive-not-pin."""
    if os.environ.get("LIMEN_SI_APPLY", "1") != "1":
        return {}
    floor = float(os.environ.get("LIMEN_SI_WEIGHT_FLOOR", "0.25"))
    try:
        data = json.loads((ROOT / "logs" / "self-improve-proposal.json").read_text())
    except Exception:
        return {}  # no proposal yet / unreadable -> no effect (fail-open to budget+runway split)
    weights: dict[str, float] = {}
    for adj in data.get("lane_adjustments", []):
        lane, w = adj.get("lane"), adj.get("target_weight")
        if lane and isinstance(w, (int, float)):
            weights[lane] = max(floor, min(1.0, float(w)))
    return weights


def _refresh_self_improve_proposal() -> None:
    """Run the self-IMPROVE *producer* at low cadence so its proposal stays fresh for the *consumer*
    (_learned_weights, above) to apply — the other half of the self-improve rung.

    Why it lives here: the live heartbeat loop (scripts/heartbeat-loop.sh) calls route.py every beat
    but has NO separate self-improve step, and the only other caller of scripts/self-improve.py is
    metabolize.sh — which the live loop never invokes (only saturate.sh does). So without this, the
    proposal was never generated in the running system and _learned_weights always fell through to {}
    (the rung was wired into a script the daemon doesn't run). Co-locating the producer in route — the
    organ that already consumes it — keeps the WHOLE rung in the spawned-subprocess layer: route.py is
    re-exec'd fresh each beat, so this deploys on the next sync-release ff with NO loop-body edit and
    NO daemon kickstart (the original design intent for this rung).

    Proposal-only + read-only (self-improve.py never writes tasks.yaml). LIMEN_SI_APPLY=0 disables the
    whole rung (producer + consumer) for a clean rollback; cadence-gated by LIMEN_SI_CADENCE hours so
    most beats are a cheap mtime check; timeout-bounded and FAIL-OPEN — any error just leaves the last
    proposal in place (or none → _learned_weights → {}, today's split) and never blocks routing."""
    if os.environ.get("LIMEN_SI_APPLY", "1") != "1":
        return
    try:
        cadence_h = float(os.environ.get("LIMEN_SI_CADENCE", "10"))
        proposal = ROOT / "logs" / "self-improve-proposal.json"
        if proposal.exists() and (time.time() - proposal.stat().st_mtime) / 3600.0 < cadence_h:
            return  # fresh enough — skip the producer this beat
        script = ROOT / "scripts" / "self-improve.py"
        if not script.exists():
            return
        subprocess.run(
            ["python3", str(script)], cwd=str(ROOT),
            timeout=float(os.environ.get("LIMEN_SI_TIMEOUT", "120")), capture_output=True,
        )
    except Exception:
        return  # fail-open: a stale/absent proposal just means _learned_weights -> {} (no effect)


def _task_classes(task: dict) -> set[str]:
    """The work-classes of one task — its type plus every label. The ledger grades a lane per class,
    so this is the key we look the lane's waste/win record up against."""
    return {c for c in ([task.get("type")] + list(task.get("labels") or [])) if c}


def _ledger_bias(task: dict) -> dict[str, float]:
    """Steer each lane AWAY from the work-classes the value ledger shows it wastes on — derived from
    logs/ledger.json (lanes[lane].waste_classes / .win_classes), so no lane name is pinned and it self-
    corrects as performance changes ([[value-is-discovered-never-assumed]] is the input side; this acts
    on the output side). Returns {lane: floor} for lanes that waste THIS task's class, applied as a low
    weight so the lane is picked far less for that work — but never 0 (floored → never starved), and a
    lane that WINS any of the task's classes is exempt (we don't shed jules's revenue work just because
    it also wastes generic 'code'). Gated by LIMEN_LEDGER_BIAS (default on); fail-open to {} (= today's
    routing) on any missing/torn ledger."""
    if os.environ.get("LIMEN_LEDGER_BIAS", "1") != "1":
        return {}
    floor = float(os.environ.get("LIMEN_LEDGER_BIAS_FLOOR", "0.2"))
    try:
        lanes = json.loads((ROOT / "logs" / "ledger.json").read_text()).get("lanes", {})
    except Exception:
        return {}
    classes = _task_classes(task)
    if not classes:
        return {}
    bias: dict[str, float] = {}
    for lane, d in lanes.items():
        if not isinstance(d, dict):
            continue
        if classes & set(d.get("win_classes") or []):
            continue  # this lane LANDS this kind of work — never shed it
        if classes & set(d.get("waste_classes") or []):
            bias[lane] = floor
    return bias


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

    # learned (self-improve) weights, then ledger bias on top — the ledger sheds a lane from the
    # work-classes it wastes on (opencode off code/build-out here; it still won deploy above). Bias wins.
    weights = {**_learned_weights(), **_ledger_bias(task)}

    def load(v: str) -> float:
        b = budget.get(v, 0) or 1
        # round so near-equal loads tie and let the refresh-runway signal break the tie.
        base = assigned.get(v, 0) / b
        # self-improve nudge: a down-weighted (historically less-shipping) lane carries a higher
        # effective load so it's picked less; floored weight means never fully starved.
        return round(base / weights.get(v, 1.0), 3)

    def runway_of(v: str) -> float:
        return runway.get(v, float("inf"))

    # cliff-urgency: a lane near its reset with unspent budget should DRAIN FIRST (its headroom expires
    # otherwise). Read from the live meter; ~0 away from a cliff, so this only reorders near a reset.
    cliff = _vendor_cliff_urgency()

    def urgency_of(v: str) -> float:
        return cliff.get(v, 0.0)

    # least-loaded by budget ratio; then HIGHEST cliff-urgency (drain expiring budget before reset);
    # then MOST refresh runway (freshest window); then higher-budget lane; then name (stable).
    return min(candidates,
               key=lambda v: (load(v), -urgency_of(v), -runway_of(v), -budget.get(v, 0), v))


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
            reasons[agent] = "GitHub Actions workflow_dispatch via oz-agent-action (Warp cloud agent)"

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

    # No (healthy) local lane: reach the extended paid fleet (jules/copilot/github_actions/warp/oz)
    # for whatever it can serve — DISTRIBUTING across the capable extended lanes by least-assigned-
    # so-far so we never dump the whole remote backlog on one lane (origin's 'don't strand / don't
    # pile on one vendor' lesson, applied to the fan-out). Jules competes here too when it's up.
    planned_remaining = {agent: _task_cost(task) for agent in PAID_AGENT_ORDER}
    agents, reasons = _capable_agents(task, health, planned_remaining, workdir)
    extended = [a for a in agents if a not in LOCAL_CHECKOUT_AGENTS]
    if extended:
        # ledger bias here steers jules off the busywork classes it wastes (coverage/docs/...) while
        # KEEPING it for its winners (revenue/product/ship-now) and for any repo where it's the only
        # capable lane (the penalty only reorders — min() still picks it when it's the sole option, so
        # a no-local-checkout repo is never stranded). [[no-never-happens-again]]
        bias = _ledger_bias(task)
        pick = min(extended, key=lambda a: (1 if bias.get(a, 1.0) < 1.0 else 0,
                                            assigned.get(a, 0), PAID_AGENT_ORDER.index(a)))
        return pick, reasons[pick]
    return "unroutable", "no reachable capable paid lane"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", "tasks.yaml"))
    ap.add_argument("--workdir", default=os.environ.get(
        "LIMEN_WORKDIR", str(Path.home() / "Workspace")))
    ap.add_argument("--apply", action="store_true",
                    help="rewrite target_agent in tasks.yaml (reversible); never dispatches")
    args = ap.parse_args()

    # PRODUCE the self-improve proposal (low cadence) before we CONSUME it in routing below — this is
    # the live home of the improve producer (the heartbeat loop has no separate self-improve step).
    _refresh_self_improve_proposal()

    tasks_path = Path(args.tasks)
    workdir = Path(args.workdir).expanduser()
    # Read through the RESILIENT loader (sanitizes torn writes) instead of raw yaml.safe_load —
    # so route never re-emits / re-encodes the malformed dispatch_log rows that produced the
    # "dispatch_log.*.agent Field required" trace every beat. Decisions run on a (possibly stale)
    # snapshot WITHOUT the lock, because the capacity census/health probes shell out (which/gh) and
    # we must not hold the queue mutex across slow work. The actual write re-reads fresh UNDER the
    # lock below, so we only ever clobber our own target_agent field, never a dispatcher's append.
    data = load_limen_file(tasks_path).model_dump(mode="json", exclude_none=True)
    census = capacity_census(data)
    health = _fleet_health(data)

    # Only route LOCAL lanes the daemon can actually DISPATCH. The dispatchable set is DERIVED from
    # LIMEN_LANES (the same env the heartbeat uses) + jules. This stops stranding tasks on a local
    # lane that's healthy but not in the dispatch rotation (e.g. agy when the launchd plist drops it).
    # Remote/issue lanes (jules/copilot/github_actions/warp/oz) self-dispatch and aren't constrained.
    _lanes_env = os.environ.get("LIMEN_LANES")
    if _lanes_env:
        _dispatchable = {ln.strip() for ln in _lanes_env.split(",") if ln.strip()} | {"jules"}
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
    assignments: dict[str, str] = {}  # task id -> chosen vendor (decisions only; applied under lock)
    for t in opens:
        # pass the running tally as the assigned-so-far counts so load spreads across lanes,
        # and the live runway so the split steers toward the freshest refresh window.
        vendor, reason = route_task(t, health, workdir, assigned=tally, budget=budget, runway=runway)
        tally[vendor] += 1
        print(f"| {t['id']} | {t.get('repo','-')} | {vendor} | {reason} |")
        if vendor not in ("unroutable",):
            assignments[t["id"]] = vendor

    print(f"\nrouted: {dict(tally)}")
    if not args.apply:
        print("dry-run (no changes). re-run with --apply to set target_agent.")
        return 0

    # Apply UNDER the queue lock with a FRESH sanitized re-read, so route stops racing the
    # dispatchers (the race that wrote a Task into a dispatch_log = the torn-write source). We
    # mutate ONLY target_agent on tasks that are still open, then write through the validated
    # save_limen_file (never a raw dump). If the lock is busy, skip this pass — a missed routing
    # write is harmless and self-corrects next beat (never block the beat / never dead-stop).
    with queue_lock(tasks_path) as got:
        if not got:
            print("queue busy — skipped applying target_agent this pass (self-corrects next beat).")
            return 0
        lf = load_limen_file(tasks_path)
        applied = 0
        for task in lf.tasks:
            v = assignments.get(task.id)
            if v and task.status == "open":
                task.target_agent = v
                applied += 1
        save_limen_file(tasks_path, lf)
    print(f"applied target_agent assignments ({applied}) -> {tasks_path} "
          f"(dispatch separately, gated: limen dispatch --agent <v> --live)")
    return 0


def _stamp_health() -> None:
    """Proprioception: record that the ROUTE organ fired this beat, so organ-health.py can read it
    as a fresh artifact (mtime). Fail-open — a missed stamp never blocks routing."""
    try:
        logs = ROOT / "logs"
        logs.mkdir(exist_ok=True)
        (logs / "route-health.json").write_text(
            json.dumps({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n"
        )
    except OSError:
        pass


if __name__ == "__main__":
    rc = main()
    _stamp_health()
    sys.exit(rc)
