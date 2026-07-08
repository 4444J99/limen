#!/usr/bin/env python3
"""handoff-relay — the seam-survival organ.

The 84-ask overnight/walk-away loop kept dying at every session/vendor/beat seam because each
pickup cold-derived the world from scratch (retro 2026-07-08, finding 3). This writes one compact,
PII-clean ``logs/handoff.json`` every beat and at SessionEnd, so the NEXT session/vendor/beat
resumes WARM: it knows the open lanes, the in-flight claims, the last blocker, the budget left, and
the single next action. ``session-orient`` injects it at SessionStart.

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
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
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


def _load_tasks() -> list[dict[str, Any]]:
    try:
        import yaml
    except Exception:
        return []
    try:
        board = yaml.safe_load(TASKS.read_text())
    except Exception:
        return []
    tasks = board.get("tasks", board) if isinstance(board, dict) else board
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


def _budget() -> dict[str, Any]:
    """What runway is left — the beat's async budget and per-vendor spend."""
    out: dict[str, Any] = {"overnight_spent": None, "overnight_cap": None, "vendors": {}}
    # overnight-watch prints "spent=62/600" — the cheapest live gauge.
    try:
        for ln in reversed(OVERNIGHT.read_text().splitlines()):
            if "spent=" in ln:
                frag = ln.split("spent=", 1)[1].split()[0]
                spent, cap = frag.split("/")
                out["overnight_spent"], out["overnight_cap"] = int(spent), int(cap)
                out["overnight_remaining"] = int(cap) - int(spent)
                break
    except Exception:
        pass
    usage = _load_json(USAGE, {})
    vendors = usage.get("vendors") if isinstance(usage, dict) else None
    if isinstance(vendors, dict):
        for name, v in list(vendors.items())[:10]:
            if isinstance(v, dict):
                out["vendors"][name] = {k: v.get(k) for k in ("remaining", "spent", "state", "status") if k in v}
    return out


def _next_action(tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The single next honest step: highest-priority OPEN task whose deps are satisfied. The
    resume acts instead of re-deriving 'what now'."""
    done = {t.get("id") for t in tasks if t.get("status") in {"done", "archived"}}
    candidates = []
    for t in tasks:
        if t.get("status") != "open":
            continue
        deps = t.get("depends_on") or []
        if any(d not in done for d in deps):
            continue
        candidates.append(t)
    if not candidates:
        return None
    top = sorted(candidates, key=lambda t: (_PRIORITY.get(str(t.get("priority")), 9), str(t.get("id"))))[0]
    return {
        "id": top.get("id"),
        "title": str(top.get("title", ""))[:90],
        "repo": top.get("repo"),
        "agent": top.get("target_agent"),
        "priority": top.get("priority"),
    }


def build() -> dict[str, Any]:
    now = _now()
    tasks = _load_tasks()
    return {
        "generated": now.isoformat(timespec="seconds"),
        "open_lanes": _open_lanes(tasks),
        "in_flight_claims": _in_flight(tasks, now),
        "last_blocker": _last_blocker(tasks),
        "budget_remaining": _budget(),
        "next_action": _next_action(tasks),
    }


def write() -> int:
    HANDOFF.parent.mkdir(parents=True, exist_ok=True)
    payload = build()
    tmp = HANDOFF.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True))
    tmp.replace(HANDOFF)
    na = payload["next_action"]
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
    for field in ("open_lanes", "in_flight_claims", "last_blocker", "budget_remaining"):
        if field not in data:
            print(f"handoff-relay --check: FAIL — missing '{field}'")
            return 1
    na = (data.get("next_action") or {}).get("id") if data.get("next_action") else "none(board drained)"
    print(f"handoff-relay --check: OK — fresh ({age_min:.0f}m), warm resume ready; next={na}")
    return 0


def render(data: dict[str, Any]) -> str:
    if not isinstance(data, dict):
        return ""
    na = data.get("next_action")
    b = data.get("budget_remaining") or {}
    blk = data.get("last_blocker") or {}
    inflight = data.get("in_flight_claims") or {}
    lanes = data.get("open_lanes") or {}
    parts = [
        "**Resume from (handoff)** — "
        f"{lanes.get('total_open', 0)} open across {len(lanes.get('by_lane', {}))} lanes · "
        f"{inflight.get('count', 0)} in-flight ({inflight.get('stale', 0)} stale) · "
        f"needs_human {blk.get('needs_human_count', 0)}",
    ]
    if b.get("overnight_remaining") is not None:
        parts[0] += f" · beat budget {b.get('overnight_spent')}/{b.get('overnight_cap')}"
    if na:
        parts.append(f"  next → `{na.get('id')}` [{na.get('priority')}] {na.get('title', '')}")
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
