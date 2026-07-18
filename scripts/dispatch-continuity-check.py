#!/usr/bin/env python3
"""dispatch-continuity-check.py — detect a vendor lane that goes silent while work + budget exist.

PRECEDENT (Jul 3–5 starvation, organvm/limen):
  The Jules lane accepted zero tasks for 72+ hours while ~40 open tasks with
  target_agent=jules sat in the queue and the daily budget showed ample headroom.
  The daemon was alive, the queue was full, the meter read green — but the lane
  was not flowing. Nothing surfaced this gap until a human noticed the backlog
  had not shrunk in three days. This check closes that gap: every beat it reads
  the live board and the usage meter and classifies each lane as "flowing",
  "idle-ok" (silence is fine because queue or budget is empty), "starved"
  (silent > window AND queue non-empty AND budget ok), or "unknown" (missing
  data — never alarm on missing data). A starved verdict on TWO consecutive
  beats hangs an idempotent ASK-lane-starved-<lane> needs_human atom.

Read-only on tasks.yaml for analysis; briefly takes the queue_lock only to upsert
a starved-lane atom. Never holds the lock while doing analysis.

Env:
  LIMEN_TASKS                  — path to tasks.yaml (default: repo-relative)
  LIMEN_CONTINUITY_CHECK       — "0" to skip this step from metabolize.sh (default: "1")
  LIMEN_CONTINUITY_WINDOW_H    — starvation window in hours (default: 24)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
VOICE_DIR = LOGS / ".voice"
LEDGER = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
USAGE_JSON = LOGS / "usage.json"
ARTIFACT = LOGS / "dispatch-continuity.json"
VOICE_STAMP = VOICE_DIR / "continuity"

_DEFAULT_WINDOW_H = 24


def _positive_float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return default
    return v if v > 0 else default


def _parse_ts(s: object) -> datetime | None:
    """Parse an ISO timestamp string defensively; return None on any failure."""
    if not isinstance(s, str):
        return None
    s = s.strip()
    # normalise: replace space with T, strip trailing Z/+00:00 to a naive UTC
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(s[:26], fmt[: len(fmt)])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _load_tasks_doc() -> dict:
    """Load tasks.yaml as a raw dict (read-only). Returns {} on any error."""
    try:
        import yaml  # type: ignore[import]
    except ImportError:
        yaml = None  # type: ignore[assignment]

    if not LEDGER.exists():
        return {}
    try:
        text = LEDGER.read_text()
    except OSError:
        return {}

    if yaml is not None:
        try:
            return yaml.safe_load(text) or {}
        except Exception:
            return {}

    # stdlib fallback: not ideal, but we only need the raw structure for analysis
    # tasks.yaml is structured YAML; without pyyaml we can't safely parse it.
    return {}


def _known_lanes(tasks_doc: dict) -> list[str]:
    """Derive lane names from portal.budget.per_agent (the canonical registry)."""
    try:
        return list((tasks_doc.get("portal", {}) or {}).get("budget", {}).get("per_agent", {}).keys())
    except Exception:
        return []


def lane_last_dispatch(tasks_doc: dict) -> dict[str, datetime]:
    """Return per-agent most-recent dispatch timestamp from every task's dispatch_log.

    Walks every task's dispatch_log list; each entry has agent + timestamp fields.
    Parses defensively — a malformed entry is skipped (fail-open per entry).
    """
    latest: dict[str, datetime] = {}
    tasks = tasks_doc.get("tasks") or []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        for entry in task.get("dispatch_log") or []:
            if not isinstance(entry, dict):
                continue
            agent = entry.get("agent")
            if not isinstance(agent, str) or not agent:
                continue
            dt = _parse_ts(entry.get("timestamp"))
            if dt is None:
                continue
            if agent not in latest or dt > latest[agent]:
                latest[agent] = dt
    return latest


def lane_queue(tasks_doc: dict) -> dict[str, int]:
    """Return per-lane open task count, plus a 'shared' key for open tasks routable to any lane.

    A shared task has target_agent in (None, '', 'any').
    """
    counts: dict[str, int] = {}
    shared = 0
    tasks = tasks_doc.get("tasks") or []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        if task.get("status") != "open":
            continue
        ta = task.get("target_agent")
        if not ta or str(ta).lower() in ("any", ""):
            shared += 1
        else:
            ta = str(ta)
            counts[ta] = counts.get(ta, 0) + 1
    counts["shared"] = shared
    return counts


def _load_usage() -> dict:
    """Load logs/usage.json; returns {} on any error."""
    try:
        return json.loads(USAGE_JSON.read_text())
    except Exception:
        return {}


def lane_budget_ok(usage: dict) -> dict[str, str]:
    """Return per-lane budget status: 'ok', 'exhausted', 'unknown'.

    Reads usage['vendors'][lane]: health == "ok"-ish (not exhausted/rate-limited)
    and consumed < possible.  Missing vendor/file → "unknown".
    """
    vendors = usage.get("vendors") or {}
    result: dict[str, str] = {}
    for lane, info in vendors.items():
        if not isinstance(info, dict):
            result[lane] = "unknown"
            continue
        health = str(info.get("health", "")).lower()
        consumed = info.get("consumed")
        possible = info.get("possible")
        if health in ("exhausted", "rate-limited", "rate_limited", "depleted"):
            result[lane] = "exhausted"
        elif health == "ok" or health == "ok (tcc_gated)":
            # secondary: if consumed >= possible, exhausted
            if isinstance(consumed, (int, float)) and isinstance(possible, (int, float)):
                if possible > 0 and consumed >= possible:
                    result[lane] = "exhausted"
                else:
                    result[lane] = "ok"
            else:
                result[lane] = "ok"
        elif health:
            # unknown-ish health string — treat conservatively as unknown
            result[lane] = "unknown"
        else:
            result[lane] = "unknown"
    return result


def _load_prev_artifact() -> dict:
    """Load the previous dispatch-continuity.json; returns {} on missing/error."""
    try:
        return json.loads(ARTIFACT.read_text())
    except Exception:
        return {}


def verdicts(now: datetime, window_h: float | None = None) -> dict[str, dict]:
    """Classify each known lane as flowing / idle-ok / starved / unknown.

    Rules:
      - flowing:  last dispatch within window (regardless of queue/budget)
      - starved:  silent > window AND queue_open > 0 AND budget ok
      - idle-ok:  silent > window but queue empty OR budget not ok
      - unknown:  usage data missing for this lane (never alarm on missing data)

    'queue_open' counts only tasks targeted at this lane specifically (not shared),
    because shared tasks can go to any lane — silence on one lane with only shared
    tasks is ambiguous. If a lane has dedicated open tasks, that is a clear starvation
    signal.
    """
    if window_h is None:
        window_h = _positive_float_env("LIMEN_CONTINUITY_WINDOW_H", _DEFAULT_WINDOW_H)

    tasks_doc = _load_tasks_doc()
    usage = _load_usage()

    last_dispatch = lane_last_dispatch(tasks_doc)
    queue = lane_queue(tasks_doc)
    budget = lane_budget_ok(usage)
    lanes = _known_lanes(tasks_doc)

    result: dict[str, dict] = {}
    for lane in lanes:
        last = last_dispatch.get(lane)
        if last is not None:
            gap_h = (now - last).total_seconds() / 3600.0
        else:
            gap_h = None

        queue_open = queue.get(lane, 0)
        bstatus = budget.get(lane, "unknown")

        if gap_h is not None and gap_h <= window_h:
            verdict = "flowing"
        elif bstatus == "unknown":
            verdict = "unknown"
        elif bstatus == "exhausted":
            verdict = "idle-ok"
        elif queue_open == 0:
            verdict = "idle-ok"
        else:
            # silent > window, queue non-empty, budget ok → starved
            verdict = "starved"

        result[lane] = {
            "last_dispatch": last.isoformat() if last else None,
            "gap_h": round(gap_h, 2) if gap_h is not None else None,
            "queue_open": queue_open,
            "budget_ok": bstatus,
            "verdict": verdict,
        }
    return result


def _upsert_starved_atom(lane: str, info: dict) -> None:
    """Hang ASK-lane-starved-<lane> as a needs_human atom under queue_lock. Idempotent."""
    try:
        sys.path.insert(0, str(ROOT / "cli" / "src"))
        from datetime import date  # noqa: PLC0415
        from limen.io import load_limen_file, queue_lock, save_limen_file  # noqa: PLC0415
        from limen.intake import contract_fields, github_issue_owner_contract  # noqa: PLC0415
        from limen.models import Task, has_jules_landing_hold  # noqa: PLC0415
        from limen.workstream_contract import WORKSTREAM_SUCCESSOR_REQUIRED_LABEL  # noqa: PLC0415
    except Exception as e:
        print(f"  [continuity] ledger import failed ({e}); starved atom not hung", flush=True)
        return

    if not LEDGER.exists():
        print(f"  [continuity] no ledger at {LEDGER}; starved atom not hung", flush=True)
        return

    tid = f"ASK-lane-starved-{lane}"
    gap_h = info.get("gap_h")
    queue_open = info.get("queue_open", 0)
    gap_str = f"{gap_h:.1f}h" if gap_h is not None else "unknown"
    ctx = (
        f"Lane '{lane}' has been silent for {gap_str} while {queue_open} open task(s) await it "
        f"and its budget is ok. This matches the Jul 3–5 starvation signature: daemon alive, "
        f"queue non-empty, budget available, zero dispatches for an extended period (window: "
        f"{_positive_float_env('LIMEN_CONTINUITY_WINDOW_H', _DEFAULT_WINDOW_H):.0f}h). "
        f"Likely cause: routing bypass, gate mis-config, or lane not being selected. "
        f"See scripts/route.py for routing logic. Auto-hung by dispatch-continuity-check.py."
    )
    now = datetime.now(timezone.utc)

    with queue_lock(LEDGER) as got:
        if not got:
            print(f"  [continuity] queue busy; starved atom for {lane} deferred", flush=True)
            return
        lf = load_limen_file(LEDGER)
        index = {t.id: t for t in lf.tasks}
        contract = contract_fields(github_issue_owner_contract("organvm/limen", tid))
        changed = False
        ex = index.get(tid)
        if (
            ex
            and ex.status != "done"
            and WORKSTREAM_SUCCESSOR_REQUIRED_LABEL not in (ex.labels or [])
            and not has_jules_landing_hold(ex)
        ):
            if ex.context != ctx:
                ex.context = ctx
                ex.updated = now
                changed = True
            if ex.status != "needs_human":
                ex.status = "needs_human"
                ex.updated = now
                changed = True
        elif ex is None:
            lf.tasks.append(
                Task(
                    id=tid,
                    title=f"Lane '{lane}' starved: silent >{gap_str} with open queue + ok budget",
                    repo="organvm/limen",
                    type="ops",
                    target_agent="human",
                    priority="high",
                    status="needs_human",
                    labels=["dispatch-continuity", "needs-human"],
                    context=ctx,
                    **contract,
                    created=date.today(),
                    updated=now,
                )
            )
            changed = True
        if changed:
            save_limen_file(LEDGER, lf)
            print(f"  [continuity] hung/refreshed starved atom: {tid}", flush=True)
        else:
            print(f"  [continuity] starved atom already current: {tid}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect dispatch lanes silent while queue + budget exist (Jul 3–5 precedent)."
    )
    parser.add_argument("--check", action="store_true", help="exit 1 if any lane is starved")
    parser.add_argument(
        "--window-h",
        type=float,
        default=None,
        help=f"starvation window in hours (default: LIMEN_CONTINUITY_WINDOW_H or {_DEFAULT_WINDOW_H})",
    )
    args = parser.parse_args()

    window_h = args.window_h or _positive_float_env("LIMEN_CONTINUITY_WINDOW_H", _DEFAULT_WINDOW_H)

    now = datetime.now(timezone.utc)
    lane_verdicts = verdicts(now, window_h=window_h)

    # ── two-consecutive rule: load previous artifact ──────────────────────────
    prev = _load_prev_artifact()
    prev_lanes = (prev.get("lanes") or {}) if isinstance(prev, dict) else {}

    # ── write artifact ────────────────────────────────────────────────────────
    artifact = {
        "generated": now.isoformat(),
        "window_h": window_h,
        "lanes": lane_verdicts,
    }
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        ARTIFACT.write_text(json.dumps(artifact, indent=2))
    except OSError as e:
        print(f"  [continuity] could not write artifact: {e}", flush=True)

    # ── stamp voice ───────────────────────────────────────────────────────────
    try:
        VOICE_DIR.mkdir(parents=True, exist_ok=True)
        VOICE_STAMP.write_text(now.isoformat())
    except OSError:
        pass

    # ── report ────────────────────────────────────────────────────────────────
    any_starved = False
    for lane, info in sorted(lane_verdicts.items()):
        verdict = info["verdict"]
        gap = f"{info['gap_h']:.1f}h" if info["gap_h"] is not None else "never"
        q = info["queue_open"]
        b = info["budget_ok"]
        print(
            f"  {lane:12s}  {verdict:10s}  gap={gap:>8s}  queue={q}  budget={b}",
            flush=True,
        )
        if verdict == "starved":
            # two-consecutive check
            prev_info = prev_lanes.get(lane) or {}
            prev_verdict = prev_info.get("verdict") if isinstance(prev_info, dict) else None
            if prev_verdict == "starved":
                print(
                    f"  [continuity] {lane} starved TWO consecutive readings — hanging atom",
                    flush=True,
                )
                _upsert_starved_atom(lane, info)
            else:
                print(
                    f"  [continuity] {lane} starved (first reading) — watching next beat",
                    flush=True,
                )
            any_starved = True

    if args.check and any_starved:
        sys.exit(1)


if __name__ == "__main__":
    main()
