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
  - Local lanes can clone a repo on demand through dispatch.py, so they are capable
    for any task with a repo. Jules remains the async cloud lane for large batches
    and as a remote fallback, not the only no-checkout escape hatch.
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
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen import census  # noqa: E402
from limen.capacity import (  # noqa: E402
    ISSUE_ASSIGNMENT_AGENTS,
    LOCAL_CHECKOUT_AGENTS,
    PAID_AGENT_ORDER,
    capacity_census,
    derived_floor_from_budget,
    format_capacity_census,
    local_floor_classes,
    local_floor_enabled,
    ollama_model,
    select_lanes,
    task_has_github_issue,
)
from limen.model_selection import _claude_fable_classes, _claude_opus_classes  # noqa: E402
from limen.io import load_limen_file, queue_lock  # noqa: E402
from limen.tabularius import apply_limen_file_sync  # noqa: E402
from limen.dispatch import _down_lanes, _reset_budget_if_needed  # noqa: E402
from limen.workstream import UNASSIGNED, assign_channel  # noqa: E402
from limen.workstream_contract import WORKSTREAM_SUCCESSOR_REQUIRED_LABEL  # noqa: E402


def _route_open_task(task) -> bool:
    """Whether routing may inspect or stamp this open lifecycle row."""
    if isinstance(task, dict):
        status = task.get("status")
        labels = task.get("labels") or []
    else:
        status = task.status
        labels = task.labels or []
    return status == "open" and WORKSTREAM_SUCCESSOR_REQUIRED_LABEL not in labels


# Vendor health: which local lanes are usable right now. gemini needs an API key.
def _vendor_health() -> dict[str, bool]:
    """Fallback health map (used only when capacity_census raises). Lane names + binaries DERIVE
    from the census register (the single vendor umbrella) — the earned local rotation
    (census.lane_cascade()) with each vendor's binary — so this fallback can never drift to a
    different vendor set than the census-backed main path. gemini additionally needs an API key."""

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
    binaries = census.default_binaries()
    health: dict[str, bool] = {}
    for name in census.lane_cascade():  # the local rotation — each lane with a binary to probe
        ok = has(binaries.get(name, name))
        if name == "gemini":
            ok = ok and bool(gemini_auth)
        health[name] = ok
    return health


def _fleet_health(data) -> dict[str, bool]:
    """One health map for the whole capacity registry."""
    try:
        return {str(row["agent"]): bool(row["reachable"]) for row in capacity_census(data)}
    except Exception:
        return _vendor_health()


def _read_usage_vendors() -> dict:
    """Read the LIVE usage meter (logs/usage.json) vendors dict — shared by the runway and
    cliff-urgency readers below so the file path + error handling live in one place. Returns {}
    on any read/parse error (fail-open), never raises. Derived from the live signal, never pinned."""
    f = Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen"))) / "logs" / "usage.json"
    try:
        return (json.loads(f.read_text()) or {}).get("vendors", {})
    except (OSError, ValueError):
        return {}


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _load_limen_for_routing(tasks_path: Path):
    """Load a routing snapshot with budget windows projected forward.

    Route and dispatch must agree on lane availability. Without this projection, a lane such as
    jules can be healthy in live usage telemetry but still look exhausted to capacity_census because
    tasks.yaml has a stale per-agent counter from a prior window.
    """
    lf = load_limen_file(tasks_path)
    _reset_budget_if_needed(lf, _now_utc())
    return lf


