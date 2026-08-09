#!/usr/bin/env python3
"""handoff-relay — the seam-survival organ.

The 84-ask overnight/walk-away loop kept dying at every session/vendor/beat seam because each
pickup cold-derived the world from scratch (retro 2026-07-08, finding 3). This writes one compact,
PII-clean ``logs/handoff.json`` every beat and at SessionEnd, so the NEXT session/vendor/beat
resumes WARM: it knows the open lanes, the in-flight claims, the last blocker, authoritative board
budget, timestamped provider headroom, and both the ostensible and actually dispatchable next task.
``session-orient`` injects it at SessionStart.

  write   (default)   recompute logs/handoff.json from the live board + beat state
  --check             predicate: exit 0 iff a FRESH, complete handoff exists (a warm resume is
                      possible); non-zero otherwise. This is the done.sh for the walk-away loop.
  --print             emit the current handoff as a short human/agent-readable block (for orient)

Fail-open and beat-safe: a missing source degrades a field to null, never crashes the beat.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

CODE_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("LIMEN_ROOT", CODE_ROOT))
sys.path.insert(0, str(CODE_ROOT / "cli" / "src"))

from limen.capacity import PAID_AGENT_ORDER, agent_status, canonical_agent  # noqa: E402
from limen.dispatch import (
    _down_lanes,
    _effective_target_agent,
    _weak_proxy_exhaustion,
    _window_hours,
    agent_can_run_task,
)  # noqa: E402
from limen.models import Task  # noqa: E402
from limen.progress_selection import HOLD_LABELS  # noqa: E402
from limen.runtime_requirements import task_execution_ready  # noqa: E402
from limen.work_loan import task_work_loan_readiness  # noqa: E402
from limen.workstream_contract import WORKSTREAM_SUCCESSOR_REQUIRED_LABEL  # noqa: E402

# One reason code per canonical hold label; a label added to HOLD_LABELS without a
# name here still gates admission (generic "hold_label") instead of silently passing.
_HOLD_LABEL_REASONS = {
    "needs-human": "human_gate",
    "operator-paused": "operator_paused",
    WORKSTREAM_SUCCESSOR_REQUIRED_LABEL: "successor_required",
}

# These are control-plane failure sentinels, not provider identities. Treating them as
# unknown-but-healthy providers would turn a failed route derivation into dispatchable work.
_PLAN_BUILDER_SENTINELS = frozenset({
    "__plan_builder_invalid__",
    "__plan_builder_unavailable__",
})

HANDOFF = ROOT / "logs" / "handoff.json"
TASKS = Path(os.environ.get("LIMEN_TASKS") or ROOT / "tasks.yaml")
USAGE = ROOT / "logs" / "usage.json"
SELF_HEAL = ROOT / "logs" / "self-heal.log"
OVERNIGHT = ROOT / "logs" / "overnight-watch.out.log"
FRESH_MAX_MINUTES = 90  # a handoff older than this is stale — the seam went cold

_PRIORITY = {"critical": 0, "high": 1, "medium": 2, "low": 3, "backlog": 4}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _load_board() -> dict[str, Any]:
    try:
        import yaml
    except Exception:
        return {}
    try:
        board = yaml.safe_load(TASKS.read_text())
    except Exception:
        return {}
    return board if isinstance(board, dict) else {}


def _load_tasks(board: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    board = _load_board() if board is None else board
    if not isinstance(board, dict):
        return []
    tasks = board.get("tasks", board)
    if isinstance(tasks, dict):
        tasks = list(tasks.values())
    return [t for t in (tasks or []) if isinstance(t, dict)]


def _open_lanes(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """Open work grouped by lane (workstream, falling back to target_agent). The next session
    knows which lanes have fuel without re-reading the whole board."""
    lanes: Counter[str] = Counter()
    for t in tasks:
        if t.get("status") != "open":
            continue
        lane = str(t.get("workstream") or t.get("target_agent") or "unassigned")
        lanes[lane] += 1
    return {"total_open": sum(lanes.values()), "by_lane": dict(lanes.most_common(12))}


def _in_flight(tasks: list[dict[str, Any]], now: dt.datetime) -> dict[str, Any]:
    """Tasks a lane has claimed (dispatched / in_progress) with age — so a resume doesn't
    double-claim, and a STALE claim (owner died mid-work) is visible for release."""
    claims = []
    for t in tasks:
        if t.get("status") not in {"dispatched", "in_progress"}:
            continue
        updated = str(t.get("updated") or "")
        age_h = None
        try:
            when = dt.datetime.fromisoformat(updated.replace("Z", "+00:00"))
            age_h = round((now - when).total_seconds() / 3600, 1)
        except Exception:
            pass
        agent = ""
        for e in reversed(t.get("dispatch_log") or []):
            if e.get("agent"):
                agent = str(e.get("agent"))
                break
        claims.append({"id": t.get("id"), "agent": agent, "status": t.get("status"), "age_h": age_h})
    stale = [c for c in claims if isinstance(c["age_h"], (int, float)) and c["age_h"] > 2]
    return {"count": len(claims), "stale": len(stale), "claims": sorted(claims, key=lambda c: -(c["age_h"] or 0))[:12]}


def _last_blocker(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """The freshest thing standing in the way: a failed task, or the heal-lane pressure line."""
    failed = [t for t in tasks if t.get("status") in {"failed", "failed_blocked"}]
    needs_human = sum(1 for t in tasks if t.get("status") == "needs_human")
    heal_line = None
    try:
        lines = [ln for ln in SELF_HEAL.read_text().splitlines() if ln.startswith("[self-heal]")]
        if lines:
            heal_line = lines[-1].split("|")[0].strip()[:160]
    except Exception:
        pass
    newest_failed = None
    if failed:
        newest_failed = sorted(failed, key=lambda t: str(t.get("updated") or ""), reverse=True)[0]
        newest_failed = {"id": newest_failed.get("id"), "title": str(newest_failed.get("title", ""))[:80]}
    return {
        "failed_count": len(failed),
        "needs_human_count": needs_human,
        "newest_failed": newest_failed,
        "heal_pressure": heal_line,
    }


def _live_down_lanes() -> list[str]:
    """Snapshot the dispatcher's live lane gates for truthful admission reporting.

    This calls the dispatcher-owned union: manual lanes-down entries, usage
    exhaustion, browser-OAuth preflight, and provider-outcome health must not
    acquire a second handoff-only implementation.
    """
    try:
        return sorted(
            {
                canonical_agent(str(agent))
                for agent in _down_lanes()
                if str(agent).strip() and canonical_agent(str(agent)) not in {"", "any"}
            }
        )
    except Exception:
        # A broken probe must not crash a beat; provider rows remain authoritative.
        return []


def _lane_reachable(agent: str, provider_headroom: dict[str, Any]) -> bool:
    """Return live reachability for a candidate lane.

    Fresh handoffs carry the dispatcher-owned reachability bit beside each usage row. Older
    handoffs and hermetic unit fixtures may omit it; a present usage row remains a valid legacy
    snapshot, while a lane absent from telemetry must prove reachability through the capacity
    registry instead of inheriting the static roster's optimistic default.
    """
    vendors = provider_headroom.get("vendors") if isinstance(provider_headroom, dict) else {}
    value = vendors.get(agent) if isinstance(vendors, dict) else None
    if isinstance(value, dict):
        if "reachable" in value:
            return bool(value["reachable"])
        return True
    try:
        return bool(agent_status(agent).get("reachable"))
    except Exception:
        return False


def _provider_headroom() -> dict[str, Any]:
    """Timestamped provider capacity from the owning usage receipt."""
    usage = _load_json(USAGE, {})
    generated = None
    vendors: dict[str, Any] = {}
    if isinstance(usage, dict):
        generated = usage.get("generated") or usage.get("generated_at")
        raw_vendors = usage.get("vendors")
        if isinstance(raw_vendors, dict):
            for name, value in list(raw_vendors.items())[:20]:
                if isinstance(value, dict):
                    projected = {
                        key: value.get(key)
                        for key in (
                            "remaining",
                            "spent",
                            "consumed",
                            "state",
                            "status",
                            "health",
                            "headroom_pct",
                            "effective_reserve_pct",
                            # Provider-health receipts are the live admission signal. Keep
                            # them beside ordinary usage headroom instead of silently dropping
                            # auth failures/cooldowns on the way into the handoff.
                            "provider_outcome_health",
                            "provider_cooldown_count",
                            "provider_last_success",
                            "provider_last_terminal_failure",
                            "provider_cooldown_expiry",
                            "provider_health_snapshot_hash",
                            "provider_outcome_all_blocked",
                            "provider_outcome_provider_count",
                            "provider_outcome_blocked_provider_count",
                            "provider_outcome_model_count",
                            "provider_outcome_blocked_model_count",
                        )
                        if key in value
                    }
                    reset_at = value.get("resets_at", value.get("reset_at"))
                    if reset_at is not None:
                        projected["resets_at"] = reset_at
                    # A usage row alone is not a capability census: preserve the live dispatcher
                    # reachability result so the any-task roster cannot route into a missing binary,
                    # workflow, or unauthenticated hosted lane.
                    try:
                        projected["reachable"] = bool(
                            agent_status(canonical_agent(str(name))).get("reachable")
                        )
                    except Exception:
                        projected["reachable"] = False
                    vendors[str(name)] = projected
    return {"generated": generated, "vendors": vendors, "down_lanes": _live_down_lanes()}


def _legacy_budget(provider_headroom: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible overnight gauge retained for existing handoff consumers."""
    out: dict[str, Any] = {
        "overnight_spent": None,
        "overnight_cap": None,
        "vendors": dict(provider_headroom.get("vendors") or {}),
    }
    try:
        for line in reversed(OVERNIGHT.read_text().splitlines()):
            if "spent=" not in line:
                continue
            fragment = line.split("spent=", 1)[1].split()[0]
            spent, cap = fragment.split("/")
            out["overnight_spent"], out["overnight_cap"] = int(spent), int(cap)
            out["overnight_remaining"] = int(cap) - int(spent)
            break
    except Exception:
        pass
    return out


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _reset_window_active(agent: str, reset_at: Any, now: dt.datetime) -> bool:
    """Whether a stale board counter still belongs to the lane's active reset window."""
    if not reset_at:
        return False
    try:
        stamp = dt.datetime.fromisoformat(str(reset_at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    try:
        window_hours = _window_hours(agent)
    except Exception:
        window_hours = 24.0
    return now < stamp + dt.timedelta(hours=float(window_hours))


def _board_budget(board: dict[str, Any]) -> dict[str, Any]:
    """Authoritative budget from ``tasks.yaml`` rather than the overnight log proxy."""
    portal = board.get("portal") if isinstance(board, dict) else None
    budget = portal.get("budget") if isinstance(portal, dict) else None
    budget = budget if isinstance(budget, dict) else {}
    track = budget.get("track") if isinstance(budget.get("track"), dict) else {}
    caps = budget.get("per_agent") if isinstance(budget.get("per_agent"), dict) else {}
    spent_by = track.get("per_agent") if isinstance(track.get("per_agent"), dict) else {}
    reset_by = track.get("per_agent_reset") if isinstance(track.get("per_agent_reset"), dict) else {}
    track_date = str(track.get("date") or "")
    # Dispatch refreshes the budget clock before admission. If the projection
    # still carries an earlier date, discard its expired counters rather than
    # explaining the current beat with yesterday's exhaustion.
    now = _now()
    current_date = now.date().isoformat()
    if track_date != current_date:
        # The board date is only a projection stamp. Dispatch resets each lane on its own
        # cadence, so preserve a counter whose per-agent window has not actually elapsed.
        active_spent = {
            str(name): value
            for name, value in spent_by.items()
            if _reset_window_active(str(name), reset_by.get(name), now)
        }
        spent_by = active_spent
        track_spent = sum(_as_int(value) or 0 for value in spent_by.values())
    else:
        track_spent = _as_int(track.get("spent"))
    daily = _as_int(budget.get("daily"))
    spent = track_spent
    global_remaining = max(0, daily - spent) if daily is not None and spent is not None else None
    agents: dict[str, Any] = {}
    for name in sorted(set(caps) | set(spent_by) | set(reset_by)):
        cap = _as_int(caps.get(name))
        agent_spent = _as_int(spent_by.get(name)) or 0
        remaining = global_remaining
        if cap is not None:
            cap_remaining = max(0, cap - agent_spent)
            remaining = cap_remaining if remaining is None else min(remaining, cap_remaining)
        agents[str(name)] = {
            "cap": cap,
            "spent": agent_spent,
            "remaining": remaining,
            "reset_at": reset_by.get(name),
        }
    return {
        "daily": daily,
        "unit": budget.get("unit"),
        "track_date": track.get("date"),
        "spent": spent,
        "remaining": global_remaining,
        "per_agent": agents,
    }


def _task_summary(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task.get("id"),
        "title": str(task.get("title", ""))[:90],
        "repo": task.get("repo"),
        "agent": task.get("target_agent"),
        "priority": task.get("priority"),
    }


def _ostensible_next(tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Highest-priority open row with no admission interpretation."""
    candidates = [task for task in tasks if task.get("status") == "open"]
    if not candidates:
        return None
    top = sorted(
        candidates,
        key=lambda task: (_PRIORITY.get(str(task.get("priority")), 9), str(task.get("id"))),
    )[0]
    return _task_summary(top)


def _has_terminal_transition(task: dict[str, Any]) -> bool:
    for entry in task.get("dispatch_log") or []:
        if isinstance(entry, dict) and str(entry.get("status") or "") in {"done", "archived", "pr_open"}:
            return True
    return False


def _dependency_merged(task: dict[str, Any] | None) -> bool:
    if not isinstance(task, dict):
        return False
    for entry in task.get("dispatch_log") or []:
        if not isinstance(entry, dict):
            continue
        text = f"{entry.get('status') or ''} {entry.get('output') or ''}".lower()
        if "merged" in text:
            return True
    return False


def _effective_task_agent(task: dict[str, Any]) -> str:
    """Resolve the provider that dispatch will actually execute, without mutating ownership."""
    try:
        return _effective_target_agent(Task.model_validate(task))
    except Exception:
        # Historical fixture rows may omit required Task fields; still honor their latest
        # explicit route receipt rather than falling back to the stale target_agent.
        for entry in reversed(task.get("dispatch_log") or []):
            if not isinstance(entry, dict):
                continue
            if str(entry.get("status") or "") == "open" and entry.get("route_to"):
                return canonical_agent(str(entry["route_to"]))
        return canonical_agent(str(task.get("target_agent") or ""))


def _provider_block_reason(agent: str, provider_headroom: dict[str, Any]) -> str | None:
    """Return the dispatch-relevant reason for a measured provider block.

    Usage telemetry carries ordinary budget/health fields and a provider-outcome receipt.
    The latter is deliberately interpreted here: a lane in an auth-failure cooldown is not
    merely health=ok with a stale usage row, and should never be advertised as routable.
    Missing rows remain available because unmetered lanes are intentionally absent from the
    usage-budget projection; capability admission is the next gate for those lanes.
    """
    if agent in {"", "any"}:
        return None
    vendors = provider_headroom.get("vendors")
    value = vendors.get(agent) if isinstance(vendors, dict) else None
    if not isinstance(value, dict):
        return None  # unknown is not the same as measured-down

    down_lanes = provider_headroom.get("down_lanes")
    if isinstance(down_lanes, (list, tuple, set)) and agent in {
        canonical_agent(str(lane)) for lane in down_lanes
    }:
        return "provider_health"

    # Dispatch deliberately exempts Agy's board-derived dispatch-count proxy from hard-down
    # treatment; only a real rate-limit signal benches that lane. Keep this report aligned with
    # that exemption so a healthy Agy task is not mislabeled provider_health/capacity_blocked.
    if _weak_proxy_exhaustion(agent, value):
        return None

    ordinary_states = {
        str(value.get(key) or "").strip().lower().replace("-", "_")
        for key in ("health", "state", "status")
    }
    auth_markers = {
        "auth",
        "auth_needed",
        "auth_blocked",
        "auth_failure",
        "authentication",
        "unauthenticated",
        "unauthorized",
        "credentials",
        "credential",
        "login_required",
    }
    if any(
        marker in state or "auth" in state or "credential" in state
        for state in ordinary_states
        for marker in auth_markers
    ):
        return "auth_blocked"
    if ordinary_states & {
        "down",
        "disabled",
        "exhausted",
        "low",
        "rate_limited",
        "unavailable",
        "blocked",
    }:
        return "provider_health"

    remaining = value.get("remaining")
    if isinstance(remaining, (int, float)) and not isinstance(remaining, bool) and remaining <= 0:
        return "provider_health"

    # Provider telemetry aggregates model/provider entries. Match dispatch's
    # all-provider gate: a cooldown on one model is not a whole-lane outage.
    if value.get("provider_outcome_all_blocked") is True:
        outcome_states = {
            str(value.get(key) or "").strip().lower().replace("-", "_")
            for key in ("provider_outcome_health", "provider_last_terminal_failure")
        }
        if any(
            marker in state or "auth" in state or "credential" in state
            for state in outcome_states
            for marker in auth_markers
        ):
            return "auth_blocked"
        return "provider_health"
    return None


def _provider_available(agent: str, provider_headroom: dict[str, Any]) -> bool:
    return _provider_block_reason(agent, provider_headroom) is None



def _eligible_any_agent(task: dict[str, Any], agent: str) -> bool:
    """Use the dispatcher's own capability contract for every candidate lane."""
    try:
        return agent_can_run_task(agent, Task.model_validate(task))
    except Exception:
        # A malformed historical row is not evidence that any lane can execute it.
        return False


def _dispatch_admission(
    tasks: list[dict[str, Any]],
    board_budget: dict[str, Any],
    provider_headroom: dict[str, Any],
) -> dict[str, Any]:
    """Explain the same stable gates that make an open task broker-admissible.

    Admission itself reads this handoff, so the relay cannot recursively launch the admission
    subprocess. Each open row receives one primary reason in deterministic gate order.
    """
    by_id = {str(task.get("id")): task for task in tasks if task.get("id")}
    global_remaining = _as_int(board_budget.get("remaining"))
    per_agent = board_budget.get("per_agent") if isinstance(board_budget.get("per_agent"), dict) else {}
    candidates: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    provider_health_reasons: Counter[str] = Counter()
    down_lanes = {
        canonical_agent(str(agent))
        for agent in (provider_headroom.get("down_lanes") or [])
        if str(agent).strip() and canonical_agent(str(agent)) not in {"", "any"}
    }
    admissible_agents: Counter[str] = Counter()
    admissible_any_agents: Counter[str] = Counter()
    raw_vendors = provider_headroom.get("vendors") if isinstance(provider_headroom, dict) else {}
    # Usage telemetry is a metered-budget view. The dispatcher can also claim canonical
    # unmetered lanes (for example github_actions, Ollama, Copilot, Warp, or Oz), so any-task
    # admission starts from the capability census and only overlays measured provider rows.
    known_agents = sorted(
        {
            canonical_agent(str(name))
            for name in [*PAID_AGENT_ORDER, *(raw_vendors or {})]
            if str(name).strip() and canonical_agent(str(name)) not in {"", "any"}
        }
    )
    for task in tasks:
        if task.get("status") != "open":
            continue
        reason: str | None = None
        if _has_terminal_transition(task):
            reason = "terminal_history"
        labels = {str(label) for label in task.get("labels") or []}
        held = labels & HOLD_LABELS
        if reason is None and held:
            reason = _HOLD_LABEL_REASONS.get(min(held), "hold_label")
        deps = [str(value) for value in task.get("depends_on") or []]
        if reason is None and any(not _dependency_merged(by_id.get(dep)) for dep in deps):
            reason = "dependencies"
        underwriting = task_work_loan_readiness(task)
        if reason is None and not underwriting.ready:
            reason = str(underwriting.reason_code)
        cost = _as_int(task.get("budget_cost")) or 1
        if reason is None and global_remaining is not None and cost > global_remaining:
            reason = "budget_global"
        agent = _effective_task_agent(task)
        if reason is None and agent in _PLAN_BUILDER_SENTINELS:
            reason = "admission_blocked"
        if reason is None and agent in down_lanes:
            reason = "provider_health"
        if reason is None and agent not in {"", "any"} and not _lane_reachable(agent, provider_headroom):
            reason = "provider_health"
        if reason is None and agent not in {"", "any"} and not _eligible_any_agent(task, agent):
            reason = "admission_blocked"
        agent_budget = per_agent.get(agent) if isinstance(per_agent, dict) else None
        agent_remaining = _as_int(agent_budget.get("remaining")) if isinstance(agent_budget, dict) else None
        if reason is None and agent_remaining is not None and cost > agent_remaining:
            reason = "budget_agent"
        if reason is None:
            reason = _provider_block_reason(agent, provider_headroom)
        if reason is None and not task_execution_ready(task):
            reason = "execution_requirements"
        if reason is not None:
            reasons[reason] += 1
            if reason in {"provider_health", "auth_blocked"}:
                provider_health_reasons[agent] += 1
            continue
        if agent in {"", "any"}:
            eligible_any_agents = 0
            any_blockers: Counter[str] = Counter()
            for candidate_agent in known_agents:
                candidate_budget = per_agent.get(candidate_agent) if isinstance(per_agent, dict) else None
                candidate_remaining = (
                    _as_int(candidate_budget.get("remaining"))
                    if isinstance(candidate_budget, dict)
                    else None
                )
                if candidate_remaining is not None and cost > candidate_remaining:
                    any_blockers["budget_agent"] += 1
                    continue
                if candidate_agent in down_lanes:
                    any_blockers["provider_health"] += 1
                    provider_health_reasons[candidate_agent] += 1
                    continue
                if not _lane_reachable(candidate_agent, provider_headroom):
                    any_blockers["provider_health"] += 1
                    provider_health_reasons[candidate_agent] += 1
                    continue
                provider_reason = _provider_block_reason(candidate_agent, provider_headroom)
                if provider_reason is not None:
                    any_blockers[provider_reason] += 1
                    if provider_reason in {"provider_health", "auth_blocked"}:
                        provider_health_reasons[candidate_agent] += 1
                    continue
                if not _eligible_any_agent(task, candidate_agent):
                    any_blockers["admission_blocked"] += 1
                    continue
                admissible_any_agents[candidate_agent] += 1
                eligible_any_agents += 1
            if eligible_any_agents == 0:
                # Preserve the strongest observed cause so conducting-report can distinguish
                # auth/capacity blocks from a genuinely unavailable capability route.
                for blocker in ("auth_blocked", "provider_health", "budget_agent", "admission_blocked"):
                    if any_blockers.get(blocker):
                        reasons[blocker] += 1
                        break
                else:
                    reasons["admission_blocked"] += 1
                continue
        candidates.append(task)
        admissible_agents[agent or "any"] += 1
    top = (
        sorted(
            candidates,
            key=lambda task: (_PRIORITY.get(str(task.get("priority")), 9), str(task.get("id"))),
        )[0]
        if candidates
        else None
    )
    open_count = sum(task.get("status") == "open" for task in tasks)
    return {
        "schema_version": "limen.dispatch_admission.v1",
        "open_considered": open_count,
        "admissible": len(candidates),
        "gated": open_count - len(candidates),
        "reason_counts": dict(sorted(reasons.items())),
        "provider_health_reason_counts": dict(sorted(provider_health_reasons.items())),
        "down_lanes": sorted(down_lanes),
        "admissible_agent_counts": dict(sorted(admissible_agents.items())),
        "admissible_any_agent_counts": dict(sorted(admissible_any_agents.items())),
        "dispatchable_next": _task_summary(top) if top else None,
    }


def _dispatchable_next(
    tasks: list[dict[str, Any]],
    board_budget: dict[str, Any],
    provider_headroom: dict[str, Any],
) -> dict[str, Any] | None:
    return _dispatch_admission(tasks, board_budget, provider_headroom)["dispatchable_next"]


def build() -> dict[str, Any]:
    now = _now()
    board = _load_board()
    tasks = _load_tasks(board)
    provider_headroom = _provider_headroom()
    board_budget = _board_budget(board)
    ostensible_next = _ostensible_next(tasks)
    dispatch_admission = _dispatch_admission(tasks, board_budget, provider_headroom)
    dispatchable_next = dispatch_admission["dispatchable_next"]
    return {
        "generated": now.isoformat(timespec="seconds"),
        "open_lanes": _open_lanes(tasks),
        "in_flight_claims": _in_flight(tasks, now),
        "last_blocker": _last_blocker(tasks),
        "board_budget": board_budget,
        "provider_headroom": provider_headroom,
        "ostensible_next": ostensible_next,
        "dispatchable_next": dispatchable_next,
        "dispatch_admission": dispatch_admission,
        # Compatibility aliases for consumers deployed before the truthful split.
        "budget_remaining": _legacy_budget(provider_headroom),
        "next_action": dispatchable_next,
    }


def write() -> int:
    HANDOFF.parent.mkdir(parents=True, exist_ok=True)
    payload = build()
    tmp = HANDOFF.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True))
    tmp.replace(HANDOFF)
    na = payload["dispatchable_next"]
    print(
        f"handoff-relay: wrote {HANDOFF.name} — open={payload['open_lanes']['total_open']} "
        f"in_flight={payload['in_flight_claims']['count']} "
        f"next={(na or {}).get('id', 'none')}"
    )
    return 0


def check() -> int:
    """Done predicate: a fresh, complete handoff exists ⟺ a warm resume is possible."""
    data = _load_json(HANDOFF, None)
    if not isinstance(data, dict):
        print("handoff-relay --check: FAIL — no handoff.json (seam would be cold)")
        return 1
    try:
        age_min = (_now() - dt.datetime.fromisoformat(str(data["generated"]))).total_seconds() / 60
    except Exception:
        print("handoff-relay --check: FAIL — unparseable timestamp")
        return 1
    if age_min > FRESH_MAX_MINUTES:
        print(f"handoff-relay --check: FAIL — stale ({age_min:.0f}m > {FRESH_MAX_MINUTES}m); seam went cold")
        return 1
    for field in (
        "open_lanes",
        "in_flight_claims",
        "last_blocker",
        "budget_remaining",
        "board_budget",
        "provider_headroom",
        "ostensible_next",
        "dispatchable_next",
        "dispatch_admission",
    ):
        if field not in data:
            print(f"handoff-relay --check: FAIL — missing '{field}'")
            return 1
    provider = data.get("provider_headroom")
    try:
        provider_generated = dt.datetime.fromisoformat(str(provider["generated"]))
        provider_age_min = (_now() - provider_generated).total_seconds() / 60
    except Exception:
        print("handoff-relay --check: FAIL — provider headroom timestamp missing or unparseable")
        return 1
    if provider_age_min > FRESH_MAX_MINUTES:
        print(f"handoff-relay --check: FAIL — provider headroom stale ({provider_age_min:.0f}m > {FRESH_MAX_MINUTES}m)")
        return 1
    na = (
        (data.get("dispatchable_next") or {}).get("id")
        if data.get("dispatchable_next")
        else "none(gated or board drained)"
    )
    print(f"handoff-relay --check: OK — fresh ({age_min:.0f}m), warm resume ready; next={na}")
    return 0


def render(data: dict[str, Any]) -> str:
    if not isinstance(data, dict):
        return ""
    na = data.get("dispatchable_next")
    ostensible = data.get("ostensible_next")
    b = data.get("board_budget") or {}
    blk = data.get("last_blocker") or {}
    inflight = data.get("in_flight_claims") or {}
    lanes = data.get("open_lanes") or {}
    parts = [
        "**Resume from (handoff)** — "
        f"{lanes.get('total_open', 0)} open across {len(lanes.get('by_lane', {}))} lanes · "
        f"{inflight.get('count', 0)} in-flight ({inflight.get('stale', 0)} stale) · "
        f"needs_human {blk.get('needs_human_count', 0)}",
    ]
    if b.get("remaining") is not None:
        parts[0] += f" · board budget {b.get('spent')}/{b.get('daily')}"
    if na:
        parts.append(f"  next → `{na.get('id')}` [{na.get('priority')}] {na.get('title', '')}")
    elif ostensible:
        parts.append(f"  ostensible (currently gated) → `{ostensible.get('id')}` {ostensible.get('title', '')}")
        reasons = (data.get("dispatch_admission") or {}).get("reason_counts") or {}
        if reasons:
            parts.append("  gates: " + ", ".join(f"{key}={value}" for key, value in sorted(reasons.items())))
    if blk.get("heal_pressure"):
        parts.append(f"  heal: {blk['heal_pressure']}")
    return "\n".join(parts)


def print_handoff() -> int:
    """Render the stored handoff — loudly distinguishing absence from a real empty board.

    A missing/corrupt/unstamped handoff.json used to collapse to {} and render as a
    healthy-looking "0 open across 0 lanes"; absence must never look like health.
    """
    data = _load_json(HANDOFF, None)
    if not isinstance(data, dict) or not data.get("generated"):
        print(
            "**Resume from (handoff)** — NO HANDOFF RECORDED "
            "(logs/handoff.json missing, corrupt, or unstamped) — "
            "run `python3 scripts/handoff-relay.py` to scan"
        )
        return 1
    try:
        age_min = (_now() - dt.datetime.fromisoformat(str(data["generated"]))).total_seconds() / 60
    except Exception:
        print(
            "**Resume from (handoff)** — NO HANDOFF RECORDED "
            "(logs/handoff.json missing, corrupt, or unstamped) — "
            "run `python3 scripts/handoff-relay.py` to scan"
        )
        return 1
    if age_min > FRESH_MAX_MINUTES:
        print(f"⚠ handoff is {age_min:.0f}m old (> {FRESH_MAX_MINUTES}m) — seam may be cold")
    print(render(data))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="seam-survival handoff relay")
    ap.add_argument("--check", action="store_true", help="predicate: fresh+complete handoff exists")
    ap.add_argument("--print", dest="do_print", action="store_true", help="render current handoff")
    args = ap.parse_args()
    if args.check:
        return check()
    if args.do_print:
        return print_handoff()
    return write()


if __name__ == "__main__":
    raise SystemExit(main())