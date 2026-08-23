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

import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _notify import NotificationResult, emit_event_v1, notify_event, notify_ntfy

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
VIEW = LOGS / "money-view.json"
STATE = LOGS / ".notify-state.json"
SHIP_BUCKETS = [10, 25, 50, 100]
_LOUD = {"deploy-ready", "live", "monetized"}


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


def main():
    view = _load(VIEW, None)
    if not view:
        return 0  # no feed yet -> nothing to do
    prev = _load(STATE, {})
    prev_stages = prev.get("stages", {})
    today = datetime.now().strftime("%Y-%m-%d")
    prev_bucket = prev.get("ship_bucket", 0) if prev.get("ship_date") == today else 0

    events = []
    structured_results = []
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
    ships = (view.get("ships_24h") or {}).get("total", 0)
    cur_bucket = max([b for b in SHIP_BUCKETS if ships >= b], default=0)
    if cur_bucket > prev_bucket:
        observed_at = datetime.now()
        receipt = emit_event_v1(
            ROOT,
            stable_id="limen.shipping.threshold",
            transition="milestone",
            subject_key=f"{today}:{cur_bucket}",
            event_id=f"shipping-{today}-{cur_bucket}",
            facts={"threshold": cur_bucket, "observed": ships, "snapshot_time": observed_at.strftime("%H:%M")},
            evidence_ref=str(VIEW),
            producer="scripts/notify-events.py",
        )
        structured_results.append(receipt)
        print(f"[notify:{receipt.status}] shipping: crossed {cur_bucket}; {ships} observed at {observed_at:%H:%M}")

    results = [_emit(f"LIMEN {title}", msg) for title, msg in events]

    structured_settled = all(
        result.status in {"delivered", "deduped", "recorded", "withheld"} for result in structured_results
    )
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