def _float_or_default(raw: object, default: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    return _float_or_default(os.environ.get(name), default)


def _vendor_runway() -> dict[str, float]:
    """Per-vendor hours-of-runway from the LIVE usage meter (logs/usage.json, written by
    usage-telemetry.py). This is the refresh-vs-remaining input to the split decision: how long
    until each lane's rolling window is exhausted at the current burn. Missing/None runway (an idle
    lane, burn≈0) reads as +inf — maximally fresh. Derived from the live signal, never pinned."""
    vendors = _read_usage_vendors()
    out: dict[str, float] = {}
    for name, info in vendors.items():
        if not isinstance(info, dict):
            continue
        r = info.get("runway_h")
        out[name] = float("inf") if r is None else _float_or_default(r, float("inf"))
    return out


def _vendor_cliff_urgency() -> dict[str, float]:
    """Per-vendor 'budget about to EXPIRE unused' pressure, from the live meter (usage.json, written
    by usage-telemetry.py: headroom_pct + time_left_frac). urgency = headroom_frac * (1 - time_left_frac):
    HIGH when a lane has lots of unspent budget AND little time left in its window → drain it FIRST so
    it ships value before the reset wipes the headroom. ~0 early in a window (runway breaks the tie as
    before). Derived from the live signal, never pinned; missing meter → {} → no effect (today's routing)."""
    vendors = _read_usage_vendors()
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
    for cand in (workdir / repo, workdir / org / name, workdir / name, cart / org / name, cart / name):
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
_LOCAL_LANES = tuple(agent for agent in PAID_AGENT_ORDER if agent in LOCAL_CHECKOUT_AGENTS)
_REMOTE_BATCH_LANES = ("jules",)


def _learned_weights() -> dict[str, float]:
    """Conservative lane weights LEARNED by the self-improve organ — the feedback that closes the
    self-IMPROVE rung (route consumes what improve learned). Read from the proposal the organ already
    writes (logs/self-improve-proposal.json: lane_adjustments[].target_weight). Applied to the local
    split by default now that the ladder is closed — set LIMEN_SI_APPLY=0 to disable (clean rollback).
    Still a no-op until a proposal exists (fail-open below), so the flip is safe before the first run.

    A down-weighted lane gets a proportionally higher effective load (picked less), while a
    boost-underused lane gets a lower effective load (picked more). We clamp to a floor
    (LIMEN_SI_WEIGHT_FLOOR, default 0.25) and ceiling (LIMEN_SI_WEIGHT_CEILING, default 2.0) so no lane
    is ever fully STARVED or allowed to swamp the fleet. Missing lane -> 1.0 (no effect). Derive-not-pin."""
    if os.environ.get("LIMEN_SI_APPLY", "1") != "1":
        return {}
    floor = max(0.001, _env_float("LIMEN_SI_WEIGHT_FLOOR", 0.25))
    ceiling = max(floor, _env_float("LIMEN_SI_WEIGHT_CEILING", 2.0))
    try:
        data = json.loads((ROOT / "logs" / "self-improve-proposal.json").read_text())
    except Exception:
        return {}  # no proposal yet / unreadable -> no effect (fail-open to budget+runway split)
    weights: dict[str, float] = {}
    for adj in data.get("lane_adjustments", []):
        lane, w = adj.get("lane"), adj.get("target_weight")
        if lane and isinstance(w, (int, float)):
            weights[lane] = max(floor, min(ceiling, float(w)))
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
        cadence_h = _env_float("LIMEN_SI_CADENCE", 10.0)
        proposal = ROOT / "logs" / "self-improve-proposal.json"
        if proposal.exists() and (time.time() - proposal.stat().st_mtime) / 3600.0 < cadence_h:
            return  # fresh enough — skip the producer this beat
        script = ROOT / "scripts" / "self-improve.py"
        if not script.exists():
            return
        subprocess.run(
            ["python3", str(script)],
            cwd=str(ROOT),
            timeout=_env_float("LIMEN_SI_TIMEOUT", 120.0),
            capture_output=True,
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
    floor = max(0.001, _env_float("LIMEN_LEDGER_BIAS_FLOOR", 0.2))
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
    When LIMEN_LANE_FLOORS=1 (default), a lane that is below its derived daily floor gets its
    effective load halved so it sorts before above-floor lanes at similar raw load — preventing
    healthy lanes (e.g. codex at 5/100, jules at 0/100) from idling while others overfill.
    """
    runway = runway or {}
    text = f"{task.get('type', '')} {task.get('title', '')} {task.get('context', '')}".lower()
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

    # Derive floors once per call (not per comparison): each lane's daily floor from its budget cap.
    # LIMEN_LANE_FLOORS=1 (default on) enables the under-floor boost; =0 restores prior ordering.
    floors_enabled = os.environ.get("LIMEN_LANE_FLOORS", "1") == "1"
    floors: dict[str, int] = {}
    if floors_enabled:
        for v in candidates:
            floors[v] = derived_floor_from_budget(v, budget)

    def load(v: str) -> float:
        b = budget.get(v, 0) or 1
        # round so near-equal loads tie and let the refresh-runway signal break the tie.
        base = assigned.get(v, 0) / b
        # self-improve nudge: a down-weighted (historically less-shipping) lane carries a higher
        # effective load so it's picked less; floored weight means never fully starved.
        effective = round(base / weights.get(v, 1.0), 3)
        # under-floor boost: a lane below its daily floor gets half the effective load so it sorts
        # before above-floor lanes — pulling starved healthy lanes into rotation proactively.
        if floors_enabled and floors.get(v, 0) > 0 and assigned.get(v, 0) < floors[v]:
            effective *= 0.5
        return effective

    def runway_of(v: str) -> float:
        return runway.get(v, float("inf"))

    # cliff-urgency: a lane near its reset with unspent budget should DRAIN FIRST (its headroom expires
    # otherwise). Read from the live meter; ~0 away from a cliff, so this only reorders near a reset.
    cliff = _vendor_cliff_urgency()

    def urgency_of(v: str) -> float:
        return cliff.get(v, 0.0)

    # least-loaded by budget ratio; then HIGHEST cliff-urgency (drain expiring budget before reset);
    # then MOST refresh runway (freshest window); then higher-budget lane; then name (stable).
    return min(candidates, key=lambda v: (load(v), -urgency_of(v), -runway_of(v), -budget.get(v, 0), v))


def _pick_repo_worker(
    task: dict,
    health: dict[str, bool],
    assigned: dict[str, int],
    budget: dict[str, int],
    runway: dict[str, float] | None = None,
) -> str | None:
    """Pick from every healthy repo-capable worker that should be actively filled.

    Jules is remote, but it is still repo-capable and has a known daily run budget. Keeping it only
    as a slow/fallback lane leaves 100/day unused while local lanes churn. For ordinary repo work it
    therefore competes with the local pool by the same budget/runway cadence; special deploy work
    still gets opencode first because that is an explicit lane specialization.
    """
    runway = runway or {}
    text = f"{task.get('type', '')} {task.get('title', '')} {task.get('context', '')}".lower()
    if any(h in text for h in _DEPLOY_HINTS) and health.get("opencode"):
        return "opencode"

    candidates = [v for v in _LOCAL_LANES if health.get(v)]
    if os.environ.get("LIMEN_JULES_BATCH_FILL", "1") == "1":
        candidates.extend(v for v in _REMOTE_BATCH_LANES if health.get(v))
    if not candidates:
        return None

    weights = {**_learned_weights(), **_ledger_bias(task)}
    if os.environ.get("LIMEN_REMOTE_BATCH_BIAS", "0") != "1":
        # Batch-fill lanes have an explicit daily utilization target. A historical ledger penalty can
        # still be inspected and re-enabled, but it must not quietly suppress a healthy 100/day lane.
        for lane in _REMOTE_BATCH_LANES:
            weights.pop(lane, None)

    def load(v: str) -> float:
        b = budget.get(v, 0) or 1
        return round((assigned.get(v, 0) / b) / weights.get(v, 1.0), 3)

    def runway_of(v: str) -> float:
        return runway.get(v, float("inf"))

    cliff = _vendor_cliff_urgency()

    def urgency_of(v: str) -> float:
        return cliff.get(v, 0.0)

    return min(candidates, key=lambda v: (load(v), -urgency_of(v), -runway_of(v), -budget.get(v, 0), v))


def _capable_agents(
    task: dict,
    health: dict[str, bool],
    planned_remaining: dict[str, int],
    workdir: Path,
) -> tuple[list[str], dict[str, str]]:
    """The full paid-fleet capability map for one task."""
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
            if not has_repo:
                continue
            agents.append(agent)
            if checkout is not None:
                reasons[agent] = f"local checkout at {checkout}"
            else:
                reasons[agent] = "repo set -> local clone-on-demand"
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


def _existing_assignment_usable(task: dict, agent: str | None, health: dict[str, bool], workdir: Path) -> bool:
    """True when an existing ``target_agent`` can still run this open task.

    Routing uses live usage/runway signals. Recomputing every open row on every beat can otherwise
    reshuffle hundreds of still-valid assignments as telemetry changes by a few tokens, creating board
    churn with no new work. Keep a healthy/capable assignment sticky; route only empty, down, or
    incapable assignments to a new lane.
    """
    if not agent or agent in {"any", "unroutable", "human"}:
        return False
    if not health.get(agent):
        return False

    repo = task.get("repo")
    labels = set(task.get("labels") or [])
    if repo and "slow" in labels and health.get("jules"):
        return agent == "jules"

    if agent == "ollama":
        return _local_floor_lane(task, health) == "ollama"
    if agent in LOCAL_CHECKOUT_AGENTS:
        return bool(repo)
    if agent == "jules":
        return bool(repo)
    if agent in ISSUE_ASSIGNMENT_AGENTS:
        return task_has_github_issue(task)
    if agent == "github_actions":
        return bool(repo)
    if agent in ("warp", "oz"):
        return bool(repo) or _local_checkout(repo, workdir) is not None
    return False


def _local_floor_lane(task: dict, health: dict[str, bool]) -> str | None:
    """Route a cheap mechanical-class task to the unmetered local ollama floor — DARK by default.

    Only fires when LIMEN_LOCAL_FLOOR=1 (the arm is the parity gate's decision — see
    organvm/manumissio; operator rule 2026-07-09: nothing switches over until the math maths)
    AND the floor is actually lit (ollama healthy + a model pulled). Reserved opus/fable classes
    never route local. A class the value ledger has graded wasted on the ollama lane falls back
    automatically (self-correcting rollback, same source as _ledger_bias). Fail-soft: any error
    -> None, i.e. today's routing byte-identical."""
    try:
        if not local_floor_enabled():
            return None
        if not task.get("repo") or not health.get("ollama"):
            return None  # the isolated run needs a worktree; the lane must be up
        classes = _task_classes(task)
        if not classes & local_floor_classes():
            return None
        if classes & (set(_claude_opus_classes()) | set(_claude_fable_classes())):
            return None  # reserved tiers never drop to the floor
        try:
            lanes = json.loads((ROOT / "logs" / "ledger.json").read_text()).get("lanes", {})
            if classes & set((lanes.get("ollama") or {}).get("waste_classes") or []):
                return None
        except Exception:
            pass  # no ledger yet -> no rollback signal
        if ollama_model() is None:
            return None
        return "ollama"
    except Exception:
        return None


def route_task(
    task: dict,
    health: dict[str, bool],
    workdir: Path,
    assigned: dict[str, int] | None = None,
    budget: dict[str, int] | None = None,
    runway: dict[str, float] | None = None,
) -> tuple[str, str]:
    """Return (vendor, reason) for one open task.

    Local-first: if a repo exists, split across the healthy local lanes by budget + refresh runway.
    dispatch.py clones on demand when no checkout exists. If no local lane is available, extend to
    the full paid fleet (copilot for issues, github_actions, warp/oz, Jules)."""
    assigned = assigned if assigned is not None else {}
    budget = budget if budget is not None else {}
    repo = task.get("repo")
    checkout = _local_checkout(repo, workdir)
    # ASYNC SIGNAL first: a task that already TIMED OUT on a wall-clock-bound sync local lane carries
    # the "slow" label (dispatch.py's timeout->jules path, which also sets target_agent=jules). A local
    # sync lane BLOCKS the beat and would just time it out AGAIN, then retarget it back to jules — an
    # infinite loop where jules never actually runs (verified: a slow, jules-pinned task cycled
    # agy->opencode->codex with ZERO `jules remote` sessions launched, because this local-first router
    # stole the jules retarget every beat). Honor the signal: send a slow task straight to the async
    # remote lane (jules, no wall-clock cap) whenever it is healthy; only fall through to a local lane
    # if jules is down (never strand — [[no-never-happens-again]]).
    if repo and "slow" in set(task.get("labels") or []) and health.get("jules"):
        return "jules", "slow (timed out on a sync local lane) -> jules async remote (no wall-clock cap)"
    floor = _local_floor_lane(task, health)
    if floor:
        return floor, "local floor class -> ollama (unmetered; armed by parity gate)"
    if repo:
        lane = _pick_repo_worker(task, health, assigned, budget, runway)
        if lane:
            if lane == "jules":
                return lane, "repo set -> jules remote async clone (split by budget+refresh runway)"
            if checkout is not None:
                return lane, f"local checkout at {checkout} -> {lane} (split by budget+refresh runway)"
            return lane, f"repo set -> {lane} clone-on-demand (split by budget+refresh runway)"
        # repo exists but no healthy local lane -> fall through to the extended fleet / jules

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
        pick = min(
            extended, key=lambda a: (1 if bias.get(a, 1.0) < 1.0 else 0, assigned.get(a, 0), PAID_AGENT_ORDER.index(a))
        )
        return pick, reasons[pick]
    return "unroutable", "no reachable capable paid lane"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", "tasks.yaml"))
    ap.add_argument("--workdir", default=os.environ.get("LIMEN_WORKDIR", str(Path.home() / "Workspace")))
    ap.add_argument(
        "--apply", action="store_true", help="rewrite target_agent in tasks.yaml (reversible); never dispatches"
    )
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
    data = _load_limen_for_routing(tasks_path).model_dump(mode="json", exclude_none=True)
    census = capacity_census(data)
    health = _fleet_health(data)

    # Honest routing: never assign work to a lane the LIVE usage meter says is dead — token-exhausted,
    # rate-limited, or at/below the pacing reserve (stop BEFORE 0). Same _down_lanes() the dispatcher
    # skips on, so route and dispatch agree. Self-heals as each lane's window refills.
    _dead = _down_lanes()
    if _dead:
        health = {k: (v and k not in _dead) for k, v in health.items()}

    selector = os.environ.get("LIMEN_DISPATCH_LANES", "auto")
    dispatchable = set(select_lanes(selector, data, down_lanes=_dead))
    health = {k: (v and k in dispatchable) for k, v in health.items()}

    # The refresh-vs-remaining split signal: hours of runway per lane (live, derived).
    runway = _vendor_runway()

    up = [k for k, v in health.items() if v]
    down = [k for k, v in health.items() if not v]
    print(format_capacity_census(census))
    print(f"\n# Router plan  (agents up: {', '.join(up) or 'none'}; down: {', '.join(down) or 'none'})\n")

    opens = [t for t in data["tasks"] if _route_open_task(t)]
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
        current = str(t.get("target_agent") or "")
        if _existing_assignment_usable(t, current, health, workdir):
            vendor = current
            reason = f"existing target_agent {current} is still healthy/capable (sticky route)"
        else:
            vendor, reason = route_task(t, health, workdir, assigned=tally, budget=budget, runway=runway)
        tally[vendor] += 1
        print(f"| {t['id']} | {t.get('repo', '-')} | {vendor} | {reason} |")
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
        _reset_budget_if_needed(lf, _now_utc())
        applied = 0
        ws_applied = 0
        for task in lf.tasks:
            if not _route_open_task(task):
                continue
            v = assignments.get(task.id)
            if v and task.target_agent != v:
                task.target_agent = v
                applied += 1
            # PURPOSE partition (workstream) — the axis ABOVE target_agent, without which the
            # channels organ's scoped `cell conduct --workstream <handle>` conductors draw an empty
            # lane. Stamp only when EMPTY (honor explicit intent) and only a RESOLVED channel (leave
            # UNASSIGNED as None so it re-derives next beat when new signal appears). Same lock, same
            # fresh re-read, same validated save — a sibling of the vendor assignment above.
            if not task.workstream:
                handle = assign_channel(task, ROOT)
                if handle != UNASSIGNED:
                    task.workstream = handle
                    ws_applied += 1
        apply_limen_file_sync(tasks_path, lf, agent="route", session_id="route-apply")
    print(
        f"applied target_agent assignments ({applied}) -> {tasks_path} "
        f"(dispatch separately, gated: limen dispatch --agent <v> --live)"
    )
    print(f"applied workstream assignments ({ws_applied}) -> {tasks_path} (purpose partition)")
    return 0


def _stamp_health() -> None:
    """Proprioception: record that the ROUTE organ fired this beat, so organ-health.py can read it
    as a fresh artifact (mtime). Fail-open — a missed stamp never blocks routing."""
    try:
        logs = ROOT / "logs"
        logs.mkdir(exist_ok=True)
        (logs / "route-health.json").write_text(json.dumps({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
    except OSError:
        pass


if __name__ == "__main__":
    rc = main()
    _stamp_health()
    sys.exit(rc)
