# Overnight Watch

- Status: `alert`
- Updated: `2026-08-21T11:38:05+00:00`
- Log age: `22` seconds
- Launchd: `active`
- Latest tick: `tick emitted: 2026-08-21T04:06:06+00:00 total=3184 open=884 spent=8/600`
- Latest async: `None`
- Stale tick samples: `6`
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

- Handoff refresh: `1`; check: `1`.
- Value gate: `0`; action: `bootstrap_idle_dispatch`.
- Dispatch control: handoff relay check failed; refresh handoff before launching workers.
- Selected owner: `none`.

## Throughput

- Recent per-60min completions: `[0, 0, 0]` (derived floor `0.0`, median `0.0`).
- Below floor: `false`; suppressed: `no`.
  - child `56095` `S` `01-21:50:01` `/bin/bash /Users/4jp/Workspace/limen/scripts/heartbeat-loop.sh`

## WATCH_ALERT
- `handoff-relay-stale`: handoff-relay --check: FAIL — provider headroom stale (959m > 90m)
