#!/usr/bin/env python3
"""notify-events.py — the push face of the money view. Comes to you so you don't have to look.

Each beat it diffs logs/money-view.json against the last emitted state (logs/.notify-state.json) and
fires ONLY on events that matter:
  • a product reaches deploy-ready / live / monetized  (a stage transition)
  • YOUR gate becomes ready  (a 'yours' product hits deploy-ready/live — your move = first dollar)
  • a ship milestone in the last 24h (10 / 25 / 50 / 100 PRs)

Delivery is CASCADED (never-"NO"): local macOS notification (osascript, best-effort) AND, if
LIMEN_NTFY_TOPIC is set, a free ntfy.sh push to your phone (subscribe to the topic in the ntfy app —
works at the pool / on the road). Quiet by default: nothing changes -> nothing fires. Fail-open: a
missing feed or a network error skips silently, never crashes the beat.
"""

import argparse
import json
import os
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli" / "src"))

from _notify import NotificationResult, emit_event_v1, notify_event, notify_ntfy
from _ships_24h import read_ships_24h
from limen.universe_recovery import UniverseBaselineReceiptV1

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
VIEW = LOGS / "money-view.json"
STATE = LOGS / ".notify-state.json"
BASELINE = ROOT / "docs" / "receipts" / "universe-baseline.json"
CANARY_RECEIPT = LOGS / "notification-canary-receipt.json"
RECORDING_CANARY_RECEIPT = LOGS / "notification-recording-canary-receipt.json"
CANARY_RECORDING = LOGS / "notification-recording-canary.jsonl"
CANARY_RECORDING_LEDGER = LOGS / "notification-recording-canary-ledger.json"
SHIP_BUCKETS = [10, 25, 50, 100]
_LOUD = {"deploy-ready", "live", "monetized"}
MAX_BASELINE_AGE_HOURS = 24.0


def _load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def _notify_macos(title, msg):
    return notify_event(
        ROOT,
        source="money-view",
        event=title,
        message=msg,
        title=title,
        payload={"message": msg},
    )


def _notify_ntfy(title, msg):
    return notify_ntfy(ROOT, msg, title=title, tags="money_with_wings")


def _emit(title, msg) -> NotificationResult:
    result = _notify_macos(title, msg)
    pushed = _notify_ntfy(title, msg) if result.reserved else False
    print(f"[notify:{result.status}{'+ntfy' if pushed else ''}] {title}: {msg}")
    return result


def _event_settled(result: NotificationResult) -> bool:
    """Whether advancing source state can no longer lose this notification event."""
    return result.reserved or result.status == "duplicate"


def _structured_event_settled(result) -> bool:
    accepted = getattr(result, "accepted", None)
    if isinstance(accepted, bool):
        return accepted or result.status == "withheld"
    return result.status in {
        "submitted",
        "submitted_unverified",
        "deduped",
        "recorded",
        "cleared",
        "withheld",
    }


def _baseline_status(now: datetime | None = None):
    observed_now = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        receipt = UniverseBaselineReceiptV1.model_validate_json(BASELINE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"state": "unavailable", "receipt": None, "reason": "aggregate receipt unavailable"}
    except (OSError, ValueError) as exc:
        return {"state": "invalid", "receipt": None, "reason": f"aggregate receipt invalid: {exc}"}
    age_hours = max(0.0, (observed_now - receipt.observed_at).total_seconds() / 3600.0)
    if age_hours > MAX_BASELINE_AGE_HOURS:
        state = "stale"
        reason = f"aggregate receipt is {age_hours:.1f}h old"
    elif not receipt.complete:
        state = "incomplete"
        reason = f"census has {receipt.failure_count} failures and {receipt.unaccounted} unaccounted leaves"
    else:
        state = "complete"
        reason = "fresh complete aggregate receipt"
    return {"state": state, "receipt": receipt, "reason": reason, "age_hours": round(age_hours, 2)}


def _partition(receipt, kind):
    return next(row for row in receipt.partitions if row.kind == kind)


