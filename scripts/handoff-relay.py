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

from limen.runtime_requirements import task_execution_ready  # noqa: E402
from limen.work_loan import task_work_loan_readiness  # noqa: E402
from limen.workstream_contract import WORKSTREAM_SUCCESSOR_REQUIRED_LABEL  # noqa: E402

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
                        )
                        if key in value
                    }
                    reset_at = value.get("resets_at", value.get("reset_at"))
                    if reset_at is not None:
                        projected["resets_at"] = reset_at
                    vendors[str(name)] = projected
    return {"generated": generated, "vendors": vendors}


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


def _board_budget(board: dict[str, Any]) -> dict[str, Any]:
    """Authoritative budget from ``tasks.yaml`` rather than the overnight log proxy."""
    portal = board.get("portal") if isinstance(board, dict) else None
    budget = portal.get("budget") if isinstance(portal, dict) else None
    budget = budget if isinstance(budget, dict) else {}
    track = budget.get("track") if isinstance(budget.get("track"), dict) else {}
    caps = budget.get("per_agent") if isinstance(budget.get("per_agent"), dict) else {}
    spent_by = track.get("per_agent") if isinstance(track.get("per_agent"), dict) else {}
    reset_by = track.get("per_agent_reset") if isinstance(track.get("per_agent_reset"), dict) else {}
    daily = _as_int(budget.get("daily"))
    spent = _as_int(track.get("spent"))
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


def _provider_available(agent: str, provider_headroom: dict[str, Any]) -> bool:
    if agent in {"", "any"}:
        return True
    vendors = provider_headroom.get("vendors")
    value = vendors.get(agent) if isinstance(vendors, dict) else None
    if not isinstance(value, dict):
        return True  # unknown is not the same as measured-down
    remaining = value.get("remaining")
    if isinstance(remaining, (int, float)) and not isinstance(remaining, bool) and remaining <= 0:
        return False
    state = str(value.get("health") or value.get("state") or value.get("status") or "")
    state = state.strip().lower().replace("-", "_")
    return state not in {
        "down",
        "disabled",
        "exhausted",
        "low",
        "rate_limited",
        "unavailable",
        "blocked",
    }


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
    for task in tasks:
        if task.get("status") != "open":
            continue
        reason: str | None = None
        if _has_terminal_transition(task):
            reason = "terminal_history"
        labels = {str(label) for label in task.get("labels") or []}
        if reason is None and "needs-human" in labels:
            reason = "human_gate"
        if reason is None and WORKSTREAM_SUCCESSOR_REQUIRED_LABEL in labels:
            reason = "successor_required"
        deps = [str(value) for value in task.get("depends_on") or []]
        if reason is None and any(not _dependency_merged(by_id.get(dep)) for dep in deps):
            reason = "dependencies"
        underwriting = task_work_loan_readiness(task)
        if reason is None and not underwriting.ready:
            reason = str(underwriting.reason_code)
        cost = _as_int(task.get("budget_cost")) or 1
        if reason is None and global_remaining is not None and cost > global_remaining:
            reason = "budget_global"
        agent = str(task.get("target_agent") or "")
        agent_budget = per_agent.get(agent) if isinstance(per_agent, dict) else None
        agent_remaining = _as_int(agent_budget.get("remaining")) if isinstance(agent_budget, dict) else None
        if reason is None and agent_remaining is not None and cost > agent_remaining:
            reason = "budget_agent"
        if reason is None and not _provider_available(agent, provider_headroom):
            reason = "provider_health"
        if reason is None and not task_execution_ready(task):
            reason = "execution_requirements"
        if reason is not None:
            reasons[reason] += 1
            continue
        candidates.append(task)
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


def main() -> int:
    ap = argparse.ArgumentParser(description="seam-survival handoff relay")
    ap.add_argument("--check", action="store_true", help="predicate: fresh+complete handoff exists")
    ap.add_argument("--print", dest="do_print", action="store_true", help="render current handoff")
    args = ap.parse_args()
    if args.check:
        return check()
    if args.do_print:
        print(render(_load_json(HANDOFF, {})))
        return 0
    return write()


if __name__ == "__main__":
    raise SystemExit(main())
