#!/usr/bin/env python3
"""conducting-report — the answer to "did it use all the usage overnight?" arrives BEFORE you ask.

Once a day this distills logs/usage.json into a per-vendor verdict — consumed vs the safe steady-state
rate vs the reserve floor — and a one-line headline: did the fleet conduct at FULL FORCE (burned each
window toward the reserve drops) or did it IDLE at a full tank (and why)? It also counts how many repos
got value-discovery work. Delivery is CASCADED (never-"NO"): a local macOS notification AND, if
LIMEN_NTFY_TOPIC is set, an ntfy.sh push to your phone. Idempotent: fires at most once per day (tracks
logs/.conducting-report-state.json); --force re-emits now. Fail-open: a missing/torn feed prints what it
can and never crashes the beat. Before claiming a route, it runs dispatch's canonical always-working
owner reconciliation; otherwise it writes only its own state and delivery receipts.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli" / "src"))

from _notify import NotificationResult, notify_event, notify_ntfy

try:
    from limen.dispatch import run_always_working_before_dispatch as _run_always_working_before_dispatch
except Exception:  # pragma: no cover - an older installed runtime must fail closed below
    _run_always_working_before_dispatch = None

try:
    from limen.bounded_subprocess import (
        BoundedSubprocessError as _BoundedSubprocessError,
        run_bounded_subprocess as _run_bounded_subprocess,
    )
except Exception:  # pragma: no cover - an older installed runtime must fail closed below
    _BoundedSubprocessError = None
    _run_bounded_subprocess = None

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
USAGE = LOGS / "usage.json"
TASKS = Path(os.environ.get("LIMEN_TASKS", str(ROOT / "tasks.yaml")))
STATE = LOGS / ".conducting-report-state.json"
HANDOFF = LOGS / "handoff.json"
CONTINUITY = LOGS / "dispatch-continuity.json"
ADMISSION_REFRESH_RECEIPT = LOGS / "conducting-admission-refresh.jsonl"
ROUTING_REASONS = frozenset({"routable", "admission_blocked", "capacity_blocked", "auth_blocked", "keeper_unavailable"})
TELEMETRY_MAX_AGE_SECONDS = 5400
ADMISSION_REFRESH_TIMEOUT_SECONDS = 60.0
ADMISSION_REFRESH_OUTPUT_LIMIT_BYTES = 8192
SESSION_VALUE_TIMEOUT_SECONDS = 90.0
SESSION_VALUE_OUTPUT_LIMIT_BYTES = 8192


def _load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def _admission_refresh_receipt(event: str, **fields: object) -> None:
    """Emit a bounded, public-safe start/finish receipt for the relay subprocess."""
    try:
        ADMISSION_REFRESH_RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **fields,
        }
        with ADMISSION_REFRESH_RECEIPT.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    except OSError:
        pass


def _refresh_admission() -> bool:
    """Refresh keeper-owned admission through one process-group-bounded relay."""
    path = Path(__file__).with_name("handoff-relay.py")
    try:
        configured_timeout = float(
            os.environ.get("LIMEN_CONDUCTING_REFRESH_TIMEOUT", ADMISSION_REFRESH_TIMEOUT_SECONDS)
        )
        timeout = (
            max(1.0, configured_timeout) if math.isfinite(configured_timeout) else ADMISSION_REFRESH_TIMEOUT_SECONDS
        )
    except ValueError:
        timeout = ADMISSION_REFRESH_TIMEOUT_SECONDS
    started = time.monotonic()
    _admission_refresh_receipt(
        "start",
        timeout_seconds=timeout,
        output_limit_bytes=ADMISSION_REFRESH_OUTPUT_LIMIT_BYTES * 2,
        stdout_limit_bytes=ADMISSION_REFRESH_OUTPUT_LIMIT_BYTES,
        stderr_limit_bytes=ADMISSION_REFRESH_OUTPUT_LIMIT_BYTES,
    )
    if _run_bounded_subprocess is None:
        _admission_refresh_receipt(
            "finish",
            elapsed_seconds=round(time.monotonic() - started, 3),
            outcome="runner_unavailable",
        )
        return False
    try:
        result = _run_bounded_subprocess(
            [sys.executable, str(path)],
            cwd=ROOT,
            timeout_seconds=timeout,
            stdout_ceiling=ADMISSION_REFRESH_OUTPUT_LIMIT_BYTES,
            stderr_ceiling=ADMISSION_REFRESH_OUTPUT_LIMIT_BYTES,
        )
    except Exception as exc:
        failure_kind = (
            str(exc.kind)
            if _BoundedSubprocessError is not None and isinstance(exc, _BoundedSubprocessError)
            else "unavailable"
        )
        outcome = {
            "output": "output_limit",
            "unavailable": "launch_failed",
        }.get(failure_kind, failure_kind)
        _admission_refresh_receipt(
            "finish",
            elapsed_seconds=round(time.monotonic() - started, 3),
            outcome=outcome,
        )
        return False
    outcome = "ok" if result.returncode == 0 else "failed"
    _admission_refresh_receipt(
        "finish",
        elapsed_seconds=round(time.monotonic() - started, 3),
        outcome=outcome,
        returncode=result.returncode,
    )
    return result.returncode == 0


def _session_value_admission() -> dict[str, object]:
    """Evaluate the same session-value gate that withholds generic dispatch."""
    if os.environ.get("LIMEN_SESSION_VALUE_GATE", "1") in {"0", "false", "False"}:
        return {"status": "allowed", "reason": "session value gate disabled"}
    path = Path(__file__).with_name("session-value-review.py")
    hours = os.environ.get(
        "LIMEN_VALUE_GATE_HOURS",
        os.environ.get("LIMEN_ASYNC_VALUE_GATE_HOURS", "1.5"),
    )
    try:
        configured_timeout = float(
            os.environ.get(
                "LIMEN_VALUE_GATE_TIMEOUT",
                os.environ.get("LIMEN_ASYNC_VALUE_GATE_TIMEOUT", SESSION_VALUE_TIMEOUT_SECONDS),
            )
        )
        timeout = max(1.0, configured_timeout) if math.isfinite(configured_timeout) else SESSION_VALUE_TIMEOUT_SECONDS
    except ValueError:
        timeout = SESSION_VALUE_TIMEOUT_SECONDS
    started = time.monotonic()
    _admission_refresh_receipt(
        "start",
        step="session_value",
        timeout_seconds=timeout,
        output_limit_bytes=SESSION_VALUE_OUTPUT_LIMIT_BYTES * 2,
        stdout_limit_bytes=SESSION_VALUE_OUTPUT_LIMIT_BYTES,
        stderr_limit_bytes=SESSION_VALUE_OUTPUT_LIMIT_BYTES,
    )
    if _run_bounded_subprocess is None:
        _admission_refresh_receipt(
            "finish",
            step="session_value",
            elapsed_seconds=round(time.monotonic() - started, 3),
            outcome="runner_unavailable",
        )
        return {"status": "unavailable", "reason": "bounded session value runner unavailable"}
    try:
        result = _run_bounded_subprocess(
            [sys.executable, str(path), "--gate", "--hours", hours, "--no-record-gate"],
            cwd=ROOT,
            timeout_seconds=timeout,
            stdout_ceiling=SESSION_VALUE_OUTPUT_LIMIT_BYTES,
            stderr_ceiling=SESSION_VALUE_OUTPUT_LIMIT_BYTES,
        )
    except Exception as exc:
        failure_kind = (
            str(exc.kind)
            if _BoundedSubprocessError is not None and isinstance(exc, _BoundedSubprocessError)
            else "unavailable"
        )
        outcome = "output_limit" if failure_kind == "output" else failure_kind
        _admission_refresh_receipt(
            "finish",
            step="session_value",
            elapsed_seconds=round(time.monotonic() - started, 3),
            outcome=outcome,
        )
        detail = "exceeded output limit" if failure_kind == "output" else failure_kind
        return {"status": "unavailable", "reason": f"session value gate unavailable: {detail}"}
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    detail = (stderr or stdout or "session value gate returned no detail").strip()
    try:
        gate_payload = json.loads(stdout) if stdout else None
    except (TypeError, ValueError):
        gate_payload = None
    if isinstance(gate_payload, dict):
        action = str(gate_payload.get("action") or "unspecified")
        detail = f"action={action}"
    else:
        detail = " ".join(detail.split())[:500]
    if result.returncode == 0:
        outcome = "allowed"
        response = {"status": "allowed", "reason": detail or "session value gate allowed dispatch"}
    elif result.returncode == 10:
        outcome = "blocked"
        response = {"status": "blocked", "reason": detail or "session value gate withheld dispatch"}
    else:
        outcome = "unavailable"
        response = {"status": "unavailable", "reason": detail or f"session value gate exited {result.returncode}"}
    _admission_refresh_receipt(
        "finish",
        step="session_value",
        elapsed_seconds=round(time.monotonic() - started, 3),
        outcome=outcome,
        returncode=result.returncode,
        output_bytes=len(result.stdout) + len(result.stderr),
        output_truncated=False,
    )
    return response


def _always_working_admission() -> dict[str, str]:
    """Run the dispatcher's canonical final pre-reservation gate."""
    if _run_always_working_before_dispatch is None:
        return {
            "status": "unavailable",
            "reason": "canonical always-working gate is unavailable",
        }
    try:
        allowed = _run_always_working_before_dispatch(TASKS)
    except Exception as exc:
        return {
            "status": "unavailable",
            "reason": f"canonical always-working gate raised {type(exc).__name__}",
        }
    if allowed:
        return {"status": "allowed", "reason": "canonical always-working gate allowed dispatch"}
    return {"status": "blocked", "reason": "canonical always-working gate withheld dispatch"}