def _estate_event_specs(status):
    receipt = status.get("receipt")
    state = status["state"]
    now = datetime.now(UTC)
    snapshot_time = now.astimezone().strftime("%H:%M")
    complete = state == "complete"
    unavailable = "count unavailable/incomplete"
    if receipt is None:
        observation = now.isoformat().replace("+00:00", "Z")
        generation = f"unavailable-{state}"
        open_or_blocked_prs = unavailable
        stable_repositories = unavailable
        total_repositories = unavailable
        branch_debt = unavailable
        worktree_debt = unavailable
    else:
        observation = receipt.observed_at.isoformat().replace("+00:00", "Z")
        generation = receipt.source_generation
        pulls = _partition(receipt, "pull_requests")
        branches = _partition(receipt, "branches")
        worktrees = _partition(receipt, "worktrees")
        open_or_blocked_prs = pulls.blocked + pulls.protected if complete else unavailable
        stable_repositories = receipt.stable_count if complete else unavailable
        total_repositories = receipt.repository_denominator if complete else unavailable
        branch_debt = branches.blocked + branches.protected + branches.unaccounted if complete else unavailable
        worktree_debt = worktrees.blocked + worktrees.protected + worktrees.unaccounted if complete else unavailable
    facts = {
        "snapshot_time": snapshot_time,
        "census_status": state,
        "prs_landed_batch": unavailable,
        "prs_landed_generation": unavailable,
        "open_or_blocked_prs": open_or_blocked_prs,
        "stable_repositories": stable_repositories,
        "total_repositories": total_repositories,
        "branch_debt": branch_debt,
        "worktree_debt": worktree_debt,
        "observation_timestamp": observation,
    }
    specs = [
        {
            "stable_id": "limen.estate.progress",
            "transition": "summary",
            "subject_key": f"{generation}:{state}",
            "event_id": f"estate-progress-{generation[:20]}-{state}",
            "facts": facts,
            "evidence_ref": str(BASELINE),
            "producer": "scripts/notify-events.py",
        }
    ]
    specs.append(
        {
            "stable_id": "limen.estate.integrity",
            "transition": "clear" if complete else "onset",
            "subject_key": "universe-baseline",
            "event_id": f"estate-integrity-{generation[:20]}-{state}",
            "facts": {
                "census_status": state,
                "observation_timestamp": observation,
                "reason": status["reason"],
            },
            "evidence_ref": str(BASELINE),
            "producer": "scripts/notify-events.py",
        }
    )
    return specs


def _status_payload():
    status = _baseline_status()
    receipt = status.get("receipt")
    complete = status["state"] == "complete"
    counts = None
    if receipt is not None and complete:
        pulls = _partition(receipt, "pull_requests")
        branches = _partition(receipt, "branches")
        worktrees = _partition(receipt, "worktrees")
        counts = {
            "stable_repositories": receipt.stable_count,
            "repository_denominator": receipt.repository_denominator,
            "open_or_blocked_prs": pulls.blocked + pulls.protected,
            "remaining_branch_debt": branches.blocked + branches.protected + branches.unaccounted,
            "remaining_worktree_debt": worktrees.blocked + worktrees.protected + worktrees.unaccounted,
        }
    canary = {
        "recording": _load(RECORDING_CANARY_RECEIPT, None),
        "macos": _load(CANARY_RECEIPT, None),
    }
    return {
        "schema": "limen.notification-status.v1",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "census": {
            "status": status["state"],
            "reason": status["reason"],
            "counts": counts,
            "count_display": "available" if counts is not None else "count unavailable/incomplete",
        },
        "transports": {
            "macos": "submission_only_visible_delivery_unverified",
            "ntfy": "configured" if os.environ.get("LIMEN_NTFY_TOPIC") else "not_configured",
        },
        "canary": canary,
    }


