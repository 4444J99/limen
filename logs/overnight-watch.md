# Overnight Watch

- Status: `alert`
- Updated: `2026-08-05T13:59:34+00:00`
- Log age: `117` seconds
- Launchd: `active`
- Latest tick: `None`
- Latest async: `None`
- Stale tick samples: `918`
- Active workers: `0`
- Heartbeat child processes: `1`

## Overnight Summary

- Launched: `0`; harvested: `0`; reaped: `0`.
- Done: `0`; failed: `0`; no-op: `0`; timed out: `0`.
- Stale handoff: `true`.
- Gate action: `stop_no_durable_progress` (exit `20`).
- Dispatch allowed: `false`.
- Lane switch: `blocked`; owner packet: `none`; tickets: `0`.
- Lane blocker: `overnight-handoff-blocked`.
- Next command: `python3 scripts/handoff-relay.py && python3 scripts/handoff-relay.py --check`.

## Gate Checks

- Handoff refresh: `0`; check: `1`.
- Value gate: `20`; action: `stop_no_durable_progress`.
- Dispatch control: handoff relay is not fresh enough to transfer one owner packet.
- Selected owner: `organvm/limen`.

## Throughput

- Recent per-60min completions: `None` (derived floor `None`, median `None`).
- Below floor: `false`; suppressed: `no`.
  - child `2720` `S` `02-02:43:35` `/bin/bash /Users/4jp/Workspace/limen/scripts/heartbeat-loop.sh`

## WATCH_ALERT
- `heartbeat-tick-missing`: no tick emitted line found in recent heartbeat log
- `handoff-relay-stale`: handoff-relay --check: FAIL — provider headroom stale (4363m > 90m)
- `overnight-lane-switch-blocked`: blocker=overnight-handoff-blocked owner=organvm/limen reason=handoff relay is not fresh enough to transfer one owner packet
