# Overnight Watch

- Status: `alert`
- Updated: `2026-08-19T13:17:46+00:00`
- Log age: `89` seconds
- Launchd: `active`
- Latest tick: `None`
- Latest async: `None`
- Stale tick samples: `54`
- Active workers: `0`
- Heartbeat child processes: `1`

## Overnight Summary

- Launched: `0`; harvested: `0`; reaped: `0`.
- Done: `0`; failed: `0`; no-op: `0`; timed out: `0`.
- Stale handoff: `true`.
- Gate action: `bootstrap_idle_dispatch` (exit `0`).
- Dispatch allowed: `false`.
- Lane switch: `not_requested`; owner packet: `none`; tickets: `0`.
- Lane blocker: `none`.
- Next command: `python3 scripts/handoff-relay.py && python3 scripts/handoff-relay.py --check`.

## Gate Checks

- Handoff refresh: `0`; check: `1`.
- Value gate: `0`; action: `bootstrap_idle_dispatch`.
- Dispatch control: handoff relay check failed; refresh handoff before launching workers.
- Selected owner: `none`.

## Throughput

- Recent per-60min completions: `[0, 0, 0]` (derived floor `0.0`, median `0`).
- Below floor: `false`; suppressed: `no`.
  - child `1297` `S` `01-23:09:51` `/bin/bash /Users/4jp/Workspace/limen/scripts/heartbeat-loop.sh`

## WATCH_ALERT
- `heartbeat-tick-missing`: no tick emitted line found in recent heartbeat log
- `handoff-relay-stale`: handoff-relay --check: FAIL — provider headroom stale (2603m > 90m)