def _write_canary(payload, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _recording_contains_event(path, event_id):
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and isinstance(row.get("event"), dict):
            if row["event"].get("event_id") == event_id:
                return True
    return False


def _run_canary(mode):
    observed = datetime.now(UTC)
    stamp = observed.strftime("%Y%m%dT%H%M%SZ")
    event_id = f"notification-canary-{mode}-{stamp}"
    canary_receipt = RECORDING_CANARY_RECEIPT if mode == "recording" else CANARY_RECEIPT
    broker_environ = None
    if mode == "recording":
        broker_environ = dict(os.environ)
        broker_environ.update(
            {
                "DOMUS_NOTIFY": "0",
                "DOMUS_NOTIFY_RECORDING": str(CANARY_RECORDING),
                "DOMUS_NOTIFY_RECORDING_LEDGER": str(CANARY_RECORDING_LEDGER),
            }
        )
    receipt = emit_event_v1(
        ROOT,
        stable_id="limen.notification.canary",
        transition="milestone",
        subject_key=event_id,
        event_id=event_id,
        facts={"canary_mode": mode, "snapshot_time": observed.strftime("%H:%M")},
        evidence_ref=str(canary_receipt),
        producer="scripts/notify-events.py",
        observed_at=observed.isoformat().replace("+00:00", "Z"),
        level="normal",
        environ=broker_environ,
    )
    broker_accepted = receipt.status in {
        "submitted",
        "submitted_unverified",
        "deduped",
        "recorded",
    }
    recording_accepted = (
        receipt.status == "recorded" and _recording_contains_event(CANARY_RECORDING, event_id)
        if mode == "recording"
        else None
    )
    canary_accepted = recording_accepted if mode == "recording" else broker_accepted
    payload = {
        "schema": "limen.notification-canary-receipt.v1",
        "event_id": event_id,
        "mode": mode,
        "submitted_at": observed.isoformat().replace("+00:00", "Z"),
        "broker_status": receipt.status,
        "broker_accepted": broker_accepted,
        "broker_invoked": receipt.broker_invoked,
        "reason": receipt.reason,
        "channels": receipt.channels,
        "recording_accepted": recording_accepted,
        "recording_evidence": str(CANARY_RECORDING) if mode == "recording" else None,
        "visible_acceptance": "pending_operator" if mode == "macos" else "not_applicable_recording_only",
        "visible_observed_at": None,
    }
    _write_canary(payload, canary_receipt)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if canary_accepted else 1


def _confirm_macos_canary(event_id):
    payload = _load(CANARY_RECEIPT, None)
    if not isinstance(payload, dict) or payload.get("event_id") != event_id or payload.get("mode") != "macos":
        print("macOS canary confirmation refused: no matching submitted canary", file=sys.stderr)
        return 1
    payload["visible_acceptance"] = "observed_by_operator"
    payload["visible_observed_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    _write_canary(payload, CANARY_RECEIPT)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--status", action="store_true", help="report census and transport truth without emitting")
    mode.add_argument("--recording-canary", action="store_true", help="submit a silent recording-backend canary")
    mode.add_argument("--macos-canary", action="store_true", help="submit a macOS canary and leave acceptance pending")
    mode.add_argument("--confirm-macos-canary", metavar="EVENT_ID", help="record operator-observed acceptance")
    parser.add_argument("--dry-run", action="store_true", help="show candidate events without emitting or writing state")
    args = parser.parse_args([] if argv is None else argv)
    if args.status:
        print(json.dumps(_status_payload(), indent=2, sort_keys=True))
        return 0
    if args.recording_canary:
        return _run_canary("recording")
    if args.macos_canary:
        return _run_canary("macos")
    if args.confirm_macos_canary:
        return _confirm_macos_canary(args.confirm_macos_canary)

    view = _load(VIEW, None)
    if not view:
        return 0  # no feed yet -> nothing to do
    prev = _load(STATE, {})
    prev_stages = prev.get("stages", {})
    today = datetime.now().strftime("%Y-%m-%d")
    prev_bucket = prev.get("ship_bucket", 0) if prev.get("ship_date") == today else 0

    events = []
    structured_results = []
    structured_specs = []
    cur_stages = {}
    for p in view.get("products", []):
        repo, stage = p.get("repo", ""), p.get("stage", "")
        # keyed by repo::product — several products share a repo, and a bare-repo key
        # made them overwrite each other's state, re-firing the same "transition" every beat
        key = f"{repo}::{p.get('product', '')}"
        cur_stages[key] = stage
        before = prev_stages.get(key)
        if before is not None and before != stage and stage in _LOUD:
            if p.get("whose_hand") == "yours":
                events.append(("⟶ YOUR MOVE", f"{p.get('product')} is {stage} — {p.get('next_action', '')} = first $"))
            else:
                events.append(("milestone", f"{p.get('product')} reached {stage}"))

    # ship milestone (rolling 24h; only fire when crossing a NEW higher bucket today)
    ships, _, _ = read_ships_24h(ROOT)
    cur_bucket = max([b for b in SHIP_BUCKETS if ships >= b], default=0)
    if cur_bucket > prev_bucket:
        observed_at = datetime.now()
        structured_specs.append(
            {
                "stable_id": "limen.shipping.threshold",
                "transition": "milestone",
                "subject_key": f"{today}:{cur_bucket}",
                "event_id": f"shipping-{today}-{cur_bucket}",
                "facts": {
                    "threshold": cur_bucket,
                    "observed": ships,
                    "snapshot_time": observed_at.strftime("%H:%M"),
                },
                "evidence_ref": str(ROOT / "logs" / "ships-24h.json"),
                "producer": "scripts/notify-events.py",
            }
        )

    estate_specs = _estate_event_specs(_baseline_status())
    structured_specs.extend(estate_specs)
    if args.dry_run:
        print(json.dumps({"events": events, "structured_events": structured_specs}, indent=2, sort_keys=True))
        return 0
    for spec in structured_specs:
        receipt = emit_event_v1(ROOT, **spec)
        structured_results.append(receipt)
        if spec["stable_id"] == "limen.shipping.threshold":
            print(f"[notify:{receipt.status}] shipping: crossed {cur_bucket}; {ships} observed at {observed_at:%H:%M}")
        else:
            print(f"[notify:{receipt.status}] {spec['stable_id']}: {spec['facts']['census_status']}")

    results = [_emit(f"LIMEN {title}", msg) for title, msg in events]

    structured_settled = all(_structured_event_settled(result) for result in structured_results)
    if all(_event_settled(result) for result in results) and structured_settled:
        STATE.write_text(
            json.dumps(
                {
                    "stages": cur_stages,
                    "ship_bucket": cur_bucket,
                    "ship_date": today,
                    "updated": datetime.now().isoformat(timespec="seconds"),
                },
                indent=2,
            )
        )
    else:
        print("[notify] source state withheld — an event reservation was not established")
    if not events:
        print("[notify] no change — quiet")
    return 0 if structured_settled else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