def _notify_macos(title, msg, day, *, force=False) -> NotificationResult:
    return notify_event(
        ROOT,
        source="conducting-report",
        event="daily-report",
        stable_id=day,
        local_day=day,
        payload={"headline": msg},
        message=msg,
        title=title,
        force=force,
    )


def _notify_ntfy(title, msg):
    return notify_ntfy(ROOT, msg, title=title, tags="battery")


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _fresh_timestamp(payload: object, instant: datetime) -> bool:
    if not isinstance(payload, dict):
        return False
    generated = _parse_timestamp(payload.get("generated") or payload.get("generated_at"))
    if generated is None:
        return False
    age = (instant.astimezone(timezone.utc) - generated.astimezone(timezone.utc)).total_seconds()
    return 0 <= age <= TELEMETRY_MAX_AGE_SECONDS


def _safe_count(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _normalize_provider(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _continuity_summary(instant: datetime) -> str:
    payload = _load(CONTINUITY, {})
    if not _fresh_timestamp(payload, instant):
        return "continuity unavailable or stale"
    lanes = payload.get("lanes") if isinstance(payload, dict) else None
    if not isinstance(lanes, dict):
        return "continuity unavailable"
    counts: dict[str, int] = {}
    for row in lanes.values():
        if not isinstance(row, dict):
            continue
        verdict = str(row.get("verdict") or "unknown")
        counts[verdict] = counts.get(verdict, 0) + 1
    return "continuity " + ", ".join(f"{key}={counts[key]}" for key in sorted(counts))


def _routing_reason(
    now: datetime | None = None,
    target_providers: set[str] | None = None,
    session_value_gate: dict[str, object] | None = None,
    always_working_gate: dict[str, object] | None = None,
) -> tuple[str, str]:
    """Classify routing from keeper-owned admission, never from vendor consumption."""
    handoff = _load(HANDOFF, None)
    if not isinstance(handoff, dict):
        return "keeper_unavailable", "handoff missing or unreadable"
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    if not _fresh_timestamp(handoff, instant):
        return "keeper_unavailable", "handoff missing a fresh keeper timestamp"

    pause_marker = ROOT / "logs" / "AUTONOMY_PAUSED"
    if pause_marker.exists() and os.environ.get("LIMEN_FORCE_AUTONOMY") != "1":
        return "admission_blocked", "autonomy pause marker is present"

    admission = handoff.get("dispatch_admission")
    if not isinstance(admission, dict) or admission.get("schema_version") != "limen.dispatch_admission.v1":
        return "keeper_unavailable", "canonical dispatch admission unavailable"
    if admission.get("keeper_available") is False:
        return "keeper_unavailable", "keeper board unavailable during admission refresh"

    if session_value_gate is not None:
        gate_status = str(session_value_gate.get("status") or "unavailable")
        gate_reason = str(session_value_gate.get("reason") or "session value gate returned no detail")
        if gate_status == "blocked":
            return "admission_blocked", f"session value gate withheld dispatch: {gate_reason}"
        if gate_status != "allowed":
            return "keeper_unavailable", f"session value gate unavailable: {gate_reason}"

    provider_headroom = handoff.get("provider_headroom")
    if not _fresh_timestamp(provider_headroom, instant):
        return "keeper_unavailable", "provider-headroom telemetry unavailable or stale"

    admissible = _safe_count(admission.get("admissible"))
    open_considered = _safe_count(admission.get("open_considered"))
    continuity = _continuity_summary(instant)
    raw_down_lanes = admission.get("down_lanes")
    if not isinstance(raw_down_lanes, (list, tuple, set)):
        raw_down_lanes = provider_headroom.get("down_lanes", [])
    down_lanes = {_normalize_provider(lane) for lane in raw_down_lanes if str(lane).strip()}
    target_names = {_normalize_provider(name) for name in (target_providers or set()) if str(name).strip()}
    if admissible > 0 or admission.get("dispatchable_next"):
        gate = always_working_gate if always_working_gate is not None else _always_working_admission()
        gate_status = str(gate.get("status") or "unavailable")
        gate_reason = str(gate.get("reason") or "always-working gate returned no detail")
        if gate_status == "blocked":
            return "admission_blocked", f"always-working gate withheld dispatch: {gate_reason}"
        if gate_status != "allowed":
            return "keeper_unavailable", f"always-working gate unavailable: {gate_reason}"
        if target_providers is None:
            lane_counts = admission.get("admissible_agent_counts")
            any_lane_counts = admission.get("admissible_any_agent_counts")
            lane_counts = lane_counts if isinstance(lane_counts, dict) else {}
            any_lane_counts = any_lane_counts if isinstance(any_lane_counts, dict) else {}
            live_available = sum(
                _safe_count(count)
                for name, count in [*lane_counts.items(), *any_lane_counts.items()]
                if str(name).strip().lower().replace("-", "_") not in down_lanes
            )
            if down_lanes and live_available == 0:
                return (
                    "admission_blocked",
                    f"admissible={admissible} but all admitted lanes are down; "
                    f"down={','.join(sorted(down_lanes))}; {continuity}",
                )
            return "routable", f"admissible={admissible}; {continuity}"
        agent_counts = admission.get("admissible_agent_counts")
        any_agent_counts = admission.get("admissible_any_agent_counts")
        if not isinstance(agent_counts, dict) or not isinstance(any_agent_counts, dict):
            return "keeper_unavailable", "canonical targeted admission unavailable"
        target_counts = {
            _normalize_provider(agent): _safe_count(count)
            for agent, count in agent_counts.items()
            if _normalize_provider(agent) != "any"
            and _normalize_provider(agent) in target_names
            and _normalize_provider(agent) not in down_lanes
            and _safe_count(count)
        }
        for agent, count in any_agent_counts.items():
            if (
                _normalize_provider(agent) in target_names
                and _normalize_provider(agent) not in down_lanes
                and _safe_count(count)
            ):
                normalized = _normalize_provider(agent)
                target_counts[normalized] = target_counts.get(normalized, 0) + _safe_count(count)
        if target_counts:
            idle_admissible = sum(target_counts.values())
            return "routable", f"admissible_for_idle={idle_admissible}; {continuity}"
        down_detail = f"; live down lanes={','.join(sorted(down_lanes))}" if down_lanes else ""
        return (
            "admission_blocked",
            f"admissible={admissible} globally but none target idle providers{down_detail}; {continuity}",
        )

    reasons = admission.get("reason_counts")
    reasons = reasons if isinstance(reasons, dict) else {}
    if target_providers is not None:
        # Handoff admission preserves the effective provider for each gated row.  Use only
        # those rows for an idle lane; a Jules-only failure must not become a Codex alert.
        by_agent = admission.get("reason_counts_by_agent")
        if isinstance(by_agent, dict):
            filtered: dict[str, int] = {}
            for agent, counts in by_agent.items():
                normalized = _normalize_provider(agent)
                if normalized not in target_names or not isinstance(counts, dict):
                    continue
                for key, value in counts.items():
                    amount = _safe_count(value)
                    if amount:
                        filtered[str(key)] = filtered.get(str(key), 0) + amount
            reasons = filtered
    active_reasons = {str(key): _safe_count(value) for key, value in reasons.items() if _safe_count(value)}
    reason_keys = {key.lower() for key in active_reasons}
    explicit_auth_block = any("auth" in key or "credential" in key for key in reason_keys)
    provider_health_block = "provider_health" in reason_keys

    vendors = provider_headroom.get("vendors", {}) if isinstance(provider_headroom, dict) else {}
    blocked_counts = admission.get("provider_health_reason_counts")
    blocked_counts = blocked_counts if isinstance(blocked_counts, dict) else {}
    blocked_providers = {_normalize_provider(name) for name, count in blocked_counts.items() if _safe_count(count)}
    if target_providers is not None:
        blocked_providers = {name for name in blocked_providers if name in target_names}
    normalized_vendors = {_normalize_provider(name): row for name, row in vendors.items()}
    provider_states = {
        str(row.get("health") or row.get("state") or row.get("status") or "").lower().replace("-", "_")
        for name, row in normalized_vendors.items()
        if name in blocked_providers and isinstance(row, dict)
    }
    if (
        explicit_auth_block
        or provider_health_block
        and provider_states
        & {
            "auth_needed",
            "auth_blocked",
            "unauthenticated",
        }
    ):
        reason = "auth_blocked"
    else:
        capacity_keys = {"budget_global", "budget_agent", "provider_health", "capacity"}
        reason = "capacity_blocked" if reason_keys and reason_keys <= capacity_keys else "admission_blocked"
    detail = f"open={open_considered}; gates=" + (
        ",".join(f"{key}={active_reasons[key]}" for key in sorted(active_reasons)) if active_reasons else "board_empty"
    )
    return reason, f"{detail}; {continuity}"


def _local_day(now: datetime | None = None) -> str:
    """Daily dedupe follows the host's local calendar, not a UTC usage timestamp."""
    instant = now or datetime.now().astimezone()
    return instant.date().isoformat()


def _named_blocked_task(task_id: str, now: datetime | None = None) -> str | None:
    """Return admission truth for a named task without promoting it to 'next'."""
    handoff = _load(HANDOFF, None)
    instant = now or datetime.now(timezone.utc)
    if not isinstance(handoff, dict) or not _fresh_timestamp(handoff, instant):
        return None
    admission = handoff.get("dispatch_admission")
    rows = admission.get("gated_tasks") if isinstance(admission, dict) else None
    if not isinstance(rows, list):
        return None
    row = next(
        (item for item in rows if isinstance(item, dict) and item.get("id") == task_id),
        None,
    )
    if row is None:
        return None
    reason = str(row.get("reason") or "admission_blocked")
    agent = str(row.get("agent") or "any")
    if reason == "auth_blocked":
        status = "auth_blocked"
    elif reason in {"provider_health", "budget_agent", "budget_global", "capacity"}:
        status = "capacity_blocked"
    else:
        status = "admission_blocked"
    return f"{task_id}: {status} ({agent}; gate={reason})"


def _value_verdict() -> str | None:
    """The ledger's net value verdict (worth-it vs sunk money). Fail-open to None — so the burn
    report still fires even before the ledger has scored anything."""
    rep = _load(LOGS / "ledger.json", {})
    if isinstance(rep, dict) and rep.get("verdict"):
        return str(rep["verdict"])
    return None


def _discovery_count() -> int:
    """Open value-discovery tasks (cheap YAML scan; fail-open to 0)."""
    try:
        import yaml

        data = yaml.safe_load(TASKS.read_text()) or {}
        tasks = data.get("tasks", []) if isinstance(data, dict) else (data or [])
        return sum(
            1
            for t in tasks
            if isinstance(t, dict) and t.get("status") == "open" and str(t.get("id", "")).startswith("DISCOVER-")
        )
    except Exception:
        return 0


def _verdict(v: dict) -> tuple[str, bool]:
    """One-line per-vendor verdict + whether this vendor was 'burned' (consumed past half its window)."""
    hr = v.get("headroom_pct")
    reserve = v.get("reserve_pct", 15)
    consumed = v.get("consumed", 0)
    burn = v.get("burn_rate_per_h", 0)
    safe = v.get("safe_rate_per_h", 0)
    if hr is None:
        return ("usage unknown (meter source unreadable — assuming healthy)", False)
    used_pct = 100 - hr
    if hr <= reserve + 5:
        return (f"burned {used_pct}% — down to the reserve drops ✓", True)
    if consumed == 0:
        return (f"IDLE — full tank, 0 consumed (headroom {hr}%)", False)
    pace = f"{burn:,}/h vs safe {safe:,}/h" if safe else f"{burn:,}/h"
    return (f"used {used_pct}% (headroom {hr}%, pace {pace})", used_pct >= 50)


def build_report(
    *,
    session_value_gate: dict[str, object] | None = None,
    usage_snapshot: dict | None = None,
) -> tuple[str, str, str, str]:
    """Returns (headline, full_text, local_day_key, canonical_routing_reason)."""
    usage = usage_snapshot if usage_snapshot is not None else (_load(USAGE, {}) or {})
    vendors = usage.get("vendors", {})
    day = _local_day()
    lines, burned, idle = [], 0, 0
    idle_providers: set[str] = set()
    for name in sorted(vendors):
        v = vendors[name]
        if not isinstance(v, dict):
            continue
        verdict, was_burned = _verdict(v)
        if was_burned:
            burned += 1
        elif "IDLE" in verdict:
            idle += 1
            idle_providers.add(str(name))
        lines.append(f"  {name:9} {verdict}")
    routing_reason, routing_detail = _routing_reason(
        target_providers=idle_providers if idle_providers else None,
        session_value_gate=session_value_gate,
    )
    disc = _discovery_count()
    tracked = burned + idle
    # Actionable admission truth outranks the burn-rate summary: an idle lane with admitted
    # work must never be headlined as FULL FORCE while the macOS notification hides the route.
    if idle and routing_reason == "routable":
        headline = f"ROUTABLE WORK EXISTS — fleet admission is open while {idle} lane(s) are idle"
    elif tracked and burned >= max(1, tracked - 1):
        headline = f"FULL FORCE — {burned}/{len(lines)} lanes burned to the drops"
    elif idle:
        headline = f"IDLED — {idle} lane(s) sat at a full tank ({routing_reason})"
    else:
        headline = f"partial — {burned}/{len(lines)} lanes burned"
    if disc:
        headline += f"; {disc} repos in value-discovery"
    # the credit side: did the spend earn its keep? (the "was it worth my money?" answer)
    value = _value_verdict()
    body = f"Conducting report {day}\n{headline}\n  routing: {routing_reason} — {routing_detail}\n"
    if value:
        body += f"  value: {value}\n"
    corpus_state = _named_blocked_task("CONST-CORPUS-REFRESH")
    if corpus_state:
        body += f"  task: {corpus_state}\n"
    body += "\n".join(lines)
    return headline, body, day, routing_reason


def census() -> dict:
    """Counts-only public census for report liveness; no vendor names, task titles, or headlines."""
    usage = _load(USAGE, {}) or {}
    vendors = usage.get("vendors", {}) if isinstance(usage, dict) else {}
    vendor_rows = [row for row in vendors.values() if isinstance(row, dict)] if isinstance(vendors, dict) else []
    verdicts = [_verdict(row) for row in vendor_rows]
    return {
        "usage_present": USAGE.exists(),
        "vendor_count": len(vendor_rows),
        "vendors_with_headroom": sum(1 for row in vendor_rows if row.get("headroom_pct") is not None),
        "vendors_burned": sum(1 for _verdict_text, burned in verdicts if burned),
        "vendors_idle": sum(1 for verdict_text, _burned in verdicts if "IDLE" in verdict_text),
        "value_verdict_present": _value_verdict() is not None,
        "open_value_discovery": _discovery_count(),
        "state_present": STATE.exists(),
        # The public census is counts-only and must not run the writer-backed pre-dispatch gate.
        # Without that proof it also must not claim that a route is live.
        "routing_reason": _routing_reason(
            always_working_gate={
                "status": "unavailable",
                "reason": "not evaluated by counts-only census",
            }
        )[0],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="emit now even if already sent today")
    ap.add_argument("--print", dest="print_only", action="store_true", help="print only; no push")
    ap.add_argument("--census", action="store_true", help="print counts-only public census JSON")
    args = ap.parse_args(argv)
    if args.census:
        print(json.dumps(census(), indent=2, sort_keys=True))
        return 0

    day = _local_day()
    state = _load(STATE, {})
    if not args.force and not args.print_only and state.get("last_day") == day:
        return 0

    # Usage and admission are emitted by separate heartbeat rungs. Refresh the keeper
    # snapshot immediately before pairing them so a once-daily report cannot reuse a prior beat's
    # routing decision after budgets, auth, or worktree pressure changed.
    if not _refresh_admission():
        print("conducting-report: keeper admission refresh failed; delivery withheld")
        return 0
    session_value_gate = _session_value_admission()
    usage = _load(USAGE, {})
    if not isinstance(usage, dict):
        usage = {}
    headline, body, day, routing_reason = build_report(
        session_value_gate=session_value_gate,
        usage_snapshot=usage,
    )
    print(body)
    if args.print_only:
        return 0

    instant = datetime.now(timezone.utc)
    if not _fresh_timestamp(usage, instant):
        print("conducting-report: usage telemetry unavailable or stale; delivery withheld")
        return 0
    usage_generated = str(usage.get("generated") or usage.get("generated_at"))

    macos = _notify_macos("Limen — conducting", headline, day, force=args.force)
    retry_ntfy = macos.reserved or (
        macos.status == "duplicate" and getattr(macos, "prior_status", None) in {"delivery_failed", "withheld"}
    )
    ntfy = _notify_ntfy("Limen — conducting", body) if retry_ntfy else False
    macos_settled = macos.status == "emitted" or (
        macos.status == "duplicate" and getattr(macos, "prior_status", None) == "emitted"
    )
    if not macos_settled and not ntfy:
        print(f"conducting-report: delivery not recorded ({macos.status})")
        return 0
    try:
        STATE.write_text(
            json.dumps(
                {
                    "last_day": day,
                    "usage_generated": usage_generated,
                    "headline": headline,
                    "routing_reason": routing_reason,
                }
            )
        )
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
